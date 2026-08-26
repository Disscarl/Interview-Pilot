"""LLM service wrapper — supports OpenAI, Anthropic and DeepSeek.

Model selection is lazy: importing this module never raises, even when no
API key is configured. The RuntimeError only surfaces when an LLM instance
is actually created without any key.

Every created instance carries a lightweight callback that logs prompt
summary + token usage to the local logger (cheap observability without
LangSmith).
"""
import logging

from config import settings, logger
from langchain_core.callbacks import BaseCallbackHandler

# Priority: Anthropic → OpenAI → DeepSeek
ANTHROPIC_KEY = settings.anthropic_api_key
OPENAI_KEY = settings.openai_api_key
DEEPSEEK_KEY = settings.deepseek_api_key


class _CallLogger(BaseCallbackHandler):
    """Logs each LLM call (prompt summary) and its token usage."""

    def __init__(self, log: logging.Logger):
        self._log = log

    def on_llm_start(self, serialized, prompts, **kwargs):
        try:
            if prompts:
                first = prompts[0]
                if not isinstance(first, str):
                    first = str(first)
                summary = " ".join(first.split())[:120]
                self._log.info("LLM call: %s…", summary)
        except Exception:
            pass

    def on_llm_end(self, response, **kwargs):
        try:
            llm_output = getattr(response, "llm_output", None) or {}
            usage = llm_output.get("token_usage") or llm_output.get("usage") or {}
            total = usage.get("total_tokens") or usage.get("total_tokens", "?")
            self._log.info("LLM done: tokens=%s", total)
        except Exception:
            pass


_CALL_LOGGER = _CallLogger(logger)


def _select_model():
    """Pick the model class + default kwargs based on configured keys."""
    if ANTHROPIC_KEY:
        from langchain_anthropic import ChatAnthropic
        return ChatAnthropic, dict(
            model="claude-sonnet-4-5",
            api_key=ANTHROPIC_KEY,
            temperature=0.7,
            max_tokens=1024,
            timeout=60.0,
        )
    if OPENAI_KEY:
        from langchain_openai import ChatOpenAI
        return ChatOpenAI, dict(
            model="gpt-4o",
            api_key=OPENAI_KEY,
            temperature=0.7,
            max_tokens=1024,
            timeout=60.0,
        )
    if DEEPSEEK_KEY:
        # DeepSeek exposes an OpenAI-compatible API
        from langchain_openai import ChatOpenAI
        return ChatOpenAI, dict(
            model=settings.deepseek_model,
            api_key=DEEPSEEK_KEY,
            base_url=settings.deepseek_base_url,
            temperature=0.7,
            max_tokens=1024,
            timeout=60.0,
        )
    raise RuntimeError(
        "Set ANTHROPIC_API_KEY, OPENAI_API_KEY or DEEPSEEK_API_KEY in .env"
    )


def create_llm(temperature: float = 0.7, max_tokens: int = 1024, **kwargs):
    """Create an LLM instance with the given parameters."""
    Model, default_kwargs = _select_model()
    return Model(
        **(default_kwargs | dict(temperature=temperature, max_tokens=max_tokens) | kwargs)
    )


def get_default_llm():
    """Get a default LLM instance (with local call logging attached)."""
    llm = create_llm()
    try:
        llm.callbacks = [_CALL_LOGGER]
    except Exception:
        pass
    return llm
