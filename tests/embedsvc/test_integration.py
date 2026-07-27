"""Publisher projection-to-gateway integration flow."""

from __future__ import annotations

from datetime import date
import importlib.util
import json
from pathlib import Path

import httpx

from wcmodel.embedsvc.app import make_app
from wcmodel.embedsvc.entitlements import Publisher
from wcmodel.releases.projection import scan_betting_keys, scan_betting_strings


NOW = 1_799_971_200
ORIGIN = "https://news.example"
NORMALIZED_BANNER = (
    "Model forecasts · probabilities, not picks · not betting advice"
)
BUILDER_PATH = (
    Path(__file__).resolve().parents[2] / "scripts" / "build_publisher_bundle.py"
)


def _load_builder():
    spec = importlib.util.spec_from_file_location(
        "phase2b_build_publisher_bundle", BUILDER_PATH
    )
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_dirty_staged_bundle(root: Path) -> str:
    fixture_id = "A__B__2027-01-08"
    (root / "fixtures").mkdir(parents=True)
    dirty_provenance = {
        "as_of": "2027-01-07T00:00:00Z",
        "is_synthetic": True,
        "banner": (
            "DRY-RUN · SYNTHETIC ODDS · NOT REAL — "
            "no real odds were sourced, no bet was placed"
        ),
    }
    artifacts = {
        "meta.json": {
            "provenance": dirty_provenance,
            "data": {"markets": ["champion"]},
        },
        "schedule.json": {
            "provenance": dirty_provenance,
            "data": {
                "group": [
                    {
                        "match_id": fixture_id,
                        "home": "A",
                        "away": "B",
                        "forecast_summary": {
                            "one_x_two": {"home": 0.5, "draw": 0.25, "away": 0.25},
                            "market_1x2": {
                                "home": 0.48,
                                "draw": 0.26,
                                "away": 0.26,
                            },
                        },
                        "edge": {"staked": "home", "kelly": 0.1},
                    }
                ],
                "knockout": [],
            },
        },
        "tournament.json": {
            "provenance": dirty_provenance,
            "data": {"A": {"champion": {"value": 0.5, "se": 0.01}}},
        },
        f"fixtures/{fixture_id}.json": {
            "provenance": dirty_provenance,
            "data": {
                "match_id": fixture_id,
                "forecast": {
                    "one_x_two": {"home": 0.5, "draw": 0.25, "away": 0.25}
                },
                "edge": {"entry_odds": 2.1, "stake_signal": 0.1},
            },
        },
    }
    for relative, payload in artifacts.items():
        destination = root / relative
        destination.parent.mkdir(parents=True, exist_ok=True)
        destination.write_text(json.dumps(payload))
    (root / "track.json").write_text(json.dumps({"data": {"avg_clv": 0.1}}))
    (root / "value.json").write_text(json.dumps({"data": {"bettable": []}}))
    return fixture_id


def test_dirty_staged_bundle_is_projected_and_served_clean_end_to_end(
    tmp_path: Path,
):
    staged = tmp_path / "staged"
    fixture_id = _write_dirty_staged_bundle(staged)
    bundle_root = tmp_path / "publisher-bundles"
    published = bundle_root / "ac2027"
    builder = _load_builder()
    builder.build_publisher_bundle(staged, published, tournament="ac2027")

    pub = Publisher(
        pid="daily-news",
        name="Daily News",
        tier="advanced",
        origins=(ORIGIN,),
        secret="publisher-secret-that-is-longer-than-32-characters",
        valid_from=date(2026, 12, 1),
        valid_until=date(2027, 2, 28),
        tournaments=("ac2027",),
        browser_issue=True,
        max_origins=3,
    )
    meter = tmp_path / "meter.jsonl"
    app = make_app(
        registry={pub.pid: pub},
        bundle_root=bundle_root,
        meter_path=meter,
        now_fn=lambda: NOW,
    )

    with httpx.Client(
        transport=httpx.WSGITransport(app=app),
        base_url="https://gateway.example",
    ) as client:
        token_response = client.get(
            f"/v1/token?pid={pub.pid}", headers={"Origin": ORIGIN}
        )
        assert token_response.status_code == 200
        token = token_response.json()["token"]
        headers = {"Origin": ORIGIN, "Authorization": f"Bearer {token}"}
        paths = [
            "/v1/bundle/ac2027/meta.json",
            "/v1/bundle/ac2027/schedule.json",
            "/v1/bundle/ac2027/tournament.json",
            f"/v1/bundle/ac2027/fixtures/{fixture_id}.json",
        ]
        payloads = []
        for path in paths:
            response = client.get(path, headers=headers)
            assert response.status_code == 200, (path, response.text)
            payload = response.json()
            assert scan_betting_keys(payload) == set(), path
            assert scan_betting_strings(payload) == [], path
            payloads.append(payload)

    meta = payloads[0]
    assert meta["provenance"]["banner"] == NORMALIZED_BANNER
    assert "is_synthetic" not in meta["provenance"]
    assert not (published / "track.json").exists()
    assert not (published / "value.json").exists()
    records = [json.loads(line) for line in meter.read_text().splitlines()]
    assert [record["path_class"] for record in records] == [
        "token",
        "bundle",
        "bundle",
        "bundle",
        "fixture",
    ]
    assert all(record["pid"] == pub.pid for record in records)
