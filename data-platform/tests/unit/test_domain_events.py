from __future__ import annotations

import json

import pytest

from quancrypt_data.domain.events import (
    MAX_QUARANTINE_RECORD_BYTES,
    SOURCE_BY_EVENT_TYPE,
    EventSource,
    ProjectKeyTable,
    clip_message,
    fingerprint,
    has_unstorable_text,
    is_project_key,
    parse_timestamp,
    project_key_of,
    require_project_key,
    storable_record,
)
from tests.support.envelopes import KEY_A, PAYLOADS


class TestProjectKey:
    def test_a_project_key_is_64_lower_case_hex_digits(self) -> None:
        assert is_project_key(KEY_A)
        assert not is_project_key("A" * 64)
        assert not is_project_key("a" * 63)
        assert not is_project_key("a" * 65)
        assert not is_project_key(None)
        assert not is_project_key(12)

    def test_require_refuses_a_bad_key(self) -> None:
        with pytest.raises(ValueError, match="project_key"):
            require_project_key("not-a-key")
        assert require_project_key(KEY_A) == KEY_A

    def test_the_key_of_an_item_is_read_only_when_valid(self) -> None:
        assert project_key_of({"project_key": KEY_A}) == KEY_A
        assert project_key_of({"project_key": "x"}) is None
        assert project_key_of(["project_key"]) is None
        assert project_key_of({}) is None


class TestTimestamp:
    @pytest.mark.parametrize(
        "text",
        [
            "2026-10-09T10:00:00Z",
            "2026-10-09T10:00:00.123Z",
            "2026-10-09T10:00:00.123456789Z",
            "2026-10-09T13:00:00+03:00",
        ],
    )
    def test_rfc_3339_forms_the_relays_write_are_read_as_utc(self, text: str) -> None:
        parsed = parse_timestamp(text)
        assert parsed is not None
        assert parsed.utcoffset() is not None
        assert parsed.utcoffset().total_seconds() == 0  # type: ignore[union-attr]
        assert (parsed.hour, parsed.minute) == (10, 0)

    @pytest.mark.parametrize(
        "value",
        ["2026-10-09", "2026-10-09 10:00:00Z", "2026-10-09T10:00:00", "yesterday", "", "2026-13-09T10:00:00Z", 5, None],
    )
    def test_anything_else_is_not_a_timestamp(self, value: object) -> None:
        assert parse_timestamp(value) is None


class TestUnstorableText:
    def test_nul_and_lone_surrogates_are_found_anywhere(self) -> None:
        assert has_unstorable_text("a\x00b")
        assert has_unstorable_text("\ud800")
        assert has_unstorable_text({"k": ["ok", {"deep": "x\x00"}]})
        assert has_unstorable_text({"bad\x00key": 1})

    def test_ordinary_text_is_fine(self) -> None:
        assert not has_unstorable_text({"k": ["çğış", "😀", 1, None, True]})

    def test_a_very_deep_structure_does_not_overflow_the_stack(self) -> None:
        nested: object = "leaf"
        for _ in range(5000):
            nested = [nested]
        assert not has_unstorable_text(nested)


class TestQuarantineRecord:
    def test_the_fingerprint_is_stable_and_ignores_key_order(self) -> None:
        assert fingerprint({"a": 1, "b": [1, 2]}) == fingerprint({"b": [1, 2], "a": 1})
        assert fingerprint({"a": 1}) != fingerprint({"a": 2})
        assert len(fingerprint({"a": 1})) == 64

    def test_a_record_is_kept_verbatim_when_small_and_clean(self) -> None:
        record = {"event_id": "x", "n": 1}
        assert storable_record(record) == record

    def test_an_unstorable_record_is_replaced_by_a_marker_without_its_content(self) -> None:
        marker = storable_record({"secret": "a\x00b"})
        assert marker == {"unstorable": True, "reason": "NUL character or lone surrogate"}
        assert "secret" not in json.dumps(marker)

    def test_a_large_record_is_replaced_by_a_size_marker(self) -> None:
        marker = storable_record({"blob": "x" * MAX_QUARANTINE_RECORD_BYTES})
        assert isinstance(marker, dict)
        assert marker["truncated"] is True
        assert marker["size_bytes"] > MAX_QUARANTINE_RECORD_BYTES

    def test_a_message_is_clipped(self) -> None:
        assert clip_message("short") == "short"
        assert len(clip_message("x" * 900)) == 500


class TestRegistry:
    def test_a_table_identifier_is_lower_case_letters_and_underscores_only(self) -> None:
        assert ProjectKeyTable("raw", "event").qualified == "raw.event"
        for schema, name in (("raw", "event; DROP TABLE x"), ("Raw", "event"), ("raw", "ev-ent"), ("", "event")):
            with pytest.raises(ValueError, match="identifier"):
                ProjectKeyTable(schema, name)


class TestEventSources:
    def test_every_payload_sample_has_a_source_and_scope_decision_is_the_only_agent_event(self) -> None:
        assert set(PAYLOADS) == set(SOURCE_BY_EVENT_TYPE)
        agent = {name for name, source in SOURCE_BY_EVENT_TYPE.items() if source is EventSource.AGENT_SERVICE}
        assert agent == {"scope_decision"}
