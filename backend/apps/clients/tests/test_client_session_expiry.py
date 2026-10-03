# backend/apps/clients/tests/test_client_session_expiry.py
"""
Phase 4 regression tests — CLIENT SESSION LIFECYCLE.

Covers:
  - a ClientSession past CLIENT_SESSION_TTL_DAYS is treated as invalid at
    every validation call site (not just one)
  - a fresh session still works (the TTL doesn't break normal unlocked
    gallery browsing)
  - the scheduled purge task removes expired sessions without touching
    live ones
"""
import bcrypt
from datetime import timedelta

from django.test import override_settings
from django.utils import timezone
from django.contrib.auth import get_user_model
from rest_framework.test import APITestCase
from rest_framework import status

from apps.galleries.models import Gallery
from apps.clients.models import ClientSession
from apps.clients.tasks import purge_expired_client_sessions

User = get_user_model()


class ClientSessionExpiryTestCase(APITestCase):
    def setUp(self):
        self.photographer = User.objects.create_user(
            email="sessionttl@kyapture.com",
            password="SecurePassword123!",
            username="sessionttlphotog",
        )
        self.gallery = Gallery.objects.create(
            photographer=self.photographer,
            title="TTL Gallery",
            slug="ttl-gallery",
            is_published=True,
            is_active=True,
            is_password_protected=True,
        )
        self.gallery.password_hash = bcrypt.hashpw(b"secret123", bcrypt.gensalt()).decode()
        self.gallery.save(update_fields=["password_hash"])

        self.fresh_session = ClientSession.objects.create(gallery=self.gallery)
        self.expired_session = ClientSession.objects.create(gallery=self.gallery)
        # created_at is auto_now_add — backdate it directly at the DB level.
        ClientSession.objects.filter(id=self.expired_session.id).update(
            created_at=timezone.now() - timedelta(days=31)
        )
        self.expired_session.refresh_from_db()

        self.gallery_url = f"/api/v1/public/{self.photographer.username}/{self.gallery.slug}/"

    @override_settings(CLIENT_SESSION_TTL_DAYS=30)
    def test_fresh_session_still_grants_access(self):
        response = self.client.get(
            self.gallery_url, HTTP_AUTHORIZATION=f"Bearer {self.fresh_session.access_token}"
        )
        self.assertEqual(response.status_code, status.HTTP_200_OK, response.data)

    @override_settings(CLIENT_SESSION_TTL_DAYS=30)
    def test_expired_session_is_rejected(self):
        response = self.client.get(
            self.gallery_url, HTTP_AUTHORIZATION=f"Bearer {self.expired_session.access_token}"
        )
        self.assertEqual(response.status_code, status.HTTP_401_UNAUTHORIZED)

    @override_settings(CLIENT_SESSION_TTL_DAYS=30)
    def test_purge_task_removes_only_expired_sessions(self):
        purge_expired_client_sessions()
        self.assertFalse(ClientSession.objects.filter(id=self.expired_session.id).exists())
        self.assertTrue(ClientSession.objects.filter(id=self.fresh_session.id).exists())

    @override_settings(CLIENT_SESSION_TTL_DAYS=30)
    def test_purge_task_is_idempotent(self):
        first_run_count = purge_expired_client_sessions()
        second_run_count = purge_expired_client_sessions()
        self.assertEqual(first_run_count, 1)
        self.assertEqual(second_run_count, 0)
