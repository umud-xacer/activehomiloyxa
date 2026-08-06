"""search -- `CrossScriptNormalizationService [P]` (DDD Sec 5.5; FR-SRCH-004, DEC-19, Baseline
Sec 5.8; SAD/SRS named risk R-2: "Cross-script search relevance may under-perform... validate
cross-script matching early against representative content"). Pure string transforms, no I/O --
this is domain logic per the standing orders (a normalizer belongs in domain/, same discipline
`catalog.domain.policies` already applies to catalog's own pure functions).

Design. Rather than detecting "the" script of an input string and transliterating it wholesale in
one direction, both `to_latin`/`to_cyrillic` scan and convert whatever Cyrillic/Latin runs they
find, passing already-matching-script characters (and anything unmapped, e.g. digits/Latin
loanword letters q/c outside the Uzbek 29-letter set) through unchanged. This makes
`normalize_for_matching` robust to mixed-script input (rare but real in free-text listing titles)
without a separate script-detection heuristic, and makes both directions of FR-SRCH-004's
acceptance criterion ("a Latin query returns matching Cyrillic content and vice-versa") the exact
same function applied to query text as to indexed text -- one normalizer, symmetric use.

Apostrophe handling (the flagged R-2 edge case). Real-world Uzbek Latin text for the oʻ/gʻ
digraphs uses several different Unicode "apostrophe-like" characters depending on keyboard/OCR
source (plain ASCII apostrophe, the two curly quote marks, the two IPA modifier-letter
apostrophes, and occasionally a grave/acute accent typo). `_canonicalize_apostrophes` folds every
variant this module is aware of to one canonical marker (`'`, U+0027) before digraph matching, so
`o'`, `o'`, `oʻ`, `oʼ`, and a grave-accent typo all recognise the same digraph. A bare `o`/`g`
with the apostrophe simply omitted (a real data-quality issue in authored content) is NOT
"corrected" here -- there is no way to distinguish an intentional plain `o` from a mistyped `oʻ`
without false-positive risk, so this normalizer deliberately does not guess.

Case folding. Both directions lowercase first: the normalized shadow fields exist only for
matching (never displayed), so case carries no information worth preserving here, and folding it
away up front avoids doubling every mapping table entry.
"""

from __future__ import annotations

import re

_APOSTROPHE_VARIANTS = "‘’ʻʼ`´′"
"""Left/right single quotation marks, modifier letter turned comma, modifier letter apostrophe,
grave accent, acute accent, prime -- folded to a plain ASCII apostrophe (U+0027) before digraph
matching."""

_APOSTROPHE_PATTERN = re.compile(f"[{_APOSTROPHE_VARIANTS}]")


def _canonicalize_apostrophes(text: str) -> str:
    return _APOSTROPHE_PATTERN.sub("'", text)


# Cyrillic (single char) -> Latin (1-2 chars). Uzbek Cyrillic alphabet, 34 letters incl. ъ/ь
# (dropped -- no Latin equivalent in the modern 29-letter Uzbek Latin alphabet) and ц/э (retained
# for loanwords/older text, mapped to their closest practical Latin equivalents for matching
# purposes only -- this is a search normalizer, not a literary transliteration standard).
_CYRILLIC_TO_LATIN: dict[str, str] = {
    "а": "a",
    "б": "b",
    "в": "v",
    "г": "g",
    "д": "d",
    "е": "e",
    "ё": "yo",
    "ж": "j",
    "з": "z",
    "и": "i",
    "й": "y",
    "к": "k",
    "л": "l",
    "м": "m",
    "н": "n",
    "о": "o",
    "п": "p",
    "р": "r",
    "с": "s",
    "т": "t",
    "у": "u",
    "ф": "f",
    "х": "x",
    "ц": "ts",
    "ч": "ch",
    "ш": "sh",
    "ъ": "",
    "ь": "",
    "э": "e",
    "ю": "yu",
    "я": "ya",
    "ў": "o'",
    "қ": "q",
    "ғ": "g'",
    "ҳ": "h",
}

# Latin -> Cyrillic. Multi-character sequences (checked longest-first) before single characters,
# so e.g. "sh" -> "ш" (one letter) rather than "s"+"h" -> "сҳ". The apostrophe digraphs assume
# `_canonicalize_apostrophes` has already run.
_LATIN_DIGRAPHS: tuple[tuple[str, str], ...] = (
    ("o'", "ў"),
    ("g'", "ғ"),
    ("sh", "ш"),
    ("ch", "ч"),
    ("yo", "ё"),
    ("yu", "ю"),
    ("ya", "я"),
    ("ts", "ц"),
)
_LATIN_SINGLE: dict[str, str] = {
    "a": "а",
    "b": "б",
    "v": "в",
    "g": "г",
    "d": "д",
    "e": "е",
    "j": "ж",
    "z": "з",
    "i": "и",
    "y": "й",
    "k": "к",
    "l": "л",
    "m": "м",
    "n": "н",
    "o": "о",
    "p": "п",
    "r": "р",
    "s": "с",
    "t": "т",
    "u": "у",
    "f": "ф",
    "x": "х",
    "h": "ҳ",
    "q": "қ",
}


def to_latin(text: str) -> str:
    """Converts any Cyrillic characters in `text` to their Latin equivalents; already-Latin
    characters (and anything unmapped -- digits, punctuation, other-language letters) pass
    through unchanged. Idempotent on pure-Latin input."""
    lowered = text.lower()
    return "".join(_CYRILLIC_TO_LATIN.get(ch, ch) for ch in lowered)


def to_cyrillic(text: str) -> str:
    """Converts any Latin characters/digraphs in `text` to their Cyrillic equivalents;
    already-Cyrillic characters pass through unchanged. Idempotent on pure-Cyrillic input."""
    lowered = _canonicalize_apostrophes(text.lower())
    result: list[str] = []
    i = 0
    length = len(lowered)
    while i < length:
        matched = False
        for latin_seq, cyrillic_char in _LATIN_DIGRAPHS:
            if lowered.startswith(latin_seq, i):
                result.append(cyrillic_char)
                i += len(latin_seq)
                matched = True
                break
        if matched:
            continue
        ch = lowered[i]
        result.append(_LATIN_SINGLE.get(ch, ch))
        i += 1
    return "".join(result)


def normalize_for_matching(text: str) -> tuple[str, str]:
    """Returns `(as_latin, as_cyrillic)` -- both canonical forms of `text`, regardless of its
    original script. Applied identically to indexed document text (producing the shadow fields
    `ListingSearchDocument.title_normalized_latin`/`title_normalized_cyrillic`) and to query text
    at search time, so a Latin-script query matches Cyrillic-authored content and vice versa
    (FR-SRCH-004's acceptance criterion, both directions, by construction)."""
    return to_latin(text), to_cyrillic(text)
