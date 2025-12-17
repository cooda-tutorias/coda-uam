"""
Django settings for testing with SQLite and ArrayField->JSONField conversion.
"""
import os
import sys
from pathlib import Path

# Add ssocial to path
BASE_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(BASE_DIR))

# Monkeypatch ArrayField to use JSONField for SQLite compatibility
from django.db import models
from django.contrib.postgres import fields as postgres_fields

# Reemplazar ArrayField con JSONField
class CompatibleArrayField(models.JSONField):
    """ArrayField compatible con SQLite usando JSONField internamente"""
    def __init__(self, base_field=None, **kwargs):
        if base_field:
            kwargs.pop('base_field', None)
        super().__init__(**kwargs)

postgres_fields.ArrayField = CompatibleArrayField

# Import all settings from ssocial AFTER patching
from ssocial.settings import *  # noqa

# Override database to use SQLite for testing
DATABASES = {
    'default': {
        'ENGINE': 'django.db.backends.sqlite3',
        'NAME': ':memory:',  # Use in-memory database for speed
    }
}

# Disable email for testing
EMAIL_BACKEND = 'django.core.mail.backends.console.EmailBackend'

# Disable S3 storage for testing
DEFAULT_FILE_STORAGE = 'django.core.files.storage.FileSystemStorage'

# Disable migrations and use syncdb instead
class DisableMigrations:
    def __contains__(self, item):
        return True

    def __getitem__(self, item):
        return None

MIGRATION_MODULES = DisableMigrations()
