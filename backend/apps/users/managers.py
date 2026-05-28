from django.contrib.auth.base_user import BaseUserManager


class CustomUserManager(BaseUserManager):
    """
    Custom user model manager where email is the unique identifier
    for authentication instead of usernames. Built to handle scale,
    multi-DB environments, and strict permission verification.
    """

    def create_user(self, email, password=None, **extra_fields):
        """
        Creates, hashes, and saves a User with the given email and password.
        """
        if not email:
            raise ValueError("The Email field must be set")
        
        # Elite Normalization: Strip spaces and lowercase the ENTIRE email
        email = self.normalize_email(email).strip().lower()
        
        user = self.model(email=email, **extra_fields)
        
        if password:
            user.set_password(password)
        else:
            user.set_unusable_password()  # Securely handles social/OAuth users without blank passwords

        # Crucial for scale: Save using the DB router's designated database context
        user.save(using=self._db)
        return user

    def create_superuser(self, email, password=None, **extra_fields):
        """
        Creates and saves a Superuser with strict validation and error raising.
        """
        extra_fields.setdefault("is_staff", True)
        extra_fields.setdefault("is_superuser", True)
        extra_fields.setdefault("is_active", True)

        # Strict validation: Don't let developer error compromise security
        if extra_fields.get("is_staff") is not True:
            raise ValueError("Superuser must have is_staff=True.")
        if extra_fields.get("is_superuser") is not True:
            raise ValueError("Superuser must have is_superuser=True.")

        return self.create_user(email, password, **extra_fields)