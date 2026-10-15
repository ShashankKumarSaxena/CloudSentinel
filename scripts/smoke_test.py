"""Check an already running local workspace; optionally inspect signed-in routes."""

import argparse
from getpass import getpass
from http.cookiejar import CookieJar
import json
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import build_opener, HTTPCookieProcessor, HTTPRedirectHandler, Request


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError("Unexpected redirect; checks require the local workspace origin.")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", default="http://127.0.0.1:8000")
    parser.add_argument(
        "--authenticated",
        action="store_true",
        help="Prompt for credentials and inspect private routes.",
    )
    args = parser.parse_args()
    parsed = urlparse(args.base)
    if (
        parsed.scheme not in ("http", "https")
        or (parsed.scheme == "http" and parsed.hostname not in ("127.0.0.1", "localhost", "::1"))
        or parsed.username
        or parsed.password
        or parsed.query
        or parsed.fragment
        or parsed.path not in ("", "/")
    ):
        raise SystemExit(
            "Use a loopback HTTP URL or an explicit HTTPS workspace origin without credentials or a path."
        )
    base = args.base.rstrip("/")
    client = build_opener(HTTPCookieProcessor(CookieJar()), NoRedirect())

    def request(path, body=None, csrf=None):
        headers = {"Content-Type": "application/json"}
        if csrf:
            headers["X-CSRF-Token"] = csrf
        req = Request(
            base + path,
            data=json.dumps(body).encode() if body is not None else None,
            headers=headers,
        )
        with client.open(req, timeout=10) as response:
            return json.load(response)

    csrf = None
    try:
        health = request("/api/v1/health")
        assert health["status"] == "ok"
        assert health.get("mode") == "production" or health["model_ready"]
        print("PASS health and model readiness")
        setup = request("/api/v1/auth/status")
        assert setup["authentication_required"] is True
        print("PASS authentication enabled")
        try:
            request("/api/v1/scans/latest")
            raise AssertionError("Private API accepted an anonymous request.")
        except HTTPError as exc:
            assert exc.code == 401
        print("PASS anonymous workspace access rejected")
        with client.open(base, timeout=10) as response:
            assert response.status == 200 and b"CloudSentinel" in response.read()
        print("PASS dashboard HTML")
        if setup["setup_required"]:
            print(
                "SETUP REQUIRED: create the first administrator with make create-admin (or the Docker CLI command in docs/deployment.md)."
            )
            if args.authenticated:
                raise ValueError("Create an administrator before running authenticated checks.")
        else:
            assert request("/api/v1/ready")["ready"]
            print("PASS workspace readiness")
        if args.authenticated:
            username = input("Workspace username: ").strip()
            password = getpass("Workspace password: ")
            session = request("/api/v1/auth/login", {"username": username, "password": password})
            del password
            csrf = session["csrf_token"]
            for path in (
                "/auth/me",
                "/scans/latest",
                "/scans",
                "/rules",
                "/model",
                "/connectors",
                "/alerts",
                "/schedules",
                "/monitor/runs",
                "/operations",
                "/export",
            ):
                try:
                    value = request("/api/v1" + path)
                except HTTPError as exc:
                    if (
                        exc.code == 404
                        and health.get("mode") == "production"
                        and path in ("/scans/latest", "/export")
                    ):
                        print("EMPTY /api/v1" + path + " — queue the first approved collection")
                        continue
                    raise
                if path == "/scans/latest":
                    assert value["summary"]["resources"] >= 1 and value["source"] in (
                        "demo",
                        "import",
                        "live",
                    )
                print("PASS /api/v1" + path)
    except (URLError, TimeoutError, ValueError, AssertionError, KeyError, OSError):
        raise SystemExit(
            "Smoke check failed. Check the local URL, server, setup status, and credentials. Start with bash scripts/demo.sh or docker compose up -d --build."
        ) from None
    finally:
        if csrf:
            try:
                request("/api/v1/auth/logout", {}, csrf)
                print("PASS smoke-test session signed out")
            except (URLError, OSError, ValueError):
                print("Could not sign out the smoke-test session; it will expire automatically.")


if __name__ == "__main__":
    main()
