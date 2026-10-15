# EchoSort

EchoSort is an automated event photo distribution platform powered by facial recognition and vector similarity search.

---

## Overview

At events such as conferences, weddings, sports meets, and concerts, photographers capture hundreds or thousands of photos. Delivering these photos to the individual attendees who appear in them is a persistent challenge. Attendees are typically left to browse through massive, unsorted galleries, or rely on manual tagging which rarely scales.

EchoSort resolves this bottleneck through automated facial identification:
- Event organizers create an event and upload batch photos.
- An asynchronous machine learning pipeline processes every photo, detects faces, extracts 512-dimensional facial feature embeddings using ArcFace, and indexes them in PostgreSQL using pgvector.
- Attendees access a dedicated event link, upload or capture a selfie, and the system executes a cosine similarity search against the event's indexed face embeddings.
- Attendees are immediately served a private, personalized gallery containing every photo in which they appear, delivered via secure time-limited signed URLs.

---

## Key Capabilities

- Automated Face Detection and Feature Extraction: Uses RetinaFace for multi-face detection under varied lighting and orientations, paired with the ArcFace deep neural network to generate discriminative 512-dimensional facial vectors.
- Approximate Nearest Neighbor (ANN) Search: Employs PostgreSQL with the pgvector extension and Hierarchical Navigable Small World (HNSW) indexing to execute fast cosine distance queries against thousands of face vectors.
- Asynchronous Task Queue: Decouples long-running ML workloads from user-facing HTTP requests using Redis queues, allowing seamless scaling and preventing request timeouts during batch uploads.
- Privacy-Conscious Media Delivery: Raw photos and selfies reside in private storage buckets. Matched photos are served exclusively through short-lived signed URLs, avoiding public bucket exposures.
- Minimal Attendee Friction: Attendees require no account creation or app installation to retrieve their photos; access is provided via a direct event link and selfie submission.
- Organizer Management: Provides a dashboard for creating events, uploading photo collections with progress feedback, monitoring embedding statuses, and sharing event access links.

---

## System Architecture

```
Attendee / Organizer
       |
       |  HTTPS
       v
Next.js Frontend (Vercel)
       |
       |  REST API (JSON / Bearer Token)
       v
FastAPI Backend (Render)
       |
       +---> Upstash Redis (Task Queue: LPUSH / RPOP)
       |        |
       |        v
       |     ML Worker (Modal / Serverless)
       |        |  - RetinaFace (Detection)
       |        |  - ArcFace (512d Embedding)
       |        v
       +---> Supabase PostgreSQL (pgvector HNSW index)
       +---> Supabase Storage (Private Media Buckets)
```

---

## How It Works

### 1. Photo Ingestion and Indexing
1. The organizer creates an event and uploads bulk photos via the web interface.
2. The FastAPI service receives the files, stores them in Supabase Storage, creates records in the database with status `pending`, and pushes jobs to the Redis queue.
3. The background ML worker polls the queue, downloads each image, runs RetinaFace to crop detected faces, and generates an ArcFace embedding vector for each face.
4. Extracted embeddings and bounding confidence values are inserted into the `face_embeddings` table and linked to the photo record.
5. The photo status is updated to `done`.

### 2. Attendee Discovery and Matching
1. The attendee opens the event link and captures a selfie using their device camera or file selector.
2. The selfie is submitted to the API, which records a match request and enqueues a matching job.
3. The ML worker extracts the facial embedding of the selfie.
4. A PostgreSQL RPC function executes an HNSW-indexed cosine similarity query against all face embeddings associated with that specific event, filtering by a strict similarity threshold.
5. Distinct matching photo IDs are saved to the match request, and the frontend displays the matched gallery with signed URLs for viewing and downloading.

---

## Tech Stack

- Frontend: Next.js 14 (App Router), React, TypeScript, Tailwind CSS
- Backend API: FastAPI, Python, Pydantic, HTTPX
- ML Pipeline: DeepFace, ArcFace, RetinaFace, TensorFlow
- Vector Database: Supabase PostgreSQL with pgvector (HNSW cosine similarity index)
- Task Queue: Upstash Redis
- Object Storage: Supabase Storage (private buckets with time-limited signed URLs)
- Authentication: Supabase Auth with server-side session verification

---

## Repository Structure

```
echosort/
  api/                  FastAPI backend service and endpoint routers
    routers/            Route definitions for events, photos, and match requests
    config.py           Environment configuration and validation
    dependencies.py     Authentication guards and database clients
  frontend/             Next.js 14 web application
    src/app/            App router pages (dashboard, event upload, selfie matching)
    src/components/     Reusable UI components (uploader, camera capture, galleries)
    src/lib/            Supabase clients and utility functions
  ml_worker/            Asynchronous machine learning pipeline
    embedder.py         Face detection and embedding generation logic
    job_runner.py       Redis queue consumer and job execution lifecycle
    modal_app.py        Serverless deployment configuration
  supabase/             Database migrations and SQL schema definitions
    migrations/         pgvector schema, tables, RPC functions, and RLS policies
  docs/                 Detailed system architecture, critique, and technical notes
```

---

## Documentation

In-depth technical and architectural documentation can be found in the `docs` directory:
- System Architecture: [docs/SYSTEM_ARCHITECTURE.md](docs/SYSTEM_ARCHITECTURE.md)
- Architectural Critique and Analysis: [docs/ARCHITECTURAL_CRITIQUE.md](docs/ARCHITECTURAL_CRITIQUE.md)
- Technical Discussion and Design Rationale: [docs/INTERVIEW_PREP.md](docs/INTERVIEW_PREP.md)

---

## Setup and Installation

Environment setup, local configuration guidelines, and deployment instructions are currently pending and will be documented in a future update.

---

## License

MIT
