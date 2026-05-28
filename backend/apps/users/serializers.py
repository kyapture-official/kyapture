import re
from django.contrib.auth import authenticate
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError as DjangoValidationError
from rest_framework import serializers
from rest_framework_simplejwt.tokens import RefreshToken
from .models import User

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
            'bio', 'avatar', 'is_active_plan', 'created_at'
        ]
        read_only_fields = ['id', 'email', 'is_active_plan', 'created_at']

    def validate_username(self, value):
        """Ensures updates to usernames are strictly validated as URL-safe subdomains."""
        clean_username = value.strip().lower()
        # 1. Enforce admin reserve-word protections
        if clean_username in RESERVED_USERNAMES:
            raise serializers.ValidationError("This username is reserved for system administration.")
            
        # 2. Enforce RFC-compliant URL patterns
        if not USERNAME_REGEX.match(clean_username):
            raise serializers.ValidationError(
                "Username must be lowercase, alphanumeric, and can only contain single dashes."
            )
        
        # 3. Enforce Unique checks while excluding the current user's own ID [1.1.2]
        user_instance = self.instance  # Resolves to the user being updated
        query_set = User.objects.filter(username=clean_username)
        
        if user_instance:
            query_set = query_set.exclude(id=user_instance.id)
            
        if query_set.exists():
            raise serializers.ValidationError("This username is already taken.")
        return clean_username


class RegisterSerializer(serializers.ModelSerializer):
    """
    Handles secure photographer registration.
    Enforces password strength validation and protects the platform subdomain namespace [1.1.2].
    """
    password = serializers.CharField(write_only=True, style={'input_type': 'password'})
    password2 = serializers.CharField(write_only=True, style={'input_type': 'password'})

    class Meta:
        model = User
        fields = ['email', 'username', 'display_name', 'password', 'password2']

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
        return user