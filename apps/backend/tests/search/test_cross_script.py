"""`search.domain.cross_script` -- thorough, both-directions tests (SAD/SRS named risk R-2:
"Cross-script search relevance may under-perform... validate cross-script matching early against
representative content"; FR-SRCH-004's acceptance criterion: "a Latin query returns matching
Cyrillic content and vice-versa"). This is P-08's own flagged highest-risk area."""

from __future__ import annotations

import pytest

from search.domain.cross_script import normalize_for_matching, to_cyrillic, to_latin

# Representative Uzbek listing titles, Latin <-> Cyrillic pairs (both scripts are official/in
# active use for Uzbek). Digraphs (sh/ch/yo/yu/ya/ts and the oʻ/gʻ apostrophe letters) are the
# named edge case -- covered explicitly, both directions.
_PAIRS: tuple[tuple[str, str], ...] = (
    ("kvartira", "квартира"),
    ("avtomobil", "автомобил"),
    ("uy-joy", "уй-жой"),
    ("shahar", "шаҳар"),
    ("choyxona", "чойхона"),
    ("g'isht", "ғишт"),
    ("bog'", "боғ"),
    ("qishloq xo'jaligi", "қишлоқ хўжалиги"),
)


class TestToLatin:
    @pytest.mark.parametrize(("latin", "cyrillic"), _PAIRS)
    def test_I01_converts_cyrillic_to_latin(self, latin: str, cyrillic: str) -> None:
        assert to_latin(cyrillic) == latin

    def test_I02_passes_through_already_latin_text_unchanged_case_folded(self) -> None:
        assert to_latin("Kvartira") == "kvartira"

    def test_I03_is_idempotent_on_pure_latin_input(self) -> None:
        once = to_latin("kvartira sotiladi")
        assert to_latin(once) == once

    def test_I04_passes_through_digits_and_punctuation(self) -> None:
        assert to_latin("3-xonali, 45 m2") == "3-xonali, 45 m2"

    def test_I05_handles_mixed_script_input_without_a_detection_heuristic(self) -> None:
        # a free-text title with both scripts present (rare but real) -- every run is converted
        # independently of any "detected" dominant script.
        assert to_latin("kvartira квартира") == "kvartira kvartira"


class TestToCyrillic:
    @pytest.mark.parametrize(("latin", "cyrillic"), _PAIRS)
    def test_I06_converts_latin_to_cyrillic(self, latin: str, cyrillic: str) -> None:
        assert to_cyrillic(latin) == cyrillic

    def test_I07_passes_through_already_cyrillic_text_unchanged_case_folded(self) -> None:
        assert to_cyrillic("Квартира") == "квартира"

    def test_I08_is_idempotent_on_pure_cyrillic_input(self) -> None:
        once = to_cyrillic("квартира сотилади")
        assert to_cyrillic(once) == once

    def test_I09_prefers_longest_digraph_match_sh_over_s_plus_h(self) -> None:
        assert to_cyrillic("shahar") == "шаҳар"
        assert "сҳ" not in to_cyrillic("shahar")

    def test_I10_prefers_longest_digraph_match_ch_over_c_plus_h(self) -> None:
        assert to_cyrillic("choyxona") == "чойхона"

    @pytest.mark.parametrize(
        "apostrophe_variant",
        ["o'", "o'", "oʻ", "oʼ", "o`", "o´"],
        ids=[
            "ascii",
            "curly-right",
            "modifier-turned-comma",
            "modifier-apostrophe",
            "grave",
            "acute",
        ],
    )
    def test_I11_normalizes_every_known_apostrophe_variant_for_the_ou_digraph(
        self, apostrophe_variant: str
    ) -> None:
        assert to_cyrillic(apostrophe_variant) == "ў"

    @pytest.mark.parametrize(
        "apostrophe_variant",
        ["g'", "g'", "gʻ", "gʼ", "g`", "g´"],
        ids=[
            "ascii",
            "curly-right",
            "modifier-turned-comma",
            "modifier-apostrophe",
            "grave",
            "acute",
        ],
    )
    def test_I12_normalizes_every_known_apostrophe_variant_for_the_gu_digraph(
        self, apostrophe_variant: str
    ) -> None:
        assert to_cyrillic(apostrophe_variant) == "ғ"

    def test_I13_does_not_guess_a_missing_apostrophe(self) -> None:
        # a bare "o"/"g" without the apostrophe is a real data-quality issue, not something this
        # normalizer silently "corrects" -- deliberately not folded to ў/ғ.
        assert to_cyrillic("bog") == "бог"
        assert to_cyrillic("bog") != to_cyrillic("bog'")


class TestNormalizeForMatchingSymmetry:
    """FR-SRCH-004's acceptance criterion, exercised as one property: applying the SAME normalizer
    to query text and to indexed text makes a query in either script match content in either
    script -- both directions, by construction."""

    @pytest.mark.parametrize(("latin", "cyrillic"), _PAIRS)
    def test_I14_latin_query_matches_latin_normalized_shadow_of_cyrillic_content(
        self, latin: str, cyrillic: str
    ) -> None:
        query_latin, _query_cyrillic = normalize_for_matching(latin)
        content_latin, _content_cyrillic = normalize_for_matching(cyrillic)
        assert query_latin == content_latin

    @pytest.mark.parametrize(("latin", "cyrillic"), _PAIRS)
    def test_I15_cyrillic_query_matches_cyrillic_normalized_shadow_of_latin_content(
        self, latin: str, cyrillic: str
    ) -> None:
        _query_latin, query_cyrillic = normalize_for_matching(cyrillic)
        _content_latin, content_cyrillic = normalize_for_matching(latin)
        assert query_cyrillic == content_cyrillic

    def test_I16_returns_both_forms_regardless_of_the_input_scripts_own_identity(self) -> None:
        as_latin, as_cyrillic = normalize_for_matching("Kvartira")
        assert as_latin == "kvartira"
        assert as_cyrillic == "квартира"
