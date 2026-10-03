# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/collection_defaults.py
"""
Collection Defaults — a photographer's starting values for NEW collections.

Storage: User.collection_defaults (a small JSON object). Nothing else is
stored and nothing here is a second design system: the `design` block uses the
exact vocabulary the Design page already persists into
Gallery.design_settings, and every other key maps 1:1 onto an existing Gallery
column. Only settings that exist per-gallery today are offered; there is no
favorites/slideshow default because there is no such per-gallery setting.

Applied ONCE, when a collection is created (GalleryCreateSerializer), and only
for values the creation request did not set explicitly. They are never read
when a gallery is edited or displayed, so changing defaults can never alter an
existing collection.

Schema:
    {
      "is_published":       bool,         # new collections start published (visible) or as drafts
      "is_downloadable":    bool,         # Gallery.allow_download
      "watermark_enabled":  bool,         # Pro+; re-checked when applied
      "expires_in_days":    int | null,   # Gallery.expires_at = created + N days; null = never
      "design": {                         # Gallery.design_settings (subset)
          "typography", "colorPalette", "layout", "gridStyle", "thumbSize", "gridSpacing"
      }
    }
"""
from datetime import timedelta

from django.utils import timezone

# Mirrors frontend/src/utils/designSettings.js — the fixed MVP vocabulary
# (docs/KYAPTURE_PRODUCT_DECISIONS.md #6: a small fixed set, not a theme builder).
DESIGN_CHOICES = {
    'typography': ('sans', 'serif', 'modern', 'timeless', 'bold', 'subtle'),
    'colorPalette': ('light', 'gold', 'rose', 'terracotta', 'sand', 'olive', 'agave', 'sea', 'dark'),
    'layout': ('center', 'left', 'novel', 'vintage', 'frame', 'stripe'),
    'gridStyle': ('vertical', 'horizontal'),
    'thumbSize': ('regular', 'large'),
}
GRID_SPACING_RANGE = (4, 32)          # the Design page's slider range
EXPIRY_DAYS_RANGE = (1, 3650)
BOOLEAN_KEYS = ('is_published', 'is_downloadable', 'watermark_enabled')
ALLOWED_KEYS = set(BOOLEAN_KEYS) | {'expires_in_days', 'design'}


def _is_int(value):
    return isinstance(value, int) and not isinstance(value, bool)


def validate_collection_defaults(raw):
    """
    Returns (normalized, errors). Unknown keys are ERRORS (not dropped), so a
    typo can never look like a saved setting. `errors` maps key -> message.
    """
    if not isinstance(raw, dict):
        return None, {'collection_defaults': 'Collection defaults must be an object.'}

    errors, clean = {}, {}
    for key in raw:
        if key not in ALLOWED_KEYS:
            errors[key] = 'Unknown collection default.'

    for key in BOOLEAN_KEYS:
        if key in raw:
            if isinstance(raw[key], bool):
                clean[key] = raw[key]
            else:
                errors[key] = 'Must be true or false.'

    if 'expires_in_days' in raw:
        days = raw['expires_in_days']
        low, high = EXPIRY_DAYS_RANGE
        if days is None:
            clean['expires_in_days'] = None
        elif _is_int(days) and low <= days <= high:
            clean['expires_in_days'] = days
        else:
            errors['expires_in_days'] = f'Must be a whole number of days between {low} and {high}, or empty for never.'

    if 'design' in raw:
        design = raw['design']
        if not isinstance(design, dict):
            errors['design'] = 'Design defaults must be an object.'
        else:
            clean_design = {}
            for key, value in design.items():
                if key in DESIGN_CHOICES:
                    if value in DESIGN_CHOICES[key]:
                        clean_design[key] = value
                    else:
                        errors[f'design.{key}'] = f"Must be one of: {', '.join(DESIGN_CHOICES[key])}."
                elif key == 'gridSpacing':
                    low, high = GRID_SPACING_RANGE
                    if _is_int(value) and low <= value <= high:
                        clean_design[key] = value
                    else:
                        errors['design.gridSpacing'] = f'Must be a whole number between {low} and {high}.'
                else:
                    errors[f'design.{key}'] = 'Unknown design default.'
            clean['design'] = clean_design

    return (None, errors) if errors else (clean, {})


def get_collection_defaults(user):
    """The user's stored defaults, re-validated; anything invalid/legacy is dropped, never applied."""
    stored = user.collection_defaults if isinstance(user.collection_defaults, dict) else {}
    clean, errors = validate_collection_defaults(stored)
    if clean is not None:
        return clean
    # Stored data that no longer validates: keep only the individually-valid keys.
    salvaged = {}
    for key, value in stored.items():
        ok, _ = validate_collection_defaults({key: value})
        if ok:
            salvaged.update(ok)
    return salvaged


def apply_collection_defaults(user, create_kwargs, explicit_keys):
    """
    Fills `create_kwargs` (the field values a new Gallery is about to be created
    with) from the user's defaults, skipping any field the request set
    explicitly (`explicit_keys` = the keys present in the request body).
    Returns the updated dict; never mutates the input.

    - watermark_enabled is only applied while the user is still entitled to
      Watermark; a lapsed plan silently gets none instead of failing creation.
    - branding_color follows the photographer's brand color (Branding
      settings), the existing documented "default brand accent colour".
    """
    from apps.subscriptions.entitlements import WATERMARK, has_feature

    result = dict(create_kwargs)
    defaults = get_collection_defaults(user)

    if 'branding_color' not in explicit_keys and getattr(user, 'branding_color', None):
        result['branding_color'] = user.branding_color

    if 'is_published' not in explicit_keys and 'is_published' in defaults:
        result['is_published'] = defaults['is_published']

    if 'is_downloadable' not in explicit_keys and 'is_downloadable' in defaults:
        result['allow_download'] = defaults['is_downloadable']

    if 'watermark_enabled' not in explicit_keys and defaults.get('watermark_enabled'):
        if has_feature(user, WATERMARK):
            result['watermark_enabled'] = True

    if 'expires_at' not in explicit_keys and defaults.get('expires_in_days'):
        result['expires_at'] = timezone.now() + timedelta(days=defaults['expires_in_days'])

    if defaults.get('design'):
        result['design_settings'] = dict(defaults['design'])

    return result
