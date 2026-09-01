"""Synthetic-only harness primitives for the preregistered EPL shots/SOT arm.

This module implements the mechanism frozen in ``reports/epl_shots_prereg.md``
(commit ``20dbd59``).  It deliberately has no CLI and no function that loads the
decision outcomes/probabilities, generates a native forecast, writes an
artifact, or runs a real fit.  Its real-data entry points are read-only identity
validators: the shot sidecar/archive join, the 1,520-row training schedule, and
the 2,280-row decision fixture-key schedule.

The prediction path is supplied arrays/data frames by a later, separately
audited runner.  That separation is a lifecycle guard: importing this file, or
running its tests, cannot produce the experiment's answer.
"""

from __future__ import annotations

import csv
import hashlib
import importlib.metadata
import io
import json
import math
import re
import subprocess
import sys
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Mapping, Sequence

import numpy as np
import pandas as pd
from scipy.optimize import minimize

from epl import paths, teams

__all__ = [
    # constants
    "ARM_NAME", "BUILD_STATES", "RAW_DIGESTS", "RAW_ROWS", "RAW_COLUMNS",
    "TRAINING_RAW_DIGESTS", "TRAINING_HISTORY_ROWS",
    "TRAINING_SEASONS", "TRAINING_ROWS", "TRAINING_BLOCK_COUNTS",
    "HALF_LIFE_DAYS", "KAPPA", "PINNED_QUARANTINE",
    "FEATURE_NAMES", "WEEK_BOOTSTRAP_SEED", "SEASON_BOOTSTRAP_SEED",
    "N_BOOT", "NATIVE_STORED_SUM_TOLERANCE",
    "MODEL_PROBABILITY_SUM_TOLERANCE", "OPTIMIZER_GRADIENT_TOLERANCE",
    "OPTIMIZER_BETA_DISTANCE_BOUND_L2",
    "H_MANIFEST_SCHEMA", "K_MANIFEST_SCHEMA", "CANARY_NAMES",
    "AUDIT_DEFECT_SEVERITIES",
    "H_OUTPUT_SCHEMAS", "CANARY_TEST_IDS", "CANARY_TEST_PLAN",
    "MATCHES_SHA256", "DECISION_CORPUS_SHA256", "NATIVE_PARENT_COMMIT",
    # typed refusals
    "ShotsError", "SourceDigestMismatch", "ShotSchemaMismatch",
    "ShotValueInvalid", "ShotPanelMismatch", "FixtureSetMismatch",
    "TimeBoundaryViolation", "ProbabilityInvalid", "FitFailure",
    "CanaryFailed", "LockMismatch",
    # panel
    "QuarantineRecord", "ShotPanel", "sha256_file", "parse_shot_csv",
    "validate_and_join_shots", "assert_source_digests",
    "load_pinned_shot_panel", "load_pinned_training_shot_panel",
    "load_pinned_training_fixtures",
    "DecisionFixture", "load_pinned_decision_schedule",
    "load_pinned_decision_fixture_ids", "attach_weekly_cutoffs",
    "attach_training_cutoffs",
    # feature construction and typed records; fit/score arithmetic stays
    # private until the audited runner re-verifies H/K at call time.
    "shot_features", "FeatureScaler", "TiltFit", "PairScores", "BootstrapCI",
    "assert_fixture_sets",
    # non-self-referential H lifecycle hooks
    "canonical_manifest_bytes",
    "H_MANIFEST_PATH", "make_harness_manifest", "harness_manifest_status",
    "require_harness_manifest",
]


# ==========================================================================
# 0. Frozen constants and typed refusals
# ==========================================================================

ARM_NAME = "dc_1x2_shots"
# Amendment 2 Rider 2: the build-state reading is derived from the live gates
# at inspection time (see ``shots_harness.inspect_state``).  The retired
# ``BUILD_STATE`` constant claimed "BUILT_UNFROZEN_PRE_H" inside frozen bytes;
# no stored constant may assert a lifecycle fact only a live gate can know.
BUILD_STATES = (
    "BUILT_UNFROZEN_PRE_H",
    "H_MANIFEST_PRESENT_UNVERIFIED",
    "FROZEN_H_VERIFIED",
)

RAW_DIGESTS: dict[str, str] = {
    "E0_1415.csv": "76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149",
    "E0_1516.csv": "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
    "E0_1617.csv": "9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0",
    "E0_1718.csv": "4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b",
    "E0_1819.csv": "7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e",
    "E0_1920.csv": "100037618b94f94057400bb02bf6bac4ef74ddaa58cde4b38370839c39caee61",
    "E0_2021.csv": "5afe63f69401457b8354eaacee24f9a3e520b3c3af6329564a9783e20d789c62",
    "E0_2122.csv": "335afcbabeb2939fa10ab39ba3e8215072d0b577cb8d0705c1e44c56e934e703",
    "E0_2223.csv": "8442792d3b614c94ea3cf381bd2736805889cc1713169035368fff19c3d02380",
    "E0_2324.csv": "b2e057b0ed959f198b0f63d2391c01239f3608e6de5db68edab3f88e04d07ff3",
    "E0_2425.csv": "d0c8ce4a96d886cf60cf101f570f4a3893844226f91c7bd769eb568c49edbfa4",
}
RAW_ROWS = 4_180
ROWS_PER_SEASON = 380
RAW_COLUMNS = ("Date", "HomeTeam", "AwayTeam", "HS", "AS", "HST", "AST")
SHOT_COLUMNS = ("HS", "AS", "HST", "AST")


def _expected_training_raw_digests() -> dict[str, str]:
    """Return fresh identities for burn-in plus coefficient-training shots.

    This is deliberately literal rather than a slice of the mutable diagnostic
    ``RAW_DIGESTS`` mapping.  The official training loader must remain bound to
    exactly E0_1415 through E0_1819 even if a caller mutates a module global.
    """
    return {
        "E0_1415.csv": "76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149",
        "E0_1516.csv": "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
        "E0_1617.csv": "9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0",
        "E0_1718.csv": "4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b",
        "E0_1819.csv": "7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e",
    }


# Public diagnostics for receipts; the loader recomputes a fresh mapping above.
TRAINING_RAW_DIGESTS = _expected_training_raw_digests()
TRAINING_HISTORY_ROWS = 1_900

TRAINING_SEASONS = ("2015/16", "2016/17", "2017/18", "2018/19")
TRAINING_ROWS = 1_520
TRAINING_BLOCK_COUNTS = {
    "2015/16": 35, "2016/17": 36, "2017/18": 36, "2018/19": 35,
}
HALF_LIFE_DAYS = 365.0
KAPPA = 10.0
FEATURE_NAMES = ("x1", "x2", "x3", "x4")

N_BOOT = 10_000
WEEK_BOOTSTRAP_SEED = 20260831
SEASON_BOOTSTRAP_SEED = 20260832

# Amendment 1 separates immutable eight-decimal native ledger cells from the
# normalized probabilities used by the residual-logit model.  The optimizer's
# configured gtol remains part of its invocation intent; this independent
# threshold is the experiment's acceptance certificate.
NATIVE_STORED_SUM_TOLERANCE = 1.5e-8
MODEL_PROBABILITY_SUM_TOLERANCE = 1e-12
OPTIMIZER_GRADIENT_TOLERANCE = 1e-5
OPTIMIZER_BETA_DISTANCE_BOUND_L2 = math.sqrt(8.0) * OPTIMIZER_GRADIENT_TOLERANCE

H_MANIFEST_SCHEMA = "epl-shots-harness-manifest-4"
H_MANIFEST_PATH = "reports/evidence/epl_shots/harness_manifest.json"
SHOTS_ARTIFACT_ROOT = "data/epl/fit/shots_sot"
H_REQUIRED_FILES = (
    "epl/shots.py",
    "epl/shots_harness.py",
    "epl/tests/test_shots.py",
)
PRE_H_FORBIDDEN_PATHS = (
    SHOTS_ARTIFACT_ROOT,
    "reports/evidence/epl_shots",
    "reports/epl_shots_result.md",
)
K_MANIFEST_SCHEMA = "epl-shots-coefficient-manifest-2"
K_MANIFEST_PATH = "reports/evidence/epl_shots/coefficient_manifest.json"
K_REQUIRED_ARTIFACTS = (
    "training_predictions", "feature_moments", "coefficients", "optimizer",
)
CANARY_NAMES = (
    "cutoff_boundary", "same_block_isolation", "outcome_isolation",
    "odds_isolation", "zero_tilt_identity", "quarantine_poison",
    "fixture_integrity", "lookahead_trap", "amendment_1_contract",
)
H_RECEIPT_SUBJECT_SCHEMA = "epl-shots-pre-h-subject-3"
H_CANARY_RECEIPT_SCHEMA = "epl-shots-canary-receipt-3"
# Amendment 2 Rider 2: receipt-4 adds a typed defects list.  A disclosed
# non-blocking defect may ride in a valid manifest; a blocking defect still
# refuses the freeze.
H_AUDIT_RECEIPT_SCHEMA = "epl-shots-adversarial-audit-receipt-4"
AUDIT_DEFECT_SEVERITIES = ("blocking", "non_blocking")

# These constants are copied literally from the committed preregistration.
# Unlike a manifest supplied by a caller, they are part of the audited harness
# bytes and therefore cannot be changed without invalidating H.
PREREG_COMMIT = "20dbd59ef784a932473aa2768d8f34d418ea00cf"
PREREG_PATH = "reports/epl_shots_prereg.md"
AMENDMENT_1_COMMIT = "bd7431295a1b366a86324ca00e85a8fe524e2876"
AMENDMENT_1_TREE = "dee4fcf2c4cfc9301e87a1badd50198f9eef4854"
AMENDMENT_1_PATH = "reports/epl_shots_prereg_amendment_1.md"
AMENDMENT_1_SHA256 = (
    "a563882f8698efa60440ed47c24e4854b4c1cd8d1dd59b5311bb0ed54cdb26b9"
)
# Amendment 2 (the replacement freeze) is the sole child of Amendment 1 and is
# the governance parent of H'.  Its B2 disclosed that the superseded candidate
# bytes still pinned the freeze parent to Amendment 1; the owner's freeze
# authorization naming Amendment 2 re-binds the parent gates below.  Amendment 1
# stays bound and independently verified, so the frozen bytes carry both shas.
AMENDMENT_2_COMMIT = "d4d2ce3d7b5fcb84545e83fed7cd4846129cad70"
AMENDMENT_2_TREE = "bbbef6b36e177c42200a7e05f17b741ca09e206c"
AMENDMENT_2_PATH = "reports/epl_shots_prereg_amendment_2.md"
AMENDMENT_2_SHA256 = (
    "4b37345e75bb296a98aa1ee5bc694c3e355b7d60ecc843843ea4c2585f3783e6"
)
NATIVE_PARENT_COMMIT = "6450fb51aef22021a00b3eed72395f1c4141cae3"
NATIVE_PARENT_TREE = "3bfe865d7b441d03b55d356857cd58a89d589fea"
NATIVE_WALKFORWARD_SHA256 = "c68f316f4f3d74881de1312aafd42ae08b5963bfc43ec5065baab4250c5c8710"
NATIVE_FIT_SHA256 = "ab471e96b8321359a0998d6ca7a03496b91b484582ef081f0d43462db6ed1ce6"
NATIVE_CODE_FAMILY_SHA256 = "d388375d3158c122c2fd92c05a670329da7f96957c3814f02937f1c85f6433b0"
NATIVE_CODE_FAMILY_FILES = 157

