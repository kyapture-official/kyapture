# C:/Users/LENOVO/Desktop/kyapture/backend/apps/core/share.py
"""
The ONE canonical, shareable URL of a gallery.

It is the plain path-based client URL (docs/KYAPTURE_PRODUCT_DECISIONS.md #3):
    {FRONTEND_URL}/g/{username}/{slug}

Deliberately carries NO credential of any kind — no unlock/session token, no
download token or PIN, no signed or storage URL. Whoever opens it meets the
gallery's normal gates (published, not expired, password) exactly like anyone
else; sharing the link can never grant access. Built from settings.FRONTEND_URL
(the public app origin in production), so it never depends on whatever host the
photographer happens to be browsing from.
"""
from django.conf import settings


def build_gallery_share_url(gallery):
    return f"{settings.FRONTEND_URL}/g/{gallery.photographer.username}/{gallery.slug}"
