"""WSGI gateway authorization, CORS, integrity, and metering."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
import json
from pathlib import Path

import httpx
import pytest

from wcmodel.embedsvc.app import make_app
from wcmodel.embedsvc.entitlements import Publisher, issue_token


NOW = 1_799_971_200  # 2027-01-15 UTC, inside the example entitlement window
ORIGIN = "https://news.example"


def _publisher(*, tier: str = "advanced", browser_issue: bool = True) -> Publisher:
    from datetime import date

    return Publisher(
        pid="daily-news",
        name="Daily News",
        tier=tier,
        origins=(ORIGIN,),
        secret="publisher-secret-that-is-longer-than-32-characters",
        valid_from=date(2026, 12, 1),
        valid_until=date(2027, 2, 28),
        tournaments=("ac2027",),
        browser_issue=browser_issue,
        max_origins=3 if tier == "advanced" else 1,
    )


def _bundle(root: Path, *, poisoned: bool = False) -> None:
    target = root / "ac2027"
    (target / "fixtures").mkdir(parents=True)
    provenance = {
        "as_of": "2027-01-07T00:00:00Z",
        "banner": "Model forecasts · probabilities, not picks · not betting advice",
    }
    for name, data in {
        "meta.json": {"provenance": provenance, "data": {"markets": ["champion"]}},
        "schedule.json": {"provenance": provenance, "data": {"group": [], "knockout": []}},
        "tournament.json": {"provenance": provenance, "data": {"A": {"champion": {"value": 0.5}}}},
    }.items():
        (target / name).write_text(json.dumps(data))
    fixture = {"provenance": provenance, "data": {"forecast": {"home": "A"}}}
    (target / "fixtures" / "A__B__2027-01-08.json").write_text(json.dumps(fixture))
    if poisoned:
        meta = json.loads((target / "meta.json").read_text())
        meta["data"]["note"] = "synthetic odds were used"
        (target / "meta.json").write_text(json.dumps(meta))


@pytest.fixture
def gateway(tmp_path: Path):
    pub = _publisher()
    root = tmp_path / "bundles"
    _bundle(root)
    app = make_app(
        registry={pub.pid: pub},
        bundle_root=root,
        meter_path=tmp_path / "usage.jsonl",
        now_fn=lambda: NOW,
    )
    with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://gateway.example") as client:
        yield client, pub, tmp_path / "usage.jsonl"


def _token(client: httpx.Client) -> str:
    response = client.get("/v1/token?pid=daily-news", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    return response.json()["token"]


def _auth(token: str, origin: str = ORIGIN) -> dict[str, str]:
    return {"Origin": origin, "Authorization": f"Bearer {token}"}


def test_token_route_and_private_bundle(gateway):
    client, _, meter = gateway
    response = client.get("/v1/token?pid=daily-news", headers={"Origin": ORIGIN})
    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store"
    assert response.headers["access-control-allow-origin"] == ORIGIN
    token = response.json()["token"]

    response = client.get("/v1/bundle/ac2027/meta.json", headers=_auth(token))
    assert response.status_code == 200
    assert response.headers["cache-control"] == "private, max-age=60"
    assert response.headers["x-content-type-options"] == "nosniff"
    lines = [json.loads(line) for line in meter.read_text().splitlines()]
    assert [line["path_class"] for line in lines] == ["token", "bundle"]
    assert set(lines[-1]) == {"day", "pid", "path_class"}


def test_attack_matrix_and_cors_on_visible_errors(gateway):
    client, pub, _ = gateway
    good = _token(client)
    expired = issue_token(pub, now=NOW - 901)
    forged = good[:-1] + ("0" if good[-1] != "0" else "1")
    for token in (expired, forged):
        response = client.get("/v1/bundle/ac2027/meta.json", headers=_auth(token))
        assert response.status_code == 403
        assert response.headers["access-control-allow-origin"] == ORIGIN
        assert response.headers["vary"] == "Origin"

    response = client.get(
        "/v1/bundle/ac2027/meta.json", headers=_auth(good, "https://thief.example")
    )
    assert response.status_code == 403
    assert "access-control-allow-origin" not in response.headers


def test_token_refuses_denied_inactive_and_server_issue(tmp_path: Path):
    for pub in (
        _publisher(browser_issue=False),
        Publisher(**{**_publisher().__dict__, "valid_until": __import__("datetime").date(2027, 1, 1)}),
    ):
        app = make_app(registry={pub.pid: pub}, bundle_root=tmp_path, meter_path=tmp_path / "m", now_fn=lambda: NOW)
        with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
            response = client.get("/v1/token?pid=daily-news", headers={"Origin": ORIGIN})
            assert response.status_code == 403
            assert response.headers["access-control-allow-origin"] == ORIGIN
    app = make_app(registry={"daily-news": _publisher()}, bundle_root=tmp_path, meter_path=tmp_path / "m", now_fn=lambda: NOW)
    with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
        response = client.get("/v1/token?pid=daily-news", headers={"Origin": "https://thief.example"})
        assert response.status_code == 403
        assert "access-control-allow-origin" not in response.headers


def test_options_advertises_authorization(gateway):
    client, _, _ = gateway
    response = client.options("/v1/bundle/ac2027/meta.json", headers={"Origin": ORIGIN})
    assert response.status_code == 204
    assert response.headers["access-control-allow-origin"] == ORIGIN
    assert response.headers["access-control-allow-methods"] == "GET"
    assert response.headers["access-control-allow-headers"] == "Authorization"
    assert response.headers["access-control-max-age"] == "600"


@pytest.mark.parametrize(
    "path",
    ["/v1/token?pid=daily-news&pid=daily-news", "/v1/bundle/ac2027/meta.json?t=a&t=b"],
)
def test_duplicate_security_query_parameters_are_400(gateway, path: str):
    client, _, _ = gateway
    response = client.get(path, headers={"Origin": ORIGIN})
    assert response.status_code == 400


def test_percent_encoded_pid_resolves(gateway):
    client, _, _ = gateway
    response = client.get("/v1/token?pid=daily%2Dnews", headers={"Origin": ORIGIN})
    assert response.status_code == 200


def test_basic_tier_cannot_fetch_fixture(tmp_path: Path):
    pub = _publisher(tier="basic")
    root = tmp_path / "bundles"
    _bundle(root)
    app = make_app(registry={pub.pid: pub}, bundle_root=root, meter_path=tmp_path / "m", now_fn=lambda: NOW)
    token = issue_token(pub, now=NOW)
    with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
        response = client.get(
            "/v1/bundle/ac2027/fixtures/A__B__2027-01-08.json", headers=_auth(token)
        )
    assert response.status_code == 403
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_poisoned_string_triggers_integrity_500(tmp_path: Path):
    pub = _publisher()
    root = tmp_path / "bundles"
    _bundle(root, poisoned=True)
    app = make_app(registry={pub.pid: pub}, bundle_root=root, meter_path=tmp_path / "m", now_fn=lambda: NOW)
    token = issue_token(pub, now=NOW)
    with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
        response = client.get("/v1/bundle/ac2027/meta.json", headers=_auth(token))
    assert response.status_code == 500
    assert response.json() == {"error": "integrity"}
    assert response.headers["access-control-allow-origin"] == ORIGIN


def test_concurrent_meter_writers_do_not_interleave(tmp_path: Path):
    pub = _publisher()
    root, meter = tmp_path / "bundles", tmp_path / "usage.jsonl"
    _bundle(root)
    app = make_app(registry={pub.pid: pub}, bundle_root=root, meter_path=meter, now_fn=lambda: NOW)
    token = issue_token(pub, now=NOW)

    def fetch(_: int) -> int:
        with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
            return client.get("/v1/bundle/ac2027/meta.json", headers=_auth(token)).status_code

    with ThreadPoolExecutor(max_workers=12) as pool:
        assert list(pool.map(fetch, range(80))) == [200] * 80
    records = [json.loads(line) for line in meter.read_text().splitlines()]
    assert len(records) == 80
    assert all(record["pid"] == pub.pid for record in records)


def test_meter_failure_is_counted_but_paid_response_stays_available(tmp_path: Path, monkeypatch):
    pub = _publisher()
    root = tmp_path / "bundles"
    _bundle(root)
    app = make_app(registry={pub.pid: pub}, bundle_root=root, meter_path=tmp_path / "m", now_fn=lambda: NOW)
    token = issue_token(pub, now=NOW)
    monkeypatch.setattr("wcmodel.embedsvc.app.os.open", lambda *args, **kwargs: (_ for _ in ()).throw(PermissionError("no")))
    with httpx.Client(transport=httpx.WSGITransport(app=app), base_url="https://g") as client:
        response = client.get("/v1/bundle/ac2027/meta.json", headers=_auth(token))
    assert response.status_code == 200
    assert app.meter_errors == 1
