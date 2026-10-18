"""Does the user's `.gitignore` already keep `.quancrypt/` out of git? (D-272: the CLI only advises.)"""

from __future__ import annotations

from collections.abc import Iterable

IGNORE_LINE = ".quancrypt/"
_COVERING = frozenset(
    {
        ".quancrypt",
        ".quancrypt/",
        "/.quancrypt",
        "/.quancrypt/",
        ".quancrypt/*",
        ".quancrypt/**",
        "/.quancrypt/*",
        "/.quancrypt/**",
        "**/.quancrypt",
        "**/.quancrypt/",
    }
)


def covers_quancrypt(lines: Iterable[str]) -> bool:
    """True when a plain pattern ignores the `.quancrypt` directory (comments and negations do not count)."""
    return any(line.strip() in _COVERING for line in lines)
