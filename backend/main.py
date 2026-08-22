"""FastAPI backend — HTTP + WebSocket server for Interview Pilot."""
import asyncio
import base64
import json
import os
import re
import sys
import uuid
from contextlib import asynccontextmanager

# Fix Windows GBK console encoding for Chinese/emoji output
try:
    sys.stdout.reconfigure(encoding="utf-8")
except Exception:
    pass

from fastapi import FastAPI, WebSocket, WebSocketDisconnect, HTTPException, Depends, Header, Query, Request
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pydantic import BaseModel

from config import settings, logger
from models.interview import InterviewPhase
from agent.interviewer import InterviewerAgent, EvaluatorAgent
from services.session import session_manager
from services.jd import analyze_jd, analyze_candidate
from services.resume import extract_text
from services.history import (
    init_db, save_interview, list_interviews, get_interview, delete_interview,
    list_all_session_ids, create_user, get_user_by_username, get_user_by_id,
)
from services.tts import synthesize_cached
from services.asr import transcribe_wav, AsrNotConfigured
from services.auth import hash_password, verify_password, create_token, decode_token
from services.ratelimit import rate_limiter


# Global interviewer/evaluator (created once at startup)
interviewer = InterviewerAgent()
evaluator = EvaluatorAgent()


# ─── Auth ─────────────────────────────────────────────────

async def get_current_user(authorization: str | None = Header(default=None)) -> dict:
    """FastAPI dependency: return the authenticated user, or raise 401."""
    token = ""
    if authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    user_id = decode_token(token) if token else None
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    user = await get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="用户不存在")
    return user


def _user_id_from_token(token: str) -> int | None:
    return decode_token(token) if token else None


# ─── Rate limiting + input caps ──────────────────────────

# per-user calls allowed per 60s window
_RATE_LIMITS = {"jd": 10, "tts": 30, "resume": 30, "stt": 20}

# input length/size caps
_MAX_JD_TEXT = 20000
_MAX_JD_COMPANY = 2000
_MAX_JD_RESUME = 20000
_MAX_TTS_TEXT = 500
_MAX_RESUME_BYTES = 10 * 1024 * 1024
_MAX_AUDIO_BYTES = 15 * 1024 * 1024


def _enforce_rate_limit(bucket: str, user_id: int) -> None:
    if not rate_limiter.allow(f"{bucket}:{user_id}", _RATE_LIMITS[bucket]):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


# per-IP rate limit for unauthenticated endpoints (login/register)
_AUTH_IP_LIMIT = 10


def _enforce_ip_rate_limit(ip: str) -> None:
    if not rate_limiter.allow(f"auth_ip:{ip}", _AUTH_IP_LIMIT):
        raise HTTPException(status_code=429, detail="请求过于频繁，请稍后再试")


async def send_streamed(ws: WebSocket, state):
    """Stream the interviewer's next message token-by-token to the client."""
    await ws.send_text(json.dumps({"type": "thinking", "content": True}))
    async for token in interviewer.generate_next_stream(state):
        await ws.send_text(json.dumps({"type": "stream_token", "content": token}))
    await ws.send_text(json.dumps({"type": "stream_end", "phase": state.phase.value}))


async def after_candidate_answer(ws: WebSocket, state) -> bool:
    """After a candidate answer: end + evaluate, or stream the next message.

    Returns True when the interview ended (caller should break the loop).
    """
    if state.phase == InterviewPhase.CLOSING and interviewer.should_transition(state):
        state.phase = InterviewPhase.EVALUATE
        await ws.send_text(json.dumps({
            "type": "interview_end",
            "content": "面试结束，正在生成评估报告...",
        }))
        report = await evaluator.evaluate(state)
        await save_history(state, report)
        await ws.send_text(json.dumps({"type": "report", "report": report}))
        return True
    await send_streamed(ws, state)
    return False


async def save_history(state, report):
    """Persist a completed interview to the history store (best-effort)."""
    try:
        await save_interview(
            state.session_id,
            state.role_title or "面试",
            (state.jd_profile or {}).get("company_name") or "",
            state.messages,
            report,
            state.user_id,
        )
    except Exception as e:
        logger.warning("Failed to save history: %s", e)


_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")


