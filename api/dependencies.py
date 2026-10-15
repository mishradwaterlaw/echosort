from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from functools import lru_cache
from supabase import create_client, Client
from upstash_redis import Redis
from config import settings

security = HTTPBearer()

@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    """
    Singleton Supabase client with connection pooling, shared across requests.

    Q: Why use @lru_cache(maxsize=1) here instead of creating a client per request?
    A: 1. Connection Reuse (HTTP Keep-Alive): create_client() initializes an internal
          HTTP transport session. Creating a new client on every single incoming HTTP
          request forces python to re-establish TCP handshakes and TLS negotiations with
          Supabase for every query. A cached singleton keeps connections alive in a pool.
       2. Memory & GC Pressure: Instantiating client objects on every request causes
          continual allocation and garbage collection churn under load.
       3. Testability Preserved: Even with @lru_cache, FastAPI's dependency injection
          system (app.dependency_overrides[get_supabase_client] = mock_client) can still
          override this function during automated tests.

    Q: Why service_role_key and not anon_key?
    A: The anon_key respects Row Level Security (RLS) — it can only see data the
       public or authenticated user is permitted to see. The service_role_key bypasses
       RLS entirely, allowing the backend server to manage events, store embeddings,
       and validate user JWTs. This key NEVER leaves the backend environment.
    """
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

@lru_cache(maxsize=1)
def get_redis_client() -> Redis:
    """
    Singleton Redis client, shared across ALL routers.

    Q: Why @lru_cache here instead of defining this inside each router?
    A: @lru_cache caches the return value per function OBJECT in memory.
       If two routers define their own get_redis_client(), each function
       has its own cache entry — so you get TWO separate Redis clients,
       each with their own HTTP session pool. By defining it once here
       and importing the same function everywhere, all routers share
       the exact same cached client instance.

    Q: Why not just make it a module-level global variable?
    A: Two reasons:
       1. Lazy initialization — the client is only created the first time
          it's actually called, not at import time. If Redis is unavailable
          at startup, the error surfaces on the first request (with context)
          rather than silently crashing the entire process at import.
       2. Testability — tests can call lru_cache.cache_clear() to force
          a fresh client to be created, or mock the function with
          dependency_overrides in FastAPI's test client.
    """
    return Redis(
        url=settings.upstash_redis_url,
        token=settings.upstash_redis_token
    )

async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    supabase: Client = Depends(get_supabase_client)
):
    token = credentials.credentials  # the raw JWT string from the Authorization header

    # Q2: Why try/except instead of checking if response is None?
    # supabase.auth.get_user() raises an exception on invalid/expired tokens
    # rather than returning None. If we only checked for None, a bad token
    # would silently fall through and we'd accidentally return a None user.
    # try/except catches ALL failure modes (expired, malformed, revoked).
    try:
        response = supabase.auth.get_user(token)
        user = response.user
    except Exception:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    # Supabase returns a user object even on some soft failures, so guard
    # against a None user just in case.
    if user is None:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token"
        )

    return user
