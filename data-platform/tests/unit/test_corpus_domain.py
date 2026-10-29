"""The corpus rules (P6.2): repository addresses, the selection policy, license recognition, the clone checks."""

from __future__ import annotations

import pytest

from quancrypt_data.domain.corpus import (
    ALLOWED_LICENSES,
    Candidate,
    Eligibility,
    ExclusionReason,
    InvalidRepoUrlError,
    Rejection,
    RepoRef,
    SelectionPolicy,
    is_valid_benchmark_name,
)
from quancrypt_data.domain.licenses import identify_license

MIT = """MIT License

Copyright (c) 2024 Someone

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED.
"""

APACHE = """                                 Apache License
                           Version 2.0, January 2004
                        http://www.apache.org/licenses/

   TERMS AND CONDITIONS FOR USE, REPRODUCTION, AND DISTRIBUTION
"""

BSD_2 = """Redistribution and use in source and binary forms, with or without modification, are permitted provided that the
following conditions are met:

1. Redistributions of source code must retain the above copyright notice, this list of conditions and the following
   disclaimer.

2. Redistributions in binary form must reproduce the above copyright notice, this list of conditions and the following
   disclaimer in the documentation and/or other materials provided with the distribution.
"""

BSD_3 = (
    BSD_2
    + """
3. Neither the name of the copyright holder nor the names of its contributors may be used to endorse or promote products
   derived from this software without specific prior written permission.
"""
)

GPL = "GNU GENERAL PUBLIC LICENSE Version 3, 29 June 2007\n" + MIT

# Standard texts with a term added that makes them another license: they must not be recognised as an allowed one.
BSD_4 = (
    BSD_3
    + "\n4. All advertising materials mentioning features or use of this software must display the following"
    + " acknowledgement.\n"
)
MIT_COMMONS_CLAUSE = MIT + "\nCommons Clause License Condition v1.0: the Software may not be sold.\n"


def candidate(url: str = "https://github.com/acme/shop", **kwargs: object) -> Candidate:
    fields: dict[str, object] = {
        "default_branch": None,
        "license_spdx": None,
        "language": None,
        "service_count": None,
    }
    fields.update(kwargs)
    return Candidate(repo=RepoRef.parse(url), **fields)  # type: ignore[arg-type]


class TestRepoRef:
    @pytest.mark.parametrize(
        "text",
        [
            "https://github.com/acme/shop",
            "https://github.com/acme/shop/",
            "https://github.com/acme/shop.git",
            "  https://github.com/Acme/Shop-App.v2  ",
        ],
    )
    def test_a_github_https_address_is_accepted(self, text: str) -> None:
        repo = RepoRef.parse(text)

        assert repo.url.startswith("https://github.com/")
        assert repo.canonical == repo.url.lower()

    @pytest.mark.parametrize(
        "text",
        [
            "http://github.com/acme/shop",
            "git@github.com:acme/shop.git",
            "ssh://git@github.com/acme/shop",
            "file:///etc",
            "ext::sh -c touch /tmp/x",
            "https://gitlab.com/acme/shop",
            "https://github.com.evil.example/acme/shop",
            "https://user:pw@github.com/acme/shop",
            "https://github.com:8443/acme/shop",
            "https://github.com/acme/shop?x=1",
            "https://github.com/acme/shop#frag",
            "https://github.com/acme/shop/extra",
            "https://github.com/acme/..",
            "https://github.com/acme/.hidden",
            "https://github.com/-acme/shop",
            "https://github.com/acme/shop name",
            "",
        ],
    )
    def test_anything_else_is_refused_without_repeating_it(self, text: str) -> None:
        with pytest.raises(InvalidRepoUrlError) as raised:
            RepoRef.parse(text)

        assert text.strip() == "" or text.strip() not in str(raised.value)

    def test_the_directory_name_is_lower_case_and_free_of_separators(self) -> None:
        repo = RepoRef.parse("https://github.com/Acme/Shop.App")

        assert repo.dir_name == "acme__shop.app"
        assert "/" not in repo.dir_name

    def test_the_same_repository_in_another_case_is_the_same_project(self) -> None:
        assert (
            RepoRef.parse("https://github.com/ACME/Shop").canonical
            == RepoRef.parse("https://github.com/acme/shop").canonical
        )


