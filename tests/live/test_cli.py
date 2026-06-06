from wcmodel.live.cli import run_live_scan, run_live_scan_dry, build_arg_parser


def test_cli_defaults_to_dry_run(cfg):
    # The CLI is dry-run by default (the spend/safety gate): no api_key, no spend.
    parser = build_arg_parser()
    args = parser.parse_args([])               # no flags
    assert args.dry_run is True
    assert args.api_key is None


def test_cli_refuses_live_without_api_key():
    # Asking for a LIVE run (--no-dry-run) without a key is REFUSED (the gate).
    import pytest
    parser = build_arg_parser()
    args = parser.parse_args(["--no-dry-run"])
    with pytest.raises(SystemExit):
        run_live_scan(args)                    # gated: no key => refuse, never spend


def test_cli_dry_run_scan_on_synthetic_returns_ranked(small_store, cfg, tmp_path):
    # A dry-run scan over the synthetic harness returns a non-real Ranked artifact.
    from wcmodel.backtest.odds_ingest import synthetic_odds_sample
    s = synthetic_odds_sample(home="Brazil", away="Croatia",
                              commence="2024-06-30T19:00:00Z",
                              entry=(2.50, 3.40, 3.00), close=(2.10, 3.50, 3.40),
                              bookmaker="pinnacle", seed=0)
    ranked = run_live_scan_dry(
        small_store, [{"sample": s["sample"], "liquidity": 50.0}],
        cutoff="2024-06-30T19:00:00Z", config=cfg,
        fit_kwargs={"draws": 60, "advi_iters": 1500, "seed": 0})
    assert ranked.is_synthetic is True
    assert ranked.signal_only is True
