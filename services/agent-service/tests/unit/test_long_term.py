"""The pure logic of the knowledge base: runtime version parsing, version ranges and the chunker."""

from __future__ import annotations

import pytest

from src.memory.long_term import (
    Applicability,
    RuntimeVersions,
    chunk_text,
    parse_java_major,
    parse_major_minor,
)
from src.memory.short_term import InvalidRecordError


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("17", 17),
        ("21.0.2", 21),
        ("24-ea", 24),
        ("25", 25),
        ("1.8.0_292", 8),
        (" 17 ", 17),
        ("0", None),
        ("", None),
        ("abc", None),
        (None, None),
    ],
)
def test_java_versions_are_reduced_to_their_major_number(raw: str | None, expected: int | None) -> None:
    assert parse_java_major(raw) == expected


@pytest.mark.parametrize(
    ("raw", "expected"),
    [
        ("3.5.4", (3, 5)),
        ("3.5", (3, 5)),
        ("4", (4, 0)),
        ("3.5.0-SNAPSHOT", (3, 5)),
        ("x", None),
        ("", None),
        (None, None),
    ],
)
def test_spring_boot_versions_are_reduced_to_major_and_minor(raw: str | None, expected: tuple[int, int] | None) -> None:
    assert parse_major_minor(raw) == expected


def test_runtime_versions_are_built_from_the_profile_strings() -> None:
    assert RuntimeVersions.from_strings("1.8.0_292", "3.5.4") == RuntimeVersions(java_major=8, spring_boot=(3, 5))
    assert RuntimeVersions.from_strings(None, "garbage") == RuntimeVersions()


@pytest.mark.parametrize(
    ("java", "admitted"),
    [(17, False), (23, False), (24, True), (25, True), (None, True)],
)
def test_a_java_24_note_is_admitted_only_from_jdk_24_and_when_the_version_is_unknown(
    java: int | None, admitted: bool
) -> None:
    rule = Applicability("JAVA", min_version=(24, 0))

    assert rule.admits(RuntimeVersions(java_major=java)) is admitted


def test_both_bounds_of_a_range_are_inclusive_and_the_other_component_is_ignored() -> None:
    rule = Applicability("SPRING_BOOT", min_version=(3, 5), max_version=(3, 9))

    assert [rule.admits(RuntimeVersions(spring_boot=v)) for v in [(3, 4), (3, 5), (3, 9), (4, 0), None]] == [
        False,
        True,
        True,
        False,
        True,
    ]
    assert rule.admits(RuntimeVersions(java_major=8)) is True  # no Spring Boot version known


@pytest.mark.parametrize(
    "kwargs",
    [
        {},
        {"min_version": (-1, 0)},
        {"min_version": (30, 0), "max_version": (24, 0)},
    ],
)
def test_an_invalid_range_is_refused(kwargs: dict[str, tuple[int, int]]) -> None:
    with pytest.raises(InvalidRecordError):
        Applicability("JAVA", **kwargs)


def test_a_java_bound_has_no_minor_part() -> None:
    with pytest.raises(InvalidRecordError):
        Applicability("JAVA", min_version=(17, 5))


# ---- chunker ----

PROSE = " ".join(f"Cümle numarası {n} bir miktar metin içerir." for n in range(1, 80))


def test_the_chunker_is_deterministic_and_respects_the_size_limit() -> None:
    first = chunk_text(PROSE, 300, 40)
    second = chunk_text(PROSE, 300, 40)

    assert first == second
    assert len(first) > 3
    assert all(0 < len(piece) <= 300 for piece in first)
    assert all(piece == piece.strip() for piece in first)


def test_consecutive_chunks_share_words_when_there_is_an_overlap() -> None:
    pieces = chunk_text(PROSE, 300, 60)

    for before, after in zip(pieces, pieces[1:], strict=False):
        assert set(after.split()[:3]) & set(before.split()[-14:]), (before[-60:], after[:60])


def test_without_an_overlap_the_chunks_cover_the_text_once() -> None:
    pieces = chunk_text(PROSE, 300, 0)

    assert " ".join(" ".join(pieces).split()) == " ".join(PROSE.split())


def test_a_short_text_is_one_chunk_and_blank_text_is_none() -> None:
    assert chunk_text("  kısa not  ", 1200, 150) == ["kısa not"]
    assert chunk_text("   \n\n  ", 1200, 150) == []
    assert chunk_text("", 1200, 150) == []


def test_a_word_longer_than_a_chunk_is_cut_hard_and_nothing_is_lost() -> None:
    pieces = chunk_text("x" * 1000, 300, 0)

    assert [len(p) for p in pieces] == [300, 300, 300, 100]


def test_a_table_row_is_not_split_when_a_line_break_is_available() -> None:
    rows = [f"| satır {n} | birinci hücre {n} | ikinci hücre {n} | üçüncü hücre {n} |" for n in range(1, 40)]
    pieces = chunk_text("\n".join(rows), 400, 50)

    assert len(pieces) > 2
    for piece in pieces:
        assert all(line.startswith("| satır") and line.endswith("|") for line in piece.split("\n")), piece


@pytest.mark.parametrize(("size", "overlap"), [(0, 0), (100, 100), (100, -1), (100, 150)])
def test_an_impossible_chunking_is_refused(size: int, overlap: int) -> None:
    with pytest.raises(InvalidRecordError):
        chunk_text("metin", size, overlap)
