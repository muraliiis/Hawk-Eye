from pydantic_settings import BaseSettings, SettingsConfigDict
from functools import lru_cache


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="APP_", env_file=".env", extra="ignore")

    # Database
    database_url: str = "postgresql+asyncpg://postgres:postgres@localhost:5432/road_intelligence"
    redis_url: str = "redis://localhost:6379/0"

    # Security
    secret_key: str = "change-me-in-production-use-a-long-random-string"
    algorithm: str = "HS256"
    access_token_expire_minutes: int = 30

    # Features
    postgis_enabled: bool = True
    max_road_event_age_days: int = 365

    # App
    app_name: str = "Road Intelligence API"
    debug: bool = False
    api_v1_prefix: str = "/api/v1"

    # Cache TTLs (seconds)
    segment_cache_ttl: int = 60
    nearby_events_cache_ttl: int = 30
    parking_cache_ttl: int = 45

    # Scoring weights
    pothole_penalty: float = 0.5
    road_damage_penalty: float = 0.3
    positive_observation_bonus: float = 0.1
    base_quality_score: float = 7.0

    # Ingestion
    max_bulk_ingest_size: int = 500


@lru_cache()
def get_settings() -> Settings:
    return Settings()
