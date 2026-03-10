# EchoSort

Event photo sharing with facial recognition. Organizers upload bulk photos from an event. Attendees take a selfie and the system finds every photo they appear in using vector similarity search against ArcFace face embeddings.

---

## What It Does

An event organizer creates a gallery, uploads photos, and shares a link. When an attendee visits the link and submits a selfie, the system runs face detection on the selfie, generates a 512-dimensional embedding using the ArcFace model, and performs a cosine similarity search against all embeddings stored for that event. Matching photos are returned as a signed-URL gallery the attendee can view and download.

The ML pipeline runs asynchronously. Photo uploads are queued via Redis, picked up by a worker, processed through TensorFlow and RetinaFace for detection and ArcFace for embedding, and written to a pgvector index in PostgreSQL. The same queue pattern handles selfie match requests.

---

## Tech Stack

**Frontend**
- Next.js 14 with App Router and TypeScript
- Supabase Auth with server-side session management
- Server Components for data fetching, Client Components for interactivity
- Server Actions for credential handling without exposing tokens to the browser
- Hosted on Vercel

**Backend**
- FastAPI with Python
- Pydantic Settings for environment validation
- Supabase Python client with service role key for RLS bypass
- Upstash Redis for job queuing (LPUSH/RPOP FIFO pattern)
- Hosted on Render

**ML Worker**
- DeepFace with ArcFace model for 512-dimensional face embeddings
- RetinaFace for face detection
- TensorFlow CPU runtime
- Modal.com for serverless GPU execution in production
- Runs as a polling worker consuming jobs from Redis

**Database and Storage**
- Supabase PostgreSQL with pgvector extension
- HNSW index on face embeddings for approximate nearest neighbor search
- Postgres RPC function for cosine similarity queries with threshold filtering
- Row Level Security policies on all tables
- Supabase Storage with private buckets and time-limited signed URLs

---

## Architecture

```
Browser
  |
  | HTTP
  v
Next.js (Vercel)
  |
  | REST API calls with JWT
  v
FastAPI (Render)
  |            |
  |            | LPUSH job
  |            v
  |         Upstash Redis
  |            |
  |            | RPOP job
  |            v
  |         ML Worker (Modal)
  |            |
  |            | INSERT embeddings
  |            v
  +---------> Supabase PostgreSQL + pgvector
              Supabase Storage (private buckets)
```

---

## Project Structure

```
echosort/
  api/
    main.py                         FastAPI app with CORS and router registration
    config.py                       Pydantic Settings environment validation
    dependencies.py                 JWT auth guard and cached Supabase client
    routers/
      events.py                     CRUD for events
      photos.py                     Bulk photo upload and status polling
      matches.py                    Selfie upload and match result retrieval
  ml_worker/
    embedder.py                     ArcFace embedding logic and cosine similarity
    job_runner.py                   Redis polling worker with state machine
    modal_app.py                    Modal.com deployment configuration
    tests/
      test_embedder.py              Unit tests for embedding pipeline
  frontend/
    src/
      app/
        dashboard/                  Organizer event management
        events/[eventId]/           Event detail and photo upload
        find/[eventId]/             Attendee selfie capture
        find/[eventId]/results/     Matched photo gallery with polling
        (auth)/                     Login and signup pages
        auth/callback/              Supabase OAuth callback handler
      components/
        PhotoUploader.tsx           XHR-based uploader with per-file progress
        SelfieCapture.tsx           Webcam capture and file fallback
        PollResultsClient.tsx       Headless polling component
        CreateEventForm.tsx         Server Action form
      lib/supabase/
        client.ts                   Browser Supabase client
        server.ts                   Server-side Supabase client with cookies
  supabase/
    migrations/
      001_initial.sql               Full schema with extensions, indexes, RLS
```

---

## Database Schema

