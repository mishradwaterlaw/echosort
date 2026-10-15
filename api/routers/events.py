import json
import uuid
import logging
from uuid import UUID
from datetime import date, datetime
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from supabase import Client

from dependencies import get_current_user, get_supabase_client, get_redis_client
from config import settings

logger = logging.getLogger(__name__)

# Allowed file formats and size ceiling for photo & selfie uploads
ALLOWED_MIME_TYPES = {"image/jpeg", "image/png", "image/webp"}
MAX_FILE_SIZE = 15 * 1024 * 1024  # 15MB


router = APIRouter()

class MatchRequestResponse(BaseModel):
    request_id: UUID
    status: str = "pending"
    message: str

class EventCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    event_date: Optional[date] = None

class EventCreateResponse(BaseModel):
    id: UUID
    name: str
    description: Optional[str] = None
    event_date: Optional[date] = None
    owner_id: UUID
    created_at: datetime
    is_active: bool

class EventPublicResponse(BaseModel):
    """Publicly safe event metadata for attendees (ommits owner.id)"""
    id: UUID
    name: str
    description: Optional[str] = None
    event_date: Optional[date] = None
    created_at: datetime
    is_active: bool

@router.post("", response_model=EventCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreateRequest,
    current_user = Depends(get_current_user),       
    supabase: Client = Depends(get_supabase_client)
):
    # Step 1: Build insert payload.
    # owner_id comes from the verified JWT user, NOT from the request body —
    # if it came from the body, any user could claim to own any event.
    data = {
        "name": event.name,
        "description": event.description,
        "event_date": event.event_date.isoformat() if event.event_date else None,
        "owner_id": str(current_user.id),
        "is_active": True,
    }

    # Step 2 & 3: Insert with proper error handling
    try:
        response = supabase.table("events").insert(data).execute()
    except Exception as e:
        logger.error(f"Supabase insert failed: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Database temporarily unavailable"
        )

    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to create event"
        )

    # Step 4: Return the first (and only) created row as EventCreateResponse
    created = response.data[0]
    return EventCreateResponse(**created)

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

    # Step 6: Append to 'stream:match_jobs' Redis Stream
    job = {
        "request_id": str(request_id),
        "event_id": str(event_id),
        "selfie_path": storage_path
    }
    try:
        get_redis_client().xadd("stream:match_jobs", {"payload": json.dumps(job)})
    except Exception as e:
        logger.error(f"Failed to append match job to Redis Stream: {e}")
        
    # Step 7: Return MatchRequestResponse with request_id
    return MatchRequestResponse(
        request_id=request_id,
        status="pending",
        message="Selfie uploaded. Match finding is in progress."
    )



@router.get("", response_model=List[EventCreateResponse], status_code=200)
async def get_my_events(
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    """Fetch all events owned by the authenticated user, newest first."""
    try:
        response = (
            supabase.table("events")
            .select("*")
            .eq("owner_id", str(current_user.id))
            .order("created_at", desc=True)
            .execute()
        )
        return response.data or []
    except Exception as e:
        logger.error(f"Failed to fetch events: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch events"
        )


@router.get("/{event_id}", response_model=EventCreateResponse, status_code=200)
async def get_event(
    event_id: UUID,
    current_user = Depends(get_current_user),
    supabase: Client = Depends(get_supabase_client)
):
    # Q: Why .single() instead of .execute() + data[0]?
    # .execute() always returns a list (even if 0 or 1 rows). Accessing
    # data[0] on an empty list throws an IndexError — NOT a clean 404.
    # .single() tells the Supabase client "I expect exactly one row".
    # If zero rows exist, it raises an exception, which our try/except
    # catches and converts into a clean 404 with a meaningful message.
    try:
        response = supabase.table("events").select("*").eq("id", str(event_id)).single().execute()
        event = response.data
    except Exception as e:
        logger.error(f"Failed to fetch event: {e}")
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    if not event:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    if event["owner_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this event"
        )

    return event

@router.get("/{event_id}/public",response_model=EventPublicResponse, status_code=status.HTTP_200_OK)
async def get_public_event(
    event_id : UUID,
    current_user=Depends(get_current_user),
    supabase:Client=Depends(get_supabase_client)
):
    """
    Allows any authenticated attendee to view an event's name and details.
    Guards:
    1. Returns 404 if event does not exist.
    2. Returns 404 if the organizer has deactivated the event (is_active == False).
    """
    try:
        response=(
            supabase.table("events")
            .select("id, name,description, event_date, created_at, is_active")
            .eq("id", str(event_id))
            .execute()
        )
    except Exception as e:
        logger.error(f"Failed to fetch public event: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to fetch event"
        )
    if not response.data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found"
        )

    event = response.data[0]
    if not event.get("is_active"):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Event not found or is inactive"
        )

    return EventPublicResponse(**event)

