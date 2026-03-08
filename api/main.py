from fastapi import FastAPI
from routers import events, photos, matches

app = FastAPI(title="FaceFind API")

# Register routers with their URL prefixes
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(photos.router, prefix="/events", tags=["photos"])
app.include_router(matches.router, prefix="/matches", tags=["matches"])