"""BrowserOpener adapter: the standard library's `webbrowser`."""

from __future__ import annotations

import webbrowser


class WebbrowserOpener:
    """Implements BrowserOpener."""

    def open(self, url: str) -> bool:
        try:
            return webbrowser.open(url)
        except webbrowser.Error:
            return False
