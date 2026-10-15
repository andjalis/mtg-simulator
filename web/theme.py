"""The shared look of the web pages: fonts, the stylesheet (static/theme.css) and the masthead.

    page(title, body, active)   -> a whole page in the theme
    dress(page_html, active)    -> an existing page (index.html, a ladder report) put in the theme
"""
from __future__ import annotations

import html

FONTS = ("https://fonts.googleapis.com/css2?family=Cinzel:wght@500;700&family=Inter:wght@400;500;600;700"
         "&family=Spectral:ital@1&display=swap")
HEAD = (f'<link rel="preconnect" href="https://fonts.googleapis.com">'
        f'<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>'
        f'<link rel="stylesheet" href="{FONTS}"><link rel="stylesheet" href="/static/theme.css">')

# The five mana colours on a ring (white, blue, black, red, green), as the brand mark.
WHEEL = ('<svg class="wheel" viewBox="0 0 40 40" aria-hidden="true">'
         '<circle cx="20" cy="20" r="13" fill="none" stroke="#5e4622" stroke-width="1.5"/>'
         + "".join(f'<circle cx="{x}" cy="{y}" r="5.2" fill="{c}" stroke="#0c0a09" stroke-width="1.5"/>'
                   for x, y, c in ((20, 6, "#f4ead2"), (33.3, 15.7, "#3d8fe0"), (28.2, 31.3, "#9d8bb3"),
                                   (11.8, 31.3, "#e2553b"), (6.7, 15.7, "#3fa262")))
         + '</svg>')
PIPS = '<span class="pips" aria-hidden="true">' + "".join(f'<i class="pip {c}"></i>' for c in "wubrg") + "</span>"
NAV = [("test", "/", "Test a deck"), ("leaderboard", "/leaderboard", "Leaderboard")]


def masthead(active: str = "") -> str:
    links = "".join(f'<a href="{href}"{" class=on" if key == active else ""}>{label}</a>' for key, href, label in NAV)
    return (f'<header class="masthead"><div class="in"><a class="brand" href="/">{WHEEL}'
            f'<span><b>MTG SIMULATOR</b><small>Ranked deck trials</small></span></a>'
            f'<nav>{links}</nav></div></header>')


def titlebar(title: str) -> str:
    return f'<div class="titlebar"><h2>{html.escape(title)}</h2>{PIPS}</div>'


def frame(title: str, inner: str, cls: str = "") -> str:
    """A panel drawn like a card: gilt border, dark face, a name bar on top."""
    return f'<section class="frame {cls}"><div class="face">{titlebar(title)}{inner}</div></section>'


def page(title: str, body: str, active: str = "") -> str:
    return ('<!doctype html><html lang="en"><head><meta charset="utf-8">'
            '<meta name="viewport" content="width=device-width,initial-scale=1">'
            f'<title>{html.escape(title)}</title>{HEAD}</head><body>{masthead(active)}'
            f'<main class="page">{body}</main></body></html>')


def dress(page_html: str, active: str = "", before: str = "", after: str = "") -> str:
    """Add the theme's head tags and masthead to a page that was rendered without them,
    with `before` and `after` around the page's own body."""
    return (page_html.replace("</head>", HEAD + "</head>", 1)
            .replace("<body>", "<body>" + masthead(active) + before, 1)
            .replace("</body>", after + "</body>", 1))
