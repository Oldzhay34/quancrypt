"""License identification from the text of a LICENSE file (P6.2): the four licenses the corpus allows, recognised by the
standard wording of their text. Anything else, a dual text or a modified text is not recognised, which excludes the
project (the safe direction: a license that cannot be verified is not assumed)."""

from __future__ import annotations

import re

_SPACE = re.compile(r"\s+")

_APACHE = ("apache license", "version 2.0", "terms and conditions for use, reproduction, and distribution")
_MIT = (
    "permission is hereby granted, free of charge, to any person obtaining a copy",
    "the above copyright notice and this permission notice shall be included in all copies or substantial portions of the software",  # noqa: E501
    'the software is provided "as is", without warranty of any kind',
)
_BSD = (
    "redistribution and use in source and binary forms, with or without modification, are permitted provided that the following conditions are met",  # noqa: E501
    "redistributions of source code must retain the above copyright notice",
    "redistributions in binary form must reproduce the above copyright notice",
)
_BSD_THIRD_CLAUSE = ("neither the name of", "endorse or promote products derived from this software")
# Extra terms that turn an allowed text into another license: the advertising clause of BSD-4-Clause and the usual
# "source available" riders. A text that carries one is not the standard license, whatever else it says.
_EXTRA_TERMS = (
    "advertising materials mentioning features or use of this software",
    "commons clause",
    "non-commercial",
    "noncommercial",
    "not for commercial",
    "academic use only",
    "research use only",
)
_COPYLEFT = ("gnu general public license", "gnu lesser general public license", "gnu affero general public license")


def identify_license(text: str) -> str | None:
    """The SPDX id of the license the text is, or None when it is none of the four or is more than one."""
    normal = _SPACE.sub(" ", text.casefold().replace("“", '"').replace("”", '"'))
    if any(word in normal for word in _COPYLEFT) or any(term in normal for term in _EXTRA_TERMS):
        return None
    found = []
    if all(part in normal for part in _APACHE):
        found.append("Apache-2.0")
    if all(part in normal for part in _MIT):
        found.append("MIT")
    if all(part in normal for part in _BSD):
        third = all(part in normal for part in _BSD_THIRD_CLAUSE)
        found.append("BSD-3-Clause" if third else "BSD-2-Clause")
    return found[0] if len(found) == 1 else None
