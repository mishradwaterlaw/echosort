import json
import uuid
import logging
from functools import lru_cache
from upstash_redis import Redis

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List

from supabase import Client
from dependencies import get_current_user, get_supabase_client
from config import settings

logger = logging.getLogger(__name__)

ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB

@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    return Redis(
        url=settings.upstash_redis_url,
        token=settings.upstash_redis_token
    )

router = APIRouter()

class MatchedPhoto(BaseModel):
    id: UUID
    signed_url: str
    created_at: datetime

class MatchRequestResponse(BaseModel):
    request_id: UUID
    status: str = "pending"
    message: str

class MatchResultResponse(BaseModel):
    request_id: UUID
    status: str
    photos: List[MatchedPhoto]  # FIX 1: you wrote 'matches' but the contract says 'photos'. Field names are your API's public contract — changing them later is a breaking change for any client consuming this API.

@router.post("/{event_id}/match", response_model=MatchRequestResponse, status_code=status.HTTP_202_ACCEPTED)
async def request_match(
    event_id: UUID,
    selfie: UploadFile = File(...),
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Contract 4: Submit a selfie to find matches in an event.
    Dispatches async job. Returns request_id for polling.
    """
    # Step 1: Verify event exists and is_active=True -> 404 if not
    try:
        response = supabase.table("events").select("id, is_active").eq("id", str(event_id)).single().execute()
        event_data = response.data
    except Exception as e:
        logger.error(f"Error fetching event {event_id}: {e}")
        raise HTTPException(status_code=404, detail="Event not found")
        
    if not event_data or not event_data.get("is_active"):
        raise HTTPException(status_code=404, detail="Event not found or is inactive")

    # Step 2: Validate MIME type -> 415 if not image
    if selfie.content_type not in ALLOWED_MIME_TYPES:
        raise HTTPException(status_code=415, detail="Unsupported media type for selfie")
        
    # Step 3: Read bytes + size check (reuse same 15MB limit)
    selfie_bytes = await selfie.read()
    if len(selfie_bytes) > MAX_FILE_SIZE:
        raise HTTPException(status_code=413, detail="Selfie exceeds 15MB limit")

    request_id = uuid.uuid4()
    
    # Step 4: Upload to 'selfies' bucket
    #         path: f"selfies/{event_id}/{request_id}"
    storage_path = f"{event_id}/{request_id}"
    try:
        supabase.storage.from_("selfies").upload(
            path=storage_path,
            file=selfie_bytes,
            file_options={"content-type": selfie.content_type}
        )
    except Exception as e:
        logger.error(f"Failed to upload selfie to storage: {e}")
        raise HTTPException(status_code=500, detail="Failed to upload selfie")

    # Step 5: Insert into match_requests table
    #         status='pending', user_id=current_user.id
    match_data = {
        "id": str(request_id),
        "event_id": str(event_id),
        "user_id": str(current_user.id),
        "selfie_path": storage_path,
        "status": "pending"
    }
    
    try:
        db_response = supabase.table("match_requests").insert(match_data).execute()
        if not db_response.data:
            raise Exception("No data returned from insert")
    except Exception as e:
        logger.error(f"Failed to insert match request {request_id}: {e}")
        raise HTTPException(status_code=500, detail="Database error occurred")

    # Step 6: Push to 'match_jobs' queue
    job = {
        "request_id": str(request_id),
        "event_id": str(event_id),
        "selfie_path": storage_path
    }
    try:
        get_redis_client().lpush("match_jobs", json.dumps(job))
    except Exception as e:
        logger.error(f"Failed to push match job to Redis: {e}")
        # Not failing the whole request here, the worker or a cron could theoretically pick up stuck 'pending' requests later
        
    # Step 7: Return MatchRequestResponse with request_id
    return MatchRequestResponse(
        request_id=request_id,
        status="pending",
        message="Selfie uploaded. Match finding is in progress."
    )

@router.get("/matches/{request_id}", response_model=MatchResultResponse, status_code=status.HTTP_200_OK)
async def get_match_results(
    request_id: UUID,
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Contract 5: Poll for match results using request_id.
    Returns status + photos if done, status + empty list if still processing.
    """
    # Step 1: Fetch match_request row -> 404 if not found
    try:
        response = supabase.table("match_requests").select("*").eq("id", str(request_id)).single().execute()
        match_request = response.data
    except Exception as e:
        logger.error(f"Error fetching match request {request_id}: {e}")
        raise HTTPException(status_code=404, detail="Match request not found")
        
    if not match_request:
        raise HTTPException(status_code=404, detail="Match request not found")

    # Step 2: Verify user_id matches current_user.id -> 403
    if match_request.get("user_id") != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this match request")

    # Step 3: If status != 'done' -> return early with empty photos []
    match_status = match_request.get("status", "pending")
    if match_status != "done":
        return MatchResultResponse(
            request_id=request_id,
            status=match_status,
            photos=[]
        )

    # Step 4: If status == 'done':
    #         - fetch each photo_id from result_photo_ids
    #         - generate signed URL for each
    #         - build List[MatchedPhoto]
    matched_photos = []
    photo_ids = match_request.get("result_photo_ids", [])
    
    if photo_ids:
        try:
            # Note: The 'in' operator avoids making N separate queries for N photos
            photos_response = supabase.table("photos").select("id, storage_path, created_at").in_("id", photo_ids).execute()
            photos_data = photos_response.data
            
            # One call for all photos to avoid N+1 query problem
            paths = [photo["storage_path"] for photo in photos_data]
            
            # create_signed_urls accepts an array of paths and returns a list of dictionaries
            signed_urls_response = supabase.storage.from_("photos").create_signed_urls(
                paths=paths,
                expires_in=3600
            )
            
            # Build a lookup dict for easy access
            url_map = {item["path"]: item["signedURL"] for item in signed_urls_response}
            
            for photo in photos_data:
                matched_photos.append(
                    MatchedPhoto(
                        id=photo["id"],
                        signed_url=url_map[photo["storage_path"]],
                        created_at=photo["created_at"]
                    )
                )
        except Exception as e:
            logger.error(f"Failed to fetch matching photos or generate signed URLs: {e}")
            raise HTTPException(status_code=500, detail="Failed to retrieve matching photos")

    # Step 5: Return MatchResultResponse
    return MatchResultResponse(
        request_id=request_id,
        status=match_status,
        photos=matched_photos
    )