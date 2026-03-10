import modal

# Step 1: Define the container image
# We pre-download models during the image build phase to avoid
# multi-gigabyte downloads every time the worker starts.
def download_models():
    from deepface import DeepFace
    # Pre-load the ArcFace recognition model weights into the image.
    # RetinaFace is a detector (not a recognition model) — it does not use
    # DeepFace.build_model() and will auto-download its weights on first use.
    DeepFace.build_model("ArcFace")

image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install(
        "libgl1",          # Provides libGL.so.1 — required by opencv-python-headless
        "libglib2.0-0",    # Required by certain OpenCV functions
    )
    .pip_install(
        "deepface",
        "retina-face",
        "supabase",
        "upstash-redis",
        "numpy",
        "opencv-python-headless",
        "python-dotenv",
        "tf-keras",
        "tensorflow", # Ensure tensorflow is present for deepface
    )
    .run_function(download_models)
    .add_local_file("job_runner.py", "/root/job_runner.py")
    .add_local_file("embedder.py", "/root/embedder.py")
)

app = modal.App("facefind-worker", image=image)
secrets = [modal.Secret.from_name("facefind-secrets")]

@app.function(
    gpu="T4",
    secrets=secrets,
    timeout=600,
    retries=2,
    schedule=modal.Period(seconds=30),
)
def process_jobs():
    import json
    import os
    from supabase import create_client
    from upstash_redis import Redis
    
    # These are in /root/ thanks to .add_local_file in the image definition above
    from job_runner import (
        process_embedding_job,
        process_match_job,
        validate_env,
    )

    validate_env()

    supabase = create_client(
        os.environ["SUPABASE_URL"],
        os.environ["SUPABASE_SERVICE_ROLE_KEY"],
    )
    redis = Redis(
        url=os.environ["UPSTASH_REDIS_URL"],
        token=os.environ["UPSTASH_REDIS_TOKEN"],
    )

    # Drain embedding_jobs
    while True:
        job = redis.rpop("embedding_jobs")
        if not job:
            break
        try:
            process_embedding_job(supabase, json.loads(job))
        except Exception as e:
            print(f"Embedding job failed: {e}")

    # Drain match_jobs
    while True:
        job = redis.rpop("match_jobs")
        if not job:
            break
        try:
            process_match_job(supabase, json.loads(job))
        except Exception as e:
            print(f"Match job failed: {e}")

@app.local_entrypoint()
def main():
    process_jobs.remote()
