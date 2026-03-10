import cv2
import numpy as np
import logging
from deepface import DeepFace
from typing import List, Dict, Any, Union

logger = logging.getLogger(__name__)

VECTOR_DIMENSIONS = 512  # Must match pgvector schema: vector(512)

def get_faces_and_embeddings(img_path_or_array: Union[str, np.ndarray]) -> List[Dict[str, Any]]:
    """
    Detects faces in an image and generates vector embeddings for each face.

    Args:
        img_path_or_array: Path to the image file or a numpy array (BGR format).

    Returns:
        List of dictionaries containing:
        - 'embedding': The FaceNet vector (list of 128 floats)
        - 'facial_area': Dict with x, y, w, h
        - 'confidence': Detection confidence score
    """
    try:
        # model_name="ArcFace" outputs exactly 512-dimensional embeddings
        # detector_backend="retinaface" is highly accurate for small/crowded faces
        # enforce_detection=False prevents blowing up if 0 faces are found
        results = DeepFace.represent(
            img_path=img_path_or_array,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False
        )

        valid_faces = []
        for face_data in results:
            # DeepFace sometimes returns an embedding for the whole image if no face is found
            # (when enforce_detection=False). Usually face_confidence is 0 in that case.
            confidence = face_data.get("face_confidence", 0)
            if confidence > 0.5:
                # Validate dimensions match schema
                if len(face_data["embedding"]) != VECTOR_DIMENSIONS:
                    logger.warning(f"Unexpected embedding size: {len(face_data['embedding'])}, expected {VECTOR_DIMENSIONS}. Skipping.")
                    continue
                    
                # Ensure it's not a dummy detection
                valid_faces.append({
                    "embedding": face_data["embedding"],
                    "facial_area": face_data["facial_area"],
                    "confidence": confidence
                })

        return valid_faces
    
    except Exception as e:
        logger.error(f"Failed to generate embeddings: {e}")
        return []

def bytes_to_image(image_bytes: bytes) -> np.ndarray:
    """
    Converts raw image bytes to an OpenCV numpy array (BGR format).
    """
    nparr = np.frombuffer(image_bytes, np.uint8)
    img_np = cv2.imdecode(nparr, cv2.IMREAD_COLOR)
    if img_np is None:
        raise ValueError("Failed to decode image bytes into numpy array")
    return img_np

def cosine_similarity(vec1: List[float], vec2: List[float]) -> float:
    """
    Calculates cosine similarity between two vectors.
    Returns a score between -1.0 and 1.0 (higher means more similar).
    """
    a, b = np.array(vec1), np.array(vec2)
    norm_a, norm_b = np.linalg.norm(a), np.linalg.norm(b)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a, b) / (norm_a * norm_b))
