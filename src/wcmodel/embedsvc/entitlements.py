"""Publisher registry and browser-grade entitlement tokens.

`Origin` is a browser-supplied header; any `curl -H 'Origin: https://publisher.example'` can obtain and replay a token. Therefore:

- **What the Origin+token pair actually provides:** browser-grade hotlink deterrence (a third-party *site* cannot silently embed the widget, because real browsers send their own Origin), per-publisher revocation, tier gating, and metering. **It is NOT authentication of the requester.**
- **The genuinely enforceable control** for a publisher who wants it: **server-side issuance** — the publisher's own server holds their secret and mints tokens (`issue_token`) for their pages; the gateway never issues to a browser for that publisher (`browser_issue: false` in the registry). Offered in the rate card as the "server-issued" option.
- **The commercial control is contractual**, backed by metering and revocation. The runbook and the plan say this in those words; no document in this repo may claim the pair "proves" entitlement.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
import hashlib
import hmac
import ipaddress
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit

import yaml


EXAMPLE_SECRET = "replace-with-a-unique-32-character-secret"
_PID = re.compile(r"^[a-z0-9][a-z0-9_-]{1,31}$")
_TOURNAMENT = re.compile(r"^[a-z0-9]{2,16}$")
_TIER_CAPS = {"basic": 1, "advanced": 3}


@dataclass(frozen=True)
class Publisher:
    pid: str
    name: str
    tier: str
    origins: tuple[str, ...]
    secret: str
    valid_from: date
    valid_until: date
    tournaments: tuple[str, ...]
    browser_issue: bool
    max_origins: int


def _canonical_origin(origin: str) -> str:
    if not isinstance(origin, str) or not origin or origin != origin.strip():
        raise ValueError("must be a non-empty origin without surrounding whitespace")
    if "*" in origin:
        raise ValueError("wildcards are not allowed")
    try:
        parts = urlsplit(origin)
    except ValueError as exc:
        raise ValueError(f"cannot be parsed: {exc}") from exc
    scheme = parts.scheme.lower()
    if scheme not in {"https", "http"}:
        raise ValueError("scheme must be https (or http for localhost)")
    if parts.username is not None or parts.password is not None:
        raise ValueError("userinfo is not allowed")
    if not parts.netloc or parts.hostname is None:
        raise ValueError("host is required")
    if parts.path or parts.query or parts.fragment:
        raise ValueError("path, query, and fragment are not allowed")
    try:
        port = parts.port
    except ValueError as exc:
        raise ValueError(f"port is invalid: {exc}") from exc
    if port is not None and not 1 <= port <= 65535:
        raise ValueError("port must be between 1 and 65535")

    raw_host = parts.hostname.lower()
    try:
        host = raw_host.encode("idna").decode("ascii").lower()
    except (UnicodeError, UnicodeEncodeError) as exc:
        raise ValueError("host cannot be IDNA-encoded") from exc
    if not host or any(char.isspace() for char in host):
        raise ValueError("host is invalid")

    is_local = host == "localhost"
    try:
        is_local = is_local or ipaddress.ip_address(host).is_loopback
    except ValueError:
        pass
    if scheme == "http" and not is_local:
        raise ValueError("http is allowed only for localhost")

    if (scheme, port) in {("https", 443), ("http", 80)}:
        port = None
    rendered_host = f"[{host}]" if ":" in host else host
    return f"{scheme}://{rendered_host}{f':{port}' if port is not None else ''}"


def _parse_date(value: Any, field: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if not isinstance(value, str):
        raise ValueError(f"{field} must be an ISO date")
    try:
        return date.fromisoformat(value)
    except ValueError as exc:
        raise ValueError(f"{field} must be an ISO date") from exc


def _publisher_rows(document: Any) -> list[tuple[Any, Any]]:
    if not isinstance(document, dict) or "publishers" not in document:
        raise ValueError("registry must contain a publishers mapping or list")
    publishers = document["publishers"]
    if isinstance(publishers, dict):
        return list(publishers.items())
    if isinstance(publishers, list):
        rows: list[tuple[Any, Any]] = []
        for item in publishers:
            if isinstance(item, dict):
                rows.append((item.get("pid"), item))
            else:
                rows.append((None, item))
        return rows
    raise ValueError("publishers must be a mapping or list")


def load_registry(path: str | Path) -> dict[str, Publisher]:
    """Load a publisher registry, collecting every publisher validation error."""
    try:
        document = yaml.safe_load(Path(path).read_text())
        rows = _publisher_rows(document)
    except (OSError, yaml.YAMLError, ValueError) as exc:
        raise ValueError(f"invalid publisher registry: {exc}") from exc

    errors: list[str] = []
    registry: dict[str, Publisher] = {}
    for raw_pid, raw in rows:
        before = len(errors)
        label = str(raw_pid) if raw_pid is not None else "<missing>"
        if not isinstance(raw, dict):
            errors.append(f"{label}: publisher entry must be a mapping")
            continue
        pid = raw_pid
        if not isinstance(pid, str) or not _PID.fullmatch(pid):
            errors.append(f"{label}: pid must match {_PID.pattern}")

        name = raw.get("name")
        if not isinstance(name, str) or not name.strip():
            errors.append(f"{label}: name must be a non-empty string")

        tier = raw.get("tier")
        if tier not in _TIER_CAPS:
            errors.append(f"{label}: tier must be basic or advanced")
        tier_cap = _TIER_CAPS.get(tier, 1)

        raw_cap = raw.get("max_origins", tier_cap)
        if (
            isinstance(raw_cap, bool)
            or not isinstance(raw_cap, int)
            or raw_cap < 1
            or raw_cap > tier_cap
        ):
            errors.append(
                f"{label}: max_origins must be between 1 and the {tier!r} tier cap {tier_cap}"
            )
            max_origins = tier_cap
        else:
            max_origins = raw_cap

        raw_origins = raw.get("origins")
        origins: list[str] = []
        if not isinstance(raw_origins, list) or not raw_origins:
            errors.append(f"{label}: origins must be a non-empty list")
        else:
            for index, origin in enumerate(raw_origins):
                try:
                    origins.append(_canonical_origin(origin))
                except (TypeError, ValueError) as exc:
                    errors.append(f"{label}: origins[{index}] {exc}")
        if len(origins) > max_origins:
            errors.append(
                f"{label}: {len(origins)} origins exceeds max_origins={max_origins}"
            )
        if len(set(origins)) != len(origins):
            errors.append(f"{label}: origins must be unique after canonicalization")

        secret = raw.get("secret")
        if not isinstance(secret, str) or len(secret) < 32:
            errors.append(f"{label}: secret must contain at least 32 characters")
        elif secret == EXAMPLE_SECRET:
            errors.append(f"{label}: example secret must be replaced")

        valid_from = valid_until = date.min
        try:
            valid_from = _parse_date(raw.get("valid_from"), "valid_from")
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
        try:
            valid_until = _parse_date(raw.get("valid_until"), "valid_until")
        except ValueError as exc:
            errors.append(f"{label}: {exc}")
        if valid_from != date.min and valid_until != date.min and valid_until < valid_from:
            errors.append(f"{label}: valid_until must be on or after valid_from")

        raw_tournaments = raw.get("tournaments")
        tournaments: list[str] = []
        if not isinstance(raw_tournaments, list) or not raw_tournaments:
            errors.append(f"{label}: tournaments must be a non-empty list")
        else:
            for tournament in raw_tournaments:
                if not isinstance(tournament, str) or not _TOURNAMENT.fullmatch(tournament):
                    errors.append(
                        f"{label}: tournament {tournament!r} must match {_TOURNAMENT.pattern}"
                    )
                else:
                    tournaments.append(tournament)

        browser_issue = raw.get("browser_issue")
        if not isinstance(browser_issue, bool):
            errors.append(f"{label}: browser_issue must be true or false")

        if len(errors) == before:
            assert isinstance(pid, str)
            registry[pid] = Publisher(
                pid=pid,
                name=name.strip(),
                tier=tier,
                origins=tuple(origins),
                secret=secret,
                valid_from=valid_from,
                valid_until=valid_until,
                tournaments=tuple(tournaments),
                browser_issue=browser_issue,
                max_origins=max_origins,
            )

    if errors:
        raise ValueError("invalid publisher registry:\n- " + "\n- ".join(errors))
    return registry


def origin_allowed(pub: Publisher, origin: str | None) -> bool:
    if origin is None:
        return False
    try:
        return _canonical_origin(origin) in pub.origins
    except (TypeError, ValueError):
        return False


def active(pub: Publisher, on_day: date) -> bool:
    return pub.valid_from <= on_day <= pub.valid_until


def _timestamp(now: int | float | datetime) -> int:
    if isinstance(now, datetime):
        return int(now.timestamp())
    return int(now)


def issue_token(pub: Publisher, *, now: int | float | datetime, ttl: int = 900) -> str:
    exp = _timestamp(now) + int(ttl)
    message = f"{pub.pid}.{exp}"
    signature = hmac.new(
        pub.secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256
    ).hexdigest()
    return f"{message}.{signature}"


def verify_token(
    pub: Publisher, token: str, *, now: int | float | datetime
) -> bool:
    try:
        pid, raw_exp, supplied = token.split(".")
        if pid != pub.pid or not raw_exp.isascii() or not raw_exp.isdigit():
            return False
        exp = int(raw_exp)
        if exp <= _timestamp(now):
            return False
        message = f"{pid}.{exp}"
        expected = hmac.new(
            pub.secret.encode("utf-8"), message.encode("ascii"), hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(supplied, expected)
    except (AttributeError, TypeError, ValueError, OverflowError):
        return False