MATCHES_PATH = "data/epl/matches.parquet"
MATCHES_SHA256 = "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"
DECISION_CORPUS_PATH = "data/epl/fit/walkforward_predictions.parquet"
DECISION_CORPUS_SHA256 = "f31580073eb3a7f0deca59b45d1576fb262272efc6d1893ce8c9931b9eff451a"
PINNED_CONFIG_IDENTITIES = {
    "epl_frozen_config": (
        "epl/config_frozen.json",
        "9f2e086d39ae4b855ba21604367109e8e9ce00f96010c5ec65c380d317986abc",
    ),
    "runtime_config": (
        "config/config.yaml",
        "ffc577bdb690e699fbf9febceddebf41739fbf52d9910cc529b8462f7a7fee65",
    ),
}
PINNED_DEPENDENCY_IDENTITIES = {
    "pyproject": (
        "pyproject.toml",
        "97c2299706e305f0583c59aeb155028aa84e5ec18ddaba3c3addfbefe7882d9b",
    ),
    "uv_lock": (
        "uv.lock",
        "aa57fed33191e34bbed23940f174e411beab0bfe395d8898146f13adea4f2df7",
    ),
}
RESOLVED_PACKAGE_NAMES = (
    "numpy", "pandas", "pyarrow", "duckdb", "scipy", "pymc", "pytensor",
    "arviz",
)
H_OUTPUT_SCHEMA_KEYS = (
    "native_intent", "native_block", "native_completion", "native_refusal",
    "training_predictions", "feature_moments",
    "coefficients", "optimizer_intent", "optimizer_receipt",
    "decision_prediction_intent", "decision_prediction_block",
    "decision_predictions", "prediction_access_receipt", "prediction_seal",
    "scoring_access_intent", "scoring_access_receipt", "decision_scores",
    "decision_canary_receipt", "decision_result", "evidence_manifest",
    "result_report",
)
def _expected_h_output_schemas() -> dict[str, Any]:
    """Return a fresh, code-defined contract immune to global rebinding."""
    return {
    "native_intent": {
        "schema": "epl-shots-native-training-intent-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "parent_commit", "parent_tree", "training_schedule_sha256",
            "raw_inputs", "schedule", "sandbox_contract_sha256",
        ],
        "raw_files": 5,
        "schedule_rows": TRAINING_ROWS,
        "schedule_blocks": 142,
    },
    "native_block": {
        "schema": "epl-shots-native-training-block-2",
        "format": "canonical-json",
        "top_fields": [
            "schema", "native_intent_sha256", "block_identity_sha256",
            "harness_commit", "harness_manifest_sha256",
            "parent_commit", "parent_tree",
            "training_schedule_sha256", "block_ordinal", "block", "cutoff",
            "rows", "receipt",
        ],
        "row_fields": [
            "ordinal", "match_id", "season", "block", "cutoff",
            "home_key", "away_key", "native", "y",
        ],
        "shards": 142,
        "ordered_by": "pinned_training_schedule",
        "native_stored_contract": {
            "cell_decimals": 8,
            "strictly_positive": True,
            "sum_tolerance": NATIVE_STORED_SUM_TOLERANCE,
            "last_cell_repair": False,
        },
    },
    "native_completion": {
        "schema": "epl-shots-native-job-completion-3",
        "format": "canonical-json",
        "fields": [
            "schema", "native_intent_sha256", "job_request_sha256",
            "job_ordinals", "block_records", "clean_exit", "exit_code",
            "sandbox", "stream",
        ],
        "sandbox_schema": "epl-shots-native-sandbox-run-3",
        "sandbox_run_fields": [
            "schema", "contract_sha256", "sandbox_executable",
            "policy_sha256", "python_launcher", "python_resolved",
            "python_sha256", "site_packages", "compiler_paths", "sdk_root",
            "python_flags",
            "runtime_read_paths", "process_exec_paths", "temporary_root",
            "file_read_metadata", "path_resolution_literals",
            "parent_read_path", "request_read_path",
            "runtime_read_write_path", "environment", "resource_limits",
            "isolated_process_group", "network",
        ],
        "sandbox_contract_schema": "epl-shots-native-sandbox-contract-3",
        "sandbox_contract_fields": [
            "schema", "sandbox_executable", "python_launcher",
            "python_resolved", "python_sha256", "python_abi",
            "site_packages", "compiler_paths", "sdk_root", "python_flags",
            "runtime_read_paths", "process_exec_paths", "file_read_metadata",
            "path_resolution_literals",
            "runtime_closure",
            "temporary_read_roles", "temporary_write_roles", "network",
            "inherit_environment", "environment_keys", "resource_limits",
        ],
        "runtime_closure_schema": "epl-shots-native-runtime-lock-2",
        "runtime_closure_fields": [
            "schema", "sha256", "tree_digest_schema", "sealed_read_roots",
            "mutable_roots", "executables", "platform", "file_count",
            "directory_count", "symlink_count", "bytes",
        ],
        "stream_fields": [
            "output_lines", "output_bytes", "total_timeout_seconds",
            "inactivity_timeout_seconds", "max_line_bytes",
            "max_output_bytes", "runtime_tree_max_bytes",
            "runtime_tree_max_files", "runtime_tree_observed_bytes",
            "runtime_tree_observed_files", "runtime_tree_completion",
            "resident_memory_max_bytes",
            "resident_memory_poll_seconds",
            "resident_memory_sampled_peak_bytes",
        ],
        "runtime_tree_completion_schema":
            "epl-shots-generated-runtime-tree-1",
        "runtime_tree_completion_fields": [
            "schema", "sha256", "file_count", "directory_count",
            "bytes", "entries",
        ],
        "runtime_tree_completion_entry_fields": [
            "relative_path", "kind", "mode", "bytes", "sha256",
        ],
        "acceptance": "exact_nonoverlapping_clean_exit_coverage_0_through_141",
    },
    "native_refusal": {
        "schema": "epl-shots-native-refusal-receipt-2",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "training_schedule_sha256", "native_intent_sha256",
            "native_intent_record", "job_request_sha256", "job_ordinals",
            "semantic_refusal", "block_records", "output_lines",
            "output_bytes", "exit_code",
        ],
        "semantic_refusal_schema": "epl-shots-native-refusal-execution-1",
        "semantic_refusal_fields": [
            "schema", "source", "terminal_event", "worker_event",
            "sandbox_contract", "sandbox_contract_sha256", "sandbox_run",
            "runtime_snapshot", "runtime_observed",
            "post_launch_sandbox_contract",
            "post_launch_sandbox_contract_sha256",
        ],
        "semantic_event_schema": "epl-shots-native-semantic-refusal-1",
        "semantic_event_fields": [
            "schema", "native_intent_sha256", "job_request_sha256",
            "harness_commit", "harness_manifest_sha256",
            "training_schedule_sha256", "refusal_kind",
            "exception_type", "message",
        ],
        "sandbox_contract_schema": "epl-shots-native-sandbox-contract-3",
        "sandbox_run_schema": "epl-shots-native-sandbox-run-3",
        "runtime_snapshot_schema": "epl-shots-generated-runtime-tree-1",
        "runtime_observed_fields": ["files", "bytes", "rss_bytes"],
        "sources": [
            "worker_semantic_refusal",
            "parent_runtime_closure_mismatch",
        ],
        "worker_event_nullable": True,
        "terminal_only_after": (
            "validated_execution_envelope_and_closed_process_group"
        ),
    },
    "training_predictions": {
        "schema": "epl-shots-training-predictions-2",
        "format": "canonical-json",
        "rows": TRAINING_ROWS,
        "top_fields": [
            "schema", "training_schedule_sha256", "native_block_set_sha256",
            "feature_moments_sha256", "coefficients_sha256",
            "optimizer_receipt_sha256", "n_rows", "rows",
        ],
        "row_fields": [
            "ordinal", "match_id", "season", "date", "home_key", "away_key",
            "block", "cutoff", "shot_expectations", "features",
            "standardized_features", "native", "candidate", "y",
        ],
        "ordered_by": "pinned_training_schedule",
        "native_stored_sum_tolerance": NATIVE_STORED_SUM_TOLERANCE,
        "candidate_sum_tolerance": MODEL_PROBABILITY_SUM_TOLERANCE,
    },
    "feature_moments": {
        "schema": "epl-shots-feature-moments-2",
        "format": "canonical-json",
        "fields": [
            "schema", "training_schedule_sha256", "native_block_set_sha256",
            "names", "means", "population_standard_deviations", "ddof",
            "n_training", "seasons",
        ],
    },
    "coefficients": {
        "schema": "epl-shots-coefficients-2",
        "format": "canonical-json",
        "fields": [
            "schema", "training_schedule_sha256", "native_block_set_sha256",
            "feature_moments_sha256", "optimizer_receipt_sha256",
            "feature_names", "reference_outcome", "coefficient_order",
            "beta_H", "beta_D",
        ],
        "n_coefficients": 8,
    },
    "optimizer_intent": {
        "schema": "epl-shots-optimizer-intent-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "training_schedule_sha256", "native_block_set_sha256",
            "feature_moments_sha256", "training_outcomes_sha256", "dtype",
            "method", "jacobian", "start", "bounds", "options",
            "objective", "coefficient_order",
        ],
    },
    "optimizer_receipt": {
        "schema": "epl-shots-optimizer-receipt-3",
        "format": "canonical-json",
        "fields": [
            "schema", "optimizer_intent_sha256", "success", "status", "dtype",
            "method", "jacobian", "start", "bounds", "options", "objective",
            "coefficient_order", "beta", "objective_value", "gradient",
            "gradient_max_abs", "iterations", "function_evaluations",
            "gradient_evaluations", "message", "independent_gradient",
            "independent_objective_value", "objective_consistent",
            "independent_gradient_max_abs", "gradient_consistent",
            "gradient_acceptance_threshold", "gradient_certified",
            "beta_distance_actual_bound_l2",
            "beta_distance_acceptance_ceiling_l2",
        ],
        "acceptance": (
            "success_is_true_and_objective_and_gradient_agree_and_"
            "independent_gradient_max_abs_lte_1e-5"
        ),
    },
    "decision_prediction_intent": {
        "schema": "epl-shots-decision-prediction-intent-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "coefficient_commit", "coefficient_manifest_sha256",
            "decision_schedule_sha256", "corpus_sha256", "source_path",
            "columns", "rows", "blocks", "feature_moments_sha256",
            "coefficients_sha256", "outcomes_excluded", "market_excluded",
            "stored_scores_excluded",
        ],
    },
    "decision_prediction_block": {
        "schema": "epl-shots-decision-prediction-block-1",
        "format": "canonical-json",
        "shards": 212,
        "top_fields": [
            "schema", "prediction_intent_sha256", "access_receipt_sha256",
            "harness_commit", "coefficient_commit",
            "decision_schedule_sha256", "corpus_sha256",
            "block_ordinal", "block", "cutoff", "rows",
        ],
        "row_fields": [
            "ordinal", "match_id", "season", "date", "home_key", "away_key",
            "block", "cutoff", "shot_expectations", "features",
            "standardized_features", "native", "candidate",
        ],
        "outcomes_excluded": True,
        "market_excluded": True,
        "native_stored_sum_tolerance": NATIVE_STORED_SUM_TOLERANCE,
        "candidate_sum_tolerance": MODEL_PROBABILITY_SUM_TOLERANCE,
    },
    "decision_predictions": {
        "schema": "epl-shots-decision-predictions-1",
        "format": "canonical-json",
        "rows": 2_280,
        "top_fields": [
            "schema", "harness_commit", "coefficient_commit",
            "decision_schedule_sha256", "corpus_sha256", "block_set_sha256",
            "access_receipt_sha256", "blocks", "n_rows", "rows",
        ],
        "row_fields": [
            "ordinal", "match_id", "season", "date", "home_key", "away_key",
            "block", "cutoff", "shot_expectations", "features",
            "standardized_features", "native", "candidate",
        ],
        "ordered_by": "pinned_decision_schedule",
        "outcomes_excluded": True,
        "market_excluded": True,
    },
    "prediction_access_receipt": {
        "schema": "epl-shots-prediction-access-receipt-1",
        "format": "canonical-json",
        "fields": [
            "schema", "prediction_intent_sha256", "phase", "source_path",
            "source_sha256", "columns", "rows", "projection_sha256",
            "outcomes_excluded", "market_excluded", "stored_scores_excluded",
        ],
    },
    "prediction_seal": {
        "schema": "epl-shots-prediction-seal-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "coefficient_commit",
            "decision_schedule_sha256", "corpus_sha256",
            "decision_predictions", "access_receipt", "rows",
            "durably_fsynced", "reopened", "semantic_verified",
        ],
    },
    "scoring_access_intent": {
        "schema": "epl-shots-scoring-access-intent-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "coefficient_commit", "coefficient_manifest_sha256",
            "decision_schedule_sha256", "prediction_seal_sha256",
            "source_path", "source_sha256", "columns", "rows",
            "exactly_once",
        ],
    },
    "scoring_access_receipt": {
        "schema": "epl-shots-scoring-access-receipt-1",
        "format": "canonical-json",
        "fields": [
            "schema", "scoring_access_intent_sha256",
            "prediction_seal_sha256", "phase", "source_path",
            "source_sha256", "columns", "rows", "projection_sha256",
            "outcomes_opened", "market_opened", "stored_scores_opened",
            "completed",
        ],
    },
    "decision_scores": {
        "schema": "epl-shots-decision-scores-1",
        "format": "canonical-json",
        "rows": 2_280,
        "top_fields": [
            "schema", "prediction_seal_sha256",
            "scoring_access_receipt_sha256", "scoring_projection_sha256",
            "n_rows", "rows",
        ],
        "row_fields": [
            "ordinal", "match_id", "season", "block", "y",
            "candidate", "native", "market",
            "candidate_rps", "native_rps", "market_rps", "d_native",
            "d_market", "stored_native_rps", "stored_market_rps",
            "native_rps_parity_error", "market_rps_parity_error",
            "candidate_log_loss", "native_log_loss", "market_log_loss",
            "ll_d_native", "ll_d_market",
        ],
    },
    "decision_canary_receipt": {
        "schema": "epl-shots-decision-canary-receipt-1",
        "format": "canonical-json",
        "fields": [
            "schema", "prediction_seal_sha256",
            "scoring_access_receipt_sha256", "decision_scores_sha256",
            "checks", "passed",
        ],
    },
    "decision_result": {
        "schema": "epl-shots-decision-result-2",
        "format": "canonical-json",
        "common_fields": [
            "schema", "status", "harness_commit", "coefficient_commit",
            "prediction_seal_sha256", "completed_receipts", "exclusions",
        ],
        "success_fields": [
            "n", "mean_d_native", "mean_d_market", "week_ci_native",
            "week_ci_market", "season_ci_native", "season_ci_market",
            "per_season_native", "per_season_market", "mean_log_loss",
            "paired_log_loss_deltas", "stored_rps_parity", "decision_gates",
            "disposition", "market_competitive",
        ],
        "refusal_fields": [
            "refusal_name", "refusal_stage", "refusal_message", "counts",
            "headline_rps", "intervals", "season_results", "log_loss",
        ],
        "refusal_na_template": "N/A \u2014 not computed after <RefusalName>",
    },
    "evidence_manifest": {
        "schema": "epl-shots-result-evidence-manifest-1",
        "format": "canonical-json",
        "fields": [
            "schema", "harness_commit", "harness_manifest_sha256",
            "coefficient_commit", "coefficient_manifest_sha256",
            "prediction_seal", "artifacts", "decision_result",
            "canary_receipts", "audit_receipt", "published_regardless_of_sign",
        ],
    },
    "result_report": {
        "schema": "epl-shots-result-report-1",
        "format": "utf-8-markdown",
        "path": "reports/epl_shots_result.md",
        "fields": ["sha256", "bytes", "evidence_manifest_sha256"],
    },
    }


H_OUTPUT_SCHEMAS = _expected_h_output_schemas()


def _expected_canary_test_ids() -> dict[str, str]:
    """Return fresh preregistered test identities for manifest validation."""
    return {
    "cutoff_boundary": "test_canary_1_literal_cutoff_and_c_minus_one_boundary",
    "same_block_isolation": "test_canary_2_target_and_same_block_rows_are_isolated_with_prior_control",
    "outcome_isolation": "test_canary_3_outcomes_cannot_change_predictions_but_training_control_moves_beta",
    "odds_isolation": "test_canary_4_market_changes_benchmark_delta_not_challenger_prediction",
    "zero_tilt_identity": "test_canary_5_zero_tilt_is_native_and_positive_coefficient_moves_home",
    "quarantine_poison": "test_canary_6_exact_quarantine_passes_but_zero_changed_or_second_bad_refuses",
    "fixture_integrity": "test_canary_7_canonical_fixture_set_passes_and_drop_duplicate_reorder_refuse",
    "lookahead_trap": "test_canary_8_future_outcome_encoding_is_inert_but_prior_encoding_moves",
    "amendment_1_contract": (
        "test_zero_tilt_uses_normalized_model_native_without_repairing_storage"
    ),
    }


CANARY_TEST_IDS = _expected_canary_test_ids()


def _expected_canary_test_plan() -> dict[str, Any]:
    """Return the immutable semantic cases that a pre-H run must exercise."""
    return {
        "schema": "epl-shots-canary-test-plan-1",
        "canaries": {
            "cutoff_boundary": [
                {"case_id": "date_at_or_after_cutoff_inert",
                 "test_id": "test_canary_1_literal_cutoff_and_c_minus_one_boundary",
                 "control": "negative"},
                {"case_id": "c_minus_one_moves",
                 "test_id": "test_canary_1_literal_cutoff_and_c_minus_one_boundary",
                 "control": "positive"},
            ],
            "same_block_isolation": [
                {"case_id": "target_and_same_block_inert",
                 "test_id": "test_canary_2_target_and_same_block_rows_are_isolated_with_prior_control",
                 "control": "negative"},
                {"case_id": "prior_block_moves",
                 "test_id": "test_canary_2_target_and_same_block_rows_are_isolated_with_prior_control",
                 "control": "positive"},
            ],
            "outcome_isolation": [
                {"case_id": "fixed_fit_outcomes_inert",
                 "test_id": "test_canary_3_outcomes_cannot_change_predictions_but_training_control_moves_beta",
                 "control": "negative"},
                {"case_id": "synthetic_training_outcomes_move_beta",
                 "test_id": "test_canary_3_outcomes_cannot_change_predictions_but_training_control_moves_beta",
                 "control": "positive"},
            ],
            "odds_isolation": [
                {"case_id": "challenger_ignores_market",
                 "test_id": "test_canary_4_market_changes_benchmark_delta_not_challenger_prediction",
                 "control": "negative"},
                {"case_id": "market_diagnostic_moves",
                 "test_id": "test_canary_4_market_changes_benchmark_delta_not_challenger_prediction",
                 "control": "positive"},
            ],
            "zero_tilt_identity": [
                {"case_id": "zero_tilt_matches_native",
                 "test_id": "test_canary_5_zero_tilt_is_native_and_positive_coefficient_moves_home",
                 "control": "negative"},
                {"case_id": "positive_home_coefficient_moves",
                 "test_id": "test_canary_5_zero_tilt_is_native_and_positive_coefficient_moves_home",
                 "control": "positive"},
            ],
            "quarantine_poison": [
                *[
                    {"case_id": case_id,
                     "test_id": "test_canary_6_poison_values_reach_shot_value_refusal",
                     "control": "positive"}
                    for case_id in (
                        "null", "nonnumeric", "negative", "noninteger",
                        "hst_gt_hs", "ast_gt_as",
                    )
                ],
                *[
                    {"case_id": case_id,
                     "test_id": "test_canary_6_duplicate_key_and_missing_join_reach_panel_refusal",
                     "control": "positive"}
                    for case_id in ("duplicate_key", "missing_join")
                ],
                {"case_id": "pinned_exact_quarantine",
                 "test_id": "test_canary_6_exact_quarantine_passes_but_zero_changed_or_second_bad_refuses",
                 "control": "negative"},
                *[
                    {"case_id": case_id,
                     "test_id": "test_canary_6_exact_quarantine_passes_but_zero_changed_or_second_bad_refuses",
                     "control": "positive"}
                    for case_id in (
                        "zero_quarantine", "changed_quarantine", "second_bad_row",
                    )
                ],
                {"case_id": "real_4180_one_quarantine",
                 "test_id": "test_pinned_raw_shape_digests_join_and_one_quarantine_only",
                 "control": "negative"},
            ],
            "fixture_integrity": [
                {"case_id": "synthetic_canonical_ordered_set",
                 "test_id": "test_canary_7_canonical_fixture_set_passes_and_drop_duplicate_reorder_refuse",
                 "control": "negative"},
                *[
                    {"case_id": f"synthetic_{case_id}",
                     "test_id": "test_canary_7_canonical_fixture_set_passes_and_drop_duplicate_reorder_refuse",
                     "control": "positive"}
                    for case_id in ("drop", "duplicate", "reorder")
                ],
                {"case_id": "real_2280_canonical_ordered_set",
                 "test_id": "test_real_2280_key_negative_control_and_fixture_positive_controls",
                 "control": "negative"},
                *[
                    {"case_id": f"real_2280_{case_id}",
                     "test_id": "test_real_2280_key_negative_control_and_fixture_positive_controls",
                     "control": "positive"}
                    for case_id in ("drop", "duplicate", "reorder")
                ],
            ],
            "lookahead_trap": [
                {"case_id": "future_encoding_inert",
                 "test_id": "test_canary_8_future_outcome_encoding_is_inert_but_prior_encoding_moves",
                 "control": "negative"},
                {"case_id": "prior_encoding_moves",
                 "test_id": "test_canary_8_future_outcome_encoding_is_inert_but_prior_encoding_moves",
                 "control": "positive"},
            ],
            "amendment_1_contract": [
                {"case_id": "stored_native_one_tick_both_directions_accepted_no_repair",
                 "test_id": "test_stored_native_accepts_both_one_tick_sum_directions",
                 "control": "negative"},
                {"case_id": "stored_native_two_tick_or_non_eight_decimal_refuses",
                 "test_id": "test_stored_native_rejects_two_ticks_or_non_eight_decimal_cells",
                 "control": "positive"},
                {"case_id": "zero_tilt_equals_normalized_native_model_without_storage_repair",
                 "test_id": "test_zero_tilt_uses_normalized_model_native_without_repairing_storage",
                 "control": "negative"},
                {"case_id": "scipy_success_nonzero_status_with_certified_gradient_accepts",
                 "test_id": "test_optimizer_preserves_exact_result_provenance_and_frozen_call",
                 "control": "negative"},
                {"case_id": "scipy_success_gradient_over_threshold_receiptable_refusal",
                 "test_id": "test_scipy_success_without_amendment_gradient_certificate_is_receiptable",
                 "control": "positive"},
                {"case_id": "scipy_failure_small_gradient_receiptable_refusal",
                 "test_id": "test_finite_optimizer_refusal_preserves_receiptable_result",
                 "control": "positive"},
                {"case_id": "finite_objective_or_gradient_mismatch_receiptable_refusal",
                 "test_id": "test_finite_optimizer_recomputation_mismatch_remains_receiptable",
                 "control": "positive"},
                {"case_id": "native_comparator_scores_stored_cells_unchanged",
                 "test_id": "test_native_comparator_rps_uses_stored_cells_while_other_simplexes_stay_strict",
                 "control": "negative"},
                {"case_id": "candidate_and_market_off_simplex_refuse",
                 "test_id": "test_native_comparator_rps_uses_stored_cells_while_other_simplexes_stay_strict",
                 "control": "positive"},
            ],
        },
        "real_validation": [
            {"case_id": "training_schedule_identity",
             "test_id": "test_real_training_identity_projection_is_exact_and_outcome_free",
             "control": "validation"},
        ],
    }


