from django.db.models import Count
from rest_framework import status
from rest_framework.response import Response
from rest_framework.views import APIView
from rest_framework.permissions import IsAuthenticated

# Dynamic permission routing prevents the Storage Lockout Paradox
from apps.core.permissions import IsSubscribed
from apps.core.utils import get_user_subscription_metrics
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
        photographer = request.user
        
        # 1. Single-pass metric calculations
        metrics = get_user_subscription_metrics(photographer)
        
        # 2. Skip limit check for administrative staff
        if not (photographer.is_superuser or photographer.is_staff):
            if metrics["current_galleries_count"] >= metrics["max_galleries"]:
                return Response({
                    "error": "Gallery limit reached for your current plan.",
                    "code": "gallery_limit_reached",
                    "current_count": metrics["current_galleries_count"],
                    "plan_limit": metrics["max_galleries"],
                    "plan_name": metrics["plan_name"],
                    "message": f"You have used {metrics['current_galleries_count']} of {metrics['max_galleries']} galleries on the {metrics['plan_name']} plan. Upgrade your plan to create more."
                }, status=status.HTTP_403_FORBIDDEN)

        # 3. Instantiate the serializer exactly once
        serializer = GalleryCreateSerializer(
            data=request.data,
            context={'request': request}
        )
        
        if serializer.is_valid():
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
        

class DashboardStatsView(APIView):
    """
    GET /api/v1/galleries/dashboard/stats/

    Returns complete dashboard analytics for the logged-in photographer.
    Uses our single-pass metrics utility to keep the database footprint at O(1)
    while matching Claude's frontend contract keys perfectly.

    David uses this to render:
    - Storage progress bar (used vs limit)
    - Gallery slots badge
    - Expiration warning banners
    """
    permission_classes = [IsAuthenticated]

    def get(self, request):
        photographer = request.user
        from django.utils import timezone
        from apps.photos.models import MediaAsset
        from apps.subscriptions.models import UserSubscription

        # 1. Fetch single-pass subscription limits and usage metrics from PostgreSQL
        metrics = get_user_subscription_metrics(photographer)

        # 2. Count total media assets (both photos and videos) across all active galleries
        photos_used = MediaAsset.objects.filter(
            gallery__photographer=photographer,
            gallery__is_active=True
        ).count()

        # 3. Resolve active subscription expiration parameters safely
        days_remaining = 0
        expires_at = None
        subscription_status = "no_subscription"

        try:
            sub = UserSubscription.objects.get(user=photographer, status='active')
            subscription_status = sub.status
            if sub.expires_at:
                expires_at = sub.expires_at
                if sub.expires_at > timezone.now():
                    days_remaining = (sub.expires_at - timezone.now()).days
        except UserSubscription.DoesNotExist:
            pass

        # 4. Handle Admin Bypass case cleanly
        if photographer.is_superuser or photographer.is_staff:
            return Response({
                'galleries_used': metrics["current_galleries_count"],
                'photos_used': photos_used,
                'storage_used_bytes': metrics["current_total_storage_bytes"],
                'storage_used_gb': round(metrics["current_total_storage_bytes"] / (1024 ** 3), 2),
                'plan_name': 'Admin',
                'plan_gallery_limit': None,
                'plan_photo_limit': None,
                'plan_storage_limit_gb': None,
                'plan_storage_limit_bytes': None,
                'galleries_remaining': None,
                'storage_remaining_gb': None,
                'subscription_status': 'admin',
                'expires_at': None,
                'days_remaining': None,
            }, status=status.HTTP_200_OK)

        # 5. Handle Unsubscribed case cleanly (No crash, returns zero bounds)
        if subscription_status == "no_subscription":
            return Response({
                'galleries_used': metrics["current_galleries_count"],
                'photos_used': photos_used,
                'storage_used_bytes': metrics["current_total_storage_bytes"],
                'storage_used_gb': round(metrics["current_total_storage_bytes"] / (1024 ** 3), 2),
                'plan_name': None,
                'plan_gallery_limit': None,
                'plan_photo_limit': None,
                'plan_storage_limit_gb': None,
                'plan_storage_limit_bytes': None,
                'galleries_remaining': None,
                'storage_remaining_gb': None,
                'subscription_status': 'no_subscription',
                'expires_at': None,
                'days_remaining': None,
            }, status=status.HTTP_200_OK)

        # 6. Calculate Remaining Quotas
        storage_used_bytes = metrics["current_total_storage_bytes"]
        plan_storage_bytes = metrics["storage_bytes_limit"]
        
        galleries_remaining = max(0, metrics["max_galleries"] - metrics["current_galleries_count"])
        storage_remaining_gb = round(
            max(0.0, (plan_storage_bytes - storage_used_bytes) / (1024 ** 3)), 
            2
        )

        # 7. Deliver the structured JSON payload matching David's exact key mappings
        return Response({
            'galleries_used': metrics["current_galleries_count"],
            'photos_used': photos_used,
            'storage_used_bytes': storage_used_bytes,
            'storage_used_gb': round(storage_used_bytes / (1024 ** 3), 2),
            
            'plan_name': metrics["plan_name"],
            'plan_gallery_limit': metrics["max_galleries"],
            'plan_photo_limit': metrics["max_photos_per_gallery"],
            'plan_storage_limit_gb': metrics["storage_bytes_limit"] / (1024 ** 3),
            'plan_storage_limit_bytes': plan_storage_bytes,
            
            'galleries_remaining': galleries_remaining,
            'storage_remaining_gb': storage_remaining_gb,
            
            'subscription_status': subscription_status,
            'expires_at': expires_at,
            'days_remaining': days_remaining,
        }, status=status.HTTP_200_OK)