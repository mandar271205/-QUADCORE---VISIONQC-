from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import Literal


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    APP_ENV: str = "development"
    APP_HOST: str = "0.0.0.0"
    APP_PORT: int = 8000
    FRONTEND_WEB_URL: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str = ""

    # Supabase
    SUPABASE_URL: str = ""
    SUPABASE_SERVICE_ROLE_KEY: str = ""
    SUPABASE_STORAGE_BUCKET: str = "visionqc"

    # Google Gemini
    GOOGLE_API_KEY: str = ""
    GOOGLE_VLM_MODEL: str = "gemini-3.8-flash"

    # Groq
    GROQ_API_KEY: str = ""
    GROQ_VLM_MODEL: str = "qwen/qwen3.8-27b"

    # NVIDIA NIM
    NVIDIA_API_KEY: str = ""
    NVIDIA_VLM_MODEL: str = "meta/llama-3.2-11b-vision-instruct"
    NVIDIA_BASE_URL: str = "https://integrate.api.nvidia.com/v1"

    # Inspection
    INSPECTION_MODE: Literal[
        "vlm_primary",
        "vlm_only",
        "model_primary",
        "model_only",
        "parallel_first_valid",
    ] = "vlm_primary"
    ML_ENABLED: bool = False
    ML_MODEL_ROOT: str = "./models"
    ML_EXPERIMENT_ROOT: str = "./outputs"
    ML_DEVICE: str = "cpu"
    ML_CACHE_SIZE: int = 2
    ML_TORCH_THREADS: int = 4
    MOBILE_USE_ML: bool = False
    ENGINE_TIMEOUT_SECONDS: int = 8
    MIN_ACCEPT_CONFIDENCE: float = 0.70
    REVIEW_MARGIN: float = 0.05

    # Upload
    MAX_UPLOAD_MB: int = 15

    # Demo Mode
    DEMO_MODE: bool = False

    # Logging
    LOG_LEVEL: str = "INFO"

    @property
    def MAX_UPLOAD_BYTES(self) -> int:
        return self.MAX_UPLOAD_MB * 1024 * 1024

    @property
    def ALLOWED_ORIGINS(self) -> list[str]:
        return [
            self.FRONTEND_WEB_URL,
            "http://localhost:5173",
            "http://localhost:8081",
            "http://127.0.0.1:5173",
            # Allow Expo Go / LAN connections
            "exp://",
        ]


settings = Settings()
