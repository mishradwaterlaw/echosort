import logging
from uuid import UUID
from datetime import datetime
from typing import List

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from supabase import Client

from dependencies import get_current_user, get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()

class MatchedPhoto(BaseModel):
    id: UUID
    signed_url: str
    created_at: datetime

class MatchResultResponse(BaseModel):
    request_id: UUID
    status: str
    photos: List[MatchedPhoto] 

@router.get("/{request_id}", response_model=MatchResultResponse, status_code=status.HTTP_200_OK)
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