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

    Q3: Why update status to 'processing' at the start? TODO() make a cronjob for this shit
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

        # Step 6: Batch insert all detected faces in a single atomic HTTP request
        # This replaces N sequential network roundtrips with a single batch payload,
        # preventing partial insertion states and cutting database latency by ~90%.
        embeddings_batch = [
            {
                "photo_id": photo_id,
                "event_id": job["event_id"],
                "embedding": face["embedding"],
                "confidence": face["confidence"],
            }
            for face in faces
        ]

        supabase.table("face_embeddings").insert(embeddings_batch).execute()

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

        # Step 6: Select the prominent foreground subject (Bounding Box Area * Confidence)
        # Background faces, posters, or distant bystanders might have high confidence,
        # but the primary attendee taking the selfie occupies the largest pixel area (w * h).
        def face_prominence_score(face):
            area = face["facial_area"].get("w", 0) * face["facial_area"].get("h", 0)
            return area * face["confidence"]

        faces.sort(key=face_prominence_score, reverse=True)
        query_embedding = faces[0]["embedding"]

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


CONSUMER_GROUP = "echosort_workers"
CONSUMER_NAME = f"worker_{os.getpid()}"


def init_stream_groups(redis: Redis) -> None:
    """
    Idempotently initializes consumer groups for both Redis streams.
    'mkstream=True' creates the stream if it does not exist yet.
    """
    for stream in ["stream:match_jobs", "stream:embedding_jobs"]:
        try:
            redis.xgroup_create(stream, CONSUMER_GROUP, id="0", mkstream=True)
            logger.info(f"Initialized Redis Stream consumer group '{CONSUMER_GROUP}' on '{stream}'")
        except Exception:
            # Group already exists (BUSYGROUP in Redis), which is expected on subsequent runs
            pass


def process_stream_job(supabase: Client, redis: Redis, stream_name: str, msg_id: str, data: dict) -> None:
    """
    Processes one message from a Redis Stream and sends an acknowledgment (XACK) upon success.
    If an unhandled crash or exception occurs, the message is NOT acked, preserving it in
    the Pending Entries List (PEL) to be reclaimed by a surviving worker.
    """
    payload_str = data.get("payload") if isinstance(data, dict) else None
    if not payload_str:
        logger.warning(f"Malformed stream entry {msg_id} on {stream_name}. ACKing to purge.")
        redis.xack(stream_name, CONSUMER_GROUP, msg_id)
        return

    job = json.loads(payload_str)

    if stream_name == "stream:match_jobs":
        process_match_job(supabase, job)
    else:
        process_embedding_job(supabase, job)

    # Acknowledge completion — removes the message from the Pending Entries List (PEL)
    redis.xack(stream_name, CONSUMER_GROUP, msg_id)
    logger.info(f"ACKed stream job {msg_id} on {stream_name}")


def drain_stream_priority(supabase: Client, redis: Redis) -> bool:
    """
    Processes stream jobs with Priority and Crash-Recovery:
    1. Reclaims orphaned jobs from dead workers via XAUTOCLAIM.
    2. Reads new unread jobs via XREADGROUP.
    3. Always prioritizes interactive attendee selfies (stream:match_jobs) over bulk uploads.

    Error Handling Design (two distinct failure types):
    - Redis infrastructure errors (xreadgroup/xautoclaim fails): caught here, logged, skip to next stream.
      These are transient network issues — we don't want one bad Redis call to crash the whole worker.
    - Job processing errors (embedding crash, DB write fail): NOT caught here.
      They're caught inside process_stream_job, which already marks the DB row as 'failed' and
      re-raises. The re-raised exception propagates to run_worker(), which lets the loop
      continue on to the next iteration. The message stays in the PEL for XAUTOCLAIM recovery.

    Returns:
        True if a job was processed; False if both queues are idle.
    """
    # -------------------------------------------------------------------------
    # Priority 1: Interactive Attendee Selfies (stream:match_jobs)
    # -------------------------------------------------------------------------
    # 1a. Reclaim any match jobs orphaned by a crashed worker (> 60s idle)
    try:
        claimed = redis.xautoclaim("stream:match_jobs", CONSUMER_GROUP, CONSUMER_NAME, 60000, "0-0", count=5)
        if claimed and len(claimed) > 1 and claimed[1]:
            for msg_id, data in claimed[1]:
                logger.info(f"Reclaimed orphaned match job {msg_id} via XAUTOCLAIM")
                process_stream_job(supabase, redis, "stream:match_jobs", msg_id, data)
            return True
    except Exception as e:
        # XAUTOCLAIM failing is an infrastructure issue (stream may not exist yet, network blip).
        # Log at debug level — this fires on every startup before the first job arrives.
        logger.debug(f"xautoclaim match_jobs check: {e}")

    # 1b. Read new unread match jobs
    try:
        entries = redis.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {"stream:match_jobs": ">"}, count=1)
    except Exception as e:
        # XREADGROUP failing = Redis infrastructure error (connection drop, auth issue).
        # This is separate from a job processing failure — log it and try the embedding stream.
        logger.error(f"Infrastructure error reading stream:match_jobs: {e}")
        entries = None

    if entries:
        for stream, messages in entries:
            for msg_id, data in messages:
                # process_stream_job re-raises on job failure — intentionally NOT caught here.
                # The message stays in the PEL; XAUTOCLAIM will reclaim it after 60s.
                process_stream_job(supabase, redis, stream, msg_id, data)
        return True

    # -------------------------------------------------------------------------
    # Priority 2: Background Bulk Photo Uploads (stream:embedding_jobs)
    # -------------------------------------------------------------------------
    # 2a. Reclaim any embedding jobs orphaned by a crashed worker (> 120s idle)
    try:
        claimed = redis.xautoclaim("stream:embedding_jobs", CONSUMER_GROUP, CONSUMER_NAME, 120000, "0-0", count=5)
        if claimed and len(claimed) > 1 and claimed[1]:
            for msg_id, data in claimed[1]:
                logger.info(f"Reclaimed orphaned embedding job {msg_id} via XAUTOCLAIM")
                process_stream_job(supabase, redis, "stream:embedding_jobs", msg_id, data)
            return True
    except Exception as e:
        logger.debug(f"xautoclaim embedding_jobs check: {e}")

    # 2b. Read new unread embedding jobs
    try:
        entries = redis.xreadgroup(CONSUMER_GROUP, CONSUMER_NAME, {"stream:embedding_jobs": ">"}, count=5)
    except Exception as e:
        logger.error(f"Infrastructure error reading stream:embedding_jobs: {e}")
        entries = None

    if entries:
        for stream, messages in entries:
            for msg_id, data in messages:
                process_stream_job(supabase, redis, stream, msg_id, data)
        return True

    return False


def run_worker():
    """
    Main worker loop for local or persistent VPS execution.
    Runs continuously, processing jobs with sub-second latency and zero job loss.
    """
    validate_env()
    supabase, redis = get_clients()
    init_stream_groups(redis)

    logger.info(f"Worker {CONSUMER_NAME} online — listening on Redis Streams with Consumer Group '{CONSUMER_GROUP}'")

    while True:
        processed_something = drain_stream_priority(supabase, redis)
        if not processed_something:
            # Idle sleep: prevents spinning the CPU when streams are empty
            time.sleep(1)


if __name__ == "__main__":
    logger.info("Starting EchoSort ML Stream Worker...")
    run_worker()
