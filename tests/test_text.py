from app.agent.text import extract_json, keywords, select_excerpts, split_sentences

TEXT = (
    "Solid state batteries use a solid electrolyte instead of a liquid one in every cell. "
    "Cats are small domesticated mammals that people keep as companions in many homes. "
    "The solid electrolyte can make batteries safer and allow higher energy density overall. "
    "Short one."
)


def test_keywords_drop_stopwords_and_short_words():
    assert keywords("The cat and the solid-state battery") == ["cat", "solid-state", "battery"]


def test_split_sentences_filters_fragments():
    assert len(split_sentences(TEXT)) == 3


def test_select_excerpts_prefers_relevant_sentences_in_reading_order():
    picked = select_excerpts(TEXT, keywords("solid state battery electrolyte"), k=2)
    assert len(picked) == 2
    assert not any("Cats" in s for s in picked)
    assert picked[0].startswith("Solid state")


def test_select_excerpts_dedupes_repeated_sentences():
    repeated = ("Solid state batteries use a solid electrolyte in every single cell. " * 5).strip()
    assert len(select_excerpts(repeated, ["solid"], k=3)) == 1


def test_extract_json_handles_fences():
    assert extract_json('Sure:\n```json\n{"a": 1}\n```') == '{"a": 1}'
