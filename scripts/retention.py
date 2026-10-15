"""Review old evidence before explicitly applying retention; default is dry-run."""

import argparse
import json
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from backend.app.core.config import Settings
from backend.app.repositories.store import Store
from backend.app.services.retention import Retention


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--days", type=int, default=90)
    parser.add_argument("--apply", action="store_true")
    args = parser.parse_args()
    settings = Settings.from_env()
    store = Store(
        settings.database_path,
        settings.database_url.get_secret_value() if settings.database_url else None,
    )
    try:
        print(json.dumps(Retention(store).run(args.days, args.apply), indent=2))
    finally:
        store.database.close()


if __name__ == "__main__":
    main()
