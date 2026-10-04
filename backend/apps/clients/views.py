#C:\Users\LENOVO\Desktop\kyapture\backend\apps\clients\views.py :
import os
import time
import tempfile
import zipfile
from django.conf import settings
from django.http import StreamingHttpResponse, HttpResponse, FileResponse, HttpResponseRedirect
from datetime import timedelta
from django.urls import reverse
from urllib.parse import urlencode
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
from .models import ClientSession, DownloadJob, DownloadLog, Favorite, FavoriteList
from . import favorite_lists as fav
from apps.photos.models import MediaAsset, PhotoSet
from .serializers import (
    PublicGallerySerializer,
    GalleryUnlockSerializer,
    PublicMediaAssetSerializer,
    FavoriteToggleSerializer,
)
from apps.core.pagination import GalleryMediaPagination

INVALID_SET = object()

# Repeat requests for the same prepared file inside this window are one download.
DOWNLOAD_RETRY_WINDOW_SECONDS = 60


def parse_set_id(raw):
    """
    Normalizes the public `?set=` filter: None for "no filter", a UUID for a
    well-formed id, and INVALID_SET for a malformed one. A malformed value
    used to reach the ORM and raise ValidationError -> an unhandled 500 on a
    public, unauthenticated endpoint; it now simply matches nothing, exactly
    like a well-formed id for a set that doesn't exist.
    """
    raw = (raw or '').strip()
    if not raw:
        return None
    try:
        return uuid.UUID(raw)
    except ValueError:
        return INVALID_SET
from apps.core.utils import (
    sanitize_download_filename,
    ALREADY_COMPRESSED_EXTS,
    process_download_master,
)
from .download_access import (
    as_clean_str,
    asset_set_is_enabled_for_download,
    authorize_download,
    download_access_ttl,
    download_limit_reached,
    effective_high_res_mode,
    email_is_allowed,
    error_response,
    file_token_state,
    get_download_policy,
    issue_download_token,
    issue_file_token,
    download_pin_enforced,
    pin_limit_reached,
    record_pin_use,
    resolution_is_allowed,
    set_is_enabled_for_download,
    validate_client_email,
    verify_pin,
    web_px_for_gallery,
)
from .download_jobs import (
    expire_if_stale,
    find_reusable_job,
    is_expired,
    job_assets,
    job_files_exist,
    mark_file_missing,
    size_limit_error,
)
from .tasks import prepare_download_job
from apps.core.storage import PrivateMediaStorage

import logging
import uuid


logger = logging.getLogger(__name__)

# 1R.6: "Original" is never a client-facing resolution any more -- the
# client only ever asks for 'web' ("Web Size") or 'download' ("High
# Resolution"); which bytes 'download' actually resolves to (the 3600px
# Download Master, or the true original for an entitled Pro photographer
# who chose it) is a server-only decision -- see effective_high_res_mode()
# in download_access.py. A raw resolution=original is rejected here with
# a plain 400, before it reaches any policy/entitlement check.
DOWNLOAD_RESOLUTIONS = ('web', 'download')


def _validate_download_resolution(gallery, resolution):
    """Return an API error when a valid size is disabled by its owner."""
    if resolution not in DOWNLOAD_RESOLUTIONS:
        return Response(
            {'error': "resolution must be 'web' or 'download'.", 'code': 'invalid_resolution'},
            status=status.HTTP_400_BAD_REQUEST,
        )
    if not resolution_is_allowed(gallery, resolution):
        return Response(
            {'error': 'That download size is not available for this gallery.', 'code': 'resolution_not_allowed'},
            status=status.HTTP_403_FORBIDDEN,
        )
    return None


def _get_client_ip(request):
    x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
    if x_forwarded_for:
        return x_forwarded_for.split(',')[0].strip()
    return request.META.get('REMOTE_ADDR')


def _studio_name(gallery):
    """Human-facing name for a "Contact {studio}" error -- never the allow-list itself."""
    photographer = gallery.photographer
    return photographer.display_name or photographer.username


def _resolve_web_source(asset, px):
    """
    Which already-generated derivative backs a 'web' ("Web Size") download
    at the gallery's configured px tier (2048/1280/640 -- the three real
    tiers apps/core/utils.py's pipeline already produces; see
    _DISPLAY_TIERS there). Video has no sized derivative, so 'web' serves
    the H.264 playback file. Falls back down the chain, then to the
    original, rather than ever returning nothing for an asset still
    processing.
    """
    if asset.media_type != MediaAsset.MediaType.IMAGE:
        return getattr(asset, 'playback_file', None) or asset.original_file
    preferred = {2048: 'display_file', 1280: 'medium_file', 640: 'thumbnail_file'}.get(px, 'display_file')
    ordered = [preferred] + [f for f in ('display_file', 'medium_file', 'thumbnail_file') if f != preferred]
    for field_name in ordered:
        field = getattr(asset, field_name, None)
        if field:
            return field
    return asset.original_file


