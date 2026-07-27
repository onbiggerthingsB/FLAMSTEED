"""Entitled iframe route and frame-context gateway access."""

from __future__ import annotations

from datetime import date
import hashlib
import hmac
import json
from pathlib import Path

import httpx

from wcmodel.embedsvc.app import make_app
from wcmodel.embedsvc.entitlements import Publisher


NOW = 1_799_971_200
PUBLISHER_ORIGIN = "https://news.example"
GATEWAY_ORIGIN = "https://gateway.example"


def _publisher(*, browser_issue: bool = False) -> Publisher:
    return Publisher(
        pid="daily-news",
        name="Daily News",
        tier="advanced",
        origins=(PUBLISHER_ORIGIN,),
        secret="publisher-secret-that-is-longer-than-32-characters",
        valid_from=date(2026, 12, 1),
        valid_until=date(2027, 2, 28),
        tournaments=("ac2027",),
        browser_issue=browser_issue,
        max_origins=3,
    )


def _frame_key(pub: Publisher) -> str:
    return hmac.new(
        pub.secret.encode("utf-8"),
        f"frame.{pub.pid}".encode("ascii"),
        hashlib.sha256,
    ).hexdigest()


def _bundle(root: Path) -> None:
    target = root / "ac2027"
    target.mkdir(parents=True)
    clean = {
        "provenance": {
            "as_of": "2027-01-07T00:00:00Z",
            "banner": "Model forecasts · probabilities, not picks · not betting advice",
        },
        "data": {"markets": ["champion"]},
    }
    (target / "meta.json").write_text(json.dumps(clean))


def test_frame_requires_key_and_sets_publisher_frame_ancestors(tmp_path: Path):
    pub = _publisher()
    frame = tmp_path / "embed-frame.html"
    frame.write_text("<!doctype html><title>Publisher forecasts</title>")
    app = make_app(
        registry={pub.pid: pub},
        bundle_root=tmp_path / "bundles",
        meter_path=tmp_path / "meter.jsonl",
        frame_path=frame,
        now_fn=lambda: NOW,
    )

    with httpx.Client(
        transport=httpx.WSGITransport(app=app), base_url=GATEWAY_ORIGIN
    ) as client:
        for query in ("", "?k=wrong"):
            denied = client.get(f"/v1/frame/{pub.pid}{query}")
            assert denied.status_code == 403
        response = client.get(f"/v1/frame/{pub.pid}?k={_frame_key(pub)}")

    assert response.status_code == 200
    assert response.text == frame.read_text()
    assert response.headers["content-type"] == "text/html; charset=utf-8"
    assert response.headers["cache-control"] == "no-store"
    assert (
        response.headers["content-security-policy"]
        == f"frame-ancestors {PUBLISHER_ORIGIN}"
    )
    assert response.headers["x-content-type-options"] == "nosniff"


def test_frame_context_can_issue_and_use_token_only_with_same_key(tmp_path: Path):
    pub = _publisher(browser_issue=False)
    bundle_root = tmp_path / "bundles"
    _bundle(bundle_root)
    frame = tmp_path / "embed-frame.html"
    frame.write_text("<!doctype html>")
    app = make_app(
        registry={pub.pid: pub},
        bundle_root=bundle_root,
        meter_path=tmp_path / "meter.jsonl",
        frame_path=frame,
        now_fn=lambda: NOW,
    )
    key = _frame_key(pub)

    with httpx.Client(
        transport=httpx.WSGITransport(app=app), base_url=GATEWAY_ORIGIN
    ) as client:
        token_response = client.get(
            f"/v1/token?pid={pub.pid}&k={key}",
            headers={"Origin": GATEWAY_ORIGIN},
        )
        assert token_response.status_code == 200
        assert (
            token_response.headers["access-control-allow-origin"] == GATEWAY_ORIGIN
        )
        token = token_response.json()["token"]

        bundle_response = client.get(
            f"/v1/bundle/ac2027/meta.json?t={token}&k={key}",
            headers={"Origin": GATEWAY_ORIGIN},
        )
        assert bundle_response.status_code == 200
        assert (
            bundle_response.headers["access-control-allow-origin"] == GATEWAY_ORIGIN
        )

        denied = client.get(
            f"/v1/bundle/ac2027/meta.json?t={token}&k=wrong",
            headers={"Origin": GATEWAY_ORIGIN},
        )
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers


def test_frame_route_rejects_unknown_or_inactive_publisher(tmp_path: Path):
    pub = _publisher()
    inactive = Publisher(
        **{**pub.__dict__, "valid_until": date(2027, 1, 1)}
    )
    frame = tmp_path / "embed-frame.html"
    frame.write_text("<!doctype html>")
    app = make_app(
        registry={inactive.pid: inactive},
        bundle_root=tmp_path,
        meter_path=tmp_path / "meter.jsonl",
        frame_path=frame,
        now_fn=lambda: NOW,
    )
    with httpx.Client(
        transport=httpx.WSGITransport(app=app), base_url=GATEWAY_ORIGIN
    ) as client:
        inactive_response = client.get(
            f"/v1/frame/{inactive.pid}?k={_frame_key(inactive)}"
        )
        unknown_response = client.get("/v1/frame/unknown?k=anything")
    assert inactive_response.status_code == 403
    assert unknown_response.status_code == 403
