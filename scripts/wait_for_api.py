"""Wait briefly for the development API and fail with an actionable message."""

import time
from urllib.error import URLError
from urllib.request import urlopen

for _ in range(40):
    try:
        with urlopen("http://127.0.0.1:8000/api/v1/health", timeout=1) as response:
            if response.status == 200:
                break
    except (URLError, TimeoutError):
        time.sleep(0.25)
else:
    raise SystemExit(
        "The API did not start on port 8000. Check the server output and whether the port is already in use."
    )
