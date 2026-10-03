# C:/Users/LENOVO/Desktop/kyapture/backend/apps/clients/favorite_lists.py
"""
Favorite LISTS for the photographer's Favorite Activity view.

There is no separate "list" table. A favorite list is simply one client's set of
favorites within one gallery — i.e. the existing Favorite rows grouped by
(gallery, client_key). That is already the identity model the client side uses
(see Favorite's docstring), so a list exists exactly when a client has favorited
something, and it is edited by that client favoriting / unfavoriting.

`client_key` is NEVER exposed: for a password-protected gallery it is the
client's session access token (a credential). A list is addressed by an opaque
HMAC of (gallery, client_key) instead, which can't be reversed into the key.
"""
import hashlib
import hmac

from django.conf import settings
from django.db.models import Count, Max, Min

from .models import ClientSession, Favorite


def favorite_list_id(gallery_id, client_key):
    digest = hmac.new(
        settings.SECRET_KEY.encode('utf-8'), f'favorite-list:{gallery_id}:{client_key}'.encode('utf-8'), hashlib.sha256
    ).hexdigest()
    return digest[:24]


def resolve_favorite_list(gallery, list_id):
    """The client_key behind `list_id` within THIS gallery, or None (unknown/foreign/malformed id)."""
    if not isinstance(list_id, str) or not list_id:
        return None
    keys = Favorite.objects.filter(gallery=gallery).values_list('client_key', flat=True).distinct()
    for key in keys:
        if hmac.compare_digest(favorite_list_id(gallery.pk, key), list_id):
            return key
    return None


def grouped_lists(gallery):
    """Queryset of one dict per list, most recently updated first."""
    return (
        Favorite.objects.filter(gallery=gallery)
        .values('client_key')
        .annotate(
            photo_count=Count('id'),
            list_email=Max('email'),
            first_added=Min('created_at'),
            last_added=Max('created_at'),
        )
        .order_by('-last_added')
    )


def serialize_lists(gallery, rows):
    """
    Public-safe rows for one page of grouped_lists(). One extra query resolves
    emails a client gave AFTER favoriting (e.g. at download time, stored on their
    unlock session) so the list shows who it belongs to.
    """
    rows = list(rows)
    keys = [row['client_key'] for row in rows]
    session_emails = dict(
        ClientSession.objects.filter(gallery=gallery, access_token__in=keys, email__isnull=False)
        .exclude(email='')
        .values_list('access_token', 'email')
    )
    return [
        {
            'id': favorite_list_id(gallery.pk, row['client_key']),
            'email': row['list_email'] or session_emails.get(row['client_key']),
            'photo_count': row['photo_count'],
            'created_at': row['first_added'],
            'updated_at': row['last_added'],
        }
        for row in rows
    ]
