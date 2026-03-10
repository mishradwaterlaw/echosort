'''
✅ MIME validation → skipped list
✅ File size guard
✅ uploaded_by in insert
✅ DB insert failure → skipped list
✅ Redis lazy loaded via lru_cache
✅ Real total count via count query
✅ Pagination + ordering
✅ Auth on both endpoints

'''


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

class PhotoUploadResponse(BaseModel):
    accepted: int
    photo_ids: List[UUID]
    skipped_files: List[str] = []
    message: str

class PhotoResponse(BaseModel):  # FIX 3: you were missing the GET endpoint entirely (Contract 3). It needs its own response model.
    id: UUID
    storage_path: str
    embedding_status: str
    created_at: datetime

class PhotoListResponse(BaseModel):
    total: int
    photos: List[PhotoResponse]

@router.post("/{event_id}/photos", response_model=PhotoUploadResponse, status_code=status.HTTP_202_ACCEPTED)
async def upload_photos(
    event_id: UUID,
    files: List[UploadFile] = File(...),
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Contract 2: Upload multiple photos for an event.
    Returns 202 Accepted because embedding generation is async.
    """
    # 1. Verify event exists AND caller is the owner
    try:
        response = supabase.table("events").select("*").eq("id", str(event_id)).single().execute()
        event_data = response.data
    except Exception as e:
        logger.error(f"Error fetching event: {e}")
        # Note: .single() raises an exception if 0 rows are found
        raise HTTPException(status_code=404, detail="Event not found")

    if not event_data:
        raise HTTPException(status_code=404, detail="Event not found")

    if event_data["owner_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to modify this event")

    accepted = 0
    photo_ids = []
    skipped = []

    for file in files:
        # Step 2a: Validate MIME type
        if file.content_type not in ALLOWED_MIME_TYPES:
            skipped.append(f"{file.filename} (unsupported format)")
            continue

        # Step 2b: Generate a new UUID for this photo
        # Q1: Why generate photo_id in API instead of letting Supabase auto-generate?
        # A1: So we know the exact ID *before* doing the storage upload.
        # This lets us define the storage path deterministicly (e.g. event_id/photo_id) 
        # and tie the DB row + the Storage object to the exact same ID.
        photo_id = uuid.uuid4()

        try:
            # Step 2c: Read file bytes and check 15MB limit
            file_bytes = await file.read()
            if len(file_bytes) > MAX_FILE_SIZE:
                skipped.append(f"{file.filename} (exceeds 15MB limit)")
                continue

            # Q2: What happens if upload succeeds for 5 photos but DB insert fails on photo 3?
            # A2: You end up with "orphaned" files in Supabase Storage with no corresponding
            # DB row. This is generally "fine" for the API (as the caller gets failure responses) 
            # but consumes storage unnecessarily. This is an eventual consistency problem, 
            # often cleaned up by a separate background cron job checking for orphans.
            storage_path = f"{event_id}/{photo_id}"

            # Upload to 'photos' bucket (Make sure this exists in your Supabase!)
            supabase.storage.from_("photos").upload(
                path=storage_path, 
                file=file_bytes,
                file_options={"content-type": file.content_type}
            )

            # Step 2d: Insert row into photos table
            photo_data = {
                "id": str(photo_id),
                "event_id": str(event_id),
                "storage_path": storage_path,
                "embedding_status": "pending",
                "uploaded_by": str(current_user.id)
            }
            db_response = supabase.table("photos").insert(photo_data).execute()
            
            if not db_response.data:
                logger.error(f"Failed to insert DB row for photo {photo_id}")
                skipped.append(f"{file.filename} (database error)")
                continue # Skip to next file if DB insertion failed but storage upload succeeded (leaves orphan, but API won't break for rest of files)

            # Step 2e: Push job to Redis
            job = {
                "photo_id": str(photo_id), 
                "event_id": str(event_id), 
                "storage_path": storage_path
            }
            get_redis_client().lpush("embedding_jobs", json.dumps(job))

            # Step 2f: Increment accepted counter and append photo_id
            accepted += 1
            photo_ids.append(photo_id)

        except Exception as e:
            logger.error(f"Failed to process photo {file.filename} - {e}")
            skipped.append(f"{file.filename} (internal error)")
            
            continue

    return PhotoUploadResponse(
        accepted=accepted,
        photo_ids=photo_ids,
        skipped_files=skipped,
        message=f"Successfully processed {accepted} out of {len(files)} photos." if accepted > 0 else "No photos successfully processed."
    )

@router.get("/{event_id}/photos", response_model=PhotoListResponse, status_code=status.HTTP_200_OK)
async def get_event_photos(
    event_id: UUID,
    embedding_status: Optional[str] = None,  # query param: ?embedding_status=pending
    limit: int = 50,
    offset: int = 0,
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """
    Contract 3: Get all photos for an event with pagination.
    Only accessible by event owner.
    """
    # 1. Fetch event -> 404 if missing 
    try:
        response = supabase.table("events").select("*").eq("id", str(event_id)).single().execute()
        event_data = response.data
    except Exception as e:
        logger.error(f"Error fetching event: {e}")
        raise HTTPException(status_code=404, detail="Event not found")

    if not event_data:
        raise HTTPException(status_code=404, detail="Event not found")

    # 2. Check owner_id matches current_user.id -> 403 if not
    if event_data["owner_id"] != str(current_user.id):
        raise HTTPException(status_code=403, detail="Not authorized to access this event's photos")

    # 3. Build base query
    query = supabase.table("photos").select("*").eq("event_id", str(event_id))

    # 4. Filter by status if provided
    if embedding_status:
        query = query.eq("embedding_status", embedding_status)

    # 5. Add pagination and sort by created_at descending (newest first)
    query = query.order("created_at", desc=True).range(offset, offset + limit - 1)

    # 6. Execute count query and fetch query
    try:
        count_query = supabase.table("photos").select(
            "*", count="exact"
        ).eq("event_id", str(event_id))

        if embedding_status:
            count_query = count_query.eq("embedding_status", embedding_status)

        count_response = count_query.execute()
        total = count_response.count

        photos_response = query.execute()
    except Exception as e:
        logger.error(f"Error fetching photos: {e}")
        raise HTTPException(status_code=500, detail="Failed to fetch photos")

    # 7. Return PhotoListResponse
    data = photos_response.data or []
    return PhotoListResponse(
        total=total,
        photos=data
    )