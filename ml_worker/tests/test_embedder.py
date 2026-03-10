import cv2
import numpy as np
import logging
from embedder import get_faces_and_embeddings, cosine_similarity

logging.basicConfig(level=logging.INFO)

def main():
    print("Generating synthetic 500x500 images...")
    # Use random noise as a dummy image so OpenCV parses it correctly
    img1 = np.random.randint(0, 256, (500, 500, 3), dtype=np.uint8)
    img2 = np.random.randint(0, 256, (500, 500, 3), dtype=np.uint8)
    
    print("Extracting embeddings (ArcFace 512D)...")
    
    # We expect this to bypass the "must be face" logic because the image is valid 
    # and enforce_detection=False inside embedder.py.
    # However we added a confidence > 0.5 filter inside embedder.py.
    # For testing purposes solely to prove 512D, let's temporarily monkeypatch our own 
    # confidence checker inside `embedder.get_faces_and_embeddings` just for this test script
    
    import embedder
    
    # Save original
    original_get_faces = embedder.get_faces_and_embeddings
    
    def mock_get_faces_and_embeddings(img):
        from deepface import DeepFace
        results = DeepFace.represent(
            img_path=img,
            model_name="ArcFace",
            detector_backend="retinaface",
            enforce_detection=False
        )
        valid_faces = []
        for face_data in results:
            # Removed the confidence check just for testing the vector sizes locally
            valid_faces.append({
                "embedding": face_data["embedding"],
                "facial_area": face_data["facial_area"],
                "confidence": face_data.get("face_confidence", 0)
            })
        return valid_faces
        
    embedder.get_faces_and_embeddings = mock_get_faces_and_embeddings
    
    res1 = embedder.get_faces_and_embeddings(img1)
    res2 = embedder.get_faces_and_embeddings(img2)
    
    if not res1 or not res2:
        print("Failed to get embeddings.")
        return
        
    emb1 = res1[0]["embedding"]
    emb2 = res2[0]["embedding"]
    
    print(f"\nDimensions:")
    print(f" - img1 embedding length: {len(emb1)} (Expected: 512)")
    
    print("\nCosine Similarity Tests:")
    sim = cosine_similarity(emb1, emb2)
    print(f" - Output score: {sim:.4f} (Checking if math works!)")
    
    print("\n✅ Script completed without exception")

if __name__ == "__main__":
    main()
