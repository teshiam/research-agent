from collections.abc import Callable

from ..config import settings
from .state import Usage

Completer = Callable[[str, str], tuple[str, Usage]]


def _estimate(text: str) -> int:
    return max(1, len(text) // 4)


def make_completer() -> Completer:
    if settings.llm_provider == "anthropic":
        return _anthropic()
    return _openai_compatible()


def _openai_compatible() -> Completer:
    from openai import OpenAI

    client = OpenAI(
        base_url=settings.llm_base_url or None,
        api_key=settings.llm_api_key or "not-needed",  # local servers like Ollama ignore it
    )

    def complete(system: str, user: str) -> tuple[str, Usage]:
        res = client.chat.completions.create(
            model=settings.llm_model,
            max_tokens=1500,
            temperature=0.3,
            messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
        )
        text = res.choices[0].message.content or ""
        usage = getattr(res, "usage", None)
        if usage and usage.prompt_tokens is not None:
            return text, Usage(usage.prompt_tokens, usage.completion_tokens or 0)
        return text, Usage(_estimate(system + user), _estimate(text))  # some providers omit usage

    return complete


def _anthropic() -> Completer:
    import anthropic

    client = anthropic.Anthropic(api_key=settings.anthropic_api_key or None)

    def complete(system: str, user: str) -> tuple[str, Usage]:
        res = client.messages.create(
            model=settings.llm_model or "claude-sonnet-5-5",
            max_tokens=1500,
            system=system,
            messages=[{"role": "user", "content": user}],
        )
        text = "".join(b.text for b in res.content if b.type == "text")
        return text, Usage(res.usage.input_tokens, res.usage.output_tokens)

    return complete
