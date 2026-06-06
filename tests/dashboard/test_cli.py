"""C6: the gated operator CLI for the v1 dashboard (SYNTHETIC DRY-RUN posture).

The CLI is the operator entry point. The #1 safety property: ``--no-dry-run`` can NEVER
reach a real feed by accident — it REFUSES (SystemExit). The tested library-level dry-run
builder (``run_build_dry``) FORCES ``dashboard.dry_run=True`` so it can never emit a
real-looking bundle, even when handed a config with ``dry_run`` somehow False.
"""
import json

import pytest

from wcmodel.dashboard.cli import build_arg_parser, run_build_dry, main
from wcmodel.backtest.odds_ingest import synthetic_odds_sample


def test_cli_defaults_to_dry_run():
    """The pre-existing scaffold contract — keep it green (parser dry-run default)."""
    args = build_arg_parser().parse_args([])
    assert args.dry_run is True
    assert args.cutoff is None              # defaults to now at runtime


@pytest.mark.slow
def test_run_build_dry_forces_non_real_full_bundle(small_store, synthetic_tournament,
                                                   tmp_path, cfg):
    """``run_build_dry`` builds the FULL bundle and FORCES NON-REAL even when the passed
    config has ``dashboard.dry_run=False``: the v1 builder can never emit a real-looking
    bundle. Every artifact is stamped ``is_synthetic=True`` with the DRY-RUN banner."""
    # A config that LIES about dry-run: dry_run=False. run_build_dry must override it.
    bad_cfg = json.loads(json.dumps(cfg))           # deep copy so we never share the fixture
    bad_cfg["dashboard"]["dry_run"] = False
    assert bad_cfg["dashboard"]["dry_run"] is False  # the trap is armed

    s = synthetic_odds_sample(home="Brazil", away="Mexico",
                              commence="2024-05-02T19:00:00Z",
                              entry=(2.5, 3.4, 3.0), close=(2.1, 3.5, 3.4), seed=0)
    b = run_build_dry(store=small_store,
                      items=[{"sample": s["sample"], "liquidity": 50.0}],
                      cutoff="2026-06-12T12:00:00Z", config=bad_cfg,
                      fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0,
                                  "cache_dir": str(tmp_path / "fc")},
                      out_root=tmp_path / "out", tournament=synthetic_tournament)

    # The FULL bundle shape: top-level artifacts + a fixtures/ dir.
    names = {p.name for p in b.glob("*.json")}
    assert {"schedule.json", "tournament.json", "track.json", "meta.json"} <= names
    assert (b / "fixtures").is_dir() and any((b / "fixtures").glob("*.json"))

    # EVERY artifact NON-REAL with a banner — even though the config claimed dry_run=False.
    for p in b.rglob("*.json"):
        env = json.loads(p.read_text())
        assert env["provenance"]["is_synthetic"] is True, f"{p.name} read as REAL"
        assert env["provenance"]["banner"], f"{p.name} missing the DRY-RUN banner"

    # The caller's config dict was NOT mutated (the forced flip is on a copy).
    assert bad_cfg["dashboard"]["dry_run"] is False


def test_run_build_dry_does_not_mutate_caller_config(small_store, synthetic_tournament,
                                                     tmp_path, cfg, monkeypatch):
    """``run_build_dry`` forces dry_run on a COPY — the caller's dict is never mutated.

    FAST: stub ``build_snapshot`` so we assert the forced-config CONTRACT (copy + flip)
    without paying for a posterior fit. The stub captures the config it was handed."""
    bad_cfg = json.loads(json.dumps(cfg))
    bad_cfg["dashboard"]["dry_run"] = False

    captured = {}

    def _stub(cutoff, *, store, config, fit_kwargs, items, out_root, tournament):
        captured["config_dry_run"] = config["dashboard"]["dry_run"]
        captured["caller_id"] = id(config)
        return tmp_path / "stub-bundle"

    monkeypatch.setattr("wcmodel.dashboard.cli.build_snapshot", _stub)

    out = run_build_dry(store=small_store, items=[], cutoff="2026-06-12T12:00:00Z",
                        config=bad_cfg, fit_kwargs={}, out_root=tmp_path / "out",
                        tournament=synthetic_tournament)
    assert out == tmp_path / "stub-bundle"
    assert captured["config_dry_run"] is True               # forced ON for the build
    assert captured["caller_id"] != id(bad_cfg)              # a COPY, not the caller's dict
    assert bad_cfg["dashboard"]["dry_run"] is False          # caller's dict untouched