def _audio_dir_for(session_id: str) -> str:
    return os.path.join(settings.audio_dir, session_id)


def _write_bytes(path: str, data: bytes) -> None:
    with open(path, "wb") as f:
        f.write(data)


def _delete_audio_dir(session_id: str) -> None:
    """Best-effort removal of a session's voice-answer audio files."""
    if not _ID_RE.match(session_id):
        return
    import shutil
    path = _audio_dir_for(session_id)
    if os.path.isdir(path):
        shutil.rmtree(path, ignore_errors=True)


def _cleanup_orphan_audio(valid_session_ids: set) -> None:
    """Remove audio directories whose session is no longer in history."""
    if not os.path.isdir(settings.audio_dir):
        return
    import shutil
    for name in os.listdir(settings.audio_dir):
        if _ID_RE.match(name) and name not in valid_session_ids:
            path = os.path.join(settings.audio_dir, name)
            if os.path.isdir(path):
                shutil.rmtree(path, ignore_errors=True)
                logger.info("Cleaned up orphan audio: %s", name)


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Startup/shutdown."""
    await init_db(settings.db_path)
    os.makedirs(settings.audio_dir, exist_ok=True)

    # Clean up audio files left behind by interviews that were never saved.
    try:
        _cleanup_orphan_audio(await list_all_session_ids())
    except Exception as e:
        logger.warning("Audio cleanup skipped: %s", e)

    logger.info("Interview Pilot backend started")
    yield
    logger.info("Shutting down")


app = FastAPI(title="Interview Pilot", version="0.1.0", lifespan=lifespan)


# ─── Auth endpoints ───────────────────────────────────────

class AuthRequest(BaseModel):
    username: str
    password: str


@app.post("/api/auth/register")
async def register(req: AuthRequest, request: Request):
    """Register a new user and return a JWT."""
    ip = request.client.host if request.client else "unknown"
    _enforce_ip_rate_limit(ip)
    username = req.username.strip()
    password = req.password
    if len(username) < 2 or len(username) > 64:
        raise HTTPException(status_code=422, detail="用户名长度需在 2-64 之间")
    if len(password) < 4 or len(password) > 128:
        raise HTTPException(status_code=422, detail="密码长度需在 4-128 之间")
    user_id = await create_user(username, hash_password(password))
    if user_id is None:
        raise HTTPException(status_code=409, detail="用户名已存在")
    return {"token": create_token(user_id), "username": username}


@app.post("/api/auth/login")
async def login(req: AuthRequest, request: Request):
    """Log in and return a JWT."""
    ip = request.client.host if request.client else "unknown"
    _enforce_ip_rate_limit(ip)
    username = req.username.strip()
    if len(req.password) > 128:
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    user = await get_user_by_username(username)
    if not user or not verify_password(req.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="用户名或密码错误")
    return {"token": create_token(user["id"]), "username": username}


@app.get("/api/auth/me")
async def me(user: dict = Depends(get_current_user)):
    """Return the current authenticated user."""
    return {"id": user["id"], "username": user["username"]}


# ─── REST endpoints ──────────────────────────────────────

@app.get("/api/scenarios")
async def list_scenarios():
    """Return available interview scenarios."""
    import os
    import glob

    scenario_dir = os.path.join(os.path.dirname(__file__), "data", "scenarios")
    scenarios = []
    for path in glob.glob(os.path.join(scenario_dir, "*.json")):
        with open(path, "r", encoding="utf-8") as f:
            data = json.load(f)
            scenarios.append({
                "id": data["id"],
                "title": data["title"],
                "description": data.get("description", ""),
                "tags": data.get("tags", []),
            })
    return {"scenarios": scenarios}


@app.get("/api/scenarios/{scenario_id}")
async def get_scenario(scenario_id: str):
    """Get a specific scenario config."""
    import os
    path = os.path.join(os.path.dirname(__file__), "data", "scenarios", f"{scenario_id}.json")
    if not os.path.exists(path):
        return {"error": "Scenario not found"}, 404
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


class JDRequest(BaseModel):
    text: str = ""
    company: str = ""
    resume_text: str = ""


class ResumeUpload(BaseModel):
    filename: str = ""
    data_base64: str = ""


@app.post("/api/resume/extract")
async def extract_resume_endpoint(req: ResumeUpload, user: dict = Depends(get_current_user)):
    """Extract text from an uploaded resume (PDF / DOCX, base64-encoded)."""
    _enforce_rate_limit("resume", user["id"])
    try:
        data = base64.b64decode(req.data_base64)
    except Exception:
        raise HTTPException(status_code=422, detail="文件数据无效")
    if len(data) > _MAX_RESUME_BYTES:
        raise HTTPException(status_code=422, detail="文件过大（最多 10MB）")
    try:
        text = extract_text(req.filename, data)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))
    return {"filename": req.filename, "text": text}


@app.post("/api/jd/analyze")
async def analyze_jd_endpoint(req: JDRequest, user: dict = Depends(get_current_user)):
    """Analyze a JD (pasted text) + optional resume into a profile + interview plan."""
    _enforce_rate_limit("jd", user["id"])
    raw_text = req.text.strip()
    company = req.company.strip()

    if not raw_text:
        raise HTTPException(status_code=422, detail="请填写岗位 JD 或职位名")
    if len(raw_text) > _MAX_JD_TEXT:
        raise HTTPException(status_code=422, detail=f"JD 文本过长（最多 {_MAX_JD_TEXT} 字）")
    if len(company) > _MAX_JD_COMPANY:
        raise HTTPException(status_code=422, detail=f"公司介绍过长（最多 {_MAX_JD_COMPANY} 字）")
    if req.resume_text and len(req.resume_text) > _MAX_JD_RESUME:
        raise HTTPException(status_code=422, detail=f"简历文本过长（最多 {_MAX_JD_RESUME} 字）")

    if company:
        raw_text = f"【公司介绍】{company}\n\n{raw_text}"

    if not req.resume_text or not req.resume_text.strip():
        raise HTTPException(status_code=422, detail="请先上传简历（必填）")

    candidate_profile = None
    try:
        candidate_profile = await analyze_candidate(interviewer.llm, req.resume_text.strip())
    except Exception:
        candidate_profile = None

    try:
        return await analyze_jd(interviewer.llm, raw_text, candidate_profile=candidate_profile)
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"JD 解析失败：{e}")


# ─── Interview history ────────────────────────────────────

@app.get("/api/history")
async def list_history(user: dict = Depends(get_current_user)):
    """List the current user's past interviews (newest first)."""
    return {"interviews": await list_interviews(user["id"])}