class TestSelection:
    def test_what_the_dataset_rules_out_is_left_out_and_counted(self) -> None:
        policy = SelectionPolicy()
        candidates = [
            candidate("https://github.com/a/ok", language="Java", service_count=5, license_spdx="MIT"),
            candidate("https://github.com/a/python", language="Python"),
            candidate("https://github.com/a/small", language="Java", service_count=2),
            candidate("https://github.com/a/gpl", language="Java", license_spdx="GPL-3.0"),
            candidate("https://github.com/a/ok", language="Java"),  # the same repository twice
        ]

        selected, turned_away = policy.select(candidates, 10)

        assert [p.candidate.repo.url for p in selected] == ["https://github.com/a/ok"]
        assert turned_away == {
            Rejection.NOT_JAVA: 1,
            Rejection.TOO_FEW_SERVICES: 1,
            Rejection.LICENSE_NOT_ALLOWED: 1,
            Rejection.DUPLICATE: 1,
        }

    def test_what_the_dataset_does_not_say_is_not_held_against_a_project(self) -> None:
        selected, turned_away = SelectionPolicy().select([candidate()], 5)

        assert len(selected) == 1
        assert turned_away == {}
        assert "to verify" in selected[0].reason

    @pytest.mark.parametrize("license_spdx", sorted(ALLOWED_LICENSES))
    def test_the_four_allowed_licenses_pass(self, license_spdx: str) -> None:
        assert SelectionPolicy().rejection(candidate(license_spdx=license_spdx)) is None

    def test_the_sample_is_the_same_every_time_and_a_longer_list_starts_with_the_shorter_one(self) -> None:
        pool = [candidate(f"https://github.com/o/p{i:03d}") for i in range(200)]
        policy = SelectionPolicy()

        first, _ = policy.select(pool, 100)
        again, _ = policy.select(list(reversed(pool)), 100)
        longer, _ = policy.select(pool, 130)

        urls = [p.candidate.repo.url for p in first]
        assert urls == [p.candidate.repo.url for p in again]
        assert urls == [p.candidate.repo.url for p in longer][:100]
        assert len(longer) == 130
        assert urls != sorted(urls)  # shuffled, not alphabetical

    def test_a_different_seed_gives_a_different_sample(self) -> None:
        pool = [candidate(f"https://github.com/o/p{i:03d}") for i in range(50)]

        a, _ = SelectionPolicy(1).select(pool, 10)
        b, _ = SelectionPolicy(2).select(pool, 10)

        assert [p.candidate.repo.url for p in a] != [p.candidate.repo.url for p in b]


class TestLicenses:
    @pytest.mark.parametrize(
        ("text", "expected"),
        [(MIT, "MIT"), (APACHE, "Apache-2.0"), (BSD_2, "BSD-2-Clause"), (BSD_3, "BSD-3-Clause")],
    )
    def test_the_standard_text_of_each_allowed_license_is_recognised(self, text: str, expected: str) -> None:
        assert identify_license(text) == expected

    def test_the_text_is_recognised_whatever_its_line_breaks_and_case(self) -> None:
        assert identify_license(MIT.upper().replace("\n", "\r\n")) == "MIT"
        assert identify_license(" ".join(MIT.split())) == "MIT"

    @pytest.mark.parametrize(
        "text",
        [
            "",
            "All rights reserved.",
            "Licensed under the Apache License 2.0",
            GPL,
            MIT + APACHE,
            "Copyright (c) 2020 X",
            BSD_4,
            MIT_COMMONS_CLAUSE,
        ],
    )
    def test_anything_else_is_not_recognised(self, text: str) -> None:
        assert identify_license(text) is None


class TestCloneChecks:
    def test_a_project_that_passes_every_check_is_kept(self) -> None:
        assert Eligibility("MIT", True, 3).exclusion() is None

    def test_the_first_failing_check_is_the_reason(self) -> None:
        assert Eligibility(None, True, 5).exclusion() is ExclusionReason.LICENSE_UNVERIFIED
        assert Eligibility("GPL-3.0", True, 5).exclusion() is ExclusionReason.LICENSE_UNVERIFIED
        assert Eligibility("MIT", False, 5).exclusion() is ExclusionReason.NO_SPRING_BOOT
        assert Eligibility("MIT", True, 2).exclusion() is ExclusionReason.TOO_FEW_SERVICES
        assert Eligibility(None, False, 0).exclusion() is ExclusionReason.LICENSE_UNVERIFIED


def test_a_benchmark_code_is_lower_case_digits_and_hyphens() -> None:
    assert is_valid_benchmark_name("cryptoapi-bench")
    assert is_valid_benchmark_name("owasp-benchmark")
    for bad in ("", "Owasp", "a_b", "../x", "a" * 41, "-x"):
        assert not is_valid_benchmark_name(bad)