def _resolve_zip_source(asset, resolution, gallery):
    """
    Which stored file represents `asset` inside a ZIP at the requested
    resolution. 'web' uses _resolve_web_source at the gallery's configured
    px tier; 'download' ("High Resolution") resolves via
    _get_client_download_source -- the 3600px Download Master, or the true
    original for an entitled Pro photographer who chose it.
    """
    if resolution == 'web':
        return _resolve_web_source(asset, web_px_for_gallery(gallery))
    return _get_client_download_source(asset, gallery)[0]


def _zip_entry_base_name(asset, source_field, resolution):
    """
    Sanitized archive filename for `asset`. A Web Size entry is a WebP
    derivative tier (2048/1280/640px), so its extension must match those
    bytes rather than the camera original's (a .jpg name holding WebP data
    is a lying file).
    """
    safe_name = sanitize_download_filename(asset.original_name, fallback=str(asset.id))
    if resolution == 'web':
        for field_name in ('display_file', 'medium_file', 'thumbnail_file'):
            field = getattr(asset, field_name, None)
            if field and source_field.name == field.name:
                safe_name = os.path.splitext(safe_name)[0] + os.path.splitext(source_field.name)[1]
                break
    return safe_name


def _unique_zip_entry_name(safe_name, used_names):
    """
    De-duplicates archive entry names. Comparison is case-insensitive:
    `Photo.jpg` and `photo.JPG` are one file on Windows/macOS extraction,
    so treating them as distinct would silently drop one for those clients.
    `used_names` holds lower-cased names.
    """
    entry_name = safe_name
    base, ext = os.path.splitext(safe_name)
    suffix = 1
    while entry_name.lower() in used_names:
        entry_name = f'{base}_{suffix}{ext}'
        suffix += 1
    used_names.add(entry_name.lower())
    return entry_name


def _get_photo_set(gallery, raw_set_id):
    """
    Resolves a client-supplied set id to a PhotoSet OF THIS GALLERY, or None.
    Scoped by gallery, so another gallery's set id can never be resolved,
    and a malformed UUID is treated as "no such set" instead of a 500.
    """
    raw_set_id = as_clean_str(raw_set_id)
    if not raw_set_id:
        return None
    try:
        return PhotoSet.objects.filter(id=raw_set_id, gallery=gallery).first()
    except (ValueError, ValidationError):
        return None


def _get_client_download_source(asset, gallery):
    """
    Return the file to serve for a 'download' ("High Resolution") request,
    plus the DownloadLog.Resolution label to record.

    'original' only when the gallery's EFFECTIVE High Resolution mode is
    'original' (chosen by the photographer AND currently Pro-entitled --
    see effective_high_res_mode(); auto-falls back to '3600' the moment a
    Pro plan lapses, with the stored choice left untouched) -- or always,
    for video, which has no Download Master pipeline (unchanged
    pre-existing behavior). Otherwise the private Download Master, lazily
    backfilled for legacy assets that predate it.
    """
    if effective_high_res_mode(gallery) == 'original' or asset.media_type != MediaAsset.MediaType.IMAGE:
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


class PinGuessThrottledMixin:
    """
    The single-file and direct-ZIP downloads are plain GETs on the generous
    browse throttle. Accepting a raw `?pin=` there would let a 4-digit
    download PIN be brute-forced at browsing speed, so any request that
    actually carries a PIN is additionally held to the tight
    'password_unlock' rate, exactly like the POST/unlock endpoints.
    Requests authorized by a download access token are unaffected.
    """

    def get_throttles(self):
        throttles = super().get_throttles()
        if self.request.query_params.get('pin'):
            throttles.append(PasswordUnlockRateThrottle())
        return throttles


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
                # cover_photo rides along in the same query — PublicGallerySerializer
                # reads it for cover_url, which was a separate round trip.
                .select_related('photographer', 'cover_photo')
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
        if photo_set_id is INVALID_SET:
            ready_qs = ready_qs.none()
        elif photo_set_id:
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
        photo_set_id = parse_set_id(request.query_params.get('set', ''))
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
        photo_set_id = parse_set_id(request.query_params.get('set', ''))
        if photo_set_id is INVALID_SET:
            ready_qs = ready_qs.none()
        elif photo_set_id:
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
            {
                'favorited_ids': [str(i) for i in set(favorited_ids)],
                # The email this visitor already gave (so the "enter your email"
                # prompt is asked once), never the client_key.
                'email': fav.visitor_email(gallery, client_key),
            },
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

        given_email, email_error = fav.clean_email(request.data.get('email'))
        if email_error:
            return error_response('Please enter a valid email address.', 'invalid_email', status.HTTP_400_BAD_REQUEST)
        email = given_email or email or fav.visitor_email(gallery, client_key)
        visitor_name = fav.clean_visitor_name(request.data.get('name'))

        list_id = request.data.get('list_id')
        if list_id:
            favorite_list = fav.get_visitor_list(gallery, client_key, list_id)
            if favorite_list is None:
                return error_response('Favorite list not found.', 'list_not_found', status.HTTP_404_NOT_FOUND)
            fav.remember_visitor(gallery, client_key, email, visitor_name)
        else:
            favorite_list = fav.ensure_default_list(gallery, client_key, email, visitor_name)

        favorite, created = Favorite.objects.get_or_create(
            favorite_list=favorite_list,
            media_asset=asset,
            defaults={
                'gallery': gallery, 'client_key': client_key, 'client_session': client_session,
                'email': favorite_list.email or email,
            },
        )
        if not created:
            favorite_list.save(update_fields=['updated_at'])   # list "updated" = last touched
        return Response({'favorited': True, 'list_id': str(favorite_list.id)}, status=status.HTTP_200_OK)

    def delete(self, request, username, slug):
        gallery = self.get_gallery(username.strip().lower(), slug.strip().lower())
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = FavoriteToggleSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        client_key, _, _, error = _resolve_client_identity(gallery, request)
        if error:
            return error

        removals = Favorite.objects.filter(
            gallery=gallery,
            media_asset_id=serializer.validated_data['media_asset_id'],
            client_key=client_key,
        )
        list_id = request.data.get('list_id')
        if list_id:
            favorite_list = fav.get_visitor_list(gallery, client_key, list_id)
            if favorite_list is None:
                return error_response('Favorite list not found.', 'list_not_found', status.HTTP_404_NOT_FOUND)
            removals = removals.filter(favorite_list=favorite_list)
        touched = list(removals.exclude(favorite_list__isnull=True).values_list('favorite_list_id', flat=True))
        removals.delete()
        FavoriteList.objects.filter(pk__in=touched).update(updated_at=timezone.now())
        return Response({
            'favorited': Favorite.objects.filter(
                gallery=gallery, media_asset_id=serializer.validated_data['media_asset_id'], client_key=client_key,
            ).exists(),
        }, status=status.HTTP_200_OK)


