from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from routers import events, photos, matches

app = FastAPI(title="FaceFind API")

# CORS must be added before routes
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "https://your-vercel-app.vercel-app",
    ],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register routers with their URL prefixes
app.include_router(events.router, prefix="/events", tags=["events"])
app.include_router(photos.router, prefix="/events", tags=["photos"])
app.include_router(matches.router, prefix="/events", tags=["matches"])  # POST /{event_id}/match
app.include_router(matches.router, prefix="/matches", tags=["matches-get"])  # GET /{request_id}