from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from pydantic import BaseModel
from uuid import UUID
from datetime import datetime
from typing import Optional, List

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
    selfie: UploadFile = File(...)  # minor: renamed 'file' to 'selfie' — variable names should be self-documenting
):
    """
    Contract 4: Submit a selfie to find matches in an event.
    Dispatches async job. Returns request_id for polling.
    """
    pass

@router.get("/{request_id}", response_model=MatchResultResponse, status_code=status.HTTP_200_OK)
async def get_match_results(
    request_id: UUID
):
    """
    Contract 5: Poll for match results using request_id.
    Returns status + photos if done, status + empty list if still processing.
    """
    pass