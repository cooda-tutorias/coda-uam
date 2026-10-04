from urllib.parse import parse_qs, urlsplit

from django.test import SimpleTestCase, override_settings
from django.urls import reverse

from custom_storages import MediaStorage


@override_settings(
    OBJECT_STORAGE_ENABLED=True,
    OBJECT_STORAGE_USE_TLS=True,
    OBJECT_STORAGE_CA_BUNDLE='/run/seaweedfs-ca/ca.crt',
    AWS_ACCESS_KEY_ID='test-access',
    AWS_SECRET_ACCESS_KEY='test-secret',
    AWS_STORAGE_BUCKET_NAME='coda-media',
    AWS_S3_REGION_NAME='us-east-1',
    AWS_S3_ENDPOINT_URL='https://seaweedfs:8333',
    AWS_S3_SIGNATURE_VERSION='s3v4',
    AWS_S3_ADDRESSING_STYLE='path',
    AWS_QUERYSTRING_AUTH=True,
)
class MediaStorageUrlTests(SimpleTestCase):
    def test_url_de_media_apunta_al_proxy_django_sin_exponer_s3(self):
        url = MediaStorage().url('trayectorias/alumno-1/historial.pdf')

        self.assertEqual(
            url,
            reverse(
                'archivo-privado',
                kwargs={'nombre': 'trayectorias/alumno-1/historial.pdf'},
            ),
        )
        self.assertNotIn('seaweedfs', url)
        self.assertNotIn('X-Amz-Signature', url)
