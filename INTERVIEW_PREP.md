# EchoSort: Technical Deep-Dive & Interview Prep Guide

> **Role Focus:** Web Developer / Full-Stack Engineer  
> **Core Concepts:** FastAPI, Asynchronous Processing, Redis Queues, PostgreSQL (`pgvector`), Face Embeddings (ArcFace + RetinaFace), Cloud Storage, Distributed Failure Modes.

---

## 1. Database Schema

All database migrations are defined in [`supabase/migrations/001_initial.sql`](file:///d:/langgraph-proj/echosort/supabase/migrations/001_initial.sql).

### Exact SQL Definitions

```sql
-- Required for vector operations
create extension if not exists vector;

-- Photos table
create table if not exists photos (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null,
  storage_path text not null,
  embedding_status text not null default 'pending',
  uploaded_by uuid,
  created_at timestamptz default now()
);

-- Face embeddings table
create table if not exists face_embeddings (
  id uuid primary key default gen_random_uuid(),
  photo_id uuid references photos(id) on delete cascade,
  event_id uuid not null,
  embedding vector(512),
  confidence float,
  created_at timestamptz default now()
);

-- Match requests table
create table if not exists match_requests (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null,
  user_id uuid,
  selfie_path text not null,
  status text not null default 'pending',
  result_photo_ids uuid[] default '{}',
  created_at timestamptz default now()
);

-- Stored Procedure: match_faces
create or replace function match_faces (
  query_embedding vector(512),
  match_threshold float,
  match_count int,
  match_event_id uuid
)
returns table (
  id uuid,
  photo_id uuid,
  event_id uuid,
  similarity float
)
language plpgsql
as $$
begin
  return query
  select
    fe.id,
    fe.photo_id,
    fe.event_id,
    1 - (fe.embedding <=> query_embedding) as similarity
  from face_embeddings fe
  where fe.event_id = match_event_id
    and 1 - (fe.embedding <=> query_embedding) > match_threshold
  order by similarity desc
  limit match_count;
end;
$$;
```

### Table & Column Breakdown

| Table | Column | Type | Constraints / Defaults | Description |
| :--- | :--- | :--- | :--- | :--- |
| **`photos`** | `id` | `uuid` | `PRIMARY KEY DEFAULT gen_random_uuid()` | Photo unique identifier |
| | `event_id` | `uuid` | `NOT NULL` | Logical parent event ID (*no FK constraint in SQL*) |
| | `storage_path` | `text` | `NOT NULL` | Path in Supabase Storage (`{event_id}/{photo_id}`) |
| | `embedding_status` | `text` | `NOT NULL DEFAULT 'pending'` | Workflow state: `pending`, `processing`, `done`, `failed` |
| | `uploaded_by` | `uuid` | *nullable* | User ID of the uploader |
| | `created_at` | `timestamptz` | `DEFAULT now()` | Row creation timestamp |
| **`face_embeddings`** | `id` | `uuid` | `PRIMARY KEY DEFAULT gen_random_uuid()` | Embedding record identifier |
| | `photo_id` | `uuid` | `REFERENCES photos(id) ON DELETE CASCADE` | **The ONLY foreign key constraint defined in the schema** |
| | `event_id` | `uuid` | `NOT NULL` | Event identifier used for filtering |
| | `embedding` | `vector(512)` | *nullable* | 512-dimensional ArcFace float vector |
| | `confidence` | `float` | *nullable* | RetinaFace detection confidence score |
| | `created_at` | `timestamptz` | `DEFAULT now()` | Insertion timestamp |
| **`match_requests`** | `id` | `uuid` | `PRIMARY KEY DEFAULT gen_random_uuid()` | Match request identifier |
| | `event_id` | `uuid` | `NOT NULL` | Target event being queried |
| | `user_id` | `uuid` | *nullable* | User ID requesting the match |
| | `selfie_path` | `text` | `NOT NULL` | Storage path of uploaded selfie |
| | `status` | `text` | `NOT NULL DEFAULT 'pending'` | Processing state: `pending`, `processing`, `done`, `failed` |
| | `result_photo_ids` | `uuid[]` | `DEFAULT '{}'` | Array of matched `photos.id` |
| | `created_at` | `timestamptz` | `DEFAULT now()` | Submission timestamp |

### pgvector Column & Vector Index Analysis

1. **Exact Type & Dimension:**
   - `vector(512)` stores a 512-dimensional vector of 32-bit floating-point numbers (~2KB per embedding).
2. **Is there an HNSW or IVFFlat Index? NO.**
   - The migration file has **NO vector index created**. 
   - There are also no B-Tree indexes on `face_embeddings.event_id` or `photos.event_id`.
   - **Execution Reality:** PostgreSQL performs a sequential, brute-force linear scan (`Seq Scan`) across `face_embeddings`, filtering on `event_id`, and computing the cosine distance `<=>` for each row one by one.
3. **Discrepancy with Migrations:**
   - The `events` table referenced throughout the API does not exist in `001_initial.sql`.

---

## 2. FastAPI Structure

Endpoints are organized into modular routers registered in [`api/main.py`](file:///d:/langgraph-proj/echosort/api/main.py). Authentication dependencies live in [`api/dependencies.py`](file:///d:/langgraph-proj/echosort/api/dependencies.py).

### Core Dependencies

- `get_supabase_client()`: Returns a Supabase `Client` authenticated with `SUPABASE_SERVICE_ROLE_KEY`. Bypasses Row Level Security (RLS) server-side.
- `get_current_user()`: Validates incoming Bearer JWT against `supabase.auth.get_user(token)`. Raises `HTTP 401 Unauthorized` if invalid or expired.

### Complete Route Catalog

```
FastAPI Router Tree:
├── POST   /events                      -> create_event
├── GET    /events                      -> get_my_events
├── GET    /events/{event_id}           -> get_event
├── POST   /events/{event_id}/photos    -> upload_photos
├── GET    /events/{event_id}/photos    -> get_event_photos
├── POST   /events/{event_id}/match     -> request_match
└── GET    /matches/{request_id}        -> get_match_results (Mounted with prefix issue)
```

#### 1. `POST /events`
- **File:** [`api/routers/events.py:28`](file:///d:/langgraph-proj/echosort/api/routers/events.py#L28)
- **Status:** `201 Created`
- **Request Model:** `EventCreateRequest` (`name: str`, `description: Optional[str]`, `event_date: Optional[date]`)
- **Response Model:** `EventCreateResponse` (`id`, `name`, `description`, `event_date`, `owner_id`, `created_at`, `is_active`)
- **Logic:** Extracts authenticated `current_user.id`, sets `is_active=True`, inserts row directly into `events` table in Postgres.
- **Target:** **Postgres directly.**

#### 2. `GET /events`
- **File:** [`api/routers/events.py:66`](file:///d:/langgraph-proj/echosort/api/routers/events.py#L66)
- **Status:** `200 OK`
- **Response Model:** `List[EventCreateResponse]`
- **Logic:** Queries `events` table where `owner_id == current_user.id`, ordered by `created_at` DESC.
- **Target:** **Postgres directly.**

#### 3. `GET /events/{event_id}`
- **File:** [`api/routers/events.py:89`](file:///d:/langgraph-proj/echosort/api/routers/events.py#L89)
- **Status:** `200 OK`
- **Response Model:** `EventCreateResponse`
- **Logic:** Retrieves event by `id`. Returns 404 if not found; verifies `owner_id == current_user.id` (returns 403 Forbidden if not owner).
- **Target:** **Postgres directly.**

#### 4. `POST /events/{event_id}/photos`
- **File:** [`api/routers/photos.py:60`](file:///d:/langgraph-proj/echosort/api/routers/photos.py#L60)
- **Status:** `202 Accepted`
- **Request:** Form-Data with `files: List[UploadFile] = File(...)`
- **Response Model:** `PhotoUploadResponse` (`accepted: int`, `photo_ids: List[UUID]`, `skipped_files: List[str]`, `message: str`)
- **Logic:**
  1. Verifies caller owns the event.
  2. Iterates over files:
     - Validates MIME type (`image/jpeg`, `image/png`, `image/webp`).
     - Reads raw bytes (`await file.read()`) and verifies size $\le$ 15MB.
     - Generates UUID `photo_id = uuid.uuid4()`.
     - Uploads bytes to Supabase Storage bucket `'photos'` at path `"{event_id}/{photo_id}"`.
     - Inserts row into `photos` table with `embedding_status = "pending"`.
     - Pushes job JSON to Upstash Redis list `"embedding_jobs"`.
- **Target:** **Both Postgres (Storage + DB) AND Redis.**

#### 5. `GET /events/{event_id}/photos`
- **File:** [`api/routers/photos.py:164`](file:///d:/langgraph-proj/echosort/api/routers/photos.py#L164)
- **Status:** `200 OK`
- **Query Params:** `embedding_status: Optional[str]`, `limit: int = 50`, `offset: int = 0`
- **Response Model:** `PhotoListResponse` (`total: int`, `photos: List[PhotoResponse]`)
- **Logic:** Checks ownership, performs a count query, and runs a paginated select query ordered by `created_at` DESC.
- **Target:** **Postgres directly.**

#### 6. `POST /events/{event_id}/match`
- **File:** [`api/routers/matches.py:46`](file:///d:/langgraph-proj/echosort/api/routers/matches.py#L46)
- **Status:** `202 Accepted`
- **Request:** Form-Data with `selfie: UploadFile = File(...)`
- **Response Model:** `MatchRequestResponse` (`request_id: UUID`, `status: str = "pending"`, `message: str`)
- **Logic:**
  1. Verifies event exists and `is_active == True`.
  2. Validates MIME type and size ($\le$ 15MB).
  3. Generates UUID `request_id = uuid.uuid4()`.
  4. Uploads selfie to Supabase Storage bucket `'selfies'` at `"{event_id}/{request_id}"`.
  5. Inserts row into `match_requests` table with `status = "pending"`.
  6. Pushes job JSON to Upstash Redis list `"match_jobs"`.
- **Target:** **Both Postgres (Storage + DB) AND Redis.**

#### 7. `GET /matches/{request_id}`
- **File:** [`api/routers/matches.py:129`](file:///d:/langgraph-proj/echosort/api/routers/matches.py#L129)
- **Status:** `200 OK`
- **Response Model:** `MatchResultResponse` (`request_id: UUID`, `status: str`, `photos: List[MatchedPhoto]`)
- **Logic:**
  1. Fetches `match_requests` row; enforces `user_id == current_user.id`.
  2. If `status != "done"`, returns early with `photos = []`.
  3. If `status == "done"`:
     - Queries `photos` table for IDs in `result_photo_ids`.
     - Calls Supabase Storage API `create_signed_urls(paths, expires_in=3600)`.
     - Returns photo IDs with 1-hour signed URLs.
- **Target:** **Postgres directly.**

> [!WARNING]
> **Routing Prefix Gotcha:**  
> In [`api/main.py:22-23`](file:///d:/langgraph-proj/echosort/api/main.py#L22-L23), `matches.router` is included twice:
> ```python
> app.include_router(matches.router, prefix="/events", tags=["matches"])
> app.include_router(matches.router, prefix="/matches", tags=["matches-get"])
> ```
> Inside `matches.py`, the endpoint is `@router.get("/matches/{request_id}")`.  
> - Under `/events`: `GET /events/matches/{request_id}`  
> - Under `/matches`: `GET /matches/matches/{request_id}` (doubled prefix)  
> The frontend client in [`PollResultsClient.tsx:27`](file:///d:/langgraph-proj/echosort/frontend/src/app/find/%5BeventId%5D/results/%5BrequestId%5D/PollResultsClient.tsx#L27) works around this by targeting `/events/matches/{requestId}`.

---

## 3. The Upload Flow End-to-End

```
[Browser Client]
       │
       ▼ 1. POST /events/{id}/photos (Multipart form)
┌─────────────────────────────────────────────────────────────┐
│ FastAPI API Server (Synchronous Request Context)            │
│  - Checks JWT & event ownership                             │
│  - Reads image bytes into memory                            │
│  - Sequentially uploads bytes to Supabase Storage: 'photos' │
│  - INSERT photos (embedding_status = 'pending')             │
│  - LPUSH 'embedding_jobs' to Upstash Redis                  │
│  - Returns 202 Accepted                                     │
└─────────────────────────────────────────────────────────────┘
       │
       ▼ 2. LPUSH JSON {photo_id, event_id, storage_path}
┌─────────────────────────────────────────────────────────────┐
│ Upstash Redis ('embedding_jobs')                            │
└─────────────────────────────────────────────────────────────┘
       │
       ▼ 3. RPOP JSON (Worker Polling Loop)
┌─────────────────────────────────────────────────────────────┐
│ ML Worker (Modal GPU or Python job_runner.py)               │
│  - UPDATE photos SET embedding_status = 'processing'        │
│  - Download raw image bytes from Supabase Storage           │
│  - cv2.imdecode(bytes) -> numpy BGR array                   │
│  - DeepFace.represent(ArcFace, RetinaFace)                  │
│  - Filter faces with confidence > 0.5                       │
│  - Convert 512D numpy array to native float list            │
│  - INSERT INTO face_embeddings (photo_id, embedding, ...)   │
│  - UPDATE photos SET embedding_status = 'done'              │
└─────────────────────────────────────────────────────────────┘
       │
       ▼ 4. Rows written to face_embeddings
[Vector Searchable via pgvector match_faces()]
```

### Where Does ArcFace Embedding Get Generated?
**Strictly inside the ML Worker, never in the API handler.**  
The FastAPI handler only handles file ingestion, storage persistence, and queuing.

### The Actual Embedding Generation Code
From [`ml_worker/embedder.py:28-53`](file:///d:/langgraph-proj/echosort/ml_worker/embedder.py#L28-L53):

```python
results = DeepFace.represent(
    img_path=img_path_or_array,
    model_name="ArcFace",
    detector_backend="retinaface",
    enforce_detection=False
)

valid_faces = []
for face_data in results:
    confidence = face_data.get("face_confidence", 0)
    if confidence > 0.5:
        if len(face_data["embedding"]) != VECTOR_DIMENSIONS:
            logger.warning(f"Unexpected embedding size: {len(face_data['embedding'])}, expected {VECTOR_DIMENSIONS}. Skipping.")
            continue
            
        valid_faces.append({
            "embedding": face_data["embedding"],
            "facial_area": face_data["facial_area"],
            "confidence": confidence
        })

return valid_faces
```

### Architectural Critique: Is the API Non-Blocking?
**No, the API is partially blocking during uploads.**  
In `photos.py`, the endpoint sequentially reads file bytes into memory and performs an HTTP upload to Supabase Storage inside the request loop. If a user uploads 30 large photos, FastAPI blocks the thread on storage I/O before returning 202.  
*Production Solution:* Issue presigned upload URLs directly to the client; the browser uploads straight to S3/Supabase Storage, and notifies the API via a webhook or completion endpoint.

---

## 4. Redis Job Queue

### Commands & Implementation
- **Client Library:** `upstash_redis` (`from upstash_redis import Redis`)
  - Communicates via HTTP/REST endpoints rather than persistent TCP sockets.
- **Producer Command:** `LPUSH`
  - In `photos.py`: `redis.lpush("embedding_jobs", json.dumps(job))`
  - In `matches.py`: `redis.lpush("match_jobs", json.dumps(job))`
- **Consumer Command:** `RPOP`
  - In `job_runner.py`: `job = redis.rpop("embedding_jobs")`
  - In `modal_app.py`: `job = redis.rpop("embedding_jobs")`
  - Forms a standard FIFO (First-In, First-Out) queue. No `BRPOP` or `BRPOPLPUSH` is used.

### Exact Job Shapes

**1. `embedding_jobs` payload:**
```json
{
  "photo_id": "848bb22d-caec-436f-824f-ef1fe9be7e3c",
  "event_id": "90e2cb11-9a74-4b53-9005-cb628a8d11c0",
  "storage_path": "90e2cb11-9a74-4b53-9005-cb628a8d11c0/848bb22d-caec-436f-824f-ef1fe9be7e3c"
}
```

**2. `match_jobs` payload:**
```json
{
  "request_id": "18f5ec43-2cb0-410a-b31f-0e643bfdd7b1",
  "event_id": "90e2cb11-9a74-4b53-9005-cb628a8d11c0",
  "selfie_path": "90e2cb11-9a74-4b53-9005-cb628a8d11c0/18f5ec43-2cb0-410a-b31f-0e643bfdd7b1"
}
```

### Worker Topology
1. **Local Mode (`job_runner.py`):**
   - Single-threaded process running `while True:` loop.
   - Pops one job, executes it, and calls `time.sleep(20)` (20-second polling interval).
2. **Cloud Mode (`modal_app.py`):**
   - Deployed on Modal with an Nvidia T4 GPU.
   - Scheduled via `@app.function(schedule=modal.Period(seconds=30), timeout=600, retries=2)`.
   - Runs every 30 seconds, drains all jobs from the queues via `while True`, and terminates.

### What Happens if a Worker Crashes Mid-Job?
**THE JOB IS LOST FROM REDIS.**

- `RPOP` is a destructive pop. The job is deleted from Redis immediately upon reading.
- The worker updates Postgres status to `'processing'`.
- If the worker process gets killed (OOM killer during TensorFlow inference, container kill, power drop):
  - **In Redis:** Job is permanently gone.
  - **In Postgres:** Row remains stranded in `'processing'` state forever.
  - **Is there automatic retry?** **No.** There is no dead-letter queue, acknowledgment protocol, or recovery cron job.
- If a standard Python exception occurs:
  - Worker catches it, marks row as `'failed'`, and re-raises. The job is **not** retried.

> **Production Improvement:**  
> Use **Redis Streams** (`XADD`, `XREADGROUP`, `XACK`). An item stays in the Pending Entries List (PEL) until acknowledged. If a worker dies, another consumer inspects `XPENDING` and reclaims it.

---

## 5. Selfie Matching Flow

### Step-by-Step Execution
1. Attendee uploads selfie to `POST /events/{event_id}/match`.
2. API validates image, uploads bytes to `'selfies'` bucket, creates `match_requests` record with `status='pending'`, and issues `LPUSH match_jobs`.
3. Worker pops job via `RPOP match_jobs` and updates `match_requests` status to `'processing'`.
4. Worker downloads selfie bytes, decodes via OpenCV, and executes `get_faces_and_embeddings(img)`.
5. If no faces detected $\rightarrow$ marks `status='failed'`.
6. If faces detected $\rightarrow$ sorts by detection confidence descending and picks `faces[0]`:
   ```python
   faces.sort(key=lambda x: x["confidence"], reverse=True)
   query_embedding = np.array(faces[0]["embedding"]).tolist()
   ```

### The Similarity Search SQL Query
The worker executes the query using Supabase RPC `match_faces` ([`ml_worker/job_runner.py:202`](file:///d:/langgraph-proj/echosort/ml_worker/job_runner.py#L202)):

```python
rpc_response = supabase.rpc("match_faces", {
    "query_embedding": query_embedding,
    "match_event_id": event_id,
    "match_threshold": 0.6,
    "match_count": 20,
}).execute()
```

Which executes the underlying PostgreSQL function:

```sql
select
  fe.id,
  fe.photo_id,
  fe.event_id,
  1 - (fe.embedding <=> query_embedding) as similarity
from face_embeddings fe
where fe.event_id = match_event_id
  and 1 - (fe.embedding <=> query_embedding) > match_threshold
order by similarity desc
limit match_count;
```

### Mathematical Formulation
- In `pgvector`, `<=>` is the **Cosine Distance** operator:
  $$D_c(u, v) = 1 - \frac{u \cdot v}{\|u\|_2 \|v\|_2}$$
- **Cosine Similarity** is therefore:
  $$S_c(u, v) = 1 - D_c(u, v) = 1 - (fe.embedding \Leftrightarrow query\_embedding)$$
- Threshold filtering ensures only matches with similarity $> 0.6$ are returned.
- Ordered by `similarity DESC` to yield closest matches first, capped at `LIMIT 20`.

### Result Post-Processing & Retrieval
- **Deduplication:** A single photo may contain multiple matching faces. Python deduplicates `photo_id`s:
  ```python
  matched_photo_ids = list({row["photo_id"] for row in (rpc_response.data or [])})
  ```
- **Update Database:** Worker updates `match_requests` with `result_photo_ids = matched_photo_ids` and `status = 'done'`.
- **Client Retrieval:** Client polls `GET /events/matches/{request_id}`. When status is `'done'`, the API generates time-limited signed URLs (`expires_in=3600`) from Supabase Storage and returns them in `MatchedPhoto` objects.

---

## 6. Interview Cheatsheet: Traps & High-Scoring Answers

| Question | Junior / Flawed Answer | Senior Engineer Answer |
| :--- | :--- | :--- |
| **"How is vector indexing configured in your database?"** | *"We have an HNSW index on the vector column so search is fast."* | *"In our current schema migration, we do not have an HNSW or IVFFlat index defined; it performs a sequential scan over the event's rows. Because events typically contain a few hundred to a few thousand photos, latency was acceptable for our prototype. For production, we would add `CREATE INDEX ON face_embeddings USING hnsw (embedding vector_cosine_ops);` along with a composite B-tree on `event_id`."* |
| **"What happens if your worker gets killed by the OOM killer?"** | *"Redis automatically retries the job."* | *"Because we use a simple `RPOP`, the job is removed from Redis the moment it is read. If an unhandled crash or OOM occurs, the job is lost from Redis and the database row remains stranded in `processing`. To resolve this, we should adopt Redis Streams with consumer groups (`XREADGROUP`, `XPENDING`, `XACK`) or run a sweeper job that re-queues stale `processing` records."* |
| **"Is your upload endpoint completely non-blocking?"** | *"Yes, everything is asynchronous using Redis."* | *"The ML embedding generation is non-blocking and offloaded to workers. However, the initial upload endpoint is partially blocking because the FastAPI handler reads file bytes into memory and performs an HTTP upload to Supabase Storage sequentially. A more scalable design would generate presigned S3 upload URLs for the browser, eliminating file payload transit through the API."* |
| **"Why do you use Cosine Similarity instead of Euclidean Distance?"** | *"Cosine similarity is standard for images."* | *"ArcFace maps faces onto a hypersphere using additive angular margin loss. The vector magnitude is normalized, so identity is encoded purely in the angle between vectors. Cosine distance ($1 - \cos\theta$) directly corresponds to this angular distance."* |