# Public diagnostic only; validators always recompute a fresh plan.
CANARY_TEST_PLAN = _expected_canary_test_plan()

_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GIT_EXECUTABLE = "/usr/bin/git"
_GIT_ENVIRONMENT = {
    "PATH": "/usr/bin:/bin",
    "LANG": "C",
    "LC_ALL": "C",
    "TMPDIR": "/tmp",
    "GIT_CONFIG_NOSYSTEM": "1",
    "GIT_CONFIG_GLOBAL": "/dev/null",
    "GIT_ATTR_NOSYSTEM": "1",
    "GIT_NO_REPLACE_OBJECTS": "1",
    "GIT_OPTIONAL_LOCKS": "0",
}


class ShotsError(ValueError):
    """Base class for a preregistered shots-harness refusal."""


class SourceDigestMismatch(ShotsError):
    """A pinned raw source is absent, extra, or has different bytes."""


class ShotSchemaMismatch(ShotsError):
    """The allowlisted raw identity/shot columns are not available exactly."""


class ShotValueInvalid(ShotsError):
    """A shot value is missing, nonnumeric, nonfinite, noninteger, or invalid."""


class ShotPanelMismatch(ShotsError):
    """The panel grain, quarantine, source shape, or archive join differs."""


class FixtureSetMismatch(ShotsError):
    """Candidate, native, market, and outcome fixture keys are not identical."""


class TimeBoundaryViolation(ShotsError):
    """A row dated at or after a prediction block cutoff entered its state."""


class ProbabilityInvalid(ShotsError):
    """A probability vector is nonfinite, out of range, zero when forbidden, or unnormalised."""


class FitFailure(ShotsError):
    """Training scaling or the one deterministic optimizer is invalid."""


class CanaryFailed(ShotsError):
    """A negative or positive-control leakage canary failed."""


class LockMismatch(ShotsError):
    """A harness manifest is malformed, self-referential, or mismatches bytes."""


@dataclass(frozen=True)
class _QuarantineSpec:
    date: str
    home_key: str
    away_key: str
    values: tuple[float, float, float, float]
    reason: str


PINNED_QUARANTINE = _QuarantineSpec(
    date="2021-08-15", home_key="newcastle", away_key="west_ham",
    values=(17.0, 8.0, 3.0, 9.0), reason="AST>AS",
)


# ==========================================================================
# 1. Raw sidecar parsing, validation, quarantine, and exact identity join
# ==========================================================================

@dataclass(frozen=True)
class QuarantineRecord:
    date: str
    home_key: str
    away_key: str
    values: tuple[float, float, float, float]
    reason: str
    source: str
    raw_row: int
    match_id: str | None = None


@dataclass(frozen=True)
class ShotPanel:
    """Validated rows after quarantine, plus an auditable panel receipt."""

    frame: pd.DataFrame
    raw_rows: int
    quarantine: tuple[QuarantineRecord, ...]
    source_digests: Mapping[str, str]


