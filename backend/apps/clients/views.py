#C:\Users\LENOVO\Desktop\kyapture\backend\apps\clients\views.py :
import os
import time
import tempfile
import zipfile
import bcrypt
from django.conf import settings
from django.http import StreamingHttpResponse, HttpResponse, FileResponse, HttpResponseRedirect
from django.shortcuts import get_object_or_404
from django.core.exceptions import ValidationError
from django.db.models import Count, Q
from django.utils import timezone
from django.core.files.storage import default_storage
from rest_framework import status, serializers
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle

from apps.galleries.models import Gallery
from .models import ClientSession, DownloadLog, Favorite
from apps.photos.models import MediaAsset, PhotoSet
from .serializers import (
    PublicGallerySerializer,
    GalleryUnlockSerializer,
    PublicMediaAssetSerializer,
    FavoriteToggleSerializer,
)
from apps.core.pagination import GalleryMediaPagination
from apps.core.utils import (
    sanitize_download_filename,
    ALREADY_COMPRESSED_EXTS,
    process_download_master,
)

import logging
import zipfile


logger = logging.getLogger(__name__)


def _get_client_download_source(asset):
    """Return the private Download Master, backfilling it lazily if needed."""
    if asset.media_type != MediaAsset.MediaType.IMAGE:
        return asset.original_file, DownloadLog.Resolution.ORIGINAL
    if asset.download_file:
        return asset.download_file, DownloadLog.Resolution.DOWNLOAD

    # Existing READY assets predate download_file. Generate only the missing
    # master through the same storage abstraction, never replacing their
    # original or regenerating display/medium/thumbnail tiers.
    try:
        download_file = process_download_master(asset.original_file)
        if download_file:
            asset.download_file = download_file
            asset.save(update_fields=['download_file'])
            return asset.download_file, DownloadLog.Resolution.DOWNLOAD
    except Exception:
        # A download must remain available even if a legacy/corrupt image
        # cannot be re-encoded. Keep this quiet at warning level: normal
        # upload validation prevents it for new assets, and the fallback is
        # intentional for unsupported historic media.
        logger.warning('Download-master backfill skipped for asset %s', asset.id)

    # Formats intentionally left un-reencoded (or a transient storage/Pillow
    # failure) retain the authorized original rather than returning corrupt
    # bytes or making the file unavailable.
    return asset.original_file, DownloadLog.Resolution.ORIGINAL
# ─────────────────────────────────────────────────────────────
# CUSTOM SECURITY THROTTLE (Password brute-force protection)
# ─────────────────────────────────────────────────────────────
class PasswordUnlockRateThrottle(AnonRateThrottle):
    """
    Limits anonymous password-unlock attempts to the custom
    'password_unlock' rate (5 attempts/minute) configured in settings.
    """
    scope = 'password_unlock'


class PublicGalleryBrowseThrottle(AnonRateThrottle):
    """
    Phase 4 (F-41 fix) — the generous, burst-friendly scope for ordinary
    public gallery viewing (metadata, pagination, video streaming,
    single-file download, portfolio listing). See its own rate comment
    in settings/base.py's DEFAULT_THROTTLE_RATES for why this exists
    separately from both the blanket 'anon' scope (too tight for normal
    browsing) and 'password_unlock' (deliberately tight — a genuine
    brute-force target this traffic is not).
    """
    scope = 'public_gallery_browse'


class PublicGalleryView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/
    GET /api/v1/public/{username}/{slug}/?token=abc123

    Public gateway. Enforces multi-tenant routing, soft-delete safety,
    and password session auditing [1.1.2].
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]
    
    def get_gallery(self, username, slug):
        """
        Retrieves a published, active gallery mapped to a specific photographer.
        This prevents MultipleObjectsReturned crashes on shared slug namespaces [1.1.2].

        Phase 2: deliberately does NOT prefetch the gallery's assets
        anymore — a gallery with hundreds/thousands of photos would mean
        prefetching (and serializing) every one of them on every single
        gallery-page load. get() below fetches only the first PAGE of
        READY assets explicitly instead (see GalleryMediaPagination); a
        guest never sees a broken thumbnail for a photo that's still
        processing or failed, exactly as before — just paginated now.
        """
        try:
            now = timezone.now()
            return (
                Gallery.objects
                .select_related('photographer')
                .get(
                    Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                    slug=slug,
                    photographer__username=username,  # Multi-tenant scoping [1.1.2]
                    is_published=True,                # Block draft galleries
                    is_active=True                    # Block soft-deleted galleries [1.1.2]
                )
            )
        except Gallery.DoesNotExist:
            return None

    def get_ready_assets_page(self, gallery, page_size, photo_set_id=None):
        """
        Fetches exactly ONE bounded page of this gallery's READY assets,
        ordered the same way the dashboard grid orders them (MediaAsset's
        own Meta.ordering = ['order', 'created_at']), plus the total READY
        count. Two small, indexed queries (idx_gallery_assets_order /
        idx_set_assets_order covers both), regardless of how many
        thousands of assets the gallery has — never an unbounded SELECT
        of every asset.

        photo_set_id (Phase 3): when a client is viewing a specific
        PhotoSet tab rather than "All", scopes both queries to that set
        only — same shape, same guarantees, just an extra filter.
        """
        ready_qs = MediaAsset.objects.filter(
            gallery=gallery,
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        if photo_set_id:
            ready_qs = ready_qs.filter(photo_set_id=photo_set_id)
        ready_qs = ready_qs.order_by('order', 'created_at')
        total_count = ready_qs.count()
        first_page = list(ready_qs[:page_size])
        return first_page, total_count

    def get_photo_sets(self, gallery):
        """
        This gallery's sets, each annotated with its READY-asset count in
        one query — used to render the client-facing set tabs. A set with
        zero READY photos still shows up (e.g. all its photos are still
        processing) rather than flickering in and out of the tab bar.
        """
        return list(
            PhotoSet.objects
            .filter(gallery=gallery)
            .annotate(photo_count=Count(
                'assets', filter=Q(assets__processing_status=MediaAsset.ProcessingStatus.READY)
            ))
            .order_by('order', 'created_at')
        )

    def get_session_token(self, request):
        """
        WHAT: Extracts the client's unlock token from either the Authorization
        header or the legacy ?token= query param.
        WHY:  Tokens shouldn't sit in a URL — server access logs and browser
        history both capture query strings. The frontend already sends
        it correctly as `Authorization: Bearer <token>`; this just makes
        the backend actually check there. Query param kept as a fallback
        only for compatibility with the older documented contract.
    """
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[len('Bearer '):].strip()
        return request.query_params.get('token', '').strip()
    
    def validate_session_token(self, token, gallery):
        """Verifies if the client's local session token is active for this gallery [1.1.2]."""
        if not token:
            return False
        return ClientSession.objects.not_expired().filter(
            access_token=token,
            gallery=gallery
        ).exists()

    def get(self, request, username, slug):
        # 1. Fetch gallery with strict multi-tenant constraints [1.1.2]
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        # 2. Process password protection gateways [1.1.2]
        if gallery.is_password_protected:
            token = self.get_session_token(request) 

            # No token provided: Instruct frontend to render password form (Status 200) [1.1.2]
            if not token:
                return Response({
                    'requires_password': True,
                    'title': gallery.title,
                    'branding_color': gallery.branding_color,
                }, status=status.HTTP_200_OK)

            # Token provided: Validate against PostgreSQL sessions
            if not self.validate_session_token(token, gallery):
                return Response(
                    {'error': 'Invalid or expired access token.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

                # 3. Access granted: fetch the first page of READY assets and
        # return fully serialized public metadata. username/slug passed
        # through context so PublicMediaAssetSerializer can build each
        # video's playback_url. gallery.photographer is already
        # select_related here, so reading it once is free — reading
        # obj.gallery.photographer per-video inside the child serializer
        # would NOT be cached and would re-query once per video (N+1).
        page_size = GalleryMediaPagination.page_size
        photo_set_id = request.query_params.get('set', '').strip() or None
        photos_page, total_count = self.get_ready_assets_page(gallery, page_size, photo_set_id)

        serializer = PublicGallerySerializer(
            gallery,
            context={
                'request': request,
                'gallery': gallery,
                'username': gallery.photographer.username,
                'slug': gallery.slug,
                'photos_page': photos_page,
                'photos_total_count': total_count,
                'photos_has_more': total_count > len(photos_page),
                'photos_page_size': page_size,
                'photo_sets': self.get_photo_sets(gallery),
            }
        )
        return Response(serializer.data, status=status.HTTP_200_OK)


class PublicGalleryPhotosView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/photos/
    GET .../photos/?page=2&token=<access_token>

    Phase 2 (large-gallery performance) continuation endpoint: serves
    subsequent pages of a gallery's READY media assets, picking up after
    the first page PublicGalleryView already embeds inline (see its
    'photos'/'photos_has_more'/'photos_page_size' fields). Standard DRF
    {count, next, previous, results} pagination envelope.

    Duplicates PublicGalleryView's gallery lookup + password/session-token
    gate rather than sharing it — matching this app's existing convention
    of small per-view copies of that same gate (GalleryUnlockView,
    PublicVideoStreamView, PublicGalleryDownloadView all do this too).
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]
    pagination_class = GalleryMediaPagination

    def get_gallery(self, username, slug):
        try:
            now = timezone.now()
            return Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None

    def get_session_token(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[len('Bearer '):].strip()
        return request.query_params.get('token', '').strip()

    def validate_session_token(self, token, gallery):
        if not token:
            return False
        return ClientSession.objects.not_expired().filter(access_token=token, gallery=gallery).exists()

    def get(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if gallery.is_password_protected:
            token = self.get_session_token(request)
            if not self.validate_session_token(token, gallery):
                return Response(
                    {'error': 'Invalid or expired access token.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        ready_qs = MediaAsset.objects.filter(
            gallery=gallery,
            processing_status=MediaAsset.ProcessingStatus.READY,
        )
        photo_set_id = request.query_params.get('set', '').strip()
        if photo_set_id:
            ready_qs = ready_qs.filter(photo_set_id=photo_set_id)
        ready_qs = ready_qs.order_by('order', 'created_at')

        paginator = self.pagination_class()
        page = paginator.paginate_queryset(ready_qs, request, view=self)
        serializer = PublicMediaAssetSerializer(
            page,
            many=True,
            context={
                'request': request,
                'gallery': gallery,
                'username': gallery.photographer.username,
                'slug': gallery.slug,
            }
        )
        return paginator.get_paginated_response(serializer.data)


class GalleryUnlockView(APIView):
    """
    POST /api/v1/public/{username}/{slug}/unlock/
    Authenticates gallery password credentials.
    On success, writes a ClientSession and returns a secure token [1.1.2].
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordUnlockRateThrottle]
    
    def get_gallery(self, username, slug):
        """Retrieves targeted active gallery for validation."""
        try:
            now = timezone.now()
            return Gallery.objects.get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None

    def post(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )

        if not gallery.is_password_protected:
            return Response(
                {'error': 'This gallery does not require a password.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Pass context into the serializer to support transactional creation [1.1.2]
        serializer = GalleryUnlockSerializer(
            data=request.data,
            context={
                'gallery': gallery,
                'request': request,
            }
        )

        if serializer.is_valid():
            # Triggers create() and returns the session instance [1.1.2]
            session = serializer.save()
            # Returns the formatted token payload from to_representation() [1.1.2]
            return Response(serializer.data, status=status.HTTP_200_OK)

        return Response(serializer.errors, status=status.HTTP_401_UNAUTHORIZED)


def _resolve_client_identity(gallery, request):
    """
    Resolves "who is making this favorite request" per Favorite's identity
    model (see apps/clients/models.py's Favorite docstring):

    - Password-protected gallery: the client MUST already hold a valid
      unlock token (same gate every other protected-gallery view uses).
      That token becomes the client_key, and its ClientSession is linked
      so the photographer can see the associated email if one was given.
      A client cannot invent an arbitrary identity for a gallery it
      hasn't actually unlocked.
    - Open gallery: no password gate exists to piggyback on, so the
      frontend-generated `client_uid` (sent in the body for POST/DELETE,
      as a query param for GET) is the identity. Required — an empty/
      missing uid is rejected rather than silently bucketing every
      anonymous visitor into one shared "favorites" pile.

    Returns (client_key, client_session, email, error_response). Exactly
    one of (client_key, error_response) is non-None.
    """
    if gallery.is_password_protected:
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        token = (
            auth_header[len('Bearer '):].strip()
            if auth_header.startswith('Bearer ')
            else request.query_params.get('token', '').strip()
        )
        if not token:
            return None, None, None, Response(
                {'error': 'An active unlocked session is required.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            session = ClientSession.objects.not_expired().get(access_token=token, gallery=gallery)
        except ClientSession.DoesNotExist:
            return None, None, None, Response(
                {'error': 'Invalid or expired access token.'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return token, session, session.email, None

    client_uid = (
        (request.data.get('client_uid') if hasattr(request.data, 'get') else None)
        or request.query_params.get('client_uid', '')
    ).strip()
    if not client_uid:
        return None, None, None, Response(
            {'error': 'client_uid is required for this gallery.', 'code': 'client_uid_required'},
            status=status.HTTP_400_BAD_REQUEST
        )
    return client_uid, None, None, None


class GalleryFavoritesView(APIView):
    """
    GET    /api/v1/public/{username}/{slug}/favorites/?client_uid=...
           Batch-fetches every media_asset id this client has favorited
           in this gallery, in ONE request — restoring heart-icon state
           across the whole grid on page load without a per-photo call.
    POST   /api/v1/public/{username}/{slug}/favorites/
           Body: { media_asset_id, client_uid? }. Idempotent: favoriting
           an already-favorited photo is a no-op 200, not a conflict.
    DELETE /api/v1/public/{username}/{slug}/favorites/
           Body: { media_asset_id, client_uid? }. Idempotent: unfavoriting
           a not-favorited photo is a no-op 200, not a 404.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get_gallery(self, username, slug):
        try:
            now = timezone.now()
            return Gallery.objects.get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None

    def get(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        client_key, _, _, error = _resolve_client_identity(gallery, request)
        if error:
            return error

        favorited_ids = Favorite.objects.filter(
            gallery=gallery, client_key=client_key
        ).values_list('media_asset_id', flat=True)
        return Response(
            {'favorited_ids': [str(i) for i in favorited_ids]},
            status=status.HTTP_200_OK
        )

    def post(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = FavoriteToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_key, client_session, email, error = _resolve_client_identity(gallery, request)
        if error:
            return error

        # Tenant scoping: the asset must belong to THIS gallery — an id
        # from another photographer's gallery (or another gallery
        # entirely) can never be favorited through this endpoint,
        # regardless of what client_key/token is supplied.
        try:
            asset = MediaAsset.objects.get(
                id=serializer.validated_data['media_asset_id'], gallery=gallery
            )
        except MediaAsset.DoesNotExist:
            return Response(
                {'error': 'Photo not found in this gallery.'},
                status=status.HTTP_404_NOT_FOUND
            )

        Favorite.objects.get_or_create(
            gallery=gallery,
            media_asset=asset,
            client_key=client_key,
            defaults={'client_session': client_session, 'email': email},
        )
        return Response({'favorited': True}, status=status.HTTP_200_OK)

    def delete(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = FavoriteToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_key, _, _, error = _resolve_client_identity(gallery, request)
        if error:
            return error

        Favorite.objects.filter(
            gallery=gallery,
            media_asset_id=serializer.validated_data['media_asset_id'],
            client_key=client_key,
        ).delete()
        return Response({'favorited': False}, status=status.HTTP_200_OK)


class PublicGalleryDownloadView(APIView):
    """
    POST /api/v1/public/{username}/{slug}/download/

    Compiles, audits, and streams a gallery's original high-res assets 
    as a single compressed ZIP archive directly to the client's browser.
    
    Uses O(1) Memory Spooling: compiles the ZIP incrementally on the server's 
    hard drive, and streams it back in small chunk-buffers (64KB) using Django's 
    StreamingHttpResponse, completely eliminating RAM exhaustion risks.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordUnlockRateThrottle]

    def get_gallery(self, username, slug):
        """Retrieves targeted active gallery for validation."""
        try:
            now = timezone.now()
            return Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True
            )
        except Gallery.DoesNotExist:
            return None

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')

    def _verify_download_pin(self, gallery, request):
        """
        Second, independent gate from the gallery access password — see
        Gallery.download_pin_hash's docstring. Returns
        (pin_was_required_and_passed: bool, error_response or None).
        A gallery with no PIN configured always passes with
        pin_was_required_and_passed=False (nothing to log as "verified").
        """
        if not gallery.download_pin_hash:
            return False, None

        pin = (request.data.get('pin') or '').strip()
        if not pin:
            return False, Response(
                {'error': 'A download PIN is required for this gallery.', 'code': 'pin_required'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        try:
            valid = bcrypt.checkpw(pin.encode('utf-8'), gallery.download_pin_hash.encode('utf-8'))
        except Exception:
            valid = False
        if not valid:
            return False, Response(
                {'error': 'Incorrect download PIN.', 'code': 'invalid_pin'},
                status=status.HTTP_401_UNAUTHORIZED
            )
        return True, None

    def post(self, request, username, slug):
        # 1. Fetch the gallery
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        # 2. Guard: Verify photographer permits downloads
        if not gallery.allow_download:
            return Response(
                {'error': 'Original file downloads are disabled for this gallery.'},
                status=status.HTTP_403_FORBIDDEN
            )

        # 3. Guard: Verify password if protected
        if gallery.is_password_protected:
            token = request.data.get('token', '').strip() or request.query_params.get('token', '').strip()

            # Assert a valid, non-expired ClientSession has been registered for this guest token
            valid_session = ClientSession.objects.not_expired().filter(
                access_token=token,
                gallery=gallery
            ).exists()

            if not valid_session:
                return Response(
                    {'error': 'An active unlocked session is required to download this gallery.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # 3b. Guard: verify the optional download PIN, independent of the
        # gallery access password above.
        pin_verified, pin_error = self._verify_download_pin(gallery, request)
        if pin_error:
            return pin_error

        # 4. Validate guest email (Photographer lead capture)
        email = request.data.get('email', '').strip()
        if not email:
            return Response(
                {'error': 'A valid email address is required to initiate downloads.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 4b. Resolution choice: 'web' serves the already-generated 2048px
        # WebP display derivative (no regeneration, no extra stored
        # file — see Gallery.design_settings-style "reuse what already
        # exists" convention); 'original' (default, preserves prior
        # behavior for any existing caller that doesn't send this field
        # yet) serves the authorized private original. An asset with no
        # display derivative yet (still processing, or a video — videos
        # have no display_file) falls back to its original rather than
        # silently dropping it from the ZIP.
        resolution = (request.data.get('resolution') or 'download').strip().lower()
        if resolution not in ('web', 'download', 'original'):
            return Response(
                {'error': "resolution must be 'web', 'download', or 'original'."},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Which PhotoSet (if any) this download was scoped to — validated
        # against this gallery before use, both as a real filter and as
        # the activity-log field, so an arbitrary/malformed client-
        # supplied value can neither leak another gallery's set nor crash
        # the query with an invalid UUID.
        raw_set_id = request.data.get('set_id')
        photo_set = None
        if raw_set_id:
            try:
                photo_set = PhotoSet.objects.filter(id=raw_set_id, gallery=gallery).first()
            except (ValueError, ValidationError):
                photo_set = None

        # 5. Fetch media assets (Support Selective Download).
        # asset_ids is validated through a real UUIDField list, exactly
        # like PhotoBulkDeleteSerializer/PhotoReorderSerializer already
        # validate similar id lists elsewhere — a malformed UUID here
        # must 400, not reach `id__in=...` and raise an uncaught
        # ValidationError/500 (the F-27 finding this closes).
        asset_ids_raw = request.data.get('asset_ids', [])
        if asset_ids_raw:
            if not isinstance(asset_ids_raw, list):
                return Response(
                    {'error': 'asset_ids must be a list.'}, status=status.HTTP_400_BAD_REQUEST
                )
            id_field = serializers.ListField(child=serializers.UUIDField(), allow_empty=True)
            try:
                asset_ids = id_field.run_validation(asset_ids_raw)
            except serializers.ValidationError:
                return Response(
                    {'error': 'One or more asset_ids are not valid UUIDs.'},
                    status=status.HTTP_400_BAD_REQUEST
                )
        else:
            asset_ids = []

        if asset_ids:
            # Download specific assets
            assets = MediaAsset.objects.filter(gallery=gallery, id__in=asset_ids)
        elif photo_set:
            assets = MediaAsset.objects.filter(gallery=gallery, photo_set=photo_set)
        else:
            # Download all gallery assets (fallback/default)
            assets = MediaAsset.objects.filter(gallery=gallery)

        # Materialize once: both the sync-work-size guard below and the
        # compilation loop need the full list, and a QuerySet would
        # otherwise re-query the database for each.
        assets = list(assets)

        if not assets:
            return Response(
                {'error': 'Cannot compile download: No valid assets found.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5b. Guard against an unbounded synchronous compile — see
        # SYNC_ZIP_MAX_ASSET_COUNT/SYNC_ZIP_MAX_TOTAL_BYTES's own comment
        # in settings/base.py for why this exists and why these are
        # deliberately generous technical ceilings, not a plan limit.
        if len(assets) > settings.SYNC_ZIP_MAX_ASSET_COUNT:
            return Response({
                'error': f'Too many items requested in one download ({len(assets)}). '
                         f'Please select {settings.SYNC_ZIP_MAX_ASSET_COUNT} or fewer at a time.',
                'code': 'download_too_large',
            }, status=status.HTTP_400_BAD_REQUEST)

        total_bytes = sum(a.file_size or 0 for a in assets)
        if total_bytes > settings.SYNC_ZIP_MAX_TOTAL_BYTES:
            return Response({
                'error': 'This selection is too large to package in one download. '
                         'Please select a smaller batch.',
                'code': 'download_too_large',
            }, status=status.HTTP_400_BAD_REQUEST)

        # 6. O(1) Memory Compression Spooling
        # Create a temporary secure file path on the hard drive rather than RAM
        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(temp_zip_fd)

        try:
            used_names = set()

            # Open the zip archive writer
            with zipfile.ZipFile(temp_zip_path, 'w') as zip_file:
                for asset in assets:
                    # 'web' prefers the already-generated display derivative;
                    # falls back to the original when none exists yet
                    # (still processing) or for videos (no display_file).
                    source_field = asset.original_file
                    if resolution == 'web' and getattr(asset, 'display_file', None):
                        source_field = asset.display_file
                    elif resolution == 'download':
                        source_field, _ = _get_client_download_source(asset)

                    if not source_field:
                        continue

                    # Sanitized against path traversal / zip-slip and
                    # header-injection characters (original_name is
                    # untrusted user input — see sanitize_download_filename's
                    # own docstring), then de-duplicated: two assets
                    # sharing a filename would otherwise silently produce
                    # two same-named entries in the archive, which most
                    # unzip tools resolve by keeping only one — a real,
                    # silent data-loss bug for the client, not a cosmetic one.
                    safe_name = sanitize_download_filename(asset.original_name, fallback=str(asset.id))
                    entry_name = safe_name
                    if entry_name in used_names:
                        base, ext = os.path.splitext(safe_name)
                        suffix = 1
                        while entry_name in used_names:
                            entry_name = f"{base}_{suffix}{ext}"
                            suffix += 1
                    used_names.add(entry_name)

                    # Already-compressed media (every format this pipeline
                    # ever produces or accepts) gains nothing from DEFLATE
                    # and just burns CPU re-compressing already-entropic
                    # bytes — STORED for those, DEFLATE only for the rare
                    # format that could actually benefit.
                    zinfo = zipfile.ZipInfo(
                        filename=entry_name,
                        date_time=time.localtime(time.time())[:6],
                    )
                    zinfo.compress_type = (
                        zipfile.ZIP_STORED
                        if os.path.splitext(entry_name)[1].lower() in ALREADY_COMPRESSED_EXTS
                        else zipfile.ZIP_DEFLATED
                    )

                    try:
                        source_field.open('rb')
                        with zip_file.open(zinfo, 'w') as dest:
                            # Stream the file in 1MB chunks instead of loading entirely into RAM
                            for chunk in source_field.chunks(chunk_size=1024 * 1024):
                                dest.write(chunk)
                    except Exception:
                        # Log the failure so you know exactly which file dropped and why
                        logger.exception(
                            "Failed to add asset %s to ZIP for gallery %s", asset.id, gallery.id
                        )
                        used_names.discard(entry_name)
                    finally:
                        source_field.close()

            # 7. Audit: register the download log for lead tracking — only
            # now, after the ZIP has actually compiled successfully. A
            # compilation failure above raises out to the except block
            # below and never reaches this line, so a failed download is
            # never recorded as if it succeeded (the F-27 finding this closes).
            ip_address = self._get_client_ip(request)
            DownloadLog.objects.create(
                gallery=gallery,
                email=email,
                ip_address=ip_address,
                download_type=DownloadLog.DownloadType.GALLERY,
                resolution=resolution,
                pin_verified=pin_verified,
                photo_set=photo_set,
            )

            # 8. Dynamic Chunked Stream Generator
            def file_iterator(file_path, chunk_size=65536):
                """Streams the compiled ZIP in 64KB chunks and unlinks it when finished."""
                try:
                    with open(file_path, 'rb') as f:
                        while True:
                            chunk = f.read(chunk_size)
                            if not chunk:
                                break
                            yield chunk
                finally:
                    # Strict Filesystem Hygiene: Clean up the disk spool
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

            # Serve the streaming attachment directly to David's frontend download handlers
            response = StreamingHttpResponse(file_iterator(temp_zip_path), content_type="application/zip")
            safe_zip_name = sanitize_download_filename(f"{gallery.slug}.zip", fallback="gallery.zip")
            response['Content-Disposition'] = f'attachment; filename="{safe_zip_name}"'
            return response

        except Exception as e:
            # If ZIP compilation completely crashes, clean up the temp file
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            return Response(
                {"error": f"Failed to compile download package: {str(e)}"},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


class PublicGalleryDirectDownloadView(PublicGalleryDownloadView):
    """
    GET /api/v1/public/{username}/{slug}/download-all/?token=<access_token>

    Anchor-friendly full-gallery download for the public client view. Unlike
    the existing POST download endpoint, this intentionally has no lead form:
    it is used only for galleries without a download PIN. The client retains
    the existing POST/email/PIN flow when a download PIN is configured.
    """
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get_gallery(self, username, slug):
        # Fetch first so an unpublished/inactive gallery can receive the same
        # explicit forbidden response as a disabled download, rather than
        # reaching any storage work.
        return Gallery.objects.select_related('photographer').filter(
            slug=slug,
            photographer__username=username,
        ).first()

    def _verify_download_pin(self, gallery, request):
        if not gallery.download_pin_hash:
            return False, None

        pin = request.query_params.get('pin', '').strip()
        if not pin:
            return False, Response(
                {'error': 'A download PIN is required for this gallery.', 'code': 'pin_required'},
                status=status.HTTP_403_FORBIDDEN,
            )
        try:
            valid = bcrypt.checkpw(pin.encode('utf-8'), gallery.download_pin_hash.encode('utf-8'))
        except Exception:
            valid = False
        if not valid:
            return False, Response(
                {'error': 'Incorrect download PIN.', 'code': 'invalid_pin'},
                status=status.HTTP_403_FORBIDDEN,
            )
        return True, None

    def get(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        is_expired = gallery.expires_at and gallery.expires_at <= timezone.now()
        if not gallery.is_published or not gallery.is_active or is_expired or not gallery.allow_download:
            return Response({'error': 'Downloads are unavailable for this gallery.'}, status=status.HTTP_403_FORBIDDEN)

        if gallery.is_password_protected:
            token = request.query_params.get('token', '').strip()
            if not ClientSession.objects.not_expired().filter(
                access_token=token,
                gallery=gallery,
            ).exists():
                return Response(
                    {'error': 'An active unlocked session is required to download this gallery.'},
                    status=status.HTTP_403_FORBIDDEN,
                )

        pin_verified, pin_error = self._verify_download_pin(gallery, request)
        if pin_error:
            return pin_error

        # The public gallery only exposes READY media. Match that contract for
        # a collection download so failed/pending uploads never become ZIP
        # entries. PublicPhotoDownloadView supports both image and video
        # originals, so both ready media types are included here too.
        assets = list(MediaAsset.objects.filter(
            gallery=gallery,
            processing_status=MediaAsset.ProcessingStatus.READY,
            media_type__in=[MediaAsset.MediaType.IMAGE, MediaAsset.MediaType.VIDEO],
        ).exclude(original_file=''))
        if not assets:
            return Response({'error': 'No ready media is available to download.'}, status=status.HTTP_400_BAD_REQUEST)

        if len(assets) > settings.SYNC_ZIP_MAX_ASSET_COUNT:
            return Response(
                {'error': 'This gallery is too large to package in one download.', 'code': 'download_too_large'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if sum(asset.file_size or 0 for asset in assets) > settings.SYNC_ZIP_MAX_TOTAL_BYTES:
            return Response(
                {'error': 'This gallery is too large to package in one download.', 'code': 'download_too_large'},
                status=status.HTTP_400_BAD_REQUEST,
            )

        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix='.zip')
        os.close(temp_zip_fd)
        try:
            used_names = set()
            added_asset_count = 0
            with zipfile.ZipFile(temp_zip_path, 'w', compression=zipfile.ZIP_STORED) as zip_file:
                for asset in assets:
                    source_field, _ = _get_client_download_source(asset)
                    safe_name = sanitize_download_filename(asset.original_name, fallback=str(asset.id))
                    entry_name = safe_name
                    base, ext = os.path.splitext(safe_name)
                    suffix = 1
                    while entry_name in used_names:
                        entry_name = f'{base}_{suffix}{ext}'
                        suffix += 1
                    used_names.add(entry_name)

                    try:
                        source_field.open('rb')
                        with zip_file.open(entry_name, 'w', force_zip64=True) as destination:
                            for chunk in source_field.chunks(chunk_size=1024 * 1024):
                                destination.write(chunk)
                        added_asset_count += 1
                    except Exception:
                        logger.exception('Failed to add asset %s to public ZIP for gallery %s', asset.id, gallery.id)
                        used_names.discard(entry_name)
                    finally:
                        source_field.close()

            if not added_asset_count:
                os.remove(temp_zip_path)
                return Response({'error': 'No ready media is available to download.'}, status=status.HTTP_400_BAD_REQUEST)

            DownloadLog.objects.create(
                gallery=gallery,
                email=None,
                ip_address=self._get_client_ip(request),
                download_type=DownloadLog.DownloadType.GALLERY,
                resolution=DownloadLog.Resolution.DOWNLOAD,
                pin_verified=pin_verified,
            )

            def file_iterator(file_path, chunk_size=65536):
                try:
                    with open(file_path, 'rb') as zip_file:
                        while chunk := zip_file.read(chunk_size):
                            yield chunk
                finally:
                    try:
                        os.remove(file_path)
                    except OSError:
                        pass

            response = StreamingHttpResponse(file_iterator(temp_zip_path), content_type='application/zip')
            safe_zip_name = sanitize_download_filename(f'{gallery.slug}.zip', fallback='gallery.zip')
            response['Content-Disposition'] = f'attachment; filename="{safe_zip_name}"'
            return response
        except Exception:
            logger.exception('Failed to compile public ZIP for gallery %s', gallery.id)
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            return Response(
                {'error': 'Unable to prepare this download. Please try again.'},
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )


class PublicVideoStreamView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/video/{asset_id}/stream/
    GET .../stream/?token=<access_token>   (password-protected galleries)

    Serves the ORIGINAL video file for in-gallery playback. Deliberately
    distinct from PublicGalleryDownloadView: no email capture, no ZIP
    compilation — this exists purely so a client can click a video and
    watch it inline, the same way they can already view full-quality
    2048px images inline with no email required. The gated ZIP archive
    is still the only bulk/lead-capture download path, and still respects
    gallery.allow_download — this view does not, matching how inline image
    viewing has never respected that flag either (it only ever gated the
    ZIP). There is currently no downsized/watermarked "safe" streaming
    variant for video (see H-7 follow-up notes) — this serves the same
    file the ZIP would contain.

    Respects the same password-gallery session-token gate as
    PublicGalleryView. A <video src="..."> is loaded directly by the
    browser with no custom headers possible, so the token travels as a
    query param — the same fallback PublicGalleryView.get_session_token()
    already supports.

    Range-request support (required for seeking/scrubbing):
      - Remote/object storage (S3 in production): redirects to a
        short-lived presigned URL, which natively supports Range.
      - Local disk (dev): streams via Django's FileResponse, which
        handles Range requests automatically.

    NOTE: video content served this way has no extra anti-download
    protection beyond controlsList="nodownload" on the frontend <video>
    tag (a UI hint only, trivially bypassed) — unlike images, which get a
    weak but real "right-click disabled" nudge. There's no strong general
    fix for this short of DRM, which is out of scope here.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get_gallery(self, username, slug):
        try:
            now = timezone.now()
            return Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None

    def get_session_token(self, request):
        auth_header = request.META.get('HTTP_AUTHORIZATION', '')
        if auth_header.startswith('Bearer '):
            return auth_header[len('Bearer '):].strip()
        return request.query_params.get('token', '').strip()

    def validate_session_token(self, token, gallery):
        if not token:
            return False
        return ClientSession.objects.not_expired().filter(access_token=token, gallery=gallery).exists()

    def get(self, request, username, slug, asset_id):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if gallery.is_password_protected:
            token = self.get_session_token(request)
            if not self.validate_session_token(token, gallery):
                return Response(
                    {'error': 'Invalid or expired access token.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        try:
            asset = MediaAsset.objects.get(
                id=asset_id,
                gallery=gallery,
                media_type=MediaAsset.MediaType.VIDEO,
            )
        except MediaAsset.DoesNotExist:
            return Response({'error': 'Video not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Prefer the processed, browser-guaranteed-compatible H.264/AAC MP4
        # derivative (faststart, capped at 1080p — see process_video_pipeline)
        # over the original: it's smaller, starts playing sooner, and
        # decodes reliably in every modern browser regardless of the
        # source codec/container (MOV/HEVC included). Falls back to the
        # original file only while processing hasn't completed yet
        # (PENDING/PROCESSING) or failed, so playback still works —
        # just unoptimized — rather than breaking until a retry succeeds.
        video_field = asset.playback_file if asset.playback_file else asset.original_file
        if not video_field:
            return Response({'error': 'Video file is not available.'}, status=status.HTTP_404_NOT_FOUND)

        # Check the storage actually backing THIS field, not one
        # project-wide default — original_file (PrivateMediaStorage) and
        # playback_file (PublicMediaStorage) are independent storage
        # classes as of Phase 2 (apps/core/storage.py), so the choice of
        # "redirect to remote URL" vs "stream from local disk" must be
        # made per-field.
        if video_field.storage.__class__.__name__ != 'FileSystemStorage':
            return HttpResponseRedirect(video_field.url)

        # Local disk (dev) — FileResponse handles Range headers automatically
        # and guesses content-type from the stored filename's extension.
        video_field.open('rb')
        return FileResponse(video_field)
    

class PublicPhotoDownloadView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/photo/{photo_id}/download/
    GET .../download/?token=<access_token>&resolution=web|download|original&pin=1234

    Streams ONE file (image OR video — despite the URL saying "photo",
    nothing here restricts media_type; PublicMediaAssetSerializer.download_url
    points here for both) with a forced Content-Disposition: attachment
    header. This is the only reliable way to force a "Save As" prompt
    across browsers and storage backends, so it's what download_url
    always points to — never a bare S3/disk URL.

    Deliberately does NOT require an email (unlike the bulk ZIP endpoint).
    A single-photo hover/lightbox download is meant to be frictionless once
    a gallery is unlocked; the "Download All" button keeps the email-capture
    step for lead generation. It DOES still respect the gallery's optional
    download PIN (query param, since this is a plain <a href> GET, not a
    JSON POST — same convention as ?token=).
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get_gallery(self, username, slug):
        try:
            now = timezone.now()
            return Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None

    def get(self, request, username, slug, photo_id):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not gallery.allow_download:
            return Response(
                {'error': 'Downloads are disabled for this gallery.'},
                status=status.HTTP_403_FORBIDDEN
            )

        if gallery.is_password_protected:
            token = request.query_params.get('token', '').strip()
            valid_session = ClientSession.objects.not_expired().filter(
                access_token=token,
                gallery=gallery
            ).exists()
            if not valid_session:
                return Response(
                    {'error': 'An active unlocked session is required to download this photo.'},
                    status=status.HTTP_401_UNAUTHORIZED
                )

        pin_verified = False
        if gallery.download_pin_hash:
            pin = request.query_params.get('pin', '').strip()
            if not pin:
                return Response(
                    {'error': 'A download PIN is required for this gallery.', 'code': 'pin_required'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            try:
                valid_pin = bcrypt.checkpw(pin.encode('utf-8'), gallery.download_pin_hash.encode('utf-8'))
            except Exception:
                valid_pin = False
            if not valid_pin:
                return Response(
                    {'error': 'Incorrect download PIN.', 'code': 'invalid_pin'},
                    status=status.HTTP_401_UNAUTHORIZED
                )
            pin_verified = True

        try:
            asset = MediaAsset.objects.get(id=photo_id, gallery=gallery)
        except MediaAsset.DoesNotExist:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)

        resolution = request.query_params.get('resolution', 'download').strip().lower()
        if resolution not in ('web', 'download', 'original'):
            resolution = 'download'

        # 'web' prefers the smaller, already-generated derivative — the
        # display WebP for an image, the H.264 playback MP4 for a video —
        # over re-serving the original. Falls back to the original when
        # no such derivative exists yet (still processing).
        source_field = asset.original_file
        if resolution == 'web':
            web_field = (
                asset.display_file
                if asset.media_type == MediaAsset.MediaType.IMAGE
                else asset.playback_file
            )
            if web_field:
                source_field = web_field
            else:
                resolution = 'original'
        elif resolution == 'download':
            source_field, resolution = _get_client_download_source(asset)

        if not source_field:
            return Response({'error': 'File unavailable.'}, status=status.HTTP_404_NOT_FOUND)

        # Phase 4 (download hardening): opens and streams the file instead
        # of `.read()`-ing it fully into memory first. FileResponse pulls
        # from the file-like object in bounded chunks as the response
        # streams out (using the WSGI server's file_wrapper when
        # available, a manual chunked read loop otherwise) and closes it
        # for us once done — this works identically whether source_field
        # is local disk (dev) or an S3Boto3StorageFile (prod): neither
        # backend needs its entire content resident in RAM at once, which
        # matters a lot more for a multi-GB video original than it ever
        # did for a photo.
        try:
            source_field.open('rb')
        except Exception:
            return Response({'error': 'File unavailable.'}, status=status.HTTP_404_NOT_FOUND)

        # A derivative has a different extension than the original
        # (.webp/.mp4 vs whatever the camera produced) — the download
        # filename must match the actual bytes being served, or the
        # saved file's extension would lie about its own format.
        if source_field is asset.original_file or resolution == 'download':
            raw_filename = asset.original_name
        else:
            raw_filename = os.path.basename(source_field.name)
        download_filename = sanitize_download_filename(raw_filename, fallback=str(asset.id))

        # Audit only after every gate above has passed and the file has
        # been confirmed openable — never before, and never for a file
        # that turned out to be unavailable.
        DownloadLog.objects.create(
            gallery=gallery,
            email=None,
            ip_address=self._get_client_ip(request),
            media_asset=asset,
            download_type=(
                DownloadLog.DownloadType.VIDEO
                if asset.media_type == MediaAsset.MediaType.VIDEO
                else DownloadLog.DownloadType.PHOTO
            ),
            resolution=resolution,
            pin_verified=pin_verified,
        )

        response = FileResponse(
            source_field,
            as_attachment=True,
            filename=download_filename,
            content_type='application/octet-stream',
        )
        return response

    def _get_client_ip(self, request):
        x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
        if x_forwarded_for:
            return x_forwarded_for.split(',')[0].strip()
        return request.META.get('REMOTE_ADDR')


class PublicPhotographerPortfolioView(APIView):
    """
    GET /api/v1/public/{username}/
    
    Public portfolio gateway.
    Returns a photographer's public profile metadata (display name, bio, avatar)
    along with an optimized array of all their published, active galleries.
    """
    permission_classes = [AllowAny]
    # Enforces empty authentication to prevent guest view blocks on unauthenticated routes
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get(self, request, username):
        # Dynamic import to prevent circular dependency boots
        from apps.users.models import User
        from apps.galleries.models import Gallery
        from apps.galleries.serializers import GalleryListSerializer

        # 1. Fetch photographer safely. Returns 404 if user is inactive/
        # absent, OR is a staff/superuser account (Phase 4, F-35 part 2)
        # — internal/admin accounts were never meant to be discoverable
        # as public photographer portfolios; excluding them here is the
        # same "return 404, don't distinguish why" pattern this app
        # already uses everywhere else to avoid enumeration.
        photographer = get_object_or_404(
            User.objects.filter(is_active=True, is_staff=False, is_superuser=False),
            username=username.strip().lower()
        )

        # 2. Fetch all published, active galleries belonging to this
        # photographer. Phase 4 (F-35 part 1): password-protected
        # galleries are explicitly excluded from this public listing —
        # "protected" means private by product intent, so a protected
        # gallery's title/cover must not be discoverable on the public
        # portfolio page even though its content is itself gated by the
        # password. A protected gallery's own direct link still works
        # exactly as before; it simply isn't listed here.
        # select_related cover_photo and Count annotations are applied to eliminate N+1 SQL queries
        now = timezone.now()
        galleries = (
            Gallery.objects
            .filter(
                Q(expires_at__isnull=True) | Q(expires_at__gt=now),
                photographer=photographer,
                is_published=True,
                is_active=True,
                is_password_protected=False,
            )
            .select_related('cover_photo')
            .annotate(photo_count=Count('assets'))
            .order_by('-created_at')
        )

        # 3. Serialize the collections array safely
        gallery_serializer = GalleryListSerializer(
            galleries,
            many=True,
            context={'request': request}
        )

        # 4. Return unified photographer portfolio metadata to unblock ClientHomePage.jsx
        return Response({
            "photographer": {
                "username": photographer.username,
                "display_name": photographer.display_name or photographer.username,
                "bio": photographer.bio,
                "avatar": request.build_absolute_uri(photographer.avatar.url) if photographer.avatar else None,
            },
            "galleries": gallery_serializer.data
        }, status=status.HTTP_200_OK)
