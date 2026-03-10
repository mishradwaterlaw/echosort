import logging
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from uuid import UUID
from datetime import date, datetime
from typing import List, Optional
from supabase import Client
from dependencies import get_current_user, get_supabase_client

logger = logging.getLogger(__name__)

router = APIRouter()

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

@router.post("", response_model=EventCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreateRequest,
    current_user = Depends(get_current_user),        # auth guard — 401 if token invalid
    supabase: Client = Depends(get_supabase_client)  # db client injected per request
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
    try:
        response = supabase.table("events").select("*").eq("id", str(event_id)).execute()
    except Exception as e:
        logger.error(f"Failed to fetch event: {e}")
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
    
    if event["owner_id"] != str(current_user.id):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Not authorized to access this event"
        )
        
    return event
