from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List  # FIX 1: removed duplicate import (you had this twice)

router = APIRouter()

class PhotoUploadResponse(BaseModel):
    accepted: int  # FIX 2: typo 'accpted' → 'accepted'. Pydantic uses field names as JSON keys — a typo here means your frontend gets a misspelled key forever.
    photo_ids: List[UUID]
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
    files: List[UploadFile] = File(...)
):
    """
    Contract 2: Upload multiple photos for an event.
    Returns 202 Accepted because embedding generation is async.
    """
    # Logic will go here:
    # 1. Check event exists (404)
    # 2. Check caller is event owner (403)
    # 3. Validate MIME types (415)
    # 4. Upload to Supabase Storage
    # 5. Insert rows into photos table with status='pending'
    # 6. Push embedding jobs to Upstash Redis queue
    pass  # FIX 4: pass was outside the function due to indentation error. In Python, indentation IS the syntax — this would have caused a runtime error.

@router.get("/{event_id}/photos", response_model=PhotoListResponse, status_code=status.HTTP_200_OK)
async def get_event_photos(
    event_id: UUID,
    embedding_status: Optional[str] = None,  # query param: ?embedding_status=pending
    limit: int = 50,
    offset: int = 0
):
    """
    Contract 3: Get all photos for an event with pagination.
    Only accessible by event owner.
    """
    # Logic will go here:
    # 1. Check event exists (404)
    # 2. Check caller is event owner (403)
    # 3. Query photos table with optional status filter
    # 4. Return paginated results
    pass