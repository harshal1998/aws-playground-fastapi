"""
Sairo S3 Browser Extension & Presigned URL Patch.

Rewrites internal container hostnames (e.g. http://localstack:4566)
to public host endpoints (e.g. http://localhost:4566) so that presigned
URLs, download links, and shared links work seamlessly in host browsers.
"""
import os

import botocore.signers

_orig_generate_presigned_url = botocore.signers.RequestSigner.generate_presigned_url


def _custom_generate_presigned_url(self, *args, **kwargs):
    url = _orig_generate_presigned_url(self, *args, **kwargs)
    internal_endpoint = os.environ.get("S3_ENDPOINT", "http://localstack:4566").rstrip("/")
    public_endpoint = os.environ.get("S3_PUBLIC_ENDPOINT", "http://localhost:4566").rstrip("/")

    if internal_endpoint and public_endpoint and internal_endpoint in url:
        url = url.replace(internal_endpoint, public_endpoint)
    return url


botocore.signers.RequestSigner.generate_presigned_url = _custom_generate_presigned_url
