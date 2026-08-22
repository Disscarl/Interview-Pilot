"""iFlytek speech-to-text (语音听写) — server-side split + transcribe.

The browser uploads one full WAV recording (16 kHz / 16-bit / mono). We split it
into <=55s PCM segments (iFlytek caps a single request at 60s), transcribe each
segment concurrently, and join the text back in order.
"""
import asyncio
import base64
import hashlib
import hmac
import json
from datetime import datetime, timezone
from urllib.parse import urlencode

from config import settings, logger

IFLYTEK_APP_ID = settings.iflytek_app_id
IFLYTEK_API_KEY = settings.iflytek_api_key
IFLYTEK_API_SECRET = settings.iflytek_api_secret

HOST = "iat-api.xfyun.cn"
PATH = "/v2/iat"
WSS_URL = "wss://" + HOST + PATH

# 16 kHz / 16-bit / mono PCM
BYTES_PER_SECOND = 16000 * 2
SEGMENT_SECONDS = 55  # under iFlytek's 60s per-request cap
SEGMENT_BYTES = SEGMENT_SECONDS * BYTES_PER_SECOND
FRAME_BYTES = 8192  # audio bytes per WS frame
MAX_CONCURRENCY = 4


class AsrNotConfigured(Exception):
    """Raised when iFlytek credentials are missing."""


def _require_config() -> None:
    if not (IFLYTEK_APP_ID and IFLYTEK_API_KEY and IFLYTEK_API_SECRET):
        raise AsrNotConfigured(
            "语音识别未配置（请在 backend/.env 填入 IFLYTEK_APP_ID / IFLYTEK_API_KEY / IFLYTEK_API_SECRET）"
        )


def _build_auth_url() -> str:
    """Build the signed wss:// URL per iFlytek WebAPI spec."""
    date = datetime.now(timezone.utc).strftime("%a, %d %b %Y %H:%M:%S") + " GMT"
    signature_origin = f"host: {HOST}\ndate: {date}\nGET {PATH} HTTP/1.1"
    signature = base64.b64encode(
        hmac.new(IFLYTEK_API_SECRET.encode(), signature_origin.encode(), hashlib.sha256).digest()
    ).decode()
    authorization_origin = (
        f'api_key="{IFLYTEK_API_KEY}", algorithm="hmac-sha256", '
        f'headers="host date request-line", signature="{signature}"'
    )
    authorization = base64.b64encode(authorization_origin.encode()).decode()
    query = urlencode({"authorization": authorization, "date": date, "host": HOST})
    return WSS_URL + "?" + query


async def _transcribe_segment(pcm: bytes) -> str:
    """Transcribe one PCM segment (<=55s). Returns text ('' on failure)."""
    if not pcm:
        return ""

    frames = [pcm[i:i + FRAME_BYTES] for i in range(0, len(pcm), FRAME_BYTES)]
    total = len(frames)

    def make_frame(status: int, data: bytes) -> str:
        return json.dumps({
            "common": {"app_id": IFLYTEK_APP_ID},
            "business": {
                "language": "zh_cn", "domain": "iat", "accent": "mandarin",
                "vad_eos": 3000,
            },
            "data": {
                "status": status,
                "format": "audio/L16;rate=16000",
                "encoding": "raw",
                "audio": base64.b64encode(data).decode(),
            },
        })

    import websockets

    words_by_sn = {}
    try:
        async with websockets.connect(_build_auth_url(), max_size=1024 * 1024) as ws:
            for idx, frame in enumerate(frames):
                status = 0 if idx == 0 else (2 if idx == total - 1 else 1)
                await ws.send(make_frame(status, frame))
                await asyncio.sleep(0.01)

            async for message in ws:
                try:
                    msg = json.loads(message)
                except Exception:
                    continue
                code = msg.get("code", 0)
                if code != 0:
                    logger.warning("iFlytek ASR error code=%s: %s", code, msg.get("message"))
                    break
                data = msg.get("data") or {}
                result = data.get("result") or {}
                sn = result.get("sn", 0)
                for item in result.get("ws") or []:
                    for c in item.get("cw") or []:
                        w = c.get("w")
                        if w:
                            words_by_sn.setdefault(sn, []).append(w)
                if data.get("status") == 2 and result.get("ls"):
                    break
    except Exception as e:
        logger.warning("iFlytek ASR segment transcribe failed: %s", e)
        return ""

    return "".join("".join(words_by_sn[k]) for k in sorted(words_by_sn))


async def _transcribe_segment_retry(pcm: bytes) -> str:
    for attempt in range(2):
        text = await _transcribe_segment(pcm)
        if text:
            return text
        if attempt == 0:
            await asyncio.sleep(0.5)
    return ""


def _pcm_from_wav(wav: bytes) -> bytes:
    """Extract the PCM 'data' chunk from a RIFF/WAVE file."""
    if len(wav) < 12 or wav[:4] != b"RIFF" or wav[8:12] != b"WAVE":
        raise ValueError("无效的 WAV 音频")
    offset = 12
    while offset + 8 <= len(wav):
        chunk_id = wav[offset:offset + 4]
        size = int.from_bytes(wav[offset + 4:offset + 8], "little")
        if chunk_id == b"data":
            return wav[offset + 8:offset + 8 + size]
        offset += 8 + size + (size & 1)  # chunks are word-aligned
    raise ValueError("WAV 缺少 data 块")


async def transcribe_wav(wav: bytes) -> dict:
    """Split a full WAV recording into segments, transcribe, join in order.

    Returns {"text": str, "duration_sec": float}.
    """
    _require_config()
    pcm = _pcm_from_wav(wav)
    duration_sec = len(pcm) / BYTES_PER_SECOND
    if not pcm:
        return {"text": "", "duration_sec": 0.0}

    segments = [pcm[i:i + SEGMENT_BYTES] for i in range(0, len(pcm), SEGMENT_BYTES)]
    semaphore = asyncio.Semaphore(MAX_CONCURRENCY)

    async def run(seg: bytes) -> str:
        async with semaphore:
            return await _transcribe_segment_retry(seg)

    texts = await asyncio.gather(*(run(seg) for seg in segments))
    return {"text": "".join(texts), "duration_sec": round(duration_sec, 1)}
