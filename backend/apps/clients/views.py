from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.galleries.models import Gallery
from .models import ClientSession
from .serializers import (
    PublicGallerySerializer,
    GalleryUnlockSerializer,
)


class PublicGalleryView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/
    GET /api/v1/public/{username}/{slug}/?token=abc123

    Public gateway. Enforces multi-tenant routing, soft-delete safety,
    and password session auditing [1.1.2].
    """
    permission_classes = [AllowAny]

    def get_gallery(self, username, slug):
        """
        Retrieves a published, active gallery mapped to a specific photographer.
        This prevents MultipleObjectsReturned crashes on shared slug namespaces [1.1.2].
        """
        try:
            return (
                Gallery.objects
                .select_related('photographer')
                .prefetch_related('photos')
                .get(
                    slug=slug,
                    photographer__username=username,  # Multi-tenant scoping [1.1.2]
                    is_published=True,                # Block draft galleries
                    is_active=True                    # Block soft-deleted galleries [1.1.2]
                )
            )
        except Gallery.DoesNotExist:
            return None

    def validate_session_token(self, token, gallery):
        """Verifies if the client's local session token is active for this gallery [1.1.2]."""
        if not token:
            return False
        return ClientSession.objects.filter(
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
            token = request.query_params.get('token', '').strip()

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

        # 3. Access granted: Return fully serialized public metadata [1.1.2]
        serializer = PublicGallerySerializer(gallery, context={'request': request})
        return Response(serializer.data, status=status.HTTP_200_OK)


class GalleryUnlockView(APIView):
    """
    POST /api/v1/public/{username}/{slug}/unlock/
    Authenticates gallery password credentials.
    On success, writes a ClientSession and returns a secure token [1.1.2].
    """
    permission_classes = [AllowAny]

    def get_gallery(self, username, slug):
        """Retrieves targeted active gallery for validation."""
        try:
            return Gallery.objects.get(
                slug=slug,
                photographer__username=username,
                is_published=True,
                is_active=True
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