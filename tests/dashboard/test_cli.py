from wcmodel.dashboard.cli import build_arg_parser


def test_cli_defaults_to_dry_run():
    args = build_arg_parser().parse_args([])
    assert args.dry_run is True
    assert args.cutoff is None              # defaults to now at runtime