@app.get("/api/history/{interview_id}")
async def get_history(interview_id: str, user: dict = Depends(get_current_user)):
    """Get a single history record owned by the current user."""
    rec = await get_interview(interview_id, user["id"])
    if not rec:
        raise HTTPException(status_code=404, detail="记录不存在")
    return rec


@app.delete("/api/history/{interview_id}")
async def delete_history(interview_id: str, user: dict = Depends(get_current_user)):
    """Delete a history record and its voice-answer audio files."""
    deleted = await delete_interview(interview_id, user["id"])
    if deleted:
        _delete_audio_dir(interview_id)
    return {"ok": True}


# ─── Voice answer audio ───────────────────────────────────


@app.get("/api/audio/{session_id}/{message_id}")
async def get_audio(
    session_id: str, message_id: str,
    token: str = Query(default=""),
    authorization: str | None = Header(default=None),
):
    """Serve a stored voice-answer WAV file (auth via query token or Bearer)."""
    if not _ID_RE.match(session_id) or not _ID_RE.match(message_id):
        raise HTTPException(status_code=400, detail="非法路径")
    if not token and authorization and authorization.startswith("Bearer "):
        token = authorization[7:].strip()
    user_id = _user_id_from_token(token)
    if user_id is None:
        raise HTTPException(status_code=401, detail="未登录或登录已过期")
    # Ownership: an active session, or a completed interview belonging to the user.
    state = await session_manager.get(session_id)
    owned = (state is not None and state.user_id == user_id) or \
            (await get_interview(session_id, user_id) is not None)
    if not owned:
        raise HTTPException(status_code=404, detail="音频不存在")
    path = os.path.join(_audio_dir_for(session_id), f"{message_id}.wav")
    if not os.path.exists(path):
        raise HTTPException(status_code=404, detail="音频不存在")
    return FileResponse(path, media_type="audio/wav")


