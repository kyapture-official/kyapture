# C:/Users/LENOVO/Desktop/kyapture/backend/apps/photos/views.py
import logging
import os
from decimal import Decimal
from django.db import transaction, IntegrityError
from django.core.exceptions import ValidationError as DjangoValidationError
from django.db.models import Count, Q
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.exceptions import ValidationError as DRFValidationError
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import UserRateThrottle
from rest_framework.views import APIView
from .tasks import process_photo_asset, process_video_asset
from PIL import Image as PILImage
from PIL.ImageOps import exif_transpose

from apps.core.utils import get_user_subscription_metrics, get_insertion_order, probe_video_duration, strip_exif_gps
from apps.subscriptions.entitlements import (
    STORAGE_LIMIT_REACHED, storage_fits, storage_quota_violation, video_quota_violation,
)
from apps.subscriptions.upload_limits import (
    apply_pillow_pixel_guard, check_image_pixels, check_size, get_upload_limits,
    image_too_many_pixels,
)
from apps.galleries.models import Gallery
from .models import MediaAsset, PhotoSet
from .purge import purge_assets, purge_photo_set
from .serializers import (
    MediaAssetSerializer,
    MediaAssetImageUploadSerializer,
    MediaAssetVideoUploadSerializer,
    PhotoBulkDeleteSerializer,
    PhotoReorderSerializer,
    PhotoSetSerializer,
    PhotoSetWriteSerializer,
    PhotoSetReorderSerializer,
    PhotoSetAssignSerializer,
    VideoPreflightSerializer,
)


logger = logging.getLogger(__name__)


def _safe_text_field(value, max_length):
    """
    Phase 4 (upload hardening): the browser-supplied filename (and any
    title derived from it) is untrusted free text with no length limit
    of its own — MediaAsset.original_name/title do have DB-level
    max_length constraints, and a name longer than that previously
    reached Postgres as a raw INSERT, surfacing as an unhandled
    DataError string via this view's existing broad exception handler
    rather than a clean, predictable outcome. Strips embedded NUL bytes
    (which Postgres' text/varchar columns reject outright with their own
    raw driver error) and truncates to fit, rather than erroring the
    whole upload over what is purely cosmetic display data.
    """
    if not value:
        return value
    cleaned = value.replace('\x00', '')
    return cleaned[:max_length]


def _split_by_storage(metrics, image_files, video_files):
    """(images that fit, videos that fit, files refused) for the plan's storage; see storage_fits()."""
    files = list(image_files) + list(video_files)
    fits = storage_fits(metrics, [f.size for f in files])
    split = len(image_files)
    return (
        [f for f, ok in zip(image_files, fits[:split]) if ok],
        [f for f, ok in zip(video_files, fits[split:]) if ok],
        [f for f, ok in zip(files, fits) if not ok],
    )


def _split_by_file_limits(image_files, video_files, limits):
    """
    (images within the limits, videos within the limits, refusals) for the admin-set
    per-file limits. Cheapest check first: the size needs no file read; the pixel
    count reads only the image header. A refused file never reaches storage or
    processing, and the rest of the batch carries on.
    """
    rejected = []
    images = []
    for f in image_files:
        refusal = check_size(f, 'image', limits) or check_image_pixels(f, limits)
        if refusal:
            rejected.append(refusal)
        else:
            images.append(f)
    videos = []
    for f in video_files:
        refusal = check_size(f, 'video', limits)
        if refusal:
            rejected.append(refusal)
        else:
            videos.append(f)
    return images, videos, rejected


def _storage_refusal(metrics, refused_files):
    return storage_quota_violation(metrics, len(refused_files), sum(f.size for f in refused_files))


