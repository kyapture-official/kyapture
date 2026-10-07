# backend/apps/photos/public_media.py
"""
Public derivative URLs that end when a gallery is closed (7-B, SEC-09 / debt row 85).

Display/medium/thumbnail WebPs, video posters and playback MP4s are public-read
objects with permanent URLs and a one-year immutable cache header (that is what
lets a CDN serve them cheaply; apps/core/storage.py). The catch: a URL a visitor
once saw kept working after the photographer added a password, changed it, or
unpublished the gallery.

Every public key of a gallery carries the gallery's `media_token`
(apps/photos/models.py::_public_dir). Closing the gallery calls
`rotate_gallery_public_media`, which picks a new random token, copies every
public file to its new key, points the rows at the new keys and deletes the old
objects, so the old URLs stop resolving at the storage. Only an unlocked visitor
receives the new URLs (in the gallery payload).

What this cannot reach: a copy already held by a browser cache or by a CDN edge
(the objects are `immutable` for a year). A CDN in front of the bucket needs an
invalidation of the gallery's old prefix when this runs (docs/security, 15-A).
"""
import logging
import os
import secrets

from django.db import transaction

logger = logging.getLogger(__name__)

PUBLIC_FIELDS = ('display_file', 'medium_file', 'thumbnail_file', 'poster_image', 'preview_file', 'playback_file')


def queue_rotation(gallery):
    """Rotate `gallery`'s public keys in the background once the current transaction commits."""
    from .tasks import rotate_public_media

    gallery_id = str(gallery.pk)

    def enqueue():
        try:
            rotate_public_media.delay(gallery_id)
        except Exception:
            logger.exception('Could not queue the public-media rotation of gallery %s', gallery_id)

    transaction.on_commit(enqueue)


def rotate_gallery_public_media(gallery_id):
    """
    Give gallery `gallery_id` a new media token and move every public derivative
    under it. Returns the number of files moved. Safe to run twice: a file that
    already sits under the current token is left alone.
    """
    from apps.galleries.models import Gallery
    from .models import MediaAsset

    try:
        gallery = Gallery.objects.select_related('photographer').get(pk=gallery_id)
    except Gallery.DoesNotExist:
        return 0
    gallery.media_token = secrets.token_hex(16)
    gallery.save(update_fields=['media_token'])

    moved = 0
    for asset in MediaAsset.objects.filter(gallery=gallery).iterator():
        asset.gallery = gallery                 # the path functions read the NEW token
        old_names, updated = [], []
        for field_name in PUBLIC_FIELDS:
            field = getattr(asset, field_name)
            if not field or not field.name or f'/{gallery.media_token}/' in field.name:
                continue
            storage = field.storage
            new_name = asset._meta.get_field(field_name).generate_filename(asset, os.path.basename(field.name))
            try:
                with storage.open(field.name, 'rb') as source:
                    saved = storage.save(new_name, source)
            except Exception:
                logger.warning('Public file %s of asset %s could not be moved', field.name, asset.pk)
                continue
            old_names.append((storage, field.name))
            field.name = saved
            updated.append(field_name)
        if updated:
            asset.save(update_fields=updated)
            for storage, name in old_names:
                try:
                    storage.delete(name)
                except Exception:
                    logger.warning('Old public file %s could not be deleted', name)
            moved += len(updated)
    return moved
