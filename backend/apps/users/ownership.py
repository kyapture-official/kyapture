# backend/apps/users/ownership.py
"""
Whether a photographer's galleries may be seen by visitors (7.5-A suspension, 7.5-E account deletion).

An owner is "public" while the account is active AND no deletion is waiting or running. Every public
lookup (apps/clients/views.py), the ZIP job (download_jobs.py) and the ready email read it from here, so
suspending an owner and deleting an owner close exactly the same doors: the gallery answers 404, downloads
stop, a PREPARING ZIP ends. Cancelling a deletion (or reactivating) opens them again with the same links.
"""

# Keyword filter for a query that starts at a Gallery: `Gallery.objects.filter(..., **PUBLIC_OWNER)`.
PUBLIC_OWNER = {
    'photographer__is_active': True,
    'photographer__deletion_requested_at__isnull': True,
}

# The same rule for a query that starts at a User (the portfolio listing).
PUBLIC_USER = {
    'is_active': True,
    'deletion_requested_at__isnull': True,
}


def owner_is_public(user):
    return bool(user.is_active and user.deletion_requested_at is None)
