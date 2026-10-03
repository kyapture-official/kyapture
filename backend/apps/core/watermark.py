# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/watermark.py
"""
Watermark configuration, validation and rendering.

Scope of a watermark (a product contract, enforced by the callers and tests):
  - it is applied ONLY to client-visible derivatives: the 2048px display,
    1280px medium and 640px thumbnail WebP tiers;
  - it is NEVER applied to the preserved original (`original_file`) and NEVER
    to the Download Master (`download_file`) — the master is the clean,
    full-quality deliverable a client is authorized to download, built from
    the original. A "Web Size" download is the display derivative itself, so
    it carries the watermark exactly as the gallery shows it.

Configuration lives in the existing persistence, not in a new store:
  - on/off:   Gallery.watermark_enabled (existing column)
  - settings: Gallery.design_settings['watermark'] (existing JSON blob)
and is only honoured while the photographer is entitled to Watermark
(apps/subscriptions/entitlements.py).

Sizes are RELATIVE (fractions of the image), so one configuration renders
sensibly on a 640px thumbnail and a 4K display tier alike:
  size    — mark width as a percentage of image width        (5–50, default 20)
  opacity — mark opacity percentage                          (5–100, default 55)
  margin  — gap to the edge as a percentage of the SHORTER   (0–20, default 5)
            image edge, so portrait and landscape get an even inset
"""
import hashlib
import io
import json
import logging
import os
from dataclasses import dataclass, field
from typing import Any, Optional

from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

WATERMARK_TYPES = ('text', 'logo')
WATERMARK_POSITIONS = (
    'top-left', 'top-center', 'top-right',
    'center-left', 'center', 'center-right',
    'bottom-left', 'bottom-center', 'bottom-right',
)
TEXT_MAX_LENGTH = 60

DEFAULTS = {
    'type': 'text',
    'text': '',               # blank text means "© <photographer name>"
    'position': 'bottom-right',
    'opacity': 55,
    'size': 20,
    'margin': 5,
}
_RANGES = {'opacity': (5, 100), 'size': (5, 50), 'margin': (0, 20)}

# A mark never covers more than this fraction of the image height, whatever
# its aspect ratio (a very tall logo, a long caption in a narrow crop).
_MAX_HEIGHT_FRACTION = 0.25
_MIN_MARK_WIDTH_PX = 24
_LOGO_WORKING_EDGE = 1024      # logos are downscaled to this once, before reuse
_TEXT_RENDER_PX = 96           # text is drawn large, then scaled to target size

_FONT_CANDIDATES = (
    os.getenv('WATERMARK_FONT_PATH', ''),
    '/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf',
    '/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf',
    '/usr/share/fonts/dejavu/DejaVuSans-Bold.ttf',
    'DejaVuSans-Bold.ttf',
    'arialbd.ttf',
    'Arial Bold.ttf',
)


# ─────────────────────────────────────────────────────────────
# CONFIGURATION VALIDATION (used by the gallery serializer)
# ─────────────────────────────────────────────────────────────

def validate_watermark_config(raw):
    """
    Validates a client-supplied watermark settings object and returns
    (normalized_config, errors). Unknown keys are dropped; every value is
    range-checked, so nothing unvalidated reaches the rendering code.
    `errors` maps field -> message (empty when valid).
    """
    if not isinstance(raw, dict):
        return None, {'watermark': 'Watermark settings must be an object.'}

    errors = {}
    config = dict(DEFAULTS)

    kind = raw.get('type', DEFAULTS['type'])
    if kind not in WATERMARK_TYPES:
        errors['type'] = "Watermark type must be 'text' or 'logo'."
    else:
        config['type'] = kind

    position = raw.get('position', DEFAULTS['position'])
    if position not in WATERMARK_POSITIONS:
        errors['position'] = 'Invalid watermark position.'
    else:
        config['position'] = position

    text = raw.get('text', DEFAULTS['text'])
    if not isinstance(text, str):
        errors['text'] = 'Watermark text must be text.'
    else:
        text = ' '.join(text.split())          # collapse newlines/control whitespace
        # Plain text only: this string is drawn into pixels, but it is also
        # echoed back to the dashboard, so refuse markup outright.
        if '<' in text or '>' in text:
            errors['text'] = 'Watermark text cannot contain < or >.'
        elif len(text) > TEXT_MAX_LENGTH:
            errors['text'] = f'Watermark text must be {TEXT_MAX_LENGTH} characters or fewer.'
        else:
            config['text'] = text

    for key, (low, high) in _RANGES.items():
        value = raw.get(key, DEFAULTS[key])
        if isinstance(value, bool) or not isinstance(value, (int, float)) or not (low <= value <= high):
            errors[key] = f'Watermark {key} must be a number between {low} and {high}.'
        else:
            config[key] = int(round(value))

    return (None, errors) if errors else (config, {})


