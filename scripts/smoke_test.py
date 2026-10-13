"""Read-only smoke test of an already running local demo server."""
import json
from urllib.error import URLError
from urllib.request import urlopen

BASE = "http://127.0.0.1:8000"
try:
    for path in ("/api/v1/health", "/api/v1/scans/latest", "/api/v1/scans", "/api/v1/rules", "/api/v1/export"):
        with urlopen(BASE + path, timeout=5) as response:
            assert response.status == 200
            value = json.load(response)
            if path.endswith("latest"):
                assert value["summary"]["resources"] >= 1
                assert value["source"] in ("demo", "import")
            print(f"PASS {path}")
    with urlopen(BASE, timeout=5) as response:
        assert response.status == 200
        assert b"CloudSentinel" in response.read()
        print("PASS dashboard HTML")
except (URLError, TimeoutError) as exc:
    raise SystemExit(f"Local demo unavailable: {exc}. Start it with: bash scripts/demo.sh")
