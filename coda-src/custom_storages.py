from django.conf import settings
from django.core.files.storage import FileSystemStorage
from django.urls import reverse
from storages.backends.s3boto3 import S3Boto3Storage
from storages.utils import clean_name

class StaticStorage(S3Boto3Storage):
    location = getattr(settings, 'STATICFILES_LOCATION', 'static')

class MediaStorage(S3Boto3Storage):
    location = getattr(settings, 'MEDIAFILES_LOCATION', 'media')
    default_acl = None
    file_overwrite = False

    def url(self, name, parameters=None, expire=None, http_method=None):
        return reverse('archivo-privado', kwargs={'nombre': clean_name(name)})


class PrivateFileSystemStorage(FileSystemStorage):
    def url(self, name):
        return reverse('archivo-privado', kwargs={'nombre': clean_name(name)})