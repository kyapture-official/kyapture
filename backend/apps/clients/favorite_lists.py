# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/favorite_lists.py
"""
Favorite LISTS (Pixieset-style "My Favorites").

A visitor (no account) owns lists inside one gallery. Ownership is the same
identity a Favorite always used - `client_key`: the gallery unlock token for a
protected gallery, or the browser's anonymous `client_uid` for an open one. It
is a credential and is never returned to anyone: the visitor proves ownership by
presenting it, the photographer sees the visitor's EMAIL instead.

Visitor side:  ensure_default_list / create_list / rename / delete / add / remove
Photographer:  visitor_groups (lists grouped by visitor) and list_rows
"""
import hashlib
import hmac
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db.models import Count, Max, Min, OuterRef, Subquery

from .models import ClientSession, Favorite, FavoriteList
from apps.photos.models import MediaAsset

DEFAULT_LIST_NAME = 'My Favorites'
MAX_LIST_NAME_LENGTH = 80
MAX_LISTS_PER_VISITOR = 20


# ─── input cleaning ──────────────────────────────────────────────────────────

def clean_list_name(raw):
    """A trimmed, single-spaced name of 1..80 characters, or None."""
    if not isinstance(raw, str):
        return None
    name = re.sub(r'\s+', ' ', raw).strip()
    if not name or len(name) > MAX_LIST_NAME_LENGTH:
        return None
    return name


def clean_email(raw):
    """(email|None, error|None): empty -> (None, None); malformed -> (None, 'invalid_email')."""
    if raw is None or raw == '':
        return None, None
    if not isinstance(raw, str):
        return None, 'invalid_email'
    email = raw.strip()
    if not email:
        return None, None
    try:
        if len(email) > 254:
            raise ValidationError('too long')
        validate_email(email)
    except ValidationError:
        return None, 'invalid_email'
    return email, None


def clean_visitor_name(raw):
    if not isinstance(raw, str):
        return ''
    return re.sub(r'\s+', ' ', raw).strip()[:80]


# ─── visitor side ────────────────────────────────────────────────────────────

def session_email(gallery, client_key):
    """The email on a protected gallery's unlock session (client_key IS that token), if any."""
    return (
        ClientSession.objects.filter(gallery=gallery, access_token=client_key)
        .exclude(email__isnull=True).exclude(email='').values_list('email', flat=True).first()
    )


def visitor_lists(gallery, client_key):
    return FavoriteList.objects.filter(gallery=gallery, client_key=client_key)


def visitor_email(gallery, client_key):
    """The email this visitor already gave (on any of their lists or their session), if any."""
    return (
        visitor_lists(gallery, client_key).exclude(email__isnull=True).exclude(email='')
        .values_list('email', flat=True).first()
    ) or session_email(gallery, client_key)


def ensure_default_list(gallery, client_key, email=None, visitor_name=''):
    """
    The visitor's default "My Favorites" list, created on first use. A later,
    better email/name fills in a blank one (never overwrites what they gave).
    """
    favorite_list = visitor_lists(gallery, client_key).filter(is_default=True).first()
    if favorite_list is None:
        favorite_list = visitor_lists(gallery, client_key).filter(name=DEFAULT_LIST_NAME).first()
        if favorite_list is not None:
            favorite_list.is_default = True
            favorite_list.save(update_fields=['is_default', 'updated_at'])
    if favorite_list is None:
        favorite_list = FavoriteList.objects.create(
            gallery=gallery, client_key=client_key, name=DEFAULT_LIST_NAME, is_default=True,
            email=email or visitor_email(gallery, client_key), visitor_name=visitor_name,
        )
    else:
        remember_visitor(gallery, client_key, email, visitor_name)
    return favorite_list


def remember_visitor(gallery, client_key, email, visitor_name=''):
    """Fill in a missing email / name on ALL of this visitor's lists and favorites."""
    if email:
        visitor_lists(gallery, client_key).filter(email__isnull=True).update(email=email)
        visitor_lists(gallery, client_key).filter(email='').update(email=email)
        Favorite.objects.filter(gallery=gallery, client_key=client_key, email__isnull=True).update(email=email)
    if visitor_name:
        visitor_lists(gallery, client_key).filter(visitor_name='').update(visitor_name=visitor_name)