```
events
  id uuid PK
  owner_id uuid FK auth.users
  name text
  description text
  event_date date
  is_active boolean
  created_at timestamptz

photos
  id uuid PK
  event_id uuid FK events
  storage_path text
  uploaded_by uuid
  embedding_status text CHECK (pending, processing, done, failed)
  created_at timestamptz
  updated_at timestamptz (moddatetime trigger)

face_embeddings
  id uuid PK
  photo_id uuid FK photos
  event_id uuid FK events
  embedding vector(512)
  confidence float
  created_at timestamptz

match_requests
  id uuid PK
  user_id uuid FK auth.users
  event_id uuid FK events
  selfie_path text
  status text CHECK (pending, processing, done, failed)
  result_photo_ids uuid[]
  created_at timestamptz
```

---

## Key Implementation Details

**Why XHR instead of fetch for photo uploads**
The Fetch API does not expose upload progress events. XHR provides xhr.upload.onprogress which enables per-file progress bars.

**Why sequential uploads instead of parallel**
Sequential uploads give accurate per-file completion state in the UI and avoid saturating the connection on mobile networks.

**Why the ML worker uses a polling loop instead of webhooks**
The worker runs on Modal as a serverless function without a persistent HTTP endpoint. Redis gives a persistent queue that survives worker restarts.

**Why embeddings use cosine similarity instead of Euclidean distance**
ArcFace embeddings are trained with angular margin loss. Cosine similarity over the unit-normalized output vectors is the correct distance metric for this model family.

**Why Server Actions handle tokens instead of props**
Passing a JWT as a React prop would serialize it into the browser bundle or client-side state. Server Actions keep credentials on the server and expose only a callable function reference to the client.

**Why getUser() instead of getSession() for server-side auth checks**
getSession() reads from the cookie without cryptographic verification. getUser() makes a network call to Supabase to verify the token. All server-side auth guards use getUser().

---

## Local Development

Prerequisites: Python 3.10, Node.js 18+, pyenv

**Backend**

```bash
cd api
pip install -r requirements.txt
uvicorn main:app --reload --port 8000
```

**ML Worker**

```bash
cd ml_worker
pip install deepface retina-face tensorflow supabase upstash-redis numpy opencv-python-headless python-dotenv
python job_runner.py
```

**Frontend**

```bash
cd frontend
npm install
npm run dev
```

**Environment variables required**

For the API and ML worker, create a .env file in the project root:

```
SUPABASE_URL=
SUPABASE_ANON_KEY=
SUPABASE_SERVICE_ROLE_KEY=
UPSTASH_REDIS_URL=
UPSTASH_REDIS_TOKEN=
```

For the frontend, create frontend/.env.local:

```
NEXT_PUBLIC_SUPABASE_URL=
NEXT_PUBLIC_SUPABASE_ANON_KEY=
NEXT_PUBLIC_API_URL=http://localhost:8000
NEXT_PUBLIC_APP_URL=http://localhost:3000
```

---

## Deployment

**Supabase**: Run migrations in the SQL editor. Enable pgvector and moddatetime extensions. Configure Auth redirect URLs. Create photos and selfies storage buckets as private.

**Upstash**: Create a Redis database. Copy the REST URL and token to environment variables. Remove any quotes from the URL value.

**Render**: Connect the GitHub repository. Set the root directory to api. Add all environment variables from .env. The service starts with uvicorn main:app --host 0.0.0.0 --port 10000.

**Modal**: Authenticate with modal token new. Deploy with modal deploy ml_worker/modal_app.py. Add secrets via the Modal dashboard under the facefind-secrets group.

**Vercel**: Import the GitHub repository. Set the root directory to frontend. Add all NEXT_PUBLIC environment variables plus update NEXT_PUBLIC_API_URL to the Render service URL.

---

## Supabase Setup Notes

Run this SQL before the application migrations:

```sql
CREATE EXTENSION IF NOT EXISTS vector;
CREATE EXTENSION IF NOT EXISTS moddatetime SCHEMA extensions;
```

The photos table requires an updated_at column added manually if not present in the initial migration:

```sql
ALTER TABLE photos ADD COLUMN IF NOT EXISTS updated_at TIMESTAMPTZ DEFAULT now();

CREATE TRIGGER handle_photos_updated_at
BEFORE UPDATE ON photos
FOR EACH ROW
EXECUTE FUNCTION moddatetime(updated_at);
```

---

## License

MIT