def _list_payload(request, favorite_list):
    """Visitor-facing summary of one list (never the client_key)."""
    cover = fav.list_cover_asset(favorite_list)
    thumbnail = None
    if cover is not None:
        thumbnail = PublicMediaAssetSerializer(cover, context={'request': request}).data.get('thumbnail_url')
    return {
        'id': str(favorite_list.id),
        'name': favorite_list.name,
        'is_default': favorite_list.is_default,
        'photo_count': getattr(favorite_list, 'photo_count', favorite_list.favorites.count()),
        'thumbnail_url': thumbnail,
        'created_at': favorite_list.created_at,
        'updated_at': favorite_list.updated_at,
    }


class FavoriteListsAccessMixin:
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def resolve(self, request, username, slug):
        """(gallery, client_key, session, email, error)."""
        try:
            gallery = Gallery.objects.get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
                slug=slug.strip().lower(), photographer__username=username.strip().lower(),
                is_published=True, is_active=True,
            )
        except Gallery.DoesNotExist:
            return None, None, None, None, Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)
        client_key, session, email, error = _resolve_client_identity(gallery, request)
        return gallery, client_key, session, email, error


class GalleryFavoriteListsView(FavoriteListsAccessMixin, APIView):
    """
    GET  /api/v1/public/{username}/{slug}/favorites/lists/?client_uid=&sort=newest|oldest
    POST /api/v1/public/{username}/{slug}/favorites/lists/   { name, client_uid, email?, visitor_name? }

    A visitor's OWN lists only: the lists are looked up by the caller's client
    identity, so another visitor's lists are simply not there.
    """

    def get(self, request, username, slug):
        gallery, client_key, _, _, error = self.resolve(request, username, slug)
        if error:
            return error
        sort = 'oldest' if request.query_params.get('sort') == 'oldest' else 'newest'
        return Response({'results': [_list_payload(request, fl) for fl in fav.annotated_lists(gallery, client_key, sort)]})

    def post(self, request, username, slug):
        gallery, client_key, _, session_email, error = self.resolve(request, username, slug)
        if error:
            return error
        name = fav.clean_list_name(request.data.get('name'))
        if name is None:
            return error_response('Give your list a name (up to 80 characters).', 'invalid_list_name', status.HTTP_400_BAD_REQUEST)
        given_email, email_error = fav.clean_email(request.data.get('email'))
        if email_error:
            return error_response('Please enter a valid email address.', 'invalid_email', status.HTTP_400_BAD_REQUEST)
        email = given_email or session_email or fav.visitor_email(gallery, client_key)
        if fav.visitor_lists(gallery, client_key).count() >= fav.MAX_LISTS_PER_VISITOR:
            return error_response(f'You can have up to {fav.MAX_LISTS_PER_VISITOR} favorite lists.', 'too_many_lists', status.HTTP_400_BAD_REQUEST)
        if fav.visitor_lists(gallery, client_key).filter(name__iexact=name).exists():
            return error_response('You already have a list with that name.', 'list_name_taken', status.HTTP_409_CONFLICT)
        # A visitor's first list is their default one.
        has_default = fav.visitor_lists(gallery, client_key).filter(is_default=True).exists()
        favorite_list = FavoriteList.objects.create(
            gallery=gallery, client_key=client_key, name=name, email=email,
            visitor_name=fav.clean_visitor_name(request.data.get('visitor_name')), is_default=not has_default,
        )
        favorite_list.photo_count = 0
        return Response(_list_payload(request, favorite_list), status=status.HTTP_201_CREATED)


