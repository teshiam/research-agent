import re

_STOP = set(
    "a an the and or of to in on for with is are was were be been it this that these those as at by "
    "from into about over after before between during than then also not no but if its their his her "
    "our your you we they he she i can could may might will would should has have had do does did "
    "which who whom what when where why how more most other some such only own same so very just".split()
)  # fmt: skip
_WORD = re.compile(r"[a-z][a-z0-9'\-]{2,}")
_SENTENCE_SPLIT = re.compile(r"(?<=[.!?])\s+(?=[A-Z0-9\"“(])")


def keywords(text: str) -> list[str]:
    return [w for w in _WORD.findall(text.lower()) if w not in _STOP]


def split_sentences(text: str, min_len: int = 40, max_len: int = 350) -> list[str]:
    sentences: list[str] = []
    for block in text.split("\n"):
        for s in _SENTENCE_SPLIT.split(block.strip()):
            s = s.strip()
            if min_len <= len(s) <= max_len:
                sentences.append(s)
    return sentences


def select_excerpts(text: str, focus_terms: list[str], k: int = 3) -> list[str]:
    """Pick the k sentences most relevant to the focus terms, returned in reading order."""
    terms = set(focus_terms)
    scored: list[tuple[float, int, str]] = []
    seen: set[str] = set()
    for pos, sentence in enumerate(split_sentences(text)):
        words = keywords(sentence)
        key = sentence[:60].lower()
        if not words or key in seen:
            continue
        seen.add(key)
        hits = sum(1 for w in words if w in terms)
        score = hits / (len(words) ** 0.5) + (0.3 if pos < 4 else 0.0)  # lead sentences matter
        scored.append((score, pos, sentence))
    best = sorted(scored, key=lambda t: (-t[0], t[1]))[:k]
    return [s for _, _, s in sorted(best, key=lambda t: t[1])]


def extract_json(text: str) -> str:
    """Pull a JSON object out of a model reply that may include code fences or chatter."""
    start, end = text.find("{"), text.rfind("}")
    if start == -1 or end <= start:
        raise ValueError("No JSON object found in the reply.")
    return text[start : end + 1]
