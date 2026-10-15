"""Provider SDK credential factories. Credentials are obtained in the worker only.

AWS role credentials are short-lived. Azure credentials are an explicitly chosen
managed/workload identity. GCP uses refreshable ADC or service-account impersonation.
No access keys, OAuth bearer tokens, or client secrets are stored in the registry.
"""

from contextlib import ExitStack
from pathlib import Path
import json
import os

from backend.app.infrastructure.collectors.base import CollectionError, RestClient


class ManagedSession:
    """Release every per-job SDK client, including clients created by nested reads."""

    def __init__(self, session, stack):
        self.session, self.stack = session, stack

    def client(self, *args, **kwargs):
        client = self.session.client(*args, **kwargs)
        self.stack.callback(client.close)
        return client


class AzureToken:
    def __init__(self, credential):
        self.credential = credential

    def __call__(self):
        return self.credential.get_token("https://management.azure.com/.default").token


class GoogleToken:
    def __init__(self, credential, transport):
        self.credential, self.transport = credential, transport

    def __call__(self):
        if not self.credential.valid:

            def bounded_request(*args, **kwargs):
                kwargs["timeout"] = 10
                return self.transport(*args, **kwargs)

            self.credential.refresh(bounded_request)
        return self.credential.token


def aws_session(account, region):
    import boto3
    from botocore.config import Config

    session = boto3.Session(region_name=region)
    if account.auth != "assume_role":
        return session
    sts = session.client(
        "sts",
        config=Config(
            connect_timeout=5, read_timeout=10, retries={"max_attempts": 2, "mode": "standard"}
        ),
    )
    try:
        credentials = sts.assume_role(
            RoleArn=account.aws_role_arn,
            ExternalId=account.aws_external_id,
            RoleSessionName="cloudsentinel-collection",
            DurationSeconds=900,
        )["Credentials"]
    finally:
        sts.close()
    return boto3.Session(
        aws_access_key_id=credentials["AccessKeyId"],
        aws_secret_access_key=credentials["SecretAccessKey"],
        aws_session_token=credentials["SessionToken"],
        region_name=region,
    )


def azure_credential(account):
    from azure.identity import ManagedIdentityCredential, WorkloadIdentityCredential

    if account.auth == "managed_identity":
        return ManagedIdentityCredential(
            connection_timeout=5,
            read_timeout=10,
            retry_total=2,
            **({"client_id": account.azure_client_id} if account.azure_client_id else {}),
        )
    return WorkloadIdentityCredential(
        tenant_id=account.azure_tenant_id,
        client_id=account.azure_client_id,
        connection_timeout=5,
        read_timeout=10,
        retry_total=2,
    )


def google_credential(account):
    import google.auth
    from google.auth import impersonated_credentials
    from google.auth.transport.requests import Request

    filename = os.environ.get("GOOGLE_APPLICATION_CREDENTIALS")
    if filename:
        # Federated credential configurations are supported; long-lived private
        # service-account key files are deliberately excluded from deployment.
        if json.loads(Path(filename).read_text()).get("type") != "external_account":
            raise CollectionError(
                "Use workload identity federation instead of a service-account private key."
            )
    credential, _ = google.auth.default(scopes=["https://www.googleapis.com/auth/cloud-platform"])
    from google.oauth2.credentials import Credentials as UserCredentials
    from google.oauth2.service_account import Credentials as PrivateKeyCredentials

    if isinstance(credential, (UserCredentials, PrivateKeyCredentials)):
        raise CollectionError(
            "Use a workload identity or federation credential for approved cloud accounts."
        )
    if account.gcp_service_account:
        credential = impersonated_credentials.Credentials(
            source_credentials=credential,
            target_principal=account.gcp_service_account,
            target_scopes=["https://www.googleapis.com/auth/cloud-platform"],
            lifetime=900,
        )
    return credential, Request()


def collect_approved(request, account):
    """Construct provider clients per job and close transports after collection."""
    try:
        if account.provider == "aws":
            from backend.app.infrastructure.collectors.aws import collect_aws

            with ExitStack() as stack:
                return collect_aws(
                    request, ManagedSession(aws_session(account, request.region), stack)
                )
        if account.provider == "azure":
            from backend.app.infrastructure.collectors.azure import collect_azure

            with azure_credential(account) as credential:
                return collect_azure(
                    request, RestClient(AzureToken(credential), {"management.azure.com"})
                )
        from backend.app.infrastructure.collectors.gcp import collect_gcp

        credential, transport = google_credential(account)
        try:
            return collect_gcp(
                request,
                RestClient(
                    GoogleToken(credential, transport),
                    {"storage.googleapis.com", "compute.googleapis.com", "logging.googleapis.com"},
                ),
            )
        finally:
            transport.session.close()
    except CollectionError:
        raise
    except ImportError:
        raise CollectionError(
            "Install the production provider SDK requirements before live collection."
        ) from None
    except Exception:
        raise CollectionError(
            "Approved account collection failed. Review workload identity, read permissions, and network access."
        ) from None
