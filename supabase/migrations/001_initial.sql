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

-- Match faces using cosine similarity (pgvector <=> operator is distance, so 1-distance is similarity)
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
