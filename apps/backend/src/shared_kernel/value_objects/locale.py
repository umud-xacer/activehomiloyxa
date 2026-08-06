"""Locale/Script -- shared kernel value object (DDD Sec 5.14).

The four locale/script codes used throughout (matches `LocalizedText`'s field names, DEC-19);
used wherever a single string (rather than the full `LocalizedText` envelope) must be tagged
with which locale it is in.
"""

from __future__ import annotations

from enum import StrEnum


class Locale(StrEnum):
    UZ_LATN = "uz_latn"
    UZ_CYRL = "uz_cyrl"
    RU = "ru"
    EN = "en"
