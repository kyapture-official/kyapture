# backend/apps/clients/tests/test_deleting_owner_7_5e.py
"""
CHUNK 7.5-E - while an account deletion is WAITING, the owner's galleries close exactly like a 7.5-A suspension.

The 19 per-path tests of test_suspended_owner_7_5a.py are re-run here with ONE difference: the owner is closed by
REQUESTING the account deletion through the real endpoint (password + email) and opened again by CANCELLING it.
Each proves 200 -> 404 -> 200 on one public path (gallery payload, photo pages, unlock, favorites, lists, video
playback, single download, download access, ZIP prepare, job poll by token and by key, ZIP file link, portfolio,
a job the visitor asked for before the request, the ready email), and that nothing is deleted by a request.
"""
import inspect

from rest_framework.test import APIClient

from apps.clients.tests import test_suspended_owner_7_5a as suspended

PASSWORD = 'SecurePassword123!'


class DeletionClosesOwnerMixin:
    """Replaces the staff suspend / reactivate calls of the 7.5-A harness."""

    def set_owner(self, active):
        owner = APIClient()
        owner.force_authenticate(user=self.photographer)
        if active:
            response = owner.post('/api/v1/auth/account/deletion/cancel/', {}, format='json')
        else:
            response = owner.post(
                '/api/v1/auth/account/deletion/request/',
                {'password': PASSWORD, 'email': self.photographer.email}, format='json')
        self.assertEqual(response.status_code, 200, getattr(response, 'data', None))
        self.photographer.refresh_from_db()


def _closing_variant(cls):
    return type(cls.__name__.replace('Suspended', 'Deleting'), (DeletionClosesOwnerMixin, cls), {'__module__': __name__})


for _name, _cls in inspect.getmembers(suspended, inspect.isclass):
    if _cls.__module__ == suspended.__name__ and issubclass(_cls, suspended.SuspendedOwnerBase) \
            and _cls is not suspended.SuspendedOwnerBase:
        _variant = _closing_variant(_cls)
        globals()[f'Closing{_variant.__name__}'] = _variant
del _name, _cls, _variant
