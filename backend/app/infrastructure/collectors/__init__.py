"""Opt-in, read-only cloud API collection. Credentials never enter the API."""

from backend.app.infrastructure.collectors.base import CollectionError, CollectionResult


def collect(request):
    if request.provider == "aws":
        from backend.app.infrastructure.collectors.aws import collect_aws

        return collect_aws(request)
    if request.provider == "azure":
        from backend.app.infrastructure.collectors.azure import collect_azure

        return collect_azure(request)
    from backend.app.infrastructure.collectors.gcp import collect_gcp

    return collect_gcp(request)
