from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from supabase import create_client, Client
from config import settings

security = HTTPBearer()

def get_supabase_client() -> Client:
    # Q3: Why is the client itself a dependency?
    # Because it makes routes testable — in tests you can swap this out
    # with a mock client using FastAPI's dependency_overrides. It also
    # ensures one clean client instance per request rather than a global.
    #
    # Q1: Why service_role_key and not anon_key?
    # The anon_key respects Row Level Security (RLS) — it can only see
    # data the logged-out public is allowed to see. The service_role_key
    # bypasses RLS entirely and can validate any user's JWT server-side.
    # This is safe here because this code only runs on YOUR server, never
    # in the browser.
    return create_client(settings.supabase_url, settings.supabase_service_role_key)

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