# ─────────────────────────────────────────────────────────────
# SPEC — the resolved, ready-to-render watermark for one gallery
# ─────────────────────────────────────────────────────────────

@dataclass(frozen=True)
class WatermarkSpec:
    kind: str                         # 'text' | 'logo'
    position: str
    opacity: float                    # 0..1
    size: float                       # fraction of image width
    margin: float                     # fraction of the image's shorter edge
    text: str = ''
    logo: Optional[Any] = field(default=None, compare=False, repr=False)   # PIL RGBA image
    logo_key: str = ''                # stored logo name — changes when the logo is replaced
    signature: str = ''


def _signature(kind, text, position, opacity, size, margin, logo_key):
    payload = json.dumps(
        [kind, text, position, opacity, size, margin, logo_key], sort_keys=True, ensure_ascii=False
    )
    return hashlib.sha256(payload.encode('utf-8')).hexdigest()[:16]


def make_spec(config, logo=None, logo_key=''):
    kind = config['type']
    return WatermarkSpec(
        kind=kind,
        position=config['position'],
        opacity=config['opacity'] / 100.0,
        size=config['size'] / 100.0,
        margin=config['margin'] / 100.0,
        text=config['text'] if kind == 'text' else '',
        logo=logo if kind == 'logo' else None,
        logo_key=logo_key if kind == 'logo' else '',
        signature=_signature(
            kind, config['text'] if kind == 'text' else '', config['position'],
            config['opacity'], config['size'], config['margin'],
            logo_key if kind == 'logo' else '',
        ),
    )


def _load_logo(photographer):
    """The photographer's branding logo as an RGBA image, or None (logged) if unusable."""
    if not photographer.logo:
        return None
    try:
        photographer.logo.open('rb')
        try:
            img = Image.open(photographer.logo)
            img.load()
        finally:
            photographer.logo.close()
        img = img.convert('RGBA')
        img.thumbnail((_LOGO_WORKING_EDGE, _LOGO_WORKING_EDGE), Image.Resampling.LANCZOS)
        return img
    except Exception:
        logger.exception('Watermark logo for photographer %s could not be loaded', photographer.pk)
        return None


def build_watermark_spec(gallery):
    """
    The watermark to apply to this gallery's NEW client-visible derivatives,
    or None for "no watermark". None whenever the gallery has it switched
    off, the photographer is not (or is no longer) entitled to Watermark, or a
    logo watermark has no usable logo — in the last case the derivative
    simply stays unwatermarked and the reason is logged.
    """
    from apps.subscriptions.entitlements import WATERMARK, has_feature

    if not gallery.watermark_enabled:
        return None
    photographer = gallery.photographer
    if not has_feature(photographer, WATERMARK):
        logger.info('Watermark skipped for gallery %s: photographer is not entitled', gallery.pk)
        return None

    stored = (gallery.design_settings or {}).get('watermark') if isinstance(gallery.design_settings, dict) else None
    config, errors = validate_watermark_config(stored if isinstance(stored, dict) else {})
    if errors:
        # Stored settings that no longer validate: fall back to the defaults
        # rather than silently dropping the photographer's watermark.
        logger.warning('Gallery %s has invalid watermark settings %s; using defaults', gallery.pk, errors)
        config = dict(DEFAULTS)

    if config['type'] == 'logo':
        logo = _load_logo(photographer)
        if logo is None:
            logger.warning('Gallery %s wants a logo watermark but has no usable logo; skipping', gallery.pk)
            return None
        return make_spec(config, logo=logo, logo_key=photographer.logo.name)

    if not config['text']:
        config['text'] = f"© {photographer.display_name or photographer.username}"
    return make_spec(config)


def current_signature(gallery):
    """Signature of the watermark a freshly processed derivative would get ('' = none)."""
    spec = build_watermark_spec(gallery)
    return spec.signature if spec else ''


# ─────────────────────────────────────────────────────────────
# RENDERING
# ─────────────────────────────────────────────────────────────

