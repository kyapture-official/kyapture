# C:\Users\LENOVO\Desktop\kyapture\backend\apps\photos\views.py

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.core.permissions import IsSubscribed
from apps.core.utils import get_user_subscription_metrics
from apps.galleries.models import Gallery
from .models import MediaAsset
from .serializers import MediaAssetSerializer, MediaAssetImageUploadSerializer


class PhotoListUploadView(APIView):
    """
    GET  /api/v1/photos/{gallery_slug}/ - Lists all media assets inside an active gallery.
    POST /api/v1/photos/{gallery_slug}/upload/ - Processes bulk image streams securely (Subscription Gated).
    """
    parser_classes = [MultiPartParser, FormParser]

    def get_permissions(self):
        """
        Enforce IsSubscribed strictly on POST requests (Resource Allocation).
        Allows expired photographers to fetch existing assets via GET, 
        but blocks uploads with an immediate 403 Forbidden.
        """
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsSubscribed()]
        return [IsAuthenticated()]

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

        # Fetches unified assets (both photos and videos) sorted by manual display sequence
        assets = MediaAsset.objects.filter(gallery=gallery).order_by('order', 'created_at')
        serializer = MediaAssetSerializer(assets, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve file list from the 'image' form-data key
        files = request.FILES.getlist('image')
        if not files:
            return Response({"image": ["No image file provided."]}, status=status.HTTP_400_BAD_REQUEST)

        photographer = request.user

        # ─── BATCH-LEVEL GATING (O(1) Database Efficiency) ───
        metrics = get_user_subscription_metrics(photographer)

        if not (photographer.is_superuser or photographer.is_staff):
            # Check 1: Max Media Assets per Gallery
            current_assets_in_gallery = MediaAsset.objects.filter(gallery=gallery).count()
            projected_assets_count = current_assets_in_gallery + len(files)
            
            if projected_assets_count > metrics["max_photos_per_gallery"]:
                return Response({
                    "error": "Photo limit reached for this gallery on your plan.",
                    "code": "photo_limit_reached",
                    "current_count": current_assets_in_gallery,
                    "batch_count": len(files),
                    "plan_limit": metrics["max_photos_per_gallery"],
                    "message": f"Uploading these {len(files)} assets would exceed your plan's maximum of {metrics['max_photos_per_gallery']} assets per gallery."
                }, status=status.HTTP_400_BAD_REQUEST)

            # Check 2: Total Plan Storage footprint (Pre-calculate total batch size)
            total_batch_size_bytes = sum(f.size for f in files)
            projected_storage_bytes = metrics["current_total_storage_bytes"] + total_batch_size_bytes
            
            if projected_storage_bytes > metrics["storage_bytes_limit"]:
                allowed_gb = metrics["storage_bytes_limit"] / (1024 ** 3)
                current_mb = metrics["current_total_storage_bytes"] / (1024 ** 2)
                batch_mb = total_batch_size_bytes / (1024 ** 2)
                return Response({
                    "error": "Storage quota limit exceeded.",
                    "code": "storage_limit_reached",
                    "current_storage_mb": f"{current_mb:.1f}",
                    "upload_batch_mb": f"{batch_mb:.1f}",
                    "plan_limit_gb": f"{allowed_gb:.1f}",
                    "message": f"This upload of {batch_mb:.1f} MB would push your account past your {allowed_gb:.1f} GB plan storage limit."
                }, status=status.HTTP_400_BAD_REQUEST)

        # ─── ENFORCEMENT CLEARED ───
        uploaded_assets = []

        # Atomic transaction: If any single image processing fails, the entire batch rolls back
        try:
            with transaction.atomic():
                for file_data in files:
                    serializer = MediaAssetImageUploadSerializer(
                        data={'image': file_data, 'title': request.data.get('title', '')},
                        context={'request': request, 'gallery': gallery}
                    )
                    serializer.is_valid(raise_exception=True)
                    asset = serializer.save(gallery=gallery)
                    uploaded_assets.append(asset)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            MediaAssetSerializer(uploaded_assets, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class PhotoDetailView(APIView):
    """
    GET    /api/v1/photos/photo/{photo_id}/ - Retrieve metadata of a single media asset.
    DELETE /api/v1/photos/photo/{photo_id}/ - Purge an asset. Calls signal for file cleanup.
    
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

        # Deleting the model row. Signals.py handles physical file/S3 purges automatically.
        asset.delete()
        return Response({'message': 'Media asset deleted successfully.'}, status=status.HTTP_200_OK)