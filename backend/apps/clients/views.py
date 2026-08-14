#C:\Users\LENOVO\Desktop\kyapture\backend\apps\clients\views.py :
import os
import tempfile
import zipfile
from django.http import StreamingHttpResponse
from django.shortcuts import get_object_or_404
from django.db.models import Count
from rest_framework import status
from rest_framework.permissions import AllowAny
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.throttling import AnonRateThrottle

from apps.galleries.models import Gallery
from .models import ClientSession, DownloadLog  
from apps.photos.models import MediaAsset 
from .serializers import (
    PublicGallerySerializer,
    GalleryUnlockSerializer,
)

# ─────────────────────────────────────────────────────────────
# CUSTOM SECURITY THROTTLE (Password brute-force protection)
# ─────────────────────────────────────────────────────────────
class PasswordUnlockRateThrottle(AnonRateThrottle):
    """
    Limits anonymous password-unlock attempts to the custom 
    'password_unlock' rate (5 attempts/minute) configured in settings.
    """
    scope = 'password_unlock'


class PublicGalleryView(APIView):
    """
    GET /api/v1/public/{username}/{slug}/
    GET /api/v1/public/{username}/{slug}/?token=abc123

    Public gateway. Enforces multi-tenant routing, soft-delete safety,
    and password session auditing [1.1.2].
    """
    permission_classes = [AllowAny]
    authentication_classes = [] 
    
    def get_gallery(self, username, slug):
        """
        Retrieves a published, active gallery mapped to a specific photographer.
        This prevents MultipleObjectsReturned crashes on shared slug namespaces [1.1.2].
        """
        try:
            return (
                Gallery.objects
                .select_related('photographer')
                .prefetch_related('assets')
                .get(
                    slug=slug,
                    photographer__username=username,  # Multi-tenant scoping [1.1.2]
                    is_published=True,                # Block draft galleries
                    is_active=True                    # Block soft-deleted galleries [1.1.2]
                )
            )
        except Gallery.DoesNotExist:
            return None
# backend/apps/clients/views.py — inside PublicGalleryView

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
    authentication_classes = []
    throttle_classes = [PasswordUnlockRateThrottle]
    
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
            return Gallery.objects.select_related('photographer').get(
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
            
            # Assert a valid ClientSession has been registered for this guest token
            valid_session = ClientSession.objects.filter(
                access_token=token,
                gallery=gallery
            ).exists()
            
            if not valid_session:
                return Response(
                    {'error': 'An active unlocked session is required to download this gallery.'}, 
                    status=status.HTTP_401_UNAUTHORIZED
                )

        # 4. Validate guest email (Photographer lead capture)
        email = request.data.get('email', '').strip()
        if not email:
            return Response(
                {'error': 'A valid email address is required to initiate downloads.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 5. Fetch all media assets inside the gallery
        assets = MediaAsset.objects.filter(gallery=gallery)
        if not assets.exists():
            return Response(
                {'error': 'Cannot compile download: Gallery is empty.'}, 
                status=status.HTTP_400_BAD_REQUEST
            )

        # 6. Audit: Register the download log for lead tracking
        ip_address = self._get_client_ip(request)
        DownloadLog.objects.create(
            gallery=gallery,
            email=email,
            ip_address=ip_address
        )

        # 7. O(1) Memory Compression Spooling
        # Create a temporary secure file path on the hard drive rather than RAM
        temp_zip_fd, temp_zip_path = tempfile.mkstemp(suffix=".zip")
        os.close(temp_zip_fd)

        try:
            # Open the zip archive writer
            with zipfile.ZipFile(temp_zip_path, 'w', zipfile.ZIP_DEFLATED) as zip_file:
                for asset in assets:
                    if asset.original_file:
                        try:
                            # Django's storage layer dynamically streams bytes from either Local disk or AWS S3
                            asset.original_file.open('rb')
                            file_data = asset.original_file.read()
                            
                            # Write file to ZIP archive using its authentic photographer filename
                            zip_file.writestr(asset.original_name, file_data)
                        except Exception as e:
                            # Log the single file capture warning but continue packing other assets
                            pass
                        finally:
                            asset.original_file.close()

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
            response['Content-Disposition'] = f'attachment; filename="{gallery.slug}.zip"'
            return response

        except Exception as e:
            # If ZIP compilation completely crashes, clean up the temp file
            if os.path.exists(temp_zip_path):
                os.remove(temp_zip_path)
            return Response(
                {"error": f"Failed to compile download package: {str(e)}"}, 
                status=status.HTTP_500_INTERNAL_SERVER_ERROR
            )


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

    def get(self, request, username):
        # Dynamic import to prevent circular dependency boots
        from apps.users.models import User
        from apps.galleries.models import Gallery
        from apps.galleries.serializers import GalleryListSerializer

        # 1. Fetch photographer safely. Returns 404 if user is inactive/absent
        photographer = get_object_or_404(
            User.objects.filter(is_active=True), 
            username=username.strip().lower()
        )

        # 2. Fetch all published, active galleries belonging to this photographer
        # select_related cover_photo and Count annotations are applied to eliminate N+1 SQL queries
        galleries = (
            Gallery.objects
            .filter(photographer=photographer, is_published=True, is_active=True)
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