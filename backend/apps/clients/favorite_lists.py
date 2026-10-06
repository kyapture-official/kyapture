# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/favorite_lists.py
"""
Favorite LISTS (Pixieset-style "My Favorites").

A visitor (no account) owns lists inside one gallery. Ownership is the same
identity a Favorite always used - `client_key`: the browser's anonymous
`client_uid` (kept in localStorage, so it survives closing the tab), or, on a
protected gallery whose client sends no client_uid, the unlock token. On a
protected gallery the unlock token is still required on every call; it gates
the gallery, the client_uid names the visitor. The key is a credential and is
never returned to anyone: the visitor proves ownership by presenting it, the
photographer sees the visitor's EMAIL instead. The email is typed and never
verified, so it only labels lists; it never grants access to one (7-A, SEC-02).

Visitor side:  ensure_default_list / create_list / rename / delete / add / remove
Photographer:  visitor_groups (lists grouped by visitor) and list_rows
"""
import hashlib
import hmac
import re

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import IntegrityError, transaction
from django.db.models import Count, Max, Min, OuterRef, Q, Subquery
from django.utils import timezone

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
#
# 7-A (SEC-02): a visitor reaches ONLY the lists their own key made. An email is
# typed and never verified, so it is a label for the photographer and nothing
# more: it never finds, merges into or edits a list another key made.

MAX_CLIENT_KEY_LENGTH = 128     # FavoriteList.client_key / Favorite.client_key


def _own_lists(gallery, client_key):
    return FavoriteList.objects.filter(gallery=gallery, client_key=client_key)


def _blank_email():
    return Q(email__isnull=True) | Q(email='')


def visitor_lists(gallery, client_key):
    """The visitor's lists: exactly the ones their client key owns."""
    return _own_lists(gallery, client_key)


def visitor_favorites(gallery, client_key):
    """Every Favorite of this visitor in the gallery (their lists' photos + legacy list-less rows)."""
    return Favorite.objects.filter(gallery=gallery).filter(
        Q(client_key=client_key) | Q(favorite_list__in=visitor_lists(gallery, client_key))
    )


def visitor_email(gallery, client_key, fallback=None):
    """The email this visitor already gave (on one of their own lists), else `fallback` (what they sent / their unlock session)."""
    return (
        _own_lists(gallery, client_key).exclude(_blank_email())
        .order_by('created_at').values_list('email', flat=True).first()
    ) or fallback or None


def email_default_list(gallery, email):
    """The ONE default list of an email in a gallery (case-insensitive), if there is one."""
    return (
        FavoriteList.objects.filter(gallery=gallery, is_default=True, email__iexact=email)
        .order_by('created_at', 'id').first()
    )


def default_list_email(gallery, email, exclude_pk=None):
    """
    `email` when a default list may carry it, else None. One email = ONE default
    list per gallery (DB constraint): when another key's default list already
    has it, a second default list stays unlabelled instead of joining that list.
    """
    if not email:
        return None
    taken = email_default_list(gallery, email)
    return email if taken is None or taken.pk == exclude_pk else None


def merge_lists(source, target):
    """
    Moves every favorite of `source` into `target` (a photo `target` already has
    is dropped, not duplicated) and deletes the emptied `source`. Only ever
    called for two lists the SAME visitor proved they hold.
    """
    with transaction.atomic():
        have = list(target.favorites.values_list('media_asset_id', flat=True))
        source.favorites.filter(media_asset_id__in=have).delete()
        source.favorites.update(favorite_list=target, **({'email': target.email} if target.email else {}))
        fields = {'updated_at': timezone.now()}
        if not target.visitor_name and source.visitor_name:
            fields['visitor_name'] = source.visitor_name
        FavoriteList.objects.filter(pk=target.pk).update(**fields)
        source.delete()


def adopt_lists(gallery, from_key, to_key):
    """
    Moves the lists and favorites made under `from_key` to `to_key`. Called only
    when ONE request proved it holds both (a protected gallery's unlock token
    plus this browser's client_uid), so the hearts a visitor made with an
    unlock token follow their browser to the next visit's new token.
    """
    if not from_key or from_key == to_key:
        return
    if not (_own_lists(gallery, from_key).exists() or Favorite.objects.filter(gallery=gallery, client_key=from_key).exists()):
        return
    with transaction.atomic():
        for source in list(_own_lists(gallery, from_key).order_by('created_at', 'id')):
            target = _own_lists(gallery, to_key).filter(name__iexact=source.name).first()
            if target is not None:
                merge_lists(source, target)
                continue
            if source.is_default and _own_lists(gallery, to_key).filter(is_default=True).exists():
                source.is_default = False
            source.client_key = to_key
            source.save(update_fields=['client_key', 'is_default', 'updated_at'])
        Favorite.objects.filter(gallery=gallery, client_key=from_key).update(client_key=to_key)


def ensure_default_list(gallery, client_key, email=None, visitor_name=''):
    """
    The visitor's default "My Favorites" list, get-or-create, among THEIR OWN
    lists only. A given email labels it when no other default list of the
    gallery already carries that email (one email = one default list); it never
    selects another key's list.
    """
    with transaction.atomic():
        remember_visitor(gallery, client_key, email, visitor_name)
        own = _own_lists(gallery, client_key)
        favorite_list = (
            own.filter(is_default=True).order_by('created_at', 'id').first()
            or own.filter(name=DEFAULT_LIST_NAME).first()
        )
        if favorite_list is not None:
            if not favorite_list.is_default and (
                not favorite_list.email or default_list_email(gallery, favorite_list.email)
            ):
                favorite_list.is_default = True
                favorite_list.save(update_fields=['is_default', 'updated_at'])
            return favorite_list
        try:
            with transaction.atomic():
                return FavoriteList.objects.create(
                    gallery=gallery, client_key=client_key, name=DEFAULT_LIST_NAME, is_default=True,
                    email=default_list_email(gallery, email or visitor_email(gallery, client_key)),
                    visitor_name=visitor_name,
                )
        except IntegrityError:
            # Lost a race with the same visitor's other request (or the email
            # was labelled meanwhile): this key's list is the one to use.
            return own.filter(name=DEFAULT_LIST_NAME).first() or FavoriteList.objects.create(
                gallery=gallery, client_key=client_key, name=DEFAULT_LIST_NAME, is_default=True,
                visitor_name=visitor_name,
            )


def remember_visitor(gallery, client_key, email, visitor_name=''):
    """
    Label THIS key's lists and favorites with a given email / name. Their guest
    default list takes the email only while no other default list has it; it is
    never merged into another key's list.
    """
    own = _own_lists(gallery, client_key)
    if email:
        for guest_default in list(own.filter(_blank_email(), is_default=True)):
            if default_list_email(gallery, email, exclude_pk=guest_default.pk):
                try:
                    with transaction.atomic():
                        guest_default.email = email
                        guest_default.save(update_fields=['email', 'updated_at'])
                except IntegrityError:
                    pass        # labelled by another key in the meantime: stays a guest list
        own.filter(_blank_email(), is_default=False).update(email=email)
        Favorite.objects.filter(gallery=gallery, client_key=client_key).filter(_blank_email()).update(email=email)
    if visitor_name:
        own.filter(visitor_name='').update(visitor_name=visitor_name)


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
