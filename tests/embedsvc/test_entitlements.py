"""Publisher registry validation and HMAC entitlement tokens."""

from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from wcmodel.embedsvc.entitlements import (
    EXAMPLE_SECRET,
    active,
    issue_token,
    load_registry,
    origin_allowed,
    verify_token,
)


def _registry(
    tmp_path: Path,
    *,
    origins: tuple[str, ...] = ("https://news.example",),
    secret: str = "publisher-secret-that-is-longer-than-32-characters",
    browser_issue: bool = True,
    tier: str = "basic",
    max_origins: int | None = None,
) -> Path:
    cap = "" if max_origins is None else f"    max_origins: {max_origins}\n"
    rendered_origins = "\n".join(f"      - {origin}" for origin in origins)
    path = tmp_path / "publishers.yaml"
    path.write_text(
        "publishers:\n"
        "  daily-news:\n"
        "    name: Daily News\n"
        f"    tier: {tier}\n"
        "    origins:\n"
        f"{rendered_origins}\n"
        f"    secret: {secret}\n"
        "    valid_from: 2026-12-01\n"
        "    valid_until: 2027-02-28\n"
        "    tournaments: [ac2027]\n"
        f"    browser_issue: {'true' if browser_issue else 'false'}\n"
        f"{cap}"
    )
    return path


def test_registry_and_token_round_trip(tmp_path: Path):
    pub = load_registry(_registry(tmp_path))["daily-news"]
    assert pub.origins == ("https://news.example",)
    assert pub.max_origins == 1
    assert active(pub, date(2027, 1, 15))
    token = issue_token(pub, now=1_799_971_200)
    assert verify_token(pub, token, now=1_799_971_201)


@pytest.mark.parametrize(
    "mutate",
    [
        lambda token: token.rsplit(".", 1)[0] + "." + "0" * 64,
        lambda token: token.replace("daily-news", "other-news", 1),
        lambda token: ".".join([token.split(".")[0], str(int(token.split(".")[1]) + 999), token.split(".")[2]]),
        lambda token: "garbage",
        lambda token: "too.many.token.parts",
    ],
)
def test_token_rejects_forgery_wrong_publisher_and_garbage(tmp_path: Path, mutate):
    pub = load_registry(_registry(tmp_path))["daily-news"]
    token = issue_token(pub, now=1_799_971_200)
    assert not verify_token(pub, mutate(token), now=1_799_971_201)


def test_token_expiry(tmp_path: Path):
    pub = load_registry(_registry(tmp_path))["daily-news"]
    token = issue_token(pub, now=1_799_971_200, ttl=10)
    assert not verify_token(pub, token, now=1_799_971_210)


def test_default_ports_canonicalize_both_directions(tmp_path: Path):
    pub = load_registry(_registry(tmp_path, origins=("https://NEWS.example:443",)))["daily-news"]
    assert pub.origins == ("https://news.example",)
    assert origin_allowed(pub, "https://news.example:443")
    assert origin_allowed(pub, "https://NEWS.example")


def test_idn_is_stored_as_ascii_and_matches_punycode(tmp_path: Path):
    pub = load_registry(_registry(tmp_path, origins=("https://münich.example",)))["daily-news"]
    assert pub.origins == ("https://xn--mnich-kva.example",)
    assert origin_allowed(pub, "https://xn--mnich-kva.example")


@pytest.mark.parametrize("origin", ["https://x.example/path", "https://*.x.example"])
def test_path_and_wildcard_origins_are_rejected(tmp_path: Path, origin: str):
    with pytest.raises(ValueError, match="origins"):
        load_registry(_registry(tmp_path, origins=(origin,)))


def test_basic_publisher_cannot_have_two_origins(tmp_path: Path):
    with pytest.raises(ValueError, match="max_origins"):
        load_registry(
            _registry(tmp_path, origins=("https://a.example", "https://b.example"))
        )


def test_example_secret_is_rejected(tmp_path: Path):
    with pytest.raises(ValueError, match="example secret"):
        load_registry(_registry(tmp_path, secret=EXAMPLE_SECRET))


def test_server_issued_publisher_flag_is_recorded(tmp_path: Path):
    pub = load_registry(_registry(tmp_path, browser_issue=False))["daily-news"]
    assert pub.browser_issue is False


def test_registry_collects_multiple_validation_errors(tmp_path: Path):
    path = _registry(tmp_path, secret="short")
    text = path.read_text().replace("daily-news:", "Bad PID!:").replace(
        "valid_until: 2027-02-28", "valid_until: not-a-date"
    )
    path.write_text(text)
    with pytest.raises(ValueError) as exc:
        load_registry(path)
    assert "pid" in str(exc.value)
    assert "secret" in str(exc.value)
    assert "valid_until" in str(exc.value)
