"""Private, checksummed deployment archives with bounded, allowlisted extraction."""

from pathlib import Path
import hashlib
import json
import re
import tarfile
import tempfile

FORMAT = "cloudsentinel-postgres-backup-v1"
MAX_BYTES = 10 * 1024 * 1024 * 1024


def digest(path: Path):
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def write_archive(staging: Path, destination: Path):
    if destination.exists():
        raise ValueError("Use a fresh backup filename; archives are not overwritten.")
    files = sorted(file for file in staging.rglob("*") if file.is_file())
    if not (staging / "database.dump").is_file() or any(file.is_symlink() for file in files):
        raise ValueError("A database dump and regular model files are required.")
    manifest = {
        "format": FORMAT,
        "files": {str(file.relative_to(staging)): digest(file) for file in files},
        "restore_policy": "Revoke sessions, pause schedules, cancel pending jobs, suppress pending email.",
    }
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2))
    destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
    with tempfile.NamedTemporaryFile(
        dir=destination.parent, prefix=".backup-", delete=False
    ) as stream:
        temporary = Path(stream.name)
    try:
        with tarfile.open(temporary, "w:gz") as archive:
            for file in sorted(file for file in staging.rglob("*") if file.is_file()):
                archive.add(file, arcname=str(file.relative_to(staging)))
        temporary.chmod(0o600)
        temporary.replace(destination)
    finally:
        temporary.unlink(missing_ok=True)


def read_archive(source: Path, staging: Path):
    names = set()
    size = 0
    with tarfile.open(source, "r:gz") as archive:
        for index, member in enumerate(archive):
            path = Path(member.name)
            allowed = member.name in ("manifest.json", "database.dump") or (
                len(path.parts) == 2
                and path.parts[0] == "models"
                and (
                    path.name == "active.json"
                    or re.fullmatch(r"[a-zA-Z0-9._-]+\.joblib", path.name)
                )
            )
            size += member.size
            if (
                index >= 10000
                or size > MAX_BYTES
                or not member.isfile()
                or not allowed
                or path.is_absolute()
                or ".." in path.parts
                or member.name in names
            ):
                raise ValueError("Archive exceeds its bounds or contains an unsafe path.")
            if member.name == "manifest.json" and member.size > 2 * 1024 * 1024:
                raise ValueError("Archive manifest exceeds its size limit.")
            names.add(member.name)
            stream = archive.extractfile(member)
            if stream is None:
                raise ValueError("Archive contains an unreadable file.")
            destination = staging / path
            destination.parent.mkdir(parents=True, exist_ok=True, mode=0o700)
            with stream, destination.open("wb") as target:
                import shutil

                shutil.copyfileobj(stream, target)
            destination.chmod(0o600)
    if not {"manifest.json", "database.dump"}.issubset(names):
        raise ValueError("Archive is missing its database dump or manifest.")
    manifest = json.loads((staging / "manifest.json").read_text())
    if (
        not isinstance(manifest, dict)
        or manifest.get("format") != FORMAT
        or not isinstance(manifest.get("files"), dict)
        or set(manifest.get("files", {})) != names - {"manifest.json"}
    ):
        raise ValueError("Archive manifest does not match its contents.")
    for name, expected in manifest["files"].items():
        if digest(staging / name) != expected:
            raise ValueError("Archive checksum validation failed.")