class GalleryFavoriteListDetailView(FavoriteListsAccessMixin, APIView):
    """
    GET    .../favorites/lists/{list_id}/?client_uid=&sort=newest|oldest&page=   photos of the list
    PATCH  .../favorites/lists/{list_id}/   { name, client_uid }                 rename
    DELETE .../favorites/lists/{list_id}/   { client_uid }                       delete the list

    The list is resolved among the CALLER's lists in THIS gallery, so another
    visitor's (or another gallery's) list id is a plain 404.
    """

    def _list(self, request, username, slug, list_id):
        gallery, client_key, _, _, error = self.resolve(request, username, slug)
        if error:
            return None, None, None, error
        favorite_list = fav.get_visitor_list(gallery, client_key, list_id)
        if favorite_list is None:
            return None, None, None, error_response('Favorite list not found.', 'list_not_found', status.HTTP_404_NOT_FOUND)
        return gallery, client_key, favorite_list, None

    def get(self, request, username, slug, list_id):
        gallery, _, favorite_list, error = self._list(request, username, slug, list_id)
        if error:
            return error
        order = 'created_at' if request.query_params.get('sort') == 'oldest' else '-created_at'
        favorites = favorite_list.favorites.select_related('media_asset').order_by(order)
        paginator = GalleryMediaPagination()
        page = paginator.paginate_queryset(favorites, request, view=self)
        assets = PublicMediaAssetSerializer(
            [f.media_asset for f in page], many=True,
            context={'request': request, 'gallery': gallery, 'username': gallery.photographer.username, 'slug': gallery.slug},
        ).data
        response = paginator.get_paginated_response(assets)
        favorite_list.photo_count = favorite_list.favorites.count()
        response.data['list'] = _list_payload(request, favorite_list)
        return response

    def patch(self, request, username, slug, list_id):
        gallery, client_key, favorite_list, error = self._list(request, username, slug, list_id)
        if error:
            return error
        name = fav.clean_list_name(request.data.get('name'))
        if name is None:
            return error_response('Give your list a name (up to 80 characters).', 'invalid_list_name', status.HTTP_400_BAD_REQUEST)
        if fav.visitor_lists(gallery, client_key).filter(name__iexact=name).exclude(pk=favorite_list.pk).exists():
            return error_response('You already have a list with that name.', 'list_name_taken', status.HTTP_409_CONFLICT)
        favorite_list.name = name
        favorite_list.save(update_fields=['name', 'updated_at'])
        return Response(_list_payload(request, favorite_list))

    def delete(self, request, username, slug, list_id):
        _, _, favorite_list, error = self._list(request, username, slug, list_id)
        if error:
            return error
        favorite_list.delete()          # its favorites go with it; photos stay in the gallery
        return Response({'deleted': True})


