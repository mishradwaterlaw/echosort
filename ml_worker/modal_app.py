"""
EchoSort Cloud ML Worker (Modal Serverless)
===========================================
Engine: InsightFace + ONNX Runtime on CPU
Architecture:
  - Container Image: Python 3.10 slim + compiled C++ ONNX Runtime
  - Pre-warmed Models: SCRFD-10G (detector) + ArcFace ResNet50 (embedder) baked into image
  - Schedule: Periodic wake-up (every 30s) or on-demand trigger
  - Priority Queue: Drains interactive match_jobs (attendee waiting) BEFORE bulk embedding_jobs
"""

import modal

# Step 1: Pre-warm models during Docker build phase
def download_models():
    """
    Downloads and compiles InsightFace ONNX models during image build.
    This guarantees zero cold-start network downloads at runtime.
    """
    import numpy as np
    from insightface.app import FaceAnalysis

    print("Pre-warming InsightFace buffalo_l (SCRFD + ArcFace) into container...")
    app = FaceAnalysis(name="buffalo_l", providers=["CPUExecutionProvider"])
    app.prepare(ctx_id=-1, det_size=(640, 640))

    # Run inference on a blank dummy frame to compile the ONNX execution graph
    dummy_img = np.zeros((640, 640, 3), dtype=np.uint8)
    app.get(dummy_img)
    print("InsightFace models successfully cached in /root/.insightface!")


# Step 2: Define container image without bloated TensorFlow/GPU packages
image = (
    modal.Image.debian_slim(python_version="3.10")
    .apt_install(
        "libgl1",          # Required by opencv-python-headless
        "libglib2.0-0",    # Required by image codecs
    )
    .pip_install(
        "insightface",
        "onnxruntime",     # High-speed C++ CPU vector inference (AVX-512)
        "supabase",
        "upstash-redis",
        "numpy",
        "opencv-python-headless",
        "python-dotenv",
    )
    .run_function(download_models)
    .add_local_file("job_runner.py", "/root/job_runner.py")
    .add_local_file("embedder.py", "/root/embedder.py")
)

app = modal.App("echosort-worker", image=image)
secrets = [modal.Secret.from_name("facefind-secrets")]


@app.function(
    cpu=2.0,            # Efficient 2-core CPU container (No expensive GPU needed!)
    memory=1024,        # Only 1GB RAM needed (TensorFlow needed 4GB+)
    secrets=secrets,
    timeout=600,
    schedule=modal.Period(seconds=30),
)
def process_jobs():
    import json
    import os
    from supabase import create_client
    from upstash_redis import Redis
    
    from job_runner import (
        init_stream_groups,
        drain_stream_priority,
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

    # Ensure consumer groups are initialized
    init_stream_groups(redis)

    # Drain streams with crash-recovery (XAUTOCLAIM) and priority queueing
    while drain_stream_priority(supabase, redis):
        pass


@app.local_entrypoint()
def main():
    process_jobs.remote()