def sha256_file(path: Path | str) -> str:
    h = hashlib.sha256()
    with Path(path).open("rb") as fh:
        for chunk in iter(lambda: fh.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _assert_file_identity(path: Path | str, expected: str, *, label: str,
                          error: type[ShotsError] = SourceDigestMismatch) -> str:
    candidate = Path(path)
    if not candidate.is_file():
        raise error(f"{label}: pinned file is absent at {candidate}")
    actual = sha256_file(candidate)
    if actual != expected:
        raise error(f"{label}: SHA-256 {actual}, expected {expected}")
    return actual


def _recompute_value_reasons(row: pd.Series) -> str:
    """Revalidate values instead of trusting the parser's marker column."""
    reasons: list[str] = []
    parsed: dict[str, float] = {}
    for column in SHOT_COLUMNS:
        raw = row[column]
        if raw is None or bool(pd.isna(raw)):
            reasons.append(f"{column}:missing")
            parsed[column] = float("nan")
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            reasons.append(f"{column}:nonnumeric")
            parsed[column] = float("nan")
            continue
        parsed[column] = value
        if not math.isfinite(value):
            reasons.append(f"{column}:nonfinite")
        elif value < 0:
            reasons.append(f"{column}:negative")
        elif not value.is_integer():
            reasons.append(f"{column}:noninteger")
    if all(math.isfinite(parsed[c]) for c in SHOT_COLUMNS):
        if parsed["HST"] > parsed["HS"]:
            reasons.append("HST>HS")
        if parsed["AST"] > parsed["AS"]:
            reasons.append("AST>AS")
    return ";".join(reasons)


def _parse_date(text: str, *, source: str, row: int) -> pd.Timestamp:
    for fmt in ("%d/%m/%y", "%d/%m/%Y"):
        try:
            return pd.Timestamp(datetime.strptime(text, fmt)).normalize()
        except ValueError:
            pass
    raise ShotValueInvalid(
        f"{source}:{row}: Date {text!r} matches neither %d/%m/%y nor "
        "%d/%m/%Y; date inference is forbidden"
    )


def _shot_value(text: str, *, column: str, source: str, row: int,
                reasons: list[str]) -> float:
    value = text.strip()
    if value == "":
        reasons.append(f"{column}:missing")
        return float("nan")
    try:
        number = float(value)
    except ValueError:
        reasons.append(f"{column}:nonnumeric")
        return float("nan")
    if not math.isfinite(number):
        reasons.append(f"{column}:nonfinite")
    elif number < 0:
        reasons.append(f"{column}:negative")
    elif not number.is_integer():
        reasons.append(f"{column}:noninteger")
    return number


def parse_shot_csv(text: str, *, season_code: str,
                   source: str = "<memory>") -> pd.DataFrame:
    """Parse only identity keys plus HS/AS/HST/AST from one raw CSV.

    Extra source columns are deliberately ignored.  Required header names must
    each occur exactly once, and no result or odds column is returned.
    Invalid shot measures are retained with ``_invalid_reason`` so the caller
    can compare the complete invalid set to the one pinned quarantine rather
    than stopping at the first row and accidentally accepting a second.
    """
    reader = csv.reader(io.StringIO(text))
    try:
        header = next(reader)
    except StopIteration as exc:
        raise ShotSchemaMismatch(f"{source}: empty CSV") from exc
    header = [str(v).strip() for v in header]
    for name in RAW_COLUMNS:
        count = header.count(name)
        if count != 1:
            raise ShotSchemaMismatch(
                f"{source}: required column {name!r} occurs {count} times; "
                "each allowlisted column must occur exactly once"
            )
    positions = {name: header.index(name) for name in RAW_COLUMNS}
    needed_position = max(positions.values())
    records: list[dict[str, Any]] = []
    for raw_row, values in enumerate(reader, 2):
        if not values:
            # A physically empty trailing CSV row has all three identity fields
            # blank and is therefore blank under the preregistered rule.
            continue
        padded_identity = [
            values[positions[c]].strip() if positions[c] < len(values) else ""
            for c in ("Date", "HomeTeam", "AwayTeam")
        ]
        if not any(padded_identity):
            continue
        if len(values) <= needed_position:
            raise ShotSchemaMismatch(
                f"{source}:{raw_row}: row ends before all allowlisted columns"
            )
        identity = padded_identity
        if not all(identity):
            raise ShotPanelMismatch(
                f"{source}:{raw_row}: Date/HomeTeam/AwayTeam is partially blank"
            )
        date = _parse_date(identity[0], source=source, row=raw_row)
        try:
            home_key = teams.team_key(identity[1])
            away_key = teams.team_key(identity[2])
        except teams.UnknownTeamError as exc:
            raise ShotPanelMismatch(f"{source}:{raw_row}: {exc}") from exc
        if home_key == away_key:
            raise ShotPanelMismatch(
                f"{source}:{raw_row}: home and away resolve to the same club"
            )
        reasons: list[str] = []
        shots = {
            c: _shot_value(values[positions[c]], column=c, source=source,
                           row=raw_row, reasons=reasons)
            for c in SHOT_COLUMNS
        }
        if all(math.isfinite(shots[c]) for c in SHOT_COLUMNS):
            if shots["HST"] > shots["HS"]:
                reasons.append("HST>HS")
            if shots["AST"] > shots["AS"]:
                reasons.append("AST>AS")
        records.append({
            "season_code": str(season_code), "date": date,
            "home_key": home_key, "away_key": away_key, **shots,
            "source": str(source), "raw_row": int(raw_row),
            "_invalid_reason": ";".join(reasons),
        })
    columns = ["season_code", "date", "home_key", "away_key", *SHOT_COLUMNS,
               "source", "raw_row", "_invalid_reason"]
    return pd.DataFrame.from_records(records, columns=columns)


def _record_from_row(row: pd.Series) -> QuarantineRecord:
    return QuarantineRecord(
        date=str(pd.Timestamp(row["date"]).date()),
        home_key=str(row["home_key"]), away_key=str(row["away_key"]),
        values=tuple(float(row[c]) for c in SHOT_COLUMNS),
        reason=str(row["_invalid_reason"]), source=str(row["source"]),
        raw_row=int(row["raw_row"]),
        match_id=(None if pd.isna(row.get("match_id"))
                  else str(row.get("match_id"))),
    )


def _quarantine_matches(record: QuarantineRecord,
                        spec: _QuarantineSpec) -> bool:
    return (
        record.date == spec.date
        and record.home_key == spec.home_key
        and record.away_key == spec.away_key
        and record.values == spec.values
        and record.reason == spec.reason
    )


def _require_columns(frame: pd.DataFrame, columns: Sequence[str], *,
                     label: str, error: type[ShotsError] = ShotSchemaMismatch,
                     ) -> None:
    missing = [c for c in columns if c not in frame.columns]
    if missing:
        raise error(f"{label} lacks required columns {missing}")


def validate_and_join_shots(
    rows: pd.DataFrame,
    archive: pd.DataFrame,
    *,
    expected_quarantine: _QuarantineSpec | None = None,
    expected_rows: int | None = None,
    source_digests: Mapping[str, str] | None = None,
) -> ShotPanel:
    """Validate raw grain, join every row exactly once, then quarantine.

    ``archive`` must be an identity-only view.  Extra columns are ignored, but
    this function never asks for outcomes.  With ``expected_quarantine=None``
    any invalid row is :class:`ShotValueInvalid`; the pinned loader supplies the
    one frozen quarantine and requires exact identity, values, and reason.
    """
    raw_required = ("season_code", "date", "home_key", "away_key",
                    *SHOT_COLUMNS, "source", "raw_row", "_invalid_reason")
    _require_columns(rows, raw_required, label="shot rows")
    archive_required = ("match_id", "season_code", "date", "home_key",
                        "away_key")
    _require_columns(archive, archive_required, label="archive")
    work = rows.copy()
    work["date"] = pd.to_datetime(work["date"], errors="raise").dt.normalize()
    # ``_invalid_reason`` is an audit aid emitted by the CSV parser, not a
    # security boundary.  Recompute it from the measures so a stale or edited
    # marker cannot bless an invalid value.
    reasons = []
    for _, row in work.iterrows():
        recomputed = _recompute_value_reasons(row)
        recorded = str(row.get("_invalid_reason", ""))
        # Parsing a nonnumeric token deliberately stores NaN, so only the
        # parser can preserve the more specific `nonnumeric` label.  The marker
        # may refine an already-invalid value; it can never make a valid value
        # pass or make an invalid value pass.
        reasons.append(recorded if recomputed and recorded else recomputed)
    work["_invalid_reason"] = reasons
    arc = archive[list(archive_required)].copy()
    if arc["match_id"].isna().any() or (arc["match_id"].astype(str).str.strip() == "").any():
        raise ShotPanelMismatch("archive match_id values must be nonnull and nonempty")
    arc["date"] = pd.to_datetime(arc["date"], errors="raise").dt.normalize()
    key = ["date", "home_key", "away_key"]
    if work.duplicated(key, keep=False).any():
        dup = work.loc[work.duplicated(key, keep=False), key].head(3)
        raise ShotPanelMismatch(
            f"shot panel has duplicate date/home/away keys: "
            f"{dup.astype(str).to_dict('records')}"
        )
    if arc.duplicated(key, keep=False).any():
        dup = arc.loc[arc.duplicated(key, keep=False), key].head(3)
        raise ShotPanelMismatch(
            f"archive has duplicate date/home/away keys: "
            f"{dup.astype(str).to_dict('records')}"
        )
    if expected_rows is not None and len(work) != int(expected_rows):
        raise ShotPanelMismatch(
            f"shot panel has {len(work)} rows, expected {int(expected_rows)}"
        )
    arc = arc.rename(columns={"season_code": "_archive_season_code"})
    try:
        joined = work.merge(arc, on=key, how="left", validate="one_to_one",
                            indicator=True)
    except pd.errors.MergeError as exc:
        raise ShotPanelMismatch(f"shot/archive join is not one-to-one: {exc}") from exc
    orphan = joined["_merge"] != "both"
    if orphan.any():
        sample = joined.loc[orphan, key].head(3).astype(str).to_dict("records")
        raise ShotPanelMismatch(
            f"{int(orphan.sum())} shot row(s) have no archive match: {sample}"
        )
    season_bad = (joined["season_code"].astype(str)
                  != joined["_archive_season_code"].astype(str))
    if season_bad.any():
        sample = joined.loc[season_bad,
                            [*key, "season_code", "_archive_season_code"]]
        raise ShotPanelMismatch(
            f"shot/archive season mismatch: {sample.head(3).astype(str).to_dict('records')}"
        )
    if joined["match_id"].astype(str).duplicated().any():
        raise ShotPanelMismatch("two shot rows joined to the same match_id")

    invalid = joined["_invalid_reason"].astype(str) != ""
    quarantine = tuple(_record_from_row(row)
                       for _, row in joined.loc[invalid].iterrows())
    if expected_quarantine is None:
        if quarantine:
            first = quarantine[0]
            raise ShotValueInvalid(
                f"{first.source}:{first.raw_row}: {first.reason}; no quarantine "
                "is permitted for this panel"
            )
    elif (len(quarantine) != 1
          or not _quarantine_matches(quarantine[0], expected_quarantine)):
        observed = [{"date": q.date, "home": q.home_key, "away": q.away_key,
                     "values": q.values, "reason": q.reason}
                    for q in quarantine]
        raise ShotPanelMismatch(
            "invalid-row set does not equal the one pinned quarantine: "
            f"observed={observed}"
        )

    clean = joined.loc[~invalid].copy()
    clean = clean.drop(columns=["_invalid_reason", "_merge",
                                "_archive_season_code"])
    clean = clean.sort_values(
        ["date", "home_key", "away_key"], kind="mergesort"
    ).reset_index(drop=True)
    return ShotPanel(
        frame=clean, raw_rows=int(len(joined)), quarantine=quarantine,
        source_digests=dict(source_digests or {}),
    )


def _assert_named_source_digests(
    files: Mapping[str, Path | str], expected_digests: Mapping[str, str], *,
    label: str,
) -> dict[str, str]:
    """Require one exact named file set and all of its byte digests."""
    supplied = set(files)
    expected = set(expected_digests)
    if supplied != expected:
        raise SourceDigestMismatch(
            f"{label} file set differs: missing={sorted(expected - supplied)}, "
            f"extra={sorted(supplied - expected)}"
        )
    actual: dict[str, str] = {}
    for name, expected_digest in expected_digests.items():
        path = Path(files[name])
        if not path.is_file():
            raise SourceDigestMismatch(f"{name}: pinned source is absent at {path}")
        digest = sha256_file(path)
        actual[name] = digest
        if digest != expected_digest:
            raise SourceDigestMismatch(
                f"{name}: SHA-256 {digest}, expected {expected_digest}"
            )
    return actual


def assert_source_digests(files: Mapping[str, Path | str]) -> dict[str, str]:
    """Require the exact eleven pinned file names and byte digests."""
    return _assert_named_source_digests(files, RAW_DIGESTS, label="raw")


def _read_training_source_texts(
    files: Mapping[str, Path | str],
) -> tuple[dict[str, str], dict[str, str]]:
    """Hash and decode the same bytes for the five fixed training sources."""
    expected = _expected_training_raw_digests()
    supplied, wanted = set(files), set(expected)
    if supplied != wanted:
        raise SourceDigestMismatch(
            "training raw file set differs: "
            f"missing={sorted(wanted - supplied)}, "
            f"extra={sorted(supplied - wanted)}"
        )
    texts, digests = {}, {}
    for name, expected_digest in expected.items():
        path = Path(files[name])
        if not path.is_file():
            raise SourceDigestMismatch(f"{name}: pinned source is absent at {path}")
        raw = path.read_bytes()
        digest = hashlib.sha256(raw).hexdigest()
        if digest != expected_digest:
            raise SourceDigestMismatch(
                f"{name}: SHA-256 {digest}, expected {expected_digest}"
            )
        try:
            texts[name] = raw.decode("utf-8-sig")
        except UnicodeDecodeError as exc:
            raise ShotSchemaMismatch(f"{name}: pinned bytes are not UTF-8") from exc
        digests[name] = digest
    return texts, digests


def _expected_matches_sha256() -> str:
    """Return a fresh archive identity for the fixed-path training reader."""
    return "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"


def load_pinned_shot_panel(*, raw_dir: Path | str | None = None,
                           archive_path: Path | str | None = None,
                           ) -> ShotPanel:
    """Read-only validation of the 4,180-row pinned sidecar.

    Only identity columns are projected from the tidy archive.  This function
    neither imports fitting code nor reads a decision-prediction artifact.
    """
    raw_dir = Path(raw_dir) if raw_dir is not None else paths.RAW_DIR
    files = {name: raw_dir / name for name in RAW_DIGESTS}
    digests = assert_source_digests(files)
    parts: list[pd.DataFrame] = []
    for name in RAW_DIGESTS:
        season_code = name.removeprefix("E0_").removesuffix(".csv")
        text = Path(files[name]).read_text(encoding="utf-8-sig")
        part = parse_shot_csv(text, season_code=season_code, source=name)
        if len(part) != ROWS_PER_SEASON:
            raise ShotPanelMismatch(
                f"{name}: {len(part)} nonblank rows, expected {ROWS_PER_SEASON}"
            )
        parts.append(part)
    rows = pd.concat(parts, ignore_index=True)
    archive_path = (Path(archive_path) if archive_path is not None
                    else paths.MATCHES_PARQUET)
    _assert_file_identity(
        archive_path, MATCHES_SHA256, label=MATCHES_PATH,
        error=SourceDigestMismatch,
    )
    archive = pd.read_parquet(
        archive_path,
        columns=["match_id", "season_code", "date", "home_key", "away_key"],
    )
    return validate_and_join_shots(
        rows, archive, expected_quarantine=PINNED_QUARANTINE,
        expected_rows=RAW_ROWS, source_digests=digests,
    )


def load_pinned_training_shot_panel() -> ShotPanel:
    """Load only the fixed 1,900-row burn-in/training shot sidecar.

    The path set is not caller-configurable.  Exactly ``E0_1415.csv`` through
    ``E0_1819.csv`` are hashed and opened; later-season shot files are neither
    enumerated nor read.  The tidy match archive is itself hash-pinned and is
    projected to identity columns only.  Any invalid selected row is a refusal:
    the one preregistered quarantine is in 2021/22 and cannot enter this panel.
    """
    expected = _expected_training_raw_digests()
    files = {name: paths.RAW_DIR / name for name in expected}
    texts, digests = _read_training_source_texts(files)

    parts: list[pd.DataFrame] = []
    for name in expected:
        season_code = name.removeprefix("E0_").removesuffix(".csv")
        part = parse_shot_csv(
            texts[name], season_code=season_code, source=name,
        )
        if len(part) != ROWS_PER_SEASON:
            raise ShotPanelMismatch(
                f"{name}: {len(part)} nonblank rows, expected {ROWS_PER_SEASON}"
            )
        parts.append(part)
    rows = pd.concat(parts, ignore_index=True)

    archive_path = paths.MATCHES_PARQUET
    if not archive_path.is_file():
        raise SourceDigestMismatch(
            f"{MATCHES_PATH}: pinned file is absent at {archive_path}"
        )
    archive_bytes = archive_path.read_bytes()
    archive_digest = hashlib.sha256(archive_bytes).hexdigest()
    expected_archive_digest = _expected_matches_sha256()
    if archive_digest != expected_archive_digest:
        raise SourceDigestMismatch(
            f"{MATCHES_PATH}: SHA-256 {archive_digest}, "
            f"expected {expected_archive_digest}"
        )
    archive = pd.read_parquet(
        io.BytesIO(archive_bytes),
        columns=["match_id", "season_code", "date", "home_key", "away_key"],
    )
    panel = validate_and_join_shots(
        rows, archive, expected_quarantine=None,
        expected_rows=TRAINING_HISTORY_ROWS, source_digests=digests,
    )
    expected_counts = {
        name.removeprefix("E0_").removesuffix(".csv"): ROWS_PER_SEASON
        for name in expected
    }
    observed_counts = (
        panel.frame["season_code"].astype(str).value_counts().to_dict()
    )
    if (panel.raw_rows != TRAINING_HISTORY_ROWS
            or len(panel.frame) != TRAINING_HISTORY_ROWS
            or panel.quarantine
            or observed_counts != expected_counts):
        raise ShotPanelMismatch(
            "training shot panel is not exactly 1,900 clean rows across the "
            f"five fixed seasons: counts={observed_counts}, "
            f"quarantine={len(panel.quarantine)}"
        )
    return panel


def load_pinned_training_fixtures(*, archive_path: Path | str | None = None,
                                  ) -> pd.DataFrame:
    """Return the exact ordered 1,520-row coefficient-training identities.

    This projects identity/schedule fields only.  Outcomes remain outside the
    frame and no model code is imported or called.
    """
    archive_path = (Path(archive_path) if archive_path is not None
                    else paths.MATCHES_PARQUET)
    _assert_file_identity(archive_path, MATCHES_SHA256, label=MATCHES_PATH)
    archive = pd.read_parquet(
        archive_path,
        columns=["match_id", "season", "date", "home_key", "away_key"],
    )
    frame = archive.loc[
        archive["season"].astype(str).isin(TRAINING_SEASONS),
        ["match_id", "season", "date", "home_key", "away_key"],
    ].copy()
    counts = frame["season"].astype(str).value_counts().to_dict()
    expected = {season: ROWS_PER_SEASON for season in TRAINING_SEASONS}
    if len(frame) != TRAINING_ROWS or counts != expected:
        raise FixtureSetMismatch(
            f"training archive counts are {counts}, expected {expected}"
        )
    return attach_training_cutoffs(frame)


@dataclass(frozen=True)
class DecisionFixture:
    """One outcome-free row of the immutable decision schedule."""

    match_id: str
    season: str
    block: str


def load_pinned_decision_schedule(
    *, corpus_path: Path | str | None = None,
) -> tuple[DecisionFixture, ...]:
    """Return the exact ordered, outcome-free decision schedule.

    The returned tuple binds fixture identity, season, and weekly resampling
    block together.  Later decision code must compare all three fields in
    order; accepting caller-supplied labels by count or set alone can change
    the confidence interval and season gates without changing fixture IDs.
    """
    corpus_path = (Path(corpus_path) if corpus_path is not None
                   else paths.FIT_DIR / "walkforward_predictions.parquet")
    _assert_file_identity(
        corpus_path, DECISION_CORPUS_SHA256, label=DECISION_CORPUS_PATH,
    )
    frame = pd.read_parquet(
        corpus_path, columns=["match_id", "season", "date", "block"],
    )
    ids = _ids(frame["match_id"].astype(str), label="frozen decision corpus")
    seasons = tuple(frame["season"].astype(str))
    blocks = tuple(frame["block"].astype(str))
    expected_seasons = {
        season: ROWS_PER_SEASON for season in
        ("2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25")
    }
    counts = frame["season"].astype(str).value_counts().to_dict()
    if len(frame) != 2_280 or counts != expected_seasons:
        raise FixtureSetMismatch(
            f"decision corpus season counts are {counts}, expected {expected_seasons}"
        )
    derived = attach_weekly_cutoffs(frame[["match_id", "season", "date"]])
    if tuple(derived["block"].astype(str)) != blocks:
        raise FixtureSetMismatch(
            "decision corpus block labels differ from derived (season, ISO week)"
        )
    if derived["block"].nunique() != 212:
        raise FixtureSetMismatch(
            f"decision corpus has {derived['block'].nunique()} blocks, expected 212"
        )
    return tuple(
        DecisionFixture(match_id=mid, season=season, block=block)
        for mid, season, block in zip(ids, seasons, blocks, strict=True)
    )


def load_pinned_decision_fixture_ids(
    *, corpus_path: Path | str | None = None,
) -> tuple[str, ...]:
    """Backward-compatible identity-only view of the frozen schedule."""
    return tuple(
        row.match_id for row in load_pinned_decision_schedule(
            corpus_path=corpus_path,
        )
    )


# ==========================================================================
# 2. Exact weekly cutoffs and causal shot/SOT features
# ==========================================================================

def attach_weekly_cutoffs(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Attach the frozen `(season, ISO year, ISO week)` opening-day cutoff.

    Row order is preserved.  ``cutoff`` is the minimum normalized date in the
    block, and all rows in that block share it.
    """
    _require_columns(fixtures, ("match_id", "season", "date"),
                     label="fixtures")
    out = fixtures.copy()
    ids = out["match_id"].astype(str)
    if ids.empty or (ids == "").any() or ids.duplicated().any():
        raise FixtureSetMismatch("fixture match_id values must be nonempty and unique")
    seasons = out["season"].astype(str).str.strip()
    if (seasons == "").any() or out["season"].isna().any():
        raise FixtureSetMismatch("fixture seasons must be nonnull and nonempty")
    out["season"] = seasons
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.normalize()
    if out["date"].isna().any():
        raise TimeBoundaryViolation("fixture dates must be finite parseable dates")
    iso = out["date"].dt.isocalendar()
    out["block"] = [
        f"{season}|{int(year)}W{int(week):02d}"
        for season, year, week in zip(out["season"], iso["year"], iso["week"])
    ]
    out["cutoff"] = out.groupby("block", sort=False)["date"].transform("min")
    if (out["date"] < out["cutoff"]).any():
        raise TimeBoundaryViolation("a fixture falls before its own block cutoff")
    return out


def attach_training_cutoffs(fixtures: pd.DataFrame) -> pd.DataFrame:
    """Attach and verify the exact 1,520-row, 142-block tune schedule."""
    _require_columns(fixtures, ("season",), label="training fixtures")
    counts = fixtures["season"].astype(str).value_counts().to_dict()
    expected_rows = {season: ROWS_PER_SEASON for season in TRAINING_SEASONS}
    if len(fixtures) != TRAINING_ROWS or counts != expected_rows:
        raise FitFailure(
            f"training schedule requires exactly {expected_rows}, got {counts}"
        )
    out = attach_weekly_cutoffs(fixtures)
    observed = out[["season", "block"]].drop_duplicates()["season"].value_counts().to_dict()
    if observed != TRAINING_BLOCK_COUNTS:
        raise FitFailure(
            f"training schedule block counts are {observed}, expected "
            f"{TRAINING_BLOCK_COUNTS}"
        )
    return out


def _validated_history(history: pd.DataFrame) -> pd.DataFrame:
    required = ("date", "home_key", "away_key", *SHOT_COLUMNS)
    _require_columns(history, required, label="shot history")
    out = history[list(required)].copy()
    out["date"] = pd.to_datetime(out["date"], errors="raise").dt.normalize()
    if out.duplicated(["date", "home_key", "away_key"]).any():
        raise ShotPanelMismatch("shot history has duplicate date/home/away keys")
    values = out[list(SHOT_COLUMNS)].to_numpy(dtype=float)
    if not np.isfinite(values).all():
        raise ShotValueInvalid("shot history contains a nonfinite measure")
    if (values < 0).any() or not np.equal(values, np.floor(values)).all():
        raise ShotValueInvalid("shot history measures must be nonnegative integers")
    if (out["HST"] > out["HS"]).any() or (out["AST"] > out["AS"]).any():
        raise ShotValueInvalid("shot history violates HST<=HS or AST<=AS")
    return out


def _ratios(history: pd.DataFrame, weights: np.ndarray,
            *, home_col: str, away_col: str, mean_home: float,
            mean_away: float) -> tuple[dict[str, float], dict[str, float]]:
    attack_num: dict[str, float] = {}
    attack_den: dict[str, float] = {}
    defence_num: dict[str, float] = {}
    defence_den: dict[str, float] = {}

    def add(num: dict[str, float], den: dict[str, float], team: str,
            w: float, normalized: float) -> None:
        num[team] = num.get(team, 0.0) + w * normalized
        den[team] = den.get(team, 0.0) + w

    for row, weight in zip(history.itertuples(index=False), weights):
        home = str(row.home_key)
        away = str(row.away_key)
        home_value = float(getattr(row, home_col))
        away_value = float(getattr(row, away_col))
        add(attack_num, attack_den, home, float(weight), home_value / mean_home)
        add(attack_num, attack_den, away, float(weight), away_value / mean_away)
        add(defence_num, defence_den, home, float(weight), away_value / mean_away)
        add(defence_num, defence_den, away, float(weight), home_value / mean_home)
    names = set(attack_den) | set(defence_den)
    attack = {t: (KAPPA + attack_num.get(t, 0.0))
                  / (KAPPA + attack_den.get(t, 0.0)) for t in names}
    defence = {t: (KAPPA + defence_num.get(t, 0.0))
                   / (KAPPA + defence_den.get(t, 0.0)) for t in names}
    return attack, defence


def shot_features(history: pd.DataFrame, fixtures: pd.DataFrame) -> pd.DataFrame:
    """Build the four frozen features at each fixture's block cutoff.

    ``fixtures`` must already carry ``cutoff`` (normally from
    :func:`attach_weekly_cutoffs`).  The mask is literally ``date < cutoff``;
    rows on the cutoff day and later cannot enter a weighted mean or team state.
    """
    hist = _validated_history(history)
    fixture_required = ("match_id", "cutoff", "home_key", "away_key")
    _require_columns(fixtures, fixture_required, label="feature fixtures")
    work = fixtures.copy()
    ids = work["match_id"].astype(str)
    if ids.empty or (ids == "").any() or ids.duplicated().any():
        raise FixtureSetMismatch("feature fixture ids must be nonempty and unique")
    work["cutoff"] = pd.to_datetime(work["cutoff"], errors="raise")
    if not (work["cutoff"] == work["cutoff"].dt.normalize()).all():
        raise TimeBoundaryViolation("every cutoff must be a normalized midnight date")

    records: list[dict[str, Any]] = []
    for cutoff, group in work.groupby("cutoff", sort=True):
        eligible = hist.loc[hist["date"] < cutoff].copy()
        if eligible.empty:
            raise FitFailure(f"{cutoff.date()}: no eligible row for league means")
        if (eligible["date"] >= cutoff).any():
            raise TimeBoundaryViolation(f"{cutoff.date()}: date>=cutoff entered history")
        age = (cutoff - eligible["date"]).dt.days.to_numpy(dtype=float)
        if (age <= 0).any():
            raise TimeBoundaryViolation(f"{cutoff.date()}: nonpositive history age")
        weights = np.power(2.0, -age / HALF_LIFE_DAYS)
        means = {
            col: float(np.average(eligible[col].to_numpy(float), weights=weights))
            for col in SHOT_COLUMNS
        }
        if any(not math.isfinite(v) or v <= 0.0 for v in means.values()):
            raise FitFailure(f"{cutoff.date()}: a weighted league mean is nonpositive")
        attack_shots, defence_shots = _ratios(
            eligible, weights, home_col="HS", away_col="AS",
            mean_home=means["HS"], mean_away=means["AS"],
        )
        attack_sot, defence_sot = _ratios(
            eligible, weights, home_col="HST", away_col="AST",
            mean_home=means["HST"], mean_away=means["AST"],
        )
        for row in group.itertuples(index=False):
            home = str(row.home_key)
            away = str(row.away_key)
            hs = (means["HS"] * attack_shots.get(home, 1.0)
                  * defence_shots.get(away, 1.0))
            ass = (means["AS"] * attack_shots.get(away, 1.0)
                   * defence_shots.get(home, 1.0))
            hst = (means["HST"] * attack_sot.get(home, 1.0)
                   * defence_sot.get(away, 1.0))
            ast = (means["AST"] * attack_sot.get(away, 1.0)
                   * defence_sot.get(home, 1.0))
            records.append({
                "match_id": str(row.match_id), "cutoff": cutoff,
                "home_key": home, "away_key": away,
                "HS_hat": hs, "AS_hat": ass, "HST_hat": hst,
                "AST_hat": ast,
                "x1": hst - ast,
                "x2": (hs - hst) - (ass - ast),
                "x3": hst + ast,
                "x4": (hs - hst) + (ass - ast),
            })
    result = pd.DataFrame.from_records(records)
    result = result.set_index("match_id").loc[ids].reset_index()
    if not np.isfinite(result[list(FEATURE_NAMES)].to_numpy(float)).all():
        raise FitFailure("a constructed shot feature is nonfinite")
    return result


# ==========================================================================
# 3. Training-only scaling and the one residual-logit tilt
# ==========================================================================

@dataclass(frozen=True)
class FeatureScaler:
    means: tuple[float, float, float, float]
    standard_deviations: tuple[float, float, float, float]
    n_training: int
    seasons: tuple[str, ...]


def _fit_training_scaler(features: pd.DataFrame) -> FeatureScaler:
    """Fit population moments only on the four frozen 380-row tune seasons."""
    _require_columns(features, ("match_id", "season", *FEATURE_NAMES),
                     label="training features")
    training_ids = features["match_id"].astype(str)
    if (training_ids == "").any() or training_ids.duplicated().any():
        raise FixtureSetMismatch(
            "training feature match_id values must be nonempty and unique"
        )
    seasons = features["season"].astype(str)
    counts = seasons.value_counts().to_dict()
    expected = {season: ROWS_PER_SEASON for season in TRAINING_SEASONS}
    if len(features) != TRAINING_ROWS or counts != expected:
        raise FitFailure(
            f"scaler requires exactly {expected} ({TRAINING_ROWS} rows), got {counts}"
        )
    x = features[list(FEATURE_NAMES)].to_numpy(dtype=float)
    if not np.isfinite(x).all():
        raise FitFailure("training features contain nonfinite values")
    means = x.mean(axis=0)
    sd = x.std(axis=0, ddof=0)
    if not np.isfinite(sd).all() or (sd <= 0.0).any():
        raise FitFailure("a training feature has zero or nonfinite population sd")
    return FeatureScaler(
        means=tuple(float(v) for v in means),
        standard_deviations=tuple(float(v) for v in sd),
        n_training=TRAINING_ROWS, seasons=TRAINING_SEASONS,
    )


def _standardize_features(features: pd.DataFrame,
                          scaler: FeatureScaler) -> np.ndarray:
    _require_columns(features, FEATURE_NAMES, label="features")
    x = features[list(FEATURE_NAMES)].to_numpy(dtype=float)
    means = np.asarray(scaler.means, dtype=np.float64)
    sd = np.asarray(scaler.standard_deviations, dtype=np.float64)
    if means.shape != (4,) or sd.shape != (4,) or not np.isfinite(x).all():
        raise FitFailure("feature/scaler shape or finiteness is invalid")
    if not np.isfinite(means).all() or not np.isfinite(sd).all() or (sd <= 0).any():
        raise FitFailure("scaler moments are invalid")
    return (x - means) / sd


def _round_training_native(native_probs: np.ndarray) -> np.ndarray:
    """Apply the native ledger's independent eight-decimal cell rounding.

    Amendment 1 permits the bounded discrepancy created by three independent
    cells.  The returned values are immutable ledger cells, not yet the
    normalized probabilities supplied to the residual-logit model.
    """
    native = _check_probabilities(native_probs, label="unrounded training native",
                                  strictly_positive=True)
    rounded = np.round(native, 8)
    return _check_stored_native_probabilities(
        rounded, label="rounded training native",
    )


def _check_stored_native_probabilities(
    probs: np.ndarray, *, label: str,
) -> np.ndarray:
    """Validate exact eight-decimal native ledger cells under Amendment 1."""
    p = np.asarray(probs, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ProbabilityInvalid(
            f"{label} probabilities must have shape (n,3), got {p.shape}"
        )
    if not np.isfinite(p).all():
        raise ProbabilityInvalid(f"{label} probabilities contain nonfinite values")
    if (p <= 0.0).any() or (p > 1.0).any():
        raise ProbabilityInvalid(
            f"{label} probabilities must be strictly positive and at most one"
        )
    if any(float(value) != round(float(value), 8) for value in p.flat):
        raise ProbabilityInvalid(
            f"{label} is not the exact eight-decimal stored native value"
        )
    total = p.sum(axis=1)
    if not np.all(
        np.abs(total - 1.0) <= NATIVE_STORED_SUM_TOLERANCE
    ):
        worst = float(np.max(np.abs(total - 1.0)))
        raise ProbabilityInvalid(
            f"{label} stored native probabilities do not sum within "
            f"{NATIVE_STORED_SUM_TOLERANCE:g} (worst {worst})"
        )
    return p


def _native_model_probabilities(
    native_stored: np.ndarray, *, label: str = "stored native",
) -> np.ndarray:
    """Normalize accepted stored native cells solely for model arithmetic."""
    stored = _check_stored_native_probabilities(native_stored, label=label)
    model = stored / stored.sum(axis=1, keepdims=True)
    return _check_probabilities(
        model, label=f"{label} model normalization", strictly_positive=True,
    )


def _check_probabilities(probs: np.ndarray, *, label: str,
                         strictly_positive: bool) -> np.ndarray:
    p = np.asarray(probs, dtype=np.float64)
    if p.ndim != 2 or p.shape[1] != 3:
        raise ProbabilityInvalid(f"{label} probabilities must have shape (n,3), got {p.shape}")
    if not np.isfinite(p).all():
        raise ProbabilityInvalid(f"{label} probabilities contain nonfinite values")
    if (p < 0.0).any() or (p > 1.0).any():
        raise ProbabilityInvalid(f"{label} probability is outside [0,1]")
    if strictly_positive and (p <= 0.0).any():
        raise ProbabilityInvalid(f"{label} probabilities must be strictly positive")
    total = p.sum(axis=1)
    if not np.all(
        np.abs(total - 1.0) <= MODEL_PROBABILITY_SUM_TOLERANCE
    ):
        worst = float(np.max(np.abs(total - 1.0)))
        raise ProbabilityInvalid(
            f"{label} probabilities do not sum to one within "
            f"{MODEL_PROBABILITY_SUM_TOLERANCE:g} (worst {worst})"
        )
    return p


def _check_z(z: np.ndarray, n: int) -> np.ndarray:
    arr = np.asarray(z, dtype=np.float64)
    if arr.shape != (n, 4) or not np.isfinite(arr).all():
        raise FitFailure(f"standardized features must be finite ({n},4), got {arr.shape}")
    return arr


def _check_y(y: Sequence[int] | np.ndarray, n: int) -> np.ndarray:
    raw = np.asarray(y)
    if raw.shape != (n,):
        raise FitFailure(f"outcome shape {raw.shape} does not match {n} rows")
    try:
        numeric = raw.astype(float)
    except (TypeError, ValueError) as exc:
        raise FitFailure("outcomes must be integer codes 0/1/2") from exc
    if not np.isfinite(numeric).all() or not np.equal(numeric, np.floor(numeric)).all():
        raise FitFailure("outcomes must be finite integer codes 0/1/2")
    codes = numeric.astype(int)
    if not np.isin(codes, (0, 1, 2)).all():
        raise FitFailure("outcomes must be 0=home, 1=draw, 2=away")
    return codes


def _beta_matrix(beta: np.ndarray | Sequence[float]) -> np.ndarray:
    arr = np.asarray(beta, dtype=np.float64)
    if arr.size != 8 or not np.isfinite(arr).all():
        raise FitFailure("tilt beta must contain exactly eight finite coefficients")
    return arr.reshape(2, 4)


def _transform_unchecked(native: np.ndarray, z: np.ndarray,
                         beta: np.ndarray) -> np.ndarray:
    eta_h = np.log(native[:, 0] / native[:, 2]) + z @ beta[0]
    eta_d = np.log(native[:, 1] / native[:, 2]) + z @ beta[1]
    eta = np.column_stack((eta_h, eta_d, np.zeros(len(native), dtype=float)))
    eta -= eta.max(axis=1, keepdims=True)
    exp_eta = np.exp(eta)
    return exp_eta / exp_eta.sum(axis=1, keepdims=True)


def _transform_probabilities(native_probs: np.ndarray, z: np.ndarray,
                             beta: np.ndarray | Sequence[float]) -> np.ndarray:
    """Apply the fixed no-intercept residual multinomial-logit transform."""
    native_stored = _check_stored_native_probabilities(
        native_probs, label="native comparator",
    )
    native_model = _native_model_probabilities(
        native_stored, label="native comparator",
    )
    zz = _check_z(z, len(native_model))
    bb = _beta_matrix(beta)
    q = _transform_unchecked(native_model, zz, bb)
    return _check_probabilities(q, label=ARM_NAME, strictly_positive=False)


def _tilt_loss_gradient(beta: np.ndarray | Sequence[float],
                        native_probs: np.ndarray, z: np.ndarray,
                        y: Sequence[int] | np.ndarray,
                        ) -> tuple[float, np.ndarray]:
    """Exact sum-NLL + 0.5||beta||² objective and analytic gradient."""
    native = _check_probabilities(native_probs, label="native",
                                  strictly_positive=True)
    zz = _check_z(z, len(native))
    codes = _check_y(y, len(native))
    bb = _beta_matrix(beta)
    q = _transform_unchecked(native, zz, bb)
    loss = -float(np.log(q[np.arange(len(q)), codes]).sum())
    loss += 0.5 * float(np.square(bb).sum())
    target_h = (codes == 0).astype(float)
    target_d = (codes == 1).astype(float)
    grad = np.vstack(((q[:, 0] - target_h) @ zz,
                      (q[:, 1] - target_d) @ zz)) + bb
    return loss, grad.reshape(8)


@dataclass(frozen=True)
class TiltFit:
    success: bool
    status: int
    beta: tuple[float, ...]
    objective: float
    independent_objective: float
    objective_consistent: bool
    # ``gradient`` is the exact SciPy-reported Jacobian.  The independent
    # vector is recomputed outside the optimizer callback at the returned x.
    gradient: tuple[float, ...]
    independent_gradient: tuple[float, ...]
    gradient_consistent: bool
    independent_gradient_max_abs: float
    gradient_certified: bool
    beta_distance_actual_bound_l2: float
    beta_distance_acceptance_ceiling_l2: float
    iterations: int
    function_evaluations: int
    gradient_evaluations: int
    message: str

    def matrix(self) -> np.ndarray:
        return np.asarray(self.beta, dtype=np.float64).reshape(2, 4)


class _TiltOptimizerFailure(FitFailure):
    """Finite optimizer refusal carrying the exact receiptable result."""

    def __init__(self, fit: TiltFit):
        self.fit = fit
        super().__init__(
            f"L-BFGS-B failed: success={fit.success}, status={fit.status}, "
            f"objective_consistent={fit.objective_consistent}, "
            f"gradient_consistent={fit.gradient_consistent}, "
            f"gradient_certified={fit.gradient_certified}, "
            f"independent_gradient_max_abs="
            f"{fit.independent_gradient_max_abs}, message={fit.message}"
        )


def _fit_residual_tilt(native_probs: np.ndarray, z: np.ndarray,
                       y: Sequence[int] | np.ndarray) -> TiltFit:
    """Run the one deterministic float64 L-BFGS-B fit from an all-zero start."""
    native = _check_probabilities(native_probs, label="native",
                                  strictly_positive=True)
    zz = _check_z(z, len(native))
    codes = _check_y(y, len(native))

    def objective(flat: np.ndarray) -> tuple[float, np.ndarray]:
        bb = np.asarray(flat, dtype=np.float64).reshape(2, 4)
        q = _transform_unchecked(native, zz, bb)
        loss = -float(np.log(q[np.arange(len(q)), codes]).sum())
        loss += 0.5 * float(np.square(bb).sum())
        target_h = (codes == 0).astype(float)
        target_d = (codes == 1).astype(float)
        grad = np.vstack(((q[:, 0] - target_h) @ zz,
                          (q[:, 1] - target_d) @ zz)) + bb
        return loss, grad.reshape(8)

    result = minimize(
        objective, np.zeros(8, dtype=np.float64), method="L-BFGS-B", jac=True,
        options={"maxiter": 10_000, "ftol": 1e-12, "gtol": 1e-10},
    )
    required = {
        "success", "status", "x", "fun", "jac", "nit", "nfev", "njev",
        "message",
    }
    missing = sorted(name for name in required if not hasattr(result, name))
    if missing:
        raise FitFailure(f"L-BFGS-B result is missing fields: {missing}")
    if type(result.success) is not bool or type(result.status) is not int:
        raise FitFailure("L-BFGS-B result success/status types are malformed")
    if (not isinstance(result.fun, (float, np.floating))
            or isinstance(result.fun, (bool, np.bool_))):
        raise FitFailure("L-BFGS-B result objective type is malformed")
    if (not isinstance(result.x, np.ndarray)
            or result.x.shape != (8,) or result.x.dtype != np.dtype(np.float64)):
        raise FitFailure("L-BFGS-B result coefficient vector is not float64[8]")
    if (not isinstance(result.jac, np.ndarray)
            or result.jac.shape != (8,)
            or result.jac.dtype != np.dtype(np.float64)):
        raise FitFailure("L-BFGS-B result gradient vector is not float64[8]")
    if (type(result.nit) is not int or result.nit < 0
            or type(result.nfev) is not int or result.nfev < 1
            or type(result.njev) is not int or result.njev < 1):
        raise FitFailure("L-BFGS-B result evaluation counts are malformed")
    if type(result.message) is not str or not result.message:
        raise FitFailure("L-BFGS-B result message type is malformed")
    if (not np.isfinite(result.fun) or not np.isfinite(result.x).all()
            or not np.isfinite(result.jac).all()):
        raise FitFailure(
            f"L-BFGS-B failed: success={result.success}, status={result.status}, "
            f"message={result.message}"
        )
    independent_objective, independent_gradient = _tilt_loss_gradient(
        result.x, native, zz, codes,
    )
    objective_consistent = math.isclose(
        float(result.fun), independent_objective,
        rel_tol=1e-13, abs_tol=1e-10,
    )
    gradient_consistent = bool(np.allclose(
        result.jac, independent_gradient, rtol=1e-11, atol=1e-10,
    ))
    independent_gradient_max_abs = float(
        np.max(np.abs(independent_gradient))
    )
    gradient_certified = (
        independent_gradient_max_abs <= OPTIMIZER_GRADIENT_TOLERANCE
    )
    fit = TiltFit(
        success=result.success, status=result.status,
        beta=tuple(float(v) for v in result.x), objective=float(result.fun),
        independent_objective=float(independent_objective),
        objective_consistent=objective_consistent,
        gradient=tuple(float(v) for v in result.jac),
        independent_gradient=tuple(float(v) for v in independent_gradient),
        gradient_consistent=gradient_consistent,
        independent_gradient_max_abs=independent_gradient_max_abs,
        gradient_certified=gradient_certified,
        beta_distance_actual_bound_l2=float(
            np.linalg.norm(independent_gradient, ord=2)
        ),
        beta_distance_acceptance_ceiling_l2=(
            OPTIMIZER_BETA_DISTANCE_BOUND_L2
        ),
        iterations=int(result.nit), function_evaluations=int(result.nfev),
        gradient_evaluations=int(result.njev), message=result.message,
    )
    if (not fit.success or not fit.objective_consistent
            or not fit.gradient_consistent or not fit.gradient_certified):
        # The one-shot coordinator must persist this exact finite failure as an
        # optimizer receipt before stopping.  Raising a typed exception keeps
        # existing fit-call semantics while preventing provenance loss.
        raise _TiltOptimizerFailure(fit)
    return fit


def _fit_training_tilt_after_h(
    features: pd.DataFrame, native_probs: np.ndarray,
    y: Sequence[int] | np.ndarray, *, native_ids: Sequence[Any],
    outcome_ids: Sequence[Any],
) -> tuple[FeatureScaler, TiltFit]:
    """Internal training arithmetic for the runner after live H verification.

    This function is deliberately private and is not a lifecycle authority.
    The separately audited runner must generate all arrays itself and re-run
    committed-manifest verification immediately before calling it.
    """
    scaler = _fit_training_scaler(features)
    feature_ids = _ids(features["match_id"].astype(str), label="training features")
    pinned_ids = tuple(load_pinned_training_fixtures()["match_id"].astype(str))
    if feature_ids != pinned_ids:
        raise FixtureSetMismatch(
            "training feature keys differ from the pinned archive order"
        )
    if (_ids(native_ids, label="training native") != feature_ids
            or _ids(outcome_ids, label="training outcomes") != feature_ids):
        raise FixtureSetMismatch(
            "training feature/native/outcome keys are not identical and ordered"
        )
    z = _standardize_features(features, scaler)
    native_stored = _check_stored_native_probabilities(
        native_probs, label="assembled training native",
    )
    if len(native_stored) != TRAINING_ROWS:
        raise FitFailure(
            f"training native panel has {len(native_stored)} rows, expected {TRAINING_ROWS}"
        )
    native_model = _native_model_probabilities(
        native_stored, label="rounded training native",
    )
    fit = _fit_residual_tilt(native_model, z, y)
    return scaler, fit


# ==========================================================================
# 4. Exact fixture-set guard, paired RPS, and frozen block bootstraps
# ==========================================================================

def _ids(values: Sequence[Any], *, label: str) -> tuple[str, ...]:
    ids = tuple(str(v) for v in values)
    if not ids:
        raise FixtureSetMismatch(f"{label} fixture set is empty")
    if any(v == "" for v in ids):
        raise FixtureSetMismatch(f"{label} contains an empty match_id")
    if len(ids) != len(set(ids)):
        raise FixtureSetMismatch(f"{label} contains duplicate match_id values")
    return ids


def assert_fixture_sets(*, candidate_ids: Sequence[Any],
                        native_ids: Sequence[Any], market_ids: Sequence[Any],
                        outcome_ids: Sequence[Any],
                        expected_ids: Sequence[Any] | None = None,
                        ) -> tuple[str, ...]:
    """Require identical ordered, unique keys; never sort or intersect them."""
    named = {
        "candidate": _ids(candidate_ids, label="candidate"),
        "native": _ids(native_ids, label="native"),
        "market": _ids(market_ids, label="market"),
        "outcome": _ids(outcome_ids, label="outcome"),
    }
    reference = named["candidate"]
    for label, ids in named.items():
        if ids != reference:
            raise FixtureSetMismatch(
                f"{label} ordered fixture keys differ from candidate keys"
            )
    if expected_ids is not None:
        expected = _ids(expected_ids, label="expected")
        if reference != expected:
            raise FixtureSetMismatch("fixture keys differ from the frozen expected order")
    return reference


def _rps(probs: np.ndarray, y: np.ndarray) -> np.ndarray:
    onehot = np.zeros_like(probs)
    onehot[np.arange(len(y)), y] = 1.0
    return 0.5 * (
        np.square(probs[:, 0] - onehot[:, 0])
        + np.square(probs[:, 0] + probs[:, 1]
                    - onehot[:, 0] - onehot[:, 1])
    )


@dataclass(frozen=True)
class PairScores:
    fixture_ids: tuple[str, ...]
    candidate_rps: tuple[float, ...]
    native_rps: tuple[float, ...]
    market_rps: tuple[float, ...]
    d_native: tuple[float, ...]
    d_market: tuple[float, ...]

    @property
    def mean_d_native(self) -> float:
        return float(np.mean(self.d_native))

    @property
    def mean_d_market(self) -> float:
        return float(np.mean(self.d_market))


def _paired_rps_unchecked(
    candidate_probs: np.ndarray, native_probs: np.ndarray,
    market_probs: np.ndarray, y: Sequence[int] | np.ndarray, *,
    candidate_ids: Sequence[Any], native_ids: Sequence[Any],
    market_ids: Sequence[Any], outcome_ids: Sequence[Any],
    expected_ids: Sequence[Any],
) -> PairScores:
    ids = assert_fixture_sets(
        candidate_ids=candidate_ids, native_ids=native_ids,
        market_ids=market_ids, outcome_ids=outcome_ids,
        expected_ids=expected_ids,
    )
    candidate = _check_probabilities(candidate_probs, label=ARM_NAME,
                                     strictly_positive=False)
    native = _check_stored_native_probabilities(
        native_probs, label="native comparator",
    )
    market = _check_probabilities(market_probs, label="market",
                                  strictly_positive=True)
    if not (len(candidate) == len(native) == len(market) == len(ids)):
        raise FixtureSetMismatch("probability row counts do not match fixture keys")
    codes = _check_y(y, len(ids))
    cr = _rps(candidate, codes)
    nr = _rps(native, codes)
    mr = _rps(market, codes)
    return PairScores(
        fixture_ids=ids,
        candidate_rps=tuple(float(v) for v in cr),
        native_rps=tuple(float(v) for v in nr),
        market_rps=tuple(float(v) for v in mr),
        d_native=tuple(float(v) for v in cr - nr),
        d_market=tuple(float(v) for v in cr - mr),
    )


@dataclass(frozen=True)
class BootstrapCI:
    mean: float
    low: float
    high: float
    n_blocks: int
    n_boot: int
    seed: int


def _block_bootstrap(delta: Sequence[float] | np.ndarray,
                     labels: Sequence[Any], *, seed: int) -> BootstrapCI:
    values = np.asarray(delta, dtype=np.float64)
    lab = np.asarray(labels, dtype=object)
    if values.ndim != 1 or lab.shape != values.shape or values.size == 0:
        raise ShotValueInvalid("bootstrap delta/label vectors must be nonempty and aligned")
    if (not np.isfinite(values).all()
            or any(v is None or bool(pd.isna(v)) or str(v) == "" for v in lab)):
        raise ShotValueInvalid("bootstrap values must be finite and labels nonempty")
    ordered = list(dict.fromkeys(str(v) for v in lab))
    sums = np.array([values[np.array([str(v) == block for v in lab])].sum()
                     for block in ordered], dtype=float)
    counts = np.array([sum(str(v) == block for v in lab)
                       for block in ordered], dtype=float)
    rng = np.random.Generator(np.random.PCG64(seed))
    sampled = rng.integers(0, len(ordered), size=(N_BOOT, len(ordered)))
    boot = sums[sampled].sum(axis=1) / counts[sampled].sum(axis=1)
    low, high = np.percentile(boot, (2.5, 97.5))
    return BootstrapCI(
        mean=float(values.mean()), low=float(low), high=float(high),
        n_blocks=len(ordered), n_boot=N_BOOT, seed=int(seed),
    )


def _per_season_means_unchecked(delta: Sequence[float] | np.ndarray,
                                seasons: Sequence[Any]) -> dict[str, float]:
    values = np.asarray(delta, dtype=float)
    labels = np.asarray(seasons, dtype=object)
    if (values.ndim != 1 or labels.shape != values.shape
            or not np.isfinite(values).all()
            or any(v is None or bool(pd.isna(v)) or str(v) == "" for v in labels)):
        raise ShotValueInvalid("season delta/label vectors must be finite and aligned")
    ordered = list(dict.fromkeys(str(v) for v in labels))
    return {season: float(values[np.array([str(v) == season for v in labels])].mean())
            for season in ordered}


# ==========================================================================
# 5. Non-self-referential H-manifest construction and verification hooks
# ==========================================================================

def _canonical_json(value: Any) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False)


def canonical_manifest_bytes(manifest: Mapping[str, Any]) -> bytes:
    """The only byte serialization accepted for committed H/K manifests."""
    return (_canonical_json(dict(manifest)) + "\n").encode("ascii")


def _exact_json_value(left: Any, right: Any) -> bool:
    """Compare JSON values by their strict canonical representation.

    Python considers values such as ``4180`` and ``4180.0`` equal.  A frozen
    receipt must not: those are different canonical JSON bytes and therefore
    different contracts.
    """
    try:
        return _canonical_json(left) == _canonical_json(right)
    except (TypeError, ValueError):
        return False


def _canonical_sha256(schema: str, value: Any) -> str:
    """Domain-separate the hash of one strict JSON value."""
    payload = f"{schema}\n{_canonical_json(value)}\n".encode("ascii")
    return hashlib.sha256(payload).hexdigest()


def _safe_relative(path: str) -> bool:
    candidate = Path(path)
    return (not candidate.is_absolute() and ".." not in candidate.parts
            and str(candidate) not in ("", "."))


def _git_bytes(root: Path, *args: str) -> bytes:
    try:
        result = subprocess.run(
            (_GIT_EXECUTABLE, "-C", str(root), *args), capture_output=True,
            check=False, timeout=30, env=dict(_GIT_ENVIRONMENT),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise LockMismatch(f"git {' '.join(args)} could not run: {exc}") from exc
    if result.returncode != 0:
        message = result.stderr.decode("utf-8", "replace").strip()
        raise LockMismatch(f"git {' '.join(args)} failed: {message}")
    return result.stdout


def _git_text(root: Path, *args: str) -> str:
    return _git_bytes(root, *args).decode("utf-8", "replace").strip()


def _require_git_regular_blobs(
    root: Path, commit: str, paths_to_check: Sequence[str], *, label: str,
) -> None:
    """Require an exact set of non-executable regular blobs at one commit."""
    paths_tuple = tuple(paths_to_check)
    expected = set(paths_tuple)
    if not expected or len(expected) != len(paths_tuple):
        raise LockMismatch(f"{label} Git path set is empty or duplicated")
    raw = _git_bytes(
        root, "ls-tree", "-rz", commit, "--", *tuple(sorted(expected)),
    )
    observed: dict[str, tuple[str, str]] = {}
    try:
        for entry in raw.split(b"\0"):
            if not entry:
                continue
            metadata, encoded_path = entry.split(b"\t", 1)
            mode, kind, _ = metadata.decode("ascii").split()
            path = encoded_path.decode("utf-8", "strict")
            if path in observed:
                raise ValueError("duplicate path")
            observed[path] = (mode, kind)
    except (UnicodeError, ValueError) as exc:
        raise LockMismatch(f"{label} Git tree output is malformed") from exc
    if (set(observed) != expected
            or any(value != ("100644", "blob") for value in observed.values())):
        raise LockMismatch(
            f"{label} paths must be exact 100644 regular blobs"
        )


def _native_family_digest(root: Path) -> tuple[int, str]:
    listed = _git_text(
        root, "ls-tree", "-r", "--name-only", NATIVE_PARENT_COMMIT,
        "--", "epl", "src/wcmodel",
    ).splitlines()
    relatives = sorted(
        path for path in listed
        if path.endswith(".py") and not path.startswith("epl/tests/")
    )
    digest = hashlib.sha256()
    for relative in relatives:
        name = relative.encode("utf-8")
        blob = _git_bytes(root, "show", f"{NATIVE_PARENT_COMMIT}:{relative}")
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(blob).to_bytes(8, "big")); digest.update(blob)
    return len(relatives), digest.hexdigest()


def _resolved_packages() -> dict[str, str]:
    versions = {"python": sys.version.split()[0]}
    for name in RESOLVED_PACKAGE_NAMES:
        try:
            versions[name] = importlib.metadata.version(name)
        except importlib.metadata.PackageNotFoundError:
            versions[name] = "MISSING"
    return versions


def _identity_record(root: Path, relative: str, expected: str, *,
                     label: str) -> dict[str, Any]:
    path = root / relative
    _assert_file_identity(path, expected, label=label, error=LockMismatch)
    return {"path": relative, "sha256": expected,
            "bytes": int(path.stat().st_size)}


def _runtime_dependency_closure(repo_root: Path | str) -> dict[str, Any]:
    """Hash the two active runtime modules used by the shot-sidecar reader.

    ``epl.paths`` and ``epl.teams`` are outside the three-file H change set but
    execute in-process while identities are projected.  Record the bytes of
    the modules that are actually imported, and refuse an import resolved from
    anywhere other than this repository.
    """
    root = Path(repo_root).resolve()
    modules = (
        ("epl.paths", paths, "epl/paths.py"),
        ("epl.teams", teams, "epl/teams.py"),
    )
    records: dict[str, Any] = {}
    for name, module, relative in modules:
        module_file = getattr(module, "__file__", None)
        if not isinstance(module_file, str) or not module_file:
            raise LockMismatch(f"{name}: active module has no source path")
        active = Path(module_file).resolve()
        expected = (root / relative).resolve()
        if active != expected:
            raise LockMismatch(
                f"{name}: active module is {active}, expected {expected}"
            )
        try:
            raw = active.read_bytes()
        except OSError as exc:
            raise LockMismatch(f"{name}: active source could not be read: {exc}") from exc
        records[name] = {
            "path": relative,
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw),
        }
    return records


def _native_runtime_lock_snapshot() -> dict[str, Any]:
    """Discover the worker runtime lock through the H-hashed runner bytes.

    The import is deliberately lazy: ``shots_harness`` imports this module,
    while H validation happens only after both modules can be fully loaded.
    Keeping the discovery implementation in the runner avoids maintaining a
    second, weaker copy of the sandbox/runtime rules here.
    """
    try:
        from epl import shots_harness

        lock = shots_harness._native_sandbox_contract()["runtime_closure"]
        raw = canonical_manifest_bytes(lock)
    except (ImportError, KeyError, TypeError, ValueError, ShotsError) as exc:
        raise LockMismatch(f"native runtime lock could not be built: {exc}") from exc
    if json.loads(raw.decode("ascii")) != lock:
        raise LockMismatch("native runtime lock is not strict canonical JSON")
    return dict(lock)


def _schedule_iso_date(value: Any) -> str:
    try:
        date = pd.Timestamp(value)
    except (TypeError, ValueError, OverflowError) as exc:
        raise TimeBoundaryViolation(
            f"schedule date is not a valid timestamp: {value!r}"
        ) from exc
    if pd.isna(date) or date != date.normalize():
        raise TimeBoundaryViolation("schedule dates must be finite midnight dates")
    return date.date().isoformat()


def _schedule_identity_rows(frame: pd.DataFrame) -> tuple[dict[str, Any], ...]:
    required = {
        "match_id", "season", "date", "home_key", "away_key", "block",
        "cutoff",
    }
    missing = sorted(required - set(frame.columns))
    if missing:
        raise FixtureSetMismatch(f"schedule identity fields are absent: {missing}")
    return tuple({
        "ordinal": ordinal,
        "match_id": str(row.match_id),
        "season": str(row.season),
        "date": _schedule_iso_date(row.date),
        "home_key": str(row.home_key),
        "away_key": str(row.away_key),
        "block": str(row.block),
        "cutoff": _schedule_iso_date(row.cutoff),
    } for ordinal, row in enumerate(frame.itertuples(index=False)))


def _schedule_identity_digest(
    schema: str, rows: Sequence[Mapping[str, Any]],
) -> str:
    digest = hashlib.sha256((schema + "\n").encode("ascii"))
    for row in rows:
        digest.update((_canonical_json(dict(row)) + "\n").encode("ascii"))
    return digest.hexdigest()


def _expected_quarantine_identity() -> dict[str, Any]:
    """Return the full literal identity of the sole sanctioned bad raw row."""
    return {
        "date": "2021-08-15",
        "home_key": "newcastle",
        "away_key": "west_ham",
        "values": [17.0, 8.0, 3.0, 9.0],
        "reason": "AST>AS",
        "source": "E0_2122.csv",
        "raw_row": 10,
        "match_id": "57b6538de8a5404c",
    }


def _fixed_h_invariants(repo_root: Path | str) -> dict[str, Any]:
    """Recompute the outcome/probability-free row and schedule H receipts."""
    root = Path(repo_root).resolve()
    raw_dir = root / "data/epl/raw"
    archive_path = root / MATCHES_PATH
    decision_path = root / DECISION_CORPUS_PATH

    panel = load_pinned_shot_panel(
        raw_dir=raw_dir, archive_path=archive_path,
    )
    if panel.raw_rows != 4_180 or len(panel.frame) != 4_179:
        raise LockMismatch(
            "shot-panel H invariants require exactly 4,180 raw and 4,179 clean rows"
        )
    if len(panel.quarantine) != 1:
        raise LockMismatch("shot-panel H invariants require exactly one quarantine")
    quarantined = panel.quarantine[0]
    quarantine_identity = {
        "date": quarantined.date,
        "home_key": quarantined.home_key,
        "away_key": quarantined.away_key,
        "values": [float(value) for value in quarantined.values],
        "reason": quarantined.reason,
        "source": quarantined.source,
        "raw_row": int(quarantined.raw_row),
        "match_id": quarantined.match_id,
    }
    if not _exact_json_value(
        quarantine_identity, _expected_quarantine_identity(),
    ):
        raise LockMismatch("the exact quarantined raw-row identity changed")

    training_codes = ("1415", "1516", "1617", "1718", "1819")
    training_universe = panel.frame.loc[
        panel.frame["season_code"].astype(str).isin(training_codes)
    ]
    training_universe_counts = (
        training_universe["season_code"].astype(str).value_counts().to_dict()
    )
    expected_universe_counts = {code: 380 for code in training_codes}
    if (len(training_universe) != 1_900
            or training_universe_counts != expected_universe_counts):
        raise LockMismatch(
            "training shot universe is not exactly 1,900 clean rows: "
            f"{training_universe_counts}"
        )

    training = load_pinned_training_fixtures(archive_path=archive_path)
    training_rows = _schedule_identity_rows(training)
    training_blocks = len({row["block"] for row in training_rows})
    expected_training_blocks = {
        "2015/16": 35, "2016/17": 36, "2017/18": 36, "2018/19": 35,
    }
    observed_training_blocks = (
        training.groupby(training["season"].astype(str))["block"]
        .nunique().to_dict()
    )
    if (len(training_rows) != 1_520 or training_blocks != 142
            or observed_training_blocks != expected_training_blocks):
        raise LockMismatch(
            "training schedule H invariants require 1,520 rows and 142 blocks"
        )
    _assert_file_identity(
        archive_path, MATCHES_SHA256, label=MATCHES_PATH, error=LockMismatch,
    )

    pinned_decision = load_pinned_decision_schedule(corpus_path=decision_path)
    decision = pd.read_parquet(
        decision_path,
        columns=[
            "match_id", "season", "date", "home_key", "away_key", "block",
        ],
    )
    derived = attach_weekly_cutoffs(
        decision[["match_id", "season", "date"]]
    )
    observed_decision = tuple(zip(
        decision["match_id"].astype(str),
        decision["season"].astype(str),
        decision["block"].astype(str),
        strict=True,
    ))
    expected_decision = tuple(
        (row.match_id, row.season, row.block) for row in pinned_decision
    )
    if observed_decision != expected_decision:
        raise LockMismatch("decision schedule identity projection changed in order")
    decision = decision.copy()
    decision["cutoff"] = derived["cutoff"].to_numpy(copy=True)
    decision_rows = _schedule_identity_rows(decision)
    decision_blocks = len({row["block"] for row in decision_rows})
    if len(decision_rows) != 2_280 or decision_blocks != 212:
        raise LockMismatch(
            "decision schedule H invariants require 2,280 rows and 212 blocks"
        )
    _assert_file_identity(
        decision_path, DECISION_CORPUS_SHA256,
        label=DECISION_CORPUS_PATH, error=LockMismatch,
    )

    return {
        "schema": "epl-shots-h-invariants-1",
        "raw_rows": 4_180,
        "clean_rows": 4_179,
        "quarantine_identity": quarantine_identity,
        "training_universe_rows": 1_900,
        "training_schedule": {
            "rows": 1_520,
            "blocks": 142,
            "sha256": _schedule_identity_digest(
                "epl-shots-training-schedule-1", training_rows,
            ),
        },
        "decision_schedule": {
            "rows": 2_280,
            "blocks": 212,
            "sha256": _schedule_identity_digest(
                "epl-shots-decision-schedule-1", decision_rows,
            ),
        },
    }


def _fixed_identity_snapshot(repo_root: Path | str) -> dict[str, Any]:
    """Recompute every preregistered input and historical-code identity."""
    root = Path(repo_root).resolve()
    data: dict[str, Any] = {}
    for name, digest in RAW_DIGESTS.items():
        relative = f"data/epl/raw/{name}"
        data[f"raw_{name}"] = _identity_record(
            root, relative, digest, label=relative,
        )
    data["matches"] = _identity_record(
        root, MATCHES_PATH, MATCHES_SHA256, label=MATCHES_PATH,
    )
    data["decision_corpus"] = _identity_record(
        root, DECISION_CORPUS_PATH, DECISION_CORPUS_SHA256,
        label=DECISION_CORPUS_PATH,
    )
    config = {
        name: _identity_record(root, path, digest, label=path)
        for name, (path, digest) in PINNED_CONFIG_IDENTITIES.items()
    }
    dependency = {
        name: _identity_record(root, path, digest, label=path)
        for name, (path, digest) in PINNED_DEPENDENCY_IDENTITIES.items()
    }

    resolved_parent = _git_text(root, "rev-parse", f"{NATIVE_PARENT_COMMIT}^{{commit}}")
    parent_tree = _git_text(root, "rev-parse", f"{NATIVE_PARENT_COMMIT}^{{tree}}")
    if resolved_parent != NATIVE_PARENT_COMMIT or parent_tree != NATIVE_PARENT_TREE:
        raise LockMismatch("the preregistered native parent commit/tree is unavailable")
    walk_blob = _git_bytes(root, "show", f"{NATIVE_PARENT_COMMIT}:epl/walkforward.py")
    fit_blob = _git_bytes(root, "show", f"{NATIVE_PARENT_COMMIT}:epl/fit.py")
    family_count, family_digest = _native_family_digest(root)
    if (hashlib.sha256(walk_blob).hexdigest() != NATIVE_WALKFORWARD_SHA256
            or hashlib.sha256(fit_blob).hexdigest() != NATIVE_FIT_SHA256
            or family_count != NATIVE_CODE_FAMILY_FILES
            or family_digest != NATIVE_CODE_FAMILY_SHA256):
        raise LockMismatch("historical native generator bytes differ from the preregistration")
    prereg_commit = _git_text(root, "rev-parse", f"{PREREG_COMMIT}^{{commit}}")
    prereg_blob = _git_bytes(root, "show", f"{PREREG_COMMIT}:{PREREG_PATH}")
    current_prereg = (root / PREREG_PATH).read_bytes()
    if prereg_commit != PREREG_COMMIT or prereg_blob != current_prereg:
        raise LockMismatch("the committed preregistration bytes are absent or edited")
    amendment_commit = _git_text(
        root, "rev-parse", f"{AMENDMENT_1_COMMIT}^{{commit}}",
    )
    amendment_blob = _git_bytes(
        root, "show", f"{AMENDMENT_1_COMMIT}:{AMENDMENT_1_PATH}",
    )
    current_amendment = (root / AMENDMENT_1_PATH).read_bytes()
    if (amendment_commit != AMENDMENT_1_COMMIT
            or hashlib.sha256(amendment_blob).hexdigest()
                != AMENDMENT_1_SHA256
            or amendment_blob != current_amendment):
        raise LockMismatch(
            "the committed Amendment 1 bytes are absent or edited"
        )
    amendment_2_commit = _git_text(
        root, "rev-parse", f"{AMENDMENT_2_COMMIT}^{{commit}}",
    )
    amendment_2_blob = _git_bytes(
        root, "show", f"{AMENDMENT_2_COMMIT}:{AMENDMENT_2_PATH}",
    )
    current_amendment_2 = (root / AMENDMENT_2_PATH).read_bytes()
    if (amendment_2_commit != AMENDMENT_2_COMMIT
            or hashlib.sha256(amendment_2_blob).hexdigest()
                != AMENDMENT_2_SHA256
            or amendment_2_blob != current_amendment_2):
        raise LockMismatch(
            "the committed Amendment 2 bytes are absent or edited"
        )
    native = {
        "parent_commit": NATIVE_PARENT_COMMIT,
        "parent_tree": NATIVE_PARENT_TREE,
        "walkforward_sha256": NATIVE_WALKFORWARD_SHA256,
        "fit_sha256": NATIVE_FIT_SHA256,
        "code_family_files": NATIVE_CODE_FAMILY_FILES,
        "code_family_sha256": NATIVE_CODE_FAMILY_SHA256,
        "seed": 20260611,
        "seed_override": None,
        "inference": "ADVI",
        "draws": 1000,
        "tune": 1000,
        "advi_iterations": 30000,
        "cadence": 1,
        "probability_round_decimals": 8,
        "native_stored_sum_tolerance": NATIVE_STORED_SUM_TOLERANCE,
        "model_probability_sum_tolerance": MODEL_PROBABILITY_SUM_TOLERANCE,
        "native_last_cell_repair": False,
        "optimizer_independent_gradient_tolerance": (
            OPTIMIZER_GRADIENT_TOLERANCE
        ),
        "optimizer_beta_distance_bound_l2": (
            OPTIMIZER_BETA_DISTANCE_BOUND_L2
        ),
        "prereg_commit": PREREG_COMMIT,
        "prereg_sha256": hashlib.sha256(prereg_blob).hexdigest(),
        "amendment_1_commit": AMENDMENT_1_COMMIT,
        "amendment_1_path": AMENDMENT_1_PATH,
        "amendment_1_sha256": AMENDMENT_1_SHA256,
        "amendment_2_commit": AMENDMENT_2_COMMIT,
        "amendment_2_path": AMENDMENT_2_PATH,
        "amendment_2_sha256": AMENDMENT_2_SHA256,
    }
    return {
        "data_identities": data,
        "config_identities": config,
        "dependency_identities": dependency,
        "runtime_dependency_closure": _runtime_dependency_closure(root),
        "native_runtime_lock": _native_runtime_lock_snapshot(),
        "native_contract": native,
        "resolved_packages": _resolved_packages(),
        "h_invariants": _fixed_h_invariants(root),
    }


def _expected_receipt_subject(manifest: Mapping[str, Any]) -> dict[str, Any]:
    """Bind receipts to the exact candidate, parent, contract, and runtime."""
    native = manifest.get("native_contract")
    prereg_sha256 = native.get("prereg_sha256") if isinstance(native, Mapping) else None
    fixed_contract = {
        key: manifest.get(key) for key in (
            "data_identities", "config_identities", "dependency_identities",
            "runtime_dependency_closure", "native_runtime_lock",
            "native_contract",
            "resolved_packages", "h_invariants", "output_schemas",
        )
    }
    environment = {
        key: manifest.get(key) for key in (
            "dependency_identities", "runtime_dependency_closure",
            "native_runtime_lock", "resolved_packages",
        )
    }
    return {
        "schema": H_RECEIPT_SUBJECT_SCHEMA,
        "prereg_commit": PREREG_COMMIT,
        "prereg_sha256": prereg_sha256,
        "amendment_1_commit": AMENDMENT_1_COMMIT,
        "amendment_1_sha256": AMENDMENT_1_SHA256,
        "amendment_2_commit": AMENDMENT_2_COMMIT,
        "amendment_2_sha256": AMENDMENT_2_SHA256,
        "freeze_parent_commit": manifest.get("freeze_parent_commit"),
        "freeze_parent_tree": manifest.get("freeze_parent_tree"),
        "candidate_files_sha256": _canonical_sha256(
            "epl-shots-h-files-1", manifest.get("files"),
        ),
        "fixed_contract_sha256": _canonical_sha256(
            "epl-shots-h-fixed-contract-1", fixed_contract,
        ),
        "test_plan_sha256": _canonical_sha256(
            "epl-shots-canary-test-plan-hash-1",
            _expected_canary_test_plan(),
        ),
        "environment_sha256": _canonical_sha256(
            "epl-shots-h-environment-1", environment,
        ),
    }


def _validate_receipt_subject(manifest: Mapping[str, Any]) -> str:
    subject = manifest.get("receipt_subject")
    recorded_sha256 = manifest.get("receipt_subject_sha256")
    if not isinstance(subject, Mapping):
        raise LockMismatch("receipt_subject must be a mapping")
    if not isinstance(recorded_sha256, str) or not _HEX64.fullmatch(recorded_sha256):
        raise LockMismatch("receipt_subject_sha256 is malformed")
    try:
        expected = _expected_receipt_subject(manifest)
        expected_sha256 = _canonical_sha256(
            H_RECEIPT_SUBJECT_SCHEMA, expected,
        )
    except (TypeError, ValueError) as exc:
        raise LockMismatch(f"receipt subject inputs are not strict JSON: {exc}") from exc
    if set(subject) != set(expected) or not _exact_json_value(subject, expected):
        raise LockMismatch("receipt_subject differs from the code-defined subject")
    if recorded_sha256 != expected_sha256:
        raise LockMismatch("receipt_subject_sha256 does not match receipt_subject")
    return expected_sha256


def _expected_canary_events() -> list[dict[str, str]]:
    plan = _expected_canary_test_plan()
    events: list[dict[str, str]] = []
    for canary in CANARY_NAMES:
        for case in plan["canaries"][canary]:
            events.append({
                "group": "canary", "canary": canary,
                "case_id": case["case_id"], "test_id": case["test_id"],
                "control": case["control"], "outcome": "passed",
            })
    for case in plan["real_validation"]:
        events.append({
            "group": "real_validation", "case_id": case["case_id"],
            "test_id": case["test_id"], "control": case["control"],
            "outcome": "passed",
        })
    return events


def _expected_canary_execution(manifest: Mapping[str, Any],
                               subject: Mapping[str, Any]) -> dict[str, Any]:
    packages = manifest.get("resolved_packages")
    python = packages.get("python") if isinstance(packages, Mapping) else None
    return {
        "argv": [
            ".venv/bin/python", "-m", "pytest", "epl/tests/test_shots.py",
            "-q", "-p", "no:cacheprovider",
        ],
        "cwd": ".",
        "environment": {
            "PYTHONPATH": "src:.", "PYTHONDONTWRITEBYTECODE": "1",
        },
        "python": python,
        "environment_sha256": subject.get("environment_sha256"),
        "exit_code": 0,
    }


def _validate_canary_receipt(receipt: Any, *, manifest: Mapping[str, Any],
                             subject_sha256: str) -> str:
    expected_fields = {
        "schema", "subject_sha256", "execution", "events", "counts",
        "real_validation", "semantic_result_sha256", "pass",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != expected_fields:
        raise CanaryFailed("canary_receipt has an inexact schema")
    subject = manifest.get("receipt_subject")
    events = _expected_canary_events()
    n_events = len(events)
    counts = {
        "expected": n_events, "collected": n_events, "passed": n_events,
        "failed": 0, "skipped": 0, "xfailed": 0, "xpassed": 0,
        "deselected": 0,
    }
    result = {
        "events": events, "counts": counts,
        "real_validation": manifest.get("h_invariants"),
    }
    expected_result_sha256 = _canonical_sha256(
        "epl-shots-canary-semantic-result-1", result,
    )
    checks = (
        receipt.get("schema") == H_CANARY_RECEIPT_SCHEMA,
        receipt.get("subject_sha256") == subject_sha256,
        isinstance(subject, Mapping),
        _exact_json_value(
            receipt.get("execution"),
            _expected_canary_execution(
                manifest, subject if isinstance(subject, Mapping) else {},
            ),
        ),
        _exact_json_value(receipt.get("events"), events),
        _exact_json_value(receipt.get("counts"), counts),
        _exact_json_value(
            receipt.get("real_validation"), manifest.get("h_invariants"),
        ),
        receipt.get("semantic_result_sha256") == expected_result_sha256,
        receipt.get("pass") is True,
    )
    if not all(checks):
        raise CanaryFailed(
            "canary_receipt must be an exact all-pass execution of the "
            "code-defined cases with no skip, xfail, xpass, or deselection"
        )
    return expected_result_sha256


def _expected_audit_scope() -> list[dict[str, Any]]:
    return [
        {"check": check, "pass": True} for check in (
            "date_comparisons", "accumulator_membership",
            "raw_column_allowlist", "quarantine_semantics",
            "train_score_separation", "comparator_isolation", "resampling",
            "decision_inequalities", "complete_diff", "write_set",
        )
    ]


def _expected_deliberate_failure_ids() -> list[dict[str, str]]:
    plan = _expected_canary_test_plan()
    return [
        {"case_id": f"{canary}:{case['case_id']}",
         "test_id": case["test_id"]}
        for canary in CANARY_NAMES
        for case in plan["canaries"][canary]
        if case["control"] == "positive"
    ]


def _validate_audit_receipt(receipt: Any, *, subject_sha256: str,
                            canary_result_sha256: str) -> None:
    expected_fields = {
        "schema", "subject_sha256", "canary_result_sha256", "reviewer",
        "scope", "deliberate_failures", "defects", "disposition", "pass",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != expected_fields:
        raise LockMismatch("audit_receipt has an inexact schema")
    reviewer = receipt.get("reviewer")
    if (not isinstance(reviewer, Mapping)
            or set(reviewer) != {"name", "identity"}
            or any(not isinstance(reviewer.get(key), str)
                   or not reviewer[key].strip()
                   or reviewer[key] != reviewer[key].strip()
                   for key in ("name", "identity"))):
        raise LockMismatch("audit_receipt reviewer identity is incomplete")
    failures = receipt.get("deliberate_failures")
    expected_failures = _expected_deliberate_failure_ids()
    if not isinstance(failures, list) or len(failures) != len(expected_failures):
        raise LockMismatch("audit_receipt deliberate-failure set is incomplete")
    for observed, expected in zip(failures, expected_failures, strict=True):
        if (not isinstance(observed, Mapping)
                or set(observed) != {
                    "case_id", "test_id", "expected", "observed", "pass",
                }
                or observed.get("case_id") != expected["case_id"]
                or observed.get("test_id") != expected["test_id"]
                or not isinstance(observed.get("expected"), str)
                or not observed["expected"].strip()
                or not isinstance(observed.get("observed"), str)
                or not observed["observed"].strip()
                or observed.get("pass") is not True):
            raise LockMismatch(
                "audit_receipt deliberate failures must exactly cover every "
                "positive control in plan order"
            )
    # Amendment 2 Rider 2: defects are a typed disclosure channel, not a free
    # field.  Every entry names a severity and trimmed non-empty text; a
    # blocking severity refuses the freeze, a non-blocking one rides in the
    # manifest as a permanent disclosed record.
    defects = receipt.get("defects")
    if (not isinstance(defects, list)
            or not _exact_json_value(defects, defects)
            or any(not isinstance(defect, Mapping)
                   or set(defect) != {"severity", "text"}
                   or defect.get("severity") not in AUDIT_DEFECT_SEVERITIES
                   or not isinstance(defect.get("text"), str)
                   or not defect["text"].strip()
                   or defect["text"] != defect["text"].strip()
                   for defect in defects)):
        raise LockMismatch(
            "audit_receipt defects must be typed severity/text disclosures"
        )
    if any(defect["severity"] == "blocking" for defect in defects):
        raise LockMismatch(
            "audit_receipt disclosed a blocking defect; the freeze is refused"
        )
    if (receipt.get("schema") != H_AUDIT_RECEIPT_SCHEMA
            or receipt.get("subject_sha256") != subject_sha256
            or receipt.get("canary_result_sha256") != canary_result_sha256
            or not _exact_json_value(receipt.get("scope"), _expected_audit_scope())
            or receipt.get("disposition") != "PASS"
            or receipt.get("pass") is not True):
        raise LockMismatch(
            "audit_receipt is not an exact clean audit bound to this canary run"
        )


def _validate_output_schemas(schemas: Mapping[str, Any]) -> None:
    if not isinstance(schemas, Mapping) or set(schemas) != set(H_OUTPUT_SCHEMA_KEYS):
        raise LockMismatch(
            f"output_schemas must contain exactly {list(H_OUTPUT_SCHEMA_KEYS)}"
        )
    try:
        matches = (_canonical_json(dict(schemas))
                   == _canonical_json(_expected_h_output_schemas()))
    except (TypeError, ValueError) as exc:
        raise LockMismatch(f"output_schemas are not strict JSON: {exc}") from exc
    if not matches:
        raise LockMismatch("output_schemas differ from the code-defined semantic contract")


def _validate_native_runtime_lock(value: Any) -> None:
    fields = {
        "schema", "sha256", "tree_digest_schema", "sealed_read_roots",
        "mutable_roots", "executables", "platform", "file_count",
        "directory_count", "symlink_count", "bytes",
    }
    if not isinstance(value, Mapping) or set(value) != fields:
        raise LockMismatch("native_runtime_lock has an inexact schema")
    payload = {key: value[key] for key in value if key != "sha256"}
    if (value.get("schema") != "epl-shots-native-runtime-lock-2"
            or value.get("tree_digest_schema") != "epl-shots-runtime-tree-1"
            or value.get("sha256")
                != hashlib.sha256(canonical_manifest_bytes(payload)).hexdigest()
            or value.get("sealed_read_roots") != []):
        raise LockMismatch("native_runtime_lock identity differs")
    roots = value.get("mutable_roots")
    executables = value.get("executables")
    platform = value.get("platform")
    if (not isinstance(roots, list) or not roots
            or not isinstance(executables, list) or not executables
            or not isinstance(platform, Mapping)
            or set(platform) != {
                "architecture", "kernel_release", "sw_vers", "root_mount",
                "sdk_logical_path", "sdk_resolved_path", "sdk_link_chain",
                "clang_version",
            }):
        raise LockMismatch("native_runtime_lock content is incomplete")
    link_fields = {"path", "target", "resolved"}
    root_fields = {
        "logical_path", "resolved_path", "link_chain", "tree_sha256",
        "files", "directories", "symlinks", "bytes",
    }
    executable_fields = {
        "logical_path", "resolved_path", "link_chain", "mode", "bytes",
        "sha256",
    }
    for label, records, expected in (
        ("root", roots, root_fields),
        ("executable", executables, executable_fields),
    ):
        for record in records:
            if (not isinstance(record, Mapping) or set(record) != expected
                    or not isinstance(record.get("logical_path"), str)
                    or not Path(record["logical_path"]).is_absolute()
                    or not isinstance(record.get("resolved_path"), str)
                    or not Path(record["resolved_path"]).is_absolute()
                    or not isinstance(record.get("link_chain"), list)
                    or any(not isinstance(link, Mapping)
                           or set(link) != link_fields
                           or any(not isinstance(link.get(key), str)
                                  for key in link_fields)
                           for link in record["link_chain"])):
                raise LockMismatch(f"native_runtime_lock {label} record differs")
            count_fields = (
                ("files", "directories", "symlinks", "bytes")
                if label == "root" else ("mode", "bytes")
            )
            if any(type(record.get(key)) is not int or record[key] < 0
                   for key in count_fields):
                raise LockMismatch(
                    f"native_runtime_lock {label} counts are malformed"
                )
            digest_key = "tree_sha256" if label == "root" else "sha256"
            if (not isinstance(record.get(digest_key), str)
                    or not _HEX64.fullmatch(record[digest_key])):
                raise LockMismatch(
                    f"native_runtime_lock {label} digest is malformed"
                )
    unique_roots = {
        record["resolved_path"]: record for record in roots
    }.values()
    expected_totals = {
        "file_count": sum(record["files"] for record in unique_roots),
        "directory_count": sum(
            record["directories"] for record in unique_roots
        ),
        "symlink_count": sum(record["symlinks"] for record in unique_roots),
        "bytes": sum(record["bytes"] for record in unique_roots),
    }
    if any(type(value.get(key)) is not int or value[key] != expected
           for key, expected in expected_totals.items()):
        raise LockMismatch("native_runtime_lock aggregate counts differ")
    if (any(not isinstance(platform.get(key), str) or not platform[key]
            for key in set(platform) - {"sdk_link_chain"})
            or not isinstance(platform.get("sdk_link_chain"), list)
            or any(not isinstance(link, Mapping) or set(link) != link_fields
                   for link in platform["sdk_link_chain"])):
        raise LockMismatch("native_runtime_lock platform receipt differs")


def make_harness_manifest(
    *,
    repo_root: Path | str,
    freeze_parent_commit: str,
    freeze_parent_tree: str,
    data_identities: Mapping[str, Any] | None = None,
    config_identities: Mapping[str, Any] | None = None,
    dependency_identities: Mapping[str, Any] | None = None,
    resolved_packages: Mapping[str, str] | None = None,
    canary_receipts: Mapping[str, Any],
    audit_receipt: Mapping[str, Any],
) -> dict[str, Any]:
    """Build the non-self-referential H payload from live audited identities.

    This function never writes or commits the manifest.  Caller-supplied
    identity mappings are compatibility assertions only: they must exactly
    equal the freshly recomputed contract and cannot replace live checks.
    """
    root = Path(repo_root).resolve()
    if (freeze_parent_commit != AMENDMENT_2_COMMIT
            or freeze_parent_tree != AMENDMENT_2_TREE):
        raise LockMismatch(
            "H freeze parent must be the exact Amendment 2 governance commit/tree"
        )
    resolved_parent = _git_text(
        root, "rev-parse", f"{freeze_parent_commit}^{{commit}}",
    )
    resolved_tree = _git_text(
        root, "rev-parse", f"{freeze_parent_commit}^{{tree}}",
    )
    if (resolved_parent != freeze_parent_commit
            or resolved_tree != freeze_parent_tree):
        raise LockMismatch("H freeze parent commit/tree is unavailable")
    if _git_text(root, "rev-parse", "HEAD^{commit}") != freeze_parent_commit:
        raise LockMismatch(
            "H preparation requires HEAD at the Amendment 2 governance commit"
        )
    forbidden = set(_git_text(
        root, "ls-tree", "-r", "--name-only", freeze_parent_commit, "--",
        *PRE_H_FORBIDDEN_PATHS,
    ).splitlines())
    if forbidden:
        raise LockMismatch(
            f"H freeze parent contains forbidden experiment outputs: {sorted(forbidden)}"
        )

    files: dict[str, Any] = {}
    for relative in H_REQUIRED_FILES:
        path = root / relative
        if path.is_symlink() or not path.is_file():
            raise LockMismatch(f"H candidate file is absent or not regular: {relative}")
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError) as exc:
            raise LockMismatch(f"H candidate file is not UTF-8: {relative}") from exc
        raw = text.encode("utf-8")
        if raw != path.read_bytes():
            raise LockMismatch(f"H candidate UTF-8 bytes changed: {relative}")
        files[relative] = {
            "sha256": hashlib.sha256(raw).hexdigest(),
            "bytes": len(raw), "lines": len(text.splitlines()),
        }

    fixed = _fixed_identity_snapshot(root)
    supplied = {
        "data_identities": data_identities,
        "config_identities": config_identities,
        "dependency_identities": dependency_identities,
        "resolved_packages": resolved_packages,
    }
    for key, value in supplied.items():
        if value is not None and not _exact_json_value(value, fixed[key]):
            raise LockMismatch(
                f"caller-supplied {key} differs from fresh live verification"
            )

    manifest: dict[str, Any] = {
        "schema": H_MANIFEST_SCHEMA,
        "harness_frozen": True,
        "freeze_parent_commit": freeze_parent_commit,
        "freeze_parent_tree": freeze_parent_tree,
        "files": files,
        **fixed,
        "output_schemas": _expected_h_output_schemas(),
    }
    subject = _expected_receipt_subject(manifest)
    subject_sha256 = _canonical_sha256(H_RECEIPT_SUBJECT_SCHEMA, subject)
    manifest.update({
        "receipt_subject": subject,
        "receipt_subject_sha256": subject_sha256,
        "canary_receipt": json.loads(json.dumps(canary_receipts)),
        "audit_receipt": json.loads(json.dumps(audit_receipt)),
    })
    canary_result_sha256 = _validate_canary_receipt(
        manifest["canary_receipt"], manifest=manifest,
        subject_sha256=subject_sha256,
    )
    _validate_audit_receipt(
        manifest["audit_receipt"], subject_sha256=subject_sha256,
        canary_result_sha256=canary_result_sha256,
    )
    # Pre-commit verification covers every field that does not require H's
    # future commit id.  A committed H must still pass require_harness_manifest.
    canonical_manifest_bytes(manifest)
    return manifest


def harness_manifest_status(
    manifest: Mapping[str, Any], *, repo_root: Path | str,
    harness_commit: str | None = None,
    rev: str = "HEAD",
    expected_parent_commit: str | None = None,
    expected_parent_tree: str | None = None,
) -> dict[str, Any]:
    """Verify H by listed bytes, never by asserting current ``HEAD == H``."""
    issues: list[str] = []
    root = Path(repo_root).resolve()
    expected_fields = {
        "schema", "harness_frozen", "freeze_parent_commit",
        "freeze_parent_tree", "files",
        "data_identities", "config_identities", "dependency_identities",
        "runtime_dependency_closure", "native_runtime_lock",
        "native_contract", "resolved_packages",
        "h_invariants", "output_schemas", "receipt_subject",
        "receipt_subject_sha256", "canary_receipt", "audit_receipt",
    }
    unknown_fields = sorted(set(manifest) - expected_fields)
    missing_fields = sorted(expected_fields - set(manifest))
    if unknown_fields:
        issues.append(f"unknown top-level fields present: {unknown_fields}")
    if missing_fields:
        issues.append(f"required top-level fields absent: {missing_fields}")
    forbidden = {"harness_freeze_commit", "freeze_commit", "head_commit",
                 "manifest_sha256", "self_sha256"}
    present_forbidden = sorted(forbidden & set(manifest))
    if present_forbidden:
        issues.append(f"self-referential/top-of-tree fields present: {present_forbidden}")
    if manifest.get("schema") != H_MANIFEST_SCHEMA:
        issues.append(f"schema is {manifest.get('schema')!r}, expected {H_MANIFEST_SCHEMA!r}")
    if manifest.get("harness_frozen") is not True:
        issues.append("harness_frozen is not true")
    parent = str(manifest.get("freeze_parent_commit", ""))
    tree = str(manifest.get("freeze_parent_tree", ""))
    if not _HEX40.fullmatch(parent):
        issues.append("freeze_parent_commit is not a 40-char lowercase git id")
    if not _HEX40.fullmatch(tree):
        issues.append("freeze_parent_tree is not a 40-char lowercase git id")
    if parent != AMENDMENT_2_COMMIT:
        issues.append("freeze_parent_commit is not the Amendment 2 governance commit")
    if tree != AMENDMENT_2_TREE:
        issues.append("freeze_parent_tree is not the Amendment 2 governance tree")
    if expected_parent_commit is not None and parent != expected_parent_commit:
        issues.append("freeze_parent_commit differs from the expected parent")
    if expected_parent_tree is not None and tree != expected_parent_tree:
        issues.append("freeze_parent_tree differs from the expected parent tree")

    file_records = manifest.get("files")
    if not isinstance(file_records, Mapping):
        issues.append("files is not a mapping")
        file_records = {}
    if set(file_records) != set(H_REQUIRED_FILES):
        issues.append(
            f"locked file set differs: expected={sorted(H_REQUIRED_FILES)}, "
            f"observed={sorted(file_records)}"
        )
    checked: dict[str, dict[str, Any]] = {}
    for relative, record in file_records.items():
        relative = str(relative)
        if not _safe_relative(relative) or relative == H_MANIFEST_PATH:
            issues.append(f"unsafe or self-referential locked path {relative!r}")
            continue
        path = (root / relative).resolve()
        try:
            path.relative_to(root)
        except ValueError:
            issues.append(f"locked path escapes repo root: {relative}")
            continue
        if not isinstance(record, Mapping) or set(record) != {
            "sha256", "bytes", "lines",
        }:
            issues.append(f"{relative}: file record has an inexact schema")
            continue
        if (type(record.get("bytes")) is not int
                or type(record.get("lines")) is not int):
            issues.append(f"{relative}: byte and line counts must be exact integers")
            continue
        recorded = record.get("sha256")
        if not isinstance(recorded, str) or not _HEX64.fullmatch(recorded):
            issues.append(f"{relative}: recorded sha256 is malformed")
            continue
        actual = sha256_file(path) if path.is_file() else None
        match = actual == recorded
        checked[relative] = {"recorded": recorded, "actual": actual,
                             "match": match}
        if not match:
            issues.append(f"{relative}: bytes differ from manifest")
        else:
            if record.get("bytes") != path.stat().st_size:
                issues.append(f"{relative}: byte count differs from manifest")
            try:
                actual_lines = len(path.read_text().splitlines())
            except UnicodeDecodeError:
                actual_lines = None
            if record.get("lines") != actual_lines:
                issues.append(f"{relative}: line count differs from manifest")

    try:
        _validate_native_runtime_lock(manifest.get("native_runtime_lock"))
    except LockMismatch as exc:
        issues.append(str(exc))
    try:
        fixed = _fixed_identity_snapshot(root)
    except ShotsError as exc:
        fixed = {}
        issues.append(f"fixed identity recomputation failed: {exc}")
    for key in (
        "data_identities", "config_identities", "dependency_identities",
        "runtime_dependency_closure", "native_runtime_lock",
        "native_contract", "resolved_packages",
        "h_invariants",
    ):
        if fixed and not _exact_json_value(manifest.get(key), fixed[key]):
            issues.append(f"{key} differs from the recomputed preregistered contract")
    try:
        _validate_output_schemas(manifest.get("output_schemas", {}))
    except LockMismatch as exc:
        issues.append(str(exc))
    subject_sha256 = ""
    try:
        subject_sha256 = _validate_receipt_subject(manifest)
    except LockMismatch as exc:
        issues.append(str(exc))
    canary_result_sha256 = ""
    try:
        canary_result_sha256 = _validate_canary_receipt(
            manifest.get("canary_receipt"), manifest=manifest,
            subject_sha256=subject_sha256,
        )
    except (CanaryFailed, TypeError, ValueError) as exc:
        issues.append(str(exc))
    try:
        _validate_audit_receipt(
            manifest.get("audit_receipt"),
            subject_sha256=subject_sha256,
            canary_result_sha256=canary_result_sha256,
        )
    except LockMismatch as exc:
        issues.append(str(exc))
    try:
        manifest_bytes = canonical_manifest_bytes(manifest)
    except (TypeError, ValueError) as exc:
        manifest_bytes = b""
        issues.append(f"manifest is not strict canonical JSON: {exc}")
    manifest_sha256 = (
        hashlib.sha256(manifest_bytes).hexdigest() if manifest_bytes else ""
    )
    resolved_h = ""
    if harness_commit is None or not _HEX40.fullmatch(str(harness_commit)):
        issues.append("an external 40-char harness commit H is required")
    else:
        try:
            resolved_h = _git_text(root, "rev-parse", f"{harness_commit}^{{commit}}")
            if resolved_h != str(harness_commit):
                issues.append("harness commit does not resolve exactly")
            parent_line = _git_text(root, "rev-list", "--parents", "-n", "1", resolved_h)
            parents = parent_line.split()[1:]
            if parents != [parent]:
                issues.append(
                    f"H parent set is {parents}, expected exactly [{parent}]"
                )
            actual_parent_tree = _git_text(root, "rev-parse", f"{parent}^{{tree}}")
            if actual_parent_tree != tree:
                issues.append("H's parent tree differs from freeze_parent_tree")
            pre_h_outputs = set(_git_text(
                root, "ls-tree", "-r", "--name-only", parent, "--",
                *PRE_H_FORBIDDEN_PATHS,
            ).splitlines())
            if pre_h_outputs:
                issues.append(
                    "freeze parent already contains forbidden shots outputs: "
                    f"{sorted(pre_h_outputs)}"
                )
            ancestor = subprocess.run(
                (_GIT_EXECUTABLE, "-C", str(root), "merge-base", "--is-ancestor",
                 resolved_h, rev), capture_output=True, check=False, timeout=30,
                env=dict(_GIT_ENVIRONMENT),
            )
            if ancestor.returncode != 0:
                issues.append(f"H is not an ancestor of {rev}")
            changed = set(_git_text(
                root, "diff-tree", "--no-commit-id", "--name-only", "-r",
                resolved_h,
            ).splitlines())
            expected_changed = set(H_REQUIRED_FILES) | {H_MANIFEST_PATH}
            if changed != expected_changed:
                issues.append(
                    f"H changed paths differ: expected={sorted(expected_changed)}, "
                    f"observed={sorted(changed)}"
                )
            added = set(_git_text(
                root, "diff-tree", "--no-commit-id", "--name-only",
                "--diff-filter=A", "-r", resolved_h,
            ).splitlines())
            if added != expected_changed:
                issues.append(
                    "H must add every freeze path from an artifact-free parent: "
                    f"expected={sorted(expected_changed)}, observed={sorted(added)}"
                )
            try:
                _require_git_regular_blobs(
                    root, resolved_h, tuple(expected_changed), label="H",
                )
            except LockMismatch as exc:
                issues.append(str(exc))
            committed_manifest = _git_bytes(
                root, "show", f"{resolved_h}:{H_MANIFEST_PATH}",
            )
            if manifest_bytes and committed_manifest != manifest_bytes:
                issues.append("manifest mapping differs from the bytes committed at H")
            current_manifest_path = root / H_MANIFEST_PATH
            if (manifest_bytes and (not current_manifest_path.is_file()
                    or current_manifest_path.read_bytes() != manifest_bytes)):
                issues.append("working-tree harness manifest differs from H")
            for relative, record in file_records.items():
                if not isinstance(record, Mapping):
                    continue
                committed = _git_bytes(root, "show", f"{resolved_h}:{relative}")
                if hashlib.sha256(committed).hexdigest() != record.get("sha256"):
                    issues.append(f"{relative}: committed H bytes differ from manifest")
        except (OSError, ShotsError, subprocess.SubprocessError) as exc:
            issues.append(f"H commit binding failed: {exc}")
    return {
        "frozen": not issues, "schema": H_MANIFEST_SCHEMA,
        "harness_commit": resolved_h,
        "freeze_parent_commit": parent, "freeze_parent_tree": tree,
        "files": checked, "issues": tuple(issues),
        "manifest_payload_sha256": manifest_sha256,
    }


def require_harness_manifest(manifest: Mapping[str, Any], *,
                             repo_root: Path | str,
                             harness_commit: str,
                             rev: str = "HEAD",
                             expected_parent_commit: str | None = None,
                             expected_parent_tree: str | None = None,
                             ) -> dict[str, Any]:
    status = harness_manifest_status(
        manifest, repo_root=repo_root, harness_commit=harness_commit, rev=rev,
        expected_parent_commit=expected_parent_commit,
        expected_parent_tree=expected_parent_tree,
    )
    if not status["frozen"]:
        raise LockMismatch("; ".join(status["issues"]))
    return status


def _ordered_id_sha256(values: Sequence[Any]) -> str:
    digest = hashlib.sha256()
    for value in _ids(values, label="manifest fixture ids"):
        blob = value.encode("utf-8")
        digest.update(len(blob).to_bytes(8, "big")); digest.update(blob)
    return digest.hexdigest()