class PublicDownloadAccessView(APIView):
    """
    POST /api/v1/public/{username}/{slug}/download-access/
    Body: { email?, pin?, token? }      (token may also be a Bearer header)

    Step one of an explicit client Download. Opening, browsing, favoriting
    and sharing a gallery never reach this endpoint — it runs only when the
    client chooses Download. It authorizes the download SERVER-side:

      1. gallery is published/active/unexpired and allow_download is on
      2. a password-protected gallery still requires its own unlock session
         (the gallery password and the download PIN are separate gates)
      3. the download PIN, when the gallery has one
      4. a valid email (lead capture) — taken from the unlock session when
         the client already gave one there, otherwise required in the body

    On success returns a short-lived signed `download_token` the client then
    presents to the single-file / ZIP endpoints, so email and PIN are asked
    once instead of for every photo. See download_access.py for what the
    token is bound to and why it is not a long-lived bearer secret.

    Uses the tight 'password_unlock' throttle: this is the one place a PIN
    can be guessed, so it gets the same brute-force protection as the
    gallery password.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PasswordUnlockRateThrottle]

    def post(self, request, username, slug):
        try:
            gallery = Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
                slug=slug.strip().lower(),
                photographer__username=username.strip().lower(),
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not gallery.allow_download:
            return error_response(
                'Downloads are disabled for this gallery.', 'downloads_disabled',
                status.HTTP_403_FORBIDDEN,
            )

        session = None
        if gallery.is_password_protected:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            token = (
                auth_header[len('Bearer '):].strip()
                if auth_header.startswith('Bearer ')
                else as_clean_str(request.data.get('token'))
            )
            session = ClientSession.objects.not_expired().filter(
                access_token=token, gallery=gallery
            ).first() if token else None
            if session is None:
                return error_response(
                    'An active unlocked session is required to download this gallery.',
                    'session_required', status.HTTP_401_UNAUTHORIZED,
                )

        pin_verified = False
        if download_pin_enforced(gallery):
            # 1R.6 "Limit PIN usage" (Privacy tab, Advanced) -- checked
            # before the PIN itself so a limit already hit can't be worked
            # around by guessing; the limit counts successful verifications
            # only (see record_pin_use below), never bare attempts.
            if pin_limit_reached(gallery):
                return error_response(
                    f'Download limit reached. Contact {_studio_name(gallery)}.', 'pin_limit_reached',
                    status.HTTP_403_FORBIDDEN,
                )
            raw_pin = request.data.get('pin')
            if not as_clean_str(raw_pin):
                return error_response(
                    'A download PIN is required for this gallery.', 'pin_required',
                    status.HTTP_401_UNAUTHORIZED,
                )
            if not verify_pin(gallery, raw_pin):
                return error_response(
                    'Incorrect download PIN.', 'invalid_pin', status.HTTP_401_UNAUTHORIZED,
                )
            pin_verified = True
            record_pin_use(gallery)

        policy = get_download_policy(gallery)
        email = None
        if as_clean_str(request.data.get('email')):
            email, email_error = validate_client_email(request.data.get('email'))
            if email_error:
                return email_error
        elif session is not None and session.email:
            email = session.email
        elif policy['require_email']:
            _, email_error = validate_client_email(None)
            return email_error

        # 1R.6 "Restrict Downloads to Specific Contacts" -- never reveals
        # the allow-list itself, win or lose.
        if not email_is_allowed(gallery, email):
            return error_response(
                f'This email is not authorized to download. Contact {_studio_name(gallery)}.',
                'email_not_authorized', status.HTTP_403_FORBIDDEN,
            )

        # Remember the email on the unlock session (never overwriting one
        # the client already gave) so downloads and favorite activity for
        # this unlocked visit are attributed consistently.
        if session is not None:
            updates = []
            if email and not session.email:
                session.email = email
                updates.append('email')
            if not session.has_download_access:
                session.has_download_access = True
                updates.append('has_download_access')
            if updates:
                session.save(update_fields=updates)

        return Response({
            'download_token': issue_download_token(gallery, email, pin_verified),
            'expires_in': download_access_ttl(),
            'email': email,
            'pin_verified': pin_verified,
        }, status=status.HTTP_200_OK)


class PublicGalleryDownloadView(APIView):
    """
    POST /api/v1/public/{username}/{slug}/download/

    Starts the background preparation of a gallery / set ZIP. It does NOT
    stream anything: after the same gates as before (gallery, allow_download,
    password session, download PIN / email token, size policy, selection
    limits) it creates a DownloadJob, queues the Celery task that builds the
    ZIP into private storage, and answers 202 with the job id.

    The client then polls GET .../download-jobs/{job_id}/ and, once ready,
    downloads through the signed file URL it returns (see
    PublicDownloadJobStatusView / PublicDownloadJobFileView).

    Body: { download_token | pin, email?, token?, resolution?, set_id?, asset_ids? }
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
            token = as_clean_str(request.data.get('token')) or request.query_params.get('token', '').strip()

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

        # 3b. Guard: the download PIN gate (a PIN or a download access token
        # earned by passing it), independent of the gallery password above.
        authorization, auth_error = authorize_download(
            gallery,
            pin=request.data.get('pin'),
            download_token=request.data.get('download_token'),
        )
        if auth_error:
            return auth_error
        pin_verified = authorization.pin_verified

        # 4. Guest email (photographer lead capture): taken from the
        # authorized download session when there is one, else from the body.
        # A deliberately frictionless gallery has neither a PIN nor a
        # require-email rule, so email=None is the correct audited outcome.
        email = authorization.email
        if not email and get_download_policy(gallery)['require_email']:
            email, email_error = validate_client_email(request.data.get('email'))
            if email_error:
                return email_error

        # 4b. Resolution choice: 'web' ("Web Size") serves the gallery's
        # configured derivative tier; 'download' ("High Resolution")
        # resolves to either the 3600px Download Master or, for an
        # entitled Pro photographer who chose it, the true original -- see
        # effective_high_res_mode(). Only 'web'/'download' are ever
        # accepted from a client.
        resolution = as_clean_str(request.data.get('resolution')).lower() or 'download'
        resolution_error = _validate_download_resolution(gallery, resolution)
        if resolution_error:
            return resolution_error

        # Which PhotoSet (if any) this download was scoped to — validated
        # against this gallery before use, both as a real filter and as
        # the activity-log field, so an arbitrary/malformed client-
        # supplied value can neither leak another gallery's set nor crash
        # the query with an invalid UUID.
        photo_set = _get_photo_set(gallery, request.data.get('set_id'))
        # A set that was asked for but isn't one of THIS gallery's (foreign,
        # unknown or malformed id) is refused, never widened to the whole
        # gallery - the client must not receive a different download than
        # the one it asked for.
        if as_clean_str(request.data.get('set_id')) and photo_set is None:
            return error_response('Photo set not found.', 'set_not_found', status.HTTP_404_NOT_FOUND)

        # 1R.6 "Photo Sets Available for Download" -- a whole-gallery
        # download (photo_set is None) is refused outright once restricted
        # to a subset of sets, rather than silently shipping a partial ZIP.
        if not set_is_enabled_for_download(gallery, photo_set):
            return error_response(
                'That part of the gallery is not available for download.', 'set_not_enabled',
                status.HTTP_403_FORBIDDEN,
            )

        # 1R.6 "Limit Photo Downloads" (total, shared by all visitors).
        if download_limit_reached(gallery):
            return error_response(
                f'Download limit reached. Contact {_studio_name(gallery)}.', 'download_limit_reached',
                status.HTTP_403_FORBIDDEN,
            )

        # 5. Selection. asset_ids is validated through a real UUIDField list,
        # exactly like PhotoBulkDeleteSerializer/PhotoReorderSerializer
        # validate similar id lists elsewhere - a malformed UUID must 400, not
        # reach `id__in=...` and raise an uncaught ValidationError/500.
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

        # Same READY-only contract as the public gallery; scoped to THIS gallery.
        assets = list(job_assets(gallery, photo_set, asset_ids))
        if not assets:
            return error_response(
                'No ready photos are available to download.', 'no_media', status.HTTP_400_BAD_REQUEST,
            )
        if size_limit_error(assets):
            return error_response(
                'This selection is too large to package in one download. Please choose a smaller set.',
                'download_too_large', status.HTTP_400_BAD_REQUEST,
            )

        # 6. Reuse an identical job already in flight, otherwise create + queue one.
        normalized_ids = sorted(str(asset_id) for asset_id in asset_ids)
        job = find_reusable_job(
            gallery, photo_set=photo_set, resolution=resolution, asset_ids=normalized_ids, email=email,
        )
        if job is None:
            job = DownloadJob.objects.create(
                gallery=gallery, photo_set=photo_set, resolution=resolution, asset_ids=normalized_ids,
                email=email, pin_verified=pin_verified,
            )
            try:
                prepare_download_job.delay(str(job.id))
            except Exception:
                logger.exception('Could not queue download job %s', job.id)
                job.state = DownloadJob.State.FAILED
                job.error_code = 'prepare_unavailable'
                job.save(update_fields=['state', 'error_code', 'updated_at'])
                return error_response(
                    'We could not start preparing your photos. Please try again in a moment.',
                    'prepare_unavailable', status.HTTP_503_SERVICE_UNAVAILABLE,
                )
            job.refresh_from_db()   # eager mode (local dev/tests) has already finished it

        return Response({
            'job_id': str(job.id),
            'state': job.state,
            'status_url': request.build_absolute_uri(reverse(
                'gallery-download-job-status',
                kwargs={'username': gallery.photographer.username, 'slug': gallery.slug, 'job_id': job.id},
            )),
        }, status=status.HTTP_202_ACCEPTED)


