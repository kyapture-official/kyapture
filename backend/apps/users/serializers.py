# C:/Users/LENOVO/Desktop/kyapture/backend/apps/users/serializers.py
import logging
import re
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from apps.core.branding import InvalidLogo, sanitize_logo_upload
from apps.subscriptions.entitlements import BRANDING, require_feature
from .models import User

logger = logging.getLogger(__name__)

# List of reserved system subdomains to prevent hijacking/spoofing
RESERVED_USERNAMES = {
    'admin', 'api', 'app', 'www', 'mail', 'blog', 'support', 'billing',
    'root', 'static', 'media', 'domain', 'kaypture', 'test', 'dev'
}

# Enforces RFC-compliant, URL-safe subdomains (lowercase alphanumeric, with single internal dashes)
USERNAME_REGEX = re.compile(r'^[a-z0-9](-?[a-z0-9])*$')

class UserProfileSerializer(serializers.ModelSerializer):
    """
    Serializes complete User profile data.
    Protects read-only fields from administrative or photographer manipulation.
    """
    class Meta:
        model = User
        fields = [
            'id', 'email', 'username', 'display_name',
            'bio', 'avatar', 'logo', 'branding_color',
            'phone', 'website', 'is_active_plan', 'created_at'
        ]
        read_only_fields = ['id', 'email', 'is_active_plan', 'created_at']

    def validate_username(self, value):
        clean_username = value.strip().lower()
        if clean_username in RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved for system administration.")
        if not USERNAME_REGEX.match(clean_username):
            raise serializers.ValidationError(
                "Username must be lowercase, alphanumeric, and can only contain single dashes."
            )
        query_set = User.objects.filter(username=clean_username)
        if self.instance:
            query_set = query_set.exclude(id=self.instance.id)
        if query_set.exists():
            raise serializers.ValidationError("This username is already taken.")
        return clean_username

    def validate_branding_color(self, value):
        if value and not re.match(r'^#[0-9a-fA-F]{6}$', value):
            raise serializers.ValidationError('Color must be a valid hex code (e.g., #FF5733).')
        return value

    def to_internal_value(self, data):
        """
        Check the Branding entitlement BEFORE any field parses the upload.
        DRF's ImageField decodes the file with Pillow during field
        validation, which would otherwise run on an untrusted file for an
        account that is not allowed to upload one, and answer a Free user's
        bad file with a 400 instead of the real reason (403).
        """
        if self.instance is not None and hasattr(data, 'get') and data.get('logo') not in (None, ''):
            require_feature(self.instance, BRANDING)
        return super().to_internal_value(data)

    def validate_logo(self, value):
        """
        Branding is a Pro+ feature, enforced HERE (server-side) — the settings
        UI's locked state is only a courtesy. Setting/replacing a logo needs
        the entitlement; removing one (value is None) never does, so a
        photographer whose plan lapsed can still clean up. The upload itself
        is validated by Pillow and re-encoded (see apps/core/branding.py).
        """
        if value is None:
            return value
        require_feature(self.instance, BRANDING)
        try:
            return sanitize_logo_upload(value)
        except InvalidLogo as exc:
            raise serializers.ValidationError(str(exc))

    def update(self, instance, validated_data):
        previous_logo = instance.logo.name if instance.logo else None
        instance = super().update(instance, validated_data)
        if 'logo' in validated_data and previous_logo:
            current_logo = instance.logo.name if instance.logo else None
            if previous_logo != current_logo:
                # Unique key per upload (see get_branding_logo_path), so the
                # old file is now an orphan — delete it. Never let a storage
                # hiccup fail the profile save the user just made.
                try:
                    instance.logo.storage.delete(previous_logo)
                except Exception:
                    logger.exception('Failed to delete replaced branding logo %s', previous_logo)
        return instance


