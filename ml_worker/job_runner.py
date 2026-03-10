import json
import logging
import time
import os
import numpy as np
from dotenv import load_dotenv
from supabase import create_client, Client
from upstash_redis import Redis
from embedder import get_faces_and_embeddings, bytes_to_image

# Load .env before os.getenv() calls
load_dotenv()

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
SUPABASE_URL = os.getenv("SUPABASE_URL")
SUPABASE_SERVICE_ROLE_KEY = os.getenv("SUPABASE_SERVICE_ROLE_KEY")
UPSTASH_REDIS_URL = os.getenv("UPSTASH_REDIS_URL")
UPSTASH_REDIS_TOKEN = os.getenv("UPSTASH_REDIS_TOKEN")

MATCH_THRESHOLD = 0.6
MATCH_COUNT = 20


def validate_env():
    """
    Ensure all required environment variables are present before starting.
    Clean startup failure beats mysterious runtime crashes.
    """
    required = [
        "SUPABASE_URL", 
        "SUPABASE_SERVICE_ROLE_KEY",
        "UPSTASH_REDIS_URL", 
        "UPSTASH_REDIS_TOKEN"
    ]
    missing = [var for var in required if not os.getenv(var)]
    if missing:
        raise EnvironmentError(f"Missing required env vars: {missing}")


def get_clients():
    """Initialize and return Supabase and Redis clients."""
    supabase = create_client(SUPABASE_URL, SUPABASE_SERVICE_ROLE_KEY)
    redis = Redis(url=UPSTASH_REDIS_URL, token=UPSTASH_REDIS_TOKEN)
    return supabase, redis


def download_image(supabase: Client, bucket: str, path: str) -> bytes:
    """
    Download a file from Supabase Storage.
    Returns raw bytes.
    """
    return supabase.storage.from_(bucket).download(path)


def process_embedding_job(supabase: Client, job: dict) -> None:
    """
    Handles one job from the embedding_jobs queue.

    Job shape: {
        "photo_id": str,
        "event_id": str,
        "storage_path": str
    }

    Q3: Why update status to 'processing' at the start?
    A3: If this worker crashes mid-job (OOM, network drop, machine restart),
        any job still showing status='pending' can be safely retried by another
        worker or a future restart. Jobs showing 'processing' that stay stuck
        too long can be identified and re-queued by a cron job. Without this,
        a crash leaves the photo silently stuck as 'pending' forever with no way
        to distinguish "not yet started" from "started but died".

    Q4: Why is a photo with no faces → 'done' (not 'failed')?
    A4: It's a completely valid outcome. Event photos (group shots, landscapes,
        crowd scenes) may genuinely have no detectable faces. Marking them 'done'
        means "fully processed — nothing actionable found". Marking them 'failed'
        would imply the worker crashed or the photo was corrupt, which would
        be misleading and might trigger unnecessary retries.
    """
    photo_id = job["photo_id"]
    storage_path = job["storage_path"]

    try:
        # Step 1: Mark as processing before we do any real work (see Q3 above)
        supabase.table("photos").update(
            {"embedding_status": "processing"}
        ).eq("id", photo_id).execute()

        # Step 2: Download raw bytes from Storage
        image_bytes = download_image(supabase, "photos", storage_path)

        # Step 3: Convert to OpenCV numpy array
        img = bytes_to_image(image_bytes)

        # Step 4: Detect faces and generate 512D embeddings
        faces = get_faces_and_embeddings(img)

        # Step 5: No faces is a valid outcome for event photos (see Q4 above)
        if not faces:
            logger.info(f"No faces found in photo {photo_id} — marking as done")
            supabase.table("photos").update(
                {"embedding_status": "done"}
            ).eq("id", photo_id).execute()
            return

        # Step 6: Insert one row per face into face_embeddings
        for face in faces:
            # Q2: Why store the embedding as a plain Python list and not a numpy array?
            # A2: JSON serialization. Supabase's Python client sends data as JSON to
            # the REST API. numpy arrays are NOT JSON-serializable — json.dumps(np.array([...]))
            # will raise TypeError. .tolist() converts each float64 element to a native
            # Python float that json can handle. pgvector receives it as a JSON array
            # and casts it to vector(512) on the Postgres side.
            embedding_list = np.array(face["embedding"]).tolist()

            supabase.table("face_embeddings").insert({
                "photo_id": photo_id,
                "event_id": job["event_id"],
                "embedding": embedding_list,
                "confidence": face["confidence"],
            }).execute()

        # Step 7: Mark photo as fully processed
        supabase.table("photos").update(
            {"embedding_status": "done"}
        ).eq("id", photo_id).execute()

        logger.info(f"Embedded {len(faces)} face(s) for photo {photo_id}")

    except Exception as e:
        logger.error(f"Embedding job failed for photo {photo_id}: {e}")
        supabase.table("photos").update(
            {"embedding_status": "failed"}
        ).eq("id", photo_id).execute()
        raise