class PublicGalleryDirectDownloadView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/download-all/  - RETIRED.

    Gallery and set downloads are never streamed straight from a request any
    more: POST .../download/ prepares them in the background and the files are
    served from the gated download-jobs endpoints. This route performs no
    gallery lookup, no storage work and no logging; it only tells a stale
    client where the flow went.
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def get(self, request, username, slug):
        return error_response(
            'Gallery downloads are prepared first. Use the Download button to start one.',
            'download_requires_preparation', status.HTTP_410_GONE,
        )


JOB_ERROR_MESSAGES = {
    'no_media': 'No ready photos are available to download.',
    'download_too_large': 'This selection is too large to package in one download.',
    'download_expired': 'This download has expired. Please start it again.',
    'file_missing': 'This download is no longer available. Please prepare it again.',
}
JOB_GENERIC_ERROR = "We couldn't prepare your photos. Please try again."


class DownloadJobGateMixin:
    """
    The checks every download-job endpoint repeats on EVERY request, however
    the caller got the job id: the gallery must be live and downloadable, a
    password-protected gallery needs its unlock session, and the job must
    belong to this gallery. Returns (gallery, job, error Response | None).
    """
    permission_classes = [AllowAny]
    authentication_classes = []
    throttle_classes = [PublicGalleryBrowseThrottle]

    def resolve_job(self, request, username, slug, job_id):
        try:
            gallery = Gallery.objects.select_related('photographer').get(
                Q(expires_at__isnull=True) | Q(expires_at__gt=timezone.now()),
                slug=slug.strip().lower(),
                photographer__username=username.strip().lower(),
                is_published=True,
                is_active=True,
            )
        except Gallery.DoesNotExist:
            return None, None, Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        if not gallery.allow_download:
            return None, None, error_response(
                'Downloads are disabled for this gallery.', 'downloads_disabled', status.HTTP_403_FORBIDDEN,
            )

        if gallery.is_password_protected:
            auth_header = request.META.get('HTTP_AUTHORIZATION', '')
            token = (
                auth_header[len('Bearer '):].strip()
                if auth_header.startswith('Bearer ')
                else request.query_params.get('token', '').strip()
            )
            if not (token and ClientSession.objects.not_expired().filter(
                access_token=token, gallery=gallery
            ).exists()):
                return None, None, error_response(
                    'An active unlocked session is required to download this gallery.',
                    'session_required', status.HTTP_401_UNAUTHORIZED,
                )

        job = DownloadJob.objects.filter(id=job_id, gallery=gallery).select_related('photo_set').first()
        if job is None:
            return None, None, error_response('Download not found.', 'download_not_found', status.HTTP_404_NOT_FOUND)
        return gallery, job, None