class PhotoListUploadView(APIView):
    """
    GET  /api/v1/photos/{gallery_slug}/ - Lists all media assets inside an active gallery.
    POST /api/v1/photos/{gallery_slug}/upload/ - Processes bulk image streams securely.
    
    Accepts two independent multipart field keys in the same request:
    - 'image' — one or many image files (JPEG/PNG/WEBP/TIFF)
    - 'video' — one or many video files (MP4/MOV/M4V)
    Either or both may be present, so a single mixed drag-and-drop batch
    (photos + videos together) uploads in one call. Note: within a mixed
    batch, all images are assigned display order before all videos,
    regardless of original drop order — a minor cosmetic quirk of routing
    by form field, fixable afterward via drag-reorder in the grid.
    """
    parser_classes = [MultiPartParser, FormParser]
    permission_classes = [IsAuthenticated]


    def get_gallery(self, slug, user):
        """Retrieves an active gallery scoped strictly to the requesting user."""
        try:
            return Gallery.objects.get(slug=slug, photographer=user, is_active=True)
        except Gallery.DoesNotExist:
            return None

    def get(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        photo_set_id = request.query_params.get('set', '').strip()
        if photo_set_id:
            try:
                photo_set = PhotoSet.objects.get(id=photo_set_id, gallery=gallery)
            except (PhotoSet.DoesNotExist, ValueError, DjangoValidationError):
                return Response({'error': 'Set not found in this gallery.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            photo_set = None

        # Fetches unified assets (both photos and videos) sorted by manual display sequence
        assets = MediaAsset.objects.filter(gallery=gallery).order_by('order', 'created_at')
        if photo_set is not None:
            assets = assets.filter(photo_set=photo_set)
        serializer = MediaAssetSerializer(assets, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        raw_set_id = request.data.get('set_id', '').strip()
        if raw_set_id:
            try:
                photo_set = PhotoSet.objects.get(id=raw_set_id, gallery=gallery)
            except (PhotoSet.DoesNotExist, ValueError, DjangoValidationError):
                return Response({'error': 'Set not found in this gallery.'}, status=status.HTTP_404_NOT_FOUND)
        else:
            photo_set = PhotoSet.objects.filter(gallery=gallery).order_by('order', 'created_at').first()
            if photo_set is None:
                return Response(
                    {'error': 'No default set is available for this gallery.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

        image_files = request.FILES.getlist('image')
        video_files = request.FILES.getlist('video')

        if not image_files and not video_files:
            return Response(
                {"error": "No files provided.", "details": {"image": ["No image or video file provided."]}},
                status=status.HTTP_400_BAD_REQUEST
            )

        # Per-file safety limits (admin-edited, read now): before the plan check, ffprobe,
        # storage or any decoding. Refused files are reported; the others carry on.
        limits = apply_pillow_pixel_guard(get_upload_limits())
        image_files, video_files, limit_rejected = _split_by_file_limits(image_files, video_files, limits)
        if not image_files and not video_files:
            return Response({**limit_rejected[0], 'rejected': limit_rejected}, status=status.HTTP_400_BAD_REQUEST)

        photographer = request.user
        metrics = get_user_subscription_metrics(photographer)
        metered = not (photographer.is_superuser or photographer.is_staff)

        # Files the plan's storage cannot take; reported back, never stored.
        storage_refused = []
        if metered:
            # Check 0: plan has no video at all (video_minutes == 0) — refuse
            # before the files are probed or stored, so nothing uploads partially.
            if video_files and not metrics["allow_video"]:
                return Response(video_quota_violation(metrics, 0), status=status.HTTP_403_FORBIDDEN)

            # Storage (GB) is the only photo cap; there is no per-collection photo limit.
            # A mixed batch uploads what fits; nothing fitting is a plain 403.
            image_files, video_files, storage_refused = _split_by_storage(metrics, image_files, video_files)
            if not image_files and not video_files:
                return Response(_storage_refusal(metrics, storage_refused), status=status.HTTP_403_FORBIDDEN)

        # Video minutes: measure every video with ffprobe now, and refuse the
        # whole batch if used + new would pass the plan's limit. Durations are
        # kept for the row so the stored value is the one that was checked.
        video_durations = {}
        for file_data in video_files:
            # Extension / signature / size checks first: ffprobe only ever sees a plausible video.
            checker = MediaAssetVideoUploadSerializer(
                data={'video': file_data}, context={'request': request, 'upload_limits': limits})
            if not checker.is_valid():
                return Response(
                    {"error": "Upload validation failed.", "details": checker.errors, "code": "upload_validation_failed"},
                    status=status.HTTP_400_BAD_REQUEST,
                )
            seconds = probe_video_duration(file_data)
            if seconds is None:
                return Response({
                    "error": "This video could not be read.",
                    "code": "video_unreadable",
                    "message": f"{file_data.name} is not a valid video file.",
                }, status=status.HTTP_400_BAD_REQUEST)
            video_durations[id(file_data)] = seconds
        if video_files and metered:
            violation = video_quota_violation(metrics, sum(video_durations.values()))
            if violation:
                return Response(violation, status=status.HTTP_403_FORBIDDEN)

# ─── ENFORCEMENT CLEARED ───
        uploaded_assets = []

        # Atomic transaction: If database saving fails, the batch rolls back safely
        try:
            with transaction.atomic():
                if metered:
                    # The decision that counts: under a lock on the account's own row, against
                    # usage read now, so two uploads running at once cannot both claim the
                    # same free space. The check above only spares an ffprobe for a full account.
                    type(photographer).objects.select_for_update().only('pk').get(pk=photographer.pk)
                    image_files, video_files, late_refused = _split_by_storage(
                        get_user_subscription_metrics(photographer), image_files, video_files)
                    storage_refused += late_refused
                    if not image_files and not video_files:
                        return Response(
                            _storage_refusal(get_user_subscription_metrics(photographer), storage_refused),
                            status=status.HTTP_403_FORBIDDEN,
                        )
                for file_data in image_files:
                    # Validate image size and magic-byte security first
                    serializer = MediaAssetImageUploadSerializer(
                        data={'image': file_data, 'title': request.data.get('title', '')},
                        context={'request': request, 'gallery': gallery, 'upload_limits': limits}
                    )
                    serializer.is_valid(raise_exception=True)
                    
                    title = request.data.get('title', '').strip()
                    if not title:
                        title = os.path.splitext(file_data.name)[0]

                    clean_file = strip_exif_gps(file_data)

                    clean_file.seek(0)
                    with PILImage.open(clean_file) as img:
                        img = exif_transpose(img)
                        width, height = img.size
                    clean_file.seek(0)

                    # Create the raw asset under 'pending' status immediately
                    asset = MediaAsset.objects.create(
                        gallery=gallery,
                        media_type=MediaAsset.MediaType.IMAGE,
                        original_file=clean_file,
                        original_name=_safe_text_field(file_data.name, 255),
                        file_size=clean_file.size,
                        title=_safe_text_field(title, 200),
                        width=width,                
                        height=height,
                        processing_status=MediaAsset.ProcessingStatus.PENDING,
                        order=get_insertion_order(gallery.id),
                        photo_set=photo_set,
                    )
                    
                    # Dispatch Celery background task for WebP conversions and BlurHash encoding
                    transaction.on_commit(lambda a_id=asset.id: process_photo_asset.delay(str(a_id)))
                    uploaded_assets.append(asset)
                    
                    # ── Videos ──
                for file_data in video_files:
                    serializer = MediaAssetVideoUploadSerializer(
                        data={'video': file_data, 'title': request.data.get('title', '')},
                        context={'request': request, 'gallery': gallery, 'upload_limits': limits}
                    )
                    serializer.is_valid(raise_exception=True)

                    title = request.data.get('title', '').strip()
                    if not title:
                        title = os.path.splitext(file_data.name)[0]

                    asset = MediaAsset.objects.create(
                        gallery=gallery,
                        media_type=MediaAsset.MediaType.VIDEO,
                        original_file=file_data,
                        original_name=_safe_text_field(file_data.name, 255),
                        file_size=file_data.size,
                        title=_safe_text_field(title, 200),
                        duration=video_durations[id(file_data)],
                        processing_status=MediaAsset.ProcessingStatus.PENDING,
                        order=get_insertion_order(gallery.id),
                        photo_set=photo_set,
                    )

                    transaction.on_commit(lambda a_id=asset.id: process_video_asset.delay(str(a_id)))
                    uploaded_assets.append(asset)
                    

        except DRFValidationError as exc:
            # Validation details are intentionally limited to serializer
            # messages.  Never stringify an arbitrary exception here: file
            # storage, database, and OS errors can contain credentials,
            # absolute paths, or provider internals (F-29).
            return Response(
                {
                    "error": "Upload validation failed.",
                    "details": exc.detail,
                    "code": "upload_validation_failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except PILImage.DecompressionBombError:
            # Pillow's own guard (the pixel limit) fired somewhere after the header check.
            refusal = image_too_many_pixels('', limits)
            return Response({**refusal, 'rejected': limit_rejected + [refusal]}, status=status.HTTP_400_BAD_REQUEST)
        except IntegrityError:
            logger.exception("Upload transaction failed due to a database integrity error.")
            return Response(
                {
                    "error": "Upload could not be saved.",
                    "code": "upload_save_failed",
                },
                status=status.HTTP_400_BAD_REQUEST,
            )
        except Exception:
            logger.exception("Unexpected upload processing failure for gallery %s.", gallery.slug)
            return Response(
                {
                    "error": "Upload could not be processed.",
                    "code": "upload_processing_error",
                },
                status=status.HTTP_500_INTERNAL_SERVER_ERROR,
            )

        # Return 202 Accepted immediately so David's frontend has the IDs to render skeleton loaders
        assets_data = MediaAssetSerializer(uploaded_assets, many=True, context={'request': request}).data
        if not storage_refused and not limit_rejected:
            return Response(assets_data, status=status.HTTP_202_ACCEPTED)
        # Part of the batch was refused: the uploaded rows plus a report of the rest.
        body = {'uploaded': assets_data}
        if limit_rejected:
            body['rejected'] = limit_rejected  # over a per-file size or pixel limit
        if storage_refused:
            body['refused'] = [{'name': f.name, 'size_bytes': f.size, 'code': STORAGE_LIMIT_REACHED} for f in storage_refused]
            body['storage'] = _storage_refusal(get_user_subscription_metrics(photographer), storage_refused)
        return Response(body, status=status.HTTP_202_ACCEPTED)


class VideoPreflightRateThrottle(UserRateThrottle):
    scope = 'video_preflight'


class VideoPreflightView(APIView):
    """
    POST /api/v1/photos/video-preflight/ - "would these videos fit my plan?",
    asked by the upload page BEFORE any file is sent.

    Body: {"video_count": N, "durations": [seconds, ...]} (the browser's own
    reading of each video; see VideoPreflightSerializer). Answers 200
    {"allowed": true}, or the SAME 403 body the upload gives
    (video_not_in_plan / video_minutes_exceeded with plan_limit_minutes and
    used_minutes), from the same video_quota_violation rule. It only ever
    reads the signed-in user's own usage. The client lengths are untrusted, so
    this is advice: the upload still measures every video with ffprobe and
    makes the authoritative decision.
    """
    permission_classes = [IsAuthenticated]
    throttle_classes = [VideoPreflightRateThrottle]

    def post(self, request):
        serializer = VideoPreflightSerializer(data=request.data)
        if not serializer.is_valid():
            return Response(
                {"error": "Invalid video details.", "code": "invalid_preflight", "details": serializer.errors},
                status=status.HTTP_400_BAD_REQUEST,
            )
        user = request.user
        if not (user.is_superuser or user.is_staff):
            violation = video_quota_violation(
                get_user_subscription_metrics(user), sum(serializer.validated_data['durations']),
            )
            if violation:
                return Response(violation, status=status.HTTP_403_FORBIDDEN)
        return Response({"allowed": True}, status=status.HTTP_200_OK)


class PhotoBatchStatusView(APIView):
    """
    GET /api/v1/photos/{gallery_slug}/status/?ids=<uuid>,<uuid>,...

    Phase 2 (large-gallery performance): replaces the dashboard's previous
    per-asset polling pattern — N parallel GET /photo/{id}/ requests,
    once per still-processing asset, every 3 seconds — with exactly ONE
    request per poll tick regardless of how many assets are mid-processing
    (a big batch upload could mean dozens of videos processing at once).
    Same tenant scoping as every other view here: a gallery that isn't
    this photographer's returns 404, and any requested id that doesn't
    belong to THIS gallery is silently excluded from the response,
    consistent with PhotoBulkDeleteView's existing "unknown ids ignored"
    behavior.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request, gallery_slug):
        try:
            gallery = Gallery.objects.get(
                slug=gallery_slug, photographer=request.user, is_active=True
            )
        except Gallery.DoesNotExist:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        raw_ids = request.query_params.get('ids', '')
        requested_ids = [v.strip() for v in raw_ids.split(',') if v.strip()]
        if not requested_ids:
            return Response([], status=status.HTTP_200_OK)

        # Defensive cap — this is a polling endpoint for assets currently
        # in flight, not a general listing endpoint; no legitimate poll
        # tick needs more than a couple hundred ids at once.
        requested_ids = requested_ids[:200]

        assets = MediaAsset.objects.filter(gallery=gallery, id__in=requested_ids)
        serializer = MediaAssetSerializer(assets, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class PhotoDetailView(APIView):
    """
    GET    /api/v1/photos/photo/{photo_id}/ - Retrieve metadata of a single media asset.
    DELETE /api/v1/photos/photo/{photo_id}/ - PERMANENTLY delete an asset: its row
           and every stored file (original, Download Master, derivatives, video
           files), purged after commit by an idempotent task. Not recoverable.
    
    NOTE: Enforces IsAuthenticated only. This ensures photographers with expired or
    frozen accounts can always call DELETE to clean up space and regain storage compliance.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, photo_id, user):
        """Fetch asset using double join lookup: MediaAsset -> Gallery -> User"""
        try:
            return MediaAsset.objects.select_related('gallery').get(
                id=photo_id,
                gallery__photographer=user,
                gallery__is_active=True
            )
        except MediaAsset.DoesNotExist:
            return None

    def get(self, request, photo_id):
        asset = self.get_object(photo_id, request.user)
        if not asset:
            return Response({'error': 'Media asset not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = MediaAssetSerializer(asset, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, photo_id):
        asset = self.get_object(photo_id, request.user)
        if not asset:
            return Response({'error': 'Media asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        purge_assets(asset.gallery, MediaAsset.objects.filter(pk=asset.pk))
        return Response({'message': 'Media asset deleted successfully.'}, status=status.HTTP_200_OK)


class PhotoBulkDeleteView(APIView):
    """
    POST /api/v1/photos/{gallery_slug}/delete-bulk/

    Deletes multiple MediaAsset database rows in a single API request.
    Scopes selection strictly to the authorized photographer and active gallery 
    to prevent cross-tenant enumeration deletion attacks.
    """
    permission_classes = [IsAuthenticated]

    def post(self, request, gallery_slug):
        gallery = get_object_or_404(
            Gallery, 
            slug=gallery_slug, 
            photographer=request.user, 
            is_active=True
        )

        serializer = PhotoBulkDeleteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        photo_ids = serializer.validated_data['photo_ids']

        # Restrict the QuerySet scope strictly to this photographer's target gallery.
        # Unknown or forged IDs belong to other users will be silently ignored.
        queryset = MediaAsset.objects.filter(gallery=gallery, id__in=photo_ids)

        # Permanent delete: rows now, every stored file after commit (apps/photos/purge.py);
        # the cover falls back to the next READY photo if it was among them.
        deleted_count = purge_assets(gallery, queryset)

        return Response({'deleted_count': deleted_count}, status=status.HTTP_200_OK)


class PhotoReorderView(APIView):
    """
    PATCH /api/v1/photos/{gallery_slug}/reorder/

    Accepts the complete array of asset UUIDs and reassigns clean, sequential 
    decimal 'order' values (1.00, 2.00, 3.00...) to match David's frontend sequence.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, gallery_slug):
        gallery = get_object_or_404(
            Gallery, 
            slug=gallery_slug, 
            photographer=request.user, 
            is_active=True
        )

        serializer = PhotoReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data['ordered_ids']

        # Map assets belonging solely to this specific gallery in a dictionary for O(1) lookups
        assets_by_id = {
            str(asset.id): asset
            for asset in MediaAsset.objects.filter(gallery=gallery, id__in=ordered_ids)
        }

        if not assets_by_id:
            return Response(
                {'error': 'None of the supplied photo IDs belong to this gallery.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_assets = []
        position = Decimal('1.0')
        
        for photo_id in ordered_ids:
            asset = assets_by_id.get(str(photo_id))
            if asset is None:
                continue  # Skip any invalid or forged IDs silently
            asset.order = position
            updated_assets.append(asset)
            position += Decimal('1.0')

        # Execute bulk_update inside a transaction block to write to Postgres in a single hit
        with transaction.atomic():
            MediaAsset.objects.bulk_update(updated_assets, ['order'])

        return Response({
            'success': True,
            'ordered_ids': [str(a.id) for a in updated_assets],
        }, status=status.HTTP_200_OK)


# ─────────────────────────────────────────────────────────────
# PHOTO SETS (Phase 3 — client experience)
# ─────────────────────────────────────────────────────────────

class PhotoSetListCreateView(APIView):
    """
    GET  /api/v1/photos/{gallery_slug}/sets/  — list this gallery's sets,
         each annotated with its live READY+unsorted-agnostic photo count
         in the SAME query (no N+1: one Count() per set via GROUP BY, not
         one query per set).
    POST /api/v1/photos/{gallery_slug}/sets/  — create a new set, appended
         to the end of the gallery's set order.
    """
    permission_classes = [IsAuthenticated]

    def get_gallery(self, slug, user):
        try:
            return Gallery.objects.get(slug=slug, photographer=user, is_active=True)
        except Gallery.DoesNotExist:
            return None

    def get(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        sets = (
            PhotoSet.objects
            .filter(gallery=gallery)
            .annotate(photo_count=Count('assets'))
            .order_by('order', 'created_at')
        )
        serializer = PhotoSetSerializer(sets, many=True)
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PhotoSetWriteSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        last_set = PhotoSet.objects.filter(gallery=gallery).order_by('-order').first()
        next_order = (last_set.order + Decimal('1.0')) if last_set else Decimal('1.0')

        try:
            photo_set = PhotoSet.objects.create(
                gallery=gallery,
                order=next_order,
                **serializer.validated_data
            )
        except IntegrityError:
            return Response(
                {'error': 'A set with this name already exists in this gallery.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        photo_set.photo_count = 0
        return Response(PhotoSetSerializer(photo_set).data, status=status.HTTP_201_CREATED)


class PhotoSetDetailView(APIView):
    """
    PATCH  /api/v1/photos/{gallery_slug}/sets/{set_id}/  — rename.
    DELETE /api/v1/photos/{gallery_slug}/sets/{set_id}/  — PERMANENTLY delete the
           set AND the photos in it (rows + every stored file). The last
           remaining set cannot be deleted.
    """
    permission_classes = [IsAuthenticated]

    def get_gallery(self, slug, user):
        try:
            return Gallery.objects.get(slug=slug, photographer=user, is_active=True)
        except Gallery.DoesNotExist:
            return None

    def get_set(self, gallery, set_id):
        try:
            return PhotoSet.objects.get(id=set_id, gallery=gallery)
        except PhotoSet.DoesNotExist:
            return None

    def patch(self, request, gallery_slug, set_id):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        photo_set = self.get_set(gallery, set_id)
        if not photo_set:
            return Response({'error': 'Set not found.'}, status=status.HTTP_404_NOT_FOUND)

        serializer = PhotoSetWriteSerializer(photo_set, data=request.data, partial=True)
        serializer.is_valid(raise_exception=True)
        try:
            serializer.save()
        except IntegrityError:
            return Response(
                {'error': 'A set with this name already exists in this gallery.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        photo_set.photo_count = photo_set.assets.count()
        return Response(PhotoSetSerializer(photo_set).data, status=status.HTTP_200_OK)

    def delete(self, request, gallery_slug, set_id):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        with transaction.atomic():
            sets = list(
                PhotoSet.objects.select_for_update()
                .filter(gallery=gallery)
                .order_by('order', 'created_at')
            )
            photo_set = next((item for item in sets if str(item.id) == str(set_id)), None)
            if photo_set is None:
                return Response({'error': 'Set not found.'}, status=status.HTTP_404_NOT_FOUND)
            if len(sets) == 1:
                return Response(
                    {'error': 'The final remaining set cannot be deleted.'},
                    status=status.HTTP_400_BAD_REQUEST,
                )

            deleted_photos = purge_photo_set(gallery, photo_set)
        return Response(
            {'message': 'Set deleted successfully.', 'deleted_photos': deleted_photos},
            status=status.HTTP_200_OK,
        )


class PhotoSetReorderView(APIView):
    """
    PATCH /api/v1/photos/{gallery_slug}/sets/reorder/

    Same fractional-decimal renumbering pattern as PhotoReorderView, one
    level up (sets instead of photos).
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, gallery_slug):
        gallery = get_object_or_404(
            Gallery, slug=gallery_slug, photographer=request.user, is_active=True
        )

        serializer = PhotoSetReorderSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        ordered_ids = serializer.validated_data['ordered_ids']

        sets_by_id = {
            str(s.id): s
            for s in PhotoSet.objects.filter(gallery=gallery, id__in=ordered_ids)
        }
        if not sets_by_id:
            return Response(
                {'error': 'None of the supplied set IDs belong to this gallery.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        updated_sets = []
        position = Decimal('1.0')
        for set_id in ordered_ids:
            photo_set = sets_by_id.get(str(set_id))
            if photo_set is None:
                continue
            photo_set.order = position
            updated_sets.append(photo_set)
            position += Decimal('1.0')

        with transaction.atomic():
            PhotoSet.objects.bulk_update(updated_sets, ['order'])

        return Response({
            'success': True,
            'ordered_ids': [str(s.id) for s in updated_sets],
        }, status=status.HTTP_200_OK)


class PhotoSetAssignView(APIView):
    """
    PATCH /api/v1/photos/{gallery_slug}/move/
    Body: { "set_id": "<uuid>" | null, "photo_ids": ["<uuid>", ...] }

    Moves the given photos into the given set in one bulk write. set_id
    of null moves them OUT of whatever set they're currently in (back to
    "unsorted"). Both the set and every photo are scoped strictly to this
    gallery — an id from another gallery/tenant is silently excluded, the
    same "unknown ids ignored" convention PhotoBulkDeleteView/PhotoReorderView
    already use.
    """
    permission_classes = [IsAuthenticated]

    def patch(self, request, gallery_slug):
        gallery = get_object_or_404(
            Gallery, slug=gallery_slug, photographer=request.user, is_active=True
        )

        serializer = PhotoSetAssignSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        set_id = serializer.validated_data['set_id']
        photo_ids = serializer.validated_data['photo_ids']

        target_set = None
        if set_id is not None:
            try:
                target_set = PhotoSet.objects.get(id=set_id, gallery=gallery)
            except PhotoSet.DoesNotExist:
                return Response(
                    {'error': 'Set not found in this gallery.'},
                    status=status.HTTP_404_NOT_FOUND
                )

        updated_count = MediaAsset.objects.filter(
            gallery=gallery, id__in=photo_ids
        ).update(photo_set=target_set)

        return Response({
            'success': True,
            'updated_count': updated_count,
            'set_id': str(target_set.id) if target_set else None,
        }, status=status.HTTP_200_OK)


class PhotoFavoriteView(APIView):
    """
    PUT /api/v1/photos/photo/{photo_id}/favorite/   { "is_favorite": true | false }

    The PHOTOGRAPHER's own favorite mark (the heart on a workspace tile) - it
    never touches the collection cover or visitors' favorites. Idempotent.
    Owner-only: another photographer's (or a trashed gallery's) photo id is a 404.
    """
    permission_classes = [IsAuthenticated]

    def put(self, request, photo_id):
        try:
            asset = MediaAsset.objects.select_related('gallery').get(
                id=photo_id, gallery__photographer=request.user, gallery__is_active=True,
            )
        except MediaAsset.DoesNotExist:
            return Response({'error': 'Media asset not found.'}, status=status.HTTP_404_NOT_FOUND)

        value = request.data.get('is_favorite')
        if not isinstance(value, bool):
            return Response(
                {'error': 'is_favorite must be true or false.', 'code': 'invalid_is_favorite'},
                status=status.HTTP_400_BAD_REQUEST,
            )
        if asset.is_favorite != value:
            asset.is_favorite = value
            asset.favorited_at = timezone.now() if value else None
            asset.save(update_fields=['is_favorite', 'favorited_at', 'updated_at'])
        return Response(MediaAssetSerializer(asset, context={'request': request}).data, status=status.HTTP_200_OK)


class PhotographerFavoritesView(APIView):
    """
    GET /api/v1/photos/favorites/all/?page=N

    Every photo the signed-in photographer has marked as a favorite, across
    their (non-trashed) collections, newest favorite first. Powers the
    dashboard's Favorites page.
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        from apps.core.pagination import StandardResultsSetPagination

        favorites = (
            MediaAsset.objects
            .filter(gallery__photographer=request.user, gallery__is_active=True, is_favorite=True)
            .select_related('gallery')
            .order_by('-favorited_at', '-created_at')
        )
        paginator = StandardResultsSetPagination()
        page = paginator.paginate_queryset(favorites, request, view=self)
        rows = MediaAssetSerializer(page, many=True, context={'request': request}).data
        for row, asset in zip(rows, page):
            row['gallery_slug'] = asset.gallery.slug
            row['gallery_title'] = asset.gallery.title
        return paginator.get_paginated_response(rows)
