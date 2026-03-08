from pydantic_settings import BaseSettings

class Settings(BaseSettings):
    supabase_url: str
    supabase_anon_key: str
    supabase_service_role_key: str
    upstash_redis_url: str
    upstash_redis_token: str

    class Config:
        env_file = ".env"

settings = Settings()