"""Opt-in, read-only cloud API collection. Credentials never enter the API."""
from .base import CollectionError, CollectionResult


def collect(request):
    if request.provider == "aws":
        from .aws import collect_aws
        return collect_aws(request)
    if request.provider == "azure":
        from .azure import collect_azure
        return collect_azure(request)
    from .gcp import collect_gcp
    return collect_gcp(request)