def annotated_lists(gallery, client_key, sort='newest'):
    qs = visitor_lists(gallery, client_key).annotate(
        photo_count=Count('favorites'), last_added=Max('favorites__created_at'),
    )
    if sort == 'oldest':
        return qs.order_by('created_at')
    return qs.order_by('-created_at')


def get_visitor_list(gallery, client_key, list_id):
    """One of THIS visitor's lists in THIS gallery, or None (foreign / unknown / malformed id)."""
    try:
        return visitor_lists(gallery, client_key).filter(pk=list_id).first()
    except (ValueError, ValidationError):
        return None


def list_cover_asset(favorite_list):
    """The most recently added photo of a list (its thumbnail), or None."""
    favorite = favorite_list.favorites.select_related('media_asset').order_by('-created_at').first()
    return favorite.media_asset if favorite else None


# ─── photographer side ───────────────────────────────────────────────────────

def _cover_subquery():
    """The most recently favorited photo of a list, as an annotation (no per-list query)."""
    return Subquery(
        Favorite.objects.filter(favorite_list=OuterRef('pk')).order_by('-created_at').values('media_asset_id')[:1]
    )


def thumbnail_urls(request, asset_ids):
    """{asset_id: absolute thumbnail url} for the given ids, in ONE query."""
    urls = {}
    for asset in MediaAsset.objects.filter(pk__in={i for i in asset_ids if i}):
        image = asset.thumbnail_file or asset.poster_image
        if image:
            urls[asset.pk] = request.build_absolute_uri(image.url)
    return urls


def _hmac(value):
    return hmac.new(settings.SECRET_KEY.encode('utf-8'), value.encode('utf-8'), hashlib.sha256).hexdigest()[:24]


def photographer_list_rows(gallery, email=None, sort='newest'):
    """One dict per favorite list in the gallery (annotated), for the photographer."""
    qs = FavoriteList.objects.filter(gallery=gallery).annotate(
        photo_count=Count('favorites'), last_added=Max('favorites__created_at'), first_added=Min('favorites__created_at'),
        cover_asset_id=_cover_subquery(),
    ).filter(photo_count__gt=0)
    if email:
        qs = qs.filter(email__icontains=email)
    if sort == 'oldest':
        return qs.order_by('created_at')
    if sort == 'email':
        return qs.order_by('email', '-created_at')
    return qs.order_by('-last_added')


def visitor_groups(gallery, email=None, sort='newest'):
    """
    The photographer's Favorite Activity: favorite lists grouped by VISITOR.
    A visitor is identified by their email (so the same person on two devices
    is one row); a visitor who never gave an email is a Guest, one row per
    browser. Returns a list of dicts, ordered by `sort`.
    """
    groups = {}
    for favorite_list in photographer_list_rows(gallery, email=email, sort=sort):
        key = favorite_list.email.lower() if favorite_list.email else f'guest:{_hmac(favorite_list.client_key)}'
        group = groups.setdefault(key, {
            'id': _hmac(f'visitor:{gallery.pk}:{key}'),
            'email': favorite_list.email or None,
            'name': favorite_list.visitor_name or '',
            'lists': [],
        })
        group['lists'].append(favorite_list)
        if not group['name'] and favorite_list.visitor_name:
            group['name'] = favorite_list.visitor_name
    result = list(groups.values())
    for group in result:
        stamps = [fl.last_added or fl.created_at for fl in group['lists']]
        group['total_photos'] = sum(fl.photo_count for fl in group['lists'])
        group['created_at'] = min(fl.created_at for fl in group['lists'])
        group['updated_at'] = max(stamps)
    if sort == 'email':
        result.sort(key=lambda g: ((g['email'] or '~').lower()))
    elif sort == 'oldest':
        result.sort(key=lambda g: g['created_at'])
    else:
        result.sort(key=lambda g: g['updated_at'], reverse=True)
    return result
