"""Interviewer TTS — synthesize via iFlytek 超拟人语音合成 (hyper TTS).

Uses the same iFlytek APPID/APIKey/APISecret as STT. Returns MP3 bytes for
browser playback. Falls back to "no voice" on any failure.
"""
import asyncio
import base64
import hashlib
import hmac
import json
import re
from datetime import datetime, timezone
from pathlib import Path
from urllib.parse import urlencode

from config import settings, logger

TTS_VOICE = settings.tts_voice
TTS_SPEED = settings.tts_speed

IFLYTEK_APP_ID = settings.iflytek_app_id
IFLYTEK_API_KEY = settings.iflytek_api_key
IFLYTEK_API_SECRET = settings.iflytek_api_secret

_TTS_HOST = "cbm01.cn-huabei-1.xf-yun.com"
_TTS_PATH = "/v1/private/mcd9m97e6"
_TTS_TIMEOUT_SECONDS = 30.0
_TTS_CACHE_MAX_FILES = 1000

_VOICE_RE = re.compile(r"^[A-Za-z0-9_]+$")


# ─── Stage-direction cleanup ──────────────────────────────
# Parenthetical stage directions the interviewer sometimes emits ("（笑）" etc.)
# should never be spoken: strip them from the TTS text only (display unchanged).

_STAGE_DIRECTION_WORDS = {
    "笑", "微笑", "苦笑", "轻笑", "大笑", "无奈一笑", "停顿", "思考", "沉思",
    "点头", "摇头", "轻咳", "咳嗽", "叹气", "叹息", "惊讶", "皱眉", "沉默",
    "鼓掌", "眨眼", "摊手", "摆手", "挥手", "示意", "喝水", "清了清嗓子",
    "laughs", "laughing", "pause", "sighs", "smile",
}

_BRACKET_RE = re.compile(
    r"（[^（）]*）|\([^()]*\)|【[^【】]*】|\[[^\[\]]*\]|\*[^*]*\*|_[^_]*_"
)


def _is_stage_direction(inner: str) -> bool:
    inner = inner.strip().strip("，。！？、；:;…—")
    return not inner or inner in _STAGE_DIRECTION_WORDS


def clean_tts_text(text: str) -> str:
    """Remove parenthetical stage directions so TTS doesn't read them aloud."""
    if not text:
        return ""
    cleaned = _BRACKET_RE.sub(
        lambda m: "" if _is_stage_direction(m.group()[1:-1]) else m.group(),
        text,
    )
    return re.sub(r"[ \t]+", " ", cleaned).strip()


# ─── Synthesis ────────────────────────────────────────────

def _build_tts_auth_url() -> str:
    """Build the signed wss:// URL per iFlytek WebAPI spec (hyper TTS endpoint)."""
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " GMT"
    signature_origin = f"host: {_TTS_HOST}\ndate: {date}\nGET {_TTS_PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(IFLYTEK_API_SECRET.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    authorization_origin = (
        f'api_key="{IFLYTEK_API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode()).decode()
    query = urlencode({"authorization": authorization, "date": date, "host": _TTS_HOST})
    return f"wss://{_TTS_HOST}{_TTS_PATH}?{query}"


async def synthesize(text: str, voice: str | None = None, speed: int | None = None) -> bytes | None:
    """Synthesize Chinese speech to MP3 bytes, or None on any failure.

    ``voice`` = iFlytek 超拟人发音人 vcn (default TTS_VOICE); ``speed`` = 0-100.
    """
    text = clean_tts_text(text or "")
    if not text:
        return None

    voice = voice if (voice and _VOICE_RE.match(voice)) else TTS_VOICE
    try:
        speed_val = int(speed) if speed is not None else TTS_SPEED
    except (TypeError, ValueError):
        speed_val = TTS_SPEED
    speed_val = max(0, min(100, speed_val))

    import websockets

    request = {
        "header": {"app_id": IFLYTEK_APP_ID, "status": 2},
        "parameter": {
            "tts": {
                "vcn": voice,
                "speed": speed_val,
                "volume": 50,
                "pitch": 50,
                "bgs": 0,
                "reg": 0,
                "rdn": 0,
                "rhy": 0,
                "audio": {
                    "encoding": "lame",
                    "sample_rate": 24000,
                    "channels": 1,
                    "bit_depth": 16,
                    "frame_size": 0,
                },
            }
        },
        "payload": {
            "text": {
                "encoding": "utf8",
                "compress": "raw",
                "format": "plain",
                "status": 2,
                "seq": 0,
                "text": base64.b64encode(text.encode()).decode(),
            }
        },
    }

    audio = bytearray()

    async def _run() -> bytes | None:
        async with websockets.connect(
            _build_tts_auth_url(), max_size=20 * 1024 * 1024, open_timeout=30
        ) as ws:
            await ws.send(json.dumps(request))
            async for message in ws:
                if not isinstance(message, str):
                    continue
                try:
                    msg = json.loads(message)
                except Exception:
                    continue
                hdr = msg.get("header") or {}
                code = hdr.get("code", -1)
                if code != 0:
                    logger.warning("iFlytek TTS error code=%s: %s", code, hdr.get("message"))
                    return None
                chunk = (msg.get("payload") or {}).get("audio") or {}
                audio_b64 = chunk.get("audio")
                if audio_b64:
                    audio.extend(base64.b64decode(audio_b64))
                if chunk.get("status") == 2:
                    break
        return bytes(audio) if audio else None

    try:
        return await asyncio.wait_for(_run(), timeout=_TTS_TIMEOUT_SECONDS)
    except Exception as e:
        logger.warning("iFlytek TTS synthesis failed: %s", e)
        return None


def _cache_key(text: str, voice: str, speed: int) -> str:
    return hashlib.sha256(f"{voice}|{speed}|{text}".encode()).hexdigest()[:24]


def _cache_path(key: str) -> Path:
    return Path(settings.tts_cache_dir) / f"{key}.mp3"


def _evict_cache_if_needed() -> None:
    """Bound the TTS cache: delete oldest-by-mtime files over the cap."""
    cache_dir = Path(settings.tts_cache_dir)
    if not cache_dir.is_dir():
        return
    try:
        files = [p for p in cache_dir.glob("*.mp3") if p.is_file()]
    except OSError:
        return
    if len(files) <= _TTS_CACHE_MAX_FILES:
        return
    excess = len(files) - _TTS_CACHE_MAX_FILES
    for p in sorted(files, key=lambda p: p.stat().st_mtime)[:excess]:
        try:
            p.unlink(missing_ok=True)
        except OSError:
            pass


async def synthesize_cached(text: str, voice: str | None = None, speed: int | None = None) -> bytes | None:
    """Synthesize with an on-disk cache keyed by (voice, speed, text).

    Repeated previews of the same voice/speed/text reuse the cached MP3 file
    instead of calling iFlytek again.
    """
    cleaned = clean_tts_text(text or "")
    if not cleaned:
        return None

    voice = voice if (voice and _VOICE_RE.match(voice)) else TTS_VOICE
    try:
        speed_val = int(speed) if speed is not None else TTS_SPEED
    except (TypeError, ValueError):
        speed_val = TTS_SPEED
    speed_val = max(0, min(100, speed_val))

    path = _cache_path(_cache_key(cleaned, voice, speed_val))
    if path.exists():
        return path.read_bytes()

    audio = await synthesize(cleaned, voice=voice, speed=speed_val)
    if audio:
        try:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(audio)
            _evict_cache_if_needed()
        except Exception as e:
            logger.warning("TTS cache write failed: %s", e)
    return audio
