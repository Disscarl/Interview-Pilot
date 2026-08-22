"""Centralized configuration.

Reads backend/.env once and exposes typed settings. No external dependency
beyond python-dotenv (already installed).
"""
import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

BACKEND_DIR = Path(__file__).resolve().parent
load_dotenv(BACKEND_DIR / ".env")


def _get(name: str, default: str = "") -> str:
    return (os.getenv(name) or default).strip()


def _get_int(name: str, default: int) -> int:
    try:
        return int(_get(name, str(default)))
    except ValueError:
        return default


@dataclass
class Settings:
    # LLM (priority: Anthropic -> OpenAI -> DeepSeek)
    anthropic_api_key: str = _get("ANTHROPIC_API_KEY")
    openai_api_key: str = _get("OPENAI_API_KEY")
    deepseek_api_key: str = _get("DEEPSEEK_API_KEY")
    deepseek_model: str = _get("DEEPSEEK_MODEL", "deepseek-chat")
    deepseek_base_url: str = _get("DEEPSEEK_BASE_URL", "https://api.deepseek.com")

    # iFlytek (STT speech-to-text + TTS, shared credentials)
    iflytek_app_id: str = _get("IFLYTEK_APP_ID")
    iflytek_api_key: str = _get("IFLYTEK_API_KEY")
    iflytek_api_secret: str = _get("IFLYTEK_API_SECRET")

    # TTS defaults
    tts_voice: str = _get("TTS_VOICE", "x5_lingxiaotang_flow")
    tts_speed: int = _get_int("TTS_SPEED", 50)

    # Auth
    jwt_secret: str = _get("JWT_SECRET", "dev-insecure-secret-change-me")
    jwt_expires_days: int = _get_int("JWT_EXPIRES_DAYS", 7)

    # Server
    host: str = _get("HOST", "0.0.0.0")
    port: int = _get_int("PORT", 8000)
    ws_max_size: int = _get_int("WS_MAX_SIZE", 64 * 1024 * 1024)

    # Data paths
    db_path: str = str(BACKEND_DIR / "data" / "interviews.db")
    audio_dir: str = str(BACKEND_DIR / "data" / "audio")
    tts_cache_dir: str = str(BACKEND_DIR / "data" / "tts_cache")


settings = Settings()


def setup_logging() -> logging.Logger:
    """Configure a lightweight structured-ish logger for the backend."""
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    return logging.getLogger("interview-pilot")


logger = setup_logging()

if settings.jwt_secret == "dev-insecure-secret-change-me":
    logger.warning("JWT_SECRET is using the dev default — set it in backend/.env before public deployment")

