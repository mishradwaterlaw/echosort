-- ============================================================================
-- 001_initial.sql - EchoSort Production Database Schema
-- ============================================================================

-- Step 0: Required Extensions
-- 'vector' enables pgvector embedding columns and HNSW vector indexing.
-- 'moddatetime' automatically updates the updated_at timestamp on row mutation.
create extension if not exists vector;
create extension if not exists moddatetime schema extensions;


-- ============================================================================
-- 1. Events Table
-- ============================================================================
-- Stores organizer galleries. Was completely missing from the original migration!
create table if not exists events (
  id uuid primary key default gen_random_uuid(),
  owner_id uuid not null references auth.users(id) on delete cascade,
  name text not null,
  description text,
  event_date date,
  is_active boolean not null default true,
  created_at timestamptz not null default now()
);

-- B-Tree Index: Organizers frequently query 'WHERE owner_id = $1 ORDER BY created_at DESC'
create index if not exists idx_events_owner_id on events(owner_id);


-- ============================================================================
-- 2. Photos Table
-- ============================================================================
-- Stores individual photos uploaded to an event.
create table if not exists photos (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(id) on delete cascade,
  storage_path text not null,
  embedding_status text not null default 'pending' 
    check (embedding_status in ('pending', 'processing', 'done', 'failed')),
  uploaded_by uuid references auth.users(id),
  created_at timestamptz not null default now(),
  updated_at timestamptz not null default now()
);

-- Composite B-Tree: The API polls 'WHERE event_id = $1 AND embedding_status = $2'
create index if not exists idx_photos_event_status on photos(event_id, embedding_status);

-- Trigger: Automatically touch updated_at whenever photos row is updated
drop trigger if exists handle_photos_updated_at on photos;
create trigger handle_photos_updated_at
  before update on photos
  for each row execute function extensions.moddatetime(updated_at);


-- ============================================================================
-- 3. Face Embeddings Table
-- ============================================================================
-- Stores 512-dimensional ArcFace vector embeddings for each detected face.
create table if not exists face_embeddings (
  id uuid primary key default gen_random_uuid(),
  photo_id uuid not null references photos(id) on delete cascade,
  event_id uuid not null references events(id) on delete cascade,
  embedding vector(512) not null,
  confidence float not null check (confidence >= 0.0 and confidence <= 1.0),
  created_at timestamptz not null default now()
);

-- B-Tree: Filters candidates down to the specific event before/during similarity ranking
create index if not exists idx_face_embeddings_event_id on face_embeddings(event_id);

-- HNSW Vector Index:
-- 1. 'vector_cosine_ops' uses Cosine distance (<=>), matching ArcFace hypersphere properties.
-- 2. 'm = 16': Maximum number of bidirectional links per graph node (balance of memory & speed).
-- 3. 'ef_construction = 64': Size of the dynamic candidate list during graph building.
create index if not exists idx_face_embeddings_hnsw on face_embeddings 
using hnsw (embedding vector_cosine_ops)
with (m = 16, ef_construction = 64);


-- ============================================================================
-- 4. Match Requests Table
-- ============================================================================
-- Tracks attendee selfie submission jobs and their matched result photo IDs.
create table if not exists match_requests (
  id uuid primary key default gen_random_uuid(),
  event_id uuid not null references events(id) on delete cascade,
  user_id uuid not null references auth.users(id) on delete cascade,
  selfie_path text not null,
  status text not null default 'pending' 
    check (status in ('pending', 'processing', 'done', 'failed')),
  result_photo_ids uuid[] not null default '{}',
  created_at timestamptz not null default now()
);

-- B-Tree: Attendees poll their requests via 'WHERE user_id = $1 AND id = $2'
create index if not exists idx_match_requests_user on match_requests(user_id, status);


-- ============================================================================
-- 5. Row Level Security (RLS)
-- ============================================================================
-- Crucial for defense-in-depth in Supabase, preventing direct client tampering.
alter table events enable row level security;
alter table photos enable row level security;
alter table face_embeddings enable row level security;
alter table match_requests enable row level security;

-- Events RLS
drop policy if exists "Owners manage events" on events;
create policy "Owners manage events" on events
  for all to authenticated
  using (auth.uid() = owner_id);

drop policy if exists "Attendees can view active events" on events;
create policy "Attendees can view active events" on events
  for select to authenticated
  using (is_active = true);

-- Photos RLS: Only event owners can view and upload event photos directly
drop policy if exists "Owners manage photos" on photos;
create policy "Owners manage photos" on photos
  for all to authenticated
  using (exists (
    select 1 from events 
    where events.id = photos.event_id and events.owner_id = auth.uid()
  ));

-- Match Requests RLS: Attendees can only see and manage their own match requests
drop policy if exists "Users manage own match requests" on match_requests;
create policy "Users manage own match requests" on match_requests
  for all to authenticated
  using (auth.uid() = user_id);


-- ============================================================================
-- 6. Stored Procedure: match_faces (HNSW-Accelerated Similarity Search)
-- ============================================================================
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
  -- 'ef_search = 40' controls search depth in the HNSW graph at query time.
  -- Higher = higher recall accuracy; Lower = faster query latency.
  set local hnsw.ef_search = 40;

  return query
  select
    fe.id,
    fe.photo_id,
    fe.event_id,
    -- Cosine similarity is 1 - Cosine distance
    (1 - (fe.embedding <=> query_embedding))::float as similarity
  from face_embeddings fe
  where fe.event_id = match_event_id
    and (1 - (fe.embedding <=> query_embedding)) > match_threshold
  -- IMPORTANT: Ordering directly by '<=>' ASC enables the Postgres query planner
  -- to traverse the HNSW index graph rather than falling back to a full table scan.
  order by fe.embedding <=> query_embedding asc
  limit match_count;
end;
$$;
