from django.db import transaction
from django.shortcuts import get_object_or_404
from rest_framework import status
from rest_framework.parsers import MultiPartParser, FormParser
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.galleries.models import Gallery
from .models import Photo
from .serializers import PhotoListSerializer, PhotoUploadSerializer


class PhotoListUploadView(APIView):
    """
    GET  /api/v1/photos/{gallery_slug}/ - Lists all photos inside an active gallery.
    POST /api/v1/photos/{gallery_slug}/upload/ - Processes bulk image streams securely [1.1.2].
    """
    permission_classes = [IsAuthenticated]
    parser_classes = [MultiPartParser, FormParser]

    def get_gallery(self, slug, user):
        """Retrieves an active gallery scoped strictly to the requesting user [1.1.2]."""
        try:
            return Gallery.objects.get(slug=slug, photographer=user, is_active=True)
        except Gallery.DoesNotExist:
            return None

    def get(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        photos = Photo.objects.filter(gallery=gallery).order_by('order', 'created_at')
        serializer = PhotoListSerializer(photos, many=True, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request, gallery_slug):
        gallery = self.get_gallery(gallery_slug, request.user)
        if not gallery:
            return Response({'error': 'Gallery not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Retrieve file list from the 'image' form-data key
        files = request.FILES.getlist('image')
        if not files:
            return Response({"image": ["No image file provided."]}, status=status.HTTP_400_BAD_REQUEST)

        uploaded_photos = []

        # Atomic transaction: If any single image fails, the entire batch rolls back [1.1.2]
        try:
            with transaction.atomic():
                for file_data in files:
                    serializer = PhotoUploadSerializer(
                        data={'image': file_data, 'title': request.data.get('title', '')},
                        context={'request': request, 'gallery': gallery}
                    )
                    serializer.is_valid(raise_exception=True)
                    photo = serializer.save(gallery=gallery)
                    uploaded_photos.append(photo)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

        return Response(
            PhotoListSerializer(uploaded_photos, many=True, context={'request': request}).data,
            status=status.HTTP_201_CREATED
        )


class PhotoDetailView(APIView):
    """
    GET    /api/v1/photos/photo/{photo_id}/ - Retrieve metadata of a single photo.
    DELETE /api/v1/photos/photo/{photo_id}/ - Purge a photo. Calls signal for file cleanup [1.1.2].
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, photo_id, user):
        """Fetch photo using double join lookup: Photo -> Gallery -> User [1.1.2]"""
        try:
            return Photo.objects.select_related('gallery').get(
                id=photo_id,
                gallery__photographer=user,
                gallery__is_active=True
            )
        except Photo.DoesNotExist:
            return None

    def get(self, request, photo_id):
        photo = self.get_object(photo_id, request.user)
        if not photo:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)
        
        serializer = PhotoListSerializer(photo, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)

    def delete(self, request, photo_id):
        photo = self.get_object(photo_id, request.user)
        if not photo:
            return Response({'error': 'Photo not found.'}, status=status.HTTP_404_NOT_FOUND)

        # Deleting the model row. Signals.py handles physical file/S3 purges automatically [1.1.2].
        photo.delete()
        return Response({'message': 'Photo deleted successfully.'}, status=status.HTTP_200_OK)