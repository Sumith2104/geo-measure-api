from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GEO_", env_file=".env")
    database_url: str = "sqlite:///./data/geo.db"
    storage_dir: Path = Path("./data/uploads")
    max_upload_bytes: int = 50 * 1024 * 1024
    max_zip_uncompressed_bytes: int = 300 * 1024 * 1024
    max_zip_entries: int = 100


settings = Settings()