def _load_font(px):
    for candidate in _FONT_CANDIDATES:
        if not candidate:
            continue
        try:
            return ImageFont.truetype(candidate, px)
        except (OSError, ValueError):
            continue
    try:
        return ImageFont.load_default(size=px)       # scalable (Pillow >= 10.1, needs FreeType)
    except (TypeError, OSError):
        return ImageFont.load_default()              # tiny bitmap font; scaled up below


def _render_text_mark(text):
    """White text with a soft dark shadow on a tight transparent canvas."""
    font = _load_font(_TEXT_RENDER_PX)
    scratch = ImageDraw.Draw(Image.new('RGBA', (1, 1)))
    left, top, right, bottom = scratch.textbbox((0, 0), text, font=font)
    shadow = max(1, _TEXT_RENDER_PX // 24)
    pad = shadow + 2
    width = max(1, right - left) + pad * 2
    height = max(1, bottom - top) + pad * 2
    canvas = Image.new('RGBA', (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(canvas)
    origin = (pad - left, pad - top)
    draw.text((origin[0] + shadow, origin[1] + shadow), text, font=font, fill=(0, 0, 0, 150))
    draw.text(origin, text, font=font, fill=(255, 255, 255, 255))
    return canvas


def _scaled_mark(spec, image_size):
    width, height = image_size
    mark = spec.logo if spec.kind == 'logo' else _render_text_mark(spec.text)
    if mark is None or mark.width < 1 or mark.height < 1:
        return None
    target_w = max(_MIN_MARK_WIDTH_PX, int(round(width * spec.size)))
    target_w = min(target_w, width)
    target_h = max(1, int(round(mark.height * target_w / mark.width)))
    max_h = max(1, int(height * _MAX_HEIGHT_FRACTION))
    if target_h > max_h:
        target_w = max(1, int(round(target_w * max_h / target_h)))
        target_h = max_h
    return mark.resize((target_w, target_h), Image.Resampling.LANCZOS)


_ANCHORS = {
    'top-left': ('left', 'top'), 'top-center': ('center', 'top'), 'top-right': ('right', 'top'),
    'center-left': ('left', 'center'), 'center': ('center', 'center'), 'center-right': ('right', 'center'),
    'bottom-left': ('left', 'bottom'), 'bottom-center': ('center', 'bottom'), 'bottom-right': ('right', 'bottom'),
}


def _anchor(position, image_size, mark_size, margin_px):
    width, height = image_size
    mark_w, mark_h = mark_size
    horizontal, vertical = _ANCHORS[position]
    x = {'left': margin_px, 'center': (width - mark_w) // 2, 'right': width - mark_w - margin_px}[horizontal]
    y = {'top': margin_px, 'center': (height - mark_h) // 2, 'bottom': height - mark_h - margin_px}[vertical]
    return max(0, x), max(0, y)


def apply_watermark(img, spec):
    """
    Returns `img` (RGB) with `spec` composited on a COPY — the input image is
    never modified. Never raises: any failure is logged and the unwatermarked
    image is returned, so a watermark problem can degrade a derivative but
    can never fail or block an upload's processing.
    """
    plain = img.convert('RGB') if img.mode != 'RGB' else img
    if spec is None:
        return plain
    try:
        base = img.convert('RGBA')
        mark = _scaled_mark(spec, base.size)
        if mark is None:
            return plain
        alpha = mark.getchannel('A').point(lambda value: int(value * spec.opacity))
        mark.putalpha(alpha)
        margin_px = int(round(spec.margin * min(base.size)))
        x, y = _anchor(spec.position, base.size, mark.size, margin_px)
        layer = Image.new('RGBA', base.size, (0, 0, 0, 0))
        layer.paste(mark, (x, y))
        return Image.alpha_composite(base, layer).convert('RGB')
    except Exception:
        logger.exception('Watermark rendering failed (kind=%s); serving unwatermarked derivative',
                         getattr(spec, 'kind', '?'))
        return plain


def versioned_url(url, asset):
    """
    Appends `?v=<watermark signature>` to a derivative's URL.

    Derivatives are stored at deterministic keys and served with long-lived /
    `immutable` caching (apps/core/storage.py). Re-applying a watermark
    overwrites those keys in place, so without a changing URL a browser or CDN
    would keep showing the old image. The signature identifies the watermark
    baked into the stored bytes ('0' for none), so the URL changes exactly
    when the pixels do and is identical again if the same settings return.
    """
    if not url:
        return url
    version = getattr(asset, 'watermark_signature', '') or '0'
    return f"{url}{'&' if '?' in url else '?'}v={version}"