def test_main_no_dry_run_refuses_systemexit(capsys):
    """``main(["--no-dry-run"])`` REFUSES (SystemExit, nonzero) — the real feed is GATED and
    can NEVER be reached by accident. No build runs."""
    with pytest.raises(SystemExit) as exc:
        main(["--no-dry-run"])
    assert exc.value.code != 0
    err = capsys.readouterr().err
    assert "GATED" in err and "pre-flip checklist" in err


def test_launcher_delegates_to_cli_main(monkeypatch):
    """The ``wc-dashboard-build`` console-script target delegates to the gated CLI.

    The entry point is ``wc_dashboard_build:main`` (a physical top-level launcher), NOT
    ``wcmodel.dashboard.cli:main`` directly — so the operator CLI survives environments
    where uv's editable ``.pth`` is skipped by ``site`` (macOS ``UF_HIDDEN``). The launcher
    must pass argv straight through to the real CLI and return its result unchanged."""
    import wc_dashboard_build

    seen = {}

    def _cli(argv=None):
        seen["argv"] = argv
        return 0

    monkeypatch.setattr("wcmodel.dashboard.cli.main", _cli)
    rc = wc_dashboard_build.main(["--dry-run", "--cutoff", "2026-06-12T12:00:00Z"])
    assert rc == 0
    assert seen["argv"] == ["--dry-run", "--cutoff", "2026-06-12T12:00:00Z"]


def test_launcher_no_dry_run_refuses_through_launcher(capsys):
    """``--no-dry-run`` still REFUSES (SystemExit) when routed through the launcher — the
    bootstrap must not weaken the real-feed gate (it just makes ``wcmodel`` importable)."""
    import wc_dashboard_build

    with pytest.raises(SystemExit) as exc:
        wc_dashboard_build.main(["--no-dry-run"])
    assert exc.value.code != 0
    assert "GATED" in capsys.readouterr().err


def test_launcher_recovers_src_from_hidden_pth(tmp_path):
    """The launcher recovers the editable src root from a ``.pth`` that ``site`` skipped.

    Simulates the failure mode hermetically: a site dir containing a ``.pth`` that records a
    src root holding a ``wcmodel`` package. ``_editable_src_roots`` must surface exactly that
    root (this is the path ``site.addpackage`` would have added were the file not hidden),
    while ignoring comment/``import`` lines and unrelated roots."""
    import wc_dashboard_build

    src_root = tmp_path / "proj" / "src"
    (src_root / "wcmodel").mkdir(parents=True)
    (src_root / "wcmodel" / "__init__.py").write_text("")
    unrelated = tmp_path / "elsewhere"
    unrelated.mkdir()

    sitedir = tmp_path / "site-packages"
    sitedir.mkdir()
    # A real editable .pth (bare path) + noise lines + an unrelated path that has no wcmodel.
    (sitedir / "_editable_impl_wcmodel.pth").write_text(str(src_root))
    (sitedir / "noise.pth").write_text(f"# comment\nimport sys\n{unrelated}\n")

    roots = wc_dashboard_build._editable_src_roots([str(sitedir)])
    assert roots == [str(src_root)]


def test_main_dry_run_routes_to_builder(monkeypatch, capsys, tmp_path):
    """The default (dry-run) path ROUTES to ``run_build_dry`` and prints the bundle path.

    FAST: stub ``run_build_dry`` so we assert the wiring (not a full fit). main must build
    over a SELF-CONTAINED synthetic harness (no pytest fixtures) and print the path."""
    called = {}

    def _stub(**kwargs):
        called["kwargs"] = kwargs
        return tmp_path / "demo-bundle"

    monkeypatch.setattr("wcmodel.dashboard.cli.run_build_dry", _stub)

    rc = main(["--dry-run", "--cutoff", "2026-06-12T12:00:00Z"])
    assert rc in (None, 0)
    out = capsys.readouterr().out
    assert "demo-bundle" in out                              # the path is printed
    assert called, "main did not route to run_build_dry"
    # main supplies its own self-contained synthetic harness (store + items + tournament).
    kw = called["kwargs"]
    assert kw["store"] is not None
    assert kw["tournament"] is not None
    assert kw["cutoff"] == "2026-06-12T12:00:00Z"
