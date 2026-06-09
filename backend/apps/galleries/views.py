from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

# Dynamic permission routing prevents the Storage Lockout Paradox
from apps.core.permissions import IsSubscribed
from .models import Gallery
from .serializers import (
    GalleryListSerializer,
    GalleryCreateSerializer,
    GalleryDetailSerializer,
    GalleryUpdateSerializer,
)


class GalleryListCreateView(APIView):
    """
    GET  /api/v1/galleries/  — List all active galleries for the logged-in photographer.
    POST /api/v1/galleries/  — Create a new custom photographer gallery (Gated by Subscription) [1.1.2].
    """
    
    def get_permissions(self):
        """
        Enforce IsSubscribed strictly on write operations (POST).
        Allows expired photographers to view their dashboard and see upgrade 
        prompts, but blocks the creation of new resources [1.1.2].
        """
        if self.request.method == 'POST':
            return [IsAuthenticated(), IsSubscribed()]
        return [IsAuthenticated()]

    def get(self, request):
        # 1. Enforce strict tenant isolation (photographer=request.user) [1.1.2]
        # 2. Filter out soft-deleted galleries (is_active=True) [1.1.2]
        # 3. Use SQL Count annotation to eliminate N+1 query loops [1.1.2]
        # 4. Use select_related to INNER JOIN the cover photo details [1.1.2]
        galleries = (
            Gallery.objects
            .filter(photographer=request.user, is_active=True)
            .select_related('cover_photo')
            .annotate(photo_count=Count('photos'))
            .order_by('-created_at')
        )

        serializer = GalleryListSerializer(
            galleries,
            many=True,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def post(self, request):
        serializer = GalleryCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        if serializer.is_valid():
            # Gating calculation is triggered inside serializer.create() [1.1.2]
            gallery = serializer.save()
            return Response(
                serializer.to_representation(gallery),
                status=status.HTTP_201_CREATED
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)


class GalleryDetailView(APIView):
    """
    GET    /api/v1/galleries/{slug}/  — View detailed settings of a specific gallery.
    PUT    /api/v1/galleries/{slug}/  — Update settings or cover photo parameters.
    DELETE /api/v1/galleries/{slug}/  — Soft-delete gallery (mark is_active=False) [1.1.2].
    
    NOTE: Left with IsAuthenticated permission to allow expired users to edit/delete 
    assets to cleanly manage their database footprint and resolve plan limit blocks.
    """
    permission_classes = [IsAuthenticated]

    def get_object(self, slug, user):
        """
        Retrieves a single gallery. Scopes lookup to active galleries 
        belonging strictly to the requesting user [1.1.2].
        """
        try:
            return (
                Gallery.objects
                .select_related('cover_photo')
                .annotate(photo_count=Count('photos'))
                .get(slug=slug, photographer=user, is_active=True)
            )
        except Gallery.DoesNotExist:
            return None

    def get(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            # Mask the error as 404 to prevent enumeration attacks [1.1.2]
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        serializer = GalleryDetailSerializer(
            gallery,
            context={'request': request}
        )
        return Response(serializer.data, status=status.HTTP_200_OK)

    def put(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        serializer = GalleryUpdateSerializer(
            gallery,
            data=request.data,
            partial=True,
            context={'request': request}
        )
        if serializer.is_valid():
            updated_gallery = serializer.save()
            return Response(
                serializer.to_representation(updated_gallery),
                status=status.HTTP_200_OK
            )
        return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

    def delete(self, request, slug):
        gallery = self.get_object(slug, request.user)
        if not gallery:
            return Response(
                {'error': 'Gallery not found.'},
                status=status.HTTP_404_NOT_FOUND
            )
        
        # Safe Soft-Delete: Never hard-delete client delivery assets [1.1.2]
        gallery.is_active = False
        gallery.save()
        
        return Response(
            {'message': 'Gallery deleted successfully.'},
            status=status.HTTP_200_OK
        )