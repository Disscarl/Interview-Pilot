"""LLM service wrapper — supports OpenAI, Anthropic and DeepSeek."""
from config import settings

# Priority: Anthropic → OpenAI → DeepSeek
ANTHROPIC_KEY = settings.anthropic_api_key
OPENAI_KEY = settings.openai_api_key
DEEPSEEK_KEY = settings.deepseek_api_key

if ANTHROPIC_KEY:
    from langchain_anthropic import ChatAnthropic
    Model = ChatAnthropic
    default_kwargs = dict(
        model="claude-sonnet-4-5",
        api_key=ANTHROPIC_KEY,
        temperature=0.7,
        max_tokens=1024,
    )
elif OPENAI_KEY:
    from langchain_openai import ChatOpenAI
    Model = ChatOpenAI
    default_kwargs = dict(
        model="gpt-4o",
        api_key=OPENAI_KEY,
        temperature=0.7,
        max_tokens=1024,
    )
elif DEEPSEEK_KEY:
    # DeepSeek exposes an OpenAI-compatible API
    from langchain_openai import ChatOpenAI
    Model = ChatOpenAI
    default_kwargs = dict(
        model=settings.deepseek_model,
        api_key=DEEPSEEK_KEY,
        base_url=settings.deepseek_base_url,
        temperature=0.7,
        max_tokens=1024,
    )
else:
    raise RuntimeError(
        "Set ANTHROPIC_API_KEY, OPENAI_API_KEY or DEEPSEEK_API_KEY in .env"
    )


def create_llm(temperature: float = 0.7, max_tokens: int = 1024, **kwargs):
    """Create an LLM instance with the given parameters."""
    return Model(
        **(default_kwargs | dict(temperature=temperature, max_tokens=max_tokens) | kwargs)
    )


def get_default_llm():
    """Get a default LLM instance."""
    return create_llm()