def process_match_job(supabase: Client, job: dict) -> None:
    """
    Handles one job from the match_jobs queue.

    Job shape: {
        "request_id": str,
        "event_id": str,
        "selfie_path": str
    }

    Q1: Why sort by confidence and take faces[0] instead of just faces[0]?
    A1: get_faces_and_embeddings() returns faces in detection order, which is
        determined by the spatial layout in the image (left-to-right, top-to-bottom),
        not by confidence score. If there are multiple people in the selfie frame,
        the first detected face might be a shoulder or partially-visible bystander
        with a low confidence score. Sorting descending by confidence first ensures
        we always pick the most clearly-detected face — almost certainly the person
        who intentionally took the selfie.

    Q4 (selfie side): Why is no face in a selfie → 'failed' (not 'done')?
    A4: The selfie's entire purpose is to carry a face for matching. If we can't
        detect a face, the match is impossible and there's nothing to return to
        the user. This is genuinely an error requiring user action (retake the
        selfie). Contrast with an event photo where having no face is plausible
        and expected.
    """
    request_id = job["request_id"]
    selfie_path = job["selfie_path"]
    event_id = job["event_id"]

    try:
        # Step 1: Mark as processing before doing real work
        supabase.table("match_requests").update(
            {"status": "processing"}
        ).eq("id", request_id).execute()

        # Step 2: Download selfie bytes
        image_bytes = download_image(supabase, "selfies", selfie_path)

        # Step 3: Convert to OpenCV numpy array
        img = bytes_to_image(image_bytes)

        # Step 4: Detect faces and generate embeddings
        faces = get_faces_and_embeddings(img)

        # Step 5: A selfie MUST have a face — this is a user error, not a valid outcome
        if not faces:
            logger.warning(f"No face detected in selfie for match request {request_id}")
            supabase.table("match_requests").update(
                {"status": "failed"}
            ).eq("id", request_id).execute()
            return

        # Step 6: Take the highest-confidence face (see Q1 above)
        faces.sort(key=lambda x: x["confidence"], reverse=True)
        query_embedding = np.array(faces[0]["embedding"]).tolist()

        # Step 7: Run pgvector similarity search via Supabase RPC
        # This calls a Postgres function `match_faces` that does:
        # SELECT photo_id FROM face_embeddings
        # WHERE event_id = $event_id
        # ORDER BY embedding <=> $query_embedding
        # LIMIT $match_count
        rpc_response = supabase.rpc("match_faces", {
            "query_embedding": query_embedding,
            "match_event_id": event_id,
            "match_threshold": MATCH_THRESHOLD,
            "match_count": MATCH_COUNT,
        }).execute()

        # Step 8: Deduplicate photo_ids from results
        # A photo can have multiple faces, so multiple rows might point to the same photo
        matched_photo_ids = list({
            row["photo_id"]
            for row in (rpc_response.data or [])
        })

        # Step 9: Write results back and mark done
        supabase.table("match_requests").update({
            "result_photo_ids": matched_photo_ids,
            "status": "done",
        }).eq("id", request_id).execute()

        logger.info(f"Match request {request_id} completed — {len(matched_photo_ids)} photo(s) found")

    except Exception as e:
        logger.error(f"Match job failed for request {request_id}: {e}")
        supabase.table("match_requests").update(
            {"status": "failed"}
        ).eq("id", request_id).execute()
        raise


def run_worker():
    """
    Main worker loop. Runs forever.
    Checks both queues on each iteration.

    Using RPOP (Right POP) means jobs are processed in FIFO order —
    the API pushes with LPUSH (Left PUSH), so the oldest jobs come out first.
    """
    # Step 0: Validate environment before doing anything else
    validate_env()

    supabase, redis = get_clients()
    logger.info("Worker ready — listening on embedding_jobs and match_jobs")

    while True:
        try:
            job = redis.rpop("embedding_jobs")
            if job:
                process_embedding_job(supabase, json.loads(job))
        except Exception as e:
            logger.error(f"Embedding job failed: {e}")

        try:
            job = redis.rpop("match_jobs")
            if job:
                process_match_job(supabase, json.loads(job))
        except Exception as e:
            logger.error(f"Match job failed: {e}")

        # Sleep briefly to avoid hammering Redis when queues are empty
        time.sleep(20)


if __name__ == "__main__":
    logger.info("Starting FaceFind ML worker...")
    run_worker()
