# backend/apps/clients/tests/test_portfolio_privacy.py
"""
Phase 4 regression tests — PUBLIC PORTFOLIO PRIVACY (F-35).

Covers:
  - a password-protected gallery's title/cover never appears in the
    public portfolio listing, even though it's published+active
  - a non-protected gallery still appears normally
  - staff/superuser accounts 404 on the public portfolio endpoint
"""
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery

User = get_user_model()


class PublicPortfolioPrivacyTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="portfolio@kyapture.com",
            password="SecurePassword123!",
            # Lowercase deliberately — the view lowercases the URL's
            # username segment before querying (username.strip().lower()),
            # so a mixed-case stored username would never match its own
            # public URL. Matches the convention every other test file
            # already uses for photographer usernames.
            username="portfoliophotog",
        )
        self.open_gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Open Wedding",
            slug="open-wedding",
            is_published=True,
            is_active=True,
        )
        self.protected_gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="Secret Elopement",
            slug="secret-elopement",
            is_published=True,
            is_active=True,
            is_password_protected=True,
        )
        self.url = f"/api/v1/public/{self.photographer.username}/"

    def test_open_gallery_appears_in_portfolio(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        titles = [g["title"] for g in response.data["galleries"]]
        self.assertIn("Open Wedding", titles)

    def test_protected_gallery_title_never_appears_in_portfolio(self):
        response = self.client.get(self.url)
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)
        titles = [g["title"] for g in response.data["galleries"]]
        self.assertNotIn("Secret Elopement", titles)
        # Belt and suspenders: the raw payload must not leak the title
        # anywhere (e.g. via a slug or cover URL containing it).
        self.assertNotIn("Secret Elopement", str(response.data))

    def test_staff_account_is_not_a_public_portfolio(self):
        staff_user = User.objects.create_user(
            email="staffmember@kyapture.com",
            password="SecurePassword123!",
            username="staffmember",
            is_staff=True,
        )
        response = self.client.get(f"/api/v1/public/{staff_user.username}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)

    def test_superuser_account_is_not_a_public_portfolio(self):
        admin_user = User.objects.create_superuser(
            email="admin@kyapture.com",
            password="SecurePassword123!",
            username="siteadmin",
        )
        response = self.client.get(f"/api/v1/public/{admin_user.username}/")
        self.assertEqual(response.status_code, status.HTTP_404_NOT_FOUND)
