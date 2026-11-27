from typing import Literal

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    db_path: str = "research.db"
    cors_origins: str = "http://localhost:3000"

    # How the agent thinks:
    #   heuristic          - no LLM: scripted research plan + extractive report (free, offline)
    #   openai_compatible  - any OpenAI-style endpoint (Groq, Gemini, OpenRouter, Ollama, ...)
    #   anthropic          - Claude via the Anthropic API
    llm_provider: Literal["heuristic", "openai_compatible", "anthropic"] = "heuristic"
    llm_model: str = ""
    llm_base_url: str = ""
    llm_api_key: str = ""
    anthropic_api_key: str = ""
    input_price_per_mtok: float = 0.0  # USD per million tokens, for the cost estimate
    output_price_per_mtok: float = 0.0

    # Where the agent searches
    search_provider: Literal["wikipedia", "duckduckgo", "searxng"] = "wikipedia"
    searxng_url: str = ""
    # Wikipedia asks API clients to identify themselves: put your contact details here.
    user_agent: str = "ResearchAgent/0.1 (portfolio project; contact: you@example.com)"

    # Safety and budgets
    max_concurrent_runs: int = 2
    run_timeout_seconds: int = 240
    max_total_tokens: int = 60000
    allow_private_hosts: bool = False  # keep False: blocks localhost / internal networks (SSRF)

    # Test hooks
    run_inline: bool = False
    sse_poll_seconds: float = 0.5


settings = Settings()
