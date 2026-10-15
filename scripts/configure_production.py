"""Prepare private deployment secrets and a database TLS trust chain, offline.

This creates files only. It does not start containers, contact clouds, create
provider permissions, or publish the service. Existing deployments are never
silently overwritten; rotation is a separate operator task.
"""

import argparse
from pathlib import Path
import re
import secrets
import shutil
import subprocess
import tempfile

ROOT = Path(__file__).resolve().parents[1]


def prepare(domain: str, destination: Path):
    if (
        len(domain) > 253
        or len(domain.split(".")) < 2
        or any(
            not re.fullmatch(r"[a-z0-9](?:[a-z0-9-]{0,61}[a-z0-9])?", label)
            for label in domain.split(".")
        )
    ):
        raise ValueError("Use a valid lowercase DNS hostname without a URL, port or path.")
    if destination.exists():
        raise ValueError(
            "Choose a new private destination. Existing secrets will not be overwritten."
        )
    if not shutil.which("openssl"):
        raise ValueError("OpenSSL is required to generate the database TLS certificates.")
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.TemporaryDirectory(dir=destination.parent) as temporary:
        staging = Path(temporary)
        password = secrets.token_hex(32)
        values = {
            "database_password": password,
            "database_admin_password": secrets.token_hex(32),
            "database_url": f"postgresql://cloudsentinel:{password}@database:5432/cloudsentinel?sslmode=verify-full&sslrootcert=/run/secrets/database_ca.crt",
            "oidc_state": secrets.token_urlsafe(48),
        }
        for filename, value in values.items():
            (staging / filename).write_text(value + "\n")
        extension = staging / "server.cnf"
        extension.write_text(
            "subjectAltName=DNS:database\nbasicConstraints=CA:FALSE\nextendedKeyUsage=serverAuth\nkeyUsage=digitalSignature,keyEncipherment\n"
        )
        commands = [
            [
                "openssl",
                "req",
                "-x509",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-days",
                "3650",
                "-keyout",
                "database_ca.key",
                "-out",
                "database_ca.crt",
                "-subj",
                "/CN=CloudSentinel Database CA",
            ],
            [
                "openssl",
                "req",
                "-newkey",
                "rsa:3072",
                "-nodes",
                "-keyout",
                "database.key",
                "-out",
                "database.csr",
                "-subj",
                "/CN=database",
            ],
            [
                "openssl",
                "x509",
                "-req",
                "-in",
                "database.csr",
                "-CA",
                "database_ca.crt",
                "-CAkey",
                "database_ca.key",
                "-CAcreateserial",
                "-out",
                "database.crt",
                "-days",
                "365",
                "-extfile",
                "server.cnf",
            ],
        ]
        for command in commands:
            subprocess.run(command, cwd=staging, check=True, capture_output=True, timeout=30)
        for filename in ("server.cnf", "database.csr", "database_ca.srl"):
            (staging / filename).unlink(missing_ok=True)
        for file in staging.iterdir():
            file.chmod(0o600)
        # Compose bind-file secrets must be readable by the container UID. Their
        # host parent remains 700; private CA signing material is never mounted.
        for filename in (*values, "database_ca.crt", "database.key", "database.crt"):
            (staging / filename).chmod(0o444)
        staging.chmod(0o700)
        staging.rename(destination)
    return {"domain": domain, "secrets_directory": str(destination), "status": "prepared"}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--domain", required=True)
    parser.add_argument("--secrets-dir", type=Path, default=ROOT / "secrets/production")
    args = parser.parse_args()
    try:
        prepare(args.domain, args.secrets_dir)
    except (ValueError, OSError, subprocess.SubprocessError):
        raise SystemExit(
            "Preparation failed. Check the DNS hostname, OpenSSL, storage, and fresh secret destination. Existing files were not replaced."
        ) from None
    print("Private deployment files prepared. No services were started.")
    print(
        "Set CLOUDSENTINEL_DOMAIN in deploy/production/.env and approve accounts in config/accounts.local.json."
    )


if __name__ == "__main__":
    main()
