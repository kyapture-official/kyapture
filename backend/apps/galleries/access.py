# backend/apps/galleries/access.py
"""
What has to happen when a gallery's visitor access changes, whichever endpoint
changed it (set-password, publish, or the gallery PATCH). 7-B found the PATCH
path set a new password without ending the unlock sessions issued under the old
one, so the rules live here once:

  - the password changed, was added or was removed -> every unlock session of
    the gallery ends (a token never outlives the password it was issued under);
  - the gallery was closed to existing visitors (password added or changed, or
    unpublished) -> its public derivatives move to new random keys, so the URLs
    visitors already saw stop working (apps/photos/public_media.py, row 85).
"""
from apps.photos.public_media import queue_rotation


def access_snapshot(gallery):
    """Call BEFORE changing the gallery; pass the result to after_access_change()."""
    return (gallery.is_published, gallery.is_password_protected, gallery.password_hash or '')


def after_access_change(gallery, before):
    """Apply the rules above (call AFTER saving). Returns how many unlock sessions were ended."""
    from apps.clients.models import ClientSession

    was_published, was_protected, old_hash = before
    password_changed = (bool(gallery.is_password_protected), gallery.password_hash or '') != (
        bool(was_protected), old_hash)
    revoked = 0
    if password_changed:
        revoked, _ = ClientSession.objects.filter(gallery=gallery).delete()
    closed = (was_published and not gallery.is_published) or (gallery.is_password_protected and password_changed)
    if closed:
        queue_rotation(gallery)
    return revoked
