"""
EchoSort High-Performance ML Embedder
====================================
Engine: InsightFace + ONNX Runtime (CPU SIMD-accelerated)
Models:
  - Face Detection: SCRFD (Sample and Computation Redistribution)
  - Face Embedding: ArcFace ResNet-50 (512-dimensional hypersphere)

Why this architecture:
  - Memory Footprint: ~100MB RAM (vs ~2GB in TensorFlow)
  - Latency: ~30-50ms per image on modern CPU (no GPU needed)
  - Distance Metric: Unit-normalized vectors for pgvector cosine distance (<=>)
"""

import cv2
import numpy as np
import logging
from typing import List, Dict, Any, Union
from functools import lru_cache
from insightface.app import FaceAnalysis

logger = logging.getLogger(__name__)

VECTOR_DIMENSIONS = 512  # Must match pgvector schema: vector(512)


@lru_cache(maxsize=1)
def get_face_analyzer() -> FaceAnalysis:
    """
    Singleton factory for the InsightFace model suite.
    Using @lru_cache ensures the ONNX computational graph is loaded into
    memory exactly ONCE and reused across all incoming jobs.
    """
    logger.info("Initializing InsightFace ONNX Runtime engine (CPUExecutionProvider)...")
    
    # 'buffalo_l' contains SCRFD-10G (detector) + ArcFace ResNet50 (512D embedder)
    app = FaceAnalysis(
        name="buffalo_l",
        providers=["CPUExecutionProvider"]  # Uses AVX2/AVX-512 CPU hardware vectorization
    )
    # ctx_id=-1 forces CPU execution; det_size=(640, 640) standardizes input detection scale
    app.prepare(ctx_id=-1, det_size=(640, 640))
    return app


def get_faces_and_embeddings(img_path_or_array: Union[str, np.ndarray]) -> List[Dict[str, Any]]:
    """
    Detects faces in an image, computes 5-point (wahi corner of lips, nose point eye middle part etc etc etc shits) facial landmarks for affine
    alignment, and extracts 512-dimensional ArcFace embeddings.

    Args:
        img_path_or_array: Path to the image file or a numpy BGR array.

    Returns:
        List of dictionaries with:
        - 'embedding': List of 512 unit-normalized floats.
        - 'facial_area': Dict with 'x', 'y', 'w', 'h'.
        - 'confidence': Detection confidence score between 0.0 and 1.0.
    """
    try:
        # Step 1: Read image if path string was provided
        if isinstance(img_path_or_array, str):
            img = cv2.imread(img_path_or_array)
            if img is None:
                raise ValueError(f"Could not load image from path: {img_path_or_array}")
        else:
            img = img_path_or_array

        # Step 2: Acquire cached ONNX analyzer and run detection + representation
        analyzer = get_face_analyzer()
        raw_faces = analyzer.get(img)

        valid_faces = []
        for face in raw_faces:
            confidence = float(face.det_score)
            
            # Filter low-confidence false positives
            if confidence < 0.5:
                continue

            # In InsightFace, bbox is [x1, y1, x2, y2]
            x1, y1, x2, y2 = [int(coord) for coord in face.bbox]
            width = max(0, x2 - x1)
            height = max(0, y2 - y1)

            # normed_embedding is strictly unit-normalized (|v| = 1.0)
            embedding_vector = face.normed_embedding.tolist()

            if len(embedding_vector) != VECTOR_DIMENSIONS:
                logger.warning(
                    f"Unexpected vector dimension: {len(embedding_vector)}, expected {VECTOR_DIMENSIONS}. Skipping."
                )
                continue

            valid_faces.append({
                "embedding": embedding_vector,
                "facial_area": {"x": x1, "y": y1, "w": width, "h": height},
                "confidence": confidence,
            })

        return valid_faces

    except Exception as e:
        logger.error(f"InsightFace inference failed: {e}")
        return []


def bytes_to_image(image_bytes: bytes) -> np.ndarray:
    """
    Decodes raw image bytes from storage/HTTP into an OpenCV BGR numpy array.
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_np is None:
        raise ValueError("Failed to decode image bytes into numpy array")
    return img_np


def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculates cosine similarity: S = (A · B) / (||A|| * ||B||).
    Returns score between -1.0 and 1.0 (higher = more similar).
    """
    a = np.array(vec1, dtype=np.float32)
    b = np.array(vec2, dtype=np.float32)
    norm_a = np.linalg.norm(a)
    norm_b = np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
