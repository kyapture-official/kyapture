from django.core.management.base import BaseCommand
from django.core.files.storage import default_storage
from django.core.files.base import ContentFile
from django.conf import settings


class Command(BaseCommand):
    """
    Surgically tests the active S3 bucket connection and IAM permissions 
    by writing, reading, and deleting a dummy probe file on S3.
    """
    help = "Tests active AWS S3 storage configurations and IAM permissions."

    def handle(self, *args, **options):
        self.stdout.write(self.style.WARNING("Starting AWS S3 Storage Connectivity Test..."))

        # 1. Assert AWS credentials exist in active settings
        aws_id = getattr(settings, 'AWS_ACCESS_KEY_ID', None)
        aws_secret = getattr(settings, 'AWS_SECRET_ACCESS_KEY', None)
        aws_bucket = getattr(settings, 'AWS_STORAGE_BUCKET_NAME', None)

        if not (aws_id and aws_secret and aws_bucket):
            self.stdout.write(
                self.style.ERROR(
                    "❌ ERROR: AWS credentials are not configured in your settings/environment!\n"
                    "Ensure you have pasted AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY, "
                    "and AWS_STORAGE_BUCKET_NAME inside your backend/.env file."
                )
            )
            return

        self.stdout.write(f"Target Bucket: {aws_bucket}")
        self.stdout.write(f"Target Region: {getattr(settings, 'AWS_S3_REGION_NAME', 'us-east-1')}")

        # 2. Test Write Permissions
        test_filename = "s3_connection_test_probe.txt"
        test_content = b"Kaypture S3 dynamic verification payload. S3 connection is certified."
        probe_file = ContentFile(test_content, name=test_filename)

        try:
            self.stdout.write("Step 1: Attempting to write a test probe file to storage...")
            # If S3 is active, default_storage dynamically points to S3Boto3Storage
            path = default_storage.save(test_filename, probe_file)
            self.stdout.write(self.style.SUCCESS(f"✓ SUCCESS: File written to storage path: {path}"))
            
            # Verify URL resolution
            absolute_url = default_storage.url(path)
            self.stdout.write(f"File Resolved URL: {absolute_url}")

        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ WRITE FAILED: Could not save the file to S3.\n"
                    f"AWS Error Message: {str(e)}\n"
                    f"Check: Ensure your S3 bucket name is correct and your IAM User has 's3:PutObject' permissions."
                )
            )
            return

        # 3. Test Read/Fetch Permissions
        try:
            self.stdout.write("\nStep 2: Attempting to read probe file back from storage...")
            with default_storage.open(path, 'r') as f:
                read_content = f.read()
                
            if read_content.strip() == test_content.decode('utf-8').strip():
                self.stdout.write(self.style.SUCCESS("✓ SUCCESS: File content verified successfully!"))
            else:
                self.stdout.write(self.style.WARNING("⚠ WARNING: File read succeeded, but content mismatch detected."))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ READ FAILED: Could not retrieve the file from S3.\n"
                    f"AWS Error Message: {str(e)}\n"
                    f"Check: Ensure your bucket permits reads, or that your IAM User has 's3:GetObject' permissions."
                )
            )
            return

        # 4. Test Delete Permissions
        try:
            self.stdout.write("\nStep 3: Attempting to delete the test probe file...")
            default_storage.delete(path)
            self.stdout.write(self.style.SUCCESS("✓ SUCCESS: Test probe file purged cleanly from S3!"))
        except Exception as e:
            self.stdout.write(
                self.style.ERROR(
                    f"❌ DELETE FAILED: File remains orphaned on S3.\n"
                    f"AWS Error Message: {str(e)}\n"
                    f"Check: Ensure your IAM User has 's3:DeleteObject' permissions."
                )
            )
            return

        self.stdout.write(
            self.style.SUCCESS(
                "\n🎉 CONGRATULATIONS: AWS S3 connection and IAM policies are fully certified!\n"
                "Your storage backend is ready for production uploads."
            )
        )