class PublicDownloadJobStatusView(DownloadJobGateMixin, APIView):
    """
    GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/
        ?download_token=<from POST .../download-access/>  &token=<gallery unlock token>

    -> { state: preparing | ready | failed, files: [{name, size_bytes, url}] }

    Requires the same download access token as the POST that created the job,
    and that token's email must be the job's: another visitor's token (or
    another gallery's) reads as "not found". When ready, each file's `url` is
    a freshly signed, minutes-long link - poll again for a new one rather
    than keeping an old URL around.
    """

    def get(self, request, username, slug, job_id):
        gallery, job, error = self.resolve_job(request, username, slug, job_id)
        if error:
            return error

        authorization, auth_error = authorize_download(
            gallery, pin=None, download_token=request.query_params.get('download_token'),
        )
        if auth_error:
            return auth_error
        if (authorization.email or None) != (job.email or None):
            return error_response('Download not found.', 'download_not_found', status.HTTP_404_NOT_FOUND)

        job = expire_if_stale(job)
        if job.state == DownloadJob.State.READY and not is_expired(job) and not job_files_exist(job):
            # The row says ready but the stored ZIP is gone: say so now, instead of
            # handing out a link that can only 404.
            mark_file_missing(job)
        if job.state == DownloadJob.State.FAILED:
            return Response({
                'state': 'failed', 'code': job.error_code or 'prepare_failed', 'files': [],
                'error': JOB_ERROR_MESSAGES.get(job.error_code, JOB_GENERIC_ERROR),
            })
        if is_expired(job):
            return Response({
                'state': 'failed', 'code': 'download_expired', 'files': [],
                'error': JOB_ERROR_MESSAGES['download_expired'],
            })
        if job.state == DownloadJob.State.PREPARING:
            return Response({'state': 'preparing', 'files': []})

        files = []
        for index, entry in enumerate(job.files or []):
            url = request.build_absolute_uri(reverse(
                'gallery-download-job-file',
                kwargs={'username': gallery.photographer.username, 'slug': gallery.slug,
                        'job_id': job.id, 'index': index},
            ))
            files.append({
                'name': entry['name'],
                'size_bytes': entry['size_bytes'],
                'url': f'{url}?{urlencode({"file_token": issue_file_token(job, gallery, index)})}',
            })
        return Response({'state': 'ready', 'files': files, 'expires_at': job.expires_at})


class PublicDownloadJobFileView(DownloadJobGateMixin, APIView):
    """
    GET /api/v1/public/{username}/{slug}/download-jobs/{job_id}/files/{index}/
        ?file_token=<signed, minutes-long>  [&token=<gallery unlock token>]

    Streams one prepared ZIP from PRIVATE storage as an attachment. There is
    no way to reach the stored file except through here: the signed file
    token (issued only to a caller holding a valid download token), the live
    gallery gates, the job's own gallery binding and its expiry are all
    checked on every request. The first successful file response writes the
    job's single Download Activity row, with the real attachment filename.
    """

    # Failures a person can fix by preparing the download again. A browser
    # that NAVIGATED to the file URL (an old link, a bookmark, the emailed
    # link) is sent to the download page, which says "link expired" with a
    # button; API/XHR callers keep getting the JSON error.
    FRIENDLY_CODES = {'download_not_found', 'download_expired', 'download_link_expired', 'file_unavailable'}

    def get(self, request, username, slug, job_id, index):
        response = self.serve(request, username, slug, job_id, index)
        code = getattr(response, 'data', {}).get('code') if hasattr(response, 'data') and isinstance(response.data, dict) else None
        if code in self.FRIENDLY_CODES and 'text/html' in request.META.get('HTTP_ACCEPT', ''):
            return HttpResponseRedirect(
                f'{settings.FRONTEND_URL}/g/{username.strip().lower()}/{slug.strip().lower()}/download?link=expired'
            )
        return response

    def serve(self, request, username, slug, job_id, index):
        gallery, job, error = self.resolve_job(request, username, slug, job_id)
        if error:
            return error

        if job.state != DownloadJob.State.READY or is_expired(job):
            return error_response(
                'This download is no longer available. Please start it again.',
                'download_expired', status.HTTP_410_GONE,
            )
        files = job.files or []
        if index >= len(files):
            return error_response('Download not found.', 'download_not_found', status.HTTP_404_NOT_FOUND)
        token_state = file_token_state(request.query_params.get('file_token'), job, gallery, index)
        if token_state == 'mismatch':
            # A genuine link, but for a different job/file: reads as "not found".
            return error_response('Download not found.', 'download_not_found', status.HTTP_404_NOT_FOUND)
        if token_state != 'ok':
            return error_response(
                'This download link has expired. Please try again.',
                'download_link_expired', status.HTTP_403_FORBIDDEN,
            )

        entry = files[index]
        try:
            stored = PrivateMediaStorage().open(entry['storage_path'], 'rb')
        except Exception:
            logger.warning('Stored file for download job %s is missing', job.id)
            mark_file_missing(job)
            return error_response('File unavailable.', 'file_unavailable', status.HTTP_404_NOT_FOUND)

        filename = sanitize_download_filename(entry['name'], fallback='photo-download-1of1.zip')

        # One Download Activity row per genuine download. The ONLY thing collapsed
        # is the browser retrying/resuming the very same prepared job's file
        # moments after it was logged (this job's own latest log, same client
        # address, within DOWNLOAD_RETRY_WINDOW_SECONDS). A different job
        # (another email, set, size or file) is never matched, and a later
        # "Download again" is its own row.
        ip_address = _get_client_ip(request)
        last_log = job.download_log
        is_retry = bool(
            last_log is not None
            and last_log.ip_address == ip_address
            and last_log.created_at >= timezone.now() - timedelta(seconds=DOWNLOAD_RETRY_WINDOW_SECONDS)
        )
        # 1R.6 "Limit Photo Downloads" -- gates only a NEW Download Activity
        # row, never the harmless retry/resume above (same job, same IP,
        # within the window) that collapses into the one already logged.
        if not is_retry and download_limit_reached(gallery):
            return error_response(
                f'Download limit reached. Contact {_studio_name(gallery)}.', 'download_limit_reached',
                status.HTTP_403_FORBIDDEN,
            )

        if not is_retry:
            job.download_log = DownloadLog.objects.create(
                gallery=gallery,
                email=job.email,
                ip_address=ip_address,
                download_type=DownloadLog.DownloadType.GALLERY,
                resolution=job.resolution,
                pin_verified=job.pin_verified,
                photo_set=job.photo_set,
                filename=filename,
                photo_count=entry.get('photo_count'),
            )
            job.save(update_fields=['download_log', 'updated_at'])

        return FileResponse(stored, as_attachment=True, filename=filename, content_type='application/zip')


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
    

