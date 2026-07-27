"""Pure-WSGI entitlement gateway for publisher bundle artifacts.

Metering intentionally fails open: a paid response remains available when the
append-only usage log cannot be written. Operators must alert on meter gaps.
"""

from __future__ import annotations

from datetime import datetime, timezone
import json
import os
from pathlib import Path
import re
from typing import Callable, Iterable, Mapping
from urllib.parse import parse_qs

from wcmodel.embedsvc.entitlements import (
    Publisher,
    active,
    issue_token,
    origin_allowed,
    verify_token,
)
from wcmodel.releases.projection import scan_betting_keys, scan_betting_strings


_TOP_ASSET = re.compile(r"^/v1/bundle/([a-z0-9]{2,16})/(meta|schedule|tournament)\.json$")
_FIXTURE_ASSET = re.compile(
    r"^/v1/bundle/([a-z0-9]{2,16})/fixtures/([A-Za-z0-9_-]+)\.json$"
)
_STATUS_TEXT = {
    200: "OK",
    204: "No Content",
    400: "Bad Request",
    403: "Forbidden",
    404: "Not Found",
    405: "Method Not Allowed",
    500: "Internal Server Error",
}


class EmbedGateway:
    """WSGI application with observable in-process meter failure count."""

    def __init__(
        self,
        *,
        registry: Mapping[str, Publisher],
        bundle_root: str | Path,
        meter_path: str | Path,
        now_fn: Callable[[], int | float],
    ) -> None:
        self.registry = dict(registry)
        self.bundle_root = Path(bundle_root)
        self.meter_path = Path(meter_path)
        self.now_fn = now_fn
        self.meter_errors = 0

    def _now(self) -> int:
        return int(self.now_fn())

    @staticmethod
    def _query(environ: dict) -> tuple[dict[str, list[str]], bool]:
        query = parse_qs(
            environ.get("QUERY_STRING", ""),
            keep_blank_values=True,
            strict_parsing=False,
        )
        duplicated = any(len(query.get(key, [])) > 1 for key in ("pid", "t"))
        return query, duplicated

    @staticmethod
    def _origin(environ: dict) -> str | None:
        value = environ.get("HTTP_ORIGIN")
        return value if isinstance(value, str) and value else None

    @staticmethod
    def _token_from_request(
        environ: dict, query: dict[str, list[str]]
    ) -> tuple[str | None, bool]:
        header = environ.get("HTTP_AUTHORIZATION", "")
        header_token = None
        if isinstance(header, str) and header.startswith("Bearer "):
            header_token = header[7:]
        query_token = query.get("t", [None])[0]
        if header_token is not None and query_token is not None:
            return None, True
        return header_token if header_token is not None else query_token, False

    def _pub_from_token(self, token: str | None) -> Publisher | None:
        if not isinstance(token, str):
            return None
        pid = token.split(".", 1)[0]
        return self.registry.get(pid)

    def _cors_pub_for_origin(self, origin: str | None) -> Publisher | None:
        if origin is None:
            return None
        return next(
            (pub for pub in self.registry.values() if origin_allowed(pub, origin)),
            None,
        )

    @staticmethod
    def _headers(
        *,
        origin: str | None,
        cors_pub: Publisher | None,
        cache_control: str | None = None,
        content_type: str | None = None,
        extra: Iterable[tuple[str, str]] = (),
    ) -> list[tuple[str, str]]:
        headers = [("X-Content-Type-Options", "nosniff")]
        if content_type:
            headers.append(("Content-Type", content_type))
        if cache_control:
            headers.append(("Cache-Control", cache_control))
        if origin is not None and cors_pub is not None and origin_allowed(cors_pub, origin):
            headers.extend(
                [("Access-Control-Allow-Origin", origin), ("Vary", "Origin")]
            )
        headers.extend(extra)
        return headers

    def _respond(
        self,
        start_response,
        status: int,
        payload: dict | None,
        *,
        origin: str | None,
        cors_pub: Publisher | None,
        cache_control: str | None = None,
        extra: Iterable[tuple[str, str]] = (),
    ) -> list[bytes]:
        body = b"" if payload is None else json.dumps(payload, separators=(",", ":")).encode("utf-8")
        headers = self._headers(
            origin=origin,
            cors_pub=cors_pub,
            cache_control=cache_control,
            content_type="application/json; charset=utf-8" if payload is not None else None,
            extra=extra,
        )
        headers.append(("Content-Length", str(len(body))))
        start_response(f"{status} {_STATUS_TEXT[status]}", headers)
        return [body]

    def _meter(self, *, now: int, pub: Publisher, path_class: str) -> None:
        record = {
            "day": datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat(),
            "pid": pub.pid,
            "path_class": path_class,
        }
        line = (json.dumps(record, separators=(",", ":")) + "\n").encode("ascii")
        if len(line) > 200:  # Defensive invariant; all fields are bounded at validation.
            self.meter_errors += 1
            return
        fd = None
        try:
            fd = os.open(
                self.meter_path,
                os.O_WRONLY | os.O_APPEND | os.O_CREAT,
                0o600,
            )
            written = os.write(fd, line)  # one append write: do not split this record
            if written != len(line):
                self.meter_errors += 1
        except OSError:
            self.meter_errors += 1
        finally:
            if fd is not None:
                try:
                    os.close(fd)
                except OSError:
                    pass

    def _options(self, environ: dict, start_response, origin: str | None):
        cors_pub = self._cors_pub_for_origin(origin)
        return self._respond(
            start_response,
            204,
            None,
            origin=origin,
            cors_pub=cors_pub,
            cache_control="no-store",
            extra=(
                ("Access-Control-Allow-Methods", "GET"),
                ("Access-Control-Allow-Headers", "Authorization"),
                ("Access-Control-Max-Age", "600"),
            ),
        )

    def _token(self, query: dict[str, list[str]], start_response, origin: str | None):
        pid = query.get("pid", [""])[0]
        pub = self.registry.get(pid)
        cors_pub = pub if pub is not None and origin_allowed(pub, origin) else None
        now = self._now()
        on_day = datetime.fromtimestamp(now, tz=timezone.utc).date()
        if (
            pub is None
            or not origin_allowed(pub, origin)
            or not active(pub, on_day)
            or not pub.browser_issue
        ):
            return self._respond(
                start_response,
                403,
                {"error": "forbidden"},
                origin=origin,
                cors_pub=cors_pub,
                cache_control="no-store",
            )
        token = issue_token(pub, now=now)
        exp = int(token.split(".")[1])
        self._meter(now=now, pub=pub, path_class="token")
        return self._respond(
            start_response,
            200,
            {"token": token, "exp": exp, "tier": pub.tier},
            origin=origin,
            cors_pub=pub,
            cache_control="no-store",
        )

    def _bundle(
        self,
        environ: dict,
        query: dict[str, list[str]],
        start_response,
        origin: str | None,
    ):
        token, conflicting_token = self._token_from_request(environ, query)
        pub = self._pub_from_token(token)
        cors_pub = pub if pub is not None and origin_allowed(pub, origin) else None
        if conflicting_token:
            return self._respond(
                start_response,
                400,
                {"error": "bad_request"},
                origin=origin,
                cors_pub=cors_pub,
                cache_control="no-store",
            )

        path = environ.get("PATH_INFO", "")
        top = _TOP_ASSET.fullmatch(path)
        fixture = _FIXTURE_ASSET.fullmatch(path)
        if top:
            tournament, stem = top.groups()
            relative = Path(f"{stem}.json")
            path_class = "bundle"
        elif fixture:
            tournament, fixture_id = fixture.groups()
            relative = Path("fixtures") / f"{fixture_id}.json"
            path_class = "fixture"
        else:
            return self._respond(
                start_response,
                404,
                {"error": "not_found"},
                origin=origin,
                cors_pub=cors_pub,
                cache_control="no-store",
            )

        now = self._now()
        on_day = datetime.fromtimestamp(now, tz=timezone.utc).date()
        if (
            pub is None
            or not origin_allowed(pub, origin)
            or not active(pub, on_day)
            or tournament not in pub.tournaments
            or not verify_token(pub, token, now=now)
            or (fixture is not None and pub.tier != "advanced")
        ):
            return self._respond(
                start_response,
                403,
                {"error": "forbidden"},
                origin=origin,
                cors_pub=cors_pub,
                cache_control="no-store",
            )

        asset = self.bundle_root / tournament / relative
        try:
            body = asset.read_bytes()
        except FileNotFoundError:
            return self._respond(
                start_response,
                404,
                {"error": "not_found"},
                origin=origin,
                cors_pub=pub,
                cache_control="private, max-age=60",
            )
        except OSError:
            return self._respond(
                start_response,
                500,
                {"error": "bundle"},
                origin=origin,
                cors_pub=pub,
                cache_control="private, max-age=60",
            )
        try:
            decoded = json.loads(body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._respond(
                start_response,
                500,
                {"error": "integrity"},
                origin=origin,
                cors_pub=pub,
                cache_control="private, max-age=60",
            )
        if scan_betting_keys(decoded) or scan_betting_strings(decoded):
            return self._respond(
                start_response,
                500,
                {"error": "integrity"},
                origin=origin,
                cors_pub=pub,
                cache_control="private, max-age=60",
            )

        self._meter(now=now, pub=pub, path_class=path_class)
        headers = self._headers(
            origin=origin,
            cors_pub=pub,
            cache_control="private, max-age=60",
            content_type="application/json; charset=utf-8",
        )
        headers.append(("Content-Length", str(len(body))))
        start_response("200 OK", headers)
        return [body]

    def __call__(self, environ: dict, start_response):
        origin = self._origin(environ)
        method = environ.get("REQUEST_METHOD", "GET").upper()
        if method == "OPTIONS":
            return self._options(environ, start_response, origin)
        if method != "GET":
            return self._respond(
                start_response,
                405,
                {"error": "method_not_allowed"},
                origin=origin,
                cors_pub=self._cors_pub_for_origin(origin),
                cache_control="no-store",
            )

        query, duplicated = self._query(environ)
        if duplicated:
            pid = query.get("pid", [""])[0]
            token = query.get("t", [None])[0]
            pub = self.registry.get(pid) or self._pub_from_token(token)
            cors_pub = pub if pub is not None and origin_allowed(pub, origin) else None
            return self._respond(
                start_response,
                400,
                {"error": "bad_request"},
                origin=origin,
                cors_pub=cors_pub,
                cache_control="no-store",
            )
        if environ.get("PATH_INFO") == "/v1/token":
            return self._token(query, start_response, origin)
        if environ.get("PATH_INFO") == "/v1/status":
            tournaments: dict[str, str | None] = {}
            for meta_path in sorted(self.bundle_root.glob("*/meta.json")):
                try:
                    meta = json.loads(meta_path.read_text())
                    tournaments[meta_path.parent.name] = meta.get("provenance", {}).get(
                        "as_of"
                    )
                except (OSError, json.JSONDecodeError, AttributeError):
                    tournaments[meta_path.parent.name] = None
            return self._respond(
                start_response,
                200,
                {"ok": True, "tournaments": tournaments},
                origin=origin,
                cors_pub=self._cors_pub_for_origin(origin),
                cache_control="public, max-age=60",
            )
        if str(environ.get("PATH_INFO", "")).startswith("/v1/bundle/"):
            return self._bundle(environ, query, start_response, origin)
        return self._respond(
            start_response,
            404,
            {"error": "not_found"},
            origin=origin,
            cors_pub=self._cors_pub_for_origin(origin),
            cache_control="no-store",
        )


def make_app(
    *,
    registry: Mapping[str, Publisher],
    bundle_root: str | Path,
    meter_path: str | Path,
    now_fn: Callable[[], int | float] | None = None,
) -> EmbedGateway:
    return EmbedGateway(
        registry=registry,
        bundle_root=bundle_root,
        meter_path=meter_path,
        now_fn=now_fn or __import__("time").time,
    )
