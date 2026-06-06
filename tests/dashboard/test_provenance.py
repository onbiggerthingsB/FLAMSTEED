import pandas as pd
from wcmodel.dashboard.provenance import Provenance, stamp


def test_provenance_carries_cutoff_key_git_and_taint():
    p = Provenance(cutoff="2026-06-11T00:00:00Z", posterior_key="abc123",
                   git="deadbeef", is_synthetic=True, n_sims=20000)
    env = stamp({"hello": 1}, p)
    assert env["provenance"]["as_of"] == "2026-06-11T00:00:00Z"
    assert env["provenance"]["posterior_key"] == "abc123"
    assert env["provenance"]["git"] == "deadbeef"
    assert env["provenance"]["is_synthetic"] is True
    assert env["provenance"]["n_sims"] == 20000
    assert env["provenance"]["banner"]            # DRY-RUN banner present when synthetic
    assert env["data"] == {"hello": 1}            # payload preserved under "data"


def test_real_stamp_has_no_dryrun_banner():
    p = Provenance(cutoff="2026-06-11T00:00:00Z", posterior_key="k", git="g",
                   is_synthetic=False, n_sims=1)
    env = stamp({}, p)
    assert env["provenance"]["banner"] is None    # a real snapshot carries no NON-REAL banner
