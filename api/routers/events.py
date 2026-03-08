# 1. FastAPI
from fastapi import APIRouter, Depends, HTTPException, status

# 2. Pydantic
from pydantic import BaseModel

# 3. Python stdlib
from uuid import UUID
from datetime import date, datetime
from typing import Optional

router = APIRouter()

class EventCreateRequest(BaseModel):
    name: str
    description: Optional[str] = None
    event_date: Optional[date] = None

class EventCreateResponse(BaseModel):
    id: UUID
    name: str
    owner_id: UUID
    created_at: datetime
    is_active: bool

@router.post("", response_model=EventCreateResponse, status_code=status.HTTP_201_CREATED)
async def create_event(
    event: EventCreateRequest
    # Authentication injected via get_current_user later
):
    """
    Create a new event.
    Requires Authorization Header with JWT token.
    """
    # Logic will go here:
    # 1. Verify user using JWT
    # 2. Insert event to DB
    # 3. Return created event info
    pass
