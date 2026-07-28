"""Import-safety + report-assembly tests for ``scripts/oa_mde.py``.

The script is THIN: a per-contrast loader, a grid runner, a PURE
``assemble_report`` and a ``main``. These tests pin (a) that loading the module
by PATH runs NO analysis and writes NO report, and (b) that the report carries
its conclusions' dependence on the NOISE MODEL, not on n alone — MDE = floor +
z*sd/sqrt(n), and sd here is a chosen arm contrast, so every headline number
moves with it and Task 7 copies those numbers into a pre-registration.

The module is loaded by PATH (``scripts/`` is not a package on ``sys.path``).
"""
from __future__ import annotations

import importlib.util
from pathlib import Path

import pytest

_ROOT = Path(__file__).resolve().parents[2]
_MODULE_PATH = _ROOT / "scripts" / "oa_mde.py"
_REPORT_PATH = _ROOT / "reports" / "oa_mde.md"

_ROWS = [(0.000, 0.03), (0.001, 0.15), (0.002, 0.51), (0.003, 0.83),
         (0.004, 0.98), (0.006, 1.00), (0.010, 1.00)]


def _load():
    spec = importlib.util.spec_from_file_location("oa_mde", str(_MODULE_PATH))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


@pytest.fixture
def mod(tmp_path, monkeypatch):
    # Load from an unrelated cwd: the script's inputs and its output path are
    # cwd-relative, so ANY module-level file access surfaces here as an error
    # rather than as a silent 26s re-run that overwrites the committed report.
    monkeypatch.chdir(tmp_path)
    return _load()


def _contrast(mod, label, sd, mde_value, *, power_null=0.03, power_max=1.0,
              floor_pass=1804, support_reject=0, min_support=0.962):
    return mod.Contrast(label=label, sd=sd, mde_value=mde_value,
                        power_null=power_null, power_max=power_max,
                        floor_pass=floor_pass, support_reject=support_reject,
                        min_support=min_support)


# --------------------------------------------------------------------------- #
# Import safety (the repo's script-test pattern executes the module).           #
# --------------------------------------------------------------------------- #
def test_import_runs_no_analysis_and_writes_no_report(tmp_path, monkeypatch):
    before = _REPORT_PATH.read_bytes()
    monkeypatch.chdir(tmp_path)
    mod = _load()
    assert callable(mod.main)
    assert _REPORT_PATH.read_bytes() == before
    assert list(tmp_path.iterdir()) == []


# --------------------------------------------------------------------------- #
# The report must condition its conclusions on the noise model.                 #
# --------------------------------------------------------------------------- #
def test_report_conditions_every_conclusion_on_the_noise_model(mod, tmp_path):
    head = _contrast(mod, "k0.5", 0.01334, 0.003)
    wide = _contrast(mod, "nuts_k0.6", 0.03261, 0.004, power_null=0.21,
                     support_reject=20, min_support=0.618)
    md = mod.assemble_report(_ROWS, [head, wide], headline=head)
    # The sd travels WITH each claim: the headline framing, the binding-
    # constraint claim and the Reading verdict are all sd-dependent, and Task 7
    # copies all three into the prereg.
    assert md.count("sd(noise)=0.01334") >= 3
    # Alternatives measured on the SAME 185 pool, with their own dispersion.
    assert "nuts_k0.6" in md and "0.03261" in md
    assert list(tmp_path.iterdir()) == []       # assemble_report is pure


def test_report_reports_support_binding_only_when_a_contrast_shows_it(mod):
    head = _contrast(mod, "k0.5", 0.01334, 0.003)
    tight = _contrast(mod, "k0.7", 0.01025, 0.003)
    quiet = mod.assemble_report(_ROWS, [head, tight], headline=head)
    assert "DOES reject" not in quiet

    wide = _contrast(mod, "nuts_k0.6", 0.03261, 0.004, support_reject=20,
                     min_support=0.618)
    loud = mod.assemble_report(_ROWS, [head, wide], headline=head)
    assert "DOES reject" in loud

    # With several binders the report must cite the TIGHTEST one — that is the
    # strongest form of the falsification (how little extra dispersion it takes
    # before support starts rejecting), and it does not depend on the order the
    # arms happen to be listed in.
    tight = _contrast(mod, "k0.4", 0.02972, 0.004, support_reject=4,
                      min_support=0.774)
    both = mod.assemble_report(_ROWS, [head, tight, wide], headline=head)
    binding_para = both.split("Binding constraint:")[1].split("\n")[0]
    assert "0.02972" in binding_para and "0.03261" not in binding_para


def test_binding_paragraph_flips_when_the_headline_itself_binds(mod):
    # Reachable by editing ONE constant (HEADLINE) — and this very report
    # argues the wider contrasts are the realistic reading, so that is the
    # likely next edit. The floor-only claims must not ship in that state.
    head = _contrast(mod, "nuts_k0.6", 0.03252, 0.004, power_null=0.21,
                     support_reject=20, min_support=0.753)
    quiet = _contrast(mod, "k0.5", 0.01334, 0.003)
    md = mod.assemble_report(_ROWS, [head, quiet], headline=head)
    para = md.split("Binding constraint:")[1].split("\n\n")[0]
    assert "NOT the support requirement" not in para
    assert "power of the floor alone" not in para
    assert "sign/robustness check" not in para
    assert "BOTH halves" in para and "rejected 20" in para
    # prereg-form sentence must say support IS binding at this configuration
    assert "IS a second binding hurdle" in para
    assert "sd(noise)=0.03252" in para


def test_report_flags_a_contrast_that_cannot_resolve_the_band(mod):
    head = _contrast(mod, "k0.5", 0.01334, 0.003)
    dead = _contrast(mod, "k0.0", 0.08066, None, power_null=0.20,
                     power_max=0.7975, support_reject=493, min_support=0.301)
    md = mod.assemble_report(_ROWS, [head, dead], headline=head)
    assert "cannot resolve" in md
    assert "k0.0" in md
    # "cannot resolve the band" is a claim about the 0.80 TARGET, and this
    # contrast peaks at 0.7975 — which a 2dp print rounds to "0.80" and reads
    # as a contradiction, so the peak has to be published at full precision.
    assert "0.7975" in md

    alive = mod.assemble_report(_ROWS, [head, _contrast(mod, "k0.7", 0.01025,
                                                        0.003)], headline=head)
    assert "cannot resolve" not in alive
