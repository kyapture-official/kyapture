import uuid6
from django.db import models


class BaseModel(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid6.uuid7,
        editable=False
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True