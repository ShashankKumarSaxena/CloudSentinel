"""Cloud HTTP routes; business logic stays in services."""

from pathlib import Path
import os

from fastapi import APIRouter, HTTPException, Query, Request

from backend.app.api.contracts import CloudAccountView, CollectionJobView, JobPageView, SnapshotView
from backend.app.api.dependencies import actor, get_services
from backend.app.domain.schemas import CollectionRequest

router = APIRouter()


@router.get("/api/v1/connectors")
def connectors(request: Request):
    services = get_services(request)
    import shutil

    if services.settings.production:
        accounts = services.connections.list()
        return [
            {
                "provider": provider,
                "credential_source": "Approved worker workload identity",
                "configured": any(
                    account["provider"] == provider and account["enabled"] for account in accounts
                ),
                "scope": "Operator-approved accounts and regions",
                "requires": "Credential availability and permissions are verified only by an explicit collection.",
            }
            for provider in ("aws", "azure", "gcp")
        ]

    return [
        {
            "provider": "aws",
            "credential_source": "Local boto3 profile or role",
            "configured": bool(
                os.environ.get("AWS_PROFILE")
                or os.environ.get("AWS_ACCESS_KEY_ID")
                or (Path.home() / ".aws/config").exists()
            ),
            "scope": "One AWS region plus global IAM users",
            "requires": "Local read-only AWS profile/role and a region. Configuration status does not verify credentials.",
        },
        {
            "provider": "azure",
            "credential_source": "Local Azure CLI or mounted token file",
            "configured": bool(
                (shutil.which("az") or os.environ.get("CLOUDSENTINEL_AZURE_TOKEN_FILE"))
                and os.environ.get("AZURE_SUBSCRIPTION_ID")
            ),
            "scope": "One Azure subscription",
            "requires": "Local CLI or administrator-configured token file; subscription ID via form or AZURE_SUBSCRIPTION_ID. Hints do not verify access.",
        },
        {
            "provider": "gcp",
            "credential_source": "Local gcloud CLI or mounted token file",
            "configured": bool(
                (shutil.which("gcloud") or os.environ.get("CLOUDSENTINEL_GCP_TOKEN_FILE"))
                and os.environ.get("GOOGLE_CLOUD_PROJECT")
            ),
            "scope": "One GCP project",
            "requires": "Local CLI or administrator-configured token file; project ID via form or GOOGLE_CLOUD_PROJECT. Hints do not verify access.",
        },
    ]


@router.get("/api/v1/cloud/accounts", response_model=list[CloudAccountView])
def cloud_accounts(request: Request):
    services = get_services(request)
    return services.connections.list()


@router.post("/api/v1/cloud/jobs", status_code=202, response_model=CollectionJobView)
def submit_collection(request: Request, body: CollectionRequest):
    services = get_services(request)
    key = request.headers.get("idempotency-key", "")
    if not 8 <= len(key) <= 128 or not key.isascii():
        raise HTTPException(400, "Provide an 8–128 character ASCII Idempotency-Key header.")
    return services.jobs.submit(body, actor(request), key)


@router.get("/api/v1/cloud/jobs", response_model=JobPageView)
def collection_jobs(
    request: Request,
    limit: int = Query(default=100, ge=1, le=200),
    offset: int = Query(default=0, ge=0, le=1000000),
):
    services = get_services(request)
    return services.jobs.list(limit, offset)


@router.get("/api/v1/cloud/jobs/{job_id}", response_model=CollectionJobView)
def collection_job(request: Request, job_id: str):
    services = get_services(request)
    return services.jobs.get(job_id)


@router.post("/api/v1/cloud/jobs/{job_id}/cancel")
def cancel_collection(job_id: str, request: Request):
    services = get_services(request)
    services.jobs.cancel(job_id, actor(request))
    return {"cancelled": True}


@router.get("/api/v1/cloud/snapshots", response_model=list[SnapshotView])
def account_snapshots(request: Request):
    return get_services(request).store.account_snapshots()
