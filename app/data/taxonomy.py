"""Loads the fixed taxonomy (families, notes, moods, ...) and normalises raw note names into it."""
from __future__ import annotations

import json
import re
from functools import lru_cache
from pathlib import Path

TAXONOMY_PATH = Path(__file__).with_name("taxonomy.json")


@lru_cache(maxsize=1)
def load() -> dict:
    with TAXONOMY_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


@lru_cache(maxsize=1)
def synonym_index() -> dict[str, str]:
    """Maps every lower-cased note name and synonym to its master note name."""
    index: dict[str, str] = {}
    for master, spec in load()["notes"].items():
        index[master] = master
        for syn in spec.get("synonyms", []):
            index[syn.lower()] = master
    return index


_clean_re = re.compile(r"[^a-z0-9؀-ۿ\- ]+")


def clean_note(raw: str) -> str:
    text = raw.lower().strip()
    text = text.replace("_", " ").replace("’", "'")
    text = _clean_re.sub(" ", text)
    text = re.sub(r"\s+", " ", text).strip()
    return text


@lru_cache(maxsize=50000)
def normalise_note(raw: str) -> str | None:
    """Returns the master note for a raw note string, or None if unknown."""
    text = clean_note(raw)
    if not text:
        return None
    index = synonym_index()
    if text in index:
        return index[text]
    # Try a few loosened forms: singular/plural and dropping qualifiers.
    candidates = {text.rstrip("s"), text + "s"}
    for token_count in (2, 1):
        words = text.split(" ")
        if len(words) > token_count:
            candidates.add(" ".join(words[-token_count:]))
            candidates.add(" ".join(words[:token_count]))
    for cand in candidates:
        if cand in index:
            return index[cand]
    # Last resort: any master or synonym contained as a whole word.
    for key, master in index.items():
        if len(key) >= 4 and re.search(rf"\b{re.escape(key)}\b", text):
            return master
    return None


def note_family(master: str) -> str:
    return load()["notes"][master]["family"]


def note_label(master: str, lang: str) -> str:
    spec = load()["notes"].get(master)
    if not spec:
        return master
    return spec["ar"] if lang == "ar" else master


def label(kind: str, key: str, lang: str) -> str:
    table = load().get(kind, {})
    entry = table.get(str(key))
    if not entry:
        return str(key)
    return entry["ar" if lang == "ar" else "en"]


def families() -> list[str]:
    return list(load()["families"].keys())


def accord_family(accord: str) -> str | None:
    return load()["accord_family"].get(accord.lower().strip())
