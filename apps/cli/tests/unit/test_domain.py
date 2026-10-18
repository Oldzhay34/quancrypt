"""Domain rules: project type, display name, session token, `.gitignore` coverage."""

from __future__ import annotations

import pytest

from quancrypt_cli.domain.errors import AmbiguousProjectError, InvalidSessionTokenError, NotAProjectError
from quancrypt_cli.domain.gitignore import covers_quancrypt
from quancrypt_cli.domain.project import MAX_DISPLAY_NAME, ProjectKind, detect_kind, display_name
from quancrypt_cli.domain.services import ui_open_url
from quancrypt_cli.domain.session_token import SessionToken
from tests.support.fakes import token


@pytest.mark.parametrize(
    ("entries", "kind"),
    [
        ({"pom.xml", "src"}, ProjectKind.MAVEN),
        ({"build.gradle"}, ProjectKind.GRADLE),
        ({"build.gradle.kts", "settings.gradle.kts"}, ProjectKind.GRADLE),
    ],
)
def test_the_project_type_comes_from_the_build_file(entries: set[str], kind: ProjectKind) -> None:
    assert detect_kind(entries) is kind


def test_a_root_without_a_build_file_is_not_a_project() -> None:
    with pytest.raises(NotAProjectError):
        detect_kind({"README.md", "settings.gradle"})


def test_both_build_systems_at_once_are_ambiguous() -> None:
    with pytest.raises(AmbiguousProjectError):
        detect_kind({"pom.xml", "build.gradle"})


def test_the_display_name_is_never_empty_and_at_most_200_characters() -> None:
    assert display_name("qbank") == "qbank"
    assert display_name("") == "project"
    assert len(display_name("x" * 300)) == MAX_DISPLAY_NAME


def test_control_characters_never_reach_the_name() -> None:
    assert display_name("a\x1b[31mb\nc\u202ed") == "a[31mbcd"
    assert display_name("\x1b\x07") == "project"


def test_a_session_token_is_43_base64url_characters() -> None:
    assert SessionToken("A" * 43).value == "A" * 43
    for bad in ("", "short", "A" * 42, "A" * 44, "A" * 42 + "+", "A" * 42 + "="):
        with pytest.raises(InvalidSessionTokenError):
            SessionToken(bad)


def test_a_session_token_never_shows_its_value() -> None:
    secret = token(7)

    assert secret.value not in repr(secret) and secret.value not in str(secret) and secret.value not in f"{secret}"
    assert secret.value not in repr([secret]) and secret.value not in repr({"t": secret})


def test_the_ui_address_carries_the_token_in_the_fragment() -> None:
    secret = token(3)

    assert ui_open_url(secret) == f"http://127.0.0.1:8080/#token={secret.value}"


@pytest.mark.parametrize(
    "lines",
    [
        [".quancrypt/"],
        [".quancrypt"],
        ["/.quancrypt/"],
        ["node_modules", "  .quancrypt/  "],
        [".quancrypt/*"],
        ["**/.quancrypt"],
    ],
)
def test_a_plain_pattern_covers_the_state_directory(lines: list[str]) -> None:
    assert covers_quancrypt(lines)


@pytest.mark.parametrize(
    "lines", [[], ["# .quancrypt/"], ["!.quancrypt/"], [".quancrypt-old/"], ["quancrypt/"], ["target/", "*.log"]]
)
def test_comments_negations_and_other_names_do_not_cover_it(lines: list[str]) -> None:
    assert not covers_quancrypt(lines)
