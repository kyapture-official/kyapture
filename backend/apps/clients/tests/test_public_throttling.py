# backend/apps/clients/tests/test_public_throttling.py
"""
Phase 4 regression tests — PUBLIC ENDPOINT THROTTLING (F-41).

Covers:
  - ordinary public gallery browsing uses the dedicated
    'public_gallery_browse' scope, not the blanket 100/day 'anon' scope
    (which would make normal browsing/pagination trip on a real visit)
  - the scope actually throttles once its own (much higher) limit is hit
"""
from unittest.mock import patch

from django.core.cache import cache
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.clients.views import PublicGalleryBrowseThrottle

User = get_user_model()


class PublicGalleryBrowseThrottleScopeTestCase(APITestCase):
    """Confirms the dedicated scope is actually wired to the endpoint,
    without needing to fire 100+ requests to prove the OLD blanket
    scope was too tight (that's just reading settings)."""

    def test_scope_is_public_gallery_browse_not_blanket_anon(self):
        self.assertEqual(PublicGalleryBrowseThrottle.scope, 'public_gallery_browse')


class PublicGalleryBrowseThrottleBehaviorTestCase(APITestCase):
    def setUp(self):
        cache.clear()
        self.photographer = User.objects.create_user(
            email="throttletest@kyapture.com", password="SecurePassword123!", username="throttletestphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Throttle Test",
            slug="throttle-test",
            is_published=True,
            is_active=True,
        )
        self.url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    def test_exceeding_the_dedicated_scope_throttles(self):
        # DRF's SimpleRateThrottle.THROTTLE_RATES is bound from
        # api_settings.DEFAULT_THROTTLE_RATES as a plain class attribute
        # AT MODULE IMPORT TIME (rest_framework/throttling.py) — it is
        # NOT re-read from Django settings afterward, so
        # `override_settings(REST_FRAMEWORK=...)` has no effect on an
        # already-imported throttle class. Patching the dict this
        # specific throttle class actually consults is the only way to
        # exercise its real throttling behavior in a test.
        cache.clear()
        with patch.dict(PublicGalleryBrowseThrottle.THROTTLE_RATES, {'public_gallery_browse': '2/minute'}):
            first = self.client.get(self.url)
            second = self.client.get(self.url)
            third = self.client.get(self.url)

        self.assertEqual(first.status_code, status.HTTP_200_OK)
        self.assertEqual(second.status_code, status.HTTP_200_OK)
        self.assertEqual(third.status_code, status.HTTP_429_TOO_MANY_REQUESTS)

    def test_ordinary_browsing_is_not_throttled_at_default_rate(self):
        # A handful of ordinary requests (well under 120/minute) must
        # never be throttled — this is the actual bug being fixed
        # (normal visitors previously shared a 100/DAY bucket).
        for _ in range(10):
            response = self.client.get(self.url)
            self.assertEqual(response.status_code, status.HTTP_200_OK)
