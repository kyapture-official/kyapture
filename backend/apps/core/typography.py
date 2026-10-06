# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/typography.py
"""
Collection typography: six named styles, not a font picker (docs/KYAPTURE_TYPOGRAPHY.md).

Storage is ONE key, `design_settings.typography` (the same key Collection
Defaults already stores under `design.typography`), holding one of the six
style ids below. Everything a browser needs to draw the style (family stack,
weight, letter-spacing, case) lives HERE as server constants and is looked up
by id at read time. A stored value is never copied into CSS: an unknown or
legacy id resolves to DEFAULT_TYPOGRAPHY, and the writers reject it.

Every family is SIL OFL 1.1 and meant to be self-hosted from our own origin
(nginx CSP: `font-src 'self'`). The stack always ends in system fonts, so the
gallery stays readable when a font file fails to load.
"""

DEFAULT_TYPOGRAPHY = 'serif'          # same default as frontend DEFAULT_DESIGN_SETTINGS

_SANS_FALLBACK = 'system-ui, -apple-system, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif'
_SERIF_FALLBACK = 'Georgia, "Times New Roman", Times, serif'

# id -> presentation. Order is the order the Design page lists them in.
TYPOGRAPHY_STYLES = {
    'sans': {
        'label': 'Sans', 'family_key': 'inter', 'family': 'Inter',
        'font_family': f'"Inter", {_SANS_FALLBACK}',
        'weight': 400, 'font_style': 'normal', 'letter_spacing': '0em', 'text_transform': 'none',
    },
    'serif': {
        'label': 'Serif', 'family_key': 'libre-baskerville', 'family': 'Libre Baskerville',
        'font_family': f'"Libre Baskerville", {_SERIF_FALLBACK}',
        'weight': 400, 'font_style': 'normal', 'letter_spacing': '0em', 'text_transform': 'none',
    },
    'modern': {
        'label': 'Modern', 'family_key': 'jost', 'family': 'Jost',
        'font_family': f'"Jost", {_SANS_FALLBACK}',
        'weight': 400, 'font_style': 'normal', 'letter_spacing': '0.12em', 'text_transform': 'uppercase',
    },
    'timeless': {
        'label': 'Timeless', 'family_key': 'cormorant-garamond', 'family': 'Cormorant Garamond',
        'font_family': f'"Cormorant Garamond", {_SERIF_FALLBACK}',
        'weight': 300, 'font_style': 'italic', 'letter_spacing': '0.02em', 'text_transform': 'none',
    },
    'bold': {
        'label': 'Bold', 'family_key': 'oswald', 'family': 'Oswald',
        'font_family': f'"Oswald", Impact, "Arial Narrow Bold", {_SANS_FALLBACK}',
        'weight': 600, 'font_style': 'normal', 'letter_spacing': '0.02em', 'text_transform': 'uppercase',
    },
    'subtle': {
        'label': 'Subtle', 'family_key': 'work-sans', 'family': 'Work Sans',
        'font_family': f'"Work Sans", {_SANS_FALLBACK}',
        'weight': 300, 'font_style': 'normal', 'letter_spacing': '0.05em', 'text_transform': 'none',
    },
}

TYPOGRAPHY_IDS = tuple(TYPOGRAPHY_STYLES)

# The only keys the public payload carries for a style.
_PUBLIC_KEYS = ('family_key', 'font_family', 'weight', 'font_style', 'letter_spacing', 'text_transform')


def resolve_typography(style_id):
    """
    The public, presentation-only description of a style id. Anything that is
    not one of the six ids (missing, None, legacy, tampered, unhashable)
    resolves to the app default; this never raises.
    """
    key = style_id if isinstance(style_id, str) and style_id in TYPOGRAPHY_STYLES else DEFAULT_TYPOGRAPHY
    style = TYPOGRAPHY_STYLES[key]
    return {'id': key, **{k: style[k] for k in _PUBLIC_KEYS}}