class PublicPhotoDownloadView(PinGuessThrottledMixin, APIView):
    """
    GET /api/v1/public/{username}/{slug}/photo/{photo_id}/download/
    GET .../download/?token=<unlock token>&download_token=<download access token>
                     &resolution=web|download

    'download' ("High Resolution") resolves to the 3600px Download Master
    or, for an entitled Pro photographer who chose it, the true original --
    see _get_client_download_source()/effective_high_res_mode(). A raw
    resolution=original is rejected with a 400, never served.

    Streams ONE file (image OR video — despite the URL saying "photo",
    nothing here restricts media_type; PublicMediaAssetSerializer.download_url
    points here for both) with a forced Content-Disposition: attachment
    header. This is the only reliable way to force a "Save As" prompt
    across browsers and storage backends, so it's what download_url
    always points to — never a bare S3/disk URL.

    Authorization is entirely server-side. A client chooses Download in the
    UI, which first calls POST .../download-access/ (email + PIN when the
    gallery needs them) and then points this plain <a href> GET at the file
    with the short-lived `download_token` it got back — so email/PIN are
    asked once per session, not once per photo, and the PIN never sits in a
    URL. The email travels inside that token and is recorded on the
    DownloadLog row. A raw `?pin=` is still accepted (and held to the tight
    brute-force throttle) for scripted callers. A gallery with no PIN stays
    reachable without a token; that anonymous download logs email=None.
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

        authorization, auth_error = authorize_download(
            gallery,
            pin=request.query_params.get('pin'),
            download_token=request.query_params.get('download_token'),
        )
        if auth_error:
            return auth_error

        try:
            asset = MediaAsset.objects.get(id=photo_id, gallery=gallery)
        except MediaAsset.DoesNotExist:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)

        resolution = request.query_params.get('resolution', 'download').strip().lower()
        resolution_error = _validate_download_resolution(gallery, resolution)
        if resolution_error:
            return resolution_error

        # 1R.6 "Photo Sets Available for Download" -- a single-photo/video
        # download is refused the same way a ZIP covering it would be.
        if not asset_set_is_enabled_for_download(gallery, asset):
            return Response(
                {'error': 'That photo is not available for download.', 'code': 'set_not_enabled'},
                status=status.HTTP_403_FORBIDDEN,
            )

        # 1R.6 "Limit Photo Downloads" (total, shared by all visitors).
        if download_limit_reached(gallery):
            return Response(
                {
                    'error': f'Download limit reached. Contact {_studio_name(gallery)}.',
                    'code': 'download_limit_reached',
                },
                status=status.HTTP_403_FORBIDDEN,
            )

        # 'web' ("Web Size") serves the gallery's configured derivative
        # tier for an image, the H.264 playback MP4 for a video -- over
        # re-serving the original. Falls back to the original when no
        # such derivative exists yet (still processing).
        source_field = asset.original_file
        if resolution == 'web':
            source_field = _resolve_web_source(asset, web_px_for_gallery(gallery))
            if source_field is asset.original_file:
                resolution = 'original'
        elif resolution == 'download':
            source_field, resolution = _get_client_download_source(asset, gallery)

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
            email=authorization.email,
            ip_address=_get_client_ip(request),
            media_asset=asset,
            download_type=(
                DownloadLog.DownloadType.VIDEO
                if asset.media_type == MediaAsset.MediaType.VIDEO
                else DownloadLog.DownloadType.PHOTO
            ),
            resolution=resolution,
            pin_verified=authorization.pin_verified,
            filename=download_filename,
        )

        response = FileResponse(
            source_field,
            as_attachment=True,
            filename=download_filename,
            content_type='application/octet-stream',
        )
        return response


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
        # A photographer who turned their public portfolio off (Settings →
        # Privacy) gets the same 404 as a nonexistent one, so the page can't be
        # used to learn that the account exists. Individual gallery links are
        # separate routes and keep following each gallery's own settings.
        photographer = get_object_or_404(
            User.objects.filter(
                is_active=True, is_staff=False, is_superuser=False, portfolio_public=True
            ),
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
            .select_related('cover_photo', 'photographer')
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