class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles secure photographer registration.
    Enforces password strength validation and protects the platform subdomain namespace [1.1.2].
    """
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})
    
    # Declare fields explicitly to allow clean optional parameters during registration
    phone = serializers.CharField(required=False, allow_blank=True, default='')
    website = serializers.URLField(required=False, allow_null=True, default=None)
    class Meta:
        model = User
        fields = ['email', 'username', 'phone', 'website', 'display_name', 'password', 'password2']

    def validate_email(self, value):
        """Sanitizes and normalizes the email, then checks for global database uniqueness."""
        clean_email = value.strip().lower()
        if User.objects.filter(email=clean_email).exists():
            raise serializers.ValidationError("A user with this email already exists.")
        return clean_email

    def validate_username(self, value):
        """Validates that the username is a secure, unique, and URL-safe subdomain."""
        clean_username = value.strip().lower()
        
        if clean_username in RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved.")
            
        if not USERNAME_REGEX.match(clean_username):
            raise serializers.ValidationError(
                "Username must contain only lowercase, alphanumeric, characters and single internal dashes."
            )
            
        if User.objects.filter(username=clean_username).exists():
            raise serializers.ValidationError("This username is already taken.")
            
        return clean_username

    def validate(self, data):
        """Performs password match checks and runs Django's native strength validator [1.1.2]."""
        # Password match check
        if data['password'] != data['password2']:
            raise serializers.ValidationError({'password': 'Passwords do not match.'})
            
        # Cryptographic strength checks using Django's validation engine
        try:
            # We must pass the user instance context if we want to check against username/email
            user_instance = User(username=data.get('username'), email=data.get('email'))
            validate_password(data['password'], user=user_instance)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'password': list(e.messages)})
            
        return data

    def create(self, validated_data):
        """Creates the active photographer account using custom manager."""
        validated_data.pop('password2')
        password = validated_data.pop('password')
        return User.objects.create_user(password=password, **validated_data)


class LoginSerializer(serializers.Serializer):
    """
    Authenticates photographer credentials.
    Generates and returns JWT access/refresh tokens alongside their profile metadata [1.1.2].
    """
    email = serializers.EmailField()
    password = serializers.CharField(write_only=True)

    def validate(self, data):
        clean_email = data.get('email').strip().lower()
        password = data.get('password')

        # authenticate() evaluates clean parameters against the database hashes
        user = authenticate(
            request=self.context.get('request'),
            username=clean_email,
            password=password
        )
        
        if not user:
            raise serializers.ValidationError({'non_field_errors': 'Invalid email or password.'})
            
        if not user.is_active:
            raise serializers.ValidationError({'non_field_errors': 'This account has been disabled.'})

        # Generate standard JWT session and refresh tokens
        refresh = RefreshToken.for_user(user)

        # Connect and return the user profile directly to optimize David's frontend [1.1.2]
        return {
            'user': UserProfileSerializer(user, context=self.context).data,
            'access': str(refresh.access_token),
            'refresh': str(refresh),
        }


class ChangePasswordSerializer(serializers.Serializer):
    """
    Validates and changes active user passwords securely.
    """
    old_password = serializers.CharField(write_only=True)
    new_password = serializers.CharField(write_only=True)
    new_password2 = serializers.CharField(write_only=True)

    def validate(self, data):
        if data['new_password'] != data['new_password2']:
            raise serializers.ValidationError({'new_password': 'New passwords do not match.'})
            
        try:
            validate_password(data['new_password'], user=self.context['request'].user)
        except DjangoValidationError as e:
            raise serializers.ValidationError({'new_password': list(e.messages)})
            
        return data

    def validate_old_password(self, value):
        user = self.context['request'].user
        if not user.check_password(value):
            raise serializers.ValidationError('Old password is incorrect.')
        return value

    def save(self, **kwargs):
        user = self.context['request'].user
        user.set_password(self.validated_data['new_password'])
        user.save()

        # Phase 4 (auth hardening): invalidate every other outstanding
        # session on a self-service password change too — see
        # blacklist_all_outstanding_tokens_for_user's own docstring
        # (apps/users/utils.py) for the full rationale. Deliberately
        # blacklists ALL outstanding tokens, including the one behind the
        # request making this very call — the frontend already holds a
        # short-lived (15 min) access token and will naturally need to
        # re-authenticate/refresh soon regardless, and there is no
        # reliable way from here to distinguish "this device" from "any
        # other device" among refresh tokens without adding new state
        # this app doesn't otherwise track.
        from .utils import blacklist_all_outstanding_tokens_for_user
        blacklist_all_outstanding_tokens_for_user(user)

        return user