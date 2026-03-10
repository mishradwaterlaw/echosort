from pydantic_settings import BaseSettings
from pathlib import Path

# .env lives one level up at facefind/.env, not inside facefind/api/
_ENV_FILE = Path(__file__).parent.parent / ".env"

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    upstash_redis_url: str
    upstash_redis_token: str

    class Config:
        env_file = str(_ENV_FILE)

settings = Settings()