class TtsPreviewRequest(BaseModel):
    text: str = ""
    voice: str = ""
    speed: int = 50


@app.post("/api/tts/preview")
async def tts_preview(req: TtsPreviewRequest, user: dict = Depends(get_current_user)):
    """Synthesize a short preview clip with the given voice / speed."""
    _enforce_rate_limit("tts", user["id"])
    text = (req.text or "").strip()
    if not text:
        raise HTTPException(status_code=422, detail="文本为空")
    if len(text) > _MAX_TTS_TEXT:
        raise HTTPException(status_code=422, detail=f"文本过长（最多 {_MAX_TTS_TEXT} 字）")
    audio = await synthesize_cached(text, voice=req.voice or None, speed=req.speed)
    if not audio:
        raise HTTPException(status_code=502, detail="语音合成失败，请稍后重试")
    return {"audio_base64": base64.b64encode(audio).decode()}


# ─── WebSocket ────────────────────────────────────────────

@app.websocket("/ws/{session_id}")
async def websocket_interview(ws: WebSocket, session_id: str):
    """Main interview WebSocket connection."""
    user_id = _user_id_from_token(ws.query_params.get("token", ""))
    if user_id is None or not await get_user_by_id(user_id):
        await ws.close(code=4401)
        return

    await ws.accept()
    logger.info("WebSocket connected: %s (user %s)", session_id, user_id)

    ended = False
    try:
        # First message: setup (scenario selection or create new)
        raw = await ws.receive_text()
        setup = json.loads(raw)

        if setup.get("action") == "create":
            scenario_id = setup.get("scenario_id") or ""
            jd = setup.get("jd")  # optional {"profile": ..., "plan": ...}

            # Resolve a human-readable role title for the interviewer prompt.
            # Priority: JD role title > scenario title > generic fallback.
            role_title = ""
            if isinstance(jd, dict):
                role_title = (jd.get("profile") or {}).get("role_title") or ""
            if not role_title and scenario_id:
                try:
                    scenario_path = os.path.join(
                        os.path.dirname(__file__), "data", "scenarios", f"{scenario_id}.json"
                    )
                    with open(scenario_path, "r", encoding="utf-8") as f:
                        role_title = json.load(f).get("title", "")
                except Exception:
                    role_title = ""
            if not role_title:
                role_title = "目标岗位"

            state = await session_manager.create(
                session_id, scenario_id or "generic", role_title, jd, user_id=user_id
            )
            if setup.get("resume") and state.messages:
                # Reconnect: replay history and continue without a new question.
                await ws.send_text(json.dumps({
                    "type": "resume",
                    "phase": state.phase.value,
                    "messages": state.messages,
                }))
            else:
                await ws.send_text(json.dumps({
                    "type": "created",
                    "session_id": session_id,
                    "scenario_id": scenario_id,
                }))
                # Generate and stream the interviewer's first message
                await send_streamed(ws, state)
        else:
            await ws.send_text(json.dumps({"type": "error", "content": "First message must be 'create'"}))
            return

        # Main loop: receive candidate answers, send interviewer responses
        while True:
            raw = await ws.receive_text()
            data = json.loads(raw)
            action = data.get("action", "answer")

            if action == "answer":
                candidate_text = data.get("content", "")
                state.add_message("candidate", candidate_text)
                if await after_candidate_answer(ws, state):
                    ended = True
                    break

            elif action == "answer_audio":
                audio_b64 = data.get("audio_base64", "")
                duration_ms = data.get("duration_ms", 0)
                if not audio_b64:
                    await ws.send_text(json.dumps({"type": "error", "content": "音频数据为空"}))
                    continue
                if not rate_limiter.allow(f"stt:{user_id}", _RATE_LIMITS["stt"]):
                    await ws.send_text(json.dumps({"type": "error", "content": "请求过于频繁，请稍后再试"}))
                    continue
                try:
                    wav = base64.b64decode(audio_b64)
                except Exception:
                    await ws.send_text(json.dumps({"type": "error", "content": "音频数据无效"}))
                    continue
                if len(wav) > _MAX_AUDIO_BYTES:
                    await ws.send_text(json.dumps({"type": "error", "content": "音频过长（最多约 5 分钟）"}))
                    continue

                message_id = uuid.uuid4().hex
                audio_dir = _audio_dir_for(session_id)
                os.makedirs(audio_dir, exist_ok=True)
                audio_path = os.path.join(audio_dir, f"{message_id}.wav")
                await asyncio.to_thread(_write_bytes, audio_path, wav)
                audio_url = f"/api/audio/{session_id}/{message_id}"

                # Transcribe (server-side split + iFlytek)
                try:
                    result = await transcribe_wav(wav)
                except AsrNotConfigured as e:
                    await ws.send_text(json.dumps({
                        "type": "candidate_voice", "message_id": message_id,
                        "text": "", "audio_url": audio_url,
                        "audio_duration": round(duration_ms / 1000, 1), "error": str(e),
                    }))
                    continue
                except Exception as e:
                    await ws.send_text(json.dumps({
                        "type": "candidate_voice", "message_id": message_id,
                        "text": "", "audio_url": audio_url,
                        "audio_duration": round(duration_ms / 1000, 1),
                        "error": f"语音识别失败：{e}",
                    }))
                    continue

                text = (result.get("text") or "").strip()
                duration_sec = result.get("duration_sec") or round(duration_ms / 1000, 1)
                if not text:
                    await ws.send_text(json.dumps({
                        "type": "candidate_voice", "message_id": message_id,
                        "text": "", "audio_url": audio_url,
                        "audio_duration": duration_sec, "error": "未识别到语音，请重试",
                    }))
                    continue

                state.add_message("candidate", text, audio_url=audio_url, audio_duration=duration_sec)
                await ws.send_text(json.dumps({
                    "type": "candidate_voice", "message_id": message_id,
                    "text": text, "audio_url": audio_url, "audio_duration": duration_sec,
                }))
                if await after_candidate_answer(ws, state):
                    ended = True
                    break

            elif action == "end":
                state.phase = InterviewPhase.EVALUATE
                await ws.send_text(json.dumps({
                    "type": "interview_end",
                    "content": "面试已结束，正在生成评估报告...",
                }))
                report = await evaluator.evaluate(state)
                await save_history(state, report)
                await ws.send_text(json.dumps({
                    "type": "report",
                    "report": report,
                }))
                ended = True
                break

            elif action == "ping":
                await ws.send_text(json.dumps({"type": "pong"}))

    except WebSocketDisconnect:
        logger.info("WebSocket disconnected: %s", session_id)
    except Exception as e:
        logger.error("Error in session %s: %s", session_id, e)
        try:
            await ws.send_text(json.dumps({"type": "error", "content": str(e)}))
        except Exception:
            pass
    finally:
        if ended:
            # Interview finished cleanly → release the session immediately.
            await session_manager.delete(session_id)
            logger.info("Session removed: %s", session_id)
        else:
            # Unexpected disconnect/error → keep the session briefly for reconnect
            # (it is swept by the TTL after SESSION_TTL_SECONDS).
            logger.info("Session kept for reconnect: %s", session_id)


# ─── Static files (frontend) ──────────────────────────────

import os
frontend_dir = os.path.join(os.path.dirname(__file__), "..", "frontend")
dist_dir = os.path.join(frontend_dir, "dist")


@app.get("/")
async def root():
    # Production: serve the built Vite bundle when present.
    dist_index = os.path.join(dist_dir, "index.html")
    if os.path.isfile(dist_index):
        return FileResponse(dist_index)
    # Dev fallback: raw Vite entry (requires `npm run dev`).
    dev_index = os.path.join(frontend_dir, "index.html")
    if os.path.isfile(dev_index):
        return FileResponse(dev_index)
    raise HTTPException(status_code=404, detail="frontend not built")


# Production: serve compiled assets (JS/CSS) emitted by `vite build`.
dist_assets = os.path.join(dist_dir, "assets")
if os.path.isdir(dist_assets):
    app.mount("/assets", StaticFiles(directory=dist_assets), name="assets")

# Legacy/dev: expose the raw frontend directory under /static.
if os.path.exists(frontend_dir):
    app.mount("/static", StaticFiles(directory=frontend_dir), name="static")
