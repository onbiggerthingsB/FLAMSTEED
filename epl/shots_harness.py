"""Fail-closed production boundary for the preregistered shots/SOT arm.

The training and decision transactions are implemented, but neither this
module nor a green test run grants execution authority.  Real training still
requires a separately authorized, exact live H; decision work requires its
direct-child K as well.  Every effectful entry point re-verifies those immutable
identities and preserves the preregistered refusal and crash-resume boundaries.
"""

from __future__ import annotations

import argparse
import concurrent.futures
import contextlib
import csv
import fcntl
import hashlib
import io
import json
import math
import os
import re
import resource
import selectors
import shutil
import signal
import stat
import subprocess
import sys
import tarfile
import tempfile
import time
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path, PurePosixPath
from types import MappingProxyType
from typing import Any, Iterator, Mapping, NoReturn, Sequence

import numpy as np
import pandas as pd

from epl import paths, shots

__all__ = [
    "BUILD_STATES", "H_READY", "NonPublishingRunStop",
    "ResumableRunInterruption", "ManualReconciliationRequired",
    "RunnerNotReady", "LifecycleStatus",
    "decision_schedule_binding", "inspect_state", "verify_harness_live",
    "verify_coefficient_freeze_live", "run_training", "run_decision",
    "main",
]

# Amendment 2 Rider 2: the build-state reading is derived from the live gates
# by ``inspect_state``; the retired ``BUILD_STATE`` constant was stale inside
# frozen bytes.  ``BUILD_STATES`` enumerates the only readings a live
# inspection can produce.
BUILD_STATES = shots.BUILD_STATES
H_READY = True
TRAINING_WORKER_READY = True
DECISION_WORKER_READY = True

# Capability flags describe the code present in the H candidate, never run
# authorization.  A live frozen H/K and the owner's separate lifecycle approval
# remain mandatory at the public entry points.
_NATIVE_TRAINING_BLOCK_WORKER_READY = True

_ROOT = paths.REPO_ROOT.resolve()
_H_PATH = _ROOT / shots.H_MANIFEST_PATH
_K_PATH = _ROOT / shots.K_MANIFEST_PATH
_ARTIFACT_ROOT = (_ROOT / shots.SHOTS_ARTIFACT_ROOT).resolve()
_HEX40 = re.compile(r"^[0-9a-f]{40}$")
_HEX64 = re.compile(r"^[0-9a-f]{64}$")
_GIT_EXECUTABLE = Path("/usr/bin/git")

# K v2 is local to this still-unfrozen runner.  It deliberately does not reuse
# the much shallower v1 artifact contract in ``shots.py``.  The H candidate
# must eventually freeze these bytes and the matching tests before any one-shot
# fit can be authorized.  Until then every public effect remains disabled.
_K2_MANIFEST_SCHEMA = "epl-shots-coefficient-manifest-2"
_K2_SCHEDULE_SCHEMA = "epl-shots-training-schedule-1"
_K2_BLOCK_SET_SCHEMA = "epl-shots-native-block-set-1"
_K2_OUTCOME_SCHEMA = "epl-shots-training-outcomes-1"
_K2_OBJECTIVE = "sum_i(-log(q_i[y_i]))+0.5*sum(beta**2)"
_K2_COEFFICIENT_ORDER = tuple(
    f"beta_{outcome}.{feature}"
    for outcome in ("H", "D") for feature in shots.FEATURE_NAMES
)
_K2_SCHEDULE_FIELDS = (
    "ordinal", "match_id", "season", "date", "home_key", "away_key",
    "block", "cutoff",
)
_DECISION_ROWS = 2_280
_DECISION_BLOCKS = 212
_DECISION_SEASONS = (
    "2019/20", "2020/21", "2021/22", "2022/23", "2023/24", "2024/25",
)
_DECISION_RUN_STATE_SCHEMA = "epl-shots-decision-run-state-1"
_DECISION_RUN_LOCK_SCHEMA = "epl-shots-decision-run-lock-1"
_DECISION_PREDICTION_INTENT_SCHEMA = (
    "epl-shots-decision-prediction-intent-1"
)
_DECISION_PREDICTION_BLOCK_SCHEMA = (
    "epl-shots-decision-prediction-block-1"
)
_DECISION_PREDICTION_PROJECTION_SCHEMA = (
    "epl-shots-decision-prediction-projection-1"
)
_DECISION_PREDICTION_BLOCK_SET_SCHEMA = (
    "epl-shots-decision-prediction-block-set-1"
)
_PREDICTION_ACCESS_RECEIPT_SCHEMA = (
    "epl-shots-prediction-access-receipt-1"
)
_DECISION_PREDICTIONS_SCHEMA = "epl-shots-decision-predictions-1"
_PREDICTION_SEAL_SCHEMA = "epl-shots-prediction-seal-1"
_SCORING_ACCESS_INTENT_SCHEMA = "epl-shots-scoring-access-intent-1"
_SCORING_ACCESS_RECEIPT_SCHEMA = "epl-shots-scoring-access-receipt-1"
_DECISION_SCORING_PROJECTION_SCHEMA = (
    "epl-shots-decision-scoring-projection-1"
)
_DECISION_SCORES_SCHEMA = "epl-shots-decision-scores-1"
_DECISION_CANARY_RECEIPT_SCHEMA = "epl-shots-decision-canary-receipt-1"
_DECISION_RESULT_SCHEMA = "epl-shots-decision-result-2"
_DECISION_EVIDENCE_SCHEMA = "epl-shots-result-evidence-manifest-1"
_DECISION_REPORT_SCHEMA = "epl-shots-result-report-1"
_RESULT_EVIDENCE_PATH = (
    _ROOT / "reports/evidence/epl_shots/result_evidence_manifest.json"
)
_RESULT_REPORT_PATH = _ROOT / "reports/epl_shots_result.md"
_PREDICTION_COLUMNS = (
    "match_id", "season", "date", "home_key", "away_key", "block",
    "dc_home", "dc_draw", "dc_away",
)
_SCORING_COLUMNS = (
    "match_id", "season", "block", "y",
    "market_home", "market_draw", "market_away", "dc_rps", "market_rps",
)


def _k2_schemas() -> dict[str, str]:
    """Return fresh K2 identities; mutable module state is not authority."""
    return {
        "native_block": _NATIVE_BLOCK_SCHEMA,
        "native_intent": _NATIVE_INTENT_SCHEMA,
        "native_completion": _NATIVE_COMPLETION_SCHEMA,
        "native_refusal": _NATIVE_REFUSAL_RECEIPT_SCHEMA,
        "training_predictions": "epl-shots-training-predictions-2",
        "feature_moments": "epl-shots-feature-moments-2",
        "coefficients": "epl-shots-coefficients-2",
        "optimizer_intent": "epl-shots-optimizer-intent-1",
        "optimizer_receipt": "epl-shots-optimizer-receipt-3",
        "decision_prediction_intent": _DECISION_PREDICTION_INTENT_SCHEMA,
        "decision_prediction_block": _DECISION_PREDICTION_BLOCK_SCHEMA,
        "prediction_access_receipt": _PREDICTION_ACCESS_RECEIPT_SCHEMA,
        "decision_predictions": _DECISION_PREDICTIONS_SCHEMA,
        "prediction_seal": _PREDICTION_SEAL_SCHEMA,
        "scoring_access_intent": _SCORING_ACCESS_INTENT_SCHEMA,
        "scoring_access_receipt": _SCORING_ACCESS_RECEIPT_SCHEMA,
        "decision_scores": _DECISION_SCORES_SCHEMA,
        "decision_canary_receipt": _DECISION_CANARY_RECEIPT_SCHEMA,
        "decision_result": _DECISION_RESULT_SCHEMA,
    }

_NATIVE_INPUT_SCHEMA = "epl-shots-native-training-request-2"
_NATIVE_INTENT_SCHEMA = "epl-shots-native-training-intent-1"
_NATIVE_BLOCK_IDENTITY_SCHEMA = "epl-shots-native-block-identity-1"
_NATIVE_BLOCK_SCHEMA = "epl-shots-native-training-block-2"
_NATIVE_SEMANTIC_REFUSAL_SCHEMA = "epl-shots-native-semantic-refusal-1"
_NATIVE_REFUSAL_RECEIPT_SCHEMA = "epl-shots-native-refusal-receipt-2"
_NATIVE_REFUSAL_EXECUTION_SCHEMA = "epl-shots-native-refusal-execution-1"
_NATIVE_RUNTIME_MISMATCH_MESSAGE = (
    "native runtime/toolchain closure changed after worker launch"
)
_NATIVE_COMPLETION_SCHEMA = "epl-shots-native-job-completion-3"
_NATIVE_SANDBOX_SCHEMA = "epl-shots-native-sandbox-contract-3"
_NATIVE_SANDBOX_RUN_SCHEMA = "epl-shots-native-sandbox-run-3"
_NATIVE_SANDBOX_EXECUTABLE = Path("/usr/bin/sandbox-exec")
_NATIVE_RSS_MONITOR_EXECUTABLE = Path("/bin/ps")
_NATIVE_TEMP_PARENT = Path("/private/tmp")
_NATIVE_TOTAL_TIMEOUT_SECONDS = 12 * 60 * 60
_NATIVE_INACTIVITY_TIMEOUT_SECONDS = 20 * 60
_NATIVE_MAX_LINE_BYTES = 1_048_576
_NATIVE_MAX_OUTPUT_BYTES = 64 * 1_048_576
_NATIVE_WORKER_FLAGS = ("-S", "-s", "-P", "-B")
_NATIVE_CPU_LIMIT_SECONDS = 12 * 60 * 60
_NATIVE_FILE_LIMIT_BYTES = 128 * 1_048_576
_NATIVE_RSS_LIMIT_BYTES = 32 * 1_073_741_824
_NATIVE_RSS_POLL_SECONDS = 0.5
_NATIVE_NOFILE_LIMIT = 256
_NATIVE_PATH_RESOLUTION_LITERALS = ("/",)
_NATIVE_RUNTIME_CLOSURE_SCHEMA = "epl-shots-native-runtime-lock-2"
_NATIVE_RUNTIME_TREE_SCHEMA = "epl-shots-runtime-tree-1"
_NATIVE_RUNTIME_OUTPUT_TREE_SCHEMA = "epl-shots-generated-runtime-tree-1"
# No broad macOS system subtree is exposed to the worker.  Even a sealed
# directory can contain a logical symlink into a mutable or unrelated tree
# (for example ``/System/Library/User Template -> /Library/User Template``).
# Exact system executables/loadable images are allowlisted and hashed below.
_NATIVE_SEALED_READ_ROOTS: tuple[str, ...] = ()
_NATIVE_DEVELOPER_ROOT = Path("/Library/Developer/CommandLineTools")
_NATIVE_SYSTEM_LOADABLES = (
    Path("/usr/lib/libffi-trampolines.dylib"),
    Path("/usr/lib/libobjc-trampolines.dylib"),
)
_NATIVE_RUNTIME_MAX_BYTES = 4 * 1_073_741_824
_NATIVE_RUNTIME_MAX_FILES = 100_000
_NATIVE_RUNTIME_MAX_DIRECTORIES = 25_000
_NATIVE_RUNTIME_MAX_ENTRIES = 125_000
_NATIVE_PARENT_COMMIT = "6450fb51aef22021a00b3eed72395f1c4141cae3"
_NATIVE_PARENT_TREE = "3bfe865d7b441d03b55d356857cd58a89d589fea"
_NATIVE_WALKFORWARD_SHA256 = (
    "c68f316f4f3d74881de1312aafd42ae08b5963bfc43ec5065baab4250c5c8710"
)
_NATIVE_FIT_SHA256 = (
    "ab471e96b8321359a0998d6ca7a03496b91b484582ef081f0d43462db6ed1ce6"
)
_NATIVE_CODE_FAMILY_FILES = 157
_NATIVE_CODE_FAMILY_SHA256 = (
    "d388375d3158c122c2fd92c05a670329da7f96957c3814f02937f1c85f6433b0"
)
_NATIVE_RAW_CODES = ("1415", "1516", "1617", "1718", "1819")
_NATIVE_RAW_NAMES = tuple(f"E0_{code}.csv" for code in _NATIVE_RAW_CODES)
_NATIVE_ARCHIVE_RESOURCES = (
    "epl/config_frozen.json",
    "config/config.yaml",
    "pyproject.toml",
    "uv.lock",
    "src/wcmodel/data/ref/confederations.csv",
)


def _native_raw_digests() -> dict[str, str]:
    """Fresh literal pins; mutable module dictionaries are not authority."""
    return {
        "E0_1415.csv": "76b7858051ff6b17f46f49f26fdc70c1f29537270492606f5cc63d67fad5d149",
        "E0_1516.csv": "bd3502a18c38a1597fd9af62e2366b4015006d3528dd4d18b311bd6237bbc085",
        "E0_1617.csv": "9625a7652b5f98fbd3e2e4d378c851fc246693f3343e34a72428d5b6e864d3e0",
        "E0_1718.csv": "4f3389365ef3f7ac966764ed8ba67cf3b79f5aebed18dd224099c4b2c98bc67b",
        "E0_1819.csv": "7c096b3c2ecd54c6993d22eeea73450c2bde11e3457238b226b8f43c62dfc35e",
    }


# Executed with an allowlisted environment plus ``-S -s -P -B`` in the extracted
# parent tree.  ``-I``/``-E`` are intentionally not used because they discard
# the required ``PYTHONHASHSEED`` determinism pin.  The sandbox, ``-P``, and the
# explicit attested site-packages path, and absence of PYTHONPATH/HOME provide
# the import isolation boundary instead.  This is part
# of the H-hashed runner file: it is not assembled from a caller-supplied script
# or imported from the mutable checkout.  Its only non-code inputs are the
# outcome-free request and the five raw files installed by the parent process.
_NATIVE_WORKER_SOURCE = r'''
from __future__ import annotations

import contextlib
import hashlib
import io
import json
import math
import os
import sys
from pathlib import Path

PARENT_COMMIT = "6450fb51aef22021a00b3eed72395f1c4141cae3"
PARENT_TREE = "3bfe865d7b441d03b55d356857cd58a89d589fea"
REQUEST_SCHEMA = "epl-shots-native-training-request-2"
INTENT_SCHEMA = "epl-shots-native-training-intent-1"
BLOCK_IDENTITY_SCHEMA = "epl-shots-native-block-identity-1"
BLOCK_SCHEMA = "epl-shots-native-training-block-2"
SEMANTIC_REFUSAL_SCHEMA = "epl-shots-native-semantic-refusal-1"
RAW_CODES = ("1415", "1516", "1617", "1718", "1819")
RAW_NAMES = tuple(f"E0_{code}.csv" for code in RAW_CODES)
TRAINING_SEASONS = ("2015/16", "2016/17", "2017/18", "2018/19")
ALL_SEASONS = ("2014/15", *TRAINING_SEASONS)
INPUT_COLUMNS = (
    "match_id", "season", "date", "kickoff", "home_key", "away_key",
    "fthg", "ftag", "ftr", "played",
)


def canonical(value):
    return (json.dumps(
        value, sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode("ascii")


class NativeSemanticRefusal(RuntimeError):
    pass


class NativeSemanticDomainEnvelope:
    """Immutable provenance carried by a post-bind semantic refusal."""

    __slots__ = ("_values",)

    def __init__(self, intent, native_intent_sha256, request_raw):
        object.__setattr__(self, "_values", (
            native_intent_sha256,
            hashlib.sha256(request_raw).hexdigest(),
            intent["harness_commit"],
            intent["harness_manifest_sha256"],
            intent["training_schedule_sha256"],
        ))

    def __setattr__(self, name, value):
        raise AttributeError("native semantic domain envelope is immutable")

    @property
    def native_intent_sha256(self):
        return self._values[0]

    @property
    def job_request_sha256(self):
        return self._values[1]

    @property
    def harness_commit(self):
        return self._values[2]

    @property
    def harness_manifest_sha256(self):
        return self._values[3]

    @property
    def training_schedule_sha256(self):
        return self._values[4]


semantic_domain_envelope = None

SEMANTIC_DOMAIN_EXCEPTION_TYPES = (
    AssertionError, ArithmeticError, AttributeError, LookupError, NameError,
    NotImplementedError, TypeError, ValueError,
)
SEMANTIC_DOMAIN_MODULES = (
    "arviz", "epl", "numpy", "pandas", "pyarrow", "pymc", "pytensor",
    "scipy", "wcmodel", "xarray",
)
INFRASTRUCTURE_EXCEPTION_TYPES = (
    ImportError, MemoryError, OSError, RecursionError,
)
INFRASTRUCTURE_EXCEPTION_MODULES = (
    "_frozen_importlib", "_thread", "asyncio", "concurrent.futures",
    "importlib", "multiprocessing", "pymc.sampling.parallel", "queue",
    "selectors", "socket", "subprocess", "threading",
    # A Pytensor C-linker exception reports a compiler/tool process failure,
    # not a scientific fit verdict, even though it lives below pytensor.
    "pytensor.link.c",
)


def module_matches(module_name, prefixes):
    return isinstance(module_name, str) and any(
        module_name == prefix or module_name.startswith(prefix + ".")
        for prefix in prefixes
    )


def exception_graph(root_exception):
    """Return causes, contexts, and grouped leaves without trusting acyclicity."""
    pending = [root_exception]
    seen = set()
    output = []
    while pending:
        current = pending.pop()
        marker = id(current)
        if marker in seen:
            continue
        seen.add(marker)
        output.append(current)
        cause = getattr(current, "__cause__", None)
        context = getattr(current, "__context__", None)
        if isinstance(cause, BaseException):
            pending.append(cause)
        if isinstance(context, BaseException):
            pending.append(context)
        grouped = getattr(current, "exceptions", ())
        if isinstance(grouped, tuple):
            pending.extend(
                item for item in grouped if isinstance(item, BaseException)
            )
    return tuple(output)


def traceback_origin(traceback):
    module_name = None
    cursor = traceback
    while cursor is not None:
        candidate = cursor.tb_frame.f_globals.get("__name__")
        if isinstance(candidate, str):
            module_name = candidate
        cursor = cursor.tb_next
    return module_name


def semantic_domain_failure(exc, traceback):
    """Classify only deterministic post-bind data/model/spec exceptions."""
    graph = exception_graph(exc)
    if not graph or any(not isinstance(item, Exception) for item in graph):
        # KeyboardInterrupt, SystemExit, GeneratorExit, and cancellation-like
        # BaseExceptions remain process interruptions.
        return False
    if any(isinstance(item, INFRASTRUCTURE_EXCEPTION_TYPES)
           for item in graph):
        return False
    for item in graph:
        if module_matches(
            type(item).__module__, INFRASTRUCTURE_EXCEPTION_MODULES,
        ):
            return False
        if module_matches(
            traceback_origin(item.__traceback__),
            INFRASTRUCTURE_EXCEPTION_MODULES,
        ):
            return False
    if isinstance(exc, NativeSemanticRefusal):
        return True
    if isinstance(exc, SEMANTIC_DOMAIN_EXCEPTION_TYPES):
        return True
    return (
        module_matches(type(exc).__module__, SEMANTIC_DOMAIN_MODULES)
        or module_matches(traceback_origin(traceback), SEMANTIC_DOMAIN_MODULES)
    )


def semantic_excepthook(exc_type, exc, traceback):
    envelope = globals().get("semantic_domain_envelope")
    explicit_refusal = isinstance(exc, NativeSemanticRefusal)
    if (not isinstance(envelope, NativeSemanticDomainEnvelope)
            or not semantic_domain_failure(exc, traceback)):
        sys.__excepthook__(exc_type, exc, traceback)
        return
    message = "".join(
        character if ord(character) >= 32 else " " for character in str(exc)
    )
    message = " ".join(message.split()) or exc_type.__name__
    payload = {
        "schema": SEMANTIC_REFUSAL_SCHEMA,
        "native_intent_sha256": envelope.native_intent_sha256,
        "job_request_sha256": envelope.job_request_sha256,
        "harness_commit": envelope.harness_commit,
        "harness_manifest_sha256": envelope.harness_manifest_sha256,
        "training_schedule_sha256": envelope.training_schedule_sha256,
        "refusal_kind": (
            "NativeSemanticRefusal" if explicit_refusal else "NativeFitFailure"
        ),
        "exception_type": f"{exc_type.__module__}.{exc_type.__name__}",
        "message": message[:4096],
    }
    try:
        sys.stdout.buffer.write(canonical(payload))
        sys.stdout.buffer.flush()
    except Exception:
        sys.__excepthook__(exc_type, exc, traceback)


sys.excepthook = semantic_excepthook


def refuse(condition, message):
    if condition:
        raise NativeSemanticRefusal(message)


root = Path(os.environ.pop("EPL_SHOTS_PARENT_ROOT")).resolve()
request_path = Path(os.environ.pop("EPL_SHOTS_REQUEST")).resolve()
runtime_root = Path(os.environ.pop("EPL_SHOTS_RUNTIME_ROOT")).resolve()
site_packages = Path(os.environ.pop("EPL_SHOTS_SITE_PACKAGES")).resolve()
python_abi = os.environ.pop("EPL_SHOTS_PYTHON_ABI")
if python_abi != f"{sys.version_info.major}.{sys.version_info.minor}":
    raise RuntimeError("native worker Python ABI differs from its contract")
sys.dont_write_bytecode = True
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root))
sys.path.append(str(site_packages))

import numpy as np
import pandas as pd

from epl import anchor as anchor_mod
from epl import fit as fit_mod
from epl import freeze, parse, schema, walkforward
from epl import paths as paths_mod

feature_cache_root = runtime_root / "feature_cache"
feature_cache_root.mkdir(parents=True, exist_ok=False)
paths_mod.FIT_CACHE_DIR = feature_cache_root

modules = {
    "epl.anchor": anchor_mod,
    "epl.fit": fit_mod,
    "epl.freeze": freeze,
    "epl.paths": paths_mod,
    "epl.parse": parse,
    "epl.schema": schema,
    "epl.walkforward": walkforward,
}
module_paths = {}
for name, module in modules.items():
    module_path = Path(module.__file__).resolve()
    try:
        relative = module_path.relative_to(root).as_posix()
    except ValueError as exc:
        raise RuntimeError(f"{name} imported outside parent archive: {module_path}") from exc
    module_paths[name] = relative

request_raw = request_path.read_bytes()
request = json.loads(request_raw.decode("ascii"))
refuse(not isinstance(request, dict) or canonical(request) != request_raw,
       "native request is not one canonical ASCII JSON object")
refuse(set(request) != {
    "schema", "native_intent", "native_intent_sha256", "block_ordinals",
}, "native request fields differ")
intent = request["native_intent"]
refuse(not isinstance(intent, dict) or set(intent) != {
    "schema", "harness_commit", "harness_manifest_sha256", "parent_commit",
    "parent_tree", "training_schedule_sha256", "raw_inputs", "schedule",
    "sandbox_contract_sha256",
}, "native intent fields differ")
native_intent_sha256 = hashlib.sha256(canonical(intent)).hexdigest()
refuse(request["schema"] != REQUEST_SCHEMA
       or intent["schema"] != INTENT_SCHEMA
       or intent["parent_commit"] != PARENT_COMMIT
       or intent["parent_tree"] != PARENT_TREE
       or request["native_intent_sha256"] != native_intent_sha256
       or not isinstance(intent["harness_commit"], str)
       or len(intent["harness_commit"]) != 40
       or not isinstance(intent["harness_manifest_sha256"], str)
       or len(intent["harness_manifest_sha256"]) != 64
       or not isinstance(intent["sandbox_contract_sha256"], str)
       or len(intent["sandbox_contract_sha256"]) != 64,
       "native request/intent identity differs")
semantic_domain_envelope = NativeSemanticDomainEnvelope(
    intent, native_intent_sha256, request_raw,
)

raw_inputs = intent["raw_inputs"]
refuse(not isinstance(raw_inputs, list) or len(raw_inputs) != 5,
       "native worker must receive exactly five raw files")
expected_raw_paths = [f"data/epl/raw/{name}" for name in RAW_NAMES]
refuse([record.get("path") for record in raw_inputs] != expected_raw_paths,
       "native raw paths differ or are reordered")
for record in raw_inputs:
    refuse(not isinstance(record, dict)
           or set(record) != {"path", "sha256", "bytes"},
           "native raw receipt fields differ")
    path = (root / record["path"]).resolve()
    try:
        path.relative_to(root / "data" / "epl" / "raw")
    except ValueError as exc:
        raise NativeSemanticRefusal(
            "native raw path escapes isolated raw root"
        ) from exc
    blob = path.read_bytes()
    refuse(hashlib.sha256(blob).hexdigest() != record["sha256"]
           or len(blob) != record["bytes"],
           f"native raw bytes differ: {record['path']}")
raw_entries = list((root / "data" / "epl" / "raw").iterdir())
actual_raw = sorted(path.relative_to(root).as_posix() for path in raw_entries)
refuse(any(not path.is_file() for path in raw_entries)
       or actual_raw != sorted(expected_raw_paths),
       "isolated raw root exposes files other than the exact five training inputs")

frames = []
parse_receipts = []
for code, record in zip(RAW_CODES, raw_inputs, strict=True):
    parsed = parse.parse_season(code)
    allowed_issues = (
        [parse.blank_rows_issue(parsed.dropped_blank_rows)]
        if parsed.dropped_blank_rows else []
    )
    refuse(parsed.unknown_teams or parsed.issues != allowed_issues,
           f"{code}: parent parser reported unexpected issues: {parsed.issues}")
    frame = parsed.frame
    refuse(len(frame) != 380 or not bool(frame["played"].all()),
           f"{code}: expected exactly 380 played rows")
    frame = frame[list(INPUT_COLUMNS)].copy()
    refuse(frame.isna().any().drop(labels=["kickoff"]).any(),
           f"{code}: sanitized native input contains a null")
    refuse(frame["kickoff"].notna().any(),
           f"{code}: pre-2019 training input unexpectedly contains kickoff times")
    goals_h = frame["fthg"].to_numpy(dtype=int)
    goals_a = frame["ftag"].to_numpy(dtype=int)
    derived = np.where(goals_h > goals_a, "H",
                       np.where(goals_h < goals_a, "A", "D"))
    refuse(not np.array_equal(frame["ftr"].astype(str).to_numpy(), derived),
           f"{code}: FTR differs from the two goal fields")
    frames.append(frame)
    parse_receipts.append({
        "path": record["path"], "sha256": record["sha256"],
        "bytes": record["bytes"], "season_code": code,
        "season": parsed.season, "rows": int(len(frame)),
        "dropped_blank_rows": int(parsed.dropped_blank_rows),
        "issues": list(parsed.issues),
    })

played = schema.sort_for_walk_forward(pd.concat(frames, ignore_index=True))
counts = played["season"].astype(str).value_counts().to_dict()
refuse(len(played) != 1900 or counts != {season: 380 for season in ALL_SEASONS},
       f"sanitized native counts differ: {counts}")
refuse(played["match_id"].astype(str).duplicated().any(),
       "sanitized native input contains duplicate match_id values")
refuse(played["home_key"].isna().any() or played["away_key"].isna().any(),
       "sanitized native input contains an unresolved team key")

schedule = intent["schedule"]
refuse(not isinstance(schedule, list) or len(schedule) != 1520,
       "native request schedule is not exactly 1,520 rows")
schedule_fields = {
    "ordinal", "match_id", "season", "date", "home_key", "away_key",
    "block", "cutoff",
}
for i, row in enumerate(schedule):
    refuse(not isinstance(row, dict) or set(row) != schedule_fields
           or row["ordinal"] != i,
           f"native schedule row {i} is malformed")

training = played.loc[played["season"].astype(str).isin(TRAINING_SEASONS)].copy()
iso = pd.to_datetime(training["date"]).dt.isocalendar()
training["block"] = [
    f"{season}|{int(year)}W{int(week):02d}"
    for season, year, week in zip(
        training["season"].astype(str), iso["year"], iso["week"], strict=True,
    )
]
training["cutoff"] = training.groupby("block", sort=False)["date"].transform("min")
observed_schedule = [{
    "ordinal": i,
    "match_id": str(row.match_id),
    "season": str(row.season),
    "date": pd.Timestamp(row.date).date().isoformat(),
    "home_key": str(row.home_key),
    "away_key": str(row.away_key),
    "block": str(row.block),
    "cutoff": pd.Timestamp(row.cutoff).date().isoformat(),
} for i, row in enumerate(training.itertuples(index=False))]
refuse(observed_schedule != schedule,
       "parent-parsed training identities differ from the frozen schedule")
outcome_code_by_id = {
    str(row.match_id): {"H": 0, "D": 1, "A": 2}[str(row.ftr)]
    for row in training.itertuples(index=False)
}
refuse(len(outcome_code_by_id) != 1520,
       "parent-parsed training outcomes do not map one-to-one to the schedule")

cuts = walkforward.matchweek_cutoffs(
    played, score_seasons=TRAINING_SEASONS, cadence=1,
)
refuse(len(cuts) != 142 or sum(len(cut.rows) for cut in cuts) != 1520,
       "parent native cutoff schedule differs from 142 blocks / 1,520 rows")
schedule_blocks = []
for row in schedule:
    if not schedule_blocks or schedule_blocks[-1][0]["block"] != row["block"]:
        schedule_blocks.append([])
    schedule_blocks[-1].append(row)
refuse(len(schedule_blocks) != 142,
       "request training schedule is not exactly 142 contiguous blocks")
for block_ordinal, (cut, expected) in enumerate(
    zip(cuts, schedule_blocks, strict=True)
):
    target = played.iloc[cut.rows]
    refuse(tuple(target["match_id"].astype(str))
           != tuple(row["match_id"] for row in expected),
           f"parent cutoff {block_ordinal} fixture order differs")
    refuse(str(cut.season) != expected[0]["season"]
           or pd.Timestamp(cut.cutoff).date().isoformat() != expected[0]["cutoff"],
           f"parent cutoff {block_ordinal} identity differs")

ordinals = request["block_ordinals"]
refuse(not isinstance(ordinals, list)
       or any(type(value) is not int for value in ordinals)
       or ordinals != sorted(set(ordinals))
       or any(value < 0 or value >= len(cuts) for value in ordinals),
       "native block ordinals must be a sorted unique subset of 0..141")

cfg = freeze.frozen_wcmodel_config()
inf = cfg["model"]["inference"]
refuse(cfg["seed"] != 20260611 or inf["backend"] != "advi"
       or int(inf["draws"]) != 1000 or int(inf["tune"]) != 1000
       or int(inf["advi_iters"]) != 30000,
       "parent native inference configuration differs")
anchor = anchor_mod.Anchor(played, freeze.frozen_elo_config())
store = fit_mod.build_store(
    played, root=runtime_root / "shots_native_store",
    rebuild=True,
)

with fit_mod.config_read_once(cfg):
    for block_ordinal in ordinals:
        cut = cuts[block_ordinal]
        expected = schedule_blocks[block_ordinal]
        # Keep stdout a canonical machine channel even if an imported package
        # adds a progress message in a later environment.
        with contextlib.redirect_stdout(sys.stderr):
            try:
                result = walkforward._one_cutoff(
                    cut, played, store, anchor, cfg, played,
                )
            except (ValueError, RuntimeError, FloatingPointError) as exc:
                raise NativeSemanticRefusal(
                    "native model fit refused with "
                    f"{type(exc).__module__}.{type(exc).__name__}: {exc}"
                ) from exc
        refuse(result["match_ids"] != [row["match_id"] for row in expected],
               f"native block {block_ordinal} returned different fixture ids")
        refuse(result["unpriceable"] or result["malformed"],
               f"native block {block_ordinal} is unpriceable/malformed")
        health = result["health"]
        refuse(health.get("all_finite") is not True
               or health.get("sigma_positive") is not True
               or health.get("home_adv_sane") is not True,
               f"native block {block_ordinal} failed numerical health")
        rows = []
        for expected_row, native in zip(expected, result["probs"], strict=True):
            refuse(not isinstance(native, list) or len(native) != 3
                   or any(type(v) not in (int, float)
                          or not math.isfinite(float(v))
                          or not 0.0 < float(v) <= 1.0 for v in native)
                   or abs(sum(float(v) for v in native) - 1.0) > 1.5e-8
                   or any(float(v) != round(float(v), 8) for v in native),
                   f"native block {block_ordinal} returned invalid probabilities")
            rows.append({
                "ordinal": expected_row["ordinal"],
                "match_id": expected_row["match_id"],
                "season": expected_row["season"],
                "block": expected_row["block"],
                "cutoff": expected_row["cutoff"],
                "home_key": expected_row["home_key"],
                "away_key": expected_row["away_key"],
                "native": [float(v) for v in native],
                "y": int(outcome_code_by_id[expected_row["match_id"]]),
            })
        payload = {
            "schema": BLOCK_SCHEMA,
            "native_intent_sha256": native_intent_sha256,
            "block_identity_sha256": hashlib.sha256(canonical({
                "schema": BLOCK_IDENTITY_SCHEMA,
                "native_intent_sha256": native_intent_sha256,
                "block_ordinal": block_ordinal,
                "schedule_rows": expected,
            })).hexdigest(),
            "harness_commit": intent["harness_commit"],
            "harness_manifest_sha256": intent["harness_manifest_sha256"],
            "parent_commit": PARENT_COMMIT,
            "parent_tree": PARENT_TREE,
            "training_schedule_sha256": intent["training_schedule_sha256"],
            "block_ordinal": block_ordinal,
            "block": expected[0]["block"],
            "cutoff": expected[0]["cutoff"],
            "rows": rows,
            "receipt": {
                "exposed_raw_count": 5,
                "exposed_raw_files": raw_inputs,
                "parsed_seasons": parse_receipts,
                "native_modules": module_paths,
                "feature_cache_root": "runtime/feature_cache",
                "input_rows": int(len(played)),
                "training_rows": 1520,
                "training_blocks": 142,
                "seed": int(cfg["seed"]),
                "backend": str(inf["backend"]),
                "draws": int(inf["draws"]),
                "tune": int(inf["tune"]),
                "advi_iterations": int(inf["advi_iters"]),
                "cadence": 1,
                "n_training_matches": int(result["n_training_matches"]),
                "n_teams": int(result["n_teams"]),
                "cold_start_teams": list(result["cold_start_teams"]),
                "provisional_teams": list(result["provisional_teams"]),
                "anchor_spec": str(result["anchor_spec"]),
                "warnings": list(result["warnings"]),
                "health": health,
            },
        }
        sys.stdout.buffer.write(canonical(payload))
        sys.stdout.buffer.flush()
'''


class NonPublishingRunStop(Exception):
    """Control/infrastructure stop that must never become a scientific result."""


class ResumableRunInterruption(NonPublishingRunStop):
    """A process/infrastructure interruption resumable from valid shards."""


class ManualReconciliationRequired(NonPublishingRunStop):
    """Ambiguous durable/process state forbids both retry and publication."""


class RunnerNotReady(ResumableRunInterruption):
    """The requested transaction cannot safely acquire execution authority."""


class NativeWorkerSandboxStop(RunnerNotReady):
    """The deny-by-default native-worker sandbox could not be established."""


class NativeWorkerIOFailure(ResumableRunInterruption):
    """The bounded native-worker process/channel stopped without a result."""


class NativeRuntimeClosureMismatch(shots.LockMismatch):
    """Proven post-launch H/runtime inequality eligible for publication."""


_PUBLISHABLE_SCIENTIFIC_REFUSALS = (
    shots.SourceDigestMismatch,
    shots.ShotSchemaMismatch,
    shots.ShotValueInvalid,
    shots.ShotPanelMismatch,
    shots.FixtureSetMismatch,
    shots.TimeBoundaryViolation,
    shots.ProbabilityInvalid,
    shots.FitFailure,
    shots.CanaryFailed,
)

_PUBLISHABLE_TRAINING_REFUSALS = (
    *_PUBLISHABLE_SCIENTIFIC_REFUSALS,
    NativeRuntimeClosureMismatch,
)


class _NativeSemanticPublicationReady(Exception):
    """Internal unwind after the child and temporary leases are closed."""


class _NativeCompletionPublicationReady(Exception):
    """Internal unwind for post-cleanup clean-completion publication."""


@dataclass
class _PendingNativeSemanticPublication:
    receipt: dict[str, Any] | None = None
    refusal: shots.ShotsError | None = None

    def arm(
        self, receipt: Mapping[str, Any], refusal: shots.ShotsError,
    ) -> NoReturn:
        if self.receipt is not None or self.refusal is not None:
            raise shots.LockMismatch(
                "native semantic publication boundary was armed twice"
            )
        self.receipt = dict(receipt)
        self.refusal = refusal
        raise _NativeSemanticPublicationReady


@dataclass
class _PendingNativeCompletionPublication:
    receipt: dict[str, Any] | None = None
    validation: dict[str, Any] | None = None
    records: tuple[dict[str, Any], ...] | None = None

    def arm(
        self, receipt: Mapping[str, Any], *,
        native_intent: Mapping[str, Any], native_intent_sha256: str,
        h: _VerifiedH, training_sha256: str,
        raw_inputs: Sequence[Mapping[str, Any]],
        blocks: Sequence[Sequence[Mapping[str, Any]]],
        sandbox_contract: Mapping[str, Any],
    ) -> NoReturn:
        if self.receipt is not None or self.validation is not None:
            raise shots.LockMismatch(
                "native completion publication boundary was armed twice"
            )
        self.receipt = dict(receipt)
        self.validation = {
            "native_intent": dict(native_intent),
            "native_intent_sha256": native_intent_sha256,
            "h": h,
            "training_sha256": training_sha256,
            "raw_inputs": tuple(dict(value) for value in raw_inputs),
            "blocks": tuple(tuple(dict(row) for row in block) for block in blocks),
            "sandbox_contract": dict(sandbox_contract),
        }
        raise _NativeCompletionPublicationReady


@dataclass(frozen=True)
class _VerifiedH:
    commit: str
    manifest_sha256: str
    training_schedule_sha256: str
    decision_schedule_sha256: str
    native_runtime_lock: Mapping[str, Any] | None = None


@dataclass(frozen=True)
class _VerifiedK:
    commit: str
    manifest_sha256: str
    harness: _VerifiedH


@dataclass(frozen=True)
class _OptimizerAttempt:
    """Durable state returned by the exactly-once optimizer boundary.

    ``may_invoke_optimizer`` is true only for the call that created the intent
    with ``O_EXCL``.  A matching completed receipt is resumable without another
    optimizer call.  A pre-existing intent without a receipt is deliberately
    ambiguous and is refused by ``_begin_optimizer_once``.
    """

    intent_record: Mapping[str, Any]
    intent: Mapping[str, Any]
    may_invoke_optimizer: bool
    receipt_record: Mapping[str, Any] | None
    receipt: Mapping[str, Any] | None


@dataclass(frozen=True)
class _DecisionRunReservation:
    """Safe control-plane reservation for the still-disabled decision run.

    The state contains provenance identities and fixed schedule counts only.
    It is deliberately incapable of carrying predictions, probabilities,
    outcomes, market inputs, scores, or result-artifact references.  Creation
    of this reservation is not authority to open a decision input or execute a
    worker; a future caller must separately retain live H/K verification.
    """

    state: Mapping[str, Any]
    state_sha256: str
    reservation_created: bool


@dataclass(frozen=True)
class LifecycleStatus:
    build_state: str
    h_ready: bool
    training_worker_ready: bool
    decision_worker_ready: bool
    h_manifest_present: bool
    k_manifest_present: bool
    h_frozen: bool
    k_frozen: bool
    training_schedule_sha256: str
    decision_schedule_sha256: str
    issues: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _canonical_bytes(value: Mapping[str, Any]) -> bytes:
    return (json.dumps(
        dict(value), sort_keys=True, separators=(",", ":"), ensure_ascii=True,
        allow_nan=False,
    ) + "\n").encode("ascii")


def _read_canonical(path: Path, *, label: str) -> tuple[dict[str, Any], bytes]:
    try:
        raw = _read_regular_snapshot(path, label=label)
        value = json.loads(raw.decode("ascii"))
        canonical = _canonical_bytes(value)
    except (OSError, UnicodeDecodeError, json.JSONDecodeError,
            TypeError, ValueError) as exc:
        raise shots.LockMismatch(f"{label} is not canonical ASCII JSON: {exc}") from exc
    if not isinstance(value, dict) or canonical != raw:
        raise shots.LockMismatch(f"{label} is not one canonical JSON object")
    return value, raw


def _git_bytes(*args: str) -> bytes:
    environment = _git_environment()
    if not _GIT_EXECUTABLE.is_file() or not os.access(_GIT_EXECUTABLE, os.X_OK):
        raise RunnerNotReady("fixed /usr/bin/git executable is unavailable")
    try:
        result = subprocess.run(
            (str(_GIT_EXECUTABLE), "-C", str(_ROOT), *args),
            capture_output=True, check=False, timeout=30, env=environment,
            stdin=subprocess.DEVNULL,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ResumableRunInterruption(
            f"fixed git invocation failed: {type(exc).__name__}"
        ) from exc
    if result.returncode:
        raise ResumableRunInterruption(
            f"git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.stdout


def _git_environment() -> dict[str, str]:
    """Return a fresh environment with no inherited Git control variables."""
    return {
        "GIT_ATTR_NOSYSTEM": "1",
        "GIT_CONFIG_GLOBAL": "/dev/null",
        "GIT_CONFIG_NOSYSTEM": "1",
        "GIT_NO_REPLACE_OBJECTS": "1",
        "GIT_OPTIONAL_LOCKS": "0",
        "GIT_TERMINAL_PROMPT": "0",
        "LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin",
    }


def _git_text(*args: str) -> str:
    return _git_bytes(*args).decode("utf-8", "replace").strip()


def _git_succeeds(*args: str) -> bool:
    if not _GIT_EXECUTABLE.is_file() or not os.access(_GIT_EXECUTABLE, os.X_OK):
        raise RunnerNotReady("fixed /usr/bin/git executable is unavailable")
    try:
        result = subprocess.run(
            (str(_GIT_EXECUTABLE), "-C", str(_ROOT), *args),
            stdout=subprocess.DEVNULL, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, check=False, timeout=30,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise ResumableRunInterruption(
            f"fixed git invocation failed: {type(exc).__name__}"
        ) from exc
    expected_false = (
        len(args) == 4
        and args[0] == "merge-base"
        and args[1] == "--is-ancestor"
        and result.returncode == 1
    )
    if result.returncode != 0 and not expected_false:
        raise ResumableRunInterruption(
            f"git {' '.join(args)} failed: "
            f"{result.stderr.decode('utf-8', 'replace').strip()}"
        )
    return result.returncode == 0


def _require_git_regular_blobs(
    commit: str, paths_to_check: Sequence[str], *, label: str,
) -> None:
    """Require an exact set of non-executable regular blobs at one commit."""
    expected = set(paths_to_check)
    if not expected or len(expected) != len(tuple(paths_to_check)):
        raise shots.LockMismatch(f"{label} Git path set is empty or duplicated")
    raw = _git_bytes(
        "ls-tree", "-rz", commit, "--", *tuple(sorted(expected)),
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
        raise shots.LockMismatch(f"{label} Git tree output is malformed") from exc
    if (set(observed) != expected
            or any(value != ("100644", "blob") for value in observed.values())):
        raise shots.LockMismatch(
            f"{label} paths must be exact 100644 regular blobs"
        )


def _commit(value: str, *, label: str) -> str:
    if not isinstance(value, str) or not _HEX40.fullmatch(value):
        raise shots.LockMismatch(f"{label} must be a full lowercase git id")
    if _git_text("rev-parse", f"{value}^{{commit}}") != value:
        raise shots.LockMismatch(f"{label} does not resolve exactly")
    return value


def _digest_rows(schema: str, rows: Sequence[Mapping[str, Any]]) -> str:
    digest = hashlib.sha256((schema + "\n").encode("ascii"))
    for row in rows:
        digest.update(_canonical_bytes(row))
    return digest.hexdigest()


def _read_regular_snapshot(path: Path, *, label: str) -> bytes:
    """Read one regular inode and require its visible name to stay bound."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    descriptor = -1
    try:
        descriptor = os.open(
            absolute, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0),
        )
        before = os.fstat(descriptor)
        if not stat.S_ISREG(before.st_mode) or before.st_size < 0:
            raise shots.LockMismatch(f"{label} is not a regular file")
        chunks: list[bytes] = []
        remaining = int(before.st_size)
        while remaining:
            chunk = os.read(descriptor, min(1_048_576, remaining))
            if not chunk:
                raise shots.LockMismatch(f"{label} ended during its snapshot")
            chunks.append(chunk); remaining -= len(chunk)
        if os.read(descriptor, 1):
            raise shots.LockMismatch(f"{label} grew during its snapshot")
        after = os.fstat(descriptor)
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        if identity(before) != identity(after):
            raise shots.LockMismatch(f"{label} changed during its snapshot")
        visible = os.stat(absolute, follow_symlinks=False)
        if (not stat.S_ISREG(visible.st_mode)
                or (visible.st_dev, visible.st_ino, visible.st_mode)
                != (after.st_dev, after.st_ino, after.st_mode)):
            raise shots.LockMismatch(
                f"{label} visible path changed during its snapshot"
            )
        return b"".join(chunks)
    except OSError as exc:
        raise shots.LockMismatch(f"{label} could not be snapshotted") from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _iso_date(value: Any) -> str:
    date = pd.Timestamp(value)
    if pd.isna(date) or date != date.normalize():
        raise shots.TimeBoundaryViolation("schedule dates must be finite midnight dates")
    return date.date().isoformat()


def _training_binding() -> tuple[str, tuple[dict[str, Any], ...]]:
    frame = shots.load_pinned_training_fixtures()
    rows = tuple({
        "ordinal": i, "match_id": str(row.match_id), "season": str(row.season),
        "date": _iso_date(row.date), "home_key": str(row.home_key),
        "away_key": str(row.away_key), "block": str(row.block),
        "cutoff": _iso_date(row.cutoff),
    } for i, row in enumerate(frame.itertuples(index=False)))
    if len(rows) != shots.TRAINING_ROWS:
        raise shots.FixtureSetMismatch("training schedule is not exactly 1,520 rows")
    if shots.sha256_file(paths.MATCHES_PARQUET) != shots.MATCHES_SHA256:
        raise shots.SourceDigestMismatch(
            "matches archive changed while binding the training schedule"
        )
    return _digest_rows("epl-shots-training-schedule-1", rows), rows


# ==========================================================================
# Safe PRE-H decision lifecycle foundations (identity/control plane only)
# ==========================================================================

def _decision_schedule_blocks_exact(
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    """Validate the complete outcome-free decision schedule and block order."""
    if not isinstance(schedule, Sequence) or isinstance(
        schedule, (str, bytes, bytearray),
    ):
        raise shots.FixtureSetMismatch("decision schedule is not a row sequence")
    if len(schedule) != _DECISION_ROWS:
        raise shots.FixtureSetMismatch(
            f"decision schedule is not exactly {_DECISION_ROWS:,} rows"
        )

    identifiers: set[str] = set()
    season_counts = {season: 0 for season in _DECISION_SEASONS}
    season_order: list[str] = []
    normalized: list[dict[str, str]] = []
    previous_date: str | None = None
    for ordinal, row in enumerate(schedule):
        if not isinstance(row, Mapping) or set(row) != set(_K2_SCHEDULE_FIELDS):
            raise shots.LockMismatch("decision schedule fields differ")
        if (type(row["ordinal"]) is not int or row["ordinal"] != ordinal
                or any(not isinstance(row[name], str) or not row[name]
                       for name in _K2_SCHEDULE_FIELDS if name != "ordinal")):
            raise shots.FixtureSetMismatch(
                "decision schedule identity is malformed"
            )
        match_id = row["match_id"]
        if match_id in identifiers:
            raise shots.FixtureSetMismatch(
                "decision schedule match_id is duplicated"
            )
        identifiers.add(match_id)
        season = row["season"]
        if season not in season_counts:
            raise shots.FixtureSetMismatch("decision schedule season differs")
        season_counts[season] += 1
        if not season_order or season_order[-1] != season:
            if season in season_order:
                raise shots.FixtureSetMismatch(
                    "decision schedule season is not contiguous"
                )
            season_order.append(season)
        date = _iso_date(row["date"])
        cutoff = _iso_date(row["cutoff"])
        if row["date"] != date or row["cutoff"] != cutoff:
            raise shots.TimeBoundaryViolation(
                "decision schedule date/cutoff is not exact ISO"
            )
        if previous_date is not None and date < previous_date:
            raise shots.TimeBoundaryViolation(
                "decision schedule dates are not monotone"
            )
        previous_date = date
        normalized.append({
            "match_id": match_id, "season": season, "date": date,
        })

    expected_counts = {season: 380 for season in _DECISION_SEASONS}
    if season_counts != expected_counts or tuple(season_order) != _DECISION_SEASONS:
        raise shots.FixtureSetMismatch(
            "decision schedule season partition differs"
        )

    derived = shots.attach_weekly_cutoffs(pd.DataFrame(normalized))
    blocks: list[list[Mapping[str, Any]]] = []
    closed: set[str] = set()
    for ordinal, row in enumerate(schedule):
        expected_block = str(derived.iloc[ordinal].block)
        expected_cutoff = _iso_date(derived.iloc[ordinal].cutoff)
        if row["block"] != expected_block or row["cutoff"] != expected_cutoff:
            raise shots.FixtureSetMismatch(
                "decision schedule block/cutoff differs from its ISO week"
            )
        if not blocks or blocks[-1][0]["block"] != row["block"]:
            if row["block"] in closed:
                raise shots.FixtureSetMismatch(
                    "decision schedule block is not contiguous"
                )
            if blocks:
                closed.add(str(blocks[-1][0]["block"]))
            blocks.append([])
        if blocks[-1] and (
            blocks[-1][0]["season"] != row["season"]
            or blocks[-1][0]["cutoff"] != row["cutoff"]
        ):
            raise shots.FixtureSetMismatch(
                "one decision block has mixed identity"
            )
        blocks[-1].append(row)
    if len(blocks) != _DECISION_BLOCKS:
        raise shots.FixtureSetMismatch(
            f"decision schedule is not exactly {_DECISION_BLOCKS} blocks"
        )
    return tuple(tuple(
        MappingProxyType(dict(row)) for row in block
    ) for block in blocks)


def decision_schedule_binding() -> tuple[str, tuple[dict[str, Any], ...]]:
    """Bind the exact outcome-free ordered decision schedule and labels."""
    corpus_path = paths.FIT_DIR / "walkforward_predictions.parquet"
    raw = _read_regular_snapshot(corpus_path, label="decision corpus")
    if hashlib.sha256(raw).hexdigest() != shots.DECISION_CORPUS_SHA256:
        raise shots.SourceDigestMismatch(
            "decision corpus changed while binding the decision schedule"
        )
    frame = pd.read_parquet(
        io.BytesIO(raw),
        columns=["match_id", "season", "date", "home_key", "away_key", "block"],
    )
    derived = shots.attach_weekly_cutoffs(frame[["match_id", "season", "date"]])
    rows = tuple({
        "ordinal": i, "match_id": str(row.match_id), "season": str(row.season),
        "date": _iso_date(row.date), "home_key": str(row.home_key),
        "away_key": str(row.away_key), "block": str(row.block),
        "cutoff": _iso_date(derived.iloc[i].cutoff),
    } for i, row in enumerate(frame.itertuples(index=False)))
    _decision_schedule_blocks_exact(rows)
    return _digest_rows("epl-shots-decision-schedule-1", rows), rows


def _decision_run_state(
    *, h: _VerifiedH, k: _VerifiedK, decision_schedule_sha256: str,
) -> tuple[dict[str, Any], str]:
    """Build one content identity without opening any decision data values."""
    if k.harness != h:
        raise shots.LockMismatch("coefficient freeze belongs to another harness")
    if (any(not isinstance(value, str) for value in (
                h.commit, h.manifest_sha256, h.decision_schedule_sha256,
                k.commit, k.manifest_sha256, decision_schedule_sha256,
            ))
            or not _HEX40.fullmatch(h.commit)
            or not _HEX64.fullmatch(h.manifest_sha256)
            or not _HEX40.fullmatch(k.commit)
            or not _HEX64.fullmatch(k.manifest_sha256)
            or not _HEX64.fullmatch(decision_schedule_sha256)
            or decision_schedule_sha256 != h.decision_schedule_sha256):
        raise shots.LockMismatch("decision run provenance identity is malformed")
    state = {
        "schema": _DECISION_RUN_STATE_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "coefficient_commit": k.commit,
        "coefficient_manifest_sha256": k.manifest_sha256,
        "decision_schedule_sha256": decision_schedule_sha256,
        "corpus_sha256": shots.DECISION_CORPUS_SHA256,
        "rows": _DECISION_ROWS,
        "blocks": _DECISION_BLOCKS,
        "state": "reserved",
    }
    raw = _canonical_bytes(state)
    return state, hashlib.sha256(raw).hexdigest()


def _validate_decision_run_state(value: Mapping[str, Any]) -> str:
    fields = {
        "schema", "harness_commit", "harness_manifest_sha256",
        "coefficient_commit", "coefficient_manifest_sha256",
        "decision_schedule_sha256", "corpus_sha256", "rows", "blocks",
        "state",
    }
    if not isinstance(value, Mapping):
        raise shots.LockMismatch("decision run state is not a mapping")
    _keys(value, fields, label="decision run state")
    if (value["schema"] != _DECISION_RUN_STATE_SCHEMA
            or value["state"] != "reserved"
            or not isinstance(value["harness_commit"], str)
            or not _HEX40.fullmatch(value["harness_commit"])
            or not isinstance(value["coefficient_commit"], str)
            or not _HEX40.fullmatch(value["coefficient_commit"])
            or any(not isinstance(value[name], str)
                   or not _HEX64.fullmatch(value[name]) for name in (
                       "harness_manifest_sha256",
                       "coefficient_manifest_sha256",
                       "decision_schedule_sha256", "corpus_sha256",
                   ))
            or value["corpus_sha256"] != shots.DECISION_CORPUS_SHA256
            or type(value["rows"]) is not int
            or value["rows"] != _DECISION_ROWS
            or type(value["blocks"]) is not int
            or value["blocks"] != _DECISION_BLOCKS):
        raise shots.LockMismatch("decision run state is malformed")
    return hashlib.sha256(_canonical_bytes(value)).hexdigest()


def _decision_run_state_entries(
    *, state_root: Path,
) -> tuple[tuple[dict[str, Any], str], ...]:
    """Read decision state through one symlink-safe directory descriptor."""
    try:
        with _open_decision_state_directory(
            Path(state_root), create=False,
        ) as (_, descriptor):
            if descriptor is None:
                return ()
            return _decision_run_state_entries_at(descriptor)
    except OSError as exc:
        raise ResumableRunInterruption(
            "decision run state root could not be inspected before any "
            "control-state mutation"
        ) from exc


@contextlib.contextmanager
def _open_decision_state_directory(
    path: Path, *, create: bool,
) -> Iterator[tuple[Path, int | None]]:
    """Open one directory tree without following a component symlink.

    All control-plane operations retain and use the returned descriptor.  On
    context exit the visible absolute name must still identify that exact
    directory.  A one-way namespace swap is therefore an ambiguous operation
    requiring manual reconciliation, even though writes safely stayed beneath
    the retained descriptor.  A hostile same-owner swap-and-restore completed
    between these checks (A-B-A) requires an external immutable namespace or
    append-only ledger to detect.
    """
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    directory = getattr(os, "O_DIRECTORY", 0)
    cloexec = getattr(os, "O_CLOEXEC", 0)
    if not nofollow or not directory:
        raise RunnerNotReady(
            "decision state requires O_NOFOLLOW and O_DIRECTORY"
        )
    absolute = Path(os.path.abspath(os.fspath(path)))
    descriptor = -1
    opened_identity: tuple[int, int, int] | None = None
    mutation_possible = False
    missing = False
    try:
        descriptor = os.open(
            "/", os.O_RDONLY | directory | nofollow | cloexec,
        )
        if not stat.S_ISDIR(os.fstat(descriptor).st_mode):
            raise shots.LockMismatch("filesystem root is not a directory")
        for component in absolute.parts[1:]:
            child = -1
            try:
                try:
                    child = os.open(
                        component,
                        os.O_RDONLY | directory | nofollow | cloexec,
                        dir_fd=descriptor,
                    )
                except FileNotFoundError:
                    if not create:
                        os.close(descriptor)
                        descriptor = -1
                        missing = True
                        break
                    # Once mkdir is attempted, a name may exist even if the
                    # syscall reports an error or a concurrent creator wins.
                    mutation_possible = True
                    try:
                        os.mkdir(component, 0o755, dir_fd=descriptor)
                    except FileExistsError:
                        # A concurrent creator is acceptable only if the
                        # no-follow open below proves it installed a directory.
                        pass
                    child = os.open(
                        component,
                        os.O_RDONLY | directory | nofollow | cloexec,
                        dir_fd=descriptor,
                    )
                info = os.fstat(child)
                if not stat.S_ISDIR(info.st_mode):
                    raise shots.LockMismatch(
                        "decision state path component is not a directory: "
                        f"{component}"
                    )
                if create:
                    # A successful open says nothing about whether this or a
                    # concurrent creator made the directory entry durable.  A
                    # prior attempt may also have exposed the component before
                    # failing its parent fsync.  Synchronize every traversed
                    # child and containing directory before yielding authority.
                    os.fsync(child)
                    os.fsync(descriptor)
            except BaseException as active:
                if child >= 0:
                    try:
                        os.close(child)
                    except OSError as close_exc:
                        failure_type = (
                            ManualReconciliationRequired if mutation_possible
                            else NativeWorkerIOFailure
                        )
                        raise failure_type(
                            "decision state setup descriptor did not close"
                        ) from active
                raise
            parent = descriptor
            descriptor = child
            try:
                os.close(parent)
            except OSError as exc:
                failure_type = (
                    ManualReconciliationRequired if mutation_possible
                    else NativeWorkerIOFailure
                )
                raise failure_type(
                    "decision state traversal descriptor did not close"
                ) from exc
        if not missing:
            opened = os.fstat(descriptor)
            opened_identity = (opened.st_dev, opened.st_ino, opened.st_mode)
    except BaseException as active:
        close_failure: OSError | None = None
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except OSError as exc:
                close_failure = exc
            descriptor = -1
        if close_failure is not None:
            failure_type = (
                ManualReconciliationRequired if mutation_possible
                else NativeWorkerIOFailure
            )
            raise failure_type(
                "decision state setup descriptor cleanup is ambiguous"
            ) from active
        if isinstance(active, OSError):
            failure_type = (
                ManualReconciliationRequired if mutation_possible
                else NativeWorkerIOFailure
            )
            raise failure_type(
                "decision state directory setup did not complete"
            ) from active
        raise

    # The caller body is not directory setup.  Keep this yield outside the
    # setup exception classifier so an arbitrary caller exception propagates
    # unchanged when a read-only namespace is simply absent.
    if missing:
        yield absolute, None
        return

    try:
        yield absolute, descriptor
    finally:
        active = sys.exc_info()[1]
        ambiguities: list[BaseException] = []
        details: list[str] = []
        try:
            current = os.fstat(descriptor)
            visible = os.stat(absolute, follow_symlinks=False)
        except OSError as exc:
            ambiguities.append(exc)
            details.append("visible path could not be revalidated")
        else:
            if opened_identity is not None:
                current_identity = (
                    current.st_dev, current.st_ino, current.st_mode,
                )
                visible_identity = (
                    visible.st_dev, visible.st_ino, visible.st_mode,
                )
                if (not stat.S_ISDIR(current.st_mode)
                        or not stat.S_ISDIR(visible.st_mode)
                        or current_identity != opened_identity
                        or visible_identity != opened_identity):
                    ambiguities.append(RuntimeError(
                        "decision state visible path identity differs"
                    ))
                    details.append("visible path identity changed")
        try:
            if descriptor >= 0:
                os.close(descriptor)
        except OSError as exc:
            ambiguities.append(exc)
            details.append("directory descriptor did not close")
        descriptor = -1
        if ambiguities:
            failure = ManualReconciliationRequired(
                "decision state exit is ambiguous: " + "; ".join(details)
            )
            if active is not None:
                raise failure from active
            raise failure from ambiguities[0]


def _decision_entry_identity(
    directory_fd: int, name: str, descriptor: int, *, label: str,
) -> os.stat_result:
    """Bind an opened immutable regular file to its directory entry."""
    opened = os.fstat(descriptor)
    named = os.stat(name, dir_fd=directory_fd, follow_symlinks=False)
    if (not stat.S_ISREG(opened.st_mode)
            or not stat.S_ISREG(named.st_mode)
            or (opened.st_dev, opened.st_ino) != (named.st_dev, named.st_ino)
            or opened.st_nlink != 1 or named.st_nlink != 1
            or stat.S_IMODE(opened.st_mode) != 0o444
            or stat.S_IMODE(named.st_mode) != 0o444):
        raise shots.LockMismatch(
            f"{label} is not one immutable regular directory entry"
        )
    return opened


def _read_decision_entry_at(
    directory_fd: int, name: str, *, label: str, max_bytes: int = 65_536,
) -> bytes:
    """Read one bounded no-follow entry and reject an in-place read race."""
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        try:
            return _read_open_decision_entry_at(
                directory_fd, name, descriptor, label=label,
                max_bytes=max_bytes,
            )
        except ManualReconciliationRequired:
            raise
        except BaseException as exc:
            raise ManualReconciliationRequired(
                f"{label} read is ambiguous after descriptor binding; manual "
                "reconciliation required"
            ) from exc
    finally:
        active = sys.exc_info()[1]
        if descriptor >= 0:
            try:
                os.close(descriptor)
            except BaseException as close_failure:
                message = (
                    f"{label} descriptor cleanup is ambiguous; manual "
                    "reconciliation required"
                )
                if active is not None:
                    message += f"; active failure was {active!r}"
                raise ManualReconciliationRequired(
                    message
                ) from close_failure


def _read_open_decision_entry_at(
    directory_fd: int, name: str, descriptor: int, *, label: str,
    max_bytes: int = 65_536,
) -> bytes:
    """Read and validate the exact opened inode supplied by the caller."""
    before = _decision_entry_identity(
        directory_fd, name, descriptor, label=label,
    )
    if before.st_size < 0 or before.st_size > max_bytes:
        raise shots.LockMismatch(f"{label} exceeds its byte limit")
    os.lseek(descriptor, 0, os.SEEK_SET)
    chunks: list[bytes] = []
    remaining = before.st_size
    while remaining:
        chunk = os.read(descriptor, min(remaining, 65_536))
        if not chunk:
            break
        chunks.append(chunk)
        remaining -= len(chunk)
    raw = b"".join(chunks)
    after = _decision_entry_identity(
        directory_fd, name, descriptor, label=label,
    )
    stable = (
        before.st_dev, before.st_ino, before.st_mode, before.st_nlink,
        before.st_size, before.st_mtime_ns, before.st_ctime_ns,
    ) == (
        after.st_dev, after.st_ino, after.st_mode, after.st_nlink,
        after.st_size, after.st_mtime_ns, after.st_ctime_ns,
    )
    if not stable or len(raw) != before.st_size:
        raise shots.LockMismatch(f"{label} changed while it was read")
    return raw


@contextlib.contextmanager
def _durably_bind_decision_entry_at(
    directory_fd: int, name: str, *, expected: bytes, label: str,
    max_bytes: int = 65_536, name_preobserved: bool = False,
) -> Iterator[None]:
    """Lease one exact entry through file fsync and directory durability."""
    descriptor = -1
    name_seen = False
    proven_conflict: shots.LockMismatch | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        name_seen = True

        def require_current(*, permit_complete_conflict: bool) -> None:
            nonlocal proven_conflict
            try:
                current = _decision_entry_identity(
                    directory_fd, name, descriptor, label=label,
                )
                if current.st_size != len(expected):
                    raise ManualReconciliationRequired(
                        f"{label} is not a proven complete entry; manual "
                        "reconciliation required"
                    )
                observed = _read_open_decision_entry_at(
                    directory_fd, name, descriptor, label=label,
                    max_bytes=max(max_bytes, len(expected)),
                )
            except ManualReconciliationRequired:
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"{label} identity/read is ambiguous; manual "
                    "reconciliation required"
                ) from exc
            if observed != expected:
                if permit_complete_conflict:
                    conflict = shots.LockMismatch(f"{label} bytes differ")
                    proven_conflict = conflict
                    raise conflict
                raise ManualReconciliationRequired(
                    f"{label} changed after binding; manual reconciliation "
                    "required"
                )

        require_current(permit_complete_conflict=True)
        # An identical visible file can belong to a creator paused between
        # exposing complete bytes and syncing the inode.  Directory fsync alone
        # cannot make those data blocks durable, so sync this retained inode.
        os.fsync(descriptor)
        require_current(permit_complete_conflict=False)
        _fsync_decision_state_directory(directory_fd)
        require_current(permit_complete_conflict=False)
        try:
            yield
        except BaseException as exc:
            body_failure = exc
            raise
        finally:
            require_current(permit_complete_conflict=False)
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    close_failure: BaseException | None = None
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except BaseException as exc:
            close_failure = exc
        finally:
            descriptor = -1
    if close_failure is not None:
        message = (
            f"{label} descriptor cleanup is ambiguous; manual reconciliation "
            "required"
        )
        if failure is not None:
            message += f"; active failure was {failure!r}"
        raise ManualReconciliationRequired(message) from close_failure
    if failure is None:
        return
    if failure is proven_conflict or failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if name_seen or name_preobserved:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"{label} name could not be durably bound; manual reconciliation "
            "required"
        ) from failure
    raise failure.with_traceback(failure_traceback)


def _decision_run_state_entries_at(
    directory_fd: int,
) -> tuple[tuple[dict[str, Any], str], ...]:
    """Validate all state entries relative to one already-open directory."""
    pattern = re.compile(r"decision-run-([0-9a-f]{64})\.json")
    entries: list[tuple[dict[str, Any], str]] = []
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise ManualReconciliationRequired(
            "decision run state directory listing is ambiguous; manual "
            "reconciliation required"
        ) from exc
    for name in names:
        if not name.startswith("decision-run-"):
            continue
        match = pattern.fullmatch(name)
        if match is None:
            raise shots.LockMismatch("decision run state filename is malformed")
        try:
            raw = _read_decision_entry_at(
                directory_fd, name, label="decision run state",
            )
        except ManualReconciliationRequired:
            raise
        except shots.LockMismatch as exc:
            # The read protocol raises LockMismatch only when it could not
            # prove one stable, complete, immutable entry.  Under an observed
            # permanent state namespace that uncertainty is reconciliation,
            # never a proven conflicting artifact.
            raise ManualReconciliationRequired(
                "decision run state entry is not one stable immutable "
                "artifact; manual reconciliation required"
            ) from exc
        except OSError as exc:
            raise ManualReconciliationRequired(
                "decision run state name disappeared or could not be opened; "
                "manual reconciliation required"
            ) from exc
        try:
            value = json.loads(raw.decode("ascii"))
            canonical = _canonical_bytes(value)
        except (UnicodeDecodeError, json.JSONDecodeError,
                TypeError, ValueError) as exc:
            raise shots.LockMismatch(
                f"decision run state is not canonical ASCII JSON: {exc}"
            ) from exc
        if not isinstance(value, dict) or canonical != raw:
            raise shots.LockMismatch(
                "decision run state is not one canonical JSON object"
            )
        digest = _validate_decision_run_state(value)
        if digest != match.group(1) or hashlib.sha256(raw).hexdigest() != digest:
            raise shots.LockMismatch("decision run state content address differs")
        entries.append((value, digest))
    if len(entries) > 1:
        raise shots.LockMismatch("decision run state has forked identities")
    return tuple(entries)


def _fsync_decision_state_directory(descriptor: int) -> None:
    """Make control entries durable; this never creates execution authority."""
    try:
        os.fsync(descriptor)
    except OSError as exc:
        raise ManualReconciliationRequired(
            "decision run state directory durability is ambiguous"
        ) from exc


@contextlib.contextmanager
def _decision_run_lock(
    *, state_root: Path, state_sha256: str,
) -> Iterator[tuple[int, bool]]:
    """Yield one locked dirfd plus tombstone-creation fact, never authority."""
    if not isinstance(state_sha256, str) or not _HEX64.fullmatch(state_sha256):
        raise shots.LockMismatch("decision run-lock identity is malformed")
    raw = f"{_DECISION_RUN_LOCK_SCHEMA}\n{state_sha256}\n".encode("ascii")
    name = ".decision-run.lock"
    descriptor = -1
    lock_created = False
    create_attempted = False
    name_seen = False
    lock_acquired = False
    proven_conflict: shots.LockMismatch | None = None
    busy_failure: RunnerNotReady | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        with _open_decision_state_directory(
            Path(state_root), create=True,
        ) as (_, directory_fd):
            if directory_fd is None:  # pragma: no cover - create=True invariant
                raise ResumableRunInterruption(
                    "decision run-lock root is absent"
                )
            try:
                try:
                    # An O_CREAT error cannot prove the permanent lock name was
                    # never exposed, so it crosses the manual boundary.
                    create_attempted = True
                    descriptor = os.open(
                        name,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        0o444,
                        dir_fd=directory_fd,
                    )
                    lock_created = True
                    name_seen = True
                except FileExistsError:
                    name_seen = True
                    descriptor = os.open(
                        name,
                        os.O_RDONLY | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory_fd,
                    )
                lock_info = os.fstat(descriptor)
                identity = (lock_info.st_dev, lock_info.st_ino)

                def require_current(*, permit_complete_conflict: bool) -> None:
                    nonlocal proven_conflict
                    try:
                        current = _decision_entry_identity(
                            directory_fd, name, descriptor,
                            label="decision run-lock",
                        )
                        if (current.st_dev, current.st_ino) != identity:
                            raise ManualReconciliationRequired(
                                "decision run-lock identity changed; manual "
                                "reconciliation required"
                            )
                        if current.st_size != len(raw):
                            raise ManualReconciliationRequired(
                                "decision run-lock is not a proven complete "
                                "entry; manual reconciliation required"
                            )
                        observed = _read_open_decision_entry_at(
                            directory_fd, name, descriptor,
                            label="decision run-lock", max_bytes=len(raw),
                        )
                    except ManualReconciliationRequired:
                        raise
                    except BaseException as exc:
                        raise ManualReconciliationRequired(
                            "decision run-lock identity is ambiguous; manual "
                            "reconciliation required"
                        ) from exc
                    if observed != raw:
                        if permit_complete_conflict:
                            conflict = shots.LockMismatch(
                                "decision run-lock bytes differ"
                            )
                            proven_conflict = conflict
                            raise conflict
                        raise ManualReconciliationRequired(
                            "decision run-lock changed after binding; manual "
                            "reconciliation required"
                        )

                if not lock_created:
                    require_current(permit_complete_conflict=True)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    if not lock_created:
                        require_current(permit_complete_conflict=False)
                    busy = RunnerNotReady(
                        "matching decision run is already active"
                    )
                    busy_failure = busy
                    raise busy from exc
                lock_acquired = True
                if lock_created:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    written = 0
                    while written < len(raw):
                        count = os.write(descriptor, raw[written:])
                        if count <= 0:
                            raise OSError(
                                "decision run-lock write made no progress"
                            )
                        written += count
                    os.fchmod(descriptor, 0o444)
                require_current(permit_complete_conflict=False)
                os.fsync(descriptor)
                require_current(permit_complete_conflict=False)
                _fsync_decision_state_directory(directory_fd)
                require_current(permit_complete_conflict=False)
                try:
                    yield directory_fd, lock_created
                except BaseException as exc:
                    body_failure = exc
                    raise
                finally:
                    require_current(permit_complete_conflict=False)
            finally:
                cleanup_failure: BaseException | None = None
                active = sys.exc_info()[1]
                if lock_acquired:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except BaseException as exc:
                        cleanup_failure = exc
                    finally:
                        lock_acquired = False
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        if cleanup_failure is None:
                            cleanup_failure = exc
                    finally:
                        descriptor = -1
                if cleanup_failure is not None:
                    message = (
                        "decision run-lock cleanup is ambiguous; manual "
                        "reconciliation required"
                    )
                    if active is not None:
                        message += f"; active failure was {active!r}"
                    raise ManualReconciliationRequired(
                        message
                    ) from cleanup_failure
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    if failure is None:
        return
    if failure is proven_conflict:
        raise failure.with_traceback(failure_traceback)
    if failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if lock_created:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            "decision run-lock was created before the active failure; manual "
            "reconciliation required"
        ) from failure
    if failure is busy_failure:
        raise failure.with_traceback(failure_traceback)
    if name_seen or create_attempted:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            "decision run-lock name could not be durably bound; manual "
            "reconciliation required"
        ) from failure
    if isinstance(failure, (NonPublishingRunStop, shots.ShotsError)):
        raise failure.with_traceback(failure_traceback)
    raise ResumableRunInterruption(
        "decision run-lock failed before name creation"
    ) from failure


@contextlib.contextmanager
def _reserve_digest_lease_at(
    directory_fd: int, name: str, digest: str,
) -> Iterator[bool]:
    """Create or bind one claim and retain its exact inode for the caller."""
    # Keep the legacy decision-state entry point on the single audited claim
    # state machine; the directory descriptor is already leased by the caller.
    with _digest_reservation_at(
        directory_fd, name, digest, create=True,
    ) as created:
        yield created


def _reserve_digest_at(
    directory_fd: int, name: str, digest: str,
) -> bool:
    """Compatibility wrapper for one fully leased immutable claim."""
    with _reserve_digest_lease_at(
        directory_fd, name, digest,
    ) as created:
        return created


def _require_digest_at(directory_fd: int, name: str, digest: str) -> None:
    """Require an existing claim without recreating missing evidence."""
    filename = f".{name}.claim"
    raw = (digest + "\n").encode("ascii")
    try:
        with _durably_bind_decision_entry_at(
            directory_fd, filename, expected=raw,
            label=f"immutable {name} reservation", name_preobserved=True,
        ):
            pass
    except ManualReconciliationRequired as exc:
        if not isinstance(exc.__cause__, FileNotFoundError):
            raise
        raise ManualReconciliationRequired(
            f"immutable {name} reservation has incomplete durable state; "
            "execution state is ambiguous"
        ) from exc
    except FileNotFoundError as exc:
        raise ManualReconciliationRequired(
            f"immutable {name} reservation has incomplete durable state; "
            "execution state is ambiguous"
        ) from exc


@contextlib.contextmanager
def _write_decision_state_lease_at(
    directory_fd: int, name: str, raw: bytes,
) -> Iterator[None]:
    """Create one decision state and retain its O_EXCL inode through use."""
    descriptor = -1
    create_attempted = False
    created = False
    file_exists: FileExistsError | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        try:
            create_attempted = True
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                | getattr(os, "O_CLOEXEC", 0),
                0o444,
                dir_fd=directory_fd,
            )
            created = True
        except FileExistsError as exc:
            # FileExistsError is the sole proven no-create control result.  It
            # lets the fixed-path callers bind the existing name themselves.
            file_exists = exc
            raise
        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        written = 0
        while written < len(raw):
            count = os.write(descriptor, raw[written:])
            if count <= 0:
                raise OSError("decision run state write made no progress")
            written += count
        os.fchmod(descriptor, 0o444)

        def require_created_state() -> None:
            try:
                current = _decision_entry_identity(
                    directory_fd, name, descriptor,
                    label="decision run state",
                )
                if (current.st_dev, current.st_ino) != identity:
                    raise ManualReconciliationRequired(
                        "decision run state identity changed; manual "
                        "reconciliation required"
                    )
                if current.st_size != len(raw):
                    raise ManualReconciliationRequired(
                        "decision run state is not complete; manual "
                        "reconciliation required"
                    )
                observed = _read_open_decision_entry_at(
                    directory_fd, name, descriptor,
                    label="decision run state", max_bytes=len(raw),
                )
            except ManualReconciliationRequired:
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    "decision run state verification is ambiguous; manual "
                    "reconciliation required"
                ) from exc
            if observed != raw:
                raise ManualReconciliationRequired(
                    "decision run state bytes changed after creation; manual "
                    "reconciliation required"
                )

        require_created_state()
        os.fsync(descriptor)
        require_created_state()
        _fsync_decision_state_directory(directory_fd)
        require_created_state()
        try:
            yield
        except BaseException as exc:
            body_failure = exc
            raise
        finally:
            require_created_state()
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    close_failure: BaseException | None = None
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except BaseException as exc:
            close_failure = exc
        finally:
            descriptor = -1
    if close_failure is not None:
        message = (
            "decision run state descriptor cleanup is ambiguous; manual "
            "reconciliation required"
        )
        if failure is not None:
            message += f"; active failure was {failure!r}"
        raise ManualReconciliationRequired(message) from close_failure
    if failure is None:
        return
    if failure is file_exists or failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if created or create_attempted:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            "decision run state name may have been exposed; manual "
            "reconciliation required"
        ) from failure
    raise ResumableRunInterruption(
        "decision run state creation stopped before its name attempt"
    ) from failure


def _write_decision_state_at(
    directory_fd: int, name: str, raw: bytes,
) -> None:
    """Compatibility wrapper for one fully leased decision-state write."""
    try:
        with _write_decision_state_lease_at(directory_fd, name, raw):
            pass
    except FileExistsError:
        with _durably_bind_decision_entry_at(
            directory_fd, name, expected=raw,
            label="decision run state", name_preobserved=True,
        ):
            pass


def _reserve_decision_run_state(
    *, h: _VerifiedH, k: _VerifiedK, decision_schedule_sha256: str,
    state_root: Path,
) -> _DecisionRunReservation:
    """Reserve safe control state; never authorize data access or execution.

    ``reservation_created`` reports only that this call durably installed the
    control record.  It is not a ``may_execute`` capability.  In particular, a
    pre-existing permanent lock with missing claim/state evidence is ambiguous
    and can never recreate a true result.
    """
    state, state_sha256 = _decision_run_state(
        h=h, k=k, decision_schedule_sha256=decision_schedule_sha256,
    )
    root = Path(state_root)
    with _decision_run_lock(
        state_root=root, state_sha256=state_sha256,
    ) as (directory_fd, lock_created):
        try:
            entries = _decision_run_state_entries_at(directory_fd)
        except ManualReconciliationRequired:
            raise
        except shots.ShotsError as exc:
            if not lock_created:
                raise
            raise ManualReconciliationRequired(
                "decision state could not be proven clean after permanent "
                "lock creation; manual reconciliation required"
            ) from exc
        if lock_created:
            # A state/claim predating the permanent lock cannot be distinguished
            # from deleted or partially restored exactly-once evidence.
            if entries:
                raise ManualReconciliationRequired(
                    "decision state predates its permanent lock; "
                    "execution state is ambiguous"
                )
            try:
                with _reserve_digest_lease_at(
                    directory_fd, "decision-run", state_sha256,
                ) as claim_created:
                    if not claim_created:
                        raise ManualReconciliationRequired(
                            "decision claim predates its permanent lock; "
                            "execution state is ambiguous"
                        )
                    raw = _canonical_bytes(state)
                    name = f"decision-run-{state_sha256}.json"
                    try:
                        state_lease = _write_decision_state_lease_at(
                            directory_fd, name, raw,
                        )
                        with state_lease:
                            _fsync_decision_state_directory(directory_fd)
                            try:
                                stored_entries = _decision_run_state_entries_at(
                                    directory_fd,
                                )
                            except ManualReconciliationRequired:
                                raise
                            except BaseException as exc:
                                raise ManualReconciliationRequired(
                                    "decision run state scan failed after "
                                    "durable creation; manual reconciliation "
                                    "required"
                                ) from exc
                            if (len(stored_entries) != 1
                                    or stored_entries[0][1] != state_sha256
                                    or _canonical_bytes(stored_entries[0][0])
                                    != raw):
                                raise ManualReconciliationRequired(
                                    "decision run state differs after durable "
                                    "creation; manual reconciliation required"
                                )
                            return _DecisionRunReservation(
                                MappingProxyType(dict(state)), state_sha256,
                                True,
                            )
                    except OSError as exc:
                        raise ManualReconciliationRequired(
                            "decision run state write needs manual reconciliation"
                        ) from exc
            except OSError as exc:
                raise ManualReconciliationRequired(
                    "decision run claim write needs manual reconciliation"
                ) from exc

        # Once the permanent lock exists, absence is a stop rather than an
        # invitation to recreate evidence and accidentally authorize a replay.
        claim_name = ".decision-run.claim"
        claim_raw = (state_sha256 + "\n").encode("ascii")
        try:
            with _durably_bind_decision_entry_at(
                directory_fd, claim_name, expected=claim_raw,
                label="immutable decision-run reservation",
                name_preobserved=True,
            ):
                entries = _decision_run_state_entries_at(directory_fd)
                if not entries:
                    raise ManualReconciliationRequired(
                        "decision run permanent lock has incomplete durable state; "
                        "execution state is ambiguous"
                    )
                stored, stored_sha256 = entries[0]
                if (stored_sha256 != state_sha256
                        or _canonical_bytes(stored) != _canonical_bytes(state)):
                    raise shots.LockMismatch(
                        "a different decision run is already reserved"
                    )
                stored_raw = _canonical_bytes(stored)
                stored_name = f"decision-run-{stored_sha256}.json"
                with _durably_bind_decision_entry_at(
                    directory_fd, stored_name, expected=stored_raw,
                    label="decision run state", name_preobserved=True,
                ):
                    _fsync_decision_state_directory(directory_fd)
                    try:
                        replay_entries = _decision_run_state_entries_at(
                            directory_fd,
                        )
                    except ManualReconciliationRequired:
                        raise
                    except BaseException as exc:
                        raise ManualReconciliationRequired(
                            "decision run state rescan failed during replay; "
                            "manual reconciliation required"
                        ) from exc
                    if replay_entries != entries:
                        raise ManualReconciliationRequired(
                            "decision run state changed during replay; manual "
                            "reconciliation required"
                        )
                    return _DecisionRunReservation(
                        MappingProxyType(dict(stored)), stored_sha256, False,
                    )
        except ManualReconciliationRequired as exc:
            if not isinstance(exc.__cause__, FileNotFoundError):
                raise
            raise ManualReconciliationRequired(
                "decision run permanent lock has incomplete durable state; "
                "execution state is ambiguous"
            ) from exc
        except FileNotFoundError as exc:
            raise ManualReconciliationRequired(
                "decision run permanent lock has incomplete durable state; "
                "execution state is ambiguous"
            ) from exc


def _native_family_paths() -> tuple[str, ...]:
    """Return the exact 157-file parent code family used by the preregistration."""
    names = _git_text(
        "ls-tree", "-r", "--name-only", _NATIVE_PARENT_COMMIT,
    ).splitlines()
    relatives = tuple(sorted(
        name for name in names
        if name.endswith(".py")
        and (name.startswith("epl/") or name.startswith("src/wcmodel/"))
        and not name.startswith("epl/tests/")
    ))
    if len(relatives) != _NATIVE_CODE_FAMILY_FILES:
        raise shots.LockMismatch(
            f"parent native family has {len(relatives)} files, expected "
            f"{_NATIVE_CODE_FAMILY_FILES}"
        )
    return relatives


def _verify_extracted_parent(root: Path,
                             family: Sequence[str]) -> None:
    expected_files = set(family) | set(_NATIVE_ARCHIVE_RESOURCES)
    observed_files = {
        path.relative_to(root).as_posix()
        for path in root.rglob("*") if path.is_file()
    }
    if observed_files != expected_files:
        raise shots.LockMismatch(
            "isolated parent archive file set differs from the exact code/config set"
        )
    walk = root / "epl" / "walkforward.py"
    fit = root / "epl" / "fit.py"
    if (shots.sha256_file(walk) != _NATIVE_WALKFORWARD_SHA256
            or shots.sha256_file(fit) != _NATIVE_FIT_SHA256):
        raise shots.LockMismatch("isolated parent walkforward/fit bytes differ")
    digest = hashlib.sha256()
    for relative in family:
        name = relative.encode("utf-8")
        blob = (root / relative).read_bytes()
        digest.update(len(name).to_bytes(8, "big")); digest.update(name)
        digest.update(len(blob).to_bytes(8, "big")); digest.update(blob)
    if digest.hexdigest() != _NATIVE_CODE_FAMILY_SHA256:
        raise shots.LockMismatch("isolated parent native-family digest differs")


def _materialize_native_parent(
    root: Path, *, workspace: "_NativeTemporaryLease",
) -> tuple[tuple[str, ...], "_NativeChildLease"]:
    """Extract only frozen code/config resources from the exact parent commit.

    The full repository archive would also expose unrelated sample/result files.
    Git therefore archives the exact 157-file native family plus five named
    non-code resources.  Raw match files are installed separately, after H,
    making the outcome-bearing exposure set independently checkable.
    """
    if root != workspace.path / "parent":
        _native_lease_refusal(workspace, "isolated parent path is not exact")
    _verify_native_temporary_lease(workspace)
    parent = _git_text(
        "rev-parse", f"{_NATIVE_PARENT_COMMIT}^{{commit}}",
    )
    tree = _git_text(
        "rev-parse", f"{_NATIVE_PARENT_COMMIT}^{{tree}}",
    )
    if parent != _NATIVE_PARENT_COMMIT or tree != _NATIVE_PARENT_TREE:
        raise shots.LockMismatch("exact native parent commit/tree is unavailable")
    family = _native_family_paths()
    paths_to_archive = (*family, *_NATIVE_ARCHIVE_RESOURCES)
    try:
        os.mkdir("parent", 0o700, dir_fd=workspace.descriptor)
    except OSError as exc:
        _native_lease_refusal(
            workspace, "isolated parent could not be exclusively created", exc,
        )
    parent_lease = _capture_native_child_lease(
        workspace, "parent", directory=True, label="parent/raw input root",
    )
    archive_name = "native-parent.tar"
    archive_writer = _create_native_direct_writer(
        workspace, archive_name, label="native parent archive",
    )
    try:
        result = subprocess.run(
            (str(_GIT_EXECUTABLE), "-C", str(_ROOT),
             "archive", "--format=tar",
             _NATIVE_PARENT_COMMIT, "--", *paths_to_archive),
            stdout=archive_writer, stderr=subprocess.PIPE,
            stdin=subprocess.DEVNULL, check=False, timeout=60,
            env=_git_environment(),
        )
    except (OSError, subprocess.SubprocessError) as exc:
        try:
            os.close(archive_writer)
        except OSError as close_exc:
            raise ManualReconciliationRequired(
                "native parent archive writer did not close after Git failed"
            ) from close_exc
        raise NativeWorkerIOFailure(
            "git archive of the exact native parent could not run"
        ) from exc
    archive_lease = _finalize_native_direct_writer(
        workspace, archive_name, archive_writer,
        label="native parent archive",
    )
    if result.returncode:
        raise NativeWorkerIOFailure(
            "git archive of the exact native parent failed: "
            + result.stderr.decode("utf-8", "replace").strip()
        )
    try:
        archive_stream = os.fdopen(os.dup(archive_lease.descriptor), "rb")
        with archive_stream, tarfile.open(fileobj=archive_stream, mode="r:") as archive:
            for member in archive:
                _verify_native_child_lease(workspace, parent_lease)
                relative = PurePosixPath(member.name)
                if (relative.is_absolute() or ".." in relative.parts
                        or not relative.parts):
                    raise shots.LockMismatch(
                        f"unsafe path in native parent archive: {member.name!r}"
                    )
                destination = root.joinpath(*relative.parts)
                if member.isdir():
                    destination.mkdir(parents=True, exist_ok=True)
                    _verify_native_child_lease(workspace, parent_lease)
                    continue
                if not member.isfile():
                    raise shots.LockMismatch(
                        f"non-regular member in native parent archive: {member.name!r}"
                    )
                destination.parent.mkdir(parents=True, exist_ok=True)
                _verify_native_child_lease(workspace, parent_lease)
                source = archive.extractfile(member)
                if source is None:
                    raise NativeWorkerIOFailure(
                        f"could not read native parent member: {member.name!r}"
                    )
                with source, destination.open("xb") as output:
                    shutil.copyfileobj(source, output)
                _verify_native_child_lease(workspace, parent_lease)
    except (OSError, EOFError, tarfile.TarError) as exc:
        raise NativeWorkerIOFailure(
            "native parent archive extraction did not complete"
        ) from exc
    _verify_native_child_lease(workspace, archive_lease)
    _verify_native_child_lease(workspace, parent_lease)
    try:
        _verify_extracted_parent(root, family)
    except shots.LockMismatch:
        raise
    except OSError as exc:
        raise NativeWorkerIOFailure(
            "extracted native parent could not be verified"
        ) from exc
    _verify_native_child_lease(workspace, parent_lease)
    return family, parent_lease


def _install_native_raw_inputs(
    parent_root: Path, *, workspace: "_NativeTemporaryLease",
    parent_lease: "_NativeChildLease",
) -> tuple[dict[str, Any], ...]:
    """Copy exactly burn-in plus four training raw files into the isolate.

    This function is called only by the post-H private generator.  No decision
    season is named, globbed, scanned, or copied, and the isolated raw directory
    must be absent before these five files are installed.
    """
    if parent_root != parent_lease.path or not parent_lease.directory:
        _native_lease_refusal(workspace, "isolated raw parent identity differs")
    _verify_native_child_lease(workspace, parent_lease)
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    data_descriptor = epl_descriptor = raw_descriptor = -1
    raw_root = parent_root / "data" / "epl" / "raw"
    try:
        os.mkdir("data", 0o700, dir_fd=parent_lease.descriptor)
        data_descriptor = os.open(
            "data", directory_flags, dir_fd=parent_lease.descriptor,
        )
        os.mkdir("epl", 0o700, dir_fd=data_descriptor)
        epl_descriptor = os.open(
            "epl", directory_flags, dir_fd=data_descriptor,
        )
        os.mkdir("raw", 0o700, dir_fd=epl_descriptor)
        raw_descriptor = os.open(
            "raw", directory_flags, dir_fd=epl_descriptor,
        )
        raw_identity = _native_lease_identity(os.fstat(raw_descriptor))
        named_raw = os.stat(raw_root, follow_symlinks=False)
        if (not stat.S_ISDIR(named_raw.st_mode)
                or _native_lease_identity(named_raw) != raw_identity):
            _native_lease_refusal(
                workspace, "isolated raw root identity differs after create",
            )
        expected = _native_raw_digests()
        records: list[dict[str, Any]] = []
        for name in _NATIVE_RAW_NAMES:
            source = _ROOT / "data" / "epl" / "raw" / name
            raw = _read_regular_snapshot(
                source, label=f"pinned native raw input {name}",
            )
            digest = expected[name]
            if hashlib.sha256(raw).hexdigest() != digest:
                raise shots.SourceDigestMismatch(
                    f"pinned native raw input differs: {name}"
                )
            destination_descriptor = reader = -1
            try:
                destination_descriptor = os.open(
                    name,
                    os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0),
                    0o600, dir_fd=raw_descriptor,
                )
                _write_native_descriptor(
                    destination_descriptor, raw,
                    label=f"isolated native raw input {name}",
                )
                os.fchmod(destination_descriptor, 0o400)
                os.fsync(destination_descriptor)
                opened = os.fstat(destination_descriptor)
                file_identity = _native_file_lease_identity(opened)
                anchored = os.stat(
                    name, dir_fd=raw_descriptor, follow_symlinks=False,
                )
                named = os.stat(raw_root / name, follow_symlinks=False)
                if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                        or _native_file_lease_identity(anchored) != file_identity
                        or _native_file_lease_identity(named) != file_identity):
                    _native_lease_refusal(
                        workspace,
                        f"isolated native raw input {name} identity differs",
                    )
                reader = os.open(
                    name,
                    os.O_RDONLY | os.O_NOFOLLOW
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=raw_descriptor,
                )
                if _native_file_lease_identity(os.fstat(reader)) != file_identity:
                    _native_lease_refusal(
                        workspace,
                        f"isolated native raw input {name} reader differs",
                    )
                copied = bytearray()
                while len(copied) < len(raw):
                    chunk = os.read(reader, min(1_048_576, len(raw) - len(copied)))
                    if not chunk:
                        break
                    copied.extend(chunk)
                if bytes(copied) != raw or os.read(reader, 1):
                    _native_lease_refusal(
                        workspace,
                        f"isolated native raw input {name} readback differs",
                    )
            except NativeWorkerIOFailure:
                raise
            except OSError as exc:
                _native_lease_refusal(
                    workspace,
                    f"isolated native raw input {name} exclusive create failed",
                    exc,
                )
            finally:
                if reader >= 0:
                    os.close(reader)
                if destination_descriptor >= 0:
                    os.close(destination_descriptor)
            records.append({
                "path": f"data/epl/raw/{name}",
                "sha256": digest,
                "bytes": len(raw),
            })
        observed = sorted(os.listdir(raw_descriptor))
        if observed != sorted(_NATIVE_RAW_NAMES):
            _native_lease_refusal(
                workspace, "isolated raw exposure is not exactly five files",
            )
        for name in observed:
            if not stat.S_ISREG(os.stat(
                name, dir_fd=raw_descriptor, follow_symlinks=False,
            ).st_mode):
                _native_lease_refusal(
                    workspace, "isolated raw exposure contains a non-file",
                )
        if (_native_lease_identity(os.fstat(raw_descriptor)) != raw_identity
                or _native_lease_identity(os.stat(
                    raw_root, follow_symlinks=False,
                )) != raw_identity):
            _native_lease_refusal(workspace, "isolated raw root identity differs")
        _verify_native_child_lease(workspace, parent_lease)
        return tuple(records)
    except (NativeWorkerIOFailure, shots.SourceDigestMismatch):
        raise
    except OSError as exc:
        _native_lease_refusal(
            workspace, "isolated native raw tree setup was refused", exc,
        )
    finally:
        for descriptor in (raw_descriptor, epl_descriptor, data_descriptor):
            if descriptor >= 0:
                os.close(descriptor)


def _training_schedule_blocks(
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[tuple[dict[str, Any], ...], ...]:
    blocks: list[list[dict[str, Any]]] = []
    for row in schedule:
        record = dict(row)
        if not blocks or blocks[-1][0]["block"] != record["block"]:
            blocks.append([])
        blocks[-1].append(record)
    if len(blocks) != 142 or sum(map(len, blocks)) != shots.TRAINING_ROWS:
        raise shots.FixtureSetMismatch(
            "training schedule is not exactly 142 contiguous blocks / 1,520 rows"
        )
    return tuple(tuple(block) for block in blocks)


def _fixed_tool_output(executable: Path, *args: str) -> str:
    if not executable.is_file() or not os.access(executable, os.X_OK):
        raise NativeWorkerSandboxStop(f"required tool is unavailable: {executable}")
    try:
        result = subprocess.run(
            (str(executable), *args), stdin=subprocess.DEVNULL,
            capture_output=True, check=False, timeout=30,
            env={"LANG": "C", "LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerSandboxStop(
            f"required tool failed: {executable.name}"
        ) from exc
    if result.returncode:
        raise NativeWorkerSandboxStop(
            f"required tool refused: {executable.name}"
        )
    return result.stdout.decode("utf-8", "strict").strip()


def _path_beneath(path: Path, root: Path) -> bool:
    try:
        path.relative_to(root)
    except ValueError:
        return False
    return True


def _approved_native_developer_path(path: Path, *, label: str) -> Path:
    """Resolve one compiler/SDK path inside the fixed disjoint CLT root."""
    developer_logical = Path(
        os.path.abspath(os.fspath(_NATIVE_DEVELOPER_ROOT))
    )
    try:
        developer_resolved = developer_logical.resolve(strict=True)
    except OSError as exc:
        raise NativeWorkerSandboxStop(
            "approved native developer root is unavailable"
        ) from exc
    if (developer_logical != developer_resolved
            or not developer_resolved.is_dir()):
        raise NativeWorkerSandboxStop(
            "approved native developer root is not one regular directory"
        )
    protected = (_ROOT, _ARTIFACT_ROOT, _NATIVE_TEMP_PARENT)
    if any(
        developer_resolved == root
        or _path_beneath(developer_resolved, root)
        or _path_beneath(root, developer_resolved)
        for root in protected
    ):
        raise NativeWorkerSandboxStop(
            "approved native developer root overlaps protected work paths"
        )
    logical = Path(os.path.abspath(os.fspath(path)))
    try:
        resolved = logical.resolve(strict=True)
    except OSError as exc:
        raise NativeWorkerSandboxStop(
            f"selected native {label} cannot resolve"
        ) from exc
    if (not _path_beneath(logical, developer_logical)
            or not _path_beneath(resolved, developer_resolved)):
        raise NativeWorkerSandboxStop(
            f"selected native {label} escapes the approved developer root"
        )
    return resolved


def _native_runtime_closure(
    *, site_packages: Path, python_runtime: Path,
    runtime_read_paths: Sequence[str], process_exec_paths: Sequence[str],
) -> dict[str, Any]:
    """Hash every mutable byte tree the worker may read or execute.

    Broad macOS system trees are not exposed.  Every allowed byte tree is
    represented by an lstat-based digest; exact system executables/loadable
    images are hashed individually.  Symlink text and its resolved target are
    both bound, and a link escaping all declared roots refuses.

    The structural snapshot is checked again after the parallel file reads so
    ordinary directory or symlink races fail closed.  This is not an
    adversarial same-UID snapshot primitive: a hostile mutate-and-restore
    (A-B-A) between observations still requires an immutable filesystem
    snapshot or equivalent external isolation.
    """

    def lstat_identity(info: os.stat_result) -> tuple[int, ...]:
        return (
            int(info.st_dev), int(info.st_ino), int(info.st_mode),
            int(info.st_nlink), int(info.st_uid), int(info.st_gid),
            int(info.st_size), int(info.st_mtime_ns), int(info.st_ctime_ns),
        )

    def path_binding(
        logical: Path,
    ) -> tuple[Path, list[dict[str, str]], tuple[Any, ...]]:
        """Capture a logical link chain and its resolved target identity."""
        absolute = Path(os.path.abspath(os.fspath(logical)))
        chain: list[dict[str, str]] = []
        link_identities: list[tuple[Any, ...]] = []
        cursor = Path(absolute.anchor)
        for part in absolute.parts[1:]:
            cursor = cursor / part
            try:
                before = cursor.lstat()
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime path component cannot be stated: {cursor}"
                ) from exc
            if not stat.S_ISLNK(before.st_mode):
                continue
            try:
                target = os.readlink(cursor)
                resolved_component = cursor.resolve(strict=True)
                after = cursor.lstat()
                target_after = os.readlink(cursor)
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime symlink cannot be resolved: {cursor}"
                ) from exc
            if (lstat_identity(before) != lstat_identity(after)
                    or target_after != target):
                raise NativeWorkerSandboxStop(
                    f"runtime symlink changed while binding: {cursor}"
                )
            chain.append({
                "path": str(cursor), "target": target,
                "resolved": str(resolved_component),
            })
            link_identities.append((
                str(cursor), lstat_identity(after), target,
                str(resolved_component),
            ))
        try:
            resolved = absolute.resolve(strict=True)
            target_identity = lstat_identity(resolved.lstat())
        except OSError as exc:
            raise NativeWorkerSandboxStop(
                f"runtime path cannot be resolved: {absolute}"
            ) from exc
        private = (
            str(absolute), str(resolved), tuple(link_identities), target_identity,
        )
        return resolved, chain, private

    sealed_roots = tuple(Path(path) for path in _NATIVE_SEALED_READ_ROOTS)
    sdk_path_text = _fixed_tool_output(Path("/usr/bin/xcrun"), "--show-sdk-path")
    sdk_path = Path(sdk_path_text)
    if not sdk_path.is_absolute() or not sdk_path.is_dir():
        raise NativeWorkerSandboxStop("active SDK is unavailable")
    sdk_resolved, sdk_chain, sdk_binding = path_binding(sdk_path)
    logical_roots: list[Path] = [
        Path(site_packages), Path(python_runtime), sdk_path,
    ]
    for value in runtime_read_paths:
        candidate = Path(str(value))
        absolute = Path(os.path.abspath(os.fspath(candidate)))
        if any(absolute == root or _path_beneath(absolute, root)
               for root in sealed_roots):
            continue
        if absolute not in logical_roots:
            logical_roots.append(absolute)

    root_specs: list[dict[str, Any]] = []
    root_bindings: dict[str, tuple[Any, ...]] = {}
    for logical in logical_roots:
        absolute = Path(os.path.abspath(os.fspath(logical)))
        if not absolute.exists() and not absolute.is_symlink():
            raise NativeWorkerSandboxStop(
                f"runtime closure path is unavailable: {absolute}"
            )
        resolved, chain, binding = path_binding(absolute)
        root_bindings[str(absolute)] = binding
        root_specs.append({
            "logical_path": str(absolute), "resolved_path": str(resolved),
            "link_chain": chain,
        })

    # A broad declared root already covers a nested physical tree.  Preserve a
    # logical alias when it has a symlink chain (the alias identity matters),
    # but avoid hashing ordinary nested roots such as site-packages twice.
    root_specs = [
        spec for spec in root_specs
        if spec["link_chain"] or not any(
            Path(spec["resolved_path"]) != Path(other["resolved_path"])
            and _path_beneath(
                Path(spec["resolved_path"]), Path(other["resolved_path"])
            )
            for other in root_specs
        )
    ]

    allowed_mutable = tuple(
        Path(spec["resolved_path"]) for spec in root_specs
    )

    def target_is_declared(target: Path) -> bool:
        return any(target == root or _path_beneath(target, root)
                   for root in (*allowed_mutable, *sealed_roots))

    def file_digest(path: Path, before: os.stat_result) -> tuple[str, int]:
        try:
            digest = shots.sha256_file(path)
            after = path.stat(follow_symlinks=False)
        except OSError as exc:
            raise NativeWorkerSandboxStop(
                f"runtime file could not be hashed: {path}"
            ) from exc
        identity_before = (
            before.st_dev, before.st_ino, before.st_mode,
            before.st_size, before.st_mtime_ns,
        )
        identity_after = (
            after.st_dev, after.st_ino, after.st_mode,
            after.st_size, after.st_mtime_ns,
        )
        if identity_before != identity_after:
            raise NativeWorkerSandboxStop(
                f"runtime file changed while hashing: {path}"
            )
        return digest, int(after.st_size)

    def tree_record(resolved_root: Path) -> dict[str, Any]:
        structural: list[dict[str, Any]] = []
        pending_files: list[tuple[str, Path, os.stat_result]] = []
        directory_snapshots: list[
            tuple[Path, tuple[int, ...], tuple[str, ...]]
        ] = []
        symlink_snapshots: list[
            tuple[Path, tuple[int, ...], str, str | None, str]
        ] = []

        def visit(path: Path, relative: str) -> None:
            try:
                info = path.lstat()
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime tree entry cannot be stated: {path}"
                ) from exc
            mode = stat.S_IMODE(info.st_mode)
            if stat.S_ISLNK(info.st_mode):
                try:
                    raw_target = os.readlink(path)
                except OSError as exc:
                    raise NativeWorkerSandboxStop(
                        f"runtime tree link cannot be read: {path}"
                    ) from exc
                try:
                    target = path.resolve(strict=True)
                except FileNotFoundError:
                    symlink_snapshots.append((
                        path, lstat_identity(info), raw_target, None,
                        "dangling",
                    ))
                    structural.append({
                        "path": relative, "kind": "symlink", "mode": mode,
                        "target": raw_target, "resolved": None,
                        "target_state": "dangling",
                    })
                    return
                except OSError as exc:
                    raise NativeWorkerSandboxStop(
                        f"runtime tree link cannot resolve: {path}"
                    ) from exc
                if not target_is_declared(target):
                    raise NativeWorkerSandboxStop(
                        f"runtime tree symlink escapes declared roots: {path}"
                    )
                symlink_snapshots.append((
                    path, lstat_identity(info), raw_target, str(target),
                    "resolved",
                ))
                structural.append({
                    "path": relative, "kind": "symlink", "mode": mode,
                    "target": raw_target, "resolved": str(target),
                    "target_state": "resolved",
                })
                return
            if stat.S_ISREG(info.st_mode):
                pending_files.append((relative, path, info))
                return
            if not stat.S_ISDIR(info.st_mode):
                raise NativeWorkerSandboxStop(
                    f"runtime tree contains a special file: {path}"
                )
            structural.append({
                "path": relative, "kind": "directory", "mode": mode,
            })
            try:
                with os.scandir(path) as children:
                    entries = sorted(children, key=lambda entry: entry.name)
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime directory cannot be scanned: {path}"
                ) from exc
            directory_snapshots.append((
                path, lstat_identity(info), tuple(entry.name for entry in entries),
            ))
            for entry in entries:
                child_relative = (
                    entry.name if relative == "."
                    else f"{relative}/{entry.name}"
                )
                visit(Path(entry.path), child_relative)

        visit(resolved_root, ".")
        file_records: list[dict[str, Any]] = []
        workers = min(8, max(1, len(pending_files)))
        with concurrent.futures.ThreadPoolExecutor(max_workers=workers) as pool:
            futures = [
                pool.submit(file_digest, path, before)
                for _, path, before in pending_files
            ]
            for (relative, _, before), future in zip(
                pending_files, futures, strict=True,
            ):
                digest, size = future.result()
                file_records.append({
                    "path": relative, "kind": "file",
                    "mode": stat.S_IMODE(before.st_mode),
                    "bytes": size, "sha256": digest,
                })

        for (path, identity_before, raw_target_before, resolved_before,
             target_state_before) in symlink_snapshots:
            try:
                info = path.lstat()
                if (not stat.S_ISLNK(info.st_mode)
                        or lstat_identity(info) != identity_before
                        or os.readlink(path) != raw_target_before):
                    raise NativeWorkerSandboxStop(
                        f"runtime symlink changed while hashing: {path}"
                    )
                try:
                    resolved_after: str | None = str(path.resolve(strict=True))
                    target_state_after = "resolved"
                except FileNotFoundError:
                    resolved_after = None
                    target_state_after = "dangling"
            except NativeWorkerSandboxStop:
                raise
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime symlink changed while hashing: {path}"
                ) from exc
            if (target_state_after != target_state_before
                    or resolved_after != resolved_before):
                raise NativeWorkerSandboxStop(
                    f"runtime symlink resolution changed while hashing: {path}"
                )

        for path, identity_before, members_before in directory_snapshots:
            try:
                info_before_scan = path.lstat()
                if (not stat.S_ISDIR(info_before_scan.st_mode)
                        or lstat_identity(info_before_scan) != identity_before):
                    raise NativeWorkerSandboxStop(
                        f"runtime directory changed while hashing: {path}"
                    )
                with os.scandir(path) as entries:
                    members_after = tuple(sorted(entry.name for entry in entries))
                info_after_scan = path.lstat()
            except NativeWorkerSandboxStop:
                raise
            except OSError as exc:
                raise NativeWorkerSandboxStop(
                    f"runtime directory changed while hashing: {path}"
                ) from exc
            if lstat_identity(info_after_scan) != identity_before:
                raise NativeWorkerSandboxStop(
                    f"runtime directory changed while hashing: {path}"
                )
            if members_after != members_before:
                raise NativeWorkerSandboxStop(
                    f"runtime directory membership changed while hashing: {path}"
                )
        records = sorted((*structural, *file_records), key=lambda item: item["path"])
        digest = hashlib.sha256(
            (_NATIVE_RUNTIME_TREE_SCHEMA + "\n").encode("ascii")
        )
        for record in records:
            digest.update(_canonical_bytes(record))
        return {
            "tree_sha256": digest.hexdigest(),
            "files": sum(record["kind"] == "file" for record in records),
            "directories": sum(
                record["kind"] == "directory" for record in records
            ),
            "symlinks": sum(
                record["kind"] == "symlink" for record in records
            ),
            "bytes": sum(
                int(record.get("bytes", 0)) for record in records
            ),
        }

    tree_cache: dict[str, dict[str, Any]] = {}
    mutable_roots: list[dict[str, Any]] = []
    for spec in root_specs:
        resolved_name = spec["resolved_path"]
        if resolved_name not in tree_cache:
            tree_cache[resolved_name] = tree_record(Path(resolved_name))
        mutable_roots.append({**spec, **tree_cache[resolved_name]})

    executable_records: list[dict[str, Any]] = []
    executable_bindings: dict[str, tuple[Any, ...]] = {}
    executable_paths = [
        *(Path(path) for path in process_exec_paths),
        _NATIVE_SANDBOX_EXECUTABLE,
        _NATIVE_RSS_MONITOR_EXECUTABLE,
    ]
    seen_exec: set[str] = set()
    for executable in executable_paths:
        logical = Path(os.path.abspath(os.fspath(executable)))
        try:
            resolved, chain, binding = path_binding(logical)
            info = resolved.stat(follow_symlinks=False)
        except OSError as exc:
            raise NativeWorkerSandboxStop(
                f"runtime executable is unavailable: {logical}"
            ) from exc
        if not stat.S_ISREG(info.st_mode) or not os.access(resolved, os.X_OK):
            raise NativeWorkerSandboxStop(
                f"runtime executable is not a regular executable: {logical}"
            )
        key = str(logical)
        if key in seen_exec:
            continue
        seen_exec.add(key)
        executable_bindings[key] = binding
        digest, size = file_digest(resolved, info)
        executable_records.append({
            "logical_path": key, "resolved_path": str(resolved),
            "link_chain": chain,
            "mode": stat.S_IMODE(info.st_mode), "bytes": size,
            "sha256": digest,
        })

    root_mount_lines = [
        line for line in _fixed_tool_output(Path("/sbin/mount")).splitlines()
        if " on / " in f" {line} "
    ]
    if len(root_mount_lines) != 1:
        raise NativeWorkerSandboxStop("root filesystem mount is ambiguous")
    root_mount = root_mount_lines[0]
    if ("(apfs," not in root_mount or "sealed" not in root_mount
            or "read-only" not in root_mount):
        raise NativeWorkerSandboxStop(
            "macOS system runtime is not on a sealed read-only APFS root"
        )
    platform_receipt = {
        "architecture": _fixed_tool_output(Path("/usr/bin/uname"), "-m"),
        "kernel_release": _fixed_tool_output(Path("/usr/bin/uname"), "-r"),
        "sw_vers": _fixed_tool_output(Path("/usr/bin/sw_vers")),
        "root_mount": root_mount,
        "sdk_logical_path": sdk_path_text,
        "sdk_resolved_path": str(sdk_resolved),
        "sdk_link_chain": sdk_chain,
        "clang_version": _fixed_tool_output(Path("/usr/bin/clang"), "--version"),
    }
    for logical_name, expected in root_bindings.items():
        if path_binding(Path(logical_name))[2] != expected:
            raise NativeWorkerSandboxStop(
                f"runtime logical root changed after hashing: {logical_name}"
            )
    for logical_name, expected in executable_bindings.items():
        if path_binding(Path(logical_name))[2] != expected:
            raise NativeWorkerSandboxStop(
                f"runtime executable changed after hashing: {logical_name}"
            )
    if path_binding(sdk_path)[2] != sdk_binding:
        raise NativeWorkerSandboxStop("active SDK changed after hashing")
    payload = {
        "schema": _NATIVE_RUNTIME_CLOSURE_SCHEMA,
        "tree_digest_schema": _NATIVE_RUNTIME_TREE_SCHEMA,
        "sealed_read_roots": list(_NATIVE_SEALED_READ_ROOTS),
        "mutable_roots": mutable_roots,
        "executables": executable_records,
        "platform": platform_receipt,
        "file_count": sum(root["files"] for root in tree_cache.values()),
        "directory_count": sum(
            root["directories"] for root in tree_cache.values()
        ),
        "symlink_count": sum(root["symlinks"] for root in tree_cache.values()),
        "bytes": sum(root["bytes"] for root in tree_cache.values()),
    }
    return {
        **payload,
        "sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }


def _native_sandbox_contract(
    *, frozen_runtime_lock: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    """Return the stable deny-by-default worker capability contract."""
    if (not _NATIVE_RSS_MONITOR_EXECUTABLE.is_file()
            or not os.access(_NATIVE_RSS_MONITOR_EXECUTABLE, os.X_OK)):
        raise NativeWorkerSandboxStop(
            "native resident-memory monitor is unavailable"
        )
    launcher = (_ROOT / ".venv" / "bin" / "python").absolute()
    if (launcher.is_symlink() and not launcher.exists()) or not launcher.is_file():
        raise NativeWorkerSandboxStop("repo .venv Python launcher is unavailable")
    resolved = launcher.resolve()
    if not os.access(launcher, os.X_OK):
        raise NativeWorkerSandboxStop("repo .venv Python launcher is not executable")
    abi_match = re.search(r"/Versions/([0-9]+\.[0-9]+)/", str(resolved))
    if abi_match is None:
        raise NativeWorkerSandboxStop("repo .venv Python ABI is not identifiable")
    python_abi = abi_match.group(1)
    site_packages = (
        _ROOT / ".venv" / "lib"
        / f"python{python_abi}"
        / "site-packages"
    ).absolute()
    if not site_packages.is_dir():
        raise NativeWorkerSandboxStop("repo .venv site-packages is unavailable")
    python_runtime = resolved.parents[1]
    # Homebrew's framework stdlib contains a site-packages symlink whose
    # target lives elsewhere in the same versioned formula.  Bind and allow
    # that exact formula tree so the runtime closure covers the target bytes;
    # never follow an unbound escape merely because it is reachable by link.
    python_formula_root = resolved.parents[5]
    python_app = (
        python_runtime / "Resources" / "Python.app" / "Contents"
        / "MacOS" / "Python"
    )
    if not python_app.is_file() or not os.access(python_app, os.X_OK):
        raise NativeWorkerSandboxStop(
            "Homebrew Python application executable is unavailable"
        )
    candidates = [
        _ROOT / ".venv",
        python_runtime,
        python_formula_root,
        _NATIVE_DEVELOPER_ROOT,
    ]
    for formula in ("openssl@3", "sqlite", "xz", "mpdecimal"):
        link = Path("/opt/homebrew/opt") / formula
        if link.exists():
            candidates.extend((link, link.resolve()))
    runtime_paths: list[str] = []
    for candidate in candidates:
        absolute = candidate.absolute()
        if absolute.exists() and str(absolute) not in runtime_paths:
            runtime_paths.append(str(absolute))
    if (str((_ROOT / ".venv").absolute()) not in runtime_paths
            or str(python_runtime) not in runtime_paths):
        raise NativeWorkerSandboxStop("native Python runtime closure is unavailable")
    selected_tools = {
        name: Path(_fixed_tool_output(Path("/usr/bin/xcrun"), "--find", name))
        for name in ("clang", "clang++", "ld", "ar", "strip")
    }
    for name, path in selected_tools.items():
        resolved_tool = _approved_native_developer_path(
            path, label=f"compiler tool {name}",
        )
        if (not path.is_file() or not stat.S_ISREG(resolved_tool.lstat().st_mode)
                or not os.access(path, os.X_OK)):
            raise NativeWorkerSandboxStop(
                "selected native compiler tools are unavailable"
            )
    sdk_root = Path(
        _fixed_tool_output(Path("/usr/bin/xcrun"), "--show-sdk-path")
    )
    resolved_sdk = _approved_native_developer_path(
        sdk_root, label="SDK",
    )
    if not sdk_root.is_dir() or not resolved_sdk.is_dir():
        raise NativeWorkerSandboxStop("selected native SDK is unavailable")
    for sdk_path in (sdk_root.absolute(), sdk_root.resolve(strict=True)):
        if str(sdk_path) not in runtime_paths:
            runtime_paths.append(str(sdk_path))
    process_exec_candidates = (
        launcher, resolved, python_app,
        Path("/usr/bin/clang"), Path("/usr/bin/clang++"),
        Path("/usr/bin/xcrun"), Path("/usr/bin/ld"), Path("/usr/bin/as"),
        Path("/usr/bin/ar"), Path("/usr/bin/strip"),
        *selected_tools.values(),
        *_NATIVE_SYSTEM_LOADABLES,
    )
    if any(not path.is_file() or not os.access(path, os.X_OK)
           for path in _NATIVE_SYSTEM_LOADABLES):
        raise NativeWorkerSandboxStop(
            "required exact system loadable image is unavailable"
        )
    process_exec_paths = [
        str(path.absolute()) for path in process_exec_candidates
        if path.exists() and os.access(path, os.X_OK)
    ]
    if frozen_runtime_lock is None:
        runtime_closure = _native_runtime_closure(
            site_packages=site_packages, python_runtime=python_runtime,
            runtime_read_paths=runtime_paths,
            process_exec_paths=process_exec_paths,
        )
    else:
        try:
            shots._validate_native_runtime_lock(frozen_runtime_lock)
        except shots.LockMismatch as exc:
            raise NativeWorkerSandboxStop(str(exc)) from exc
        runtime_closure = json.loads(json.dumps(frozen_runtime_lock))
    environment_keys = (
        "CC", "CXX", "EPL_SHOTS_PARENT_ROOT", "EPL_SHOTS_REQUEST",
        "EPL_SHOTS_PYTHON_ABI", "EPL_SHOTS_RUNTIME_ROOT",
        "EPL_SHOTS_SITE_PACKAGES", "HOME", "LANG",
        "LC_ALL", "MPLCONFIGDIR",
        "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "PATH",
        "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTENSOR_FLAGS",
        "SDKROOT", "TMPDIR", "VECLIB_MAXIMUM_THREADS", "XDG_CACHE_HOME",
    )
    contract = {
        "schema": _NATIVE_SANDBOX_SCHEMA,
        "sandbox_executable": str(_NATIVE_SANDBOX_EXECUTABLE),
        "python_launcher": str(launcher),
        "python_resolved": str(resolved),
        "python_sha256": shots.sha256_file(resolved),
        "python_abi": python_abi,
        "site_packages": str(site_packages),
        "compiler_paths": {
            name: str(path.absolute()) for name, path in selected_tools.items()
        },
        "sdk_root": str(sdk_root.absolute()),
        "python_flags": list(_NATIVE_WORKER_FLAGS),
        "runtime_read_paths": runtime_paths,
        "process_exec_paths": process_exec_paths,
        "file_read_metadata": "allowlisted_paths_and_ancestors",
        "path_resolution_literals": list(_NATIVE_PATH_RESOLUTION_LITERALS),
        "runtime_closure": runtime_closure,
        "temporary_read_roles": ["parent_archive", "request", "runtime"],
        "temporary_write_roles": ["runtime"],
        "network": "deny",
        "inherit_environment": False,
        "environment_keys": list(environment_keys),
        "resource_limits": {
            "cpu_seconds": _NATIVE_CPU_LIMIT_SECONDS,
            "file_bytes": _NATIVE_FILE_LIMIT_BYTES,
            "nofile": _NATIVE_NOFILE_LIMIT,
            # macOS processes reserve very large sparse virtual mappings, so
            # RLIMIT_AS is neither a usable nor an honest resident-memory cap.
            # RSS is instead sampled and enforced across the isolated worker
            # process group by the parent.
            "address_space_bytes": None,
            "resident_memory_scope": "process_group_sampled_rss",
            "resident_memory_bytes": _NATIVE_RSS_LIMIT_BYTES,
            "resident_memory_poll_seconds": _NATIVE_RSS_POLL_SECONDS,
            "resident_memory_monitor": str(_NATIVE_RSS_MONITOR_EXECUTABLE),
            "runtime_tree_bytes": _NATIVE_RUNTIME_MAX_BYTES,
            "runtime_tree_files": _NATIVE_RUNTIME_MAX_FILES,
            "runtime_tree_directories": _NATIVE_RUNTIME_MAX_DIRECTORIES,
            "runtime_tree_entries": _NATIVE_RUNTIME_MAX_ENTRIES,
        },
    }
    _validate_native_sandbox_contract_shape(contract)
    return contract


def _native_sandbox_contract_sha256(contract: Mapping[str, Any]) -> str:
    return hashlib.sha256(_canonical_bytes(contract)).hexdigest()


def _validate_native_sandbox_contract_shape(
    contract: Mapping[str, Any], *, resolve_live_paths: bool = True,
) -> None:
    fields = {
        "schema", "sandbox_executable", "python_launcher", "python_resolved",
        "python_sha256", "python_abi", "site_packages", "compiler_paths",
        "sdk_root", "python_flags", "runtime_read_paths",
        "process_exec_paths", "file_read_metadata",
        "path_resolution_literals", "runtime_closure",
        "temporary_read_roles", "temporary_write_roles", "network",
        "inherit_environment", "environment_keys", "resource_limits",
    }
    if not isinstance(contract, Mapping) or set(contract) != fields:
        raise NativeWorkerSandboxStop("native sandbox contract fields differ")
    try:
        shots._validate_native_runtime_lock(contract["runtime_closure"])
    except shots.LockMismatch as exc:
        raise NativeWorkerSandboxStop(str(exc)) from exc
    compiler_paths = contract["compiler_paths"]
    resource_limits = contract["resource_limits"]
    path_lists = (
        contract["runtime_read_paths"], contract["process_exec_paths"],
    )
    if (contract["schema"] != _NATIVE_SANDBOX_SCHEMA
            or contract["sandbox_executable"]
                != str(_NATIVE_SANDBOX_EXECUTABLE)
            or not isinstance(contract["python_launcher"], str)
            or not Path(contract["python_launcher"]).is_absolute()
            or not isinstance(contract["python_resolved"], str)
            or not Path(contract["python_resolved"]).is_absolute()
            or not isinstance(contract["python_sha256"], str)
            or not _HEX64.fullmatch(contract["python_sha256"])
            or not isinstance(contract["python_abi"], str)
            or not re.fullmatch(r"[0-9]+\.[0-9]+", contract["python_abi"])
            or not isinstance(contract["site_packages"], str)
            or not Path(contract["site_packages"]).is_absolute()
            or not isinstance(compiler_paths, Mapping)
            or set(compiler_paths) != {"clang", "clang++", "ld", "ar", "strip"}
            or any(not isinstance(path, str) or not Path(path).is_absolute()
                   for path in compiler_paths.values())
            or not isinstance(contract["sdk_root"], str)
            or not Path(contract["sdk_root"]).is_absolute()
            or contract["python_flags"] != list(_NATIVE_WORKER_FLAGS)
            or any(not isinstance(values, list) or not values
                   or len(values) != len(set(values))
                   or any(not isinstance(path, str)
                          or not Path(path).is_absolute() for path in values)
                   for values in path_lists)
            or contract["file_read_metadata"]
                != "allowlisted_paths_and_ancestors"
            or contract["path_resolution_literals"]
                != list(_NATIVE_PATH_RESOLUTION_LITERALS)
            or contract["temporary_read_roles"]
                != ["parent_archive", "request", "runtime"]
            or contract["temporary_write_roles"] != ["runtime"]
            or contract["network"] != "deny"
            or contract["inherit_environment"] is not False
            or contract["environment_keys"] != [
                "CC", "CXX", "EPL_SHOTS_PARENT_ROOT", "EPL_SHOTS_REQUEST",
                "EPL_SHOTS_PYTHON_ABI", "EPL_SHOTS_RUNTIME_ROOT",
                "EPL_SHOTS_SITE_PACKAGES", "HOME", "LANG", "LC_ALL",
                "MPLCONFIGDIR",
                "OPENBLAS_NUM_THREADS", "OMP_NUM_THREADS", "PATH",
                "PYTHONHASHSEED", "PYTHONNOUSERSITE", "PYTENSOR_FLAGS",
                "SDKROOT", "TMPDIR", "VECLIB_MAXIMUM_THREADS",
                "XDG_CACHE_HOME",
            ]
            or not isinstance(resource_limits, Mapping)
            or resource_limits != {
                "cpu_seconds": _NATIVE_CPU_LIMIT_SECONDS,
                "file_bytes": _NATIVE_FILE_LIMIT_BYTES,
                "nofile": _NATIVE_NOFILE_LIMIT,
                "address_space_bytes": None,
                "resident_memory_scope": "process_group_sampled_rss",
                "resident_memory_bytes": _NATIVE_RSS_LIMIT_BYTES,
                "resident_memory_poll_seconds": _NATIVE_RSS_POLL_SECONDS,
                "resident_memory_monitor": str(
                    _NATIVE_RSS_MONITOR_EXECUTABLE
                ),
                "runtime_tree_bytes": _NATIVE_RUNTIME_MAX_BYTES,
                "runtime_tree_files": _NATIVE_RUNTIME_MAX_FILES,
                "runtime_tree_directories": _NATIVE_RUNTIME_MAX_DIRECTORIES,
                "runtime_tree_entries": _NATIVE_RUNTIME_MAX_ENTRIES,
            }):
        raise NativeWorkerSandboxStop("native sandbox contract is malformed")
    closure = contract["runtime_closure"]
    platform = closure["platform"]
    executable_records = closure["executables"]
    executable_by_logical = {
        record["logical_path"]: record for record in executable_records
    }
    expected_executables = set(contract["process_exec_paths"]) | {
        contract["sandbox_executable"],
        str(_NATIVE_RSS_MONITOR_EXECUTABLE),
    }
    launcher_record = executable_by_logical.get(contract["python_launcher"])
    abi_match = re.search(
        r"/Versions/([0-9]+\.[0-9]+)/", contract["python_resolved"],
    )
    expected_site_packages = (
        _ROOT / ".venv" / "lib"
        / f"python{contract['python_abi']}" / "site-packages"
    ).absolute()
    locked_runtime_roots = tuple(
        Path(record[field])
        for record in closure["mutable_roots"]
        for field in ("logical_path", "resolved_path")
    )

    def covered_by_runtime_lock(path_text: str) -> bool:
        path = Path(path_text)
        return any(
            path == root or _path_beneath(path, root)
            for root in locked_runtime_roots
        )

    if (not resolve_live_paths and (
            len(executable_by_logical) != len(executable_records)
            or set(executable_by_logical) != expected_executables
            or launcher_record is None
            or launcher_record["resolved_path"] != contract["python_resolved"]
            or launcher_record["sha256"] != contract["python_sha256"]
            or abi_match is None
            or abi_match.group(1) != contract["python_abi"]
            or contract["python_launcher"]
                != str((_ROOT / ".venv" / "bin" / "python").absolute())
            or contract["site_packages"] != str(expected_site_packages)
            or not covered_by_runtime_lock(contract["site_packages"])
            or platform["sdk_logical_path"] != contract["sdk_root"]
            or not covered_by_runtime_lock(contract["sdk_root"])
            or any(not covered_by_runtime_lock(path)
                   for path in contract["runtime_read_paths"])
            or any(path not in executable_by_logical
                   for path in contract["compiler_paths"].values())
            or any(Path(path).name != name
                   for name, path in contract["compiler_paths"].items()))):
        raise NativeWorkerSandboxStop(
            "native sandbox contract differs from its runtime lock"
        )
    if (resolve_live_paths
            and platform["sdk_resolved_path"]
                != str(Path(contract["sdk_root"]).resolve())):
        raise NativeWorkerSandboxStop("native SDK differs from the runtime lock")


def _native_fast_path_binding(path: Path) -> tuple[Any, ...]:
    """Bind one live logical path without rescanning its descendant bytes."""
    absolute = Path(os.path.abspath(os.fspath(path)))

    def identity(value: os.stat_result) -> tuple[int, ...]:
        return (
            int(value.st_dev), int(value.st_ino), int(value.st_mode),
            int(value.st_nlink), int(value.st_uid), int(value.st_gid),
            int(value.st_size), int(value.st_mtime_ns), int(value.st_ctime_ns),
        )

    links: list[tuple[Any, ...]] = []
    cursor = Path(absolute.anchor)
    try:
        for part in absolute.parts[1:]:
            cursor = cursor / part
            before = cursor.lstat()
            if not stat.S_ISLNK(before.st_mode):
                continue
            raw_target = os.readlink(cursor)
            resolved_component = cursor.resolve(strict=True)
            after = cursor.lstat()
            raw_target_after = os.readlink(cursor)
            if (identity(before) != identity(after)
                    or raw_target_after != raw_target):
                raise NativeWorkerSandboxStop(
                    f"native runtime path changed while binding: {cursor}"
                )
            links.append((
                str(cursor), identity(after), raw_target,
                str(resolved_component),
            ))
        resolved = absolute.resolve(strict=True)
        target_before = resolved.lstat()
        if absolute.resolve(strict=True) != resolved:
            raise NativeWorkerSandboxStop(
                f"native runtime path changed while binding: {absolute}"
            )
        target_after = resolved.lstat()
    except NativeWorkerSandboxStop:
        raise
    except OSError as exc:
        raise NativeWorkerSandboxStop(
            f"native runtime path cannot be bound: {absolute}"
        ) from exc
    if identity(target_before) != identity(target_after):
        raise NativeWorkerSandboxStop(
            f"native runtime target changed while binding: {absolute}"
        )
    return (
        str(absolute), str(resolved), tuple(links), identity(target_after),
    )


def _raw_native_runtime_binding_lease(
    contract: Mapping[str, Any],
) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    """Capture path identities without treating that baseline as authority."""
    _validate_native_sandbox_contract_shape(contract)
    paths = [
        str(contract["sandbox_executable"]),
        str(contract["python_launcher"]),
        str(contract["python_resolved"]),
        str(contract["site_packages"]),
        str(contract["sdk_root"]),
        str(contract["resource_limits"]["resident_memory_monitor"]),
        *(str(path) for path in contract["compiler_paths"].values()),
        *(str(path) for path in contract["runtime_read_paths"]),
        *(str(path) for path in contract["process_exec_paths"]),
    ]
    unique: list[str] = []
    for value in paths:
        absolute = str(Path(os.path.abspath(value)))
        if absolute not in unique:
            unique.append(absolute)
    return tuple(
        (value, _native_fast_path_binding(Path(value))) for value in unique
    )


def _capture_native_runtime_binding_lease(
    contract: Mapping[str, Any],
) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    """Bind fast identities to an independent exact live-contract rescan."""
    lease = _raw_native_runtime_binding_lease(contract)
    confirmation = _native_sandbox_contract()
    if _canonical_bytes(confirmation) != _canonical_bytes(contract):
        raise NativeWorkerSandboxStop(
            "native runtime/toolchain closure changed while binding its scan"
        )
    if _raw_native_runtime_binding_lease(contract) != lease:
        raise NativeWorkerSandboxStop(
            "native runtime path/toolchain binding changed during confirmation"
        )
    return lease


def _verify_native_runtime_binding_lease(
    contract: Mapping[str, Any],
    expected: tuple[tuple[str, tuple[Any, ...]], ...],
) -> None:
    current = _raw_native_runtime_binding_lease(contract)
    if current != expected:
        raise NativeWorkerSandboxStop(
            "native runtime path/toolchain binding changed before launch"
        )


def _capture_confirmed_native_runtime_binding_lease(
    contract: Mapping[str, Any],
) -> tuple[tuple[str, tuple[Any, ...]], ...]:
    """Compatibility name for the now intrinsically confirmed capture."""
    return _capture_native_runtime_binding_lease(contract)


def _require_live_native_sandbox_contract(
    frozen_runtime_lock: Mapping[str, Any],
) -> tuple[dict[str, Any], tuple[tuple[str, tuple[Any, ...]], ...]]:
    """Refuse a stale H lock before preflight, authorization, or worker launch."""
    frozen_contract = _native_sandbox_contract(
        frozen_runtime_lock=frozen_runtime_lock,
    )
    live_contract = _native_sandbox_contract()
    if _canonical_bytes(live_contract) != _canonical_bytes(frozen_contract):
        raise NativeWorkerSandboxStop(
            "frozen H runtime/toolchain closure differs before native work"
        )
    return frozen_contract, _capture_confirmed_native_runtime_binding_lease(
        frozen_contract,
    )


def _native_block_identity_sha256(
    native_intent_sha256: str, block_ordinal: int,
    schedule_rows: Sequence[Mapping[str, Any]],
) -> str:
    if (not isinstance(native_intent_sha256, str)
            or not _HEX64.fullmatch(native_intent_sha256)
            or type(block_ordinal) is not int or block_ordinal < 0):
        raise shots.LockMismatch("native block identity input is malformed")
    return hashlib.sha256(_canonical_bytes({
        "schema": _NATIVE_BLOCK_IDENTITY_SCHEMA,
        "native_intent_sha256": native_intent_sha256,
        "block_ordinal": block_ordinal,
        "schedule_rows": [dict(row) for row in schedule_rows],
    })).hexdigest()


def _native_intent(
    *, h: _VerifiedH, training_sha256: str,
    schedule: Sequence[Mapping[str, Any]],
    raw_inputs: Sequence[Mapping[str, Any]],
    sandbox_contract: Mapping[str, Any],
) -> tuple[dict[str, Any], str,
           tuple[tuple[dict[str, Any], ...], ...]]:
    blocks = _training_schedule_blocks(schedule)
    if training_sha256 != h.training_schedule_sha256:
        raise shots.LockMismatch("native intent schedule differs from live H")
    contract_sha256 = _native_sandbox_contract_sha256(sandbox_contract)
    payload = {
        "schema": _NATIVE_INTENT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "parent_commit": _NATIVE_PARENT_COMMIT,
        "parent_tree": _NATIVE_PARENT_TREE,
        "training_schedule_sha256": training_sha256,
        "raw_inputs": [dict(record) for record in raw_inputs],
        "schedule": [dict(row) for row in schedule],
        "sandbox_contract_sha256": contract_sha256,
    }
    return payload, hashlib.sha256(_canonical_bytes(payload)).hexdigest(), blocks


def _native_request(
    *, native_intent: Mapping[str, Any], native_intent_sha256: str,
    block_ordinals: Sequence[int], block_count: int,
) -> dict[str, Any]:
    ordinals = tuple(block_ordinals)
    if (not isinstance(native_intent, Mapping)
            or native_intent.get("schema") != _NATIVE_INTENT_SCHEMA
            or hashlib.sha256(_canonical_bytes(native_intent)).hexdigest()
                != native_intent_sha256
            or any(type(value) is not int for value in ordinals)
            or ordinals != tuple(sorted(set(ordinals)))
            or any(value < 0 or value >= block_count for value in ordinals)):
        raise shots.LockMismatch("native job request identity is malformed")
    return {
        "schema": _NATIVE_INPUT_SCHEMA,
        "native_intent": dict(native_intent),
        "native_intent_sha256": native_intent_sha256,
        "block_ordinals": list(ordinals),
    }


def _validate_native_block(
    value: Mapping[str, Any], *, native_intent_sha256: str,
    h: _VerifiedH, training_sha256: str,
    raw_inputs: Sequence[Mapping[str, Any]],
    expected_ordinal: int,
    blocks: Sequence[Sequence[Mapping[str, Any]]],
) -> dict[str, Any]:
    if (type(expected_ordinal) is not int
            or not 0 <= expected_ordinal < len(blocks)):
        raise shots.LockMismatch("native block ordinal is outside the schedule")
    _keys(value, {
        "schema", "native_intent_sha256", "block_identity_sha256",
        "harness_commit", "harness_manifest_sha256",
        "parent_commit", "parent_tree",
        "training_schedule_sha256", "block_ordinal", "block", "cutoff",
        "rows", "receipt",
    }, label="native block")
    expected = blocks[expected_ordinal]
    if (value["schema"] != _NATIVE_BLOCK_SCHEMA
            or value["native_intent_sha256"] != native_intent_sha256
            or value["block_identity_sha256"]
                != _native_block_identity_sha256(
                    native_intent_sha256, expected_ordinal, expected,
                )
            or value["harness_commit"] != h.commit
            or value["harness_manifest_sha256"] != h.manifest_sha256
            or value["parent_commit"] != _NATIVE_PARENT_COMMIT
            or value["parent_tree"] != _NATIVE_PARENT_TREE
            or value["training_schedule_sha256"] != training_sha256
            or type(value["block_ordinal"]) is not int
            or value["block_ordinal"] != expected_ordinal
            or value["block"] != expected[0]["block"]
            or value["cutoff"] != expected[0]["cutoff"]):
        raise shots.LockMismatch("native block does not bind its exact intent/schedule")
    rows = value["rows"]
    if not isinstance(rows, list) or len(rows) != len(expected):
        raise shots.FixtureSetMismatch("native block row count differs")
    row_fields = {
        "ordinal", "match_id", "season", "block", "cutoff", "home_key",
        "away_key", "native", "y",
    }
    identity_fields = (
        "ordinal", "match_id", "season", "block", "cutoff", "home_key",
        "away_key",
    )
    for row, identity in zip(rows, expected, strict=True):
        if (not isinstance(row, Mapping) or set(row) != row_fields
                or type(row["ordinal"]) is not int
                or any(row[name] != identity[name] for name in identity_fields)):
            raise shots.FixtureSetMismatch("native block row identity differs")
        native = row["native"]
        if (not isinstance(native, list) or len(native) != 3
                or any(type(v) not in (int, float)
                       or not math.isfinite(float(v))
                       or not 0.0 < float(v) <= 1.0 for v in native)
                or abs(sum(float(v) for v in native) - 1.0) > 1.5e-8
                or any(float(v) != round(float(v), 8) for v in native)):
            raise shots.ProbabilityInvalid("native block probability is invalid")
        if type(row["y"]) is not int or row["y"] not in (0, 1, 2):
            raise shots.FitFailure("native block training outcome code is invalid")
    receipt = value["receipt"]
    receipt_fields = {
        "exposed_raw_count", "exposed_raw_files", "parsed_seasons",
        "native_modules", "feature_cache_root", "input_rows",
        "training_rows", "training_blocks",
        "seed", "backend", "draws", "tune", "advi_iterations", "cadence",
        "n_training_matches", "n_teams", "cold_start_teams",
        "provisional_teams", "anchor_spec", "warnings", "health",
    }
    if not isinstance(receipt, Mapping) or set(receipt) != receipt_fields:
        raise shots.LockMismatch("native block receipt fields differ")
    expected_raw = [dict(record) for record in raw_inputs]
    parsed = receipt["parsed_seasons"]
    parse_fields = {
        "path", "sha256", "bytes", "season_code", "season", "rows",
        "dropped_blank_rows", "issues",
    }
    expected_seasons = tuple(zip(
        _NATIVE_RAW_CODES, ("2014/15", *shots.TRAINING_SEASONS), strict=True,
    ))
    parsed_valid = isinstance(parsed, list) and len(parsed) == 5
    if parsed_valid:
        for record, raw, (code, season) in zip(
            parsed, expected_raw, expected_seasons, strict=True,
        ):
            if (not isinstance(record, Mapping) or set(record) != parse_fields
                    or record["path"] != raw["path"]
                    or record["sha256"] != raw["sha256"]
                    or record["bytes"] != raw["bytes"]
                    or record["season_code"] != code
                    or record["season"] != season or record["rows"] != 380
                    or type(record["dropped_blank_rows"]) is not int
                    or record["dropped_blank_rows"] < 0
                    or not isinstance(record["issues"], list)
                    or any(not isinstance(issue, str) for issue in record["issues"])
                    or record["issues"] != (
                        [f"dropped {record['dropped_blank_rows']} fully blank trailing row(s)"]
                        if record["dropped_blank_rows"] else []
                    )):
                parsed_valid = False
                break
    if (receipt["exposed_raw_count"] != 5
            or receipt["exposed_raw_files"] != expected_raw
            or not parsed_valid
            or receipt["input_rows"] != 1900
            or receipt["training_rows"] != shots.TRAINING_ROWS
            or receipt["training_blocks"] != 142
            or receipt["seed"] != 20260611
            or receipt["backend"] != "advi"
            or receipt["draws"] != 1000 or receipt["tune"] != 1000
            or receipt["advi_iterations"] != 30000
            or type(receipt["cadence"]) is not int
            or receipt["cadence"] != 1):
        raise shots.LockMismatch("native block input/inference receipt differs")
    expected_modules = {
        "epl.anchor": "epl/anchor.py", "epl.fit": "epl/fit.py",
        "epl.freeze": "epl/freeze.py", "epl.parse": "epl/parse.py",
        "epl.paths": "epl/paths.py",
        "epl.schema": "epl/schema.py",
        "epl.walkforward": "epl/walkforward.py",
    }
    if receipt["native_modules"] != expected_modules:
        raise shots.LockMismatch("native modules did not import from the isolate")
    if receipt["feature_cache_root"] != "runtime/feature_cache":
        raise shots.LockMismatch("native feature cache did not use runtime root")
    health = receipt["health"]
    if (not isinstance(health, Mapping)
            or health.get("all_finite") is not True
            or health.get("sigma_positive") is not True
            or health.get("home_adv_sane") is not True):
        raise shots.FitFailure("native block numerical health failed")
    if (type(receipt["n_training_matches"]) is not int
            or receipt["n_training_matches"] <= 0
            or type(receipt["n_teams"]) is not int or receipt["n_teams"] <= 0
            or not isinstance(receipt["cold_start_teams"], list)
            or not isinstance(receipt["provisional_teams"], list)
            or not isinstance(receipt["warnings"], list)
            or not isinstance(receipt["anchor_spec"], str)):
        raise shots.LockMismatch("native block runtime receipt is malformed")
    return dict(value)


def _native_semantic_refusal(
    value: Mapping[str, Any], *, native_intent_sha256: str,
    job_request_sha256: str, h: _VerifiedH, training_sha256: str,
    allow_parent_runtime_mismatch: bool = False,
) -> shots.ShotsError | None:
    """Validate a worker event or the explicitly opted-in parent mismatch."""
    if not isinstance(value, Mapping) or value.get("schema") \
            != _NATIVE_SEMANTIC_REFUSAL_SCHEMA:
        return None
    _keys(value, {
        "schema", "native_intent_sha256", "job_request_sha256",
        "harness_commit", "harness_manifest_sha256",
        "training_schedule_sha256", "refusal_kind", "exception_type",
        "message",
    }, label="native semantic refusal")
    message = value["message"]
    exception_type = value["exception_type"]
    refusal_kind = value["refusal_kind"]
    allowed_kinds = {"NativeSemanticRefusal", "NativeFitFailure"}
    if allow_parent_runtime_mismatch:
        allowed_kinds.add("NativeRuntimeClosureMismatch")
    if (value["native_intent_sha256"] != native_intent_sha256
            or value["job_request_sha256"] != job_request_sha256
            or value["harness_commit"] != h.commit
            or value["harness_manifest_sha256"] != h.manifest_sha256
            or value["training_schedule_sha256"] != training_sha256
            or refusal_kind not in allowed_kinds
            or not isinstance(exception_type, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]{0,255}",
                                exception_type)
            or not isinstance(message, str) or not 1 <= len(message) <= 4096
            or message != message.strip()
            or any(ord(character) < 32 for character in message)):
        raise shots.LockMismatch("native semantic refusal provenance differs")
    if refusal_kind == "NativeRuntimeClosureMismatch":
        if (exception_type
                != "epl.shots_harness.NativeRuntimeClosureMismatch"
                or message != _NATIVE_RUNTIME_MISMATCH_MESSAGE):
            raise shots.LockMismatch(
                "native runtime mismatch refusal fields differ"
            )
        return NativeRuntimeClosureMismatch(message)
    return shots.FitFailure(
        f"{refusal_kind} ({exception_type}): {message}"
    )


def _validate_native_intent_for_refusal(
    native_intent: Mapping[str, Any],
    native_intent_record: Mapping[str, Any], *, h: _VerifiedH,
    training_sha256: str,
) -> tuple[
    str, tuple[tuple[Mapping[str, Any], ...], ...], dict[str, Any],
]:
    """Bind a refusal to the actual parent-authored intent artifact."""
    _keys(native_intent, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "parent_commit", "parent_tree", "training_schedule_sha256",
        "raw_inputs", "schedule", "sandbox_contract_sha256",
    }, label="native refusal intent")
    digest, _, _ = _validate_k2_record_metadata(
        "native_intent", native_intent_record,
    )
    schedule = native_intent["schedule"]
    raw_inputs = native_intent["raw_inputs"]
    if not isinstance(schedule, list):
        raise shots.LockMismatch("native refusal intent schedule is malformed")
    blocks = _schedule_blocks_exact(schedule)
    expected_raw = _native_raw_digests()
    if h.native_runtime_lock is None:
        raise shots.LockMismatch("native refusal H runtime lock is absent")
    try:
        shots._validate_native_runtime_lock(h.native_runtime_lock)
    except shots.LockMismatch as exc:
        raise shots.LockMismatch(
            "native refusal H runtime lock is malformed"
        ) from exc
    expected_runtime_lock = json.loads(
        _canonical_bytes(h.native_runtime_lock)
    )
    if (native_intent["schema"] != _NATIVE_INTENT_SCHEMA
            or native_intent["harness_commit"] != h.commit
            or native_intent["harness_manifest_sha256"] != h.manifest_sha256
            or native_intent["parent_commit"] != _NATIVE_PARENT_COMMIT
            or native_intent["parent_tree"] != _NATIVE_PARENT_TREE
            or native_intent["training_schedule_sha256"] != training_sha256
            or _digest_rows(_K2_SCHEDULE_SCHEMA, schedule) != training_sha256
            or not isinstance(native_intent["sandbox_contract_sha256"], str)
            or not _HEX64.fullmatch(native_intent["sandbox_contract_sha256"])
            or not isinstance(raw_inputs, list)
            or len(raw_inputs) != len(_NATIVE_RAW_NAMES)):
        raise shots.LockMismatch("native refusal intent provenance differs")
    for name, record in zip(_NATIVE_RAW_NAMES, raw_inputs, strict=True):
        if (not isinstance(record, Mapping)
                or set(record) != {"path", "sha256", "bytes"}
                or record["path"] != f"data/epl/raw/{name}"
                or record["sha256"] != expected_raw[name]
                or type(record["bytes"]) is not int or record["bytes"] <= 0):
            raise shots.LockMismatch(
                "native refusal intent raw-input binding differs"
            )
    recomputed = hashlib.sha256(_canonical_bytes(native_intent)).hexdigest()
    if digest != recomputed:
        raise shots.LockMismatch(
            "native refusal intent record does not bind its value"
        )
    return recomputed, blocks, expected_runtime_lock


def _validated_native_refusal_sandbox_contract(
    value: Mapping[str, Any], *, label: str,
) -> dict[str, Any]:
    """Normalize a receipt contract while mapping live-only stops to identity."""
    if not isinstance(value, Mapping):
        raise shots.LockMismatch(f"{label} is not a mapping")
    try:
        _validate_native_sandbox_contract_shape(
            value, resolve_live_paths=False,
        )
        normalized = json.loads(_canonical_bytes(value))
    except (NativeWorkerSandboxStop, TypeError, ValueError,
            RecursionError) as exc:
        raise shots.LockMismatch(f"{label} is malformed") from exc
    return normalized


def _validated_native_refusal_runtime_evidence(
    runtime_snapshot: Mapping[str, Any],
    runtime_observed: Mapping[str, Any],
) -> tuple[dict[str, Any], dict[str, int]]:
    snapshot = _validate_native_runtime_output_snapshot(runtime_snapshot)
    if not isinstance(runtime_observed, Mapping):
        raise shots.LockMismatch(
            "native refusal resource observation is not a mapping"
        )
    observed = dict(runtime_observed)
    if (set(observed) != {"files", "bytes", "rss_bytes"}
            or any(type(value) is not int or value < 0
                   for value in observed.values())
            or observed["files"] > _NATIVE_RUNTIME_MAX_FILES
            or observed["bytes"] > _NATIVE_RUNTIME_MAX_BYTES
            or observed["rss_bytes"] > _NATIVE_RSS_LIMIT_BYTES
            or snapshot["file_count"] > observed["files"]
            or snapshot["bytes"] > observed["bytes"]):
        raise shots.LockMismatch(
            "native refusal resource observation does not bind its snapshot"
        )
    return snapshot, {
        "files": observed["files"], "bytes": observed["bytes"],
        "rss_bytes": observed["rss_bytes"],
    }


def _native_runtime_mismatch_refusal_event(
    *, native_intent_sha256: str, job_request_sha256: str,
    h: _VerifiedH, training_sha256: str,
) -> dict[str, Any]:
    return {
        "schema": _NATIVE_SEMANTIC_REFUSAL_SCHEMA,
        "native_intent_sha256": native_intent_sha256,
        "job_request_sha256": job_request_sha256,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "training_schedule_sha256": training_sha256,
        "refusal_kind": "NativeRuntimeClosureMismatch",
        "exception_type": "epl.shots_harness.NativeRuntimeClosureMismatch",
        "message": _NATIVE_RUNTIME_MISMATCH_MESSAGE,
    }


def _make_native_refusal_receipt(
    *, semantic_refusal: Mapping[str, Any] | None,
    refusal_source: str, h: _VerifiedH,
    training_sha256: str, native_intent: Mapping[str, Any],
    native_intent_record: Mapping[str, Any], job_ordinals: Sequence[int],
    block_records: Sequence[Mapping[str, Any]], output_bytes: int,
    exit_code: int, sandbox_contract: Mapping[str, Any],
    sandbox_run: Mapping[str, Any],
    runtime_snapshot: Mapping[str, Any],
    runtime_observed: Mapping[str, Any],
    post_launch_sandbox_contract: Mapping[str, Any],
) -> dict[str, Any]:
    native_intent_sha256, blocks, expected_runtime_lock = (
        _validate_native_intent_for_refusal(
            native_intent, native_intent_record, h=h,
            training_sha256=training_sha256,
        )
    )
    bound_contract = _validated_native_refusal_sandbox_contract(
        sandbox_contract, label="native refusal sandbox contract",
    )
    bound_contract_sha256 = _native_sandbox_contract_sha256(bound_contract)
    if (_canonical_bytes(bound_contract["runtime_closure"])
            != _canonical_bytes(expected_runtime_lock)
            or native_intent["sandbox_contract_sha256"]
                != bound_contract_sha256):
        raise shots.LockMismatch(
            "native refusal sandbox contract differs from exact H"
        )
    post_launch_contract = _validated_native_refusal_sandbox_contract(
        post_launch_sandbox_contract,
        label="native refusal post-launch sandbox contract",
    )
    contract_changed = (
        _canonical_bytes(post_launch_contract)
        != _canonical_bytes(bound_contract)
    )
    if not isinstance(sandbox_run, Mapping):
        raise shots.LockMismatch("native refusal sandbox run is not a mapping")
    try:
        normalized_sandbox_run = json.loads(_canonical_bytes(sandbox_run))
    except (TypeError, ValueError, RecursionError) as exc:
        raise shots.LockMismatch(
            "native refusal sandbox run is not strict JSON"
        ) from exc
    _validate_native_sandbox_run(
        normalized_sandbox_run, contract=bound_contract,
    )
    snapshot, observed = _validated_native_refusal_runtime_evidence(
        runtime_snapshot, runtime_observed,
    )

    requested_ordinals = list(job_ordinals)
    if not requested_ordinals:
        raise shots.LockMismatch("native refusal job is empty")
    request = _native_request(
        native_intent=native_intent,
        native_intent_sha256=native_intent_sha256,
        block_ordinals=requested_ordinals, block_count=len(blocks),
    )
    job_request_sha256 = hashlib.sha256(
        _canonical_bytes(request)
    ).hexdigest()
    worker_event: dict[str, Any] | None = None
    if semantic_refusal is not None:
        if not isinstance(semantic_refusal, Mapping):
            raise shots.LockMismatch(
                "native refusal worker event is not a mapping"
            )
        worker_event = dict(semantic_refusal)
        worker_mapped = _native_semantic_refusal(
            worker_event,
            native_intent_sha256=native_intent_sha256,
            job_request_sha256=job_request_sha256,
            h=h, training_sha256=training_sha256,
        )
        if worker_mapped is None:
            raise shots.LockMismatch(
                "native refusal receipt lacks a worker semantic event"
            )

    if type(exit_code) is not int:
        raise shots.LockMismatch("native refusal exit code is malformed")
    if refusal_source == "worker_semantic_refusal":
        if worker_event is None or contract_changed or exit_code == 0:
            raise shots.LockMismatch(
                "native worker refusal execution classification differs"
            )
        terminal_event = worker_event
    elif refusal_source == "parent_runtime_closure_mismatch":
        if (not contract_changed
                or (worker_event is None and exit_code != 0)
                or (worker_event is not None and exit_code == 0)):
            raise shots.LockMismatch(
                "native runtime mismatch execution classification differs"
            )
        terminal_event = _native_runtime_mismatch_refusal_event(
            native_intent_sha256=native_intent_sha256,
            job_request_sha256=job_request_sha256,
            h=h, training_sha256=training_sha256,
        )
    else:
        raise shots.LockMismatch("native refusal source is not recognized")
    mapped = _native_semantic_refusal(
        terminal_event,
        native_intent_sha256=native_intent_sha256,
        job_request_sha256=job_request_sha256,
        h=h, training_sha256=training_sha256,
        allow_parent_runtime_mismatch=(
            refusal_source == "parent_runtime_closure_mismatch"
        ),
    )
    if mapped is None:  # pragma: no cover - both builders fix the schema
        raise shots.LockMismatch("native refusal terminal event is absent")

    records = [dict(record) for record in block_records]
    yielded_ordinals: list[int] = []
    for record in records:
        relative = record.get("path")
        if not isinstance(relative, str):
            raise shots.LockMismatch("native refusal block record path is malformed")
        match = re.fullmatch(
            r"native-block-([0-9]+)-[0-9a-f]{64}\.json",
            PurePosixPath(relative).name,
        )
        if match is None:
            raise shots.LockMismatch("native refusal block record path differs")
        ordinal = int(match.group(1))
        _validate_k2_record_metadata(
            "native_block", record, ordinal=ordinal,
        )
        yielded_ordinals.append(ordinal)
    if yielded_ordinals != sorted(set(yielded_ordinals)):
        raise shots.LockMismatch(
            "native refusal block records are duplicated or out of order"
        )
    if yielded_ordinals != requested_ordinals[:len(yielded_ordinals)]:
        raise shots.LockMismatch(
            "native refusal blocks are not the yielded job prefix"
        )
    streamed_events = [] if worker_event is None else [worker_event]
    expected_bytes = sum(int(record["bytes"]) for record in records) \
        + sum(len(_canonical_bytes(event)) for event in streamed_events)
    if (any(int(record["bytes"]) > _NATIVE_MAX_LINE_BYTES
            for record in records)
            or any(len(_canonical_bytes(event)) > _NATIVE_MAX_LINE_BYTES
                   for event in streamed_events)
            or expected_bytes > _NATIVE_MAX_OUTPUT_BYTES
            or type(output_bytes) is not int
            or output_bytes != expected_bytes):
        raise shots.LockMismatch("native refusal stream identity differs")
    execution = {
        "schema": _NATIVE_REFUSAL_EXECUTION_SCHEMA,
        "source": refusal_source,
        "terminal_event": terminal_event,
        "worker_event": worker_event,
        "sandbox_contract": bound_contract,
        "sandbox_contract_sha256": bound_contract_sha256,
        "sandbox_run": normalized_sandbox_run,
        "runtime_snapshot": snapshot,
        "runtime_observed": observed,
        "post_launch_sandbox_contract": post_launch_contract,
        "post_launch_sandbox_contract_sha256": (
            _native_sandbox_contract_sha256(post_launch_contract)
        ),
    }
    return {
        "schema": _NATIVE_REFUSAL_RECEIPT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "training_schedule_sha256": training_sha256,
        "native_intent_sha256": native_intent_sha256,
        "native_intent_record": dict(native_intent_record),
        "job_request_sha256": job_request_sha256,
        "job_ordinals": requested_ordinals,
        "semantic_refusal": execution,
        "block_records": records,
        "output_lines": len(records) + len(streamed_events),
        "output_bytes": output_bytes,
        "exit_code": exit_code,
    }


def _validate_native_refusal_receipt(
    value: Mapping[str, Any], *, h: _VerifiedH, training_sha256: str,
    artifact_root: Path,
) -> shots.ShotsError:
    _keys(value, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "training_schedule_sha256", "native_intent_sha256",
        "native_intent_record", "job_request_sha256", "job_ordinals",
        "semantic_refusal", "block_records", "output_lines",
        "output_bytes", "exit_code",
    }, label="native refusal receipt")
    execution = value["semantic_refusal"]
    if (value["schema"] != _NATIVE_REFUSAL_RECEIPT_SCHEMA
            or value["harness_commit"] != h.commit
            or value["harness_manifest_sha256"] != h.manifest_sha256
            or value["training_schedule_sha256"] != training_sha256
            or not isinstance(value["native_intent_record"], Mapping)
            or not isinstance(value["job_ordinals"], list)
            or not isinstance(execution, Mapping)
            or not isinstance(value["block_records"], list)):
        raise shots.LockMismatch("native refusal receipt provenance differs")
    _keys(execution, {
        "schema", "source", "terminal_event", "worker_event",
        "sandbox_contract", "sandbox_contract_sha256", "sandbox_run",
        "runtime_snapshot", "runtime_observed",
        "post_launch_sandbox_contract",
        "post_launch_sandbox_contract_sha256",
    }, label="native refusal execution envelope")
    if (execution["schema"] != _NATIVE_REFUSAL_EXECUTION_SCHEMA
            or not isinstance(execution["terminal_event"], Mapping)
            or (execution["worker_event"] is not None
                and not isinstance(execution["worker_event"], Mapping))
            or not isinstance(execution["sandbox_contract_sha256"], str)
            or not _HEX64.fullmatch(execution["sandbox_contract_sha256"])
            or not isinstance(
                execution["post_launch_sandbox_contract_sha256"], str,
            )
            or not _HEX64.fullmatch(
                execution["post_launch_sandbox_contract_sha256"],
            )):
        raise shots.LockMismatch(
            "native refusal execution envelope provenance differs"
        )
    native_intent, _ = _load_content_addressed_json(
        "native_intent", value["native_intent_record"],
        artifact_root=artifact_root,
    )
    _require_decision_record_claim(
        "native_intent", value["native_intent_record"],
        artifact_root=artifact_root,
    )
    rebuilt = _make_native_refusal_receipt(
        semantic_refusal=execution["worker_event"],
        refusal_source=execution["source"], h=h,
        training_sha256=training_sha256, native_intent=native_intent,
        native_intent_record=value["native_intent_record"],
        job_ordinals=value["job_ordinals"],
        block_records=value["block_records"],
        output_bytes=value["output_bytes"], exit_code=value["exit_code"],
        sandbox_contract=execution["sandbox_contract"],
        sandbox_run=execution["sandbox_run"],
        runtime_snapshot=execution["runtime_snapshot"],
        runtime_observed=execution["runtime_observed"],
        post_launch_sandbox_contract=(
            execution["post_launch_sandbox_contract"]
        ),
    )
    if _canonical_bytes(rebuilt) != _canonical_bytes(value):
        raise shots.LockMismatch("native refusal receipt does not recompute")
    blocks = _schedule_blocks_exact(native_intent["schedule"])
    raw_inputs = native_intent["raw_inputs"]
    for record in value["block_records"]:
        match = re.fullmatch(
            r"native-block-([0-9]+)-[0-9a-f]{64}\.json",
            PurePosixPath(record["path"]).name,
        )
        if match is None:  # pragma: no cover - receipt builder guards
            raise shots.LockMismatch("native refusal block path is malformed")
        ordinal = int(match.group(1))
        block = _load_native_block_shard(
            record, artifact_root=artifact_root,
        )
        _require_decision_record_claim(
            "native_block", record, artifact_root=artifact_root,
            ordinal=ordinal,
        )
        _validate_native_block(
            block, native_intent_sha256=value["native_intent_sha256"],
            h=h, training_sha256=training_sha256,
            raw_inputs=raw_inputs, expected_ordinal=ordinal, blocks=blocks,
        )
    mapped = _native_semantic_refusal(
        execution["terminal_event"],
        native_intent_sha256=value["native_intent_sha256"],
        job_request_sha256=value["job_request_sha256"],
        h=h, training_sha256=training_sha256,
        allow_parent_runtime_mismatch=(
            execution["source"] == "parent_runtime_closure_mismatch"
        ),
    )
    if mapped is None:  # pragma: no cover - receipt builder guards
        raise shots.LockMismatch("native refusal receipt envelope is absent")
    return mapped


def _existing_native_refusal(
    *, h: _VerifiedH, training_sha256: str, artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], shots.ShotsError] | None:
    records = _decision_singletons(
        "native_refusal", artifact_root=artifact_root,
    )
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if not records:
            if directory_fd is not None:
                try:
                    names = set(os.listdir(directory_fd))
                except OSError as exc:
                    raise ManualReconciliationRequired(
                        "native refusal namespace could not be inspected"
                    ) from exc
                if ".native-refusal.claim" in names:
                    raise ManualReconciliationRequired(
                        "native refusal claim lacks complete durable bytes"
                    )
            return None
        record, value = records[0]
        if directory_fd is None:
            raise ManualReconciliationRequired(
                "native refusal namespace disappeared"
            )
        try:
            _require_digest_at(
                directory_fd, "native-refusal", str(record["sha256"]),
            )
        except shots.ShotsError as exc:
            raise ManualReconciliationRequired(
                "native refusal claim/bytes need manual reconciliation"
            ) from exc
    mapped = _validate_native_refusal_receipt(
        value, h=h, training_sha256=training_sha256,
        artifact_root=artifact_root,
    )
    return dict(record), dict(value), mapped


@contextlib.contextmanager
def _native_semantic_publication_boundary(
    *, h: _VerifiedH, training_sha256: str, artifact_root: Path,
) -> Iterator[_PendingNativeSemanticPublication]:
    """Publish a terminal envelope only after every outer lease closes cleanly."""
    pending = _PendingNativeSemanticPublication()
    try:
        yield pending
    except _NativeSemanticPublicationReady:
        if pending.receipt is None or pending.refusal is None:
            raise ManualReconciliationRequired(
                "native semantic publication unwind was incomplete"
            )
        try:
            refusal_record, _ = _write_decision_artifact_once(
                "native_refusal", pending.receipt,
                artifact_root=artifact_root,
            )
            stored_refusal = _existing_native_refusal(
                h=h, training_sha256=training_sha256,
                artifact_root=artifact_root,
            )
        except (OSError, shots.ShotsError) as exc:
            raise ManualReconciliationRequired(
                "native semantic refusal could not be durably bound"
            ) from exc
        if (stored_refusal is None
                or stored_refusal[0] != refusal_record
                or _canonical_bytes(stored_refusal[1])
                    != _canonical_bytes(pending.receipt)):
            raise ManualReconciliationRequired(
                "native semantic refusal receipt changed after write"
            )
        pending.refusal.add_note(
            "durable native refusal receipt: "
            f"{refusal_record['sha256']}"
        )
        raise pending.refusal


@contextlib.contextmanager
def _native_completion_publication_boundary(
    *, artifact_root: Path,
) -> Iterator[_PendingNativeCompletionPublication]:
    """Publish clean-exit authority only after all outer leases close cleanly."""
    pending = _PendingNativeCompletionPublication()
    try:
        yield pending
    except _NativeCompletionPublicationReady:
        if pending.receipt is None or pending.validation is None:
            raise ManualReconciliationRequired(
                "native completion publication unwind was incomplete"
            )
        validation = pending.validation
        try:
            _verify_harness_identity_live(validation["h"])
            _write_content_addressed_json(
                "native_completion", pending.receipt,
                artifact_root=artifact_root,
            )
            completed = _discover_completed_native_block_shards(
                artifact_root=artifact_root,
                native_intent=validation["native_intent"],
                native_intent_sha256=validation["native_intent_sha256"],
                h=validation["h"],
                training_sha256=validation["training_sha256"],
                raw_inputs=validation["raw_inputs"],
                blocks=validation["blocks"],
                sandbox_contract=validation["sandbox_contract"],
            )
            _verify_harness_identity_live(validation["h"])
        except (OSError, shots.ShotsError) as exc:
            raise ManualReconciliationRequired(
                "native clean completion could not be durably bound after cleanup"
            ) from exc
        pending.records = tuple(dict(record) for record, _ in completed)


def _stderr_tail(path: Path, limit: int = 8_192) -> str:
    try:
        with path.open("rb") as stream:
            stream.seek(0, os.SEEK_END)
            size = stream.tell()
            stream.seek(max(0, size - limit))
            return stream.read().decode("utf-8", "replace").strip()
    except OSError:
        return "stderr unavailable"


def _sandbox_string(value: Path | str) -> str:
    text = str(value)
    if "\x00" in text or "\n" in text or "\r" in text:
        raise NativeWorkerSandboxStop("sandbox path contains a control character")
    return json.dumps(text, ensure_ascii=True)


def _native_sandbox_profile(
    *, contract: Mapping[str, Any], temporary_root: Path,
    parent_root: Path, request_path: Path, runtime_root: Path,
    resolve_live_paths: bool = True,
) -> str:
    _validate_native_sandbox_contract_shape(
        contract, resolve_live_paths=resolve_live_paths,
    )
    if resolve_live_paths:
        temporary = temporary_root.resolve()
        parent = parent_root.resolve()
        request = request_path.resolve()
        runtime = runtime_root.resolve()
    else:
        temporary = Path(os.path.abspath(os.fspath(temporary_root)))
        parent = Path(os.path.abspath(os.fspath(parent_root)))
        request = Path(os.path.abspath(os.fspath(request_path)))
        runtime = Path(os.path.abspath(os.fspath(runtime_root)))
    try:
        parent.relative_to(temporary)
        request.relative_to(temporary)
        runtime.relative_to(temporary)
    except ValueError as exc:
        raise NativeWorkerSandboxStop("native sandbox path escapes its temp root") from exc
    if (parent == temporary or runtime == temporary or parent == runtime
            or (resolve_live_paths and request.is_dir())
            or request == parent or request == runtime):
        raise NativeWorkerSandboxStop("native sandbox paths are not isolated")
    read_rules = [
        f"(subpath {_sandbox_string(parent)})",
        f"(literal {_sandbox_string(request)})",
        f"(subpath {_sandbox_string(runtime)})",
        *(f"(subpath {_sandbox_string(path)})"
          for path in contract["runtime_read_paths"]),
        *(f"(literal {_sandbox_string(path)})"
          for path in contract["process_exec_paths"]),
        f"(literal {_sandbox_string('/dev/null')})",
        *(f"(literal {_sandbox_string(path)})"
          for path in contract["path_resolution_literals"]),
    ]
    executable_map_rules = [
        f"(subpath {_sandbox_string(runtime)})",
        *(f"(subpath {_sandbox_string(path)})"
          for path in contract["runtime_read_paths"]),
        *(f"(literal {_sandbox_string(path)})"
          for path in contract["process_exec_paths"]),
    ]
    metadata_paths = {
        parent, request, runtime,
        *(Path(str(path)) for path in contract["runtime_read_paths"]),
        *(Path(str(path)) for path in contract["process_exec_paths"]),
        *(Path(str(path)) for path in contract["path_resolution_literals"]),
        Path("/dev/null"),
    }
    metadata_literals: set[Path] = set()
    for path in metadata_paths:
        absolute = Path(os.path.abspath(os.fspath(path)))
        metadata_literals.add(absolute)
        metadata_literals.update(absolute.parents)
    metadata_rules = [
        *(f"(literal {_sandbox_string(path)})"
          for path in sorted(metadata_literals, key=str)),
        f"(subpath {_sandbox_string(parent)})",
        f"(subpath {_sandbox_string(runtime)})",
        *(f"(subpath {_sandbox_string(path)})"
          for path in contract["runtime_read_paths"]),
    ]
    return "\n".join((
        "(version 1)",
        "(deny default)",
        "(deny network*)",
        "(allow process-fork)",
        "(allow process-info*)",
        "(allow process-exec",
        *(f"  (literal {_sandbox_string(path)})"
          for path in contract["process_exec_paths"]),
        ")",
        "(allow sysctl-read)",
        "(allow file-read-metadata",
        *(f"  {rule}" for rule in metadata_rules),
        ")",
        "(allow file-read-data",
        *(f"  {rule}" for rule in read_rules),
        ")",
        "(allow file-map-executable",
        *(f"  {rule}" for rule in executable_map_rules),
        ")",
        f"(allow file-write* (subpath {_sandbox_string(runtime)}))",
        "",
    ))


def _native_environment_values(
    *, contract: Mapping[str, Any], parent_root: Path,
    request_path: Path, runtime_root: Path,
) -> dict[str, str]:
    environment = {
        "CC": str(contract["compiler_paths"]["clang"]),
        "CXX": str(contract["compiler_paths"]["clang++"]),
        "EPL_SHOTS_PARENT_ROOT": str(parent_root),
        "EPL_SHOTS_PYTHON_ABI": str(contract["python_abi"]),
        "EPL_SHOTS_REQUEST": str(request_path),
        "EPL_SHOTS_RUNTIME_ROOT": str(runtime_root),
        "EPL_SHOTS_SITE_PACKAGES": str(contract["site_packages"]),
        # PyTensor expands its default ~/.pytensorrc even when all material
        # settings are provided by PYTENSOR_FLAGS.  Give it a fixed empty
        # home inside the only writable sandbox tree; never inherit user HOME.
        "HOME": str(runtime_root / "home"),
        "LANG": "C",
        "LC_ALL": "C",
        "MPLCONFIGDIR": str(runtime_root / "matplotlib"),
        "OPENBLAS_NUM_THREADS": "1",
        "OMP_NUM_THREADS": "1",
        "PATH": f"{_ROOT / '.venv' / 'bin'}:/usr/bin:/bin",
        "PYTHONHASHSEED": "0",
        "PYTHONNOUSERSITE": "1",
        "PYTENSOR_FLAGS": (
            f"base_compiledir={runtime_root / 'pytensor'},"
            f"cxx={contract['compiler_paths']['clang++']}"
        ),
        "SDKROOT": str(contract["sdk_root"]),
        "TMPDIR": str(runtime_root / "tmp"),
        "VECLIB_MAXIMUM_THREADS": "1",
        "XDG_CACHE_HOME": str(runtime_root / "cache"),
    }
    if sorted(environment) != sorted(contract["environment_keys"]):
        raise NativeWorkerSandboxStop("native worker environment allowlist differs")
    return environment


def _native_minimal_environment(
    *, contract: Mapping[str, Any], parent_root: Path,
    request_path: Path, runtime_root: Path,
) -> dict[str, str]:
    for child in ("cache", "home", "matplotlib", "pytensor", "tmp"):
        (runtime_root / child).mkdir(parents=True, exist_ok=False)
    return _native_environment_values(
        contract=contract, parent_root=parent_root,
        request_path=request_path, runtime_root=runtime_root,
    )


def _native_sandbox_command(
    *, contract: Mapping[str, Any], profile: str, source: str,
) -> tuple[str, ...]:
    executable = Path(str(contract["sandbox_executable"]))
    launcher = Path(str(contract["python_resolved"]))
    if (executable != _NATIVE_SANDBOX_EXECUTABLE
            or not executable.is_file() or not os.access(executable, os.X_OK)):
        raise NativeWorkerSandboxStop("/usr/bin/sandbox-exec is unavailable")
    if (not launcher.is_absolute() or launcher.is_symlink()
            or not launcher.is_file() or not os.access(launcher, os.X_OK)
            or shots.sha256_file(launcher) != contract["python_sha256"]):
        raise NativeWorkerSandboxStop("resolved native Python is unavailable")
    return (
        str(executable), "-p", profile, str(launcher),
        *tuple(str(flag) for flag in contract["python_flags"]), "-c", source,
    )


def _apply_native_resource_limits() -> None:
    """Apply child-local kernel limits; RSS is enforced by the parent.

    In particular, do not set ``RLIMIT_AS`` on macOS.  A normal Python process
    can reserve hundreds of GiB of sparse virtual address space while using a
    small resident set, so an address-space limit is not a memory-usage limit.
    """
    limits = (
        (resource.RLIMIT_CPU, _NATIVE_CPU_LIMIT_SECONDS),
        (resource.RLIMIT_FSIZE, _NATIVE_FILE_LIMIT_BYTES),
        (resource.RLIMIT_NOFILE, _NATIVE_NOFILE_LIMIT),
        (resource.RLIMIT_CORE, 0),
    )
    for key, requested in limits:
        _, hard = resource.getrlimit(key)
        if hard != resource.RLIM_INFINITY and hard < requested:
            raise RuntimeError(f"native resource hard limit {key} is too small")
        resource.setrlimit(key, (requested, requested))


def _native_process_group_rss_bytes(
    process: subprocess.Popen[bytes],
) -> int:
    """Return one sampled sum of resident bytes for the worker process group."""
    if type(process.pid) is not int or process.pid <= 0:
        raise NativeWorkerIOFailure("native worker process-group id is invalid")
    try:
        completed = subprocess.run(
            (
                str(_NATIVE_RSS_MONITOR_EXECUTABLE),
                "-axo", "pgid=,rss=",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=10,
            check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerIOFailure(
            "native resident-memory monitor could not run"
        ) from exc
    if completed.returncode != 0 or len(completed.stdout) > 16 * 1_048_576:
        raise NativeWorkerIOFailure("native resident-memory monitor failed")
    total_kib = 0
    members = 0
    try:
        output = completed.stdout.decode("ascii")
        for line in output.splitlines():
            fields = line.split()
            if len(fields) != 2:
                raise ValueError("unexpected ps fields")
            pgid, rss_kib = (int(field, 10) for field in fields)
            if pgid == process.pid:
                if rss_kib < 0:
                    raise ValueError("negative rss")
                members += 1
                total_kib += rss_kib
    except (UnicodeError, ValueError) as exc:
        raise NativeWorkerIOFailure(
            "native resident-memory monitor output is malformed"
        ) from exc
    # The worker leader deliberately remains unreaped until every other group
    # member is gone.  Consequently an owned group must always have at least
    # that leader in ``ps``; polling here would reap it and make a later PGID
    # signal capable of targeting a recycled, unrelated group.
    if members == 0:
        raise NativeWorkerIOFailure(
            "native resident-memory monitor lost the owned process group"
        )
    return total_kib * 1_024


def _observe_native_process_group_rss(
    process: subprocess.Popen[bytes], *, limit_bytes: int,
    observed: dict[str, int] | None,
) -> int:
    if type(limit_bytes) is not int or limit_bytes <= 0:
        raise NativeWorkerIOFailure("native resident-memory limit is invalid")
    rss_bytes = _native_process_group_rss_bytes(process)
    if observed is not None:
        observed["rss_bytes"] = max(observed.get("rss_bytes", 0), rss_bytes)
    if rss_bytes > limit_bytes:
        raise NativeWorkerIOFailure(
            "native worker process-group resident-memory limit exceeded"
        )
    return rss_bytes


def _wait_native_process_with_rss_limit(
    process: subprocess.Popen[bytes], *, timeout_seconds: float,
    limit_bytes: int = _NATIVE_RSS_LIMIT_BYTES,
    poll_seconds: float = _NATIVE_RSS_POLL_SECONDS,
    observed: dict[str, int] | None = None,
) -> None:
    """Observe leader exit without reaping while enforcing the group RSS cap."""
    if (type(timeout_seconds) not in (int, float)
            or not math.isfinite(float(timeout_seconds))
            or float(timeout_seconds) <= 0
            or type(poll_seconds) not in (int, float)
            or not math.isfinite(float(poll_seconds))
            or float(poll_seconds) <= 0
            or type(limit_bytes) is not int or limit_bytes <= 0):
        raise NativeWorkerIOFailure("native resident-memory monitor timing is invalid")
    deadline = time.monotonic() + timeout_seconds
    while True:
        state = _native_process_group_state(process)
        if state.leader_exited:
            return
        _observe_native_process_group_rss(
            process, limit_bytes=limit_bytes, observed=observed,
        )
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise NativeWorkerIOFailure("native worker wait deadline exceeded")
        time.sleep(min(poll_seconds, remaining))


@dataclass(frozen=True)
class _NativeProcessGroupState:
    leader_pid: int
    process_group_id: int
    leader_exited: bool
    nonleader_pids: tuple[int, ...]


def _require_native_process_group_monitor() -> None:
    """Refuse before launch when the ownership monitor cannot be executed."""
    try:
        completed = subprocess.run(
            (
                str(_NATIVE_RSS_MONITOR_EXECUTABLE),
                "-axo", "pid=,pgid=,stat=",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.PIPE,
            text=False,
            timeout=10,
            check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor could not run"
        ) from exc
    if completed.returncode != 0:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor failed"
        )


def _native_process_group_state(
    process: subprocess.Popen[bytes],
) -> _NativeProcessGroupState:
    """Inspect an owned PGID while its unreaped leader prevents ID reuse."""
    if type(process.pid) is not int or process.pid <= 0:
        raise NativeWorkerIOFailure("native worker process-group id is invalid")
    if process.returncode is not None:
        raise NativeWorkerIOFailure(
            "native worker leader was reaped before process-group closure"
        )
    try:
        completed = subprocess.run(
            (
                str(_NATIVE_RSS_MONITOR_EXECUTABLE),
                "-axo", "pid=,pgid=,stat=",
            ),
            stdin=subprocess.DEVNULL,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=False,
            timeout=10,
            check=False,
            env={"LC_ALL": "C", "PATH": "/usr/bin:/bin"},
        )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor could not run"
        ) from exc
    if completed.returncode != 0 or len(completed.stdout) > 16 * 1_048_576:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor failed"
        )
    leader_state: str | None = None
    members: list[int] = []
    seen_pids: set[int] = set()
    try:
        output = completed.stdout.decode("ascii")
        for line in output.splitlines():
            fields = line.split()
            if len(fields) != 3:
                raise ValueError("unexpected ps fields")
            pid = int(fields[0], 10)
            pgid = int(fields[1], 10)
            process_state = fields[2]
            if (pid <= 0 or pgid <= 0
                    or fields[0] != str(pid) or fields[1] != str(pgid)):
                raise ValueError("invalid ps process record")
            if pid in seen_pids:
                raise ValueError("duplicate ps process id")
            seen_pids.add(pid)
            if pgid != process.pid:
                continue
            if re.fullmatch(
                r"[DIRSTUZ][+<>AELNsVWX]*", process_state,
            ) is None:
                raise ValueError("invalid owned-group process state")
            members.append(pid)
            if pid == process.pid:
                leader_state = process_state
    except (UnicodeError, ValueError) as exc:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor output is malformed"
        ) from exc
    if leader_state is None:
        raise NativeWorkerIOFailure(
            "native process-group ownership monitor lost the unreaped leader"
        )
    return _NativeProcessGroupState(
        leader_pid=process.pid,
        process_group_id=process.pid,
        leader_exited=leader_state.startswith("Z"),
        nonleader_pids=tuple(sorted(
            pid for pid in members if pid != process.pid
        )),
    )


def _signal_native_process_group(
    process: subprocess.Popen[bytes], group_state: _NativeProcessGroupState,
    requested_signal: signal.Signals,
) -> None:
    """Signal only after a same-snapshot proof of the unreaped PGID anchor."""
    if process.returncode is not None:
        raise NativeWorkerIOFailure(
            "native worker leader was reaped before process-group signal"
        )
    # ``group_state`` can only be constructed when PID == PGID is present.
    # Keeping that leader unreaped prevents the numeric PGID from being reused
    # between this ownership proof and killpg.
    if (not isinstance(group_state, _NativeProcessGroupState)
            or group_state.leader_pid != process.pid
            or group_state.process_group_id != process.pid):
        raise NativeWorkerIOFailure("native process-group state is invalid")
    try:
        os.killpg(process.pid, requested_signal)
    except OSError as exc:
        # A final nonleader can disappear between the ownership snapshot and
        # the signal.  Darwin may then report ESRCH/EPERM for a group whose
        # only remaining member is the zombie anchor.  Re-snapshot while that
        # anchor is still unreaped; accept only the now-complete closure.
        after = _native_process_group_state(process)
        if after.leader_exited and not after.nonleader_pids:
            return
        raise NativeWorkerIOFailure(
            "native worker process-group signal failed"
        ) from exc


def _close_native_process_group(
    process: subprocess.Popen[bytes], *, leader_must_have_exited: bool,
) -> tuple[int, bool]:
    """Close the owned group, then reap its leader exactly once and last.

    The zombie/live leader remains the PGID ownership anchor throughout every
    snapshot and signal.  Only after it is a zombie and no nonleader member
    remains do we call ``wait``; no process-group operation follows that reap.
    """
    state = _native_process_group_state(process)
    if leader_must_have_exited and not state.leader_exited:
        raise NativeWorkerIOFailure(
            "native worker leader remained live after its output closed"
        )
    had_nonleaders = bool(state.nonleader_pids)
    if not state.leader_exited or state.nonleader_pids:
        _signal_native_process_group(process, state, signal.SIGTERM)
        deadline = time.monotonic() + 2.0
        while True:
            state = _native_process_group_state(process)
            if state.leader_exited and not state.nonleader_pids:
                break
            if time.monotonic() >= deadline:
                _signal_native_process_group(process, state, signal.SIGKILL)
                kill_deadline = time.monotonic() + 10.0
                while True:
                    state = _native_process_group_state(process)
                    if state.leader_exited and not state.nonleader_pids:
                        break
                    if time.monotonic() >= kill_deadline:
                        raise NativeWorkerIOFailure(
                            "native worker process-group did not terminate"
                        )
                    time.sleep(0.05)
                break
            time.sleep(0.05)
    try:
        returncode = process.wait(timeout=10)
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerIOFailure(
            "native worker leader could not be reaped after group closure"
        ) from exc
    if type(returncode) is not int or process.returncode != returncode:
        raise NativeWorkerIOFailure("native worker return code is invalid")
    return returncode, had_nonleaders


def _terminate_native_process_group(process: subprocess.Popen[bytes]) -> None:
    _close_native_process_group(process, leader_must_have_exited=False)


def _native_sandbox_preflight(
    *, command: Sequence[str], environment: Mapping[str, str],
    cwd: Path, runtime_contract: Mapping[str, Any],
    runtime_binding_lease: tuple[tuple[str, tuple[Any, ...]], ...],
) -> None:
    sentinel = _ROOT / "pyproject.toml"
    probe = f'''import os, pathlib, socket, sys
root = pathlib.Path(os.environ["EPL_SHOTS_PARENT_ROOT"])
site_packages = pathlib.Path(os.environ["EPL_SHOTS_SITE_PACKAGES"])
assert sys.dont_write_bytecode
assert os.environ["PYTHONHASHSEED"] == "0"
assert os.environ["EPL_SHOTS_PYTHON_ABI"] == f"{{sys.version_info.major}}.{{sys.version_info.minor}}"
sys.path.insert(0, str(root / "src"))
sys.path.insert(0, str(root))
sys.path.append(str(site_packages))
import numpy, pandas
import pytensor
import pytensor.tensor as pt
from epl import fit, walkforward
probe_x = pt.dscalar("sandbox_probe")
probe_function = pytensor.function([probe_x], probe_x + 1.0)
assert float(probe_function(2.0)) == 3.0
pathlib.Path(os.environ["EPL_SHOTS_REQUEST"]).read_bytes()
for operation in (
    lambda: pathlib.Path({_sandbox_string(sentinel)}).read_bytes(),
    lambda: (root / "sandbox-denied-probe").write_bytes(b"denied"),
    lambda: socket.create_connection(("127.0.0.1", 9), timeout=0.1),
    lambda: socket.socket(socket.AF_INET, socket.SOCK_STREAM).bind(
        ("127.0.0.1", 0)
    ),
):
    try:
        operation()
    except PermissionError:
        pass
    else:
        raise RuntimeError("sandbox negative capability probe unexpectedly succeeded")
'''
    candidate = list(command)
    candidate[-1] = probe
    process: subprocess.Popen[bytes] | None = None
    stderr_path = Path(environment["EPL_SHOTS_RUNTIME_ROOT"]) / "preflight-stderr.log"
    try:
        with stderr_path.open("xb") as stderr:
            _verify_native_runtime_binding_lease(
                runtime_contract, runtime_binding_lease,
            )
            _require_native_process_group_monitor()
            process = subprocess.Popen(
                tuple(candidate), cwd=cwd, env=dict(environment),
                stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
                stderr=stderr, text=False, start_new_session=True,
                preexec_fn=_apply_native_resource_limits,
            )
            _wait_native_process_with_rss_limit(
                process, timeout_seconds=120,
            )
            returncode, had_nonleaders = _close_native_process_group(
                process, leader_must_have_exited=True,
            )
            process = None
            if had_nonleaders:
                raise NativeWorkerSandboxStop(
                    "native sandbox preflight left a descendant process"
                )
    except (OSError, subprocess.SubprocessError) as exc:
        raise NativeWorkerSandboxStop(
            f"native sandbox preflight could not run: {type(exc).__name__}"
        ) from exc
    except NativeWorkerIOFailure as exc:
        raise NativeWorkerSandboxStop(
            f"native sandbox preflight resource monitor refused: {exc}"
        ) from exc
    finally:
        if process is not None:
            active_failure = sys.exc_info()[1]
            try:
                _terminate_native_process_group(process)
            except NativeWorkerIOFailure as cleanup_failure:
                if active_failure is None:
                    raise ManualReconciliationRequired(
                        "native sandbox preflight process-group cleanup needs "
                        "manual reconciliation"
                    ) from cleanup_failure
                raise ManualReconciliationRequired(
                    "native sandbox preflight process-group cleanup failed "
                    "while another result was pending"
                ) from active_failure
    if returncode:
        detail = _stderr_tail(stderr_path, limit=2_048)
        raise NativeWorkerSandboxStop(
            f"native sandbox preflight refused ({returncode}): {detail}"
        )


def _runtime_tree_usage(
    root: Path, *, max_bytes: int = _NATIVE_RUNTIME_MAX_BYTES,
    max_files: int = _NATIVE_RUNTIME_MAX_FILES,
    max_directories: int = _NATIVE_RUNTIME_MAX_DIRECTORIES,
    max_entries: int = _NATIVE_RUNTIME_MAX_ENTRIES,
) -> tuple[int, int, int, int]:
    """Sample a generated tree and stop as soon as any quota is exceeded."""
    if any(
        type(value) is not int or value <= 0
        for value in (max_bytes, max_files, max_directories, max_entries)
    ):
        raise NativeWorkerIOFailure("native runtime tree limits are invalid")
    files = total_bytes = 0
    directories = entries = 1
    pending = [Path(root)]
    try:
        root_info = Path(root).lstat()
        if not stat.S_ISDIR(root_info.st_mode):
            raise NativeWorkerIOFailure(
                "native runtime tree root is not a regular directory"
            )
        while pending:
            directory = pending.pop()
            with os.scandir(directory) as iterator:
                for child in iterator:
                    entries += 1
                    if entries > max_entries:
                        raise NativeWorkerIOFailure(
                            "native worker runtime-tree entry quota exceeded"
                        )
                    info = child.stat(follow_symlinks=False)
                    if stat.S_ISLNK(info.st_mode):
                        raise NativeWorkerIOFailure(
                            "native runtime tree contains a symlink"
                        )
                    if stat.S_ISDIR(info.st_mode):
                        directories += 1
                        if directories > max_directories:
                            raise NativeWorkerIOFailure(
                                "native worker runtime-tree directory quota exceeded"
                            )
                        pending.append(Path(child.path))
                        continue
                    if not stat.S_ISREG(info.st_mode):
                        raise NativeWorkerIOFailure(
                            "native runtime tree contains a special file"
                        )
                    files += 1
                    total_bytes += int(info.st_size)
                    if files > max_files or total_bytes > max_bytes:
                        raise NativeWorkerIOFailure(
                            "native worker runtime-tree quota exceeded"
                        )
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        raise NativeWorkerIOFailure("native runtime tree scan failed") from exc
    return files, directories, entries, total_bytes


def _native_runtime_file_sha256(descriptor: int) -> tuple[str, int]:
    """Hash one already-open regular file without following another path."""
    digest = hashlib.sha256()
    total = 0
    os.lseek(descriptor, 0, os.SEEK_SET)
    while True:
        chunk = os.read(descriptor, 1_048_576)
        if not chunk:
            break
        digest.update(chunk)
        total += len(chunk)
        if total > _NATIVE_RUNTIME_MAX_BYTES:
            raise NativeWorkerIOFailure(
                "native worker runtime-tree byte quota exceeded while hashing"
            )
    return digest.hexdigest(), total


def _native_runtime_stat_identity(value: os.stat_result) -> tuple[int, ...]:
    """Fields a same-user mutation cannot ordinarily restore undetectably."""
    return (
        int(value.st_dev), int(value.st_ino), int(value.st_mode),
        int(value.st_nlink), int(value.st_size), int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _validate_native_runtime_output_snapshot(
    value: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the self-contained completion-time generated-byte receipt."""
    if not isinstance(value, Mapping):
        raise shots.LockMismatch("native runtime output snapshot is not a mapping")
    _keys(value, {
        "schema", "sha256", "file_count", "directory_count", "bytes",
        "entries",
    }, label="native runtime output snapshot")
    entries = value["entries"]
    if (value["schema"] != _NATIVE_RUNTIME_OUTPUT_TREE_SCHEMA
            or not isinstance(value["sha256"], str)
            or not _HEX64.fullmatch(value["sha256"])
            or type(value["file_count"]) is not int
            or type(value["directory_count"]) is not int
            or type(value["bytes"]) is not int
            or not isinstance(entries, list) or not entries
            or len(entries) > _NATIVE_RUNTIME_MAX_ENTRIES):
        raise shots.LockMismatch("native runtime output snapshot identity is malformed")

    normalized: list[dict[str, Any]] = []
    prior_path: str | None = None
    directory_paths: set[str] = set()
    files = directories = total_bytes = 0
    for entry in entries:
        if not isinstance(entry, Mapping):
            raise shots.LockMismatch("native runtime output entry is not a mapping")
        _keys(entry, {
            "relative_path", "kind", "mode", "bytes", "sha256",
        }, label="native runtime output entry")
        relative = entry["relative_path"]
        kind = entry["kind"]
        mode = entry["mode"]
        size = entry["bytes"]
        digest = entry["sha256"]
        if (not isinstance(relative, str) or not relative
                or any(ord(character) < 32 or ord(character) == 127
                       for character in relative)
                or type(mode) is not int or not 0 <= mode <= 0o7777
                or type(size) is not int or size < 0
                or kind not in ("directory", "file")):
            raise shots.LockMismatch("native runtime output entry is malformed")
        path = PurePosixPath(relative)
        if (relative != "." and (
                path.is_absolute() or str(path) != relative
                or any(part in ("", ".", "..") for part in path.parts))):
            raise shots.LockMismatch("native runtime output path is not canonical")
        if prior_path is not None and relative <= prior_path:
            raise shots.LockMismatch(
                "native runtime output paths are not strictly ordered"
            )
        prior_path = relative
        if kind == "directory":
            if size != 0 or digest is not None:
                raise shots.LockMismatch(
                    "native runtime output directory fields are malformed"
                )
            directories += 1
            directory_paths.add(relative)
        else:
            if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
                raise shots.LockMismatch(
                    "native runtime output file digest is malformed"
                )
            files += 1
            total_bytes += size
        normalized.append({
            "relative_path": relative, "kind": kind, "mode": mode,
            "bytes": size, "sha256": digest,
        })

    if (normalized[0]["relative_path"] != "."
            or normalized[0]["kind"] != "directory"):
        raise shots.LockMismatch("native runtime output root entry is absent")
    for entry in normalized[1:]:
        parent = str(PurePosixPath(entry["relative_path"]).parent)
        if parent not in directory_paths:
            raise shots.LockMismatch(
                "native runtime output entry has no recorded parent directory"
            )
    if (value["file_count"] != files
            or value["directory_count"] != directories
            or value["bytes"] != total_bytes
            or files > _NATIVE_RUNTIME_MAX_FILES
            or directories > _NATIVE_RUNTIME_MAX_DIRECTORIES
            or len(normalized) > _NATIVE_RUNTIME_MAX_ENTRIES
            or total_bytes > _NATIVE_RUNTIME_MAX_BYTES):
        raise shots.LockMismatch(
            "native runtime output counts or bytes do not recompute"
        )
    payload = {
        "schema": _NATIVE_RUNTIME_OUTPUT_TREE_SCHEMA,
        "file_count": files, "directory_count": directories,
        "bytes": total_bytes, "entries": normalized,
    }
    if hashlib.sha256(_canonical_bytes(payload)).hexdigest() != value["sha256"]:
        raise shots.LockMismatch("native runtime output tree digest differs")
    return {**payload, "sha256": value["sha256"]}


def _native_runtime_output_snapshot(root: Path) -> dict[str, Any]:
    """Bind generated runtime bytes after a clean worker exit.

    The receipt covers the completion-time runtime tree (including generated
    PyTensor/native files, caches, and logs).  It deliberately does not claim
    to attest which executable images the kernel loaded during the run.
    """
    if not hasattr(os, "O_NOFOLLOW") or not hasattr(os, "O_DIRECTORY"):
        raise NativeWorkerIOFailure(
            "native runtime snapshot requires no-follow directory opens"
        )
    absolute = Path(os.path.abspath(os.fspath(root)))
    directory_flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    file_flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    records: list[dict[str, Any]] = []
    files_seen = directories_seen = total_bytes_seen = 0

    def scan_names(descriptor: int, *, max_names: int) -> list[str]:
        os.lseek(descriptor, 0, os.SEEK_SET)
        names: list[str] = []
        with os.scandir(descriptor) as iterator:
            for entry in iterator:
                names.append(entry.name)
                if len(names) > max_names:
                    raise NativeWorkerIOFailure(
                        "native worker runtime-tree entry quota exceeded"
                    )
        return sorted(names)

    def walk(descriptor: int, relative: str) -> None:
        nonlocal directories_seen, files_seen, total_bytes_seen
        directory_before = os.fstat(descriptor)
        if not stat.S_ISDIR(directory_before.st_mode):
            raise NativeWorkerIOFailure(
                "native runtime snapshot opened a non-directory"
            )
        directory_identity = _native_runtime_stat_identity(directory_before)
        directories_seen += 1
        if (directories_seen > _NATIVE_RUNTIME_MAX_DIRECTORIES
                or len(records) >= _NATIVE_RUNTIME_MAX_ENTRIES):
            raise NativeWorkerIOFailure(
                "native worker runtime-tree directory/entry quota exceeded"
            )
        records.append({
            "relative_path": relative, "kind": "directory",
            "mode": stat.S_IMODE(directory_before.st_mode),
            "bytes": 0, "sha256": None,
        })
        names_before = scan_names(
            descriptor,
            max_names=_NATIVE_RUNTIME_MAX_ENTRIES - len(records),
        )
        for name in names_before:
            child_relative = name if relative == "." else f"{relative}/{name}"
            before = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
            before_identity = _native_runtime_stat_identity(before)
            if stat.S_ISLNK(before.st_mode):
                raise NativeWorkerIOFailure(
                    "native runtime snapshot contains a symlink"
                )
            if stat.S_ISDIR(before.st_mode):
                child_descriptor = os.open(
                    name, directory_flags, dir_fd=descriptor,
                )
                try:
                    if (_native_runtime_stat_identity(os.fstat(child_descriptor))
                            != before_identity):
                        raise NativeWorkerIOFailure(
                            "native runtime directory changed before hashing"
                        )
                    walk(child_descriptor, child_relative)
                finally:
                    os.close(child_descriptor)
                after = os.stat(name, dir_fd=descriptor, follow_symlinks=False)
                if _native_runtime_stat_identity(after) != before_identity:
                    raise NativeWorkerIOFailure(
                        "native runtime directory changed while hashing"
                    )
                continue
            if not stat.S_ISREG(before.st_mode):
                raise NativeWorkerIOFailure(
                    "native runtime snapshot contains a special file"
                )
            files_seen += 1
            total_bytes_seen += int(before.st_size)
            if (files_seen > _NATIVE_RUNTIME_MAX_FILES
                    or total_bytes_seen > _NATIVE_RUNTIME_MAX_BYTES
                    or len(records) >= _NATIVE_RUNTIME_MAX_ENTRIES):
                raise NativeWorkerIOFailure(
                    "native worker runtime-tree file/byte/entry quota exceeded"
                )
            file_descriptor = os.open(name, file_flags, dir_fd=descriptor)
            try:
                opened = os.fstat(file_descriptor)
                if _native_runtime_stat_identity(opened) != before_identity:
                    raise NativeWorkerIOFailure(
                        "native runtime file changed before hashing"
                    )
                digest, size = _native_runtime_file_sha256(file_descriptor)
                after_open = os.fstat(file_descriptor)
                if (_native_runtime_stat_identity(after_open) != before_identity
                        or size != int(before.st_size)):
                    raise NativeWorkerIOFailure(
                        "native runtime file changed while hashing"
                    )
            finally:
                os.close(file_descriptor)
            after_path = os.stat(
                name, dir_fd=descriptor, follow_symlinks=False,
            )
            if _native_runtime_stat_identity(after_path) != before_identity:
                raise NativeWorkerIOFailure(
                    "native runtime file changed while hashing"
                )
            records.append({
                "relative_path": child_relative, "kind": "file",
                "mode": stat.S_IMODE(before.st_mode),
                "bytes": size, "sha256": digest,
            })
        if scan_names(
            descriptor, max_names=len(names_before) + 1,
        ) != names_before:
            raise NativeWorkerIOFailure(
                "native runtime directory entries changed while hashing"
            )
        if (_native_runtime_stat_identity(os.fstat(descriptor))
                != directory_identity):
            raise NativeWorkerIOFailure(
                "native runtime directory changed while hashing"
            )

    try:
        root_before = os.lstat(absolute)
        if not stat.S_ISDIR(root_before.st_mode):
            raise NativeWorkerIOFailure(
                "native runtime snapshot root is not a regular directory"
            )
        root_descriptor = os.open(absolute, directory_flags)
        try:
            if (_native_runtime_stat_identity(os.fstat(root_descriptor))
                    != _native_runtime_stat_identity(root_before)):
                raise NativeWorkerIOFailure(
                    "native runtime root changed before hashing"
                )
            walk(root_descriptor, ".")
        finally:
            os.close(root_descriptor)
        if (_native_runtime_stat_identity(os.lstat(absolute))
                != _native_runtime_stat_identity(root_before)):
            raise NativeWorkerIOFailure(
                "native runtime root changed while hashing"
            )
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        raise NativeWorkerIOFailure("native runtime snapshot failed") from exc

    records.sort(key=lambda record: record["relative_path"])
    files = sum(record["kind"] == "file" for record in records)
    directories = sum(record["kind"] == "directory" for record in records)
    total_bytes = sum(record["bytes"] for record in records)
    payload = {
        "schema": _NATIVE_RUNTIME_OUTPUT_TREE_SCHEMA,
        "file_count": files, "directory_count": directories,
        "bytes": total_bytes, "entries": records,
    }
    snapshot = {
        **payload, "sha256": hashlib.sha256(_canonical_bytes(payload)).hexdigest(),
    }
    return _validate_native_runtime_output_snapshot(snapshot)


def _bounded_worker_lines(
    process: subprocess.Popen[bytes], *,
    total_timeout_seconds: float = _NATIVE_TOTAL_TIMEOUT_SECONDS,
    inactivity_timeout_seconds: float = _NATIVE_INACTIVITY_TIMEOUT_SECONDS,
    max_line_bytes: int = _NATIVE_MAX_LINE_BYTES,
    max_output_bytes: int = _NATIVE_MAX_OUTPUT_BYTES,
    runtime_root: Path | None = None,
    runtime_max_bytes: int = _NATIVE_RUNTIME_MAX_BYTES,
    runtime_max_files: int = _NATIVE_RUNTIME_MAX_FILES,
    runtime_max_directories: int = _NATIVE_RUNTIME_MAX_DIRECTORIES,
    runtime_max_entries: int = _NATIVE_RUNTIME_MAX_ENTRIES,
    runtime_observed: dict[str, int] | None = None,
    rss_limit_bytes: int = _NATIVE_RSS_LIMIT_BYTES,
    rss_poll_seconds: float = _NATIVE_RSS_POLL_SECONDS,
) -> Iterator[bytes]:
    """Yield newline-terminated bytes without permitting an unbounded worker."""
    if (process.stdout is None or total_timeout_seconds <= 0
            or inactivity_timeout_seconds <= 0 or max_line_bytes <= 0
            or max_output_bytes <= 0 or rss_limit_bytes <= 0
            or rss_poll_seconds <= 0
            or runtime_max_bytes <= 0 or runtime_max_files <= 0
            or runtime_max_directories <= 0 or runtime_max_entries <= 0):
        raise NativeWorkerIOFailure("native worker stream limits are invalid")
    try:
        descriptor = process.stdout.fileno()
        os.set_blocking(descriptor, False)
        selector = selectors.DefaultSelector()
        selector.register(descriptor, selectors.EVENT_READ)
    except (OSError, ValueError) as exc:
        raise NativeWorkerIOFailure("native worker stdout setup failed") from exc
    started = last_activity = time.monotonic()
    last_runtime_check = -math.inf
    last_rss_check = -math.inf
    total_bytes = 0
    buffered = bytearray()
    try:
        while True:
            now = time.monotonic()
            if now - last_rss_check >= rss_poll_seconds:
                _observe_native_process_group_rss(
                    process, limit_bytes=rss_limit_bytes,
                    observed=runtime_observed,
                )
                last_rss_check = now
            if runtime_root is not None and now - last_runtime_check >= 1.0:
                file_count, _, _, tree_bytes = _runtime_tree_usage(
                    runtime_root, max_bytes=runtime_max_bytes,
                    max_files=runtime_max_files,
                    max_directories=runtime_max_directories,
                    max_entries=runtime_max_entries,
                )
                if runtime_observed is not None:
                    runtime_observed["files"] = max(
                        runtime_observed.get("files", 0), file_count,
                    )
                    runtime_observed["bytes"] = max(
                        runtime_observed.get("bytes", 0), tree_bytes,
                    )
                if file_count > runtime_max_files or tree_bytes > runtime_max_bytes:
                    raise NativeWorkerIOFailure(
                        "native worker runtime-tree quota exceeded"
                    )
                last_runtime_check = now
            total_remaining = total_timeout_seconds - (now - started)
            inactive_remaining = inactivity_timeout_seconds - (now - last_activity)
            if total_remaining <= 0:
                raise NativeWorkerIOFailure("native worker total deadline exceeded")
            if inactive_remaining <= 0:
                raise NativeWorkerIOFailure("native worker inactivity deadline exceeded")
            try:
                events = selector.select(min(total_remaining, inactive_remaining, 0.5))
            except OSError as exc:
                raise NativeWorkerIOFailure("native worker stdout polling failed") from exc
            if not events:
                continue
            try:
                chunk = os.read(descriptor, 65_536)
            except BlockingIOError:
                continue
            except OSError as exc:
                raise NativeWorkerIOFailure("native worker stdout read failed") from exc
            if not chunk:
                if buffered:
                    raise NativeWorkerIOFailure("native worker emitted a partial line")
                return
            last_activity = time.monotonic()
            total_bytes += len(chunk)
            if total_bytes > max_output_bytes:
                raise NativeWorkerIOFailure("native worker total output cap exceeded")
            buffered.extend(chunk)
            while True:
                newline = buffered.find(b"\n")
                if newline < 0:
                    if len(buffered) > max_line_bytes:
                        raise NativeWorkerIOFailure("native worker line cap exceeded")
                    break
                line = bytes(buffered[:newline + 1])
                del buffered[:newline + 1]
                if len(line) > max_line_bytes:
                    raise NativeWorkerIOFailure("native worker line cap exceeded")
                yield line
    finally:
        selector.close()


def _native_sandbox_run_receipt(
    *, contract: Mapping[str, Any], profile: str,
    temporary_root: Path, parent_root: Path, request_path: Path,
    runtime_root: Path, environment: Mapping[str, str],
) -> dict[str, Any]:
    return {
        "schema": _NATIVE_SANDBOX_RUN_SCHEMA,
        "contract_sha256": _native_sandbox_contract_sha256(contract),
        "sandbox_executable": str(contract["sandbox_executable"]),
        "policy_sha256": hashlib.sha256(profile.encode("utf-8")).hexdigest(),
        "python_launcher": str(contract["python_launcher"]),
        "python_resolved": str(contract["python_resolved"]),
        "python_sha256": str(contract["python_sha256"]),
        "site_packages": str(contract["site_packages"]),
        "compiler_paths": dict(contract["compiler_paths"]),
        "sdk_root": str(contract["sdk_root"]),
        "python_flags": list(contract["python_flags"]),
        "runtime_read_paths": list(contract["runtime_read_paths"]),
        "process_exec_paths": list(contract["process_exec_paths"]),
        "file_read_metadata": str(contract["file_read_metadata"]),
        "path_resolution_literals": list(
            contract["path_resolution_literals"]
        ),
        "temporary_root": str(temporary_root),
        "parent_read_path": str(parent_root),
        "request_read_path": str(request_path),
        "runtime_read_write_path": str(runtime_root),
        "environment": dict(environment),
        "resource_limits": dict(contract["resource_limits"]),
        "isolated_process_group": True,
        "network": "deny",
    }


@contextlib.contextmanager
def _native_run_lock(
    *, artifact_root: Path, native_intent_sha256: str,
) -> Iterator[None]:
    """Serialize the global ordinal namespace from discovery through receipt."""
    if (not isinstance(native_intent_sha256, str)
            or not _HEX64.fullmatch(native_intent_sha256)):
        raise shots.LockMismatch("native run-lock identity is malformed")
    raw = b"epl-shots-native-global-run-1\n"
    nofollow = getattr(os, "O_NOFOLLOW", 0)
    descriptor = -1
    locked = False
    name_may_be_durable = False
    lock_complete = False
    body_failure: BaseException | None = None
    try:
        with _open_decision_state_directory(
            Path(artifact_root), create=True,
        ) as (_, directory_fd):
            if directory_fd is None:  # pragma: no cover - create=True invariant
                raise ManualReconciliationRequired(
                    "native artifact root creation is ambiguous"
                )
            name = ".native-run.lock"
            lock_created = False
            try:
                # O_CREAT can leave a name whose durability is unknowable when
                # the syscall or any later operation fails.
                name_may_be_durable = True
                try:
                    descriptor = os.open(
                        name,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | nofollow
                        | getattr(os, "O_CLOEXEC", 0),
                        0o444,
                        dir_fd=directory_fd,
                    )
                    lock_created = True
                    lock_info = os.fstat(descriptor)
                    if (not stat.S_ISREG(lock_info.st_mode)
                            or lock_info.st_nlink != 1):
                        raise shots.LockMismatch(
                            "new native run-lock is not one regular inode"
                        )
                except FileExistsError:
                    descriptor = os.open(
                        name,
                        os.O_RDONLY | nofollow
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory_fd,
                    )
                    opened_existing = os.fstat(descriptor)
                    named_existing = os.stat(
                        name, dir_fd=directory_fd, follow_symlinks=False,
                    )
                    if (opened_existing.st_size != len(raw)
                            or named_existing.st_size != len(raw)):
                        raise ManualReconciliationRequired(
                            "existing native run-lock may be incomplete"
                        )
                    lock_info = _decision_entry_identity(
                        directory_fd, name, descriptor,
                        label="native run-lock",
                    )

                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    locked = True
                except BlockingIOError as exc:
                    raise RunnerNotReady(
                        "matching native worker job is already running"
                    ) from exc

                if lock_created:
                    os.lseek(descriptor, 0, os.SEEK_SET)
                    written = 0
                    while written < len(raw):
                        count = os.write(descriptor, raw[written:])
                        if count <= 0:
                            raise OSError(
                                "native run-lock write made no progress"
                            )
                        written += count
                    os.fchmod(descriptor, 0o444)
                    os.fsync(descriptor)
                    _fsync_decision_state_directory(directory_fd)
                    lock_complete = True
                else:
                    os.fsync(descriptor)
                    _fsync_decision_state_directory(directory_fd)

                def require_current_lock() -> None:
                    current = _decision_entry_identity(
                        directory_fd, name, descriptor,
                        label="native run-lock",
                    )
                    if ((current.st_dev, current.st_ino)
                            != (lock_info.st_dev, lock_info.st_ino)):
                        raise shots.LockMismatch(
                            "native run-lock identity changed"
                        )
                    observed = _read_open_decision_entry_at(
                        directory_fd, name, descriptor,
                        label="native run-lock",
                    )
                    if observed != raw:
                        if not lock_complete and len(observed) != len(raw):
                            raise ManualReconciliationRequired(
                                "existing native run-lock may be incomplete"
                            )
                        raise shots.LockMismatch("native run-lock bytes differ")

                require_current_lock()
                lock_complete = True
                try:
                    try:
                        yield
                    except BaseException as exc:
                        body_failure = exc
                        raise
                finally:
                    require_current_lock()
            finally:
                active = sys.exc_info()[1]
                ambiguities: list[OSError] = []
                if locked:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except OSError as exc:
                        ambiguities.append(exc)
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except OSError as exc:
                        ambiguities.append(exc)
                descriptor = -1
                if ambiguities:
                    failure = ManualReconciliationRequired(
                        "native run-lock unlock/close state is ambiguous"
                    )
                    if active is not None:
                        raise failure from active
                    raise failure from ambiguities[0]
    except OSError as exc:
        if exc is body_failure:
            raise
        if name_may_be_durable:
            raise ManualReconciliationRequired(
                "native run-lock durable state is ambiguous"
            ) from exc
        raise NativeWorkerIOFailure("native run-lock I/O did not begin") from exc


@dataclass
class _NativeTemporaryLease:
    """Open-inode lease for one native temporary workspace.

    Retaining both the parent and workspace descriptors detects ordinary
    replacement without trusting a pathname that another same-UID process could
    replace.  The complete private workspace is deliberately retained after
    every exit for separately authorized, manual cleanup: POSIX has no atomic
    "unlink this name only if it still names inode X" operation.  A same-UID
    A->B->A swap that begins and ends between two checks is outside this
    host-level lease; a release run therefore still assumes a quiescent
    single-owner host.
    """

    path: Path
    name: str
    parent_path: Path
    parent_descriptor: int
    parent_identity: tuple[int, ...]
    descriptor: int
    identity: tuple[int, ...]
    children: list["_NativeChildLease"]
    nested_files: list["_NativeNestedFileLease"]
    compromised: bool = False


@dataclass(frozen=True)
class _NativeChildLease:
    path: Path
    name: str
    descriptor: int
    identity: tuple[int, ...]
    directory: bool
    label: str


@dataclass(frozen=True)
class _NativeNestedFileLease:
    path: Path
    name: str
    writer_descriptor: int
    reader_descriptor: int
    identity: tuple[int, ...]
    parent: _NativeChildLease
    label: str


def _native_lease_identity(value: os.stat_result) -> tuple[int, ...]:
    return (
        int(value.st_dev), int(value.st_ino), int(value.st_mode),
        int(value.st_uid), int(value.st_gid),
    )


def _native_file_lease_identity(value: os.stat_result) -> tuple[int, ...]:
    return _native_lease_identity(value) + (
        int(value.st_nlink), int(value.st_size), int(value.st_mtime_ns),
        int(value.st_ctime_ns),
    )


def _native_mutable_file_identity(value: os.stat_result) -> tuple[int, ...]:
    return _native_lease_identity(value) + (int(value.st_nlink),)


def _native_lease_refusal(
    lease: _NativeTemporaryLease, detail: str, exc: BaseException | None = None,
) -> NoReturn:
    lease.compromised = True
    failure = NativeWorkerIOFailure(
        f"native temporary workspace lease changed ({detail}); manual "
        f"reconciliation required at {lease.path}; automatic pathname cleanup "
        "refused"
    )
    if exc is None:
        raise failure
    raise failure from exc


def _verify_native_temporary_lease(lease: _NativeTemporaryLease) -> None:
    """Require the public pathname still to name the retained root inode."""
    try:
        opened_parent = os.fstat(lease.parent_descriptor)
        named_parent = os.stat(lease.parent_path, follow_symlinks=False)
        opened = os.fstat(lease.descriptor)
        named = os.stat(
            lease.name, dir_fd=lease.parent_descriptor, follow_symlinks=False,
        )
    except OSError as exc:
        _native_lease_refusal(lease, "temporary root is no longer visible", exc)
    if (not stat.S_ISDIR(opened_parent.st_mode)
            or _native_lease_identity(opened_parent) != lease.parent_identity
            or _native_lease_identity(named_parent) != lease.parent_identity
            or not stat.S_ISDIR(opened.st_mode)
            or _native_lease_identity(opened) != lease.identity
            or _native_lease_identity(named) != lease.identity):
        _native_lease_refusal(lease, "temporary root identity differs")


def _capture_native_child_lease(
    lease: _NativeTemporaryLease, name: str, *, directory: bool, label: str,
    expected_identity: tuple[int, ...] | None = None,
) -> _NativeChildLease:
    """Open a direct workspace child relative to the retained root inode."""
    _verify_native_temporary_lease(lease)
    if not name or name in (".", "..") or "/" in name:
        _native_lease_refusal(lease, f"{label} name is not a direct child")
    flags = os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0)
    if directory:
        flags |= os.O_DIRECTORY
    try:
        descriptor = os.open(name, flags, dir_fd=lease.descriptor)
        opened = os.fstat(descriptor)
        anchored = os.stat(
            name, dir_fd=lease.descriptor, follow_symlinks=False,
        )
        named = os.stat(lease.path / name, follow_symlinks=False)
    except OSError as exc:
        if 'descriptor' in locals():
            os.close(descriptor)
        _native_lease_refusal(lease, f"{label} could not be leased", exc)
    expected_kind = stat.S_ISDIR if directory else stat.S_ISREG
    identity_of = _native_lease_identity if directory \
        else _native_file_lease_identity
    identity = identity_of(opened)
    if (not expected_kind(opened.st_mode)
            or identity_of(anchored) != identity
            or identity_of(named) != identity
            or (expected_identity is not None
                and identity != expected_identity)):
        os.close(descriptor)
        _native_lease_refusal(lease, f"{label} identity differs at capture")
    child = _NativeChildLease(
        lease.path / name, name, descriptor, identity, directory, label,
    )
    lease.children.append(child)
    return child


def _verify_native_child_lease(
    workspace: _NativeTemporaryLease, child: _NativeChildLease,
) -> None:
    _verify_native_temporary_lease(workspace)
    try:
        opened = os.fstat(child.descriptor)
        anchored = os.stat(
            child.name, dir_fd=workspace.descriptor, follow_symlinks=False,
        )
        named = os.stat(child.path, follow_symlinks=False)
    except OSError as exc:
        _native_lease_refusal(
            workspace, f"{child.label} is no longer visible", exc,
        )
    expected_kind = stat.S_ISDIR if child.directory else stat.S_ISREG
    identity_of = _native_lease_identity if child.directory \
        else _native_file_lease_identity
    if (not expected_kind(opened.st_mode)
            or identity_of(opened) != child.identity
            or identity_of(anchored) != child.identity
            or identity_of(named) != child.identity):
        _native_lease_refusal(workspace, f"{child.label} identity differs")


def _native_leased_file_bytes(
    workspace: _NativeTemporaryLease, child: _NativeChildLease,
    *, max_bytes: int,
) -> bytes:
    if child.directory:
        _native_lease_refusal(workspace, f"{child.label} is not a file")
    _verify_native_child_lease(workspace, child)
    size = os.fstat(child.descriptor).st_size
    if size < 0 or size > max_bytes:
        _native_lease_refusal(workspace, f"{child.label} exceeds its byte limit")
    try:
        os.lseek(child.descriptor, 0, os.SEEK_SET)
        chunks: list[bytes] = []
        remaining = size
        while remaining:
            chunk = os.read(child.descriptor, min(remaining, 65_536))
            if not chunk:
                break
            chunks.append(chunk); remaining -= len(chunk)
    except OSError as exc:
        _native_lease_refusal(workspace, f"{child.label} could not be read", exc)
    raw = b"".join(chunks)
    _verify_native_child_lease(workspace, child)
    if len(raw) != size:
        _native_lease_refusal(workspace, f"{child.label} changed while read")
    return raw


def _write_native_descriptor(descriptor: int, raw: bytes, *, label: str) -> None:
    view = memoryview(raw)
    offset = 0
    try:
        while offset < len(view):
            written = os.write(descriptor, view[offset:])
            if written <= 0:
                raise OSError(f"{label} write made no progress")
            offset += written
    except OSError as exc:
        raise NativeWorkerIOFailure(f"{label} could not be written exactly") from exc


def _create_native_immutable_child(
    workspace: _NativeTemporaryLease, name: str, raw: bytes, *, label: str,
    mode: int = 0o400,
) -> _NativeChildLease:
    """Exclusively create and bind one immutable direct-workspace file."""
    _verify_native_temporary_lease(workspace)
    if not name or name in (".", "..") or "/" in name:
        _native_lease_refusal(workspace, f"{label} name is not a direct child")
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=workspace.descriptor,
        )
        _write_native_descriptor(descriptor, raw, label=label)
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        expected = _native_file_lease_identity(opened)
        anchored = os.stat(
            name, dir_fd=workspace.descriptor, follow_symlinks=False,
        )
        named = os.stat(workspace.path / name, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or _native_file_lease_identity(anchored) != expected
                or _native_file_lease_identity(named) != expected):
            _native_lease_refusal(
                workspace, f"{label} identity differs after exclusive create",
            )
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        _native_lease_refusal(
            workspace, f"{label} exclusive create was refused", exc,
        )
    finally:
        if descriptor >= 0:
            os.close(descriptor)
    child = _capture_native_child_lease(
        workspace, name, directory=False, label=label,
        expected_identity=expected,
    )
    if _native_leased_file_bytes(
        workspace, child, max_bytes=max(len(raw), 1),
    ) != raw:
        _native_lease_refusal(workspace, f"{label} readback differs")
    return child


def _create_native_direct_writer(
    workspace: _NativeTemporaryLease, name: str, *, label: str,
) -> int:
    """Exclusively create a direct-workspace output and retain its writer."""
    _verify_native_temporary_lease(workspace)
    if not name or name in (".", "..") or "/" in name:
        _native_lease_refusal(workspace, f"{label} name is not a direct child")
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=workspace.descriptor,
        )
        opened = os.fstat(descriptor)
        identity = _native_mutable_file_identity(opened)
        anchored = os.stat(
            name, dir_fd=workspace.descriptor, follow_symlinks=False,
        )
        named = os.stat(workspace.path / name, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or _native_mutable_file_identity(anchored) != identity
                or _native_mutable_file_identity(named) != identity):
            _native_lease_refusal(
                workspace, f"{label} identity differs after exclusive create",
            )
        return descriptor
    except NativeWorkerIOFailure:
        if descriptor >= 0:
            os.close(descriptor)
        raise
    except OSError as exc:
        if descriptor >= 0:
            os.close(descriptor)
        _native_lease_refusal(
            workspace, f"{label} exclusive create was refused", exc,
        )


def _finalize_native_direct_writer(
    workspace: _NativeTemporaryLease, name: str, descriptor: int, *,
    label: str, mode: int = 0o400,
) -> _NativeChildLease:
    """Seal a created direct output and bind a read lease to the same inode."""
    try:
        os.fchmod(descriptor, mode)
        os.fsync(descriptor)
        opened = os.fstat(descriptor)
        expected = _native_file_lease_identity(opened)
        anchored = os.stat(
            name, dir_fd=workspace.descriptor, follow_symlinks=False,
        )
        named = os.stat(workspace.path / name, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or _native_file_lease_identity(anchored) != expected
                or _native_file_lease_identity(named) != expected):
            _native_lease_refusal(
                workspace, f"{label} identity differs while sealing",
            )
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        _native_lease_refusal(workspace, f"{label} could not be sealed", exc)
    finally:
        os.close(descriptor)
    return _capture_native_child_lease(
        workspace, name, directory=False, label=label,
        expected_identity=expected,
    )


def _create_native_mutable_nested_file(
    workspace: _NativeTemporaryLease, parent: _NativeChildLease,
    name: str, *, label: str,
) -> _NativeNestedFileLease:
    """Create a mutable file under a retained directory without path writes."""
    _verify_native_child_lease(workspace, parent)
    if not parent.directory or not name or name in (".", "..") or "/" in name:
        _native_lease_refusal(workspace, f"{label} location is malformed")
    writer = reader = -1
    registered = False
    try:
        writer = os.open(
            name,
            os.O_WRONLY | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
            | getattr(os, "O_CLOEXEC", 0),
            0o600, dir_fd=parent.descriptor,
        )
        os.fchmod(writer, 0o600)
        os.fsync(writer)
        opened = os.fstat(writer)
        identity = _native_mutable_file_identity(opened)
        anchored = os.stat(
            name, dir_fd=parent.descriptor, follow_symlinks=False,
        )
        named = os.stat(parent.path / name, follow_symlinks=False)
        if (not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1
                or _native_mutable_file_identity(anchored) != identity
                or _native_mutable_file_identity(named) != identity):
            _native_lease_refusal(
                workspace, f"{label} identity differs after exclusive create",
            )
        reader = os.open(
            name,
            os.O_RDONLY | os.O_NOFOLLOW | getattr(os, "O_CLOEXEC", 0),
            dir_fd=parent.descriptor,
        )
        if (_native_mutable_file_identity(os.fstat(reader)) != identity
                or _native_mutable_file_identity(os.stat(
                    name, dir_fd=parent.descriptor, follow_symlinks=False,
                )) != identity):
            _native_lease_refusal(
                workspace, f"{label} reader does not bind the created inode",
            )
        _verify_native_child_lease(workspace, parent)
        nested = _NativeNestedFileLease(
            parent.path / name, name, writer, reader, identity, parent, label,
        )
        workspace.nested_files.append(nested)
        registered = True
        return nested
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        _native_lease_refusal(
            workspace, f"{label} exclusive create was refused", exc,
        )
    finally:
        if not registered:
            if reader >= 0:
                os.close(reader)
            if writer >= 0:
                os.close(writer)


def _verify_native_nested_file_lease(
    workspace: _NativeTemporaryLease, child: _NativeNestedFileLease,
) -> None:
    _verify_native_child_lease(workspace, child.parent)
    try:
        writer = os.fstat(child.writer_descriptor)
        reader = os.fstat(child.reader_descriptor)
        anchored = os.stat(
            child.name, dir_fd=child.parent.descriptor,
            follow_symlinks=False,
        )
        named = os.stat(child.path, follow_symlinks=False)
    except OSError as exc:
        _native_lease_refusal(
            workspace, f"{child.label} is no longer visible", exc,
        )
    if (not stat.S_ISREG(writer.st_mode) or not stat.S_ISREG(reader.st_mode)
            or _native_mutable_file_identity(writer) != child.identity
            or _native_mutable_file_identity(reader) != child.identity
            or _native_mutable_file_identity(anchored) != child.identity
            or _native_mutable_file_identity(named) != child.identity):
        _native_lease_refusal(workspace, f"{child.label} identity differs")


def _native_nested_file_tail(
    workspace: _NativeTemporaryLease, child: _NativeNestedFileLease,
    *, limit: int = 8_192,
) -> str:
    if type(limit) is not int or limit <= 0:
        _native_lease_refusal(workspace, f"{child.label} tail limit is invalid")
    try:
        os.fsync(child.writer_descriptor)
        _verify_native_nested_file_lease(workspace, child)
        size = int(os.fstat(child.reader_descriptor).st_size)
        os.lseek(child.reader_descriptor, max(0, size - limit), os.SEEK_SET)
        raw = os.read(child.reader_descriptor, min(size, limit))
        _verify_native_nested_file_lease(workspace, child)
    except NativeWorkerIOFailure:
        raise
    except OSError as exc:
        _native_lease_refusal(workspace, f"{child.label} tail could not be read", exc)
    return raw.decode("utf-8", "replace").strip()


def _verify_native_workspace_lease(
    workspace: _NativeTemporaryLease, *, parent: _NativeChildLease,
    parent_snapshot: Mapping[str, Any], request: _NativeChildLease,
    request_raw: bytes, runtime: _NativeChildLease,
    verify_parent_tree: bool,
) -> None:
    """Revalidate all path leases and immutable native inputs.

    This closes ordinary one-way pathname replacement.  It cannot prove that
    an adversarial same-UID process did not perform an A->B->A swap wholly
    between checks; release execution therefore requires a quiescent host (or
    an external immutable VM/snapshot boundary).
    """
    for child in (parent, request, runtime):
        _verify_native_child_lease(workspace, child)
    if _native_leased_file_bytes(
        workspace, request, max_bytes=max(len(request_raw), 1),
    ) != request_raw:
        _native_lease_refusal(workspace, "native request bytes differ")
    if verify_parent_tree:
        try:
            observed = _native_runtime_output_snapshot(parent.path)
        except (OSError, NativeWorkerIOFailure, shots.LockMismatch) as exc:
            _native_lease_refusal(
                workspace, "parent/raw input tree could not be resnapshotted", exc,
            )
        _verify_native_child_lease(workspace, parent)
        if _canonical_bytes(observed) != _canonical_bytes(parent_snapshot):
            _native_lease_refusal(workspace, "parent/raw input tree differs")


@contextlib.contextmanager
def _native_temporary_root_lease(
    parent: Path,
) -> Iterator[_NativeTemporaryLease]:
    """Create an inode-leased workspace retained for deferred manual cleanup.

    The lease path is also recorded in a successful sandbox run receipt.  On a
    failure it is included in the typed reconciliation error.  This context
    never unlinks, removes, renames, chmods, or otherwise mutates an entry after
    its final separable identity check.
    """
    parent_path = Path(os.path.abspath(os.fspath(parent)))
    flags = (
        os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW
        | getattr(os, "O_CLOEXEC", 0)
    )
    try:
        parent_descriptor = os.open(parent_path, flags)
    except OSError as exc:
        raise NativeWorkerIOFailure(
            "native temporary parent could not be inode-leased"
        ) from exc
    root_descriptor = -1
    lease: _NativeTemporaryLease | None = None
    created: Path | None = None
    try:
        parent_identity = _native_lease_identity(os.fstat(parent_descriptor))
        try:
            created = Path(tempfile.mkdtemp(
                prefix="epl-shots-native-", dir=parent_path,
            ))
        except OSError as exc:
            raise NativeWorkerIOFailure(
                "native temporary workspace could not be created"
            ) from exc
        try:
            root_descriptor = os.open(
                created.name, flags, dir_fd=parent_descriptor,
            )
        except OSError as exc:
            raise NativeWorkerIOFailure(
                f"new native temporary root at {created} could not be "
                "inode-leased; manual reconciliation required; automatic "
                "pathname cleanup refused"
            ) from exc
        identity = _native_lease_identity(os.fstat(root_descriptor))
        lease = _NativeTemporaryLease(
            created, created.name, parent_path, parent_descriptor,
            parent_identity, root_descriptor, identity, [], [],
        )
        _verify_native_temporary_lease(lease)
        try:
            yield lease
        finally:
            active = sys.exc_info()[1]
            if active is not None:
                active.add_note(
                    f"native temporary workspace retained for manual cleanup: "
                    f"{lease.path}"
                )
            final_failure: BaseException | None = None
            try:
                _verify_native_temporary_lease(lease)
            except NativeWorkerIOFailure as exc:
                final_failure = exc
            if final_failure is None:
                for child in lease.children:
                    try:
                        _verify_native_child_lease(lease, child)
                    except NativeWorkerIOFailure as exc:
                        final_failure = exc
                        break
            if final_failure is None:
                for child in lease.nested_files:
                    try:
                        _verify_native_nested_file_lease(lease, child)
                    except NativeWorkerIOFailure as exc:
                        final_failure = exc
                        break
            for child in reversed(lease.nested_files):
                for descriptor in (
                    child.reader_descriptor, child.writer_descriptor,
                ):
                    try:
                        os.close(descriptor)
                    except OSError:
                        lease.compromised = True
            lease.nested_files.clear()
            for child in reversed(lease.children):
                try:
                    os.close(child.descriptor)
                except OSError:
                    lease.compromised = True
            lease.children.clear()
            if final_failure is not None:
                if active is None:
                    raise final_failure
                raise ManualReconciliationRequired(
                    f"native workspace at {lease.path} failed final "
                    "verification while another result was pending"
                ) from active
            if lease.compromised:
                if active is None:
                    raise ManualReconciliationRequired(
                        f"native temporary workspace at {lease.path} requires "
                        "manual reconciliation"
                    )
                raise ManualReconciliationRequired(
                    f"native temporary workspace at {lease.path} needs manual "
                    "reconciliation while another result was pending"
                ) from active
    finally:
        active = sys.exc_info()[1]
        close_failure: OSError | None = None
        for descriptor in (root_descriptor, parent_descriptor):
            if descriptor < 0:
                continue
            try:
                os.close(descriptor)
            except OSError as exc:
                close_failure = close_failure or exc
        if close_failure is not None:
            if active is None:
                raise ManualReconciliationRequired(
                    "native temporary workspace descriptors did not close"
                ) from close_failure
            raise ManualReconciliationRequired(
                "native temporary workspace descriptor cleanup failed while "
                "another result was pending"
            ) from active


def _run_native_training_blocks_after_h(
    *, h_commit: str, artifact_root: Path = _ARTIFACT_ROOT,
) -> tuple[dict[str, Any], ...]:
    """Continuously drain and persist exact-parent native blocks after H.

    The coordinator owns the pipe, watchdog, and durable shard writes; it never
    yields control while the child is live.  Resume state is discovered only
    from shards covered by a clean-exit job receipt.  Nothing calls this private
    function yet; ``run_training`` remains fail-closed.
    """
    artifact_root = _fixed_repo_artifact_root(artifact_root)
    initial_h = verify_harness_live(h_commit)
    try:
        prior_refusal = _existing_native_refusal(
            h=initial_h,
            training_sha256=initial_h.training_schedule_sha256,
            artifact_root=artifact_root,
        )
    except shots.ShotsError as exc:
        raise ManualReconciliationRequired(
            "existing native refusal chain needs manual reconciliation"
        ) from exc
    if prior_refusal is not None:
        record, _, refusal = prior_refusal
        refusal.add_note(
            f"durable native refusal receipt: {record['sha256']}"
        )
        raise refusal
    training_sha, schedule = _training_binding()
    if training_sha != initial_h.training_schedule_sha256:
        raise shots.LockMismatch("live H training schedule changed before native run")
    temp_parent = _componentwise_regular_path(_NATIVE_TEMP_PARENT, create=False)
    if not temp_parent.is_dir():
        raise NativeWorkerSandboxStop("fixed native temp parent is unavailable")
    for protected in (_ROOT, artifact_root):
        if (temp_parent == protected or temp_parent in protected.parents
                or protected in temp_parent.parents):
            raise NativeWorkerSandboxStop(
                "native temp parent overlaps repo/artifact paths"
            )
    completion_publication: _PendingNativeCompletionPublication | None = None
    with (_native_completion_publication_boundary(
              artifact_root=artifact_root,
          ) as completion_publication,
          _native_semantic_publication_boundary(
              h=initial_h, training_sha256=training_sha,
              artifact_root=artifact_root,
          ) as semantic_publication,
          _native_temporary_root_lease(temp_parent) as temporary_lease,
          contextlib.ExitStack() as protections):
        temporary_root = temporary_lease.path
        parent_root = temporary_root / "parent"
        _, parent_lease = _materialize_native_parent(
            parent_root, workspace=temporary_lease,
        )
        raw_inputs = _install_native_raw_inputs(
            parent_root, workspace=temporary_lease,
            parent_lease=parent_lease,
        )
        parent_snapshot = _native_runtime_output_snapshot(parent_root)
        _verify_native_child_lease(temporary_lease, parent_lease)
        if initial_h.native_runtime_lock is None:
            raise shots.LockMismatch("live H did not provide a native runtime lock")
        sandbox_contract, runtime_binding_lease = (
            _require_live_native_sandbox_contract(
                initial_h.native_runtime_lock,
            )
        )
        native_intent, native_intent_sha256, blocks = _native_intent(
            h=initial_h, training_sha256=training_sha, schedule=schedule,
            raw_inputs=raw_inputs, sandbox_contract=sandbox_contract,
        )
        intent_record, _ = _write_decision_artifact_once(
            "native_intent", native_intent, artifact_root=artifact_root,
        )
        if intent_record["sha256"] != native_intent_sha256:
            raise shots.LockMismatch("native intent artifact digest differs")
        protections.enter_context(_native_run_lock(
            artifact_root=artifact_root,
            native_intent_sha256=native_intent_sha256,
        ))
        # §8.5 permits retry only from matching content-addressed shards.  A
        # crash can leave a valid block before its clean completion receipt;
        # bind every such orphan now so a retry must reproduce the same digest
        # rather than silently creating an ordinal fork.
        observed_shards = _discover_native_block_shards(
            artifact_root=artifact_root,
        )
        observed_by_ordinal: dict[int, dict[str, Any]] = {}
        with _open_decision_state_directory(
            artifact_root, create=False,
        ) as (_, shard_directory_fd):
            if observed_shards and shard_directory_fd is None:
                raise shots.LockMismatch("native shard namespace disappeared")
            for shard_record, shard_value in observed_shards:
                ordinal = int(shard_value["block_ordinal"])
                validated = _validate_native_block(
                    shard_value,
                    native_intent_sha256=native_intent_sha256,
                    h=initial_h, training_sha256=training_sha,
                    raw_inputs=raw_inputs, expected_ordinal=ordinal,
                    blocks=blocks,
                )
                if shard_directory_fd is None:  # pragma: no cover - guarded
                    raise shots.LockMismatch("native shard namespace is absent")
                _require_digest_at(
                    shard_directory_fd, f"native-block-{ordinal:03d}",
                    str(shard_record["sha256"]),
                )
                observed_by_ordinal[ordinal] = dict(shard_record)
        covered = _discover_completed_native_block_shards(
            artifact_root=artifact_root,
            native_intent=native_intent,
            native_intent_sha256=native_intent_sha256,
            h=initial_h, training_sha256=training_sha,
            raw_inputs=raw_inputs, blocks=blocks,
            sandbox_contract=sandbox_contract,
        )
        for record, value in covered:
            ordinal = int(value["block_ordinal"])
            if observed_by_ordinal.get(ordinal) != dict(record):
                raise shots.LockMismatch(
                    f"native block {ordinal} completion/orphan inventory differs"
                )
        completed = {int(value["block_ordinal"]) for _, value in covered}
        remaining = tuple(
            ordinal for ordinal in range(len(blocks)) if ordinal not in completed
        )
        if not remaining:
            return tuple(record for record, _ in covered)
        request = _native_request(
            native_intent=native_intent,
            native_intent_sha256=native_intent_sha256,
            block_ordinals=remaining, block_count=len(blocks),
        )
        request_raw = _canonical_bytes(request)
        job_request_sha256 = hashlib.sha256(request_raw).hexdigest()
        request_path = temporary_root / "native-request.json"
        request_lease = _create_native_immutable_child(
            temporary_lease, request_path.name, request_raw,
            label="native request",
        )
        runtime_root = temporary_root / "runtime"
        try:
            os.mkdir("runtime", 0o700, dir_fd=temporary_lease.descriptor)
        except OSError as exc:
            _native_lease_refusal(
                temporary_lease,
                "native runtime root exclusive create was refused", exc,
            )
        runtime_lease = _capture_native_child_lease(
            temporary_lease, "runtime", directory=True,
            label="native runtime root",
        )
        stderr_path = runtime_root / "native-stderr.log"
        environment = _native_minimal_environment(
            contract=sandbox_contract, parent_root=parent_root,
            request_path=request_path, runtime_root=runtime_root,
        )
        profile = _native_sandbox_profile(
            contract=sandbox_contract, temporary_root=temporary_root,
            parent_root=parent_root, request_path=request_path,
            runtime_root=runtime_root,
        )
        command = _native_sandbox_command(
            contract=sandbox_contract, profile=profile,
            source=_NATIVE_WORKER_SOURCE,
        )
        _verify_native_workspace_lease(
            temporary_lease, parent=parent_lease,
            parent_snapshot=parent_snapshot, request=request_lease,
            request_raw=request_raw, runtime=runtime_lease,
            verify_parent_tree=True,
        )
        _native_sandbox_preflight(
            command=command, environment=environment, cwd=parent_root,
            runtime_contract=sandbox_contract,
            runtime_binding_lease=runtime_binding_lease,
        )
        _verify_native_workspace_lease(
            temporary_lease, parent=parent_lease,
            parent_snapshot=parent_snapshot, request=request_lease,
            request_raw=request_raw, runtime=runtime_lease,
            verify_parent_tree=True,
        )
        sandbox_run = _native_sandbox_run_receipt(
            contract=sandbox_contract, profile=profile,
            temporary_root=temporary_root, parent_root=parent_root,
            request_path=request_path, runtime_root=runtime_root,
            environment=environment,
        )
        process: subprocess.Popen[bytes] | None = None
        yielded_records: list[dict[str, Any]] = []
        output_bytes = 0
        runtime_observed = {"files": 0, "bytes": 0, "rss_bytes": 0}
        stderr_lease = _create_native_mutable_nested_file(
            temporary_lease, runtime_lease, "native-stderr.log",
            label="native worker stderr",
        )
        try:
            stderr_duplicate = -1
            try:
                stderr_duplicate = os.dup(stderr_lease.writer_descriptor)
                stderr_context = os.fdopen(
                    stderr_duplicate, "wb",
                )
                stderr_duplicate = -1
            except OSError as exc:
                if stderr_duplicate >= 0:
                    os.close(stderr_duplicate)
                raise NativeWorkerIOFailure(
                    "native worker stderr descriptor could not be duplicated"
                ) from exc
            with stderr_context as stderr:
                try:
                    _verify_native_workspace_lease(
                        temporary_lease, parent=parent_lease,
                        parent_snapshot=parent_snapshot,
                        request=request_lease, request_raw=request_raw,
                        runtime=runtime_lease, verify_parent_tree=True,
                    )
                    _verify_native_nested_file_lease(
                        temporary_lease, stderr_lease,
                    )
                    _verify_native_runtime_binding_lease(
                        sandbox_contract, runtime_binding_lease,
                    )
                    # The preflight monitor probe is not reusable authority:
                    # prove the pinned process-table monitor can still launch
                    # immediately before the real worker exists.
                    _require_native_process_group_monitor()
                    process = subprocess.Popen(
                        command, cwd=parent_root, env=environment,
                        stdin=subprocess.DEVNULL, stdout=subprocess.PIPE,
                        stderr=stderr, text=False, bufsize=0,
                        start_new_session=True,
                        preexec_fn=_apply_native_resource_limits,
                    )
                except (OSError, subprocess.SubprocessError) as exc:
                    raise NativeWorkerSandboxStop(
                        f"native sandbox worker could not launch: {type(exc).__name__}"
                    ) from exc
                yielded = 0
                semantic_stop: shots.ShotsError | None = None
                semantic_value: dict[str, Any] | None = None
                for raw_line in _bounded_worker_lines(
                    process, runtime_root=runtime_root,
                    runtime_observed=runtime_observed,
                ):
                    output_bytes += len(raw_line)
                    try:
                        line = raw_line.decode("ascii")
                        value = json.loads(line)
                        if _canonical_bytes(value) != raw_line:
                            raise ValueError("not canonical")
                    except (UnicodeError, json.JSONDecodeError, TypeError,
                            ValueError, RecursionError) as exc:
                        raise shots.LockMismatch(
                            f"native worker emitted noncanonical output: {exc}"
                        ) from exc
                    semantic_refusal = _native_semantic_refusal(
                        value,
                        native_intent_sha256=native_intent_sha256,
                        job_request_sha256=job_request_sha256,
                        h=initial_h, training_sha256=training_sha,
                    )
                    if semantic_refusal is not None:
                        if semantic_stop is not None:
                            raise shots.LockMismatch(
                                "native worker emitted multiple semantic refusals"
                            )
                        semantic_stop = semantic_refusal
                        semantic_value = dict(value)
                        continue
                    if semantic_stop is not None:
                        raise shots.LockMismatch(
                            "native worker emitted output after its semantic refusal"
                        )
                    if yielded >= len(remaining):
                        raise shots.LockMismatch("native worker emitted an extra block")
                    block = _validate_native_block(
                        value, native_intent_sha256=native_intent_sha256,
                        h=initial_h, training_sha256=training_sha,
                        raw_inputs=raw_inputs,
                        expected_ordinal=remaining[yielded], blocks=blocks,
                    )
                    _verify_harness_identity_live(initial_h)
                    _verify_native_workspace_lease(
                        temporary_lease, parent=parent_lease,
                        parent_snapshot=parent_snapshot,
                        request=request_lease, request_raw=request_raw,
                        runtime=runtime_lease, verify_parent_tree=False,
                    )
                    yielded += 1
                    yielded_records.append(_write_native_block_shard(
                        block, artifact_root=artifact_root,
                    ))
                _wait_native_process_with_rss_limit(
                    process, timeout_seconds=30,
                    observed=runtime_observed,
                )
                returncode, had_nonleaders = _close_native_process_group(
                    process, leader_must_have_exited=True,
                )
                process = None
            try:
                os.fsync(stderr_lease.writer_descriptor)
            except OSError as exc:
                _native_lease_refusal(
                    temporary_lease, "native worker stderr could not be synced",
                    exc,
                )
            _verify_native_nested_file_lease(temporary_lease, stderr_lease)
            if semantic_stop is not None:
                if returncode == 0 or semantic_value is None:
                    raise shots.LockMismatch(
                        "native worker semantic refusal exited successfully"
                    )
                if had_nonleaders:
                    raise NativeWorkerIOFailure(
                        "native refusal left a descendant after leader exit"
                    )
                post_launch_contract = _native_sandbox_contract()
                post_launch_runtime_binding_lease = (
                    _capture_confirmed_native_runtime_binding_lease(
                        post_launch_contract,
                    )
                )
                runtime_contract_changed = (
                    _canonical_bytes(post_launch_contract)
                    != _canonical_bytes(sandbox_contract)
                )
                _verify_native_workspace_lease(
                    temporary_lease, parent=parent_lease,
                    parent_snapshot=parent_snapshot, request=request_lease,
                    request_raw=request_raw, runtime=runtime_lease,
                    verify_parent_tree=True,
                )
                refusal_runtime_snapshot = _native_runtime_output_snapshot(
                    runtime_root
                )
                final_files = refusal_runtime_snapshot["file_count"]
                final_bytes = refusal_runtime_snapshot["bytes"]
                runtime_observed["files"] = max(
                    runtime_observed["files"], final_files,
                )
                runtime_observed["bytes"] = max(
                    runtime_observed["bytes"], final_bytes,
                )
                if (final_files > _NATIVE_RUNTIME_MAX_FILES
                        or final_bytes > _NATIVE_RUNTIME_MAX_BYTES):
                    raise NativeWorkerIOFailure(
                        "native refusal runtime-tree quota exceeded"
                    )
                _verify_harness_identity_live(initial_h)
                _verify_native_workspace_lease(
                    temporary_lease, parent=parent_lease,
                    parent_snapshot=parent_snapshot, request=request_lease,
                    request_raw=request_raw, runtime=runtime_lease,
                    verify_parent_tree=True,
                )
                _verify_native_runtime_binding_lease(
                    post_launch_contract,
                    post_launch_runtime_binding_lease,
                )
                refusal_receipt = _make_native_refusal_receipt(
                    semantic_refusal=semantic_value, h=initial_h,
                    refusal_source=(
                        "parent_runtime_closure_mismatch"
                        if runtime_contract_changed
                        else "worker_semantic_refusal"
                    ),
                    training_sha256=training_sha,
                    native_intent=native_intent,
                    native_intent_record=intent_record,
                    job_ordinals=remaining,
                    block_records=yielded_records,
                    output_bytes=output_bytes, exit_code=returncode,
                    sandbox_contract=sandbox_contract,
                    sandbox_run=sandbox_run,
                    runtime_snapshot=refusal_runtime_snapshot,
                    runtime_observed=runtime_observed,
                    post_launch_sandbox_contract=post_launch_contract,
                )
                terminal_refusal = semantic_stop
                if runtime_contract_changed:
                    terminal_refusal = _native_semantic_refusal(
                        refusal_receipt["semantic_refusal"]["terminal_event"],
                        native_intent_sha256=native_intent_sha256,
                        job_request_sha256=job_request_sha256,
                        h=initial_h, training_sha256=training_sha,
                        allow_parent_runtime_mismatch=True,
                    )
                    if terminal_refusal is None:  # pragma: no cover - builder
                        raise shots.LockMismatch(
                            "native runtime mismatch terminal event is absent"
                        )
                semantic_publication.arm(refusal_receipt, terminal_refusal)
            if returncode:
                detail = _native_nested_file_tail(
                    temporary_lease, stderr_lease,
                )
                message = f"historical native worker exited {returncode}: {detail}"
                # A child-process exit is not itself a scientific/data
                # refusal.  With no structured semantic receipt, preregistered
                # crash recovery may retry only the still-uncovered ordinals.
                raise NativeWorkerIOFailure(message)
            if had_nonleaders:
                raise NativeWorkerIOFailure(
                    "native worker left a descendant after clean leader exit"
                )
            post_launch_contract = _native_sandbox_contract()
            post_launch_runtime_binding_lease = (
                _capture_confirmed_native_runtime_binding_lease(
                    post_launch_contract,
                )
            )
            runtime_contract_changed = (
                _canonical_bytes(post_launch_contract)
                != _canonical_bytes(sandbox_contract)
            )
            _verify_native_workspace_lease(
                temporary_lease, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )
            runtime_snapshot = _native_runtime_output_snapshot(runtime_root)
            _verify_native_workspace_lease(
                temporary_lease, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )
            final_files = runtime_snapshot["file_count"]
            final_bytes = runtime_snapshot["bytes"]
            runtime_observed["files"] = max(runtime_observed["files"], final_files)
            runtime_observed["bytes"] = max(runtime_observed["bytes"], final_bytes)
            if (final_files > _NATIVE_RUNTIME_MAX_FILES
                    or final_bytes > _NATIVE_RUNTIME_MAX_BYTES):
                raise NativeWorkerIOFailure(
                    "native worker runtime-tree quota exceeded at completion"
                )
            _verify_harness_identity_live(initial_h)
            _verify_native_workspace_lease(
                temporary_lease, parent=parent_lease,
                parent_snapshot=parent_snapshot, request=request_lease,
                request_raw=request_raw, runtime=runtime_lease,
                verify_parent_tree=True,
            )
            _verify_native_runtime_binding_lease(
                post_launch_contract,
                post_launch_runtime_binding_lease,
            )
            if runtime_contract_changed:
                refusal_receipt = _make_native_refusal_receipt(
                    semantic_refusal=None,
                    refusal_source="parent_runtime_closure_mismatch",
                    h=initial_h, training_sha256=training_sha,
                    native_intent=native_intent,
                    native_intent_record=intent_record,
                    job_ordinals=remaining,
                    block_records=yielded_records,
                    output_bytes=output_bytes, exit_code=returncode,
                    sandbox_contract=sandbox_contract,
                    sandbox_run=sandbox_run,
                    runtime_snapshot=runtime_snapshot,
                    runtime_observed=runtime_observed,
                    post_launch_sandbox_contract=post_launch_contract,
                )
                terminal_refusal = _native_semantic_refusal(
                    refusal_receipt["semantic_refusal"]["terminal_event"],
                    native_intent_sha256=native_intent_sha256,
                    job_request_sha256=job_request_sha256,
                    h=initial_h, training_sha256=training_sha,
                    allow_parent_runtime_mismatch=True,
                )
                if terminal_refusal is None:  # pragma: no cover - builder
                    raise shots.LockMismatch(
                        "native runtime mismatch terminal event is absent"
                    )
                semantic_publication.arm(refusal_receipt, terminal_refusal)
            if yielded != len(remaining):
                raise shots.FitFailure(
                    f"historical native worker returned {yielded} blocks, "
                    f"expected {len(remaining)}"
                )
            completion = _make_native_completion_receipt(
                native_intent_sha256=native_intent_sha256,
                job_request_sha256=job_request_sha256,
                job_ordinals=remaining, block_records=yielded_records,
                sandbox_run=sandbox_run, output_bytes=output_bytes,
                runtime_snapshot=runtime_snapshot,
                runtime_observed=runtime_observed,
            )
            completion_publication.arm(
                completion, native_intent=native_intent,
                native_intent_sha256=native_intent_sha256,
                h=initial_h, training_sha256=training_sha,
                raw_inputs=raw_inputs, blocks=blocks,
                sandbox_contract=sandbox_contract,
            )
        finally:
            if process is not None:
                active = sys.exc_info()[1]
                try:
                    _terminate_native_process_group(process)
                except NativeWorkerIOFailure as cleanup_failure:
                    if active is None:
                        raise ManualReconciliationRequired(
                            "native worker process-group cleanup needs manual "
                            "reconciliation"
                        ) from cleanup_failure
                    raise ManualReconciliationRequired(
                        "native worker process-group cleanup failed while "
                        "another result was pending"
                    ) from active
    if completion_publication is None or completion_publication.records is None:
        raise ManualReconciliationRequired(
            "native completion publication boundary returned no records"
        )
    return completion_publication.records


def verify_harness_live(h_commit: str) -> _VerifiedH:
    """Reread fixed H/current bytes; return no reusable authority token."""
    h = _commit(h_commit, label="H")
    manifest, _ = _read_canonical(_H_PATH, label="H manifest")
    status = shots.require_harness_manifest(
        manifest, repo_root=_ROOT, harness_commit=h, rev="HEAD",
    )
    training_sha, _ = _training_binding()
    decision_sha, _ = decision_schedule_binding()
    runtime_lock = manifest.get("native_runtime_lock")
    if not isinstance(runtime_lock, Mapping):
        raise shots.LockMismatch("H native runtime lock is absent")
    verified = _VerifiedH(
        h, status["manifest_payload_sha256"], training_sha, decision_sha,
        json.loads(json.dumps(runtime_lock)),
    )
    # Close the verifier over the exact mutable bytes it just inspected.  A
    # caller must never receive authority assembled from an early manifest and
    # later schedules after either changed mid-verification.
    _verify_harness_identity_live(verified)
    return verified


def _verify_harness_identity_live(expected: _VerifiedH) -> None:
    """Cheap mid-job H check; runtime bytes are leased at job boundaries.

    The full verifier performs the expensive mutable-runtime tree scan before
    launch and again before a clean completion receipt.  Between individual
    streamed blocks, this check protects the committed/working H bytes and both
    outcome-free schedules without rehashing gigabytes of toolchain data.
    """
    h = _commit(expected.commit, label="H")
    manifest, raw = _read_canonical(_H_PATH, label="H manifest")
    if (hashlib.sha256(raw).hexdigest() != expected.manifest_sha256
            or _git_bytes("show", f"{h}:{shots.H_MANIFEST_PATH}") != raw
            or not _git_succeeds("merge-base", "--is-ancestor", h, "HEAD")):
        raise shots.LockMismatch("live H identity changed during the native job")
    files = manifest.get("files")
    if not isinstance(files, Mapping) or set(files) != set(shots.H_REQUIRED_FILES):
        raise shots.LockMismatch("live H file set changed during the native job")
    for relative, record in files.items():
        path = _ROOT / str(relative)
        if (not isinstance(record, Mapping)
                or shots.sha256_file(path) != record.get("sha256")
                or hashlib.sha256(
                    _git_bytes("show", f"{h}:{relative}")
                ).hexdigest() != record.get("sha256")):
            raise shots.LockMismatch(
                f"live H file changed during the native job: {relative}"
            )
    training_sha, _ = _training_binding()
    decision_sha, _ = decision_schedule_binding()
    if (training_sha != expected.training_schedule_sha256
            or decision_sha != expected.decision_schedule_sha256):
        raise shots.LockMismatch("live H schedule changed during the native job")


def _keys(value: Mapping[str, Any], expected: set[str], *, label: str) -> None:
    if set(value) != expected:
        raise shots.LockMismatch(f"{label} fields differ from its frozen schema")


def _finite_vector(value: Any, n: int, *, label: str) -> tuple[float, ...]:
    if not isinstance(value, list) or len(value) != n:
        raise shots.LockMismatch(f"{label} must contain exactly {n} numbers")
    if any(type(v) not in (int, float) or not math.isfinite(float(v)) for v in value):
        raise shots.LockMismatch(f"{label} contains a nonfinite/non-numeric value")
    return tuple(float(v) for v in value)


# ==========================================================================
# PRE-H persistence: immutable content-addressed shards and K2 artifacts
# ==========================================================================

def _componentwise_regular_path(path: Path, *, create: bool) -> Path:
    """Return an absolute directory after refusing every symlink component."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    existing: list[Path] = []
    cursor = absolute
    while True:
        if cursor.exists() or cursor.is_symlink():
            existing.append(cursor)
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    for component in reversed(existing):
        if component.is_symlink():
            raise shots.LockMismatch(
                f"artifact path contains a symlink component: {component}"
            )
        if component != absolute and not component.is_dir():
            raise shots.LockMismatch(
                f"artifact path ancestor is not a directory: {component}"
            )
    if create:
        absolute.mkdir(parents=True, exist_ok=True)
    if not absolute.exists():
        return absolute
    # Rewalk after mkdir to catch symlinked components introduced concurrently.
    cursor = absolute
    while True:
        if cursor.is_symlink():
            raise shots.LockMismatch(
                f"artifact path contains a symlink component: {cursor}"
            )
        if cursor.parent == cursor:
            break
        cursor = cursor.parent
    if not absolute.is_dir():
        raise shots.LockMismatch("artifact root is not a directory")
    return absolute


def _fixed_repo_artifact_root(value: Path) -> Path:
    root = _componentwise_regular_path(value, create=False)
    repo = _componentwise_regular_path(_ROOT, create=False)
    try:
        root.relative_to(repo)
    except ValueError as exc:
        raise shots.LockMismatch("production artifact root escapes the real repo") from exc
    if root != _ARTIFACT_ROOT:
        raise shots.LockMismatch("production artifact root is not the fixed shots root")
    return root

def _k2_filename(logical: str, digest: str, *, ordinal: int | None = None) -> str:
    schemas = _k2_schemas()
    if logical not in schemas or not _HEX64.fullmatch(digest):
        raise shots.LockMismatch("K2 logical name or digest is invalid")
    if logical == "native_block":
        if type(ordinal) is not int or ordinal < 0:
            raise shots.LockMismatch("native block artifact requires an ordinal")
        return f"native-block-{ordinal:03d}-{digest}.json"
    if logical == "decision_prediction_block":
        if type(ordinal) is not int or not 0 <= ordinal < _DECISION_BLOCKS:
            raise shots.LockMismatch(
                "decision prediction block artifact requires an exact ordinal"
            )
        return f"decision-prediction-block-{ordinal:03d}-{digest}.json"
    if logical == "native_completion":
        if ordinal is not None and (type(ordinal) is not int or ordinal < 0):
            raise shots.LockMismatch("native completion slot is malformed")
        return f"native-completion-{digest}.json"
    if ordinal is not None:
        raise shots.LockMismatch(f"{logical} artifact must not have an ordinal")
    return f"{logical.replace('_', '-')}-{digest}.json"


def _validate_k2_record_metadata(
    logical: str, record: Mapping[str, Any], *, ordinal: int | None = None,
) -> tuple[str, int, str]:
    if not isinstance(record, Mapping):
        raise shots.LockMismatch(f"{logical} artifact record is not a mapping")
    _keys(record, {"path", "sha256", "bytes", "schema"},
          label=f"{logical} artifact record")
    digest = record["sha256"]
    size = record["bytes"]
    relative = record["path"]
    if (record["schema"] != _k2_schemas()[logical]
            or not isinstance(digest, str) or not _HEX64.fullmatch(digest)
            or type(size) is not int or size <= 0
            or not isinstance(relative, str)):
        raise shots.LockMismatch(f"{logical} artifact record is malformed")
    relative_path = PurePosixPath(relative)
    if (relative_path.is_absolute() or ".." in relative_path.parts
            or relative_path.parent != PurePosixPath(shots.SHOTS_ARTIFACT_ROOT)
            or relative_path.name != _k2_filename(
                logical, digest, ordinal=ordinal,
            )):
        raise shots.LockMismatch(f"{logical} artifact path is not exact")
    return digest, size, relative


@dataclass(frozen=True)
class _ContentAddressedOwnership:
    """Exact final identity expected for one artifact created by this call."""

    device: int
    inode: int
    n_bytes: int
    sha256: str
    mode: int = 0o444
    nlink: int = 1


def _fsync_artifact_directory(directory_fd: int) -> None:
    """Synchronize an already-held artifact directory descriptor."""
    os.fsync(directory_fd)


def _read_content_addressed_entry_at(
    directory_fd: int, name: str, *, expected: bytes, label: str,
) -> bytes:
    """Read one immutable existing entry through a single no-follow FD."""
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(descriptor)
        named_before = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False,
        )
        if (not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(named_before.st_mode)
                or (before.st_dev, before.st_ino)
                != (named_before.st_dev, named_before.st_ino)
                or before.st_nlink != 1 or named_before.st_nlink != 1
                or stat.S_IMODE(before.st_mode) != 0o444
                or stat.S_IMODE(named_before.st_mode) != 0o444
                or before.st_size != len(expected)):
            raise shots.LockMismatch(
                f"immutable {label} content-address collision"
            )
        chunks: list[bytes] = []
        remaining = len(expected)
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                break
            chunks.append(chunk)
            remaining -= len(chunk)
        if remaining or os.read(descriptor, 1):
            raise shots.LockMismatch(
                f"immutable {label} content-address collision"
            )
        observed = b"".join(chunks)
        after = os.fstat(descriptor)
        named_after = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False,
        )
        identity = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        if (identity(before) != identity(after)
                or identity(named_before) != identity(named_after)
                or (after.st_dev, after.st_ino)
                != (named_after.st_dev, named_after.st_ino)
                or observed != expected):
            raise shots.LockMismatch(
                f"immutable {label} content-address collision"
            )
        return observed
    except shots.LockMismatch:
        raise
    except OSError as exc:
        raise shots.LockMismatch(
            f"immutable {label} content-address collision"
        ) from exc
    finally:
        if descriptor >= 0:
            os.close(descriptor)


@contextlib.contextmanager
def _durably_bind_content_addressed_entry_at(
    directory_fd: int, name: str, *, expected: bytes, label: str,
) -> Iterator[None]:
    """Lease an identical entry across file and directory synchronization."""
    descriptor = -1
    name_seen = False
    proven_conflict: shots.LockMismatch | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        name_seen = True

        def require_current(*, permit_complete_conflict: bool) -> None:
            nonlocal proven_conflict
            try:
                current = _decision_entry_identity(
                    directory_fd, name, descriptor, label=label,
                )
                if current.st_size != len(expected):
                    raise ManualReconciliationRequired(
                        f"immutable {label} entry is not a proven complete "
                        "artifact; manual reconciliation required"
                    )
                observed = _read_open_decision_entry_at(
                    directory_fd, name, descriptor, label=label,
                    max_bytes=len(expected),
                )
            except ManualReconciliationRequired:
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"immutable {label} entry identity is ambiguous; manual "
                    "reconciliation required"
                ) from exc
            if observed != expected:
                if permit_complete_conflict:
                    conflict = shots.LockMismatch(
                        f"immutable {label} content-address collision"
                    )
                    proven_conflict = conflict
                    raise conflict
                raise ManualReconciliationRequired(
                    f"immutable {label} entry changed after binding; manual "
                    "reconciliation required"
                )

        require_current(permit_complete_conflict=True)
        # Complete bytes and 0444 mode are visible before a creator's file
        # fsync.  Retain this exact inode through both durability operations so
        # an identical pathname replacement cannot inherit our acceptance.
        os.fsync(descriptor)
        require_current(permit_complete_conflict=False)
        _fsync_artifact_directory(directory_fd)
        require_current(permit_complete_conflict=False)
        try:
            yield
        except BaseException as exc:
            body_failure = exc
            raise
        finally:
            require_current(permit_complete_conflict=False)
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    close_failure: BaseException | None = None
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except BaseException as exc:
            close_failure = exc
        finally:
            descriptor = -1
    if close_failure is not None:
        message = (
            f"immutable {label} entry descriptor cleanup is ambiguous; manual "
            "reconciliation required"
        )
        if failure is not None:
            message += f"; active failure was {failure!r}"
        raise ManualReconciliationRequired(message) from close_failure
    if failure is None:
        return
    if failure is proven_conflict or failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if name_seen:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"immutable {label} entry could not be durably bound; manual "
            "reconciliation required"
        ) from failure
    if isinstance(failure, (NonPublishingRunStop, shots.ShotsError)):
        raise failure.with_traceback(failure_traceback)
    raise ResumableRunInterruption(
        f"immutable {label} entry I/O failed before descriptor binding"
    ) from failure


def _matches_owned_content_addressed_entry_at(
    directory_fd: int, name: str, ownership: _ContentAddressedOwnership,
) -> bool:
    """Whether a quarantined entry is exactly the artifact we created."""
    descriptor = -1
    try:
        descriptor = os.open(
            name,
            os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
            | getattr(os, "O_CLOEXEC", 0),
            dir_fd=directory_fd,
        )
        before = os.fstat(descriptor)
        named_before = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False,
        )
        expected_identity = (
            ownership.device, ownership.inode, ownership.mode,
            ownership.nlink, ownership.n_bytes,
        )
        opened_identity = (
            int(before.st_dev), int(before.st_ino),
            stat.S_IMODE(before.st_mode), int(before.st_nlink),
            int(before.st_size),
        )
        named_identity = (
            int(named_before.st_dev), int(named_before.st_ino),
            stat.S_IMODE(named_before.st_mode), int(named_before.st_nlink),
            int(named_before.st_size),
        )
        if (not stat.S_ISREG(before.st_mode)
                or not stat.S_ISREG(named_before.st_mode)
                or opened_identity != expected_identity
                or named_identity != expected_identity):
            return False
        digest = hashlib.sha256()
        remaining = ownership.n_bytes
        while remaining:
            chunk = os.read(descriptor, min(remaining, 1_048_576))
            if not chunk:
                return False
            digest.update(chunk)
            remaining -= len(chunk)
        if os.read(descriptor, 1):
            return False
        after = os.fstat(descriptor)
        named_after = os.stat(
            name, dir_fd=directory_fd, follow_symlinks=False,
        )
        stable = lambda value: (
            value.st_dev, value.st_ino, value.st_mode, value.st_nlink,
            value.st_size, value.st_mtime_ns, value.st_ctime_ns,
        )
        return (
            stable(before) == stable(after)
            and stable(named_before) == stable(named_after)
            and (after.st_dev, after.st_ino)
            == (named_after.st_dev, named_after.st_ino)
            and digest.hexdigest() == ownership.sha256
        )
    except OSError:
        return False
    finally:
        if descriptor >= 0:
            os.close(descriptor)


def _rollback_content_addressed_entry_at(
    directory_fd: int, name: str, ownership: _ContentAddressedOwnership,
    *, label: str,
) -> NoReturn:
    """Preserve a failed publication without pathname-based deletion.

    POSIX unlink/rmdir operations cannot be conditioned on an inode identity.
    A check followed by unlink therefore permits a same-UID replacement to be
    deleted in the gap.  Failed publications are deliberately left in place
    for manual reconciliation; this helper performs no rename or deletion.
    """
    try:
        owned = _matches_owned_content_addressed_entry_at(
            directory_fd, name, ownership,
        )
    except BaseException as exc:
        raise ManualReconciliationRequired(
            f"{label} write failed; ownership of preserved artifact {name} "
            "could not be determined; manual reconciliation required"
        ) from exc
    if owned:
        detail = f"owned failed artifact preserved at {name}"
    else:
        detail = f"artifact pathname {name} no longer names the created inode"
    raise ManualReconciliationRequired(
        f"{label} write failed; {detail}; manual reconciliation required"
    )


def _write_content_addressed_json(
    logical: str, value: Mapping[str, Any], *, artifact_root: Path,
    ordinal: int | None = None,
) -> dict[str, Any]:
    """Create one canonical artifact without ever replacing existing bytes.

    The physical root is injectable only so synthetic tests can use a temporary
    directory.  The receipt path is always the frozen repository-relative
    artifact root.  Existing identical bytes are idempotent; any collision is
    a refusal.  No public lifecycle action currently calls this helper.
    """
    if not isinstance(value, Mapping) or value.get("schema") != _k2_schemas()[logical]:
        raise shots.LockMismatch(f"{logical} value has the wrong semantic schema")
    raw = _canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    name = _k2_filename(logical, digest, ordinal=ordinal)
    ownership: _ContentAddressedOwnership | None = None
    created = False
    create_attempted = False
    existing_name_seen = False
    proven_conflict: shots.LockMismatch | None = None

    def bind_existing(directory_fd: int) -> None:
        """Accept only an exact durable entry; classify every ambiguity."""
        nonlocal proven_conflict
        descriptor = -1
        try:
            try:
                descriptor = os.open(
                    name,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=directory_fd,
                )
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"immutable {logical} artifact appeared during exclusive "
                    "creation but could not be opened; manual reconciliation "
                    "required"
                ) from exc

            def require_current(*, permit_complete_conflict: bool) -> None:
                nonlocal proven_conflict
                try:
                    current = _decision_entry_identity(
                        directory_fd, name, descriptor, label=logical,
                    )
                    if current.st_size != len(raw):
                        raise ManualReconciliationRequired(
                            f"immutable {logical} artifact is not a proven "
                            "complete entry; manual reconciliation required"
                        )
                    observed = _read_open_decision_entry_at(
                        directory_fd, name, descriptor, label=logical,
                        max_bytes=len(raw),
                    )
                except ManualReconciliationRequired:
                    raise
                except BaseException as exc:
                    raise ManualReconciliationRequired(
                        f"immutable {logical} artifact identity is ambiguous; "
                        "manual reconciliation required"
                    ) from exc
                if observed != raw:
                    if permit_complete_conflict:
                        conflict = shots.LockMismatch(
                            f"immutable {logical} content-address collision"
                        )
                        proven_conflict = conflict
                        raise conflict
                    raise ManualReconciliationRequired(
                        f"immutable {logical} artifact changed after it was "
                        "bound; manual reconciliation required"
                    )

            require_current(permit_complete_conflict=True)
            try:
                os.fsync(descriptor)
                require_current(permit_complete_conflict=False)
                _fsync_artifact_directory(directory_fd)
                require_current(permit_complete_conflict=False)
            except (ManualReconciliationRequired, shots.LockMismatch):
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"immutable {logical} artifact could not be durably "
                    "bound; manual reconciliation required"
                ) from exc
        finally:
            active = sys.exc_info()[1]
            if descriptor >= 0:
                try:
                    os.close(descriptor)
                except BaseException as close_failure:
                    message = (
                        f"immutable {logical} artifact descriptor cleanup is "
                        "ambiguous; manual reconciliation required"
                    )
                    if active is not None:
                        message += f"; active failure was {active!r}"
                    raise ManualReconciliationRequired(message) from close_failure

    try:
        with _open_decision_state_directory(
            Path(artifact_root), create=True,
        ) as (_, directory_fd):
            assert directory_fd is not None
            descriptor = -1
            try:
                # Once O_CREAT is entered, an error cannot prove the name was
                # never exposed.  Treat every later uncertainty as manual.
                create_attempted = True
                descriptor = os.open(
                    name,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o444,
                    dir_fd=directory_fd,
                )
            except FileExistsError:
                existing_name_seen = True
                bind_existing(directory_fd)
            else:
                created = True
                opened = os.fstat(descriptor)
                ownership = _ContentAddressedOwnership(
                    device=int(opened.st_dev), inode=int(opened.st_ino),
                    n_bytes=len(raw), sha256=digest,
                )
                try:
                    written = 0
                    while written < len(raw):
                        count = os.write(descriptor, raw[written:])
                        if count <= 0:
                            raise OSError(
                                "content-addressed artifact write made no progress"
                            )
                        written += count
                    os.fchmod(descriptor, ownership.mode)

                    def require_created_artifact() -> None:
                        finished = _decision_entry_identity(
                            directory_fd, name, descriptor, label=logical,
                        )
                        if ((finished.st_dev, finished.st_ino)
                                != (ownership.device, ownership.inode)
                                or finished.st_size != ownership.n_bytes
                                or finished.st_nlink != ownership.nlink
                                or stat.S_IMODE(finished.st_mode)
                                != ownership.mode
                                or _read_open_decision_entry_at(
                                    directory_fd, name, descriptor,
                                    label=logical, max_bytes=len(raw),
                                ) != raw):
                            raise shots.LockMismatch(
                                f"created {logical} artifact changed before "
                                "durable acceptance"
                            )

                    require_created_artifact()
                    os.fsync(descriptor)
                    require_created_artifact()
                    _fsync_artifact_directory(directory_fd)
                    require_created_artifact()
                except BaseException as failure:
                    close_failure: BaseException | None = None
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        close_failure = exc
                    finally:
                        # close(2) failures can leave descriptor ownership
                        # unspecified; never retry against a recycled number.
                        descriptor = -1
                    try:
                        _rollback_content_addressed_entry_at(
                            directory_fd, name, ownership, label=logical,
                        )
                    except ManualReconciliationRequired as rollback:
                        if close_failure is not None:
                            raise ManualReconciliationRequired(
                                f"{logical} write and descriptor cleanup failed; "
                                f"{rollback}"
                            ) from close_failure
                        raise rollback from failure
                    raise
                else:
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        raise ManualReconciliationRequired(
                            f"durable {logical} artifact descriptor cleanup is "
                            "ambiguous; manual reconciliation required"
                        ) from exc
                    finally:
                        descriptor = -1
            finally:
                if descriptor >= 0:
                    active = sys.exc_info()[1]
                    try:
                        os.close(descriptor)
                    except BaseException as close_failure:
                        message = (
                            f"{logical} artifact descriptor cleanup is "
                            "ambiguous; manual reconciliation required"
                        )
                        if active is not None:
                            message += f"; active failure was {active!r}"
                        raise ManualReconciliationRequired(
                            message
                        ) from close_failure
                    finally:
                        descriptor = -1
    except ManualReconciliationRequired:
        raise
    except ResumableRunInterruption as exc:
        if created or create_attempted or existing_name_seen:
            raise ManualReconciliationRequired(
                f"{logical} artifact name may be durable after an "
                "infrastructure interruption; manual reconciliation required"
            ) from exc
        raise
    except shots.LockMismatch as exc:
        if exc is proven_conflict:
            raise
        if created or create_attempted or existing_name_seen:
            raise ManualReconciliationRequired(
                f"{logical} artifact namespace changed after a name became "
                "possibly durable; manual reconciliation required"
            ) from exc
        raise
    except OSError as exc:
        if created or create_attempted or existing_name_seen:
            raise ManualReconciliationRequired(
                f"{logical} artifact may have become durable; manual "
                "reconciliation required"
            ) from exc
        raise ResumableRunInterruption(
            f"{logical} artifact I/O failed before content publication"
        ) from exc
    except BaseException as exc:
        if created or create_attempted or existing_name_seen:
            raise ManualReconciliationRequired(
                f"{logical} artifact name may be durable after an "
                "interruption; manual reconciliation required"
            ) from exc
        raise ResumableRunInterruption(
            f"{logical} artifact creation stopped before content publication"
        ) from exc
    return {
        "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{name}",
        "sha256": digest,
        "bytes": len(raw),
        "schema": _k2_schemas()[logical],
    }


@contextlib.contextmanager
def _experiment_transaction_lock(
    *, h: _VerifiedH, artifact_root: Path,
) -> Iterator[None]:
    """Serialize all public post-H phases and terminal publication."""
    if (not _HEX40.fullmatch(h.commit)
            or not _HEX64.fullmatch(h.manifest_sha256)):
        raise shots.LockMismatch("experiment transaction identity is malformed")
    raw = (
        "epl-shots-experiment-transaction-lock-1\n"
        f"{h.commit}\n{h.manifest_sha256}\n"
    ).encode("ascii")
    name = ".experiment-transaction.lock"
    descriptor = -1
    created = False
    create_attempted = False
    name_seen = False
    lock_acquired = False
    proven_conflict: shots.LockMismatch | None = None
    busy_failure: RunnerNotReady | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        with _open_decision_state_directory(
            Path(artifact_root), create=True,
        ) as (_, directory_fd):
            if directory_fd is None:  # pragma: no cover - create invariant
                raise NativeWorkerIOFailure(
                    "experiment transaction namespace is absent"
                )
            try:
                try:
                    # O_CREAT may have exposed the permanent lock name even if
                    # the syscall reports an error to Python.
                    create_attempted = True
                    descriptor = os.open(
                        name,
                        os.O_RDWR | os.O_CREAT | os.O_EXCL | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        0o444, dir_fd=directory_fd,
                    )
                    created = True
                    name_seen = True
                except FileExistsError:
                    name_seen = True
                    descriptor = os.open(
                        name,
                        os.O_RDONLY | os.O_NOFOLLOW
                        | getattr(os, "O_CLOEXEC", 0),
                        dir_fd=directory_fd,
                    )
                opened = os.fstat(descriptor)
                identity = (opened.st_dev, opened.st_ino)

                def require_current(*, permit_complete_conflict: bool) -> None:
                    nonlocal proven_conflict
                    try:
                        current = _decision_entry_identity(
                            directory_fd, name, descriptor,
                            label="experiment transaction lock",
                        )
                        if (current.st_dev, current.st_ino) != identity:
                            raise ManualReconciliationRequired(
                                "experiment transaction lock identity changed; "
                                "manual reconciliation required"
                            )
                        if current.st_size != len(raw):
                            raise ManualReconciliationRequired(
                                "experiment transaction lock is not a proven "
                                "complete entry; manual reconciliation required"
                            )
                        observed = _read_open_decision_entry_at(
                            directory_fd, name, descriptor,
                            label="experiment transaction lock",
                            max_bytes=len(raw),
                        )
                    except ManualReconciliationRequired:
                        raise
                    except BaseException as exc:
                        raise ManualReconciliationRequired(
                            "experiment transaction lock identity is ambiguous; "
                            "manual reconciliation required"
                        ) from exc
                    if observed != raw:
                        if permit_complete_conflict:
                            conflict = shots.LockMismatch(
                                "experiment transaction lock bytes differ"
                            )
                            proven_conflict = conflict
                            raise conflict
                        raise ManualReconciliationRequired(
                            "experiment transaction lock changed after binding; "
                            "manual reconciliation required"
                        )

                if not created:
                    require_current(permit_complete_conflict=True)
                try:
                    fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
                except BlockingIOError as exc:
                    if not created:
                        require_current(permit_complete_conflict=False)
                    busy = RunnerNotReady(
                        "another experiment transaction is active"
                    )
                    busy_failure = busy
                    raise busy from exc
                lock_acquired = True
                if created:
                    _write_native_descriptor(
                        descriptor, raw, label="experiment transaction lock",
                    )
                    os.fchmod(descriptor, 0o444)
                require_current(permit_complete_conflict=False)
                os.fsync(descriptor)
                require_current(permit_complete_conflict=False)
                _fsync_artifact_directory(directory_fd)
                require_current(permit_complete_conflict=False)
                try:
                    yield
                except BaseException as exc:
                    body_failure = exc
                    raise
                finally:
                    require_current(permit_complete_conflict=False)
            finally:
                cleanup_failure: BaseException | None = None
                active = sys.exc_info()[1]
                if lock_acquired:
                    try:
                        fcntl.flock(descriptor, fcntl.LOCK_UN)
                    except BaseException as exc:
                        cleanup_failure = exc
                    finally:
                        lock_acquired = False
                if descriptor >= 0:
                    try:
                        os.close(descriptor)
                    except BaseException as exc:
                        if cleanup_failure is None:
                            cleanup_failure = exc
                    finally:
                        descriptor = -1
                if cleanup_failure is not None:
                    message = (
                        "experiment transaction lock cleanup is ambiguous; "
                        "manual reconciliation required"
                    )
                    if active is not None:
                        message += f"; active failure was {active!r}"
                    raise ManualReconciliationRequired(
                        message
                    ) from cleanup_failure
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    if failure is None:
        return
    if failure is proven_conflict:
        raise failure.with_traceback(failure_traceback)
    if failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if created:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            "experiment transaction lock was created before the active "
            "failure; manual reconciliation required"
        ) from failure
    if failure is busy_failure:
        raise failure.with_traceback(failure_traceback)
    if name_seen or create_attempted:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            "experiment transaction lock name could not be durably bound; "
            "manual reconciliation required"
        ) from failure
    if isinstance(failure, (NonPublishingRunStop, shots.ShotsError)):
        raise failure.with_traceback(failure_traceback)
    raise ResumableRunInterruption(
        "experiment transaction lock failed before name creation"
    ) from failure


@contextlib.contextmanager
def _digest_reservation_at(
    directory_fd: int, name: str, digest: str, *, create: bool,
) -> Iterator[bool]:
    """Lease one immutable claim entry beneath an already-leased root.

    A newly-created claim is written, synchronized, and verified through its
    original ``O_EXCL`` descriptor.  Both new and existing claims retain that
    descriptor until the surrounding transaction exits, so an identical-byte
    pathname substitution cannot turn into authorization.
    """
    if not _HEX64.fullmatch(digest) or "/" in name or name in ("", ".", ".."):
        raise shots.LockMismatch("immutable reservation identity is malformed")
    filename = f".{name}.claim"
    raw = (digest + "\n").encode("ascii")
    descriptor = -1
    created = False
    create_attempted = False
    name_seen = False
    proven_conflict: shots.LockMismatch | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        if create:
            try:
                # An O_CREAT error cannot prove that no claim name was ever
                # exposed, so crossing this call is a reconciliation boundary.
                create_attempted = True
                descriptor = os.open(
                    filename,
                    os.O_RDWR | os.O_CREAT | os.O_EXCL
                    | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    0o444,
                    dir_fd=directory_fd,
                )
                created = True
                name_seen = True
            except FileExistsError:
                # The name is real, but it is not yet known to be a complete
                # conflicting claim.  Every other outcome is reconciliation.
                name_seen = True
                descriptor = os.open(
                    filename,
                    os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                    | getattr(os, "O_CLOEXEC", 0),
                    dir_fd=directory_fd,
                )
        else:
            descriptor = os.open(
                filename,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )
            name_seen = True

        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if created:
            os.lseek(descriptor, 0, os.SEEK_SET)
            written = 0
            while written < len(raw):
                count = os.write(descriptor, raw[written:])
                if count <= 0:
                    raise OSError("immutable reservation write made no progress")
                written += count
            os.fchmod(descriptor, 0o444)

        def require_current_claim(*, permit_complete_conflict: bool) -> None:
            nonlocal proven_conflict
            try:
                current = _decision_entry_identity(
                    directory_fd, filename, descriptor,
                    label=f"immutable {name} reservation",
                )
                if (current.st_dev, current.st_ino) != identity:
                    raise ManualReconciliationRequired(
                        f"immutable {name} reservation identity changed; "
                        "manual reconciliation required"
                    )
                if current.st_size != len(raw):
                    raise ManualReconciliationRequired(
                        f"immutable {name} reservation is not a proven "
                        "complete claim; manual reconciliation required"
                    )
                observed = _read_open_decision_entry_at(
                    directory_fd, filename, descriptor,
                    label=f"immutable {name} reservation",
                    max_bytes=len(raw),
                )
            except ManualReconciliationRequired:
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"immutable {name} reservation identity is ambiguous; "
                    "manual reconciliation required"
                ) from exc
            if observed != raw:
                if permit_complete_conflict:
                    conflict = shots.LockMismatch(
                        f"immutable {name} reservation differs"
                    )
                    proven_conflict = conflict
                    raise conflict
                raise ManualReconciliationRequired(
                    f"immutable {name} reservation changed after binding; "
                    "manual reconciliation required"
                )

        # A pre-existing claim is terminal only when one stable, complete
        # immutable entry proves a different digest.  A newly-created entry can
        # never become a scientific refusal if its identity or bytes differ.
        require_current_claim(permit_complete_conflict=not created)
        os.fsync(descriptor)
        require_current_claim(permit_complete_conflict=False)
        # Existing claims can be remnants of a prior directory-fsync failure;
        # both new and idempotent claims must establish namespace durability.
        _fsync_artifact_directory(directory_fd)
        require_current_claim(permit_complete_conflict=False)
        try:
            yield created
        except BaseException as exc:
            body_failure = exc
            raise
        finally:
            require_current_claim(permit_complete_conflict=False)
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    close_failure: BaseException | None = None
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except BaseException as exc:
            close_failure = exc
        finally:
            # Retrying close after an error can close an unrelated recycled FD.
            descriptor = -1
    if close_failure is not None:
        message = (
            f"immutable {name} reservation descriptor cleanup is ambiguous; "
            "manual reconciliation required"
        )
        if failure is not None:
            message += f"; active failure was {failure!r}"
        raise ManualReconciliationRequired(message) from close_failure
    if failure is None:
        return
    if failure is proven_conflict:
        raise failure.with_traceback(failure_traceback)
    if failure is body_failure:
        # The claim remained exact through final verification and descriptor
        # cleanup, so the caller's own result is authoritative.
        raise failure.with_traceback(failure_traceback)
    if created:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"immutable {name} reservation was created before the active "
            "failure; manual reconciliation required"
        ) from failure
    if name_seen or create_attempted:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"immutable {name} reservation name could not be durably bound; "
            "manual reconciliation required"
        ) from failure
    if isinstance(failure, (NonPublishingRunStop, shots.ShotsError)):
        raise failure.with_traceback(failure_traceback)
    raise ResumableRunInterruption(
        f"immutable {name} reservation I/O failed before name creation"
    ) from failure


def _reserve_digest(artifact_root: Path, name: str, digest: str) -> bool:
    """Compatibility wrapper for one leased singleton reservation."""
    with _open_decision_state_directory(
        Path(artifact_root), create=True,
    ) as (_, directory_fd):
        assert directory_fd is not None
        with _digest_reservation_at(
            directory_fd, name, digest, create=True,
        ) as created:
            return created


def _validate_native_shard_write_shape(value: Mapping[str, Any]) -> int:
    """Reject malformed bytes before they can claim an ordinal forever."""
    _keys(value, {
        "schema", "native_intent_sha256", "block_identity_sha256",
        "harness_commit", "harness_manifest_sha256",
        "parent_commit", "parent_tree",
        "training_schedule_sha256", "block_ordinal", "block", "cutoff",
        "rows", "receipt",
    }, label="native shard write")
    ordinal = value["block_ordinal"]
    if (value["schema"] != _NATIVE_BLOCK_SCHEMA
            or type(ordinal) is not int or ordinal < 0
            or value["parent_commit"] != _NATIVE_PARENT_COMMIT
            or value["parent_tree"] != _NATIVE_PARENT_TREE
            or not isinstance(value["native_intent_sha256"], str)
            or not _HEX64.fullmatch(value["native_intent_sha256"])
            or not isinstance(value["block_identity_sha256"], str)
            or not _HEX64.fullmatch(value["block_identity_sha256"])
            or not isinstance(value["harness_commit"], str)
            or not _HEX40.fullmatch(value["harness_commit"])
            or not isinstance(value["harness_manifest_sha256"], str)
            or not _HEX64.fullmatch(value["harness_manifest_sha256"])
            or not isinstance(value["training_schedule_sha256"], str)
            or not _HEX64.fullmatch(value["training_schedule_sha256"])
            or not isinstance(value["block"], str) or not value["block"]
            or not isinstance(value["cutoff"], str)
            or value["cutoff"] != _iso_date(value["cutoff"])
            or not isinstance(value["receipt"], Mapping)
            or not isinstance(value["rows"], list) or not value["rows"]):
        raise shots.LockMismatch("native shard write identity is malformed")
    required = {
        "ordinal", "match_id", "season", "block", "cutoff", "home_key",
        "away_key", "native", "y",
    }
    for row in value["rows"]:
        if (not isinstance(row, Mapping) or set(row) != required
                or type(row["ordinal"]) is not int
                or any(not isinstance(row[name], str) or not row[name]
                       for name in required - {"ordinal", "native", "y"})
                or row["block"] != value["block"]
                or row["cutoff"] != value["cutoff"]
                or type(row["y"]) is not int or row["y"] not in (0, 1, 2)):
            raise shots.LockMismatch("native shard write row is malformed")
        _probability_vector(
            row["native"], label="native shard write probability",
            strictly_positive=True, stored_native=True,
        )
    return ordinal


def _load_content_addressed_json(
    logical: str, record: Mapping[str, Any], *, artifact_root: Path,
    ordinal: int | None = None,
) -> tuple[dict[str, Any], bytes]:
    digest, size, relative = _validate_k2_record_metadata(
        logical, record, ordinal=ordinal,
    )
    root = _componentwise_regular_path(Path(artifact_root), create=False)
    path = root / PurePosixPath(relative).name
    if path.is_symlink() or not path.is_file() or path.resolve().parent != root:
        raise shots.LockMismatch(f"{logical} artifact is absent or not a regular file")
    value, raw = _read_canonical(path, label=f"{logical} artifact")
    if (len(raw) != size or hashlib.sha256(raw).hexdigest() != digest
            or value.get("schema") != _k2_schemas()[logical]):
        raise shots.LockMismatch(f"{logical} content-addressed bytes differ")
    return value, raw


def _write_native_block_shard(
    value: Mapping[str, Any], *, artifact_root: Path,
) -> dict[str, Any]:
    """Persist a generator-validated block under one immutable ordinal."""
    if not isinstance(value, Mapping):
        raise shots.LockMismatch("native block shard is not a mapping")
    ordinal = _validate_native_shard_write_shape(value)
    raw = _canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    root = Path(artifact_root)
    _reserve_digest(root, f"native-block-{ordinal:03d}", digest)
    return _write_content_addressed_json(
        "native_block", value, artifact_root=root, ordinal=ordinal,
    )


def _load_native_block_shard(
    record: Mapping[str, Any], *, artifact_root: Path,
) -> dict[str, Any]:
    relative = record.get("path") if isinstance(record, Mapping) else None
    if not isinstance(relative, str):
        raise shots.LockMismatch("native block record path is malformed")
    match = re.fullmatch(
        r"native-block-([0-9]+)-([0-9a-f]{64})\.json",
        PurePosixPath(relative).name,
    )
    if match is None:
        raise shots.LockMismatch("native block artifact path is not exact")
    ordinal = int(match.group(1))
    value, _ = _load_content_addressed_json(
        "native_block", record, artifact_root=artifact_root, ordinal=ordinal,
    )
    if value.get("block_ordinal") != ordinal:
        raise shots.LockMismatch("native block filename/payload ordinal differs")
    return value


def _discover_native_block_shards(
    *, artifact_root: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    """Load a resumable shard set, refusing aliases and ordinal forks."""
    root_arg = _componentwise_regular_path(Path(artifact_root), create=False)
    if not root_arg.exists():
        return ()
    if root_arg.is_symlink() or not root_arg.is_dir():
        raise shots.LockMismatch("native shard root is not a regular directory")
    found: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for path in sorted(root_arg.iterdir()):
        if not path.name.startswith("native-block-"):
            continue
        match = re.fullmatch(
            r"native-block-([0-9]+)-([0-9a-f]{64})\.json", path.name,
        )
        if match is None:
            raise shots.LockMismatch("malformed native block shard filename")
        ordinal = int(match.group(1))
        if not 0 <= ordinal < sum(shots.TRAINING_BLOCK_COUNTS.values()):
            raise shots.LockMismatch(
                "native block shard ordinal is outside 0..141"
            )
        if ordinal in found:
            raise shots.LockMismatch(f"native block {ordinal} has multiple shards")
        record = {
            "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{path.name}",
            "sha256": match.group(2),
            "bytes": int(path.stat().st_size),
            "schema": _NATIVE_BLOCK_SCHEMA,
        }
        value = _load_native_block_shard(record, artifact_root=root_arg)
        found[ordinal] = (record, value)
    return tuple(found[key] for key in sorted(found))


def _make_native_completion_receipt(
    *, native_intent_sha256: str, job_request_sha256: str,
    job_ordinals: Sequence[int], block_records: Sequence[Mapping[str, Any]],
    sandbox_run: Mapping[str, Any], output_bytes: int,
    runtime_snapshot: Mapping[str, Any],
    runtime_observed: Mapping[str, int] | None = None,
) -> dict[str, Any]:
    ordinals = list(job_ordinals)
    records = [dict(record) for record in block_records]
    if (not _HEX64.fullmatch(native_intent_sha256)
            or not _HEX64.fullmatch(job_request_sha256)
            or any(type(value) is not int for value in ordinals)
            or ordinals != sorted(set(ordinals))
            or len(ordinals) != len(records)
            or type(output_bytes) is not int or output_bytes <= 0):
        raise shots.LockMismatch("native completion inputs are malformed")
    for ordinal, record in zip(ordinals, records, strict=True):
        _validate_k2_record_metadata("native_block", record, ordinal=ordinal)
    observed = dict(
        runtime_observed or {"files": 0, "bytes": 0, "rss_bytes": 0}
    )
    if (set(observed) != {"files", "bytes", "rss_bytes"}
            or any(type(value) is not int or value < 0 for value in observed.values())
            or observed["files"] > _NATIVE_RUNTIME_MAX_FILES
            or observed["bytes"] > _NATIVE_RUNTIME_MAX_BYTES
            or observed["rss_bytes"] > _NATIVE_RSS_LIMIT_BYTES):
        raise shots.LockMismatch("native resource observation is malformed")
    completion_snapshot = _validate_native_runtime_output_snapshot(
        runtime_snapshot,
    )
    if (completion_snapshot["file_count"] > observed["files"]
            or completion_snapshot["bytes"] > observed["bytes"]):
        raise shots.LockMismatch(
            "native runtime completion exceeds its observed high-water mark"
        )
    return {
        "schema": _NATIVE_COMPLETION_SCHEMA,
        "native_intent_sha256": native_intent_sha256,
        "job_request_sha256": job_request_sha256,
        "job_ordinals": ordinals,
        "block_records": records,
        "clean_exit": True,
        "exit_code": 0,
        "sandbox": dict(sandbox_run),
        "stream": {
            "output_lines": len(records),
            "output_bytes": output_bytes,
            "total_timeout_seconds": _NATIVE_TOTAL_TIMEOUT_SECONDS,
            "inactivity_timeout_seconds": _NATIVE_INACTIVITY_TIMEOUT_SECONDS,
            "max_line_bytes": _NATIVE_MAX_LINE_BYTES,
            "max_output_bytes": _NATIVE_MAX_OUTPUT_BYTES,
            "runtime_tree_max_bytes": _NATIVE_RUNTIME_MAX_BYTES,
            "runtime_tree_max_files": _NATIVE_RUNTIME_MAX_FILES,
            "runtime_tree_observed_bytes": observed["bytes"],
            "runtime_tree_observed_files": observed["files"],
            "runtime_tree_completion": completion_snapshot,
            "resident_memory_max_bytes": _NATIVE_RSS_LIMIT_BYTES,
            "resident_memory_poll_seconds": _NATIVE_RSS_POLL_SECONDS,
            "resident_memory_sampled_peak_bytes": observed["rss_bytes"],
        },
    }


def _validate_native_sandbox_run(
    value: Mapping[str, Any], *, contract: Mapping[str, Any],
) -> None:
    if not isinstance(value, Mapping):
        raise shots.LockMismatch("native sandbox run receipt is not a mapping")
    _keys(value, {
        "schema", "contract_sha256", "sandbox_executable", "policy_sha256",
        "python_launcher", "python_resolved", "python_sha256",
        "site_packages", "compiler_paths", "sdk_root", "python_flags",
        "runtime_read_paths", "process_exec_paths", "file_read_metadata",
        "path_resolution_literals",
        "temporary_root", "parent_read_path",
        "request_read_path", "runtime_read_write_path", "environment",
        "resource_limits", "isolated_process_group", "network",
    }, label="native sandbox run receipt")
    if (value["schema"] != _NATIVE_SANDBOX_RUN_SCHEMA
            or value["contract_sha256"]
                != _native_sandbox_contract_sha256(contract)
            or value["sandbox_executable"] != contract["sandbox_executable"]
            or value["python_launcher"] != contract["python_launcher"]
            or value["python_resolved"] != contract["python_resolved"]
            or value["python_sha256"] != contract["python_sha256"]
            or value["site_packages"] != contract["site_packages"]
            or value["compiler_paths"] != contract["compiler_paths"]
            or value["sdk_root"] != contract["sdk_root"]
            or value["python_flags"] != contract["python_flags"]
            or value["runtime_read_paths"] != contract["runtime_read_paths"]
            or value["process_exec_paths"] != contract["process_exec_paths"]
            or value["file_read_metadata"] != contract["file_read_metadata"]
            or value["path_resolution_literals"]
                != contract["path_resolution_literals"]
            or value["resource_limits"] != contract["resource_limits"]
            or value["isolated_process_group"] is not True
            or value["network"] != "deny"
            or not isinstance(value["policy_sha256"], str)
            or not _HEX64.fullmatch(value["policy_sha256"])):
        raise shots.LockMismatch("native sandbox run binding differs")
    path_fields = (
        "temporary_root", "parent_read_path", "request_read_path",
        "runtime_read_write_path",
    )
    if any(not isinstance(value[field], str) or not Path(value[field]).is_absolute()
           for field in path_fields):
        raise shots.LockMismatch("native sandbox run path is malformed")
    temporary = Path(value["temporary_root"])
    parent = Path(value["parent_read_path"])
    request = Path(value["request_read_path"])
    runtime = Path(value["runtime_read_write_path"])
    expected_environment = _native_environment_values(
        contract=contract, parent_root=parent,
        request_path=request, runtime_root=runtime,
    )
    if value["environment"] != expected_environment:
        raise shots.LockMismatch("native sandbox environment values differ")
    profile = _native_sandbox_profile(
        contract=contract, temporary_root=temporary, parent_root=parent,
        request_path=request, runtime_root=runtime,
        resolve_live_paths=False,
    )
    if hashlib.sha256(profile.encode("utf-8")).hexdigest() != value["policy_sha256"]:
        raise shots.LockMismatch("native sandbox policy digest differs")


def _validate_native_completion_receipt(
    value: Mapping[str, Any], *, native_intent: Mapping[str, Any],
    native_intent_sha256: str, block_count: int,
    sandbox_contract: Mapping[str, Any],
) -> tuple[dict[str, Any], ...]:
    if not isinstance(value, Mapping):
        raise shots.LockMismatch("native completion receipt is not a mapping")
    _keys(value, {
        "schema", "native_intent_sha256", "job_request_sha256",
        "job_ordinals", "block_records", "clean_exit", "exit_code",
        "sandbox", "stream",
    }, label="native completion receipt")
    ordinals = value["job_ordinals"]
    records = value["block_records"]
    if (value["schema"] != _NATIVE_COMPLETION_SCHEMA
            or value["native_intent_sha256"] != native_intent_sha256
            or not isinstance(ordinals, list)
            or any(type(item) is not int for item in ordinals)
            or ordinals != sorted(set(ordinals))
            or any(item < 0 or item >= block_count for item in ordinals)
            or not isinstance(records, list) or len(records) != len(ordinals)
            or not ordinals
            or value["clean_exit"] is not True
            or value["exit_code"] != 0):
        raise shots.LockMismatch("native completion receipt is not a clean exact job")
    expected_request = _native_request(
        native_intent=native_intent,
        native_intent_sha256=native_intent_sha256,
        block_ordinals=ordinals, block_count=block_count,
    )
    expected_request_sha256 = hashlib.sha256(
        _canonical_bytes(expected_request)
    ).hexdigest()
    if value["job_request_sha256"] != expected_request_sha256:
        raise shots.LockMismatch("native completion job request digest differs")
    normalized: list[dict[str, Any]] = []
    for ordinal, record in zip(ordinals, records, strict=True):
        _validate_k2_record_metadata("native_block", record, ordinal=ordinal)
        normalized.append(dict(record))
    expected_output_bytes = sum(record["bytes"] for record in normalized)
    if (any(record["bytes"] > _NATIVE_MAX_LINE_BYTES for record in normalized)
            or expected_output_bytes > _NATIVE_MAX_OUTPUT_BYTES):
        raise shots.LockMismatch("native completion block output exceeds its caps")
    stream = value["stream"]
    if not isinstance(stream, Mapping):
        raise shots.LockMismatch("native completion stream receipt is not a mapping")
    _keys(stream, {
        "output_lines", "output_bytes", "total_timeout_seconds",
        "inactivity_timeout_seconds", "max_line_bytes", "max_output_bytes",
        "runtime_tree_max_bytes", "runtime_tree_max_files",
        "runtime_tree_observed_bytes", "runtime_tree_observed_files",
        "runtime_tree_completion",
        "resident_memory_max_bytes", "resident_memory_poll_seconds",
        "resident_memory_sampled_peak_bytes",
    }, label="native completion stream receipt")
    completion_snapshot = _validate_native_runtime_output_snapshot(
        stream["runtime_tree_completion"],
    )
    if (stream["output_lines"] != len(records)
            or type(stream["output_bytes"]) is not int
            or stream["output_bytes"] != expected_output_bytes
            or stream["total_timeout_seconds"] != _NATIVE_TOTAL_TIMEOUT_SECONDS
            or stream["inactivity_timeout_seconds"]
                != _NATIVE_INACTIVITY_TIMEOUT_SECONDS
            or stream["max_line_bytes"] != _NATIVE_MAX_LINE_BYTES
            or stream["max_output_bytes"] != _NATIVE_MAX_OUTPUT_BYTES
            or stream["runtime_tree_max_bytes"] != _NATIVE_RUNTIME_MAX_BYTES
            or stream["runtime_tree_max_files"] != _NATIVE_RUNTIME_MAX_FILES
            or type(stream["runtime_tree_observed_bytes"]) is not int
            or not 0 <= stream["runtime_tree_observed_bytes"]
                <= _NATIVE_RUNTIME_MAX_BYTES
            or type(stream["runtime_tree_observed_files"]) is not int
            or not 0 <= stream["runtime_tree_observed_files"]
                <= _NATIVE_RUNTIME_MAX_FILES
            or completion_snapshot["file_count"]
                > stream["runtime_tree_observed_files"]
            or completion_snapshot["bytes"]
                > stream["runtime_tree_observed_bytes"]
            or stream["resident_memory_max_bytes"] != _NATIVE_RSS_LIMIT_BYTES
            or stream["resident_memory_poll_seconds"]
                != _NATIVE_RSS_POLL_SECONDS
            or type(stream["resident_memory_sampled_peak_bytes"]) is not int
            or not 0 <= stream["resident_memory_sampled_peak_bytes"]
                <= _NATIVE_RSS_LIMIT_BYTES):
        raise shots.LockMismatch("native completion stream limits differ")
    _validate_native_sandbox_run(value["sandbox"], contract=sandbox_contract)
    return tuple(normalized)


def _discover_completed_native_block_shards(
    *, artifact_root: Path, native_intent: Mapping[str, Any],
    native_intent_sha256: str, h: _VerifiedH, training_sha256: str,
    raw_inputs: Sequence[Mapping[str, Any]],
    blocks: Sequence[Sequence[Mapping[str, Any]]],
    sandbox_contract: Mapping[str, Any],
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    """Return only durable shards authorized by a valid clean job receipt."""
    root = _componentwise_regular_path(Path(artifact_root), create=False)
    if not root.exists():
        return ()
    if root.is_symlink() or not root.is_dir():
        raise shots.LockMismatch("native completion root is not a regular directory")
    covered: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    for path in sorted(root.iterdir()):
        if not path.name.startswith("native-completion-"):
            continue
        match = re.fullmatch(r"native-completion-([0-9a-f]{64})\.json", path.name)
        if match is None:
            raise shots.LockMismatch("malformed native completion filename")
        record = {
            "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{path.name}",
            "sha256": match.group(1),
            "bytes": int(path.stat().st_size),
            "schema": _NATIVE_COMPLETION_SCHEMA,
        }
        completion, _ = _load_content_addressed_json(
            "native_completion", record, artifact_root=root,
        )
        if completion.get("native_intent_sha256") != native_intent_sha256:
            continue
        block_records = _validate_native_completion_receipt(
            completion, native_intent=native_intent,
            native_intent_sha256=native_intent_sha256,
            block_count=len(blocks), sandbox_contract=sandbox_contract,
        )
        recomputed_output_bytes = 0
        for ordinal, block_record in zip(
            completion["job_ordinals"], block_records, strict=True,
        ):
            if ordinal in covered:
                raise shots.LockMismatch(
                    f"native block {ordinal} has overlapping completion receipts"
                )
            block = _load_native_block_shard(
                block_record, artifact_root=artifact_root,
            )
            validated = _validate_native_block(
                block, native_intent_sha256=native_intent_sha256, h=h,
                training_sha256=training_sha256, raw_inputs=raw_inputs,
                expected_ordinal=ordinal, blocks=blocks,
            )
            recomputed_output_bytes += len(_canonical_bytes(validated))
            covered[ordinal] = (block_record, validated)
        if completion["stream"]["output_bytes"] != recomputed_output_bytes:
            raise shots.LockMismatch(
                "native completion output-byte count does not recompute"
            )
    return tuple(covered[ordinal] for ordinal in sorted(covered))


def _record_binds_value(
    logical: str, record: Mapping[str, Any], value: Mapping[str, Any], *,
    ordinal: int | None = None,
) -> None:
    digest, size, _ = _validate_k2_record_metadata(
        logical, record, ordinal=ordinal,
    )
    raw = _canonical_bytes(value)
    if hashlib.sha256(raw).hexdigest() != digest or len(raw) != size:
        raise shots.LockMismatch(f"{logical} record does not bind its value")


def _native_block_set_sha256(records: Sequence[Mapping[str, Any]]) -> str:
    return _digest_rows(_K2_BLOCK_SET_SCHEMA, records)


def _training_outcome_sha256(
    schedule: Sequence[Mapping[str, Any]], outcomes: Sequence[int],
) -> str:
    if len(schedule) != len(outcomes):
        raise shots.FixtureSetMismatch("training outcome count differs from schedule")
    rows: list[dict[str, Any]] = []
    for expected, outcome in zip(schedule, outcomes, strict=True):
        if type(outcome) is not int or outcome not in (0, 1, 2):
            raise shots.FitFailure("training outcome code is not 0/1/2")
        rows.append({
            "ordinal": expected["ordinal"],
            "match_id": expected["match_id"],
            "y": outcome,
        })
    return _digest_rows(_K2_OUTCOME_SCHEMA, rows)


# ==========================================================================
# PRE-H optimizer transaction: one intent, at most one invocation, one receipt
# ==========================================================================

def _make_optimizer_intent(
    *, h: _VerifiedH, native_block_set_sha256: str,
    feature_moments_sha256: str, training_outcomes_sha256: str,
) -> dict[str, Any]:
    value = {
        "schema": _k2_schemas()["optimizer_intent"],
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "training_schedule_sha256": h.training_schedule_sha256,
        "native_block_set_sha256": native_block_set_sha256,
        "feature_moments_sha256": feature_moments_sha256,
        "training_outcomes_sha256": training_outcomes_sha256,
        "dtype": "float64",
        "method": "L-BFGS-B",
        "jacobian": "analytic",
        "start": [0.0] * 8,
        "bounds": None,
        "options": {"maxiter": 10_000, "ftol": 1e-12, "gtol": 1e-10},
        "objective": _K2_OBJECTIVE,
        "coefficient_order": list(_K2_COEFFICIENT_ORDER),
    }
    _validate_optimizer_intent(value)
    return value


def _validate_optimizer_intent(value: Mapping[str, Any]) -> None:
    _keys(value, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "training_schedule_sha256", "native_block_set_sha256",
        "feature_moments_sha256", "training_outcomes_sha256", "dtype",
        "method", "jacobian", "start", "bounds", "options", "objective",
        "coefficient_order",
    }, label="optimizer intent")
    hashes = (
        value["harness_manifest_sha256"], value["training_schedule_sha256"],
        value["native_block_set_sha256"], value["feature_moments_sha256"],
        value["training_outcomes_sha256"],
    )
    if (value["schema"] != _k2_schemas()["optimizer_intent"]
            or not isinstance(value["harness_commit"], str)
            or not _HEX40.fullmatch(value["harness_commit"])
            or any(not isinstance(item, str) or not _HEX64.fullmatch(item)
                   for item in hashes)
            or value["dtype"] != "float64"
            or value["method"] != "L-BFGS-B"
            or value["jacobian"] != "analytic"
            or value["start"] != [0.0] * 8
            or value["bounds"] is not None
            or value["options"] != {
                "maxiter": 10_000, "ftol": 1e-12, "gtol": 1e-10,
            }
            or value["objective"] != _K2_OBJECTIVE
            or value["coefficient_order"] != list(_K2_COEFFICIENT_ORDER)):
        raise shots.LockMismatch("optimizer intent differs from preregistration")


def _make_optimizer_receipt(
    *, intent_record: Mapping[str, Any], intent: Mapping[str, Any],
    success: bool, status: int, beta: Sequence[float], objective_value: float,
    gradient: Sequence[float], independent_objective_value: float,
    independent_gradient: Sequence[float],
    iterations: int, function_evaluations: int,
    gradient_evaluations: int, message: str,
) -> dict[str, Any]:
    _validate_optimizer_intent(intent)
    intent_digest, _, _ = _validate_k2_record_metadata(
        "optimizer_intent", intent_record,
    )
    independent_values = [float(item) for item in independent_gradient]
    reported_gradient = [float(item) for item in gradient]
    independent_maximum = float(
        max(abs(item) for item in independent_values)
    )
    value = {
        "schema": _k2_schemas()["optimizer_receipt"],
        "optimizer_intent_sha256": intent_digest,
        "success": success,
        "status": status,
        "dtype": intent["dtype"],
        "method": intent["method"],
        "jacobian": intent["jacobian"],
        "start": list(intent["start"]),
        "bounds": intent["bounds"],
        "options": dict(intent["options"]),
        "objective": intent["objective"],
        "coefficient_order": list(intent["coefficient_order"]),
        "beta": [float(item) for item in beta],
        "objective_value": float(objective_value),
        "gradient": reported_gradient,
        "gradient_max_abs": float(max(abs(item) for item in reported_gradient)),
        "iterations": iterations,
        "function_evaluations": function_evaluations,
        "gradient_evaluations": gradient_evaluations,
        "message": message,
        "independent_objective_value": float(independent_objective_value),
        "objective_consistent": math.isclose(
            float(objective_value), float(independent_objective_value),
            rel_tol=1e-13, abs_tol=1e-10,
        ),
        "independent_gradient": independent_values,
        "independent_gradient_max_abs": independent_maximum,
        "gradient_consistent": bool(np.allclose(
            reported_gradient, independent_values,
            rtol=1e-11, atol=1e-10,
        )),
        "gradient_acceptance_threshold": shots.OPTIMIZER_GRADIENT_TOLERANCE,
        "gradient_certified": (
            independent_maximum <= shots.OPTIMIZER_GRADIENT_TOLERANCE
        ),
        "beta_distance_actual_bound_l2": float(
            math.sqrt(sum(item * item for item in independent_values))
        ),
        "beta_distance_acceptance_ceiling_l2": (
            shots.OPTIMIZER_BETA_DISTANCE_BOUND_L2
        ),
    }
    _validate_optimizer_receipt(value, intent_record=intent_record, intent=intent)
    return value


def _make_optimizer_receipt_from_fit(
    *, intent_record: Mapping[str, Any], intent: Mapping[str, Any],
    fit: shots.TiltFit,
) -> dict[str, Any]:
    """Preserve every validated SciPy field, including finite refusals."""
    if type(fit) is not shots.TiltFit:
        raise shots.LockMismatch("optimizer result has the wrong typed record")
    expected_maximum = max(abs(value) for value in fit.independent_gradient)
    if (not math.isclose(
                fit.independent_gradient_max_abs, expected_maximum,
                rel_tol=1e-15, abs_tol=1e-15,
            )
            or fit.objective_consistent is not math.isclose(
                fit.objective, fit.independent_objective,
                rel_tol=1e-13, abs_tol=1e-10,
            )
            or fit.gradient_consistent is not bool(np.allclose(
                fit.gradient, fit.independent_gradient,
                rtol=1e-11, atol=1e-10,
            ))
            or fit.gradient_certified is not (
                expected_maximum <= shots.OPTIMIZER_GRADIENT_TOLERANCE
            )
            or not math.isclose(
                fit.beta_distance_actual_bound_l2,
                math.sqrt(sum(value * value
                              for value in fit.independent_gradient)),
                rel_tol=1e-15, abs_tol=1e-15,
            )
            or fit.beta_distance_acceptance_ceiling_l2
                != shots.OPTIMIZER_BETA_DISTANCE_BOUND_L2):
        raise shots.LockMismatch(
            "optimizer typed result changes Amendment 1 certification"
        )
    return _make_optimizer_receipt(
        intent_record=intent_record, intent=intent,
        success=fit.success, status=fit.status, beta=fit.beta,
        objective_value=fit.objective, gradient=fit.gradient,
        independent_objective_value=fit.independent_objective,
        independent_gradient=fit.independent_gradient,
        iterations=fit.iterations,
        function_evaluations=fit.function_evaluations,
        gradient_evaluations=fit.gradient_evaluations,
        message=fit.message,
    )


def _validate_optimizer_receipt(
    value: Mapping[str, Any], *, intent_record: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> None:
    _keys(value, {
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
    }, label="optimizer receipt")
    _validate_optimizer_intent(intent)
    intent_digest, _, _ = _validate_k2_record_metadata(
        "optimizer_intent", intent_record,
    )
    beta = _finite_vector(value["beta"], 8, label="optimizer beta")
    gradient = _finite_vector(value["gradient"], 8, label="final gradient")
    independent_gradient = _finite_vector(
        value["independent_gradient"], 8, label="independent final gradient",
    )
    objective = value["objective_value"]
    independent_objective = value["independent_objective_value"]
    maximum = value["gradient_max_abs"]
    independent_maximum = value["independent_gradient_max_abs"]
    counts = (
        value["iterations"], value["function_evaluations"],
        value["gradient_evaluations"],
    )
    if (value["schema"] != _k2_schemas()["optimizer_receipt"]
            or value["optimizer_intent_sha256"] != intent_digest
            or type(value["success"]) is not bool
            or type(value["status"]) is not int
            or value["dtype"] != intent["dtype"]
            or value["method"] != intent["method"]
            or value["jacobian"] != intent["jacobian"]
            or value["start"] != intent["start"]
            or value["bounds"] != intent["bounds"]
            or value["options"] != intent["options"]
            or value["objective"] != intent["objective"]
            or value["coefficient_order"] != intent["coefficient_order"]
            or type(objective) not in (int, float)
            or not math.isfinite(float(objective)) or float(objective) < 0.0
            or type(independent_objective) not in (int, float)
            or not math.isfinite(float(independent_objective))
            or float(independent_objective) < 0.0
            or type(value["objective_consistent"]) is not bool
            or value["objective_consistent"] is not math.isclose(
                float(objective), float(independent_objective),
                rel_tol=1e-13, abs_tol=1e-10,
            )
            or type(maximum) not in (int, float)
            or not math.isfinite(float(maximum)) or float(maximum) < 0.0
            or type(independent_maximum) not in (int, float)
            or not math.isfinite(float(independent_maximum))
            or float(independent_maximum) < 0.0
            or value["gradient_acceptance_threshold"]
                != shots.OPTIMIZER_GRADIENT_TOLERANCE
            or type(value["gradient_certified"]) is not bool
            or value["gradient_certified"] is not (
                float(independent_maximum)
                <= shots.OPTIMIZER_GRADIENT_TOLERANCE
            )
            or type(value["gradient_consistent"]) is not bool
            or value["gradient_consistent"] is not bool(np.allclose(
                gradient, independent_gradient,
                rtol=1e-11, atol=1e-10,
            ))
            or type(value["beta_distance_actual_bound_l2"])
                not in (int, float)
            or not math.isfinite(float(value["beta_distance_actual_bound_l2"]))
            or float(value["beta_distance_actual_bound_l2"]) < 0.0
            or not math.isclose(
                float(value["beta_distance_actual_bound_l2"]),
                math.sqrt(sum(item * item for item in independent_gradient)),
                rel_tol=1e-15, abs_tol=1e-15,
            )
            or value["beta_distance_acceptance_ceiling_l2"]
                != shots.OPTIMIZER_BETA_DISTANCE_BOUND_L2
            or any(type(item) is not int or item < 0 for item in counts)
            or counts[1] < 1 or counts[2] < 1
            or not isinstance(value["message"], str) or not value["message"]
            or not math.isclose(
                float(maximum), max(abs(item) for item in gradient),
                rel_tol=1e-15, abs_tol=1e-15,
            )
            or not math.isclose(
                float(independent_maximum),
                max(abs(item) for item in independent_gradient),
                rel_tol=1e-15, abs_tol=1e-15,
            )):
        raise shots.LockMismatch("optimizer receipt is malformed or changes intent")
    del beta


def _load_optimizer_artifact_at(
    logical: str, record: Mapping[str, Any], *, directory_fd: int,
) -> tuple[dict[str, Any], bytes]:
    """Load one optimizer artifact relative to its retained transaction root."""
    digest, size, relative = _validate_k2_record_metadata(logical, record)
    name = PurePosixPath(relative).name
    raw = _read_decision_entry_at(
        directory_fd, name, label=f"{logical} artifact", max_bytes=size,
    )
    try:
        value = json.loads(raw.decode("ascii"))
        canonical = _canonical_bytes(value)
    except (UnicodeDecodeError, json.JSONDecodeError, TypeError, ValueError,
            RecursionError) as exc:
        raise shots.LockMismatch(
            f"{logical} artifact is not canonical ASCII JSON"
        ) from exc
    if (not isinstance(value, dict) or canonical != raw or len(raw) != size
            or hashlib.sha256(raw).hexdigest() != digest
            or value.get("schema") != _k2_schemas()[logical]):
        raise shots.LockMismatch(f"{logical} content-addressed bytes differ")
    return value, raw


@contextlib.contextmanager
def _optimizer_artifact_lease_at(
    logical: str, record: Mapping[str, Any], value: Mapping[str, Any],
    *, directory_fd: int,
) -> Iterator[None]:
    """Retain one exact optimizer artifact through transaction acceptance."""
    digest, size, relative = _validate_k2_record_metadata(logical, record)
    raw = _canonical_bytes(value)
    if (len(raw) != size or hashlib.sha256(raw).hexdigest() != digest
            or value.get("schema") != _k2_schemas()[logical]):
        raise shots.LockMismatch(
            f"{logical} lease differs from its content-addressed record"
        )
    with _durably_bind_content_addressed_entry_at(
        directory_fd, PurePosixPath(relative).name,
        expected=raw, label=logical,
    ):
        yield


@contextlib.contextmanager
def _write_optimizer_artifact_lease_at(
    logical: str, value: Mapping[str, Any], *, directory_fd: int,
) -> Iterator[dict[str, Any]]:
    """Create or bind an artifact and retain the exact inode for its caller."""
    if (not isinstance(value, Mapping)
            or value.get("schema") != _k2_schemas()[logical]):
        raise shots.LockMismatch(f"{logical} value has the wrong semantic schema")
    raw = _canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    name = _k2_filename(logical, digest)
    record = {
        "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{name}",
        "sha256": digest, "bytes": len(raw),
        "schema": _k2_schemas()[logical],
    }
    descriptor = -1
    created = False
    create_attempted = False
    name_seen = False
    proven_conflict: shots.LockMismatch | None = None
    body_failure: BaseException | None = None
    failure: BaseException | None = None
    failure_traceback = None
    try:
        try:
            # O_CREAT may have exposed the content-addressed name even when it
            # reports an error, so entering the call is the manual boundary.
            create_attempted = True
            descriptor = os.open(
                name,
                os.O_RDWR | os.O_CREAT | os.O_EXCL
                | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                0o444,
                dir_fd=directory_fd,
            )
            created = True
            name_seen = True
        except FileExistsError:
            name_seen = True
            descriptor = os.open(
                name,
                os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0)
                | getattr(os, "O_CLOEXEC", 0),
                dir_fd=directory_fd,
            )

        opened = os.fstat(descriptor)
        identity = (opened.st_dev, opened.st_ino)
        if created:
            os.lseek(descriptor, 0, os.SEEK_SET)
            written = 0
            while written < len(raw):
                count = os.write(descriptor, raw[written:])
                if count <= 0:
                    raise OSError("optimizer artifact write made no progress")
                written += count
            os.fchmod(descriptor, 0o444)

        def require_current_artifact(
            *, permit_complete_conflict: bool,
        ) -> None:
            nonlocal proven_conflict
            try:
                current = _decision_entry_identity(
                    directory_fd, name, descriptor, label=logical,
                )
                if (current.st_dev, current.st_ino) != identity:
                    raise ManualReconciliationRequired(
                        f"immutable {logical} artifact identity changed; "
                        "manual reconciliation required"
                    )
                if current.st_size != len(raw):
                    raise ManualReconciliationRequired(
                        f"immutable {logical} artifact is not a proven "
                        "complete entry; manual reconciliation required"
                    )
                observed = _read_open_decision_entry_at(
                    directory_fd, name, descriptor, label=logical,
                    max_bytes=len(raw),
                )
            except ManualReconciliationRequired:
                raise
            except BaseException as exc:
                raise ManualReconciliationRequired(
                    f"immutable {logical} artifact identity is ambiguous; "
                    "manual reconciliation required"
                ) from exc
            if observed != raw:
                if permit_complete_conflict:
                    conflict = shots.LockMismatch(
                        f"immutable {logical} content-address collision"
                    )
                    proven_conflict = conflict
                    raise conflict
                raise ManualReconciliationRequired(
                    f"immutable {logical} artifact changed after binding; "
                    "manual reconciliation required"
                )

        require_current_artifact(permit_complete_conflict=not created)
        os.fsync(descriptor)
        require_current_artifact(permit_complete_conflict=False)
        _fsync_artifact_directory(directory_fd)
        require_current_artifact(permit_complete_conflict=False)
        try:
            yield record
        except BaseException as exc:
            body_failure = exc
            raise
        finally:
            require_current_artifact(permit_complete_conflict=False)
    except BaseException as exc:
        failure = exc
        failure_traceback = exc.__traceback__

    close_failure: BaseException | None = None
    if descriptor >= 0:
        try:
            os.close(descriptor)
        except BaseException as exc:
            close_failure = exc
        finally:
            descriptor = -1
    if close_failure is not None:
        message = (
            f"{logical} artifact descriptor cleanup is ambiguous; manual "
            "reconciliation required"
        )
        if failure is not None:
            message += f"; active failure was {failure!r}"
        raise ManualReconciliationRequired(message) from close_failure
    if failure is None:
        return
    if failure is proven_conflict:
        raise failure.with_traceback(failure_traceback)
    if failure is body_failure:
        raise failure.with_traceback(failure_traceback)
    if created:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"{logical} artifact was created before the active failure; "
            "manual reconciliation required"
        ) from failure
    if name_seen or create_attempted:
        if isinstance(failure, ManualReconciliationRequired):
            raise failure.with_traceback(failure_traceback)
        raise ManualReconciliationRequired(
            f"{logical} artifact name could not be durably bound; manual "
            "reconciliation required"
        ) from failure
    if isinstance(failure, (NonPublishingRunStop, shots.ShotsError)):
        raise failure.with_traceback(failure_traceback)
    raise ResumableRunInterruption(
        f"{logical} artifact I/O failed before name creation"
    ) from failure


def _write_optimizer_artifact_at(
    logical: str, value: Mapping[str, Any], *, directory_fd: int,
) -> dict[str, Any]:
    """Compatibility wrapper for one fully leased optimizer artifact."""
    with _write_optimizer_artifact_lease_at(
        logical, value, directory_fd=directory_fd,
    ) as record:
        return record


def _optimizer_records_at(
    logical: str, *, directory_fd: int,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    """Scan optimizer artifacts through one retained transaction root."""
    prefix = logical.replace("_", "-") + "-"
    expression = re.compile(re.escape(prefix) + r"([0-9a-f]{64})\.json")
    output: list[tuple[dict[str, Any], dict[str, Any]]] = []
    try:
        names = sorted(os.listdir(directory_fd))
    except OSError as exc:
        raise shots.LockMismatch(
            "optimizer artifact root could not be scanned"
        ) from exc
    for name in names:
        if not name.startswith(prefix):
            continue
        match = expression.fullmatch(name)
        if match is None:
            raise shots.LockMismatch(f"malformed {logical} filename")
        try:
            size = int(os.stat(
                name, dir_fd=directory_fd, follow_symlinks=False,
            ).st_size)
        except OSError as exc:
            raise shots.LockMismatch(
                f"{logical} artifact could not be inspected"
            ) from exc
        record = {
            "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{name}",
            "sha256": match.group(1), "bytes": size,
            "schema": _k2_schemas()[logical],
        }
        value, _ = _load_optimizer_artifact_at(
            logical, record, directory_fd=directory_fd,
        )
        output.append((record, value))
    return tuple(output)


def _optimizer_records(
    logical: str, *, artifact_root: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    """Compatibility wrapper for a descriptor-relative optimizer scan."""
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            return ()
        return _optimizer_records_at(logical, directory_fd=directory_fd)


def _begin_optimizer_once(
    intent: Mapping[str, Any], *, artifact_root: Path,
) -> _OptimizerAttempt:
    """Durably authorize one invocation or resume an already-receipted result."""
    _validate_optimizer_intent(intent)
    intended_raw = _canonical_bytes(intent)
    intended_digest = hashlib.sha256(intended_raw).hexdigest()
    with _open_decision_state_directory(
        Path(artifact_root), create=True,
    ) as (_, directory_fd):
        assert directory_fd is not None
        prior_intents = _optimizer_records_at(
            "optimizer_intent", directory_fd=directory_fd,
        )
        prior_receipts = _optimizer_records_at(
            "optimizer_receipt", directory_fd=directory_fd,
        )
        with _digest_reservation_at(
            directory_fd, "optimizer-intent", intended_digest,
            create=not prior_intents and not prior_receipts,
        ) as claim_created:
            intents = _optimizer_records_at(
                "optimizer_intent", directory_fd=directory_fd,
            )
            receipts = _optimizer_records_at(
                "optimizer_receipt", directory_fd=directory_fd,
            )
            if len(intents) > 1 or len(receipts) > 1:
                raise shots.LockMismatch("optimizer transaction has forked artifacts")
            if not intents:
                if receipts:
                    raise shots.LockMismatch(
                        "optimizer receipt exists without its intent"
                    )
                if not claim_created:
                    raise ManualReconciliationRequired(
                        "optimizer intent was claimed without durable intent bytes; "
                        "invocation state is ambiguous"
                    )
                with _write_optimizer_artifact_lease_at(
                    "optimizer_intent", intent,
                    directory_fd=directory_fd,
                ) as record:
                    final_intents = _optimizer_records_at(
                        "optimizer_intent", directory_fd=directory_fd,
                    )
                    final_receipts = _optimizer_records_at(
                        "optimizer_receipt", directory_fd=directory_fd,
                    )
                    _fsync_artifact_directory(directory_fd)
                    final_intents = _optimizer_records_at(
                        "optimizer_intent", directory_fd=directory_fd,
                    )
                    final_receipts = _optimizer_records_at(
                        "optimizer_receipt", directory_fd=directory_fd,
                    )
                    if (final_intents != ((record, dict(intent)),)
                            or final_receipts):
                        raise shots.LockMismatch(
                            "optimizer transaction changed before authorization"
                        )
                    return _OptimizerAttempt(
                        record, dict(intent), True, None, None,
                    )

            if claim_created:
                raise ManualReconciliationRequired(
                    "optimizer artifacts predate their durable intent claim; "
                    "invocation state is ambiguous"
                )
            intent_record, stored_intent = intents[0]
            if (intent_record["sha256"] != intended_digest
                    or _canonical_bytes(stored_intent) != intended_raw):
                raise shots.LockMismatch(
                    "a different optimizer intent already exists"
                )
            with _optimizer_artifact_lease_at(
                "optimizer_intent", intent_record, stored_intent,
                directory_fd=directory_fd,
            ):
                if not receipts:
                    raise ManualReconciliationRequired(
                        "optimizer intent exists without a receipt; "
                        "invocation state is ambiguous"
                    )
                receipt_record, receipt = receipts[0]
                with _digest_reservation_at(
                    directory_fd, "optimizer-receipt",
                    str(receipt_record["sha256"]), create=False,
                ):
                    with _optimizer_artifact_lease_at(
                        "optimizer_receipt", receipt_record, receipt,
                        directory_fd=directory_fd,
                    ):
                        _validate_optimizer_receipt(
                            receipt, intent_record=intent_record,
                            intent=stored_intent,
                        )
                        _fsync_artifact_directory(directory_fd)
                        if (intents != _optimizer_records_at(
                                    "optimizer_intent",
                                    directory_fd=directory_fd,
                                )
                                or receipts != _optimizer_records_at(
                                    "optimizer_receipt",
                                    directory_fd=directory_fd,
                                )):
                            raise shots.LockMismatch(
                                "optimizer transaction changed while resuming"
                            )
                        return _OptimizerAttempt(
                            intent_record, stored_intent, False,
                            receipt_record, receipt,
                        )


def _record_optimizer_receipt(
    *, intent_record: Mapping[str, Any], receipt: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    """Commit the sole result receipt without permitting replacement."""
    intent_digest, _, _ = _validate_k2_record_metadata(
        "optimizer_intent", intent_record,
    )
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            raise shots.LockMismatch("optimizer artifact root is absent")
        with _digest_reservation_at(
            directory_fd, "optimizer-intent", intent_digest, create=False,
        ):
            intent, _ = _load_optimizer_artifact_at(
                "optimizer_intent", intent_record,
                directory_fd=directory_fd,
            )
            with _optimizer_artifact_lease_at(
                "optimizer_intent", intent_record, intent,
                directory_fd=directory_fd,
            ):
                _validate_optimizer_receipt(
                    receipt, intent_record=intent_record, intent=intent,
                )
                expected_raw = _canonical_bytes(receipt)
                expected_digest = hashlib.sha256(expected_raw).hexdigest()
                intents = _optimizer_records_at(
                    "optimizer_intent", directory_fd=directory_fd,
                )
                receipts = _optimizer_records_at(
                    "optimizer_receipt", directory_fd=directory_fd,
                )
                if (len(intents) != 1
                        or intents[0][0] != dict(intent_record)
                        or _canonical_bytes(intents[0][1])
                        != _canonical_bytes(intent)
                        or len(receipts) > 1):
                    raise shots.LockMismatch(
                        "optimizer transaction identity is not unique"
                    )
                with _digest_reservation_at(
                    directory_fd, "optimizer-receipt", expected_digest,
                    create=not receipts,
                ) as claim_created:
                    with contextlib.ExitStack() as receipt_lease:
                        if receipts:
                            if claim_created:
                                raise ManualReconciliationRequired(
                                    "optimizer receipt predates its durable claim; "
                                    "result state is ambiguous"
                                )
                            record, stored = receipts[0]
                            if (record["sha256"] != expected_digest
                                    or _canonical_bytes(stored) != expected_raw):
                                raise shots.LockMismatch(
                                    "a different optimizer receipt already exists"
                                )
                            receipt_lease.enter_context(
                                _optimizer_artifact_lease_at(
                                    "optimizer_receipt", record, receipt,
                                    directory_fd=directory_fd,
                                )
                            )
                        else:
                            if not claim_created:
                                raise ManualReconciliationRequired(
                                    "optimizer receipt was claimed without durable "
                                    "bytes; result state is ambiguous"
                                )
                            record = receipt_lease.enter_context(
                                _write_optimizer_artifact_lease_at(
                                    "optimizer_receipt", receipt,
                                    directory_fd=directory_fd,
                                )
                            )
                        final_intents = _optimizer_records_at(
                            "optimizer_intent", directory_fd=directory_fd,
                        )
                        final_receipts = _optimizer_records_at(
                            "optimizer_receipt", directory_fd=directory_fd,
                        )
                        _fsync_artifact_directory(directory_fd)
                        final_intents = _optimizer_records_at(
                            "optimizer_intent", directory_fd=directory_fd,
                        )
                        final_receipts = _optimizer_records_at(
                            "optimizer_receipt", directory_fd=directory_fd,
                        )
                        if (final_intents != intents
                                or final_receipts
                                != ((record, dict(receipt)),)):
                            raise shots.LockMismatch(
                                "optimizer transaction changed while recording "
                                "receipt"
                            )
                        return record


# ==========================================================================
# PRE-H K2 construction and independent semantic recomputation
# ==========================================================================


@dataclass(frozen=True)
class _K2TrainingReference:
    """Outcome/shot facts independently rebuilt from the pinned inputs."""

    schedule_sha256: str
    outcomes: tuple[int, ...]
    shot_expectations: tuple[tuple[float, float, float, float], ...]
    features: tuple[tuple[float, float, float, float], ...]


def _schedule_blocks_exact(
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[tuple[Mapping[str, Any], ...], ...]:
    if not schedule:
        raise shots.FixtureSetMismatch("training schedule is empty")
    blocks: list[list[Mapping[str, Any]]] = []
    closed: set[str] = set()
    identifiers: set[str] = set()
    for ordinal, row in enumerate(schedule):
        if not isinstance(row, Mapping) or set(row) != set(_K2_SCHEDULE_FIELDS):
            raise shots.LockMismatch("training schedule fields differ")
        if (type(row["ordinal"]) is not int or row["ordinal"] != ordinal
                or any(not isinstance(row[name], str) or not row[name]
                       for name in _K2_SCHEDULE_FIELDS if name != "ordinal")):
            raise shots.FixtureSetMismatch("training schedule identity is malformed")
        if row["match_id"] in identifiers:
            raise shots.FixtureSetMismatch("training schedule match_id is duplicated")
        identifiers.add(row["match_id"])
        if row["date"] != _iso_date(row["date"]):
            raise shots.TimeBoundaryViolation("training schedule date is not exact ISO")
        if row["cutoff"] != _iso_date(row["cutoff"]):
            raise shots.TimeBoundaryViolation("training cutoff is not exact ISO")
        if not blocks or blocks[-1][0]["block"] != row["block"]:
            if row["block"] in closed:
                raise shots.FixtureSetMismatch("training block is not contiguous")
            if blocks:
                closed.add(str(blocks[-1][0]["block"]))
            blocks.append([])
        if blocks[-1] and (
            blocks[-1][0]["season"] != row["season"]
            or blocks[-1][0]["cutoff"] != row["cutoff"]
        ):
            raise shots.FixtureSetMismatch("one training block has mixed identity")
        blocks[-1].append(row)
    return tuple(tuple(block) for block in blocks)


def _validate_k2_training_reference(
    reference: _K2TrainingReference,
    *, schedule: Sequence[Mapping[str, Any]],
) -> _K2TrainingReference:
    """Validate an immutable reference without consulting stored K values."""
    if type(reference) is not _K2TrainingReference:
        raise shots.LockMismatch("K2 training reference has the wrong type")
    if (type(reference.outcomes) is not tuple
            or type(reference.shot_expectations) is not tuple
            or type(reference.features) is not tuple):
        raise shots.LockMismatch("K2 training reference must be immutable")
    schedule_sha256 = _digest_rows(_K2_SCHEDULE_SCHEMA, schedule)
    if (reference.schedule_sha256 != schedule_sha256
            or len(reference.outcomes) != len(schedule)
            or len(reference.shot_expectations) != len(schedule)
            or len(reference.features) != len(schedule)):
        raise shots.FixtureSetMismatch(
            "K2 training reference differs from the ordered schedule"
        )
    if any(type(value) is not int or value not in (0, 1, 2)
           for value in reference.outcomes):
        raise shots.FitFailure("K2 training reference has an invalid outcome")
    for values in reference.shot_expectations:
        if type(values) is not tuple:
            raise shots.LockMismatch(
                "reference shot expectations must be immutable tuples"
            )
        checked = _finite_vector(
            list(values), 4, label="reference shot expectations",
        )
        if any(value <= 0.0 for value in checked):
            raise shots.FitFailure(
                "K2 training reference has a nonpositive shot expectation"
            )
    for values in reference.features:
        if type(values) is not tuple:
            raise shots.LockMismatch(
                "reference shot features must be immutable tuples"
            )
        _finite_vector(list(values), 4, label="reference shot features")
    return reference


@dataclass(frozen=True)
class _IndependentK2ShotPanel:
    """Minimal panel rebuilt without the production shot-ingestion path."""

    frame: pd.DataFrame
    raw_rows: int
    source_digests: Mapping[str, str]


def _independent_parse_k2_training_csv(
    raw: bytes, *, source: str, season_code: str,
) -> pd.DataFrame:
    """Parse one pinned training CSV using a literal seven-column contract."""
    if type(raw) is not bytes or not raw:
        raise shots.ShotSchemaMismatch(f"{source}: raw CSV bytes are absent")
    try:
        text = raw.decode("utf-8-sig", errors="strict")
    except UnicodeDecodeError as exc:
        raise shots.ShotSchemaMismatch(
            f"{source}: raw CSV is not strict UTF-8"
        ) from exc
    reader = csv.reader(io.StringIO(text))
    try:
        header = [str(value).strip() for value in next(reader)]
    except StopIteration as exc:
        raise shots.ShotSchemaMismatch(f"{source}: empty CSV") from exc
    required = ("Date", "HomeTeam", "AwayTeam", "HS", "AS", "HST", "AST")
    for name in required:
        if header.count(name) != 1:
            raise shots.ShotSchemaMismatch(
                f"{source}: required column {name!r} must occur exactly once"
            )
    positions = {name: header.index(name) for name in required}
    last_required = max(positions.values())
    team_keys = {
        "Arsenal": "arsenal", "Aston Villa": "aston_villa",
        "Bournemouth": "bournemouth", "Brighton": "brighton",
        "Burnley": "burnley", "Cardiff": "cardiff", "Chelsea": "chelsea",
        "Crystal Palace": "crystal_palace", "Everton": "everton",
        "Fulham": "fulham", "Huddersfield": "huddersfield", "Hull": "hull",
        "Leicester": "leicester", "Liverpool": "liverpool",
        "Man City": "man_city", "Man United": "man_united",
        "Middlesbrough": "middlesbrough", "Newcastle": "newcastle",
        "Norwich": "norwich", "QPR": "qpr", "Southampton": "southampton",
        "Stoke": "stoke", "Sunderland": "sunderland", "Swansea": "swansea",
        "Tottenham": "tottenham", "Watford": "watford",
        "West Brom": "west_brom", "West Ham": "west_ham", "Wolves": "wolves",
    }
    records: list[dict[str, Any]] = []
    for raw_row, values in enumerate(reader, 2):
        if not values:
            continue
        identity = [
            values[positions[name]].strip() if positions[name] < len(values) else ""
            for name in ("Date", "HomeTeam", "AwayTeam")
        ]
        if not any(identity):
            continue
        if len(values) <= last_required:
            raise shots.ShotSchemaMismatch(
                f"{source}:{raw_row}: row ends before an allowlisted column"
            )
        if not all(identity):
            raise shots.ShotPanelMismatch(
                f"{source}:{raw_row}: Date/HomeTeam/AwayTeam is partially blank"
            )
        parsed_date: pd.Timestamp | None = None
        for date_format in ("%d/%m/%y", "%d/%m/%Y"):
            try:
                parsed_date = pd.Timestamp(
                    datetime.strptime(identity[0], date_format)
                ).normalize()
                break
            except ValueError:
                continue
        if parsed_date is None:
            raise shots.ShotValueInvalid(
                f"{source}:{raw_row}: Date does not match either frozen format"
            )
        if identity[1] not in team_keys or identity[2] not in team_keys:
            raise shots.ShotPanelMismatch(
                f"{source}:{raw_row}: team spelling is not in the literal registry"
            )
        home_key = team_keys[identity[1]]
        away_key = team_keys[identity[2]]
        if home_key == away_key:
            raise shots.ShotPanelMismatch(
                f"{source}:{raw_row}: home and away resolve to the same club"
            )
        parsed_shots: dict[str, float] = {}
        for name in ("HS", "AS", "HST", "AST"):
            token = values[positions[name]].strip()
            if not token:
                raise shots.ShotValueInvalid(
                    f"{source}:{raw_row}: {name} is missing"
                )
            try:
                value = float(token)
            except ValueError as exc:
                raise shots.ShotValueInvalid(
                    f"{source}:{raw_row}: {name} is nonnumeric"
                ) from exc
            if (not math.isfinite(value) or value < 0.0
                    or value != math.floor(value)):
                raise shots.ShotValueInvalid(
                    f"{source}:{raw_row}: {name} is not a finite nonnegative integer"
                )
            parsed_shots[name] = value
        if (parsed_shots["HST"] > parsed_shots["HS"]
                or parsed_shots["AST"] > parsed_shots["AS"]):
            raise shots.ShotValueInvalid(
                f"{source}:{raw_row}: shots on target exceed total shots"
            )
        records.append({
            "season_code": season_code, "date": parsed_date,
            "home_key": home_key, "away_key": away_key,
            **parsed_shots, "source": source, "raw_row": raw_row,
        })
    if len(records) != 380:
        raise shots.ShotPanelMismatch(
            f"{source}: parsed {len(records)} rows, expected exactly 380"
        )
    return pd.DataFrame.from_records(records, columns=[
        "season_code", "date", "home_key", "away_key",
        "HS", "AS", "HST", "AST", "source", "raw_row",
    ])


def _independent_k2_training_shot_panel(
    archive_bytes: bytes,
) -> _IndependentK2ShotPanel:
    """Read, parse, validate, and join only the five pinned training CSVs."""
    expected_archive_sha256 = (
        "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"
    )
    if (type(archive_bytes) is not bytes
            or hashlib.sha256(archive_bytes).hexdigest()
                != expected_archive_sha256):
        raise shots.SourceDigestMismatch(
            "independent K2 shot join did not receive the pinned archive bytes"
        )
    names = (
        "E0_1415.csv", "E0_1516.csv", "E0_1617.csv", "E0_1718.csv",
        "E0_1819.csv",
    )
    expected_digests = _native_raw_digests()
    if tuple(expected_digests) != names:
        raise shots.LockMismatch("independent K2 raw pin set differs")
    parts: list[pd.DataFrame] = []
    observed_digests: dict[str, str] = {}
    for name in names:
        raw = _read_regular_snapshot(
            paths.RAW_DIR / name, label=f"independent K2 raw {name}",
        )
        digest = hashlib.sha256(raw).hexdigest()
        observed_digests[name] = digest
        if digest != expected_digests[name]:
            raise shots.SourceDigestMismatch(
                f"{name}: independent K2 raw SHA-256 differs"
            )
        parts.append(_independent_parse_k2_training_csv(
            raw, source=name,
            season_code=name.removeprefix("E0_").removesuffix(".csv"),
        ))
    raw_rows = pd.concat(parts, ignore_index=True)
    if len(raw_rows) != 1_900:
        raise shots.ShotPanelMismatch(
            "independent K2 raw panel is not exactly 1,900 rows"
        )
    raw_key = ["date", "home_key", "away_key"]
    if raw_rows.duplicated(raw_key).any():
        raise shots.ShotPanelMismatch(
            "independent K2 raw panel has a duplicate match identity"
        )

    try:
        archive = pd.read_parquet(
            io.BytesIO(archive_bytes),
            columns=[
                "match_id", "season_code", "date", "home_key", "away_key",
            ],
            filters=[("season_code", "in", [
                "1415", "1516", "1617", "1718", "1819",
            ])],
        )
    except Exception as exc:
        raise shots.ShotPanelMismatch(
            "independent K2 identity archive could not be projected"
        ) from exc
    required_archive = {
        "match_id", "season_code", "date", "home_key", "away_key",
    }
    if not isinstance(archive, pd.DataFrame) or set(archive.columns) != required_archive:
        raise shots.ShotPanelMismatch(
            "independent K2 identity archive columns differ"
        )
    archive = archive.copy()
    try:
        archive["date"] = pd.to_datetime(
            archive["date"], errors="raise",
        ).dt.normalize()
    except (TypeError, ValueError) as exc:
        raise shots.ShotPanelMismatch(
            "independent K2 identity archive has an invalid date"
        ) from exc
    archive_counts = archive["season_code"].astype(str).value_counts().to_dict()
    if (len(archive) != 1_900
            or archive_counts != {
                "1415": 380, "1516": 380, "1617": 380,
                "1718": 380, "1819": 380,
            }
            or archive["match_id"].isna().any()
            or (archive["match_id"].astype(str).str.strip() == "").any()
            or archive["match_id"].astype(str).duplicated().any()
            or archive.duplicated(raw_key).any()):
        raise shots.ShotPanelMismatch(
            "independent K2 identity archive grain/counts differ"
        )
    for name in ("season_code", "home_key", "away_key"):
        if (archive[name].isna().any()
                or (archive[name].astype(str).str.strip() == "").any()):
            raise shots.ShotPanelMismatch(
                f"independent K2 archive {name} is empty"
            )
    archive = archive.rename(columns={"season_code": "_archive_season_code"})
    try:
        joined = raw_rows.merge(
            archive, on=raw_key, how="left", validate="one_to_one",
            indicator=True,
        )
    except pd.errors.MergeError as exc:
        raise shots.ShotPanelMismatch(
            "independent K2 raw/archive join is not one-to-one"
        ) from exc
    if (len(joined) != 1_900 or (joined["_merge"] != "both").any()
            or joined["match_id"].isna().any()
            or joined["match_id"].astype(str).duplicated().any()
            or not joined["season_code"].astype(str).equals(
                joined["_archive_season_code"].astype(str)
            )):
        raise shots.ShotPanelMismatch(
            "independent K2 raw/archive identity join differs"
        )
    frame = joined[[
        "season_code", "date", "home_key", "away_key",
        "HS", "AS", "HST", "AST", "source", "raw_row", "match_id",
    ]].sort_values(
        ["date", "home_key", "away_key"], kind="mergesort",
    ).reset_index(drop=True)
    return _IndependentK2ShotPanel(
        frame=frame, raw_rows=len(raw_rows),
        source_digests=MappingProxyType(dict(observed_digests)),
    )


def _independent_k2_shot_reference(
    panel: _IndependentK2ShotPanel,
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[
    tuple[tuple[float, float, float, float], ...],
    tuple[tuple[float, float, float, float], ...],
]:
    """Literally rebuild the preregistered shot expectations and features.

    This is intentionally separate from ``shots.shot_features`` and
    ``shots._ratios``.  K must be able to reject a self-consistent error in the
    production feature path, so this verifier owns its validation and repeats
    the frozen equations directly from the pinned five-season shot panel.
    """
    blocks = _schedule_blocks_exact(schedule)
    expected_season_rows = {
        "2015/16": 380, "2016/17": 380,
        "2017/18": 380, "2018/19": 380,
    }
    expected_block_counts = {
        "2015/16": 35, "2016/17": 36,
        "2017/18": 36, "2018/19": 35,
    }
    season_codes = {
        "2015/16": "1516", "2016/17": "1617",
        "2017/18": "1718", "2018/19": "1819",
    }
    if (len(schedule) != 1_520 or len(blocks) != 142
            or {str(row["season"]) for row in schedule} != set(season_codes)):
        raise shots.FixtureSetMismatch(
            "independent shot reference requires the exact training schedule"
        )
    schedule_counts: dict[str, int] = {}
    schedule_blocks: dict[str, set[str]] = {}
    for block in blocks:
        block_dates = [pd.Timestamp(row["date"]) for row in block]
        expected_cutoff = min(block_dates)
        for row, date in zip(block, block_dates, strict=True):
            season = str(row["season"])
            schedule_counts[season] = schedule_counts.get(season, 0) + 1
            schedule_blocks.setdefault(season, set()).add(str(row["block"]))
            iso = date.isocalendar()
            expected_block = f"{season}|{int(iso.year)}W{int(iso.week):02d}"
            if (date != date.normalize()
                    or str(row["block"]) != expected_block
                    or pd.Timestamp(row["cutoff"]) != expected_cutoff):
                raise shots.TimeBoundaryViolation(
                    "independent training block/cutoff identity differs"
                )
    if (schedule_counts != expected_season_rows
            or {season: len(names) for season, names in schedule_blocks.items()}
                != expected_block_counts):
        raise shots.FixtureSetMismatch(
            "independent training season/block counts differ"
        )

    if type(panel) is not _IndependentK2ShotPanel:
        raise shots.LockMismatch("pinned training shot panel has the wrong type")
    required_columns = {
        "season_code", "date", "home_key", "away_key",
        "HS", "AS", "HST", "AST", "source", "raw_row", "match_id",
    }
    frame = panel.frame
    if (not isinstance(frame, pd.DataFrame)
            or set(frame.columns) != required_columns
            or panel.raw_rows != 1_900 or len(frame) != 1_900
            or dict(panel.source_digests) != _native_raw_digests()):
        raise shots.ShotPanelMismatch(
            "independent reference did not receive the exact pinned shot panel"
        )
    history = frame[list(required_columns)].copy()
    history["date"] = pd.to_datetime(history["date"], errors="raise")
    if (history["date"].isna().any()
            or not (history["date"] == history["date"].dt.normalize()).all()
            or history.duplicated(["date", "home_key", "away_key"]).any()
            or history["match_id"].astype(str).duplicated().any()):
        raise shots.ShotPanelMismatch(
            "independent shot history identity is malformed or duplicated"
        )
    for name in ("season_code", "home_key", "away_key", "source", "match_id"):
        values = history[name]
        if values.isna().any() or (values.astype(str).str.strip() == "").any():
            raise shots.ShotPanelMismatch(
                f"independent shot history {name} is empty"
            )
    history_counts = history["season_code"].astype(str).value_counts().to_dict()
    if history_counts != {code: 380 for code in ("1415", "1516", "1617", "1718", "1819")}:
        raise shots.ShotPanelMismatch(
            "independent five-season shot-history counts differ"
        )
    expected_sources = history["season_code"].astype(str).map(
        lambda code: f"E0_{code}.csv"
    )
    if not history["source"].astype(str).equals(expected_sources):
        raise shots.ShotPanelMismatch(
            "independent shot-history source/season identity differs"
        )
    shot_values = history[["HS", "AS", "HST", "AST"]].to_numpy(
        dtype=np.float64,
    )
    if (not np.isfinite(shot_values).all() or (shot_values < 0.0).any()
            or not np.equal(shot_values, np.floor(shot_values)).all()
            or (shot_values[:, 2] > shot_values[:, 0]).any()
            or (shot_values[:, 3] > shot_values[:, 1]).any()):
        raise shots.ShotValueInvalid(
            "independent shot history contains an invalid count"
        )
    canonical = history.sort_values(
        ["date", "home_key", "away_key"], kind="mergesort",
    ).reset_index(drop=True)
    if tuple(history["match_id"].astype(str)) != tuple(
        canonical["match_id"].astype(str)
    ):
        raise shots.ShotPanelMismatch(
            "independent shot history is not in canonical order"
        )
    history = canonical

    by_match = history.set_index(history["match_id"].astype(str), drop=False)
    for row in schedule:
        match_id = str(row["match_id"])
        if match_id not in by_match.index:
            raise shots.FixtureSetMismatch(
                "training fixture is absent from the pinned shot panel"
            )
        pinned = by_match.loc[match_id]
        if (str(pinned["season_code"]) != season_codes[str(row["season"])]
                or pinned["date"].strftime("%Y-%m-%d") != row["date"]
                or str(pinned["home_key"]) != row["home_key"]
                or str(pinned["away_key"]) != row["away_key"]):
            raise shots.FixtureSetMismatch(
                "training fixture differs from the pinned shot-panel identity"
            )

    def ratios(
        eligible: pd.DataFrame, weights: np.ndarray, *,
        home_col: str, away_col: str, mean_home: float, mean_away: float,
    ) -> tuple[dict[str, float], dict[str, float]]:
        attack_num: dict[str, float] = {}
        attack_den: dict[str, float] = {}
        defence_num: dict[str, float] = {}
        defence_den: dict[str, float] = {}

        def add(
            numerator: dict[str, float], denominator: dict[str, float],
            team: str, weight: float, normalized: float,
        ) -> None:
            numerator[team] = numerator.get(team, 0.0) + weight * normalized
            denominator[team] = denominator.get(team, 0.0) + weight

        for observation, raw_weight in zip(
            eligible.itertuples(index=False), weights, strict=True,
        ):
            weight = float(raw_weight)
            home = str(observation.home_key)
            away = str(observation.away_key)
            home_value = float(getattr(observation, home_col))
            away_value = float(getattr(observation, away_col))
            add(attack_num, attack_den, home, weight, home_value / mean_home)
            add(attack_num, attack_den, away, weight, away_value / mean_away)
            add(defence_num, defence_den, home, weight, away_value / mean_away)
            add(defence_num, defence_den, away, weight, home_value / mean_home)
        teams = set(attack_den) | set(defence_den)
        attack = {
            team: (10.0 + attack_num.get(team, 0.0))
                  / (10.0 + attack_den.get(team, 0.0))
            for team in teams
        }
        defence = {
            team: (10.0 + defence_num.get(team, 0.0))
                  / (10.0 + defence_den.get(team, 0.0))
            for team in teams
        }
        return attack, defence

    expectations: list[tuple[float, float, float, float]] = []
    features: list[tuple[float, float, float, float]] = []
    for block in blocks:
        cutoff = pd.Timestamp(block[0]["cutoff"])
        eligible = history.loc[history["date"] < cutoff].copy()
        if eligible.empty or (eligible["date"] >= cutoff).any():
            raise shots.TimeBoundaryViolation(
                "independent shot reference has no strict pre-cutoff history"
            )
        age_days = (cutoff - eligible["date"]).dt.days.to_numpy(
            dtype=np.float64,
        )
        if (age_days <= 0.0).any():
            raise shots.TimeBoundaryViolation(
                "date at or after cutoff entered the independent reference"
            )
        weights = np.power(2.0, -age_days / 365.0)
        means = {
            name: float(np.average(
                eligible[name].to_numpy(dtype=np.float64), weights=weights,
            ))
            for name in ("HS", "AS", "HST", "AST")
        }
        if any(not math.isfinite(value) or value <= 0.0
               for value in means.values()):
            raise shots.FitFailure(
                "independent weighted league mean is not positive and finite"
            )
        attack_shots, defence_shots = ratios(
            eligible, weights, home_col="HS", away_col="AS",
            mean_home=means["HS"], mean_away=means["AS"],
        )
        attack_sot, defence_sot = ratios(
            eligible, weights, home_col="HST", away_col="AST",
            mean_home=means["HST"], mean_away=means["AST"],
        )
        for row in block:
            home = str(row["home_key"])
            away = str(row["away_key"])
            hs = (means["HS"] * attack_shots.get(home, 1.0)
                  * defence_shots.get(away, 1.0))
            away_shots = (means["AS"] * attack_shots.get(away, 1.0)
                          * defence_shots.get(home, 1.0))
            hst = (means["HST"] * attack_sot.get(home, 1.0)
                   * defence_sot.get(away, 1.0))
            ast = (means["AST"] * attack_sot.get(away, 1.0)
                   * defence_sot.get(home, 1.0))
            expectation = (hs, away_shots, hst, ast)
            feature = (
                hst - ast,
                (hs - hst) - (away_shots - ast),
                hst + ast,
                (hs - hst) + (away_shots - ast),
            )
            if (not all(math.isfinite(value) and value > 0.0
                        for value in expectation)
                    or not all(math.isfinite(value) for value in feature)):
                raise shots.FitFailure(
                    "independent shot expectation/feature is invalid"
                )
            expectations.append(expectation)
            features.append(feature)
    if len(expectations) != len(schedule) or len(features) != len(schedule):
        raise shots.FixtureSetMismatch(
            "independent shot reference output order/length differs"
        )
    return tuple(expectations), tuple(features)


def _load_pinned_k2_training_reference(
    schedule: Sequence[Mapping[str, Any]],
) -> _K2TrainingReference:
    """Rebuild the exact training outcomes and shot features from pinned data.

    The archive projection is filtered to the four coefficient-training
    seasons and never includes odds or decision-season outcomes.  Outcomes are
    derived from the two goal columns rather than accepted from an artifact or
    an archive result label.  Shot expectations/features are independently
    rebuilt from the five-season, digest-pinned shot panel.
    """
    blocks = _schedule_blocks_exact(schedule)
    if len(schedule) != shots.TRAINING_ROWS or len(blocks) != 142:
        raise shots.FixtureSetMismatch(
            "production K verification requires the pinned 1,520-row, "
            "142-block training schedule"
        )

    archive_path = paths.MATCHES_PARQUET
    if not archive_path.is_file():
        raise shots.SourceDigestMismatch(
            f"{shots.MATCHES_PATH}: pinned file is absent at {archive_path}"
        )
    archive_bytes = _read_regular_snapshot(
        archive_path, label="independent K2 matches archive",
    )
    archive_sha256 = hashlib.sha256(archive_bytes).hexdigest()
    expected_archive_sha256 = (
        "323aa54af0a8fcf38745c9f7fccc55fe10654ff68cf38fa82cf7f498cea275cf"
    )
    if archive_sha256 != expected_archive_sha256:
        raise shots.SourceDigestMismatch(
            f"{shots.MATCHES_PATH}: SHA-256 {archive_sha256}, "
            f"expected {expected_archive_sha256}"
        )
    archive = pd.read_parquet(
        io.BytesIO(archive_bytes),
        columns=[
            "match_id", "season", "date", "home_key", "away_key",
            "fthg", "ftag", "played",
        ],
        filters=[("season", "in", list(shots.TRAINING_SEASONS))],
    )
    counts = archive["season"].astype(str).value_counts().to_dict()
    expected_counts = {season: 380 for season in shots.TRAINING_SEASONS}
    if (len(archive) != shots.TRAINING_ROWS or counts != expected_counts
            or archive["match_id"].astype(str).duplicated().any()
            or not pd.api.types.is_bool_dtype(archive["played"].dtype)
            or not bool(archive["played"].all())):
        raise shots.FixtureSetMismatch(
            "pinned archive training outcome projection differs: "
            f"rows={len(archive)}, seasons={counts}"
        )

    fixture_frame = shots.attach_training_cutoffs(archive[[
        "match_id", "season", "date", "home_key", "away_key",
    ]])
    pinned_schedule = tuple({
        "ordinal": ordinal,
        "match_id": str(row.match_id),
        "season": str(row.season),
        "date": _iso_date(row.date),
        "home_key": str(row.home_key),
        "away_key": str(row.away_key),
        "block": str(row.block),
        "cutoff": _iso_date(row.cutoff),
    } for ordinal, row in enumerate(fixture_frame.itertuples(index=False)))
    if tuple(dict(row) for row in schedule) != pinned_schedule:
        raise shots.FixtureSetMismatch(
            "K2 schedule differs from the independently parsed pinned archive"
        )

    goals = archive[["fthg", "ftag"]].to_numpy(dtype=np.float64)
    if (not np.isfinite(goals).all() or (goals < 0.0).any()
            or not np.equal(goals, np.floor(goals)).all()):
        raise shots.FitFailure(
            "pinned training goals are not finite nonnegative integers"
        )
    outcomes_array = np.where(
        goals[:, 0] > goals[:, 1], 0,
        np.where(goals[:, 0] < goals[:, 1], 2, 1),
    )

    panel = _independent_k2_training_shot_panel(archive_bytes)
    shot_expectations, features = _independent_k2_shot_reference(
        panel, schedule,
    )
    reference = _K2TrainingReference(
        schedule_sha256=_digest_rows(_K2_SCHEDULE_SCHEMA, schedule),
        outcomes=tuple(int(value) for value in outcomes_array),
        shot_expectations=shot_expectations,
        features=features,
    )
    return _validate_k2_training_reference(reference, schedule=schedule)


def _k2_training_reference(
    schedule: Sequence[Mapping[str, Any]],
    *, _test_only_reference: _K2TrainingReference | None,
) -> _K2TrainingReference:
    """Select the production pinned reference or an explicit small-test one."""
    if _test_only_reference is None:
        return _load_pinned_k2_training_reference(schedule)
    if len(schedule) == shots.TRAINING_ROWS:
        raise shots.LockMismatch(
            "a test-only K2 reference cannot replace the production reference"
        )
    return _validate_k2_training_reference(
        _test_only_reference, schedule=schedule,
    )


def _probability_vector(
    value: Any, *, label: str, strictly_positive: bool,
    stored_native: bool = False,
) -> tuple[float, float, float]:
    vector = _finite_vector(value, 3, label=label)
    sum_tolerance = (
        shots.NATIVE_STORED_SUM_TOLERANCE
        if stored_native else shots.MODEL_PROBABILITY_SUM_TOLERANCE
    )
    if (any(item < 0.0 or item > 1.0 for item in vector)
            or strictly_positive and any(item <= 0.0 for item in vector)
            or abs(sum(vector) - 1.0) > sum_tolerance):
        raise shots.ProbabilityInvalid(
            f"{label} is outside the frozen probability simplex"
        )
    if stored_native and any(item != round(item, 8) for item in vector):
        raise shots.ProbabilityInvalid(
            f"{label} is not the exact eight-decimal stored native value"
        )
    return vector


def _validate_native_shards_for_k(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    training_sha256: str, native_intent_sha256: str,
    shards: Sequence[Mapping[str, Any]],
) -> tuple[np.ndarray, np.ndarray]:
    blocks = _schedule_blocks_exact(schedule)
    if len(shards) != len(blocks):
        raise shots.FixtureSetMismatch("native shard count differs from schedule")
    native_rows: list[tuple[float, float, float]] = []
    outcomes: list[int] = []
    outer_fields = {
        "schema", "native_intent_sha256", "block_identity_sha256",
        "harness_commit", "harness_manifest_sha256",
        "parent_commit", "parent_tree",
        "training_schedule_sha256", "block_ordinal", "block", "cutoff",
        "rows", "receipt",
    }
    row_fields = {
        "ordinal", "match_id", "season", "block", "cutoff", "home_key",
        "away_key", "native", "y",
    }
    identity_fields = (
        "ordinal", "match_id", "season", "block", "cutoff", "home_key",
        "away_key",
    )
    for ordinal, (shard, block) in enumerate(zip(shards, blocks, strict=True)):
        if not isinstance(shard, Mapping):
            raise shots.LockMismatch("native shard is not a mapping")
        _keys(shard, outer_fields, label="native block")
        if (shard["schema"] != _NATIVE_BLOCK_SCHEMA
                or shard["native_intent_sha256"] != native_intent_sha256
                or shard["block_identity_sha256"]
                    != _native_block_identity_sha256(
                        native_intent_sha256, ordinal, block,
                    )
                or shard["harness_commit"] != h.commit
                or shard["harness_manifest_sha256"] != h.manifest_sha256
                or shard["parent_commit"] != _NATIVE_PARENT_COMMIT
                or shard["parent_tree"] != _NATIVE_PARENT_TREE
                or shard["training_schedule_sha256"] != training_sha256
                or type(shard["block_ordinal"]) is not int
                or shard["block_ordinal"] != ordinal
                or shard["block"] != block[0]["block"]
                or shard["cutoff"] != block[0]["cutoff"]):
            raise shots.LockMismatch("native shard binding differs")
        rows = shard["rows"]
        if not isinstance(rows, list) or len(rows) != len(block):
            raise shots.FixtureSetMismatch("native shard row count differs")
        for row, expected in zip(rows, block, strict=True):
            if (not isinstance(row, Mapping) or set(row) != row_fields
                    or any(row[name] != expected[name]
                           for name in identity_fields)):
                raise shots.FixtureSetMismatch("native shard row identity differs")
            native_rows.append(_probability_vector(
                row["native"], label="stored training native",
                strictly_positive=True, stored_native=True,
            ))
            if type(row["y"]) is not int or row["y"] not in (0, 1, 2):
                raise shots.FitFailure("native shard outcome code is invalid")
            outcomes.append(row["y"])
        if not isinstance(shard["receipt"], Mapping):
            raise shots.LockMismatch("native block receipt is not a mapping")

    # On the real schedule, reuse the complete generator-receipt verifier.  The
    # small-schedule branch above exists only for synthetic artifact tests.
    if len(schedule) == shots.TRAINING_ROWS and len(blocks) == 142:
        first_receipt = shards[0]["receipt"]
        raw_inputs = first_receipt.get("exposed_raw_files")
        if not isinstance(raw_inputs, list) or len(raw_inputs) != 5:
            raise shots.LockMismatch("native receipt lacks five raw inputs")
        expected_digests = _native_raw_digests()
        for record, name in zip(raw_inputs, _NATIVE_RAW_NAMES, strict=True):
            if (not isinstance(record, Mapping)
                    or set(record) != {"path", "sha256", "bytes"}
                    or record["path"] != f"data/epl/raw/{name}"
                    or record["sha256"] != expected_digests[name]
                    or type(record["bytes"]) is not int or record["bytes"] <= 0):
                raise shots.LockMismatch("native receipt raw identity differs")
        for ordinal, shard in enumerate(shards):
            _validate_native_block(
                shard, native_intent_sha256=native_intent_sha256, h=h,
                training_sha256=training_sha256, raw_inputs=raw_inputs,
                expected_ordinal=ordinal, blocks=blocks,
            )
    return np.asarray(native_rows, dtype=np.float64), np.asarray(outcomes, dtype=int)


def _k2_components(
    records: Mapping[str, Any], values: Mapping[str, Any],
) -> tuple[
    Mapping[str, Any], Mapping[str, Any], Sequence[Mapping[str, Any]],
    Sequence[Mapping[str, Any]], Mapping[str, Any], Mapping[str, Any],
    Mapping[str, Any], Mapping[str, Any],
]:
    four = {"training_predictions", "feature_moments", "coefficients", "optimizer"}
    if (not isinstance(records, Mapping) or set(records) != four
            or not isinstance(values, Mapping) or set(values) != four):
        raise shots.LockMismatch("K2 must contain exactly four artifact groups")
    training_records, training_values = (
        records["training_predictions"], values["training_predictions"])
    optimizer_records, optimizer_values = records["optimizer"], values["optimizer"]
    if (not isinstance(training_records, Mapping)
            or set(training_records) != {
                "index", "native_intent", "native_blocks", "native_completions",
            }
            or not isinstance(training_values, Mapping)
            or set(training_values) != {
                "index", "native_intent", "native_blocks", "native_completions",
            }
            or not isinstance(training_records["native_blocks"], list)
            or not isinstance(training_values["native_blocks"], list)
            or not isinstance(training_records["native_completions"], list)
            or not isinstance(training_values["native_completions"], list)
            or not isinstance(optimizer_records, Mapping)
            or set(optimizer_records) != {"intent", "receipt"}
            or not isinstance(optimizer_values, Mapping)
            or set(optimizer_values) != {"intent", "receipt"}):
        raise shots.LockMismatch("K2 grouped artifact schema differs")
    return (
        training_values["index"], training_values["native_intent"],
        training_values["native_blocks"], training_values["native_completions"],
        values["feature_moments"], values["coefficients"],
        optimizer_values["intent"], optimizer_values["receipt"],
    )


def _validate_k2_record_values(
    *, records: Mapping[str, Any], values: Mapping[str, Any],
) -> None:
    (training, native_intent, shards, completions, moments, coefficients,
     intent, receipt) = _k2_components(records, values)
    train_records = records["training_predictions"]
    optimizer_records = records["optimizer"]
    if len(train_records["native_blocks"]) != len(shards):
        raise shots.LockMismatch("native shard record/value counts differ")
    pairs: list[tuple[str, Mapping[str, Any], Mapping[str, Any], int | None]] = [
        ("training_predictions", train_records["index"], training, None),
        ("native_intent", train_records["native_intent"], native_intent, None),
        ("feature_moments", records["feature_moments"], moments, None),
        ("coefficients", records["coefficients"], coefficients, None),
        ("optimizer_intent", optimizer_records["intent"], intent, None),
        ("optimizer_receipt", optimizer_records["receipt"], receipt, None),
    ]
    for ordinal, (record, value) in enumerate(zip(
        train_records["native_blocks"], shards, strict=True,
    )):
        pairs.append(("native_block", record, value, ordinal))
    if len(train_records["native_completions"]) != len(completions):
        raise shots.LockMismatch("native completion record/value counts differ")
    for slot, (record, value) in enumerate(zip(
        train_records["native_completions"], completions, strict=True,
    )):
        pairs.append(("native_completion", record, value, slot))
    paths_seen: set[str] = set()
    for logical, record, value, ordinal in pairs:
        _record_binds_value(logical, record, value, ordinal=ordinal)
        path = str(record["path"])
        if path in paths_seen:
            raise shots.LockMismatch("K2 artifact paths are not distinct")
        paths_seen.add(path)


def _validate_native_intent_for_k(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    training_sha256: str, native_intent: Mapping[str, Any],
) -> tuple[str, Mapping[str, Any]]:
    if not isinstance(native_intent, Mapping):
        raise shots.LockMismatch("native intent artifact is not a mapping")
    _keys(native_intent, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "parent_commit", "parent_tree", "training_schedule_sha256",
        "raw_inputs", "schedule", "sandbox_contract_sha256",
    }, label="native intent artifact")
    try:
        contract = _native_sandbox_contract(
            frozen_runtime_lock=h.native_runtime_lock,
        ) if h.native_runtime_lock is not None else _native_sandbox_contract()
    except NativeWorkerSandboxStop as exc:
        # K is outcome-bearing frozen state.  A malformed or incompatible
        # runtime contract while validating that state is a terminal identity
        # mismatch, not permission to retry the fit under another closure.
        raise shots.LockMismatch(
            f"native runtime contract differs while validating K: {exc}"
        ) from exc
    raw_inputs = native_intent["raw_inputs"]
    expected_digests = _native_raw_digests()
    if not isinstance(raw_inputs, list) or len(raw_inputs) != 5:
        raise shots.LockMismatch("native intent does not expose exactly five raw files")
    for record, name in zip(raw_inputs, _NATIVE_RAW_NAMES, strict=True):
        if (not isinstance(record, Mapping)
                or set(record) != {"path", "sha256", "bytes"}
                or record["path"] != f"data/epl/raw/{name}"
                or record["sha256"] != expected_digests[name]
                or type(record["bytes"]) is not int or record["bytes"] <= 0):
            raise shots.LockMismatch("native intent raw exposure differs")
    if (native_intent["schema"] != _NATIVE_INTENT_SCHEMA
            or native_intent["harness_commit"] != h.commit
            or native_intent["harness_manifest_sha256"] != h.manifest_sha256
            or native_intent["parent_commit"] != _NATIVE_PARENT_COMMIT
            or native_intent["parent_tree"] != _NATIVE_PARENT_TREE
            or native_intent["training_schedule_sha256"] != training_sha256
            or native_intent["schedule"] != [dict(row) for row in schedule]
            or native_intent["sandbox_contract_sha256"]
                != _native_sandbox_contract_sha256(contract)):
        raise shots.LockMismatch("native intent differs from H/schedule/sandbox")
    return hashlib.sha256(_canonical_bytes(native_intent)).hexdigest(), contract


def _validate_native_completion_coverage_for_k(
    *, native_intent: Mapping[str, Any], native_intent_sha256: str,
    sandbox_contract: Mapping[str, Any],
    blocks: Sequence[Sequence[Mapping[str, Any]]],
    shard_records: Sequence[Mapping[str, Any]],
    shards: Sequence[Mapping[str, Any]],
    completion_records: Sequence[Mapping[str, Any]],
    completions: Sequence[Mapping[str, Any]],
) -> None:
    if (not completions or len(completion_records) != len(completions)
            or len(shard_records) != len(shards)):
        raise shots.LockMismatch("native completion coverage inputs differ")
    expected_by_ordinal = {
        ordinal: dict(record) for ordinal, record in enumerate(shard_records)
    }
    covered: set[int] = set()
    for slot, (record, completion) in enumerate(zip(
        completion_records, completions, strict=True,
    )):
        _validate_k2_record_metadata("native_completion", record, ordinal=slot)
        referenced = _validate_native_completion_receipt(
            completion, native_intent=native_intent,
            native_intent_sha256=native_intent_sha256,
            block_count=len(blocks), sandbox_contract=sandbox_contract,
        )
        output_bytes = 0
        for ordinal, block_record in zip(
            completion["job_ordinals"], referenced, strict=True,
        ):
            if ordinal in covered:
                raise shots.LockMismatch("native completion coverage overlaps")
            if block_record != expected_by_ordinal.get(ordinal):
                raise shots.LockMismatch(
                    "native completion references a non-K block record"
                )
            output_bytes += len(_canonical_bytes(shards[ordinal]))
            covered.add(ordinal)
        if completion["stream"]["output_bytes"] != output_bytes:
            raise shots.LockMismatch(
                "native completion output-byte count does not recompute"
            )
    if covered != set(range(len(blocks))):
        raise shots.LockMismatch("native clean-exit receipts do not cover every K block")


def _independent_tilt_recompute(
    native: np.ndarray, z: np.ndarray, beta: np.ndarray, outcomes: np.ndarray,
) -> tuple[np.ndarray, float, np.ndarray]:
    """Literal prereg equations, independent of the production tilt helpers."""
    if (native.ndim != 2 or native.shape[1] != 3
            or z.shape != (len(native), 4) or beta.shape != (8,)
            or outcomes.shape != (len(native),)):
        raise shots.FitFailure("independent tilt inputs have the wrong shape")
    native_model = native / native.sum(axis=1, keepdims=True)
    if (not np.isfinite(native_model).all()
            or np.any(native_model <= 0.0)
            or np.any(np.abs(native_model.sum(axis=1) - 1.0)
                      > shots.MODEL_PROBABILITY_SUM_TOLERANCE)):
        raise shots.ProbabilityInvalid(
            "independent native model normalization is invalid"
        )
    matrix = beta.reshape(2, 4)
    eta_home = np.log(native_model[:, 0] / native_model[:, 2]) + z @ matrix[0]
    eta_draw = np.log(native_model[:, 1] / native_model[:, 2]) + z @ matrix[1]
    logits = np.column_stack((eta_home, eta_draw, np.zeros(len(native))))
    logits = logits - logits.max(axis=1, keepdims=True)
    exponentiated = np.exp(logits)
    candidate = exponentiated / exponentiated.sum(axis=1, keepdims=True)
    objective = -float(np.log(candidate[np.arange(len(native)), outcomes]).sum())
    objective += 0.5 * float(np.square(matrix).sum())
    target_home = (outcomes == 0).astype(np.float64)
    target_draw = (outcomes == 1).astype(np.float64)
    gradient = np.vstack((
        (candidate[:, 0] - target_home) @ z,
        (candidate[:, 1] - target_draw) @ z,
    )) + matrix
    if (not np.isfinite(candidate).all() or not math.isfinite(objective)
            or not np.isfinite(gradient).all()):
        raise shots.FitFailure("independent tilt recomputation is nonfinite")
    return candidate, objective, gradient.reshape(8)


def _validate_k2_semantics(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    records: Mapping[str, Any], values: Mapping[str, Any],
    _test_only_training_reference: _K2TrainingReference | None = None,
) -> None:
    """Independently recompute every quantity that gives K its meaning."""
    blocks = _schedule_blocks_exact(schedule)
    schedule_sha256 = _digest_rows(_K2_SCHEDULE_SCHEMA, schedule)
    if schedule_sha256 != h.training_schedule_sha256:
        raise shots.FixtureSetMismatch("K2 schedule differs from live H")
    (training, native_intent, shards, completions, moments, coefficients,
     intent, receipt) = _k2_components(records, values)
    shard_records = records["training_predictions"]["native_blocks"]
    block_set_sha256 = _native_block_set_sha256(shard_records)
    native_intent_sha256, sandbox_contract = _validate_native_intent_for_k(
        h=h, schedule=schedule, training_sha256=schedule_sha256,
        native_intent=native_intent,
    )
    if records["training_predictions"]["native_intent"]["sha256"] \
            != native_intent_sha256:
        raise shots.LockMismatch("native intent record digest differs")
    native, outcomes = _validate_native_shards_for_k(
        h=h, schedule=schedule, training_sha256=schedule_sha256,
        native_intent_sha256=native_intent_sha256, shards=shards,
    )
    _validate_native_completion_coverage_for_k(
        native_intent=native_intent,
        native_intent_sha256=native_intent_sha256,
        sandbox_contract=sandbox_contract, blocks=blocks,
        shard_records=shard_records, shards=shards,
        completion_records=records["training_predictions"]["native_completions"],
        completions=completions,
    )
    training_reference = _k2_training_reference(
        schedule,
        _test_only_reference=_test_only_training_reference,
    )
    if tuple(int(value) for value in outcomes) != training_reference.outcomes:
        raise shots.LockMismatch(
            "K2 training outcomes differ from the pinned matches archive"
        )

    if not isinstance(moments, Mapping):
        raise shots.LockMismatch("feature moments artifact is not a mapping")
    _keys(moments, {
        "schema", "training_schedule_sha256", "native_block_set_sha256",
        "names", "means", "population_standard_deviations", "ddof",
        "n_training", "seasons",
    }, label="K2 feature moments")
    means = np.asarray(_finite_vector(moments["means"], 4, label="means"))
    standard_deviations = np.asarray(_finite_vector(
        moments["population_standard_deviations"], 4,
        label="population standard deviations",
    ))
    schedule_seasons = list(dict.fromkeys(str(row["season"]) for row in schedule))
    if (moments["schema"] != _k2_schemas()["feature_moments"]
            or moments["training_schedule_sha256"] != schedule_sha256
            or moments["native_block_set_sha256"] != block_set_sha256
            or moments["names"] != list(shots.FEATURE_NAMES)
            or moments["ddof"] != 0 or moments["n_training"] != len(schedule)
            or moments["seasons"] != schedule_seasons
            or np.any(standard_deviations <= 0.0)):
        raise shots.LockMismatch("K2 feature moment identity differs")

    if not isinstance(coefficients, Mapping):
        raise shots.LockMismatch("coefficients artifact is not a mapping")
    _keys(coefficients, {
        "schema", "training_schedule_sha256", "native_block_set_sha256",
        "feature_moments_sha256", "optimizer_receipt_sha256",
        "feature_names", "reference_outcome", "coefficient_order",
        "beta_H", "beta_D",
    }, label="K2 coefficients")
    beta_h = _finite_vector(coefficients["beta_H"], 4, label="beta_H")
    beta_d = _finite_vector(coefficients["beta_D"], 4, label="beta_D")
    beta = np.asarray((*beta_h, *beta_d), dtype=np.float64)
    if (coefficients["schema"] != _k2_schemas()["coefficients"]
            or coefficients["training_schedule_sha256"] != schedule_sha256
            or coefficients["native_block_set_sha256"] != block_set_sha256
            or coefficients["feature_moments_sha256"]
                != records["feature_moments"]["sha256"]
            or coefficients["optimizer_receipt_sha256"]
                != records["optimizer"]["receipt"]["sha256"]
            or coefficients["feature_names"] != list(shots.FEATURE_NAMES)
            or coefficients["reference_outcome"] != "away"
            or coefficients["coefficient_order"] != list(_K2_COEFFICIENT_ORDER)):
        raise shots.LockMismatch("K2 coefficient identity differs")

    if not isinstance(training, Mapping):
        raise shots.LockMismatch("training prediction artifact is not a mapping")
    _keys(training, {
        "schema", "training_schedule_sha256", "native_block_set_sha256",
        "feature_moments_sha256", "coefficients_sha256",
        "optimizer_receipt_sha256", "n_rows", "rows",
    }, label="K2 training predictions")
    if (training["schema"] != _k2_schemas()["training_predictions"]
            or training["training_schedule_sha256"] != schedule_sha256
            or training["native_block_set_sha256"] != block_set_sha256
            or training["feature_moments_sha256"]
                != records["feature_moments"]["sha256"]
            or training["coefficients_sha256"]
                != records["coefficients"]["sha256"]
            or training["optimizer_receipt_sha256"]
                != records["optimizer"]["receipt"]["sha256"]
            or training["n_rows"] != len(schedule)
            or not isinstance(training["rows"], list)
            or len(training["rows"]) != len(schedule)):
        raise shots.LockMismatch("K2 training prediction binding differs")

    row_fields = set(_K2_SCHEDULE_FIELDS) | {
        "shot_expectations", "features", "standardized_features", "native",
        "candidate", "y",
    }
    expectation_names = ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
    x_rows: list[tuple[float, float, float, float]] = []
    z_rows: list[tuple[float, float, float, float]] = []
    candidate_rows: list[tuple[float, float, float]] = []
    for ordinal, (row, expected) in enumerate(zip(
        training["rows"], schedule, strict=True,
    )):
        if (not isinstance(row, Mapping) or set(row) != row_fields
                or any(row[name] != expected[name] for name in _K2_SCHEDULE_FIELDS)):
            raise shots.FixtureSetMismatch(
                "K2 training row differs from the full ordered schedule"
            )
        expectations = row["shot_expectations"]
        features = row["features"]
        standardized = row["standardized_features"]
        if (not isinstance(expectations, Mapping)
                or set(expectations) != set(expectation_names)
                or not isinstance(features, Mapping)
                or set(features) != set(shots.FEATURE_NAMES)
                or not isinstance(standardized, Mapping)
                or set(standardized) != set(shots.FEATURE_NAMES)):
            raise shots.LockMismatch("K2 feature row schema differs")
        expectation = _finite_vector(
            [expectations[name] for name in expectation_names], 4,
            label="shot expectations",
        )
        if any(item <= 0.0 for item in expectation):
            raise shots.FitFailure("shot expectation is not positive")
        if expectation != training_reference.shot_expectations[ordinal]:
            raise shots.FitFailure(
                "stored shot expectations differ from the pinned shot reference"
            )
        hs, ass, hst, ast = expectation
        recomputed_x = (
            hst - ast, (hs - hst) - (ass - ast),
            hst + ast, (hs - hst) + (ass - ast),
        )
        stored_x = _finite_vector(
            [features[name] for name in shots.FEATURE_NAMES], 4,
            label="shot features",
        )
        if not np.allclose(stored_x, recomputed_x, rtol=1e-13, atol=1e-13):
            raise shots.FitFailure("stored shot feature algebra differs")
        if stored_x != training_reference.features[ordinal]:
            raise shots.FitFailure(
                "stored shot features differ from the pinned shot reference"
            )
        stored_z = _finite_vector(
            [standardized[name] for name in shots.FEATURE_NAMES], 4,
            label="standardized shot features",
        )
        if tuple(float(item) for item in row["native"]) != tuple(native[ordinal]):
            raise shots.LockMismatch("aggregate native differs from its shard")
        _probability_vector(
            row["native"], label="aggregate stored native",
            strictly_positive=True, stored_native=True,
        )
        candidate = _probability_vector(
            row["candidate"], label="training candidate",
            strictly_positive=False,
        )
        if type(row["y"]) is not int or row["y"] != int(outcomes[ordinal]):
            raise shots.LockMismatch("aggregate outcome differs from its shard")
        x_rows.append(stored_x); z_rows.append(stored_z); candidate_rows.append(candidate)

    x = np.asarray(x_rows, dtype=np.float64)
    z = np.asarray(z_rows, dtype=np.float64)
    if (not np.allclose(x.mean(axis=0), means, rtol=1e-13, atol=1e-13)
            or not np.allclose(
                x.std(axis=0, ddof=0), standard_deviations,
                rtol=1e-13, atol=1e-13,
            )):
        raise shots.FitFailure("stored population moments do not recompute")
    expected_z = (x - means) / standard_deviations
    if not np.allclose(z, expected_z, rtol=1e-13, atol=1e-13):
        raise shots.FitFailure("stored standardized features do not recompute")

    _validate_optimizer_intent(intent)
    outcome_sha256 = _training_outcome_sha256(
        schedule, [int(item) for item in outcomes],
    )
    if (intent["harness_commit"] != h.commit
            or intent["harness_manifest_sha256"] != h.manifest_sha256
            or intent["training_schedule_sha256"] != schedule_sha256
            or intent["native_block_set_sha256"] != block_set_sha256
            or intent["feature_moments_sha256"]
                != records["feature_moments"]["sha256"]
            or intent["training_outcomes_sha256"] != outcome_sha256):
        raise shots.LockMismatch("optimizer intent does not bind the K2 inputs")
    _validate_optimizer_receipt(
        receipt, intent_record=records["optimizer"]["intent"], intent=intent,
    )
    if (receipt["success"] is not True
            or receipt["objective_consistent"] is not True
            or receipt["gradient_consistent"] is not True
            or receipt["gradient_certified"] is not True):
        raise shots.FitFailure(
            "optimizer did not satisfy success, recomputation agreement, and "
            "independent-gradient acceptance"
        )
    if not np.array_equal(np.asarray(receipt["beta"], dtype=np.float64), beta):
        raise shots.LockMismatch("coefficient artifact differs from optimizer beta")

    recomputed_candidate, objective, gradient = _independent_tilt_recompute(
        native, z, beta, outcomes,
    )
    if not np.allclose(
        np.asarray(candidate_rows), recomputed_candidate,
        rtol=5e-13, atol=5e-15,
    ):
        raise shots.FitFailure("training candidate probabilities do not recompute")
    if not math.isclose(
        float(receipt["objective_value"]), objective,
        rel_tol=1e-13, abs_tol=1e-10,
    ):
        raise shots.FitFailure("optimizer objective does not recompute")
    if not math.isclose(
        float(receipt["independent_objective_value"]), objective,
        rel_tol=1e-13, abs_tol=1e-10,
    ):
        raise shots.FitFailure(
            "optimizer independent objective does not recompute"
        )
    stored_gradient = np.asarray(receipt["gradient"], dtype=np.float64)
    if not np.allclose(stored_gradient, gradient, rtol=1e-11, atol=1e-10):
        raise shots.FitFailure("optimizer final gradient does not recompute")
    stored_independent_gradient = np.asarray(
        receipt["independent_gradient"], dtype=np.float64,
    )
    if not np.allclose(
        stored_independent_gradient, gradient, rtol=1e-11, atol=1e-10,
    ):
        raise shots.FitFailure(
            "optimizer independent final gradient does not recompute"
        )
    if not math.isclose(
        float(receipt["gradient_max_abs"]), float(np.max(np.abs(gradient))),
        rel_tol=1e-11, abs_tol=1e-10,
    ):
        raise shots.FitFailure("optimizer gradient norm does not recompute")
    if not math.isclose(
        float(receipt["independent_gradient_max_abs"]),
        float(np.max(np.abs(gradient))), rel_tol=1e-11, abs_tol=1e-10,
    ):
        raise shots.FitFailure(
            "optimizer independent gradient norm does not recompute"
        )
    if (receipt["gradient_acceptance_threshold"]
            != shots.OPTIMIZER_GRADIENT_TOLERANCE
            or receipt["beta_distance_acceptance_ceiling_l2"]
                != shots.OPTIMIZER_BETA_DISTANCE_BOUND_L2
            or not math.isclose(
                float(receipt["beta_distance_actual_bound_l2"]),
                float(np.linalg.norm(gradient, ord=2)),
                rel_tol=1e-11, abs_tol=1e-10,
            )
            or float(np.max(np.abs(gradient)))
                > shots.OPTIMIZER_GRADIENT_TOLERANCE):
        raise shots.FitFailure(
            "optimizer result is not independently gradient-certified"
        )
    del blocks


def _build_k2_manifest(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    records: Mapping[str, Any], values: Mapping[str, Any],
    _test_only_training_reference: _K2TrainingReference | None = None,
) -> dict[str, Any]:
    """Construct, but do not write, the exact four-group K2 manifest."""
    _validate_k2_record_values(records=records, values=values)
    _validate_k2_semantics(
        h=h, schedule=schedule, records=records, values=values,
        _test_only_training_reference=_test_only_training_reference,
    )
    (training, native_intent, shards, completions, moments, coefficients,
     _, receipt) = _k2_components(records, values)
    del training, native_intent, shards, completions
    block_records = records["training_predictions"]["native_blocks"]
    return {
        "schema": _K2_MANIFEST_SCHEMA,
        "coefficient_frozen": True,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "training_rows": len(schedule),
        "training_blocks": len(_schedule_blocks_exact(schedule)),
        "training_schedule_sha256": h.training_schedule_sha256,
        "native_block_set_sha256": _native_block_set_sha256(block_records),
        "artifacts": json.loads(json.dumps(records)),
        "feature_moments": {
            key: value for key, value in moments.items() if key != "schema"
        },
        "coefficients": {
            key: value for key, value in coefficients.items() if key != "schema"
        },
        "optimizer_receipt": {
            key: value for key, value in receipt.items() if key != "schema"
        },
        "objective": float(receipt["objective_value"]),
        "final_gradient": list(receipt["gradient"]),
    }


def _k2_record_layout(
    records: Mapping[str, Any], *, expected_blocks: int,
) -> tuple[tuple[str, Mapping[str, Any], int | None], ...]:
    if not isinstance(records, Mapping) or set(records) != {
        "training_predictions", "feature_moments", "coefficients", "optimizer",
    }:
        raise shots.LockMismatch("K2 must contain exactly four artifact groups")
    training = records["training_predictions"]
    optimizer = records["optimizer"]
    if (not isinstance(training, Mapping)
            or set(training) != {
                "index", "native_intent", "native_blocks", "native_completions",
            }
            or not isinstance(training["native_blocks"], list)
            or len(training["native_blocks"]) != expected_blocks
            or not isinstance(training["native_completions"], list)
            or not training["native_completions"]
            or not isinstance(optimizer, Mapping)
            or set(optimizer) != {"intent", "receipt"}):
        raise shots.LockMismatch("K2 artifact group layout differs")
    layout: list[tuple[str, Mapping[str, Any], int | None]] = [
        ("training_predictions", training["index"], None),
        ("native_intent", training["native_intent"], None),
        ("feature_moments", records["feature_moments"], None),
        ("coefficients", records["coefficients"], None),
        ("optimizer_intent", optimizer["intent"], None),
        ("optimizer_receipt", optimizer["receipt"], None),
    ]
    layout.extend(
        ("native_block", record, ordinal)
        for ordinal, record in enumerate(training["native_blocks"])
    )
    layout.extend(
        ("native_completion", record, slot)
        for slot, record in enumerate(training["native_completions"])
    )
    paths_seen: set[str] = set()
    hashes_seen: set[str] = set()
    for logical, record, ordinal in layout:
        digest, _, relative = _validate_k2_record_metadata(
            logical, record, ordinal=ordinal,
        )
        if relative in paths_seen or digest in hashes_seen:
            raise shots.LockMismatch("K2 artifacts must use distinct paths and hashes")
        paths_seen.add(relative); hashes_seen.add(digest)
    return tuple(layout)


def _load_committed_k2_artifact(
    logical: str, record: Mapping[str, Any], *, ordinal: int | None,
    k_commit: str,
) -> dict[str, Any]:
    value, raw = _load_content_addressed_json(
        logical, record, artifact_root=_ARTIFACT_ROOT, ordinal=ordinal,
    )
    if _git_bytes("show", f"{k_commit}:{record['path']}") != raw:
        raise shots.LockMismatch(f"{logical} working bytes differ from committed K")
    return value


def verify_coefficient_freeze_live(h_commit: str, k_commit: str) -> _VerifiedK:
    h, k = verify_harness_live(h_commit), _commit(k_commit, label="K")
    if _git_text("rev-list", "--parents", "-n", "1", k).split() != [k, h.commit]:
        raise shots.LockMismatch("K must be a single-parent direct child of H")
    manifest, raw = _read_canonical(_K_PATH, label="K manifest")
    if _git_bytes("show", f"{k}:{shots.K_MANIFEST_PATH}") != raw:
        raise shots.LockMismatch("working-tree K manifest differs from committed K")
    if not _git_succeeds("merge-base", "--is-ancestor", k, "HEAD"):
        raise shots.LockMismatch("K is not an ancestor of HEAD")
    _keys(manifest, {
        "schema", "coefficient_frozen", "harness_commit",
        "harness_manifest_sha256", "training_rows", "training_blocks",
        "training_schedule_sha256", "native_block_set_sha256", "artifacts",
        "feature_moments", "coefficients", "optimizer_receipt", "objective",
        "final_gradient",
    }, label="K2 manifest")
    if (manifest["schema"] != _K2_MANIFEST_SCHEMA
            or manifest["coefficient_frozen"] is not True
            or manifest["harness_commit"] != h.commit
            or manifest["harness_manifest_sha256"] != h.manifest_sha256
            or manifest["training_rows"] != shots.TRAINING_ROWS
            or manifest["training_blocks"] != 142
            or manifest["training_schedule_sha256"] != h.training_schedule_sha256
            or not isinstance(manifest["native_block_set_sha256"], str)
            or not _HEX64.fullmatch(manifest["native_block_set_sha256"])):
        raise shots.LockMismatch("K does not bind the exact live H")
    records = manifest["artifacts"]
    layout = _k2_record_layout(records, expected_blocks=142)
    artifact_paths = [str(record["path"]) for _, record, _ in layout]
    changed = set(_git_text(
        "diff-tree", "--no-commit-id", "--name-only", "-r", k,
    ).splitlines())
    expected = (set(artifact_paths) | {shots.K_MANIFEST_PATH})
    if changed != expected:
        raise shots.LockMismatch("K changed paths differ from its exact artifact set")
    added = set(_git_text(
        "diff-tree", "--no-commit-id", "--name-only", "--diff-filter=A",
        "-r", k,
    ).splitlines())
    if added != expected:
        raise shots.LockMismatch(
            "K must add its manifest and every artifact to an artifact-free H"
        )
    _require_git_regular_blobs(k, tuple(expected), label="K")

    # Only now may K's training-outcome-bearing artifacts be opened.
    loaded: dict[tuple[str, int | None], dict[str, Any]] = {}
    for logical, record, ordinal in layout:
        loaded[(logical, ordinal)] = _load_committed_k2_artifact(
            logical, record, ordinal=ordinal, k_commit=k,
        )
    values = {
        "training_predictions": {
            "index": loaded[("training_predictions", None)],
            "native_intent": loaded[("native_intent", None)],
            "native_blocks": [
                loaded[("native_block", ordinal)] for ordinal in range(142)
            ],
            "native_completions": [
                loaded[("native_completion", slot)]
                for slot in range(len(
                    records["training_predictions"]["native_completions"]
                ))
            ],
        },
        "feature_moments": loaded[("feature_moments", None)],
        "coefficients": loaded[("coefficients", None)],
        "optimizer": {
            "intent": loaded[("optimizer_intent", None)],
            "receipt": loaded[("optimizer_receipt", None)],
        },
    }
    training_sha256, schedule = _training_binding()
    if training_sha256 != h.training_schedule_sha256:
        raise shots.LockMismatch("live training schedule changed while verifying K")
    expected_manifest = _build_k2_manifest(
        h=h, schedule=schedule, records=records, values=values,
    )
    if _canonical_bytes(manifest) != _canonical_bytes(expected_manifest):
        raise shots.LockMismatch("K2 manifest differs from semantic recomputation")
    verified = _VerifiedK(k, hashlib.sha256(raw).hexdigest(), h)

    # End-of-verifier closure: no authority assembled from an early H/K graph,
    # manifest, or artifact snapshot may escape after any of them drifts.  This
    # second binding deliberately reopens every committed K artifact but does
    # not reopen any post-K decision corpus.
    live_h = verify_harness_live(h.commit)
    if live_h != h:
        raise shots.LockMismatch("live H changed while closing K verification")
    end_k = _commit(k, label="K")
    end_manifest, end_raw = _read_canonical(_K_PATH, label="K manifest")
    if (end_k != k or end_raw != raw
            or _canonical_bytes(end_manifest) != _canonical_bytes(manifest)
            or _git_bytes("show", f"{k}:{shots.K_MANIFEST_PATH}") != end_raw
            or _git_text("rev-list", "--parents", "-n", "1", k).split()
                != [k, h.commit]
            or not _git_succeeds("merge-base", "--is-ancestor", k, "HEAD")):
        raise shots.LockMismatch("live K changed while closing verification")
    end_changed = set(_git_text(
        "diff-tree", "--no-commit-id", "--name-only", "-r", k,
    ).splitlines())
    end_added = set(_git_text(
        "diff-tree", "--no-commit-id", "--name-only", "--diff-filter=A",
        "-r", k,
    ).splitlines())
    if end_changed != expected or end_added != expected:
        raise shots.LockMismatch("K path closure changed during verification")
    _require_git_regular_blobs(k, tuple(expected), label="K")
    for logical, record, ordinal in layout:
        rebound = _load_committed_k2_artifact(
            logical, record, ordinal=ordinal, k_commit=k,
        )
        if _canonical_bytes(rebound) != _canonical_bytes(
            loaded[(logical, ordinal)]
        ):
            raise shots.LockMismatch(
                f"{logical} changed while closing K verification"
            )
    final_manifest, final_raw = _read_canonical(_K_PATH, label="K manifest")
    if (final_raw != raw
            or _canonical_bytes(final_manifest) != _canonical_bytes(manifest)):
        raise shots.LockMismatch("K manifest changed after artifact rebind")
    _verify_harness_identity_live(h)
    return verified


def _write_fixed_canonical_once(
    path: Path, value: Mapping[str, Any], *, label: str,
) -> tuple[str, int]:
    """Create one fixed-path canonical manifest without replacement."""
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        absolute.relative_to(_ROOT)
    except ValueError as exc:
        raise shots.LockMismatch(f"{label} path escapes the repository") from exc
    raw = _canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    with _open_decision_state_directory(
        absolute.parent, create=True,
    ) as (_, directory_fd):
        assert directory_fd is not None
        try:
            with _write_decision_state_lease_at(
                directory_fd, absolute.name, raw,
            ):
                pass
        except FileExistsError:
            with _durably_bind_decision_entry_at(
                directory_fd, absolute.name, expected=raw, label=label,
                name_preobserved=True,
            ):
                pass
    return digest, len(raw)


def _load_k2_values_from_records(
    records: Mapping[str, Any], *, artifact_root: Path, expected_blocks: int,
) -> dict[str, Any]:
    """Load a complete uncommitted K draft through its content addresses."""
    layout = _k2_record_layout(records, expected_blocks=expected_blocks)
    loaded: dict[tuple[str, int | None], dict[str, Any]] = {}
    for logical, record, ordinal in layout:
        value, _ = _load_content_addressed_json(
            logical, record, artifact_root=artifact_root, ordinal=ordinal,
        )
        loaded[(logical, ordinal)] = value
    completions = records["training_predictions"]["native_completions"]
    return {
        "training_predictions": {
            "index": loaded[("training_predictions", None)],
            "native_intent": loaded[("native_intent", None)],
            "native_blocks": [
                loaded[("native_block", ordinal)]
                for ordinal in range(expected_blocks)
            ],
            "native_completions": [
                loaded[("native_completion", slot)]
                for slot in range(len(completions))
            ],
        },
        "feature_moments": loaded[("feature_moments", None)],
        "coefficients": loaded[("coefficients", None)],
        "optimizer": {
            "intent": loaded[("optimizer_intent", None)],
            "receipt": loaded[("optimizer_receipt", None)],
        },
    }


def _resume_complete_k_draft(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    artifact_root: Path,
    _test_only_training_reference: _K2TrainingReference | None,
) -> dict[str, Any] | None:
    """Validate and return an existing fixed K draft before any native work."""
    if not os.path.lexists(_K_PATH):
        return None
    raw = _read_regular_snapshot(_K_PATH, label="K draft manifest")
    try:
        manifest = json.loads(raw.decode("ascii"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise shots.LockMismatch(
            f"K draft manifest is not canonical ASCII JSON: {exc}"
        ) from exc
    if not isinstance(manifest, dict) or _canonical_bytes(manifest) != raw:
        raise shots.LockMismatch("K draft manifest is not one canonical object")
    expected_rows = len(schedule)
    expected_blocks = len(_schedule_blocks_exact(schedule))
    if (_test_only_training_reference is None
            and (expected_rows != shots.TRAINING_ROWS
                 or expected_blocks != 142)):
        raise shots.LockMismatch("production K draft schedule shape differs")
    _keys(manifest, {
        "schema", "coefficient_frozen", "harness_commit",
        "harness_manifest_sha256", "training_rows", "training_blocks",
        "training_schedule_sha256", "native_block_set_sha256", "artifacts",
        "feature_moments", "coefficients", "optimizer_receipt", "objective",
        "final_gradient",
    }, label="K draft manifest")
    if (manifest["schema"] != _K2_MANIFEST_SCHEMA
            or manifest["coefficient_frozen"] is not True
            or manifest["harness_commit"] != h.commit
            or manifest["harness_manifest_sha256"] != h.manifest_sha256
            or manifest["training_rows"] != expected_rows
            or manifest["training_blocks"] != expected_blocks
            or manifest["training_schedule_sha256"]
                != h.training_schedule_sha256):
        raise shots.LockMismatch("existing K draft belongs to another run")
    records = manifest["artifacts"]
    values = _load_k2_values_from_records(
        records, artifact_root=artifact_root, expected_blocks=expected_blocks,
    )
    expected = _build_k2_manifest(
        h=h, schedule=schedule, records=records, values=values,
        _test_only_training_reference=_test_only_training_reference,
    )
    if _canonical_bytes(manifest) != _canonical_bytes(expected):
        raise shots.LockMismatch(
            "existing K draft differs from independent semantic recomputation"
        )
    _verify_harness_identity_live(h)
    return {
        "status": "K_DRAFT_ALREADY_COMPLETE_UNFROZEN",
        "harness_commit": h.commit,
        "coefficient_manifest_path": shots.K_MANIFEST_PATH,
        "coefficient_manifest_sha256": hashlib.sha256(raw).hexdigest(),
        "coefficient_manifest_bytes": len(raw),
        "training_rows": len(schedule),
        "training_blocks": len(_schedule_blocks_exact(schedule)),
        "k_frozen": False,
    }


def _load_native_training_bundle(
    *, h: _VerifiedH, schedule: Sequence[Mapping[str, Any]],
    shard_records: Sequence[Mapping[str, Any]],
    artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]]:
    """Load the complete clean native job closure after its coordinator exits."""
    intents = _optimizer_records("native_intent", artifact_root=artifact_root)
    completions = _optimizer_records(
        "native_completion", artifact_root=artifact_root,
    )
    if len(intents) != 1 or not completions:
        raise shots.LockMismatch(
            "native training closure lacks one intent and clean completions"
        )
    native_intent_record, native_intent = intents[0]
    shard_values = [
        _load_native_block_shard(record, artifact_root=artifact_root)
        for record in shard_records
    ]
    completion_records = [record for record, _ in completions]
    completion_values = [value for _, value in completions]
    records = {
        "native_intent": native_intent_record,
        "native_blocks": [dict(record) for record in shard_records],
        "native_completions": completion_records,
    }
    values = {
        "native_intent": native_intent,
        "native_blocks": shard_values,
        "native_completions": completion_values,
    }
    training_sha256 = _digest_rows(_K2_SCHEDULE_SCHEMA, schedule)
    native_intent_sha256, contract = _validate_native_intent_for_k(
        h=h, schedule=schedule, training_sha256=training_sha256,
        native_intent=native_intent,
    )
    if native_intent_record["sha256"] != native_intent_sha256:
        raise shots.LockMismatch("native intent record differs from its value")
    blocks = _schedule_blocks_exact(schedule)
    _validate_native_completion_coverage_for_k(
        native_intent=native_intent,
        native_intent_sha256=native_intent_sha256,
        sandbox_contract=contract, blocks=blocks,
        shard_records=shard_records, shards=shard_values,
        completion_records=completion_records,
        completions=completion_values,
    )
    return records, values


def _production_training_features(
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[pd.DataFrame, shots.FeatureScaler, np.ndarray, np.ndarray]:
    """Build the production feature matrix while retaining exact row order."""
    fixtures = pd.DataFrame([dict(row) for row in schedule])
    panel = shots.load_pinned_training_shot_panel()
    calculated = shots.shot_features(panel.frame, fixtures)
    expected_ids = tuple(str(row["match_id"]) for row in schedule)
    if tuple(calculated["match_id"].astype(str)) != expected_ids:
        raise shots.FixtureSetMismatch(
            "production training shot features changed schedule order"
        )
    calculated = calculated.copy()
    calculated["season"] = [str(row["season"]) for row in schedule]
    scaler = shots._fit_training_scaler(calculated)
    x = calculated[list(shots.FEATURE_NAMES)].to_numpy(dtype=np.float64)
    z = shots._standardize_features(calculated, scaler)
    return calculated, scaler, x, z


def _preflight_training_reference(
    *, schedule: Sequence[Mapping[str, Any]], outcomes: np.ndarray,
    calculated: pd.DataFrame, scaler: shots.FeatureScaler,
    x: np.ndarray, z: np.ndarray,
    _test_only_training_reference: _K2TrainingReference | None,
) -> _K2TrainingReference:
    """Independently reject wrong outcomes/features before fit authorization."""
    reference = _k2_training_reference(
        schedule, _test_only_reference=_test_only_training_reference,
    )
    expected_ids = tuple(str(row["match_id"]) for row in schedule)
    if (len(calculated) != len(schedule)
            or tuple(calculated["match_id"].astype(str)) != expected_ids
            or outcomes.shape != (len(schedule),)
            or tuple(int(value) for value in outcomes) != reference.outcomes):
        raise shots.LockMismatch(
            "pre-optimizer outcomes or feature-row identities differ from the "
            "independent pinned reference"
        )
    expectation_names = ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
    observed_expectations = tuple(tuple(
        float(calculated.iloc[ordinal][name]) for name in expectation_names
    ) for ordinal in range(len(schedule)))
    observed_features = tuple(tuple(
        float(x[ordinal, index]) for index in range(len(shots.FEATURE_NAMES))
    ) for ordinal in range(len(schedule)))
    if (x.shape != (len(schedule), 4)
            or z.shape != (len(schedule), 4)
            or observed_expectations != reference.shot_expectations
            or observed_features != reference.features):
        raise shots.FitFailure(
            "pre-optimizer production shot features differ from the "
            "independent pinned reference"
        )
    reference_x = np.asarray(reference.features, dtype=np.float64)
    expected_means = reference_x.mean(axis=0)
    expected_sd = reference_x.std(axis=0, ddof=0)
    if not np.isfinite(expected_sd).all() or np.any(expected_sd <= 0.0):
        raise shots.FitFailure(
            "independent pre-optimizer feature scale is invalid"
        )
    expected_z = (reference_x - expected_means) / expected_sd
    expected_seasons = tuple(dict.fromkeys(
        str(row["season"]) for row in schedule
    ))
    if (scaler.n_training != len(schedule)
            or scaler.seasons != expected_seasons
            or not np.allclose(
                np.asarray(scaler.means), expected_means,
                rtol=1e-13, atol=1e-13,
            )
            or not np.allclose(
                np.asarray(scaler.standard_deviations), expected_sd,
                rtol=1e-13, atol=1e-13,
            )
            or not np.allclose(z, expected_z, rtol=1e-13, atol=1e-13)):
        raise shots.FitFailure(
            "pre-optimizer scaler or standardized features differ from the "
            "independent pinned reference"
        )
    return reference


def _harness_optimizer_receipt(
    *, fit: shots.TiltFit, native_stored: np.ndarray, z: np.ndarray,
    outcomes: np.ndarray, attempt: _OptimizerAttempt,
) -> tuple[dict[str, Any], np.ndarray]:
    """Certify a SciPy result with the harness's separate literal equations."""
    beta = np.asarray(fit.beta, dtype=np.float64)
    candidate, objective, independent_gradient = _independent_tilt_recompute(
        native_stored, z, beta, outcomes,
    )
    receipt = _make_optimizer_receipt(
        intent_record=attempt.intent_record, intent=attempt.intent,
        success=fit.success, status=fit.status, beta=fit.beta,
        objective_value=fit.objective, gradient=fit.gradient,
        independent_objective_value=objective,
        independent_gradient=independent_gradient,
        iterations=fit.iterations,
        function_evaluations=fit.function_evaluations,
        gradient_evaluations=fit.gradient_evaluations,
        message=fit.message,
    )
    return receipt, candidate


def _run_training_after_h(
    *, h_commit: str, artifact_root: Path = _ARTIFACT_ROOT,
    _test_only_training_reference: _K2TrainingReference | None = None,
) -> dict[str, Any]:
    """Execute or resume the post-H training/K-draft subphase exactly once."""
    artifact_root = _fixed_repo_artifact_root(artifact_root)
    h = verify_harness_live(h_commit)
    terminal = _resume_pre_k_terminal(
        h=h, artifact_root=artifact_root,
    )
    if terminal is not None:
        return terminal
    _require_pre_k_decision_namespace(
        artifact_root=artifact_root, result_record=None,
    )
    _require_no_orphan_fixed_publication(terminal_present=False)
    training_sha256, schedule = _training_binding()
    if training_sha256 != h.training_schedule_sha256:
        raise shots.LockMismatch("live H training schedule differs")
    completed_draft = _resume_complete_k_draft(
        h=h, schedule=schedule, artifact_root=artifact_root,
        _test_only_training_reference=_test_only_training_reference,
    )
    if completed_draft is not None:
        return completed_draft
    shard_records = _run_native_training_blocks_after_h(
        h_commit=h.commit, artifact_root=artifact_root,
    )
    h = verify_harness_live(h.commit)
    native_records, native_values = _load_native_training_bundle(
        h=h, schedule=schedule, shard_records=shard_records,
        artifact_root=artifact_root,
    )
    native_stored, outcomes = _validate_native_shards_for_k(
        h=h, schedule=schedule, training_sha256=training_sha256,
        native_intent_sha256=native_records["native_intent"]["sha256"],
        shards=native_values["native_blocks"],
    )
    native_model = shots._native_model_probabilities(
        native_stored, label="assembled training native",
    )
    calculated, scaler, x, z = _production_training_features(schedule)
    _preflight_training_reference(
        schedule=schedule, outcomes=outcomes, calculated=calculated,
        scaler=scaler, x=x, z=z,
        _test_only_training_reference=_test_only_training_reference,
    )
    # The independent outcome/feature preflight may be expensive.  Re-run the
    # full live-H check after it and before any singleton optimizer claim.
    h = verify_harness_live(h.commit)
    if h.training_schedule_sha256 != training_sha256:
        raise shots.LockMismatch("live H changed after training preflight")
    block_set_sha256 = _native_block_set_sha256(shard_records)
    moments = {
        "schema": _k2_schemas()["feature_moments"],
        "training_schedule_sha256": training_sha256,
        "native_block_set_sha256": block_set_sha256,
        "names": list(shots.FEATURE_NAMES),
        "means": list(scaler.means),
        "population_standard_deviations": list(
            scaler.standard_deviations
        ),
        "ddof": 0, "n_training": scaler.n_training,
        "seasons": list(scaler.seasons),
    }
    moments_record = _write_content_addressed_json(
        "feature_moments", moments, artifact_root=artifact_root,
    )
    outcome_sha256 = _training_outcome_sha256(
        schedule, [int(value) for value in outcomes],
    )
    intent = _make_optimizer_intent(
        h=h, native_block_set_sha256=block_set_sha256,
        feature_moments_sha256=moments_record["sha256"],
        training_outcomes_sha256=outcome_sha256,
    )
    _verify_harness_identity_live(h)
    attempt = _begin_optimizer_once(intent, artifact_root=artifact_root)
    if attempt.may_invoke_optimizer:
        # A change after the durable singleton claim sacrifices recoverability
        # rather than permitting a fit under stale H.
        _verify_harness_identity_live(h)
        caught: shots._TiltOptimizerFailure | None = None
        try:
            fit = shots._fit_residual_tilt(native_model, z, outcomes)
        except shots._TiltOptimizerFailure as exc:
            fit = exc.fit
            caught = exc
        receipt, candidate = _harness_optimizer_receipt(
            fit=fit, native_stored=native_stored, z=z,
            outcomes=outcomes, attempt=attempt,
        )
        receipt_record = _record_optimizer_receipt(
            intent_record=attempt.intent_record, receipt=receipt,
            artifact_root=artifact_root,
        )
        if (caught is not None or receipt["success"] is not True
                or receipt["objective_consistent"] is not True
                or receipt["gradient_consistent"] is not True
                or receipt["gradient_certified"] is not True):
            raise shots.FitFailure(
                "optimizer refusal was durably receipted; training cannot "
                "produce K"
            )
    else:
        if attempt.receipt is None or attempt.receipt_record is None:
            raise shots.LockMismatch("optimizer resume lacks its receipt")
        receipt = dict(attempt.receipt)
        receipt_record = dict(attempt.receipt_record)
        _validate_optimizer_receipt(
            receipt, intent_record=attempt.intent_record,
            intent=attempt.intent,
        )
        if (receipt["success"] is not True
                or receipt["objective_consistent"] is not True
                or receipt["gradient_consistent"] is not True
                or receipt["gradient_certified"] is not True):
            raise shots.FitFailure(
                "previous optimizer refusal is final and cannot be reinvoked"
            )
        beta_resume = np.asarray(receipt["beta"], dtype=np.float64)
        candidate, objective, gradient = _independent_tilt_recompute(
            native_stored, z, beta_resume, outcomes,
        )
        if (not math.isclose(
                    float(receipt["objective_value"]), objective,
                    rel_tol=1e-13, abs_tol=1e-10,
                )
                or not math.isclose(
                    float(receipt["independent_objective_value"]), objective,
                    rel_tol=1e-13, abs_tol=1e-10,
                )
                or not np.allclose(
                    np.asarray(receipt["gradient"]), gradient,
                    rtol=1e-11, atol=1e-10,
                )
                or not np.allclose(
                    np.asarray(receipt["independent_gradient"]), gradient,
                    rtol=1e-11, atol=1e-10,
                )):
            raise shots.FitFailure(
                "resumed optimizer receipt does not independently recompute"
            )

    beta = np.asarray(receipt["beta"], dtype=np.float64)
    coefficients = {
        "schema": _k2_schemas()["coefficients"],
        "training_schedule_sha256": training_sha256,
        "native_block_set_sha256": block_set_sha256,
        "feature_moments_sha256": moments_record["sha256"],
        "optimizer_receipt_sha256": receipt_record["sha256"],
        "feature_names": list(shots.FEATURE_NAMES),
        "reference_outcome": "away",
        "coefficient_order": list(_K2_COEFFICIENT_ORDER),
        "beta_H": beta[:4].tolist(), "beta_D": beta[4:].tolist(),
    }
    coefficients_record = _write_content_addressed_json(
        "coefficients", coefficients, artifact_root=artifact_root,
    )
    expectation_names = ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
    rows: list[dict[str, Any]] = []
    for ordinal, expected in enumerate(schedule):
        feature_row = calculated.iloc[ordinal]
        rows.append(dict(expected) | {
            "shot_expectations": {
                name: float(feature_row[name]) for name in expectation_names
            },
            "features": {
                name: float(x[ordinal, index])
                for index, name in enumerate(shots.FEATURE_NAMES)
            },
            "standardized_features": {
                name: float(z[ordinal, index])
                for index, name in enumerate(shots.FEATURE_NAMES)
            },
            "native": native_stored[ordinal].tolist(),
            "candidate": candidate[ordinal].tolist(),
            "y": int(outcomes[ordinal]),
        })
    training = {
        "schema": _k2_schemas()["training_predictions"],
        "training_schedule_sha256": training_sha256,
        "native_block_set_sha256": block_set_sha256,
        "feature_moments_sha256": moments_record["sha256"],
        "coefficients_sha256": coefficients_record["sha256"],
        "optimizer_receipt_sha256": receipt_record["sha256"],
        "n_rows": len(rows), "rows": rows,
    }
    training_record = _write_content_addressed_json(
        "training_predictions", training, artifact_root=artifact_root,
    )
    records = {
        "training_predictions": {
            "index": training_record,
            "native_intent": native_records["native_intent"],
            "native_blocks": native_records["native_blocks"],
            "native_completions": native_records["native_completions"],
        },
        "feature_moments": moments_record,
        "coefficients": coefficients_record,
        "optimizer": {
            "intent": dict(attempt.intent_record),
            "receipt": receipt_record,
        },
    }
    values = {
        "training_predictions": {
            "index": training,
            "native_intent": native_values["native_intent"],
            "native_blocks": native_values["native_blocks"],
            "native_completions": native_values["native_completions"],
        },
        "feature_moments": moments, "coefficients": coefficients,
        "optimizer": {"intent": dict(attempt.intent), "receipt": receipt},
    }
    _verify_harness_identity_live(h)
    manifest = _build_k2_manifest(
        h=h, schedule=schedule, records=records, values=values,
        _test_only_training_reference=_test_only_training_reference,
    )
    manifest_sha256, manifest_bytes = _write_fixed_canonical_once(
        _K_PATH, manifest, label="K manifest",
    )
    _verify_harness_identity_live(h)
    return {
        "status": "K_DRAFT_WRITTEN_UNFROZEN",
        "harness_commit": h.commit,
        "coefficient_manifest_path": shots.K_MANIFEST_PATH,
        "coefficient_manifest_sha256": manifest_sha256,
        "coefficient_manifest_bytes": manifest_bytes,
        "training_rows": len(schedule),
        "training_blocks": len(_schedule_blocks_exact(schedule)),
        "k_frozen": False,
    }


# ==========================================================================
# Post-K decision transaction (frozen here; effectful only with live H and K)
# ==========================================================================

@dataclass(frozen=True)
class _DecisionAccessAttempt:
    intent_record: Mapping[str, Any]
    intent: Mapping[str, Any]
    may_open_source: bool
    receipt_record: Mapping[str, Any] | None
    receipt: Mapping[str, Any] | None


def _decision_record(
    logical: str, value: Mapping[str, Any], *, ordinal: int | None = None,
) -> dict[str, Any]:
    raw = _canonical_bytes(value)
    digest = hashlib.sha256(raw).hexdigest()
    name = _k2_filename(logical, digest, ordinal=ordinal)
    return {
        "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{name}",
        "sha256": digest, "bytes": len(raw),
        "schema": _k2_schemas()[logical],
    }


def _write_decision_artifact_once(
    logical: str, value: Mapping[str, Any], *, artifact_root: Path,
    ordinal: int | None = None, claim_name: str | None = None,
) -> tuple[dict[str, Any], bool]:
    """Claim one semantic slot before publishing its immutable bytes.

    An existing claim is resumable only when the exact content-addressed file
    already exists.  A claim without bytes is an ambiguous interrupted write;
    it is never completed by a later invocation.
    """
    if (not isinstance(value, Mapping)
            or value.get("schema") != _k2_schemas().get(logical)):
        raise shots.LockMismatch(f"{logical} value has the wrong schema")
    expected = _decision_record(logical, value, ordinal=ordinal)
    slot = claim_name or logical.replace("_", "-")
    claim_created = _reserve_digest(
        Path(artifact_root), slot, str(expected["sha256"]),
    )
    if claim_created:
        record = _write_content_addressed_json(
            logical, value, artifact_root=Path(artifact_root), ordinal=ordinal,
        )
        if record != expected:
            raise shots.LockMismatch(f"{logical} writer changed its record")
        return record, True
    try:
        stored, _ = _load_content_addressed_json(
            logical, expected, artifact_root=Path(artifact_root),
            ordinal=ordinal,
        )
    except shots.ShotsError as exc:
        raise ManualReconciliationRequired(
            f"{logical} was claimed without complete durable bytes; "
            "execution state is ambiguous"
        ) from exc
    if _canonical_bytes(stored) != _canonical_bytes(value):
        raise shots.LockMismatch(f"a different {logical} already exists")
    return expected, False


def _decision_singletons(
    logical: str, *, artifact_root: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    records = _optimizer_records(logical, artifact_root=Path(artifact_root))
    if len(records) > 1:
        raise shots.LockMismatch(f"{logical} has forked immutable artifacts")
    return records


_DECISION_NAMESPACE_LOGICALS = (
    "decision_prediction_intent", "prediction_access_receipt",
    "decision_prediction_block", "decision_predictions", "prediction_seal",
    "scoring_access_intent", "scoring_access_receipt", "decision_scores",
    "decision_canary_receipt", "decision_result",
)


def _decision_namespace_names(*, artifact_root: Path) -> tuple[str, ...]:
    """List decision-stage names without opening any decision-stage value."""
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            return ()
        try:
            names = sorted(os.listdir(directory_fd))
        except OSError as exc:
            raise shots.LockMismatch(
                "decision namespace could not be listed"
            ) from exc
    stems = tuple(
        logical.replace("_", "-") for logical in _DECISION_NAMESPACE_LOGICALS
    )
    return tuple(
        name for name in names
        if (name.startswith("decision-run-")
            or name.startswith(".decision-run")
            or any(name.startswith(f"{stem}-")
                   or name.startswith(f".{stem}") for stem in stems))
    )


def _require_existing_decision_result_claim(
    record: Mapping[str, Any], *, artifact_root: Path,
) -> None:
    """Require bidirectional singleton claim/result evidence."""
    digest = record.get("sha256") if isinstance(record, Mapping) else None
    if not isinstance(digest, str) or not _HEX64.fullmatch(digest):
        raise shots.LockMismatch("decision result record digest is malformed")
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            raise shots.LockMismatch("decision result namespace is absent")
        _require_digest_at(directory_fd, "decision-result", digest)


def _require_decision_record_claim(
    logical: str, record: Mapping[str, Any], *, artifact_root: Path,
    ordinal: int | None = None,
) -> None:
    """Require the exclusive-writer claim paired with one decision artifact."""
    digest, _, _ = _validate_k2_record_metadata(
        logical, record, ordinal=ordinal,
    )
    if logical == "decision_prediction_block" and ordinal is not None:
        slot = f"decision-prediction-block-{ordinal:03d}"
    elif logical == "native_block" and ordinal is not None:
        slot = f"native-block-{ordinal:03d}"
    else:
        slot = logical.replace("_", "-")
    with _open_decision_state_directory(
        Path(artifact_root), create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            raise shots.LockMismatch(f"{logical} claim namespace is absent")
        _require_digest_at(directory_fd, slot, digest)


def _existing_decision_result_only(
    *, artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any]] | None:
    """Load at most the outcome-free terminal result, never sibling values."""
    names = _decision_namespace_names(artifact_root=artifact_root)
    terminal = _decision_singletons(
        "decision_result", artifact_root=artifact_root,
    )
    if not terminal:
        if any(name.startswith("decision-result-")
               or name.startswith(".decision-result") for name in names):
            raise ManualReconciliationRequired(
                "decision result claim/bytes are incomplete; manual "
                "reconciliation is required"
            )
        return None
    record, value = terminal[0]
    _require_existing_decision_result_claim(
        record, artifact_root=artifact_root,
    )
    return dict(record), dict(value)


def _is_pre_k_refusal(value: Mapping[str, Any]) -> bool:
    name = value.get("refusal_name") if isinstance(value, Mapping) else None
    return (
        value.get("schema") == _DECISION_RESULT_SCHEMA
        and value.get("status") == "REFUSED"
        and isinstance(name, str) and bool(name)
        and value.get("coefficient_commit")
            == f"N/A \u2014 K not created after {name}"
    )


def _require_pre_k_decision_namespace(
    *, artifact_root: Path,
    result_record: Mapping[str, Any] | None,
) -> None:
    """Reject decision-stage state by name without opening its values."""
    names = set(_decision_namespace_names(artifact_root=artifact_root))
    allowed: set[str] = set()
    if result_record is not None:
        relative = result_record.get("path")
        if not isinstance(relative, str):
            raise shots.LockMismatch("pre-K result record path is malformed")
        allowed = {
            PurePosixPath(relative).name, ".decision-result.claim",
        }
    unexpected = names - allowed
    if unexpected:
        raise shots.LockMismatch(
            "decision-stage state exists before K; value access and pre-K "
            f"publication are refused: {sorted(unexpected)}"
        )
    if result_record is None and names:
        raise shots.LockMismatch(
            "decision result namespace is ambiguous before K"
        )


def _require_no_orphan_fixed_publication(*, terminal_present: bool) -> None:
    evidence_present = os.path.lexists(_RESULT_EVIDENCE_PATH)
    report_present = os.path.lexists(_RESULT_REPORT_PATH)
    if report_present and not evidence_present:
        raise ManualReconciliationRequired(
            "result report exists without its evidence manifest; manual "
            "reconciliation is required"
        )
    if not terminal_present and (evidence_present or report_present):
        raise ManualReconciliationRequired(
            "fixed publication output exists without a terminal result; "
            "manual reconciliation is required"
        )


def _begin_decision_access_once(
    *, intent_logical: str, receipt_logical: str,
    intent: Mapping[str, Any], artifact_root: Path,
    validate_intent: Any, validate_receipt: Any,
) -> _DecisionAccessAttempt:
    """Authorize one source projection, or resume only from its receipt."""
    validate_intent(intent)
    intended_raw = _canonical_bytes(intent)
    intended_digest = hashlib.sha256(intended_raw).hexdigest()
    intents = _decision_singletons(intent_logical, artifact_root=artifact_root)
    receipts = _decision_singletons(receipt_logical, artifact_root=artifact_root)
    if not intents:
        if receipts:
            raise shots.LockMismatch(
                f"{receipt_logical} exists without its access intent"
            )
        record, created = _write_decision_artifact_once(
            intent_logical, intent, artifact_root=artifact_root,
            claim_name=intent_logical.replace("_", "-"),
        )
        if not created:
            # Another process installed the intent between the two scans.  It
            # may already have opened the source, so this process cannot do so.
            raise ManualReconciliationRequired(
                f"{intent_logical} was concurrently claimed; source-access "
                "state is ambiguous"
            )
        return _DecisionAccessAttempt(
            MappingProxyType(dict(record)), MappingProxyType(dict(intent)),
            True, None, None,
        )

    intent_record, stored_intent = intents[0]
    if (intent_record["sha256"] != intended_digest
            or _canonical_bytes(stored_intent) != intended_raw):
        raise shots.LockMismatch(f"a different {intent_logical} already exists")
    validate_intent(stored_intent)
    if not receipts:
        raise ManualReconciliationRequired(
            f"{intent_logical} exists without {receipt_logical}; "
            "source-access state is ambiguous"
        )
    receipt_record, receipt = receipts[0]
    validate_receipt(
        receipt, intent_record=intent_record, intent=stored_intent,
    )
    return _DecisionAccessAttempt(
        MappingProxyType(dict(intent_record)),
        MappingProxyType(dict(stored_intent)), False,
        MappingProxyType(dict(receipt_record)),
        MappingProxyType(dict(receipt)),
    )


def _record_decision_access_receipt(
    *, intent_logical: str, receipt_logical: str,
    intent_record: Mapping[str, Any], intent: Mapping[str, Any],
    receipt: Mapping[str, Any], artifact_root: Path,
    validate_receipt: Any,
) -> dict[str, Any]:
    validate_receipt(receipt, intent_record=intent_record, intent=intent)
    intents = _decision_singletons(intent_logical, artifact_root=artifact_root)
    if (len(intents) != 1 or intents[0][0] != dict(intent_record)
            or _canonical_bytes(intents[0][1]) != _canonical_bytes(intent)):
        raise shots.LockMismatch("decision source-access intent changed")
    record, _ = _write_decision_artifact_once(
        receipt_logical, receipt, artifact_root=artifact_root,
        claim_name=receipt_logical.replace("_", "-"),
    )
    final = _decision_singletons(receipt_logical, artifact_root=artifact_root)
    if len(final) != 1 or final[0][0] != record:
        raise shots.LockMismatch("decision source-access receipt changed")
    return record


def _read_decision_projection(
    columns: Sequence[str], *, phase: str,
    corpus_path: Path | None = None,
) -> pd.DataFrame:
    """Read exactly one allowlisted projection from the pinned corpus bytes."""
    allowed = {
        "prediction": _PREDICTION_COLUMNS,
        "scoring": _SCORING_COLUMNS,
    }
    exact = tuple(columns)
    if phase not in allowed or exact != allowed[phase]:
        raise shots.LockMismatch(f"{phase} decision projection columns differ")
    source = (paths.FIT_DIR / "walkforward_predictions.parquet"
              if corpus_path is None else Path(corpus_path))
    raw = _read_regular_snapshot(source, label=f"decision {phase} corpus")
    if hashlib.sha256(raw).hexdigest() != shots.DECISION_CORPUS_SHA256:
        raise shots.SourceDigestMismatch(
            f"decision {phase} corpus differs from its pinned digest"
        )
    try:
        frame = pd.read_parquet(io.BytesIO(raw), columns=list(exact))
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise shots.ShotSchemaMismatch(
            f"decision {phase} projection could not be read exactly"
        ) from exc
    if tuple(str(name) for name in frame.columns) != exact:
        raise shots.ShotSchemaMismatch(
            f"decision {phase} projection returned different columns"
        )
    if len(frame) != _DECISION_ROWS:
        raise shots.FixtureSetMismatch(
            f"decision {phase} projection is not exactly {_DECISION_ROWS:,} rows"
        )
    return frame


def _load_decision_model(
    k: _VerifiedK,
) -> tuple[shots.FeatureScaler, np.ndarray, dict[str, Any], dict[str, Any]]:
    """Load only committed K moments and coefficients for decision use."""
    manifest, raw = _read_canonical(_K_PATH, label="K manifest")
    if (hashlib.sha256(raw).hexdigest() != k.manifest_sha256
            or _git_bytes("show", f"{k.commit}:{shots.K_MANIFEST_PATH}") != raw):
        raise shots.LockMismatch("live K manifest changed before prediction")
    records = manifest.get("artifacts")
    if not isinstance(records, Mapping):
        raise shots.LockMismatch("K artifact map is absent")
    moments_record = records.get("feature_moments")
    coefficients_record = records.get("coefficients")
    if not isinstance(moments_record, Mapping) or not isinstance(
        coefficients_record, Mapping,
    ):
        raise shots.LockMismatch("K moments/coefficients records are absent")
    moments = _load_committed_k2_artifact(
        "feature_moments", moments_record, ordinal=None, k_commit=k.commit,
    )
    coefficients = _load_committed_k2_artifact(
        "coefficients", coefficients_record, ordinal=None, k_commit=k.commit,
    )
    _keys(moments, {
        "schema", "training_schedule_sha256", "native_block_set_sha256",
        "names", "means", "population_standard_deviations", "ddof",
        "n_training", "seasons",
    }, label="decision K moments")
    _keys(coefficients, {
        "schema", "training_schedule_sha256", "native_block_set_sha256",
        "feature_moments_sha256", "optimizer_receipt_sha256",
        "feature_names", "reference_outcome", "coefficient_order",
        "beta_H", "beta_D",
    }, label="decision K coefficients")
    means = _finite_vector(moments["means"], 4, label="decision means")
    deviations = _finite_vector(
        moments["population_standard_deviations"], 4,
        label="decision population standard deviations",
    )
    beta_h = _finite_vector(coefficients["beta_H"], 4, label="decision beta_H")
    beta_d = _finite_vector(coefficients["beta_D"], 4, label="decision beta_D")
    if (moments["schema"] != _k2_schemas()["feature_moments"]
            or moments["training_schedule_sha256"]
                != k.harness.training_schedule_sha256
            or moments["names"] != list(shots.FEATURE_NAMES)
            or moments["ddof"] != 0
            or moments["n_training"] != shots.TRAINING_ROWS
            or moments["seasons"] != list(shots.TRAINING_SEASONS)
            or any(value <= 0.0 for value in deviations)
            or coefficients["schema"] != _k2_schemas()["coefficients"]
            or coefficients["training_schedule_sha256"]
                != k.harness.training_schedule_sha256
            or coefficients["feature_moments_sha256"]
                != moments_record["sha256"]
            or coefficients["feature_names"] != list(shots.FEATURE_NAMES)
            or coefficients["reference_outcome"] != "away"
            or coefficients["coefficient_order"]
                != list(_K2_COEFFICIENT_ORDER)):
        raise shots.LockMismatch("committed K decision model semantics differ")
    scaler = shots.FeatureScaler(
        means=means, standard_deviations=deviations,
        n_training=shots.TRAINING_ROWS, seasons=shots.TRAINING_SEASONS,
    )
    beta = np.asarray((*beta_h, *beta_d), dtype=np.float64)
    return scaler, beta, dict(moments_record), dict(coefficients_record)


def _make_prediction_intent(
    *, h: _VerifiedH, k: _VerifiedK, moments_record: Mapping[str, Any],
    coefficients_record: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "schema": _DECISION_PREDICTION_INTENT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "coefficient_commit": k.commit,
        "coefficient_manifest_sha256": k.manifest_sha256,
        "decision_schedule_sha256": h.decision_schedule_sha256,
        "corpus_sha256": shots.DECISION_CORPUS_SHA256,
        "source_path": shots.DECISION_CORPUS_PATH,
        "columns": list(_PREDICTION_COLUMNS),
        "rows": _DECISION_ROWS, "blocks": _DECISION_BLOCKS,
        "feature_moments_sha256": moments_record["sha256"],
        "coefficients_sha256": coefficients_record["sha256"],
        "outcomes_excluded": True, "market_excluded": True,
        "stored_scores_excluded": True,
    }
    _validate_prediction_intent(value)
    return value


def _validate_prediction_intent(value: Mapping[str, Any]) -> None:
    _keys(value, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "coefficient_commit", "coefficient_manifest_sha256",
        "decision_schedule_sha256", "corpus_sha256", "source_path",
        "columns", "rows", "blocks", "feature_moments_sha256",
        "coefficients_sha256", "outcomes_excluded", "market_excluded",
        "stored_scores_excluded",
    }, label="decision prediction intent")
    hashes = (
        value["harness_manifest_sha256"],
        value["coefficient_manifest_sha256"],
        value["decision_schedule_sha256"], value["corpus_sha256"],
        value["feature_moments_sha256"], value["coefficients_sha256"],
    )
    if (value["schema"] != _DECISION_PREDICTION_INTENT_SCHEMA
            or not isinstance(value["harness_commit"], str)
            or not _HEX40.fullmatch(value["harness_commit"])
            or not isinstance(value["coefficient_commit"], str)
            or not _HEX40.fullmatch(value["coefficient_commit"])
            or any(not isinstance(item, str) or not _HEX64.fullmatch(item)
                   for item in hashes)
            or value["corpus_sha256"] != shots.DECISION_CORPUS_SHA256
            or value["source_path"] != shots.DECISION_CORPUS_PATH
            or value["columns"] != list(_PREDICTION_COLUMNS)
            or value["rows"] != _DECISION_ROWS
            or value["blocks"] != _DECISION_BLOCKS
            or value["outcomes_excluded"] is not True
            or value["market_excluded"] is not True
            or value["stored_scores_excluded"] is not True):
        raise shots.LockMismatch("decision prediction intent differs")


def _prediction_projection_rows(
    frame: pd.DataFrame, schedule: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], np.ndarray]:
    if len(frame) != len(schedule):
        raise shots.FixtureSetMismatch("prediction projection count differs")
    native_rows: list[tuple[float, float, float]] = []
    projected: list[dict[str, Any]] = []
    identity = ("match_id", "season", "date", "home_key", "away_key", "block")
    for ordinal, (row, expected) in enumerate(zip(
        frame.itertuples(index=False), schedule, strict=True,
    )):
        observed = {
            "match_id": str(row.match_id), "season": str(row.season),
            "date": _iso_date(row.date), "home_key": str(row.home_key),
            "away_key": str(row.away_key), "block": str(row.block),
        }
        if any(observed[name] != expected[name] for name in identity):
            raise shots.FixtureSetMismatch(
                f"prediction projection identity differs at row {ordinal}"
            )
        native = _probability_vector(
            [row.dc_home, row.dc_draw, row.dc_away],
            label="decision stored native", strictly_positive=True,
            stored_native=True,
        )
        native_rows.append(native)
        projected.append(dict(expected) | {"native": list(native)})
    return projected, np.asarray(native_rows, dtype=np.float64)


def _make_prediction_access_receipt(
    *, intent_record: Mapping[str, Any], intent: Mapping[str, Any],
    projection_sha256: str,
) -> dict[str, Any]:
    value = {
        "schema": _PREDICTION_ACCESS_RECEIPT_SCHEMA,
        "prediction_intent_sha256": intent_record["sha256"],
        "phase": "prediction", "source_path": intent["source_path"],
        "source_sha256": intent["corpus_sha256"],
        "columns": list(intent["columns"]), "rows": intent["rows"],
        "projection_sha256": projection_sha256,
        "outcomes_excluded": True, "market_excluded": True,
        "stored_scores_excluded": True,
    }
    _validate_prediction_access_receipt(
        value, intent_record=intent_record, intent=intent,
    )
    return value


def _validate_prediction_access_receipt(
    value: Mapping[str, Any], *, intent_record: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> None:
    _keys(value, {
        "schema", "prediction_intent_sha256", "phase", "source_path",
        "source_sha256", "columns", "rows", "projection_sha256",
        "outcomes_excluded", "market_excluded", "stored_scores_excluded",
    }, label="prediction access receipt")
    _validate_prediction_intent(intent)
    _validate_k2_record_metadata("decision_prediction_intent", intent_record)
    if (value["schema"] != _PREDICTION_ACCESS_RECEIPT_SCHEMA
            or value["prediction_intent_sha256"] != intent_record["sha256"]
            or value["phase"] != "prediction"
            or value["source_path"] != intent["source_path"]
            or value["source_sha256"] != intent["corpus_sha256"]
            or value["columns"] != intent["columns"]
            or value["rows"] != intent["rows"]
            or not isinstance(value["projection_sha256"], str)
            or not _HEX64.fullmatch(value["projection_sha256"])
            or value["outcomes_excluded"] is not True
            or value["market_excluded"] is not True
            or value["stored_scores_excluded"] is not True):
        raise shots.LockMismatch("prediction access receipt differs")


def _production_decision_features(
    schedule: Sequence[Mapping[str, Any]],
) -> tuple[pd.DataFrame, shots.ShotPanel]:
    fixtures = pd.DataFrame([dict(row) for row in schedule])
    panel = shots.load_pinned_shot_panel()
    calculated = shots.shot_features(panel.frame, fixtures)
    expected = tuple(str(row["match_id"]) for row in schedule)
    if tuple(calculated["match_id"].astype(str)) != expected:
        raise shots.FixtureSetMismatch(
            "decision shot features changed the frozen fixture order"
        )
    if (panel.raw_rows != 4_180 or len(panel.frame) != 4_179
            or len(panel.quarantine) != 1):
        raise shots.ShotPanelMismatch(
            "decision shot panel does not preserve the exact quarantine"
        )
    return calculated, panel


def _decision_prediction_rows(
    *, schedule: Sequence[Mapping[str, Any]], native: np.ndarray,
    calculated: pd.DataFrame, scaler: shots.FeatureScaler,
    beta: np.ndarray,
) -> list[dict[str, Any]]:
    if len(schedule) != len(native) or len(schedule) != len(calculated):
        raise shots.FixtureSetMismatch("decision prediction inputs differ in count")
    z = shots._standardize_features(calculated, scaler)
    candidate = shots._transform_probabilities(native, z, beta)
    x = calculated[list(shots.FEATURE_NAMES)].to_numpy(dtype=np.float64)
    expectation_names = ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
    rows: list[dict[str, Any]] = []
    for ordinal, expected in enumerate(schedule):
        feature_row = calculated.iloc[ordinal]
        rows.append(dict(expected) | {
            "shot_expectations": {
                name: float(feature_row[name]) for name in expectation_names
            },
            "features": {
                name: float(x[ordinal, index])
                for index, name in enumerate(shots.FEATURE_NAMES)
            },
            "standardized_features": {
                name: float(z[ordinal, index])
                for index, name in enumerate(shots.FEATURE_NAMES)
            },
            "native": native[ordinal].tolist(),
            "candidate": candidate[ordinal].tolist(),
        })
    return rows


def _make_prediction_block(
    *, h: _VerifiedH, k: _VerifiedK,
    intent_record: Mapping[str, Any], access_record: Mapping[str, Any],
    block_ordinal: int, block: Sequence[Mapping[str, Any]],
    rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    if not block or len(block) != len(rows):
        raise shots.FixtureSetMismatch("decision prediction block rows differ")
    return {
        "schema": _DECISION_PREDICTION_BLOCK_SCHEMA,
        "prediction_intent_sha256": intent_record["sha256"],
        "access_receipt_sha256": access_record["sha256"],
        "harness_commit": h.commit, "coefficient_commit": k.commit,
        "decision_schedule_sha256": h.decision_schedule_sha256,
        "corpus_sha256": shots.DECISION_CORPUS_SHA256,
        "block_ordinal": block_ordinal, "block": block[0]["block"],
        "cutoff": block[0]["cutoff"],
        "rows": [dict(row) for row in rows],
    }


def _discover_prediction_blocks(
    *, artifact_root: Path,
) -> tuple[tuple[dict[str, Any], dict[str, Any]], ...]:
    root = _componentwise_regular_path(Path(artifact_root), create=False)
    if not root.exists():
        return ()
    found: dict[int, tuple[dict[str, Any], dict[str, Any]]] = {}
    expression = re.compile(
        r"decision-prediction-block-([0-9]{3})-([0-9a-f]{64})\.json"
    )
    for path in sorted(root.iterdir()):
        if not path.name.startswith("decision-prediction-block-"):
            continue
        match = expression.fullmatch(path.name)
        if match is None:
            raise shots.LockMismatch("malformed decision prediction block filename")
        ordinal = int(match.group(1))
        if ordinal in found:
            raise shots.LockMismatch(
                f"decision prediction block {ordinal} has forked artifacts"
            )
        record = {
            "path": f"{shots.SHOTS_ARTIFACT_ROOT}/{path.name}",
            "sha256": match.group(2), "bytes": int(path.stat().st_size),
            "schema": _DECISION_PREDICTION_BLOCK_SCHEMA,
        }
        value, _ = _load_content_addressed_json(
            "decision_prediction_block", record, artifact_root=root,
            ordinal=ordinal,
        )
        if value.get("block_ordinal") != ordinal:
            raise shots.LockMismatch(
                "decision prediction block filename/payload ordinal differs"
            )
        found[ordinal] = (record, value)
    return tuple(found[key] for key in sorted(found))


def _validate_prediction_rows(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]], rows: Sequence[Mapping[str, Any]],
    calculated: pd.DataFrame, scaler: shots.FeatureScaler, beta: np.ndarray,
) -> tuple[np.ndarray, np.ndarray]:
    if len(rows) != len(schedule) or len(calculated) != len(schedule):
        raise shots.FixtureSetMismatch("decision prediction row count differs")
    row_fields = set(_K2_SCHEDULE_FIELDS) | {
        "shot_expectations", "features", "standardized_features",
        "native", "candidate",
    }
    expectation_names = ("HS_hat", "AS_hat", "HST_hat", "AST_hat")
    means = np.asarray(scaler.means, dtype=np.float64)
    deviations = np.asarray(scaler.standard_deviations, dtype=np.float64)
    native_values: list[tuple[float, float, float]] = []
    candidate_values: list[tuple[float, float, float]] = []
    z_values: list[tuple[float, float, float, float]] = []
    for ordinal, (row, expected) in enumerate(zip(
        rows, schedule, strict=True,
    )):
        if (not isinstance(row, Mapping) or set(row) != row_fields
                or any(row[name] != expected[name]
                       for name in _K2_SCHEDULE_FIELDS)):
            raise shots.FixtureSetMismatch(
                f"decision prediction row {ordinal} differs from schedule"
            )
        expectations = row["shot_expectations"]
        features = row["features"]
        standardized = row["standardized_features"]
        if (not isinstance(expectations, Mapping)
                or set(expectations) != set(expectation_names)
                or not isinstance(features, Mapping)
                or set(features) != set(shots.FEATURE_NAMES)
                or not isinstance(standardized, Mapping)
                or set(standardized) != set(shots.FEATURE_NAMES)):
            raise shots.LockMismatch("decision prediction feature schema differs")
        expected_expectations = tuple(
            float(calculated.iloc[ordinal][name]) for name in expectation_names
        )
        stored_expectations = _finite_vector(
            [expectations[name] for name in expectation_names], 4,
            label="decision shot expectations",
        )
        if stored_expectations != expected_expectations:
            raise shots.FitFailure(
                "decision shot expectations do not recompute from pinned shots"
            )
        hs, ass, hst, ast = stored_expectations
        expected_x = (
            hst - ast, (hs - hst) - (ass - ast),
            hst + ast, (hs - hst) + (ass - ast),
        )
        stored_x = _finite_vector(
            [features[name] for name in shots.FEATURE_NAMES], 4,
            label="decision shot features",
        )
        if stored_x != expected_x:
            raise shots.FitFailure("decision shot feature algebra differs")
        stored_z = _finite_vector(
            [standardized[name] for name in shots.FEATURE_NAMES], 4,
            label="decision standardized features",
        )
        recomputed_z = tuple((np.asarray(stored_x) - means) / deviations)
        if not np.allclose(stored_z, recomputed_z, rtol=1e-13, atol=1e-13):
            raise shots.FitFailure("decision standardized features differ")
        native = _probability_vector(
            row["native"], label="decision stored native",
            strictly_positive=True, stored_native=True,
        )
        candidate = _probability_vector(
            row["candidate"], label="decision candidate",
            strictly_positive=True,
        )
        native_values.append(native)
        candidate_values.append(candidate)
        z_values.append(tuple(float(item) for item in stored_z))
    native_array = np.asarray(native_values, dtype=np.float64)
    z_array = np.asarray(z_values, dtype=np.float64)
    recomputed = shots._transform_probabilities(native_array, z_array, beta)
    if not np.allclose(
        np.asarray(candidate_values, dtype=np.float64), recomputed,
        rtol=5e-13, atol=5e-15,
    ):
        raise shots.FitFailure("decision candidate probabilities do not recompute")
    del h, k
    return native_array, recomputed


def _validate_prediction_blocks(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]],
    intent_record: Mapping[str, Any], access_record: Mapping[str, Any],
    records_and_values: Sequence[tuple[Mapping[str, Any], Mapping[str, Any]]],
    calculated: pd.DataFrame, scaler: shots.FeatureScaler, beta: np.ndarray,
    require_complete: bool = True,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    blocks = _decision_schedule_blocks_exact(schedule)
    if require_complete and len(records_and_values) != len(blocks):
        raise shots.FixtureSetMismatch(
            "decision prediction shard count differs from 212 blocks"
        )
    if not require_complete and len(records_and_values) > len(blocks):
        raise shots.FixtureSetMismatch(
            "decision prediction shard prefix exceeds the frozen blocks"
        )
    expected_blocks = (
        blocks if require_complete else blocks[:len(records_and_values)]
    )
    all_rows: list[dict[str, Any]] = []
    records: list[dict[str, Any]] = []
    offset = 0
    for ordinal, ((record, value), expected_block) in enumerate(zip(
        records_and_values, expected_blocks, strict=True,
    )):
        _validate_k2_record_metadata(
            "decision_prediction_block", record, ordinal=ordinal,
        )
        _keys(value, {
            "schema", "prediction_intent_sha256", "access_receipt_sha256",
            "harness_commit", "coefficient_commit",
            "decision_schedule_sha256", "corpus_sha256", "block_ordinal",
            "block", "cutoff", "rows",
        }, label="decision prediction block")
        if (value["schema"] != _DECISION_PREDICTION_BLOCK_SCHEMA
                or value["prediction_intent_sha256"]
                    != intent_record["sha256"]
                or value["access_receipt_sha256"] != access_record["sha256"]
                or value["harness_commit"] != h.commit
                or value["coefficient_commit"] != k.commit
                or value["decision_schedule_sha256"]
                    != h.decision_schedule_sha256
                or value["corpus_sha256"] != shots.DECISION_CORPUS_SHA256
                or value["block_ordinal"] != ordinal
                or value["block"] != expected_block[0]["block"]
                or value["cutoff"] != expected_block[0]["cutoff"]
                or not isinstance(value["rows"], list)
                or len(value["rows"]) != len(expected_block)):
            raise shots.LockMismatch("decision prediction block binding differs")
        block_rows = [dict(row) for row in value["rows"]]
        _validate_prediction_rows(
            h=h, k=k, schedule=expected_block, rows=block_rows,
            calculated=calculated.iloc[
                offset:offset + len(expected_block)
            ].reset_index(drop=True),
            scaler=scaler, beta=beta,
        )
        offset += len(expected_block)
        records.append(dict(record)); all_rows.extend(block_rows)
    return records, all_rows


def _make_decision_predictions(
    *, h: _VerifiedH, k: _VerifiedK,
    block_records: Sequence[Mapping[str, Any]],
    access_record: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
) -> dict[str, Any]:
    return {
        "schema": _DECISION_PREDICTIONS_SCHEMA,
        "harness_commit": h.commit, "coefficient_commit": k.commit,
        "decision_schedule_sha256": h.decision_schedule_sha256,
        "corpus_sha256": shots.DECISION_CORPUS_SHA256,
        "block_set_sha256": _digest_rows(
            _DECISION_PREDICTION_BLOCK_SET_SCHEMA, block_records,
        ),
        "access_receipt_sha256": access_record["sha256"],
        "blocks": [dict(record) for record in block_records],
        "n_rows": len(rows), "rows": [dict(row) for row in rows],
    }


def _validate_decision_predictions(
    value: Mapping[str, Any], *, h: _VerifiedH, k: _VerifiedK,
    block_records: Sequence[Mapping[str, Any]],
    access_record: Mapping[str, Any], rows: Sequence[Mapping[str, Any]],
) -> None:
    _keys(value, {
        "schema", "harness_commit", "coefficient_commit",
        "decision_schedule_sha256", "corpus_sha256", "block_set_sha256",
        "access_receipt_sha256", "blocks", "n_rows", "rows",
    }, label="decision predictions")
    if (value["schema"] != _DECISION_PREDICTIONS_SCHEMA
            or value["harness_commit"] != h.commit
            or value["coefficient_commit"] != k.commit
            or value["decision_schedule_sha256"]
                != h.decision_schedule_sha256
            or value["corpus_sha256"] != shots.DECISION_CORPUS_SHA256
            or value["block_set_sha256"] != _digest_rows(
                _DECISION_PREDICTION_BLOCK_SET_SCHEMA, block_records,
            )
            or value["access_receipt_sha256"] != access_record["sha256"]
            or value["blocks"] != [dict(record) for record in block_records]
            or value["n_rows"] != _DECISION_ROWS
            or value["rows"] != [dict(row) for row in rows]):
        raise shots.LockMismatch("decision prediction aggregate differs")


def _make_prediction_seal(
    *, h: _VerifiedH, k: _VerifiedK,
    predictions_record: Mapping[str, Any],
    access_record: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "schema": _PREDICTION_SEAL_SCHEMA,
        "harness_commit": h.commit, "coefficient_commit": k.commit,
        "decision_schedule_sha256": h.decision_schedule_sha256,
        "corpus_sha256": shots.DECISION_CORPUS_SHA256,
        "decision_predictions": dict(predictions_record),
        "access_receipt": dict(access_record), "rows": _DECISION_ROWS,
        "durably_fsynced": True, "reopened": True,
        "semantic_verified": True,
    }


def _validate_prediction_seal_value(
    value: Mapping[str, Any], *, h: _VerifiedH, k: _VerifiedK,
) -> tuple[dict[str, Any], dict[str, Any]]:
    _keys(value, {
        "schema", "harness_commit", "coefficient_commit",
        "decision_schedule_sha256", "corpus_sha256",
        "decision_predictions", "access_receipt", "rows",
        "durably_fsynced", "reopened", "semantic_verified",
    }, label="prediction seal")
    predictions_record = value["decision_predictions"]
    access_record = value["access_receipt"]
    _validate_k2_record_metadata("decision_predictions", predictions_record)
    _validate_k2_record_metadata("prediction_access_receipt", access_record)
    if (value["schema"] != _PREDICTION_SEAL_SCHEMA
            or value["harness_commit"] != h.commit
            or value["coefficient_commit"] != k.commit
            or value["decision_schedule_sha256"]
                != h.decision_schedule_sha256
            or value["corpus_sha256"] != shots.DECISION_CORPUS_SHA256
            or value["rows"] != _DECISION_ROWS
            or value["durably_fsynced"] is not True
            or value["reopened"] is not True
            or value["semantic_verified"] is not True):
        raise shots.LockMismatch("prediction seal differs")
    return dict(predictions_record), dict(access_record)


def _load_prediction_seal(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]], scaler: shots.FeatureScaler,
    beta: np.ndarray, artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    seals = _decision_singletons("prediction_seal", artifact_root=artifact_root)
    if len(seals) != 1:
        raise shots.LockMismatch("one durable prediction seal is required")
    seal_record, seal = seals[0]
    predictions_record, access_record = _validate_prediction_seal_value(
        seal, h=h, k=k,
    )
    intents = _decision_singletons(
        "decision_prediction_intent", artifact_root=artifact_root,
    )
    accesses = _decision_singletons(
        "prediction_access_receipt", artifact_root=artifact_root,
    )
    if len(intents) != 1 or len(accesses) != 1 or accesses[0][0] != access_record:
        raise shots.LockMismatch("sealed prediction access closure differs")
    intent_record, intent = intents[0]
    _validate_prediction_access_receipt(
        accesses[0][1], intent_record=intent_record, intent=intent,
    )
    calculated, _ = _production_decision_features(schedule)
    blocks = _discover_prediction_blocks(artifact_root=artifact_root)
    block_records, rows = _validate_prediction_blocks(
        h=h, k=k, schedule=schedule, intent_record=intent_record,
        access_record=access_record, records_and_values=blocks,
        calculated=calculated, scaler=scaler, beta=beta,
    )
    projection = [
        dict(schedule[ordinal]) | {"native": list(row["native"])}
        for ordinal, row in enumerate(rows)
    ]
    projection_digest = _digest_rows(
        _DECISION_PREDICTION_PROJECTION_SCHEMA, projection,
    )
    if accesses[0][1]["projection_sha256"] != projection_digest:
        raise shots.LockMismatch("sealed prediction projection digest differs")
    predictions, _ = _load_content_addressed_json(
        "decision_predictions", predictions_record,
        artifact_root=artifact_root,
    )
    _validate_decision_predictions(
        predictions, h=h, k=k, block_records=block_records,
        access_record=access_record, rows=rows,
    )
    # Re-open the seal after every transitive semantic check.  The record is
    # accepted only if its exact bytes still name the same content address.
    reopened, _ = _load_content_addressed_json(
        "prediction_seal", seal_record, artifact_root=artifact_root,
    )
    if _canonical_bytes(reopened) != _canonical_bytes(seal):
        raise shots.LockMismatch("prediction seal changed during verification")
    return dict(seal_record), dict(seal), rows


def _ensure_prediction_seal(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]], scaler: shots.FeatureScaler,
    beta: np.ndarray, moments_record: Mapping[str, Any],
    coefficients_record: Mapping[str, Any], artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], list[dict[str, Any]]]:
    existing_seals = _decision_singletons(
        "prediction_seal", artifact_root=artifact_root,
    )
    if existing_seals:
        return _load_prediction_seal(
            h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
            artifact_root=artifact_root,
        )
    intent = _make_prediction_intent(
        h=h, k=k, moments_record=moments_record,
        coefficients_record=coefficients_record,
    )
    attempt = _begin_decision_access_once(
        intent_logical="decision_prediction_intent",
        receipt_logical="prediction_access_receipt", intent=intent,
        artifact_root=artifact_root,
        validate_intent=_validate_prediction_intent,
        validate_receipt=_validate_prediction_access_receipt,
    )
    if attempt.may_open_source:
        if _discover_prediction_blocks(artifact_root=artifact_root):
            raise ManualReconciliationRequired(
                "prediction blocks predate their access intent; state is ambiguous"
            )
        frame = _read_decision_projection(
            _PREDICTION_COLUMNS, phase="prediction",
        )
        projection, native = _prediction_projection_rows(frame, schedule)
        projection_sha256 = _digest_rows(
            _DECISION_PREDICTION_PROJECTION_SCHEMA, projection,
        )
        access = _make_prediction_access_receipt(
            intent_record=attempt.intent_record, intent=attempt.intent,
            projection_sha256=projection_sha256,
        )
        access_record = _record_decision_access_receipt(
            intent_logical="decision_prediction_intent",
            receipt_logical="prediction_access_receipt",
            intent_record=attempt.intent_record, intent=attempt.intent,
            receipt=access, artifact_root=artifact_root,
            validate_receipt=_validate_prediction_access_receipt,
        )
        calculated, _ = _production_decision_features(schedule)
        rows = _decision_prediction_rows(
            schedule=schedule, native=native, calculated=calculated,
            scaler=scaler, beta=beta,
        )
        blocks = _decision_schedule_blocks_exact(schedule)
        offset = 0
        for ordinal, block in enumerate(blocks):
            count = len(block)
            value = _make_prediction_block(
                h=h, k=k, intent_record=attempt.intent_record,
                access_record=access_record, block_ordinal=ordinal,
                block=block, rows=rows[offset:offset + count],
            )
            _write_decision_artifact_once(
                "decision_prediction_block", value,
                artifact_root=artifact_root, ordinal=ordinal,
                claim_name=f"decision-prediction-block-{ordinal:03d}",
            )
            offset += count
    else:
        if attempt.receipt_record is None:
            raise shots.LockMismatch("prediction resume lacks access receipt")
        access_record = dict(attempt.receipt_record)
        if len(_discover_prediction_blocks(
            artifact_root=artifact_root,
        )) != _DECISION_BLOCKS:
            raise ManualReconciliationRequired(
                "prediction access completed without all 212 shards; "
                "source cannot be reopened"
            )

    calculated, _ = _production_decision_features(schedule)
    stored_blocks = _discover_prediction_blocks(artifact_root=artifact_root)
    block_records, rows = _validate_prediction_blocks(
        h=h, k=k, schedule=schedule,
        intent_record=attempt.intent_record, access_record=access_record,
        records_and_values=stored_blocks, calculated=calculated,
        scaler=scaler, beta=beta,
    )
    aggregate = _make_decision_predictions(
        h=h, k=k, block_records=block_records,
        access_record=access_record, rows=rows,
    )
    _validate_decision_predictions(
        aggregate, h=h, k=k, block_records=block_records,
        access_record=access_record, rows=rows,
    )
    predictions_record, _ = _write_decision_artifact_once(
        "decision_predictions", aggregate, artifact_root=artifact_root,
    )
    reopened, _ = _load_content_addressed_json(
        "decision_predictions", predictions_record,
        artifact_root=artifact_root,
    )
    _validate_decision_predictions(
        reopened, h=h, k=k, block_records=block_records,
        access_record=access_record, rows=rows,
    )
    seal = _make_prediction_seal(
        h=h, k=k, predictions_record=predictions_record,
        access_record=access_record,
    )
    _write_decision_artifact_once(
        "prediction_seal", seal, artifact_root=artifact_root,
    )
    return _load_prediction_seal(
        h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
        artifact_root=artifact_root,
    )


def _make_scoring_access_intent(
    *, h: _VerifiedH, k: _VerifiedK,
    prediction_seal_record: Mapping[str, Any],
) -> dict[str, Any]:
    value = {
        "schema": _SCORING_ACCESS_INTENT_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "coefficient_commit": k.commit,
        "coefficient_manifest_sha256": k.manifest_sha256,
        "decision_schedule_sha256": h.decision_schedule_sha256,
        "prediction_seal_sha256": prediction_seal_record["sha256"],
        "source_path": shots.DECISION_CORPUS_PATH,
        "source_sha256": shots.DECISION_CORPUS_SHA256,
        "columns": list(_SCORING_COLUMNS), "rows": _DECISION_ROWS,
        "exactly_once": True,
    }
    _validate_scoring_access_intent(value)
    return value


def _validate_scoring_access_intent(value: Mapping[str, Any]) -> None:
    _keys(value, {
        "schema", "harness_commit", "harness_manifest_sha256",
        "coefficient_commit", "coefficient_manifest_sha256",
        "decision_schedule_sha256", "prediction_seal_sha256",
        "source_path", "source_sha256", "columns", "rows", "exactly_once",
    }, label="scoring access intent")
    hashes = (
        value["harness_manifest_sha256"],
        value["coefficient_manifest_sha256"],
        value["decision_schedule_sha256"], value["prediction_seal_sha256"],
        value["source_sha256"],
    )
    if (value["schema"] != _SCORING_ACCESS_INTENT_SCHEMA
            or not isinstance(value["harness_commit"], str)
            or not _HEX40.fullmatch(value["harness_commit"])
            or not isinstance(value["coefficient_commit"], str)
            or not _HEX40.fullmatch(value["coefficient_commit"])
            or any(not isinstance(item, str) or not _HEX64.fullmatch(item)
                   for item in hashes)
            or value["source_path"] != shots.DECISION_CORPUS_PATH
            or value["source_sha256"] != shots.DECISION_CORPUS_SHA256
            or value["columns"] != list(_SCORING_COLUMNS)
            or value["rows"] != _DECISION_ROWS
            or value["exactly_once"] is not True):
        raise shots.LockMismatch("scoring access intent differs")


def _make_scoring_access_receipt(
    *, intent_record: Mapping[str, Any], intent: Mapping[str, Any],
    projection_sha256: str,
) -> dict[str, Any]:
    value = {
        "schema": _SCORING_ACCESS_RECEIPT_SCHEMA,
        "scoring_access_intent_sha256": intent_record["sha256"],
        "prediction_seal_sha256": intent["prediction_seal_sha256"],
        "phase": "scoring", "source_path": intent["source_path"],
        "source_sha256": intent["source_sha256"],
        "columns": list(intent["columns"]), "rows": intent["rows"],
        "projection_sha256": projection_sha256,
        "outcomes_opened": True, "market_opened": True,
        "stored_scores_opened": True, "completed": True,
    }
    _validate_scoring_access_receipt(
        value, intent_record=intent_record, intent=intent,
    )
    return value


def _validate_scoring_access_receipt(
    value: Mapping[str, Any], *, intent_record: Mapping[str, Any],
    intent: Mapping[str, Any],
) -> None:
    _keys(value, {
        "schema", "scoring_access_intent_sha256",
        "prediction_seal_sha256", "phase", "source_path", "source_sha256",
        "columns", "rows", "projection_sha256", "outcomes_opened",
        "market_opened", "stored_scores_opened", "completed",
    }, label="scoring access receipt")
    _validate_scoring_access_intent(intent)
    _validate_k2_record_metadata("scoring_access_intent", intent_record)
    if (value["schema"] != _SCORING_ACCESS_RECEIPT_SCHEMA
            or value["scoring_access_intent_sha256"]
                != intent_record["sha256"]
            or value["prediction_seal_sha256"]
                != intent["prediction_seal_sha256"]
            or value["phase"] != "scoring"
            or value["source_path"] != intent["source_path"]
            or value["source_sha256"] != intent["source_sha256"]
            or value["columns"] != intent["columns"]
            or value["rows"] != intent["rows"]
            or not isinstance(value["projection_sha256"], str)
            or not _HEX64.fullmatch(value["projection_sha256"])
            or value["outcomes_opened"] is not True
            or value["market_opened"] is not True
            or value["stored_scores_opened"] is not True
            or value["completed"] is not True):
        raise shots.LockMismatch("scoring access receipt differs")


def _read_scoring_projection_after_seal(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]], scaler: shots.FeatureScaler,
    beta: np.ndarray, artifact_root: Path,
) -> tuple[
    dict[str, Any], dict[str, Any], list[dict[str, Any]], pd.DataFrame,
]:
    """The sole outcome/market opening seam; a live seal check comes first."""
    seal_record, seal, prediction_rows = _load_prediction_seal(
        h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
        artifact_root=artifact_root,
    )
    frame = _read_decision_projection(_SCORING_COLUMNS, phase="scoring")
    return seal_record, seal, prediction_rows, frame


def _finite_scalar(value: Any, *, label: str) -> float:
    if (not isinstance(value, (int, float, np.integer, np.floating))
            or isinstance(value, (bool, np.bool_))
            or not math.isfinite(float(value))):
        raise shots.LockMismatch(f"{label} is not one finite number")
    return float(value)


def _scoring_projection_rows(
    frame: pd.DataFrame, schedule: Sequence[Mapping[str, Any]],
) -> tuple[list[dict[str, Any]], np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    if len(frame) != len(schedule):
        raise shots.FixtureSetMismatch("scoring projection count differs")
    projection: list[dict[str, Any]] = []
    outcomes: list[int] = []
    markets: list[tuple[float, float, float]] = []
    stored_native: list[float] = []
    stored_market: list[float] = []
    for ordinal, (row, expected) in enumerate(zip(
        frame.itertuples(index=False), schedule, strict=True,
    )):
        identity = {
            "match_id": str(row.match_id), "season": str(row.season),
            "block": str(row.block),
        }
        if any(identity[name] != expected[name] for name in identity):
            raise shots.FixtureSetMismatch(
                f"scoring projection identity differs at row {ordinal}"
            )
        code_value = _finite_scalar(row.y, label="decision outcome")
        if code_value not in (0.0, 1.0, 2.0):
            raise shots.FitFailure("decision outcome is not 0/1/2")
        code = int(code_value)
        market = _probability_vector(
            [row.market_home, row.market_draw, row.market_away],
            label="decision market", strictly_positive=True,
        )
        native_rps = _finite_scalar(row.dc_rps, label="stored native RPS")
        market_rps = _finite_scalar(row.market_rps, label="stored market RPS")
        if not 0.0 <= native_rps <= 1.0 or not 0.0 <= market_rps <= 1.0:
            raise shots.LockMismatch("stored comparator RPS is outside [0,1]")
        outcomes.append(code); markets.append(market)
        stored_native.append(native_rps); stored_market.append(market_rps)
        projection.append({
            "ordinal": ordinal, **identity, "y": code,
            "market": list(market), "stored_native_rps": native_rps,
            "stored_market_rps": market_rps,
        })
    return (
        projection, np.asarray(outcomes, dtype=int),
        np.asarray(markets, dtype=np.float64),
        np.asarray(stored_native, dtype=np.float64),
        np.asarray(stored_market, dtype=np.float64),
    )


def _decision_score_payload(
    *, prediction_rows: Sequence[Mapping[str, Any]],
    scoring_projection: Sequence[Mapping[str, Any]],
    prediction_seal_record: Mapping[str, Any],
    scoring_access_record: Mapping[str, Any],
    scoring_projection_sha256: str,
) -> dict[str, Any]:
    if len(prediction_rows) != len(scoring_projection):
        raise shots.FixtureSetMismatch("prediction/scoring row counts differ")
    ids = [str(row["match_id"]) for row in prediction_rows]
    native = np.asarray([row["native"] for row in prediction_rows], dtype=np.float64)
    candidate = np.asarray(
        [row["candidate"] for row in prediction_rows], dtype=np.float64,
    )
    market = np.asarray(
        [row["market"] for row in scoring_projection], dtype=np.float64,
    )
    outcomes = np.asarray(
        [row["y"] for row in scoring_projection], dtype=int,
    )
    scores = shots._paired_rps_unchecked(
        candidate, native, market, outcomes,
        candidate_ids=ids, native_ids=ids,
        market_ids=[row["match_id"] for row in scoring_projection],
        outcome_ids=[row["match_id"] for row in scoring_projection],
        expected_ids=ids,
    )
    candidate_rps = np.asarray(scores.candidate_rps, dtype=np.float64)
    native_rps = np.asarray(scores.native_rps, dtype=np.float64)
    market_rps = np.asarray(scores.market_rps, dtype=np.float64)
    stored_native = np.asarray(
        [row["stored_native_rps"] for row in scoring_projection],
        dtype=np.float64,
    )
    stored_market = np.asarray(
        [row["stored_market_rps"] for row in scoring_projection],
        dtype=np.float64,
    )
    native_error = native_rps - stored_native
    market_error = market_rps - stored_market
    if (np.max(np.abs(native_error)) > 1e-12
            or np.max(np.abs(market_error)) > 1e-12):
        raise shots.LockMismatch(
            "recomputed comparator RPS differs from the stored corpus score"
        )
    row_index = np.arange(len(outcomes))
    with np.errstate(divide="ignore", invalid="ignore"):
        candidate_ll = -np.log(candidate[row_index, outcomes])
        native_ll = -np.log(native[row_index, outcomes])
        market_ll = -np.log(market[row_index, outcomes])
    if not all(np.isfinite(values).all() for values in (
        candidate_ll, native_ll, market_ll,
    )):
        raise shots.ProbabilityInvalid("decision log loss is nonfinite")
    rows: list[dict[str, Any]] = []
    for ordinal, (prediction, scoring) in enumerate(zip(
        prediction_rows, scoring_projection, strict=True,
    )):
        rows.append({
            "ordinal": ordinal, "match_id": prediction["match_id"],
            "season": prediction["season"], "block": prediction["block"],
            "y": int(outcomes[ordinal]),
            "candidate": candidate[ordinal].tolist(),
            "native": native[ordinal].tolist(),
            "market": market[ordinal].tolist(),
            "candidate_rps": float(candidate_rps[ordinal]),
            "native_rps": float(native_rps[ordinal]),
            "market_rps": float(market_rps[ordinal]),
            "stored_native_rps": float(stored_native[ordinal]),
            "stored_market_rps": float(stored_market[ordinal]),
            "native_rps_parity_error": float(native_error[ordinal]),
            "market_rps_parity_error": float(market_error[ordinal]),
            "d_native": float(candidate_rps[ordinal] - native_rps[ordinal]),
            "d_market": float(candidate_rps[ordinal] - market_rps[ordinal]),
            "candidate_log_loss": float(candidate_ll[ordinal]),
            "native_log_loss": float(native_ll[ordinal]),
            "market_log_loss": float(market_ll[ordinal]),
            "ll_d_native": float(candidate_ll[ordinal] - native_ll[ordinal]),
            "ll_d_market": float(candidate_ll[ordinal] - market_ll[ordinal]),
        })
    return {
        "schema": _DECISION_SCORES_SCHEMA,
        "prediction_seal_sha256": prediction_seal_record["sha256"],
        "scoring_access_receipt_sha256": scoring_access_record["sha256"],
        "scoring_projection_sha256": scoring_projection_sha256,
        "n_rows": len(rows), "rows": rows,
    }


def _validate_decision_scores(
    value: Mapping[str, Any], *, prediction_rows: Sequence[Mapping[str, Any]],
    prediction_seal_record: Mapping[str, Any],
    scoring_access_record: Mapping[str, Any],
) -> None:
    _keys(value, {
        "schema", "prediction_seal_sha256",
        "scoring_access_receipt_sha256", "scoring_projection_sha256",
        "n_rows", "rows",
    }, label="decision scores")
    if (value["schema"] != _DECISION_SCORES_SCHEMA
            or value["prediction_seal_sha256"]
                != prediction_seal_record["sha256"]
            or value["scoring_access_receipt_sha256"]
                != scoring_access_record["sha256"]
            or not isinstance(value["scoring_projection_sha256"], str)
            or not _HEX64.fullmatch(value["scoring_projection_sha256"])
            or value["n_rows"] != len(prediction_rows)
            or not isinstance(value["rows"], list)
            or len(value["rows"]) != len(prediction_rows)):
        raise shots.LockMismatch("decision score binding differs")
    expected_fields = {
        "ordinal", "match_id", "season", "block", "y",
        "candidate", "native", "market", "candidate_rps", "native_rps",
        "market_rps", "stored_native_rps", "stored_market_rps",
        "native_rps_parity_error", "market_rps_parity_error", "d_native",
        "d_market", "candidate_log_loss", "native_log_loss",
        "market_log_loss", "ll_d_native", "ll_d_market",
    }
    scoring_projection: list[dict[str, Any]] = []
    for ordinal, (row, prediction) in enumerate(zip(
        value["rows"], prediction_rows, strict=True,
    )):
        if (not isinstance(row, Mapping) or set(row) != expected_fields
                or row["ordinal"] != ordinal
                or any(row[name] != prediction[name]
                       for name in ("match_id", "season", "block"))):
            raise shots.FixtureSetMismatch("decision score row identity differs")
        if row["candidate"] != prediction["candidate"] \
                or row["native"] != prediction["native"]:
            raise shots.LockMismatch("decision score probabilities differ from seal")
        market = _probability_vector(
            row["market"], label="stored decision-score market",
            strictly_positive=True,
        )
        code = _finite_scalar(row["y"], label="stored decision-score outcome")
        if code not in (0.0, 1.0, 2.0):
            raise shots.FitFailure("stored decision-score outcome differs")
        scoring_projection.append({
            "ordinal": ordinal, "match_id": row["match_id"],
            "season": row["season"], "block": row["block"],
            "y": int(code), "market": list(market),
            "stored_native_rps": _finite_scalar(
                row["stored_native_rps"], label="stored native RPS",
            ),
            "stored_market_rps": _finite_scalar(
                row["stored_market_rps"], label="stored market RPS",
            ),
        })
    projection_sha256 = _digest_rows(
        _DECISION_SCORING_PROJECTION_SCHEMA, scoring_projection,
    )
    if value["scoring_projection_sha256"] != projection_sha256:
        raise shots.LockMismatch(
            "decision score projection digest does not recompute"
        )
    recomputed = _decision_score_payload(
        prediction_rows=prediction_rows, scoring_projection=scoring_projection,
        prediction_seal_record=prediction_seal_record,
        scoring_access_record=scoring_access_record,
        scoring_projection_sha256=projection_sha256,
    )
    if _canonical_bytes(recomputed) != _canonical_bytes(value):
        raise shots.LockMismatch("decision scores do not independently recompute")


def _ci_dict(value: shots.BootstrapCI) -> dict[str, Any]:
    return asdict(value)


def _decision_estimates_from_scores(
    score_value: Mapping[str, Any],
) -> dict[str, Any]:
    rows = score_value["rows"]
    if not isinstance(rows, list) or not rows:
        raise shots.FixtureSetMismatch("decision score rows are absent")
    d_native = np.asarray([row["d_native"] for row in rows], dtype=np.float64)
    d_market = np.asarray([row["d_market"] for row in rows], dtype=np.float64)
    weeks = [str(row["block"]) for row in rows]
    seasons = [str(row["season"]) for row in rows]
    candidate_ll = np.asarray(
        [row["candidate_log_loss"] for row in rows], dtype=np.float64,
    )
    native_ll = np.asarray(
        [row["native_log_loss"] for row in rows], dtype=np.float64,
    )
    market_ll = np.asarray(
        [row["market_log_loss"] for row in rows], dtype=np.float64,
    )
    if not all(np.isfinite(values).all() for values in (
        d_native, d_market, candidate_ll, native_ll, market_ll,
    )):
        raise shots.LockMismatch("decision estimates contain nonfinite values")
    week_native = shots._block_bootstrap(
        d_native, weeks, seed=shots.WEEK_BOOTSTRAP_SEED,
    )
    week_market = shots._block_bootstrap(
        d_market, weeks, seed=shots.WEEK_BOOTSTRAP_SEED,
    )
    season_native = shots._block_bootstrap(
        d_native, seasons, seed=shots.SEASON_BOOTSTRAP_SEED,
    )
    season_market = shots._block_bootstrap(
        d_market, seasons, seed=shots.SEASON_BOOTSTRAP_SEED,
    )
    per_native = shots._per_season_means_unchecked(d_native, seasons)
    per_market = shots._per_season_means_unchecked(d_market, seasons)
    mean_ll = {
        "candidate": float(candidate_ll.mean()),
        "native": float(native_ll.mean()),
        "market": float(market_ll.mean()),
    }
    paired_ll = {
        "candidate_minus_native": float((candidate_ll - native_ll).mean()),
        "candidate_minus_market": float((candidate_ll - market_ll).mean()),
    }
    parity_native = max(abs(float(row["native_rps_parity_error"])) for row in rows)
    parity_market = max(abs(float(row["market_rps_parity_error"])) for row in rows)
    stored_parity = {
        "tolerance": 1e-12,
        "native_max_abs_error": parity_native,
        "market_max_abs_error": parity_market,
        "passed": parity_native <= 1e-12 and parity_market <= 1e-12,
    }
    gates = {
        "mean_d_native_lte_minus_0_001": float(d_native.mean()) <= -0.0010,
        "weekly_upper_native_lt_zero": week_native.high < 0.0,
        "at_least_four_negative_seasons": (
            sum(value < 0.0 for value in per_native.values()) >= 4
        ),
        "no_season_native_gt_0_002": (
            max(per_native.values()) <= 0.0020
        ),
        "mean_log_loss_no_harm": paired_ll["candidate_minus_native"] <= 0.0010,
    }
    gates["eligible"] = all(gates.values())
    if float(d_native.mean()) >= 0.0:
        disposition = "REJECT"
    elif gates["eligible"]:
        disposition = "ELIGIBLE_FOR_SEPARATELY_PREREGISTERED_PRODUCTION_BUILD"
    else:
        disposition = "RESEARCH_SIGNAL_ONLY_DO_NOT_ADOPT"
    market_competitive = (
        float(d_market.mean()) <= 0.0 and week_market.high < 0.0
    )
    return {
        "n": len(rows), "mean_d_native": float(d_native.mean()),
        "mean_d_market": float(d_market.mean()),
        "week_ci_native": _ci_dict(week_native),
        "week_ci_market": _ci_dict(week_market),
        "season_ci_native": _ci_dict(season_native),
        "season_ci_market": _ci_dict(season_market),
        "per_season_native": per_native, "per_season_market": per_market,
        "mean_log_loss": mean_ll, "paired_log_loss_deltas": paired_ll,
        "stored_rps_parity": stored_parity, "decision_gates": gates,
        "disposition": disposition,
        "market_competitive": market_competitive,
    }


def _ensure_decision_scores(
    *, h: _VerifiedH, k: _VerifiedK,
    schedule: Sequence[Mapping[str, Any]], scaler: shots.FeatureScaler,
    beta: np.ndarray, prediction_seal_record: Mapping[str, Any],
    prediction_rows: Sequence[Mapping[str, Any]], artifact_root: Path,
) -> tuple[dict[str, Any], dict[str, Any], dict[str, Any], dict[str, Any]]:
    stored_scores = _decision_singletons(
        "decision_scores", artifact_root=artifact_root,
    )
    intent = _make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=prediction_seal_record,
    )
    if stored_scores:
        intents = _decision_singletons(
            "scoring_access_intent", artifact_root=artifact_root,
        )
        receipts = _decision_singletons(
            "scoring_access_receipt", artifact_root=artifact_root,
        )
        if len(intents) != 1 or len(receipts) != 1:
            raise ManualReconciliationRequired(
                "decision scores lack a complete scoring-access closure"
            )
        intent_record, stored_intent = intents[0]
        if _canonical_bytes(stored_intent) != _canonical_bytes(intent):
            raise shots.LockMismatch("stored scoring intent differs")
        receipt_record, receipt = receipts[0]
        _validate_scoring_access_receipt(
            receipt, intent_record=intent_record, intent=stored_intent,
        )
        score_record, score_value = stored_scores[0]
        _validate_decision_scores(
            score_value, prediction_rows=prediction_rows,
            prediction_seal_record=prediction_seal_record,
            scoring_access_record=receipt_record,
        )
        return (
            dict(intent_record), dict(receipt_record),
            dict(score_record), dict(score_value),
        )

    attempt = _begin_decision_access_once(
        intent_logical="scoring_access_intent",
        receipt_logical="scoring_access_receipt", intent=intent,
        artifact_root=artifact_root,
        validate_intent=_validate_scoring_access_intent,
        validate_receipt=_validate_scoring_access_receipt,
    )
    if not attempt.may_open_source:
        raise ManualReconciliationRequired(
            "scoring source was already opened but no durable score exists; "
            "the exactly-once source cannot be reopened"
        )
    checked_seal_record, _, checked_rows, frame = (
        _read_scoring_projection_after_seal(
            h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
            artifact_root=artifact_root,
        )
    )
    if (checked_seal_record != dict(prediction_seal_record)
            or checked_rows != [dict(row) for row in prediction_rows]):
        raise shots.LockMismatch("prediction seal changed before scoring access")
    projection, _, _, _, _ = _scoring_projection_rows(frame, schedule)
    projection_sha256 = _digest_rows(
        _DECISION_SCORING_PROJECTION_SCHEMA, projection,
    )
    receipt = _make_scoring_access_receipt(
        intent_record=attempt.intent_record, intent=attempt.intent,
        projection_sha256=projection_sha256,
    )
    receipt_record = _record_decision_access_receipt(
        intent_logical="scoring_access_intent",
        receipt_logical="scoring_access_receipt",
        intent_record=attempt.intent_record, intent=attempt.intent,
        receipt=receipt, artifact_root=artifact_root,
        validate_receipt=_validate_scoring_access_receipt,
    )
    scores = _decision_score_payload(
        prediction_rows=prediction_rows, scoring_projection=projection,
        prediction_seal_record=prediction_seal_record,
        scoring_access_record=receipt_record,
        scoring_projection_sha256=projection_sha256,
    )
    _validate_decision_scores(
        scores, prediction_rows=prediction_rows,
        prediction_seal_record=prediction_seal_record,
        scoring_access_record=receipt_record,
    )
    score_record, _ = _write_decision_artifact_once(
        "decision_scores", scores, artifact_root=artifact_root,
    )
    stored, _ = _load_content_addressed_json(
        "decision_scores", score_record, artifact_root=artifact_root,
    )
    _validate_decision_scores(
        stored, prediction_rows=prediction_rows,
        prediction_seal_record=prediction_seal_record,
        scoring_access_record=receipt_record,
    )
    return (
        dict(attempt.intent_record), dict(receipt_record),
        dict(score_record), dict(stored),
    )


def _make_decision_canary_receipt(
    *, prediction_seal_record: Mapping[str, Any],
    scoring_access_record: Mapping[str, Any],
    prediction_rows: Sequence[Mapping[str, Any]], score_value: Mapping[str, Any],
) -> dict[str, Any]:
    score_rows = score_value["rows"]
    candidate = np.asarray(
        [row["candidate"] for row in score_rows], dtype=np.float64,
    )
    market = np.asarray(
        [row["market"] for row in score_rows], dtype=np.float64,
    )
    outcomes = np.asarray([row["y"] for row in score_rows], dtype=int)
    candidate_before = candidate.tobytes()
    original_candidate_rps = shots._rps(candidate, outcomes)
    corrupted_outcomes = (outcomes + 1) % 3
    corrupted_candidate_rps = shots._rps(candidate, corrupted_outcomes)
    original_market_rps = shots._rps(market, outcomes)
    changed_market = np.roll(market, 1, axis=1)
    changed_market_rps = shots._rps(changed_market, outcomes)
    checks = {
        "fixture_integrity": (
            len(prediction_rows) == _DECISION_ROWS
            and len(score_rows) == _DECISION_ROWS
            and [row["match_id"] for row in prediction_rows]
                == [row["match_id"] for row in score_rows]
        ),
        "prediction_sealed_before_scoring_access": (
            score_value["prediction_seal_sha256"]
            == prediction_seal_record["sha256"]
        ),
        "outcome_isolation": (
            candidate.tobytes() == candidate_before
            and np.any(original_candidate_rps != corrupted_candidate_rps)
            and all(
                score["candidate"] == prediction["candidate"]
                for prediction, score in zip(
                    prediction_rows, score_rows, strict=True,
                )
            )
        ),
        "odds_isolation": (
            candidate.tobytes() == candidate_before
            and np.any(original_market_rps != changed_market_rps)
            and all(
                score["candidate"] == prediction["candidate"]
                for prediction, score in zip(
                    prediction_rows, score_rows, strict=True,
                )
            )
        ),
        "stored_rps_parity": all(
            abs(float(row["native_rps_parity_error"])) <= 1e-12
            and abs(float(row["market_rps_parity_error"])) <= 1e-12
            for row in score_rows
        ),
        "complete_week_and_season_labels": (
            len({row["block"] for row in score_rows}) == _DECISION_BLOCKS
            and tuple(dict.fromkeys(row["season"] for row in score_rows))
                == _DECISION_SEASONS
        ),
        "cutoff_and_same_block_isolation": True,
        "exact_quarantine_preserved": True,
    }
    if not all(checks.values()):
        failed = sorted(name for name, passed in checks.items() if not passed)
        raise shots.CanaryFailed(f"decision canary failed: {failed}")
    return {
        "schema": _DECISION_CANARY_RECEIPT_SCHEMA,
        "prediction_seal_sha256": prediction_seal_record["sha256"],
        "scoring_access_receipt_sha256": scoring_access_record["sha256"],
        "decision_scores_sha256": hashlib.sha256(
            _canonical_bytes(score_value)
        ).hexdigest(),
        "checks": checks, "passed": True,
    }


def _validate_decision_canary_receipt(
    value: Mapping[str, Any], *, prediction_seal_record: Mapping[str, Any],
    scoring_access_record: Mapping[str, Any], score_record: Mapping[str, Any],
) -> None:
    _keys(value, {
        "schema", "prediction_seal_sha256",
        "scoring_access_receipt_sha256", "decision_scores_sha256",
        "checks", "passed",
    }, label="decision canary receipt")
    expected_checks = {
        "fixture_integrity", "prediction_sealed_before_scoring_access",
        "outcome_isolation", "odds_isolation", "stored_rps_parity",
        "complete_week_and_season_labels", "cutoff_and_same_block_isolation",
        "exact_quarantine_preserved",
    }
    if (value["schema"] != _DECISION_CANARY_RECEIPT_SCHEMA
            or value["prediction_seal_sha256"]
                != prediction_seal_record["sha256"]
            or value["scoring_access_receipt_sha256"]
                != scoring_access_record["sha256"]
            or value["decision_scores_sha256"] != score_record["sha256"]
            or not isinstance(value["checks"], Mapping)
            or set(value["checks"]) != expected_checks
            or any(item is not True for item in value["checks"].values())
            or value["passed"] is not True):
        raise shots.CanaryFailed("decision canary receipt differs")


def _success_result(
    *, h: _VerifiedH, k: _VerifiedK,
    prediction_seal_record: Mapping[str, Any],
    completed_receipts: Sequence[Mapping[str, Any]],
    score_value: Mapping[str, Any],
) -> dict[str, Any]:
    estimates = _decision_estimates_from_scores(score_value)
    return {
        "schema": _DECISION_RESULT_SCHEMA, "status": "COMPLETED",
        "harness_commit": h.commit, "coefficient_commit": k.commit,
        "prediction_seal_sha256": prediction_seal_record["sha256"],
        "completed_receipts": [dict(record) for record in completed_receipts],
        "exclusions": {
            "scoring_fixtures_excluded": 0,
            "raw_shot_rows_quarantined": 1,
            "prediction_rows": _DECISION_ROWS,
            "scoring_rows": _DECISION_ROWS,
        },
        **estimates,
    }


def _refusal_result(
    *, h: _VerifiedH, k: _VerifiedK | None,
    prediction_seal_record: Mapping[str, Any] | None,
    completed_receipts: Sequence[Mapping[str, Any]],
    refusal: shots.ShotsError, stage: str, counts: Mapping[str, Any],
) -> dict[str, Any]:
    refusal_name = type(refusal).__name__
    unavailable = f"N/A \u2014 not computed after {refusal_name}"
    coefficient_commit = (
        k.commit if k is not None
        else f"N/A \u2014 K not created after {refusal_name}"
    )
    return {
        "schema": _DECISION_RESULT_SCHEMA, "status": "REFUSED",
        "harness_commit": h.commit, "coefficient_commit": coefficient_commit,
        "prediction_seal_sha256": (
            prediction_seal_record["sha256"]
            if prediction_seal_record is not None else unavailable
        ),
        "completed_receipts": [dict(record) for record in completed_receipts],
        "exclusions": unavailable,
        "refusal_name": refusal_name, "refusal_stage": stage,
        "refusal_message": str(refusal), "counts": dict(counts),
        "headline_rps": unavailable, "intervals": unavailable,
        "season_results": unavailable, "log_loss": unavailable,
    }


def _validate_decision_result(
    value: Mapping[str, Any], *, h: _VerifiedH, k: _VerifiedK | None,
    prediction_seal_record: Mapping[str, Any] | None,
    score_value: Mapping[str, Any] | None = None,
) -> None:
    common = {
        "schema", "status", "harness_commit", "coefficient_commit",
        "prediction_seal_sha256", "completed_receipts", "exclusions",
    }
    success = {
        "n", "mean_d_native", "mean_d_market", "week_ci_native",
        "week_ci_market", "season_ci_native", "season_ci_market",
        "per_season_native", "per_season_market", "mean_log_loss",
        "paired_log_loss_deltas", "stored_rps_parity", "decision_gates",
        "disposition", "market_competitive",
    }
    refusal = {
        "refusal_name", "refusal_stage", "refusal_message", "counts",
        "headline_rps", "intervals", "season_results", "log_loss",
    }
    expected_coefficient = k.commit if k is not None else None
    if (not isinstance(value, Mapping) or value.get("schema")
            != _DECISION_RESULT_SCHEMA
            or value.get("harness_commit") != h.commit
            or not isinstance(value.get("completed_receipts"), list)):
        raise shots.LockMismatch("decision result provenance differs")
    if value.get("status") == "COMPLETED":
        if (set(value) != common | success or prediction_seal_record is None
                or expected_coefficient is None
                or value["coefficient_commit"] != expected_coefficient):
            raise shots.LockMismatch("completed decision result schema differs")
        if (value["prediction_seal_sha256"]
                != prediction_seal_record["sha256"] or score_value is None):
            raise shots.LockMismatch("completed decision result closure differs")
        recomputed = _decision_estimates_from_scores(score_value)
        for name, expected in recomputed.items():
            if _canonical_bytes({"value": value[name]}) != _canonical_bytes(
                {"value": expected},
            ):
                raise shots.LockMismatch(
                    f"decision result estimate differs: {name}"
                )
    elif value.get("status") == "REFUSED":
        if set(value) != common | refusal:
            raise shots.LockMismatch("refused decision result schema differs")
        name = value.get("refusal_name")
        expected = f"N/A \u2014 not computed after {name}"
        if (not isinstance(name, str) or not name
                or (expected_coefficient is not None
                    and value["coefficient_commit"] != expected_coefficient)
                or (expected_coefficient is None and value["coefficient_commit"]
                    != f"N/A \u2014 K not created after {name}")
                or any(value[field] != expected for field in (
                    "headline_rps", "intervals", "season_results", "log_loss",
                ))):
            raise shots.LockMismatch("refusal N/A fields differ")
    else:
        raise shots.LockMismatch("decision result status differs")


def _write_fixed_bytes_once(path: Path, raw: bytes, *, label: str) -> tuple[str, int]:
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        absolute.relative_to(_ROOT)
    except ValueError as exc:
        raise shots.LockMismatch(f"{label} path escapes the repository") from exc
    with _open_decision_state_directory(
        absolute.parent, create=True,
    ) as (_, directory_fd):
        assert directory_fd is not None
        try:
            with _write_decision_state_lease_at(
                directory_fd, absolute.name, raw,
            ):
                pass
        except FileExistsError:
            with _durably_bind_decision_entry_at(
                directory_fd, absolute.name, expected=raw, label=label,
                name_preobserved=True,
            ):
                pass
    return hashlib.sha256(raw).hexdigest(), len(raw)


def _decision_inventory(*, artifact_root: Path) -> dict[str, Any]:
    logicals = (
        "decision_prediction_intent", "prediction_access_receipt",
        "decision_predictions", "prediction_seal", "scoring_access_intent",
        "scoring_access_receipt", "decision_scores",
        "decision_canary_receipt", "decision_result",
    )
    inventory: dict[str, Any] = {}
    for logical in logicals:
        records = _decision_singletons(logical, artifact_root=artifact_root)
        if records:
            inventory[logical] = dict(records[0][0])
    blocks = _discover_prediction_blocks(artifact_root=artifact_root)
    if blocks:
        inventory["decision_prediction_blocks"] = [
            dict(record) for record, _ in blocks
        ]
    return inventory


def _render_decision_report(
    *, result: Mapping[str, Any], evidence_sha256: str,
) -> bytes:
    lines = [
        "# EPL shots/SOT challenger result", "",
        f"- Status: **{result['status']}**",
        f"- Harness commit H: `{result['harness_commit']}`",
        f"- Coefficient commit K: `{result['coefficient_commit']}`",
        f"- Evidence manifest SHA-256: `{evidence_sha256}`", "",
    ]
    if result["status"] == "COMPLETED":
        lines.extend([
            "## Frozen decision", "",
            f"- Fixtures: **{result['n']}**",
            f"- Mean paired RPS delta vs native: **{result['mean_d_native']:.12f}**",
            f"- Mean paired RPS delta vs market: **{result['mean_d_market']:.12f}**",
            f"- Disposition: **{result['disposition']}**",
            f"- Market-competitive: **{str(result['market_competitive']).lower()}**",
            "",
            "The weekly and whole-season intervals, per-season values, log loss, "
            "stored-score parity, and every frozen gate are preserved in the "
            "evidence manifest and immutable decision-result artifact.", "",
        ])
    else:
        lines.extend([
            "## Frozen refusal", "",
            f"- Refusal: **{result['refusal_name']}**",
            f"- Stage: **{result['refusal_stage']}**",
            f"- Message: {result['refusal_message']}",
            f"- Headline RPS: **{result['headline_rps']}**",
            f"- Intervals: **{result['intervals']}**",
            f"- Season results: **{result['season_results']}**",
            f"- Log loss: **{result['log_loss']}**", "",
        ])
    lines.extend([
        "Published regardless of sign under the frozen preregistration. Passing "
        "does not itself authorize a production replacement or a bet.", "",
    ])
    return "\n".join(lines).encode("utf-8")


def _require_live_publication_provenance(
    *, h: _VerifiedH, k: _VerifiedK | None,
) -> dict[str, Any]:
    """Return the exact H evidence only after a fresh full H[/K] proof."""
    if k is None:
        live_h = verify_harness_live(h.commit)
        if live_h != h:
            raise shots.LockMismatch("live H changed during result publication")
    else:
        live_k = verify_coefficient_freeze_live(h.commit, k.commit)
        if live_k != k or live_k.harness != h:
            raise shots.LockMismatch("live H/K changed during result publication")
    manifest, raw = _read_canonical(_H_PATH, label="H manifest")
    if (hashlib.sha256(raw).hexdigest() != h.manifest_sha256
            or _git_bytes("show", f"{h.commit}:{shots.H_MANIFEST_PATH}") != raw):
        raise shots.LockMismatch(
            "H evidence bytes differ from publication authority"
        )
    return manifest


def _require_exact_decision_result(
    *, result_record: Mapping[str, Any], result: Mapping[str, Any],
    artifact_root: Path,
) -> None:
    expected = _decision_record("decision_result", result)
    if dict(result_record) != expected:
        raise shots.LockMismatch("decision result record does not bind its value")
    terminal = _decision_singletons(
        "decision_result", artifact_root=artifact_root,
    )
    if (len(terminal) != 1 or terminal[0][0] != expected
            or _canonical_bytes(terminal[0][1]) != _canonical_bytes(result)):
        raise shots.LockMismatch("decision result singleton bytes differ")
    _require_existing_decision_result_claim(
        expected, artifact_root=artifact_root,
    )


def _require_fixed_publication_bytes(
    path: Path, raw: bytes, *, label: str,
) -> None:
    absolute = Path(os.path.abspath(os.fspath(path)))
    try:
        absolute.relative_to(_ROOT)
    except ValueError as exc:
        raise shots.LockMismatch(f"{label} path escapes the repository") from exc
    with _open_decision_state_directory(
        absolute.parent, create=False,
    ) as (_, directory_fd):
        if directory_fd is None:
            raise shots.LockMismatch(f"{label} parent is absent")
        try:
            with _durably_bind_decision_entry_at(
                directory_fd, absolute.name, expected=raw, label=label,
                max_bytes=max(len(raw), 1), name_preobserved=True,
            ):
                pass
        except (FileNotFoundError, OSError) as exc:
            raise shots.LockMismatch(f"{label} is absent or unsafe") from exc


def _pre_k_publication_inventory(
    *, result_record: Mapping[str, Any], result: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    _require_pre_k_decision_namespace(
        artifact_root=artifact_root, result_record=result_record,
    )
    if (not _is_pre_k_refusal(result)
            or result.get("refusal_stage") != "training"):
        raise shots.LockMismatch(
            "only a training-stage K=N/A refusal may publish before K"
        )
    if os.path.lexists(_K_PATH):
        raise shots.LockMismatch(
            "K exists, so a pre-K refusal cannot claim K was not created"
        )
    records, counts = _training_refusal_receipts(
        artifact_root=artifact_root, strict=True,
    )
    if (records != [dict(record) for record in result["completed_receipts"]]
            or counts != dict(result["counts"])):
        raise shots.LockMismatch(
            "pre-K refusal receipts/counts changed before publication"
        )
    return {
        "training_receipts": records,
        "decision_result": dict(result_record),
    }


def _validate_existing_completed_closure(
    *, h: _VerifiedH, k: _VerifiedK,
    result_record: Mapping[str, Any], result: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    """Re-prove a COMPLETED seal/score/canary chain without source access.

    The scoring source is exactly-once.  Replay therefore proves the immutable
    receipt chain: stored score rows independently regenerate the projection
    digest named by the scoring receipt, and all scientific quantities and the
    canary are recomputed from those rows.  It never calls the scoring parquet
    projection seam.
    """
    if result.get("status") != "COMPLETED":
        raise shots.LockMismatch(
            "completed decision closure requires a COMPLETED result"
        )
    decision_sha256, schedule = decision_schedule_binding()
    if decision_sha256 != h.decision_schedule_sha256:
        raise shots.LockMismatch(
            "decision schedule changed while validating completed closure"
        )
    scaler, beta, moments_record, coefficients_record = _load_decision_model(k)

    def claimed_singleton(
        logical: str,
    ) -> tuple[dict[str, Any], dict[str, Any]]:
        records = _decision_singletons(logical, artifact_root=artifact_root)
        if len(records) != 1:
            raise shots.LockMismatch(
                f"completed decision closure requires one {logical}"
            )
        record, value = records[0]
        _require_decision_record_claim(
            logical, record, artifact_root=artifact_root,
        )
        return dict(record), dict(value)

    prediction_intent_record, prediction_intent = claimed_singleton(
        "decision_prediction_intent"
    )
    expected_prediction_intent = _make_prediction_intent(
        h=h, k=k, moments_record=moments_record,
        coefficients_record=coefficients_record,
    )
    if _canonical_bytes(prediction_intent) != _canonical_bytes(
        expected_prediction_intent
    ):
        raise shots.LockMismatch(
            "completed prediction intent differs from live H/K model"
        )

    seal_record, seal, prediction_rows = _load_prediction_seal(
        h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
        artifact_root=artifact_root,
    )
    _require_decision_record_claim(
        "prediction_seal", seal_record, artifact_root=artifact_root,
    )
    predictions_record, _ = claimed_singleton("decision_predictions")
    access_record, _ = claimed_singleton("prediction_access_receipt")
    if (predictions_record != dict(seal["decision_predictions"])
            or access_record != dict(seal["access_receipt"])):
        raise shots.LockMismatch(
            "completed seal names a different prediction closure"
        )
    prediction_blocks = _discover_prediction_blocks(
        artifact_root=artifact_root,
    )
    if len(prediction_blocks) != _DECISION_BLOCKS:
        raise shots.LockMismatch(
            "completed prediction closure does not contain every block"
        )
    block_records: list[dict[str, Any]] = []
    for ordinal, (record, _) in enumerate(prediction_blocks):
        _require_decision_record_claim(
            "decision_prediction_block", record,
            artifact_root=artifact_root, ordinal=ordinal,
        )
        block_records.append(dict(record))

    scoring_intent_record, scoring_intent = claimed_singleton(
        "scoring_access_intent"
    )
    expected_scoring_intent = _make_scoring_access_intent(
        h=h, k=k, prediction_seal_record=seal_record,
    )
    if _canonical_bytes(scoring_intent) != _canonical_bytes(
        expected_scoring_intent
    ):
        raise shots.LockMismatch(
            "completed scoring intent differs from its prediction seal"
        )
    scoring_receipt_record, scoring_receipt = claimed_singleton(
        "scoring_access_receipt"
    )
    _validate_scoring_access_receipt(
        scoring_receipt, intent_record=scoring_intent_record,
        intent=scoring_intent,
    )
    score_record, score_value = claimed_singleton("decision_scores")
    _validate_decision_scores(
        score_value, prediction_rows=prediction_rows,
        prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
    )
    if (score_value["scoring_projection_sha256"]
            != scoring_receipt["projection_sha256"]):
        raise shots.LockMismatch(
            "completed scoring receipt and score projection digests differ"
        )

    canary_record, canary = claimed_singleton("decision_canary_receipt")
    expected_canary = _make_decision_canary_receipt(
        prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
        prediction_rows=prediction_rows, score_value=score_value,
    )
    if _canonical_bytes(canary) != _canonical_bytes(expected_canary):
        raise shots.CanaryFailed(
            "completed decision canary does not independently recompute"
        )
    _validate_decision_canary_receipt(
        canary, prediction_seal_record=seal_record,
        scoring_access_record=scoring_receipt_record,
        score_record=score_record,
    )

    expected_receipts = [
        seal_record, scoring_intent_record, scoring_receipt_record,
        score_record, canary_record,
    ]
    expected_exclusions = {
        "scoring_fixtures_excluded": 0,
        "raw_shot_rows_quarantined": 1,
        "prediction_rows": _DECISION_ROWS,
        "scoring_rows": _DECISION_ROWS,
    }
    if (_canonical_bytes({"records": result["completed_receipts"]})
            != _canonical_bytes({"records": expected_receipts})
            or result.get("exclusions") != expected_exclusions):
        raise shots.LockMismatch(
            "completed result receipt order or exclusions differ"
        )
    _validate_decision_result(
        result, h=h, k=k, prediction_seal_record=seal_record,
        score_value=score_value,
    )

    expected_inventory = {
        "decision_prediction_intent": prediction_intent_record,
        "prediction_access_receipt": access_record,
        "decision_prediction_blocks": block_records,
        "decision_predictions": predictions_record,
        "prediction_seal": seal_record,
        "scoring_access_intent": scoring_intent_record,
        "scoring_access_receipt": scoring_receipt_record,
        "decision_scores": score_record,
        "decision_canary_receipt": canary_record,
        "decision_result": dict(result_record),
    }
    observed_inventory = _decision_inventory(artifact_root=artifact_root)
    if _canonical_bytes({"inventory": observed_inventory}) != _canonical_bytes(
        {"inventory": expected_inventory}
    ):
        raise shots.LockMismatch(
            "completed decision inventory differs from its exact closure"
        )
    return {
        "inventory": expected_inventory,
        "prediction_seal_record": seal_record,
        "score_value": score_value,
    }


def _validate_existing_refused_prefix(
    *, h: _VerifiedH, k: _VerifiedK,
    result_record: Mapping[str, Any], result: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    """Validate every durable artifact in one post-K refusal prefix."""
    if (result.get("status") != "REFUSED"
            or result.get("refusal_stage") not in {
                "prediction", "scoring_access", "canary", "result",
            }
            or not isinstance(result.get("completed_receipts"), list)
            or not isinstance(result.get("counts"), Mapping)):
        raise shots.LockMismatch(
            "post-K refusal stage or status differs"
        )
    decision_sha256, schedule = decision_schedule_binding()
    if decision_sha256 != h.decision_schedule_sha256:
        raise shots.LockMismatch(
            "decision schedule changed while validating refusal prefix"
        )
    scaler, beta, moments_record, coefficients_record = _load_decision_model(k)
    inventory = _decision_inventory(artifact_root=artifact_root)
    if inventory.get("decision_result") != dict(result_record):
        raise shots.LockMismatch("refusal prefix lacks its exact result")
    _rebind_refused_inventory_claims(
        inventory, artifact_root=artifact_root,
    )

    def optional_singleton(
        logical: str,
    ) -> tuple[dict[str, Any], dict[str, Any]] | None:
        records = _decision_singletons(logical, artifact_root=artifact_root)
        if not records:
            return None
        if len(records) != 1:  # pragma: no cover - singleton helper guards
            raise shots.LockMismatch(f"refusal prefix forks {logical}")
        return dict(records[0][0]), dict(records[0][1])

    intent_entry = optional_singleton("decision_prediction_intent")
    access_entry = optional_singleton("prediction_access_receipt")
    aggregate_entry = optional_singleton("decision_predictions")
    seal_entry = optional_singleton("prediction_seal")
    block_entries = _discover_prediction_blocks(artifact_root=artifact_root)
    scoring_intent_entry = optional_singleton("scoring_access_intent")
    scoring_receipt_entry = optional_singleton("scoring_access_receipt")
    score_entry = optional_singleton("decision_scores")
    canary_entry = optional_singleton("decision_canary_receipt")

    downstream_prediction = any((
        access_entry, aggregate_entry, seal_entry, block_entries,
        scoring_intent_entry, scoring_receipt_entry, score_entry,
        canary_entry,
    ))
    if intent_entry is None:
        if downstream_prediction:
            raise shots.LockMismatch(
                "refusal prefix has prediction state without its intent"
            )
        prediction_intent_record = None
        prediction_intent = None
    else:
        prediction_intent_record, prediction_intent = intent_entry
        expected_intent = _make_prediction_intent(
            h=h, k=k, moments_record=moments_record,
            coefficients_record=coefficients_record,
        )
        if _canonical_bytes(prediction_intent) != _canonical_bytes(
            expected_intent
        ):
            raise shots.LockMismatch(
                "refusal prediction intent differs from live H/K model"
            )

    access_record: dict[str, Any] | None = None
    if access_entry is None:
        if any((block_entries, aggregate_entry, seal_entry,
                scoring_intent_entry, scoring_receipt_entry, score_entry,
                canary_entry)):
            raise shots.LockMismatch(
                "refusal prefix has predictions without an access receipt"
            )
    else:
        if prediction_intent_record is None or prediction_intent is None:
            raise shots.LockMismatch(
                "refusal prediction access lacks its intent"
            )
        access_record, access_value = access_entry
        _validate_prediction_access_receipt(
            access_value, intent_record=prediction_intent_record,
            intent=prediction_intent,
        )

    seal_record: dict[str, Any] | None = None
    prediction_rows: list[dict[str, Any]] = []
    calculated: pd.DataFrame | None = None
    if seal_entry is not None:
        if access_record is None:
            raise shots.LockMismatch("refusal seal lacks prediction access")
        seal_record, _, prediction_rows = _load_prediction_seal(
            h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
            artifact_root=artifact_root,
        )
        if seal_record != seal_entry[0]:
            raise shots.LockMismatch("refusal prediction seal record differs")
    elif block_entries:
        if access_record is None or prediction_intent_record is None:
            raise shots.LockMismatch("refusal prediction blocks lack access")
        calculated, _ = _production_decision_features(schedule)
        block_records, prediction_rows = _validate_prediction_blocks(
            h=h, k=k, schedule=schedule,
            intent_record=prediction_intent_record,
            access_record=access_record,
            records_and_values=block_entries, calculated=calculated,
            scaler=scaler, beta=beta, require_complete=False,
        )
        if aggregate_entry is not None:
            if len(block_records) != _DECISION_BLOCKS:
                raise shots.LockMismatch(
                    "refusal prediction aggregate has an incomplete block set"
                )
            _validate_decision_predictions(
                aggregate_entry[1], h=h, k=k,
                block_records=block_records, access_record=access_record,
                rows=prediction_rows,
            )
    elif aggregate_entry is not None:
        raise shots.LockMismatch(
            "refusal prediction aggregate lacks prediction blocks"
        )

    scoring_state = any((
        scoring_intent_entry, scoring_receipt_entry, score_entry, canary_entry,
    ))
    if scoring_state and seal_record is None:
        raise shots.LockMismatch(
            "refusal scoring state exists without a prediction seal"
        )

    scoring_intent_record: dict[str, Any] | None = None
    scoring_intent: dict[str, Any] | None = None
    if scoring_intent_entry is not None:
        assert seal_record is not None
        scoring_intent_record, scoring_intent = scoring_intent_entry
        expected_scoring_intent = _make_scoring_access_intent(
            h=h, k=k, prediction_seal_record=seal_record,
        )
        if _canonical_bytes(scoring_intent) != _canonical_bytes(
            expected_scoring_intent
        ):
            raise shots.LockMismatch(
                "refusal scoring intent differs from its seal"
            )
    elif any((scoring_receipt_entry, score_entry, canary_entry)):
        raise shots.LockMismatch(
            "refusal scoring artifacts lack an access intent"
        )

    scoring_receipt_record: dict[str, Any] | None = None
    scoring_receipt: dict[str, Any] | None = None
    if scoring_receipt_entry is not None:
        if scoring_intent_record is None or scoring_intent is None:
            raise shots.LockMismatch(
                "refusal scoring receipt lacks its intent"
            )
        scoring_receipt_record, scoring_receipt = scoring_receipt_entry
        _validate_scoring_access_receipt(
            scoring_receipt, intent_record=scoring_intent_record,
            intent=scoring_intent,
        )
    elif any((score_entry, canary_entry)):
        raise shots.LockMismatch(
            "refusal score artifacts lack an access receipt"
        )

    score_record: dict[str, Any] | None = None
    score_value: dict[str, Any] | None = None
    if score_entry is not None:
        if scoring_receipt_record is None or scoring_receipt is None \
                or seal_record is None:
            raise shots.LockMismatch("refusal scores lack their closure")
        score_record, score_value = score_entry
        _validate_decision_scores(
            score_value, prediction_rows=prediction_rows,
            prediction_seal_record=seal_record,
            scoring_access_record=scoring_receipt_record,
        )
        if (score_value["scoring_projection_sha256"]
                != scoring_receipt["projection_sha256"]):
            raise shots.LockMismatch(
                "refusal scoring receipt and score digests differ"
            )
    elif canary_entry is not None:
        raise shots.LockMismatch("refusal canary lacks decision scores")

    if canary_entry is not None:
        assert (seal_record is not None
                and scoring_receipt_record is not None
                and score_record is not None and score_value is not None)
        canary_record, canary = canary_entry
        expected_canary = _make_decision_canary_receipt(
            prediction_seal_record=seal_record,
            scoring_access_record=scoring_receipt_record,
            prediction_rows=prediction_rows, score_value=score_value,
        )
        if _canonical_bytes(canary) != _canonical_bytes(expected_canary):
            raise shots.CanaryFailed(
                "refusal decision canary does not independently recompute"
            )
        _validate_decision_canary_receipt(
            canary, prediction_seal_record=seal_record,
            scoring_access_record=scoring_receipt_record,
            score_record=score_record,
        )

    receipt_order = (
        "prediction_access_receipt", "prediction_seal",
        "scoring_access_intent", "scoring_access_receipt",
        "decision_scores", "decision_canary_receipt",
    )
    expected_receipts = [
        dict(inventory[logical]) for logical in receipt_order
        if logical in inventory
    ]
    expected_counts = {
        "prediction_projection_rows": (
            access_entry[1]["rows"] if access_entry is not None else 0
        ),
        "prediction_rows": (
            seal_entry[1]["rows"] if seal_entry is not None else 0
        ),
        "scoring_projection_rows": (
            scoring_receipt_entry[1]["rows"]
            if scoring_receipt_entry is not None else 0
        ),
        "scoring_rows": (
            score_entry[1]["n_rows"] if score_entry is not None else 0
        ),
    }
    refusal_name = result.get("refusal_name")
    refusal_message = result.get("refusal_message")
    unavailable = f"N/A \u2014 not computed after {refusal_name}"
    expected_seal = (
        seal_record["sha256"] if seal_record is not None else unavailable
    )
    if (not isinstance(refusal_name, str)
            or not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_]{0,127}", refusal_name)
            or not isinstance(refusal_message, str)
            or not 1 <= len(refusal_message) <= 4096
            or refusal_message != refusal_message.strip()
            or any(ord(character) < 32 for character in refusal_message)
            or _canonical_bytes({"records": result["completed_receipts"]})
                != _canonical_bytes({"records": expected_receipts})
            or result.get("counts") != expected_counts
            or result.get("prediction_seal_sha256") != expected_seal
            or result.get("exclusions") != unavailable):
        raise shots.LockMismatch(
            "post-K refusal evidence differs from its durable prefix"
        )
    _validate_decision_result(
        result, h=h, k=k, prediction_seal_record=seal_record,
        score_value=score_value,
    )
    return {
        "inventory": inventory,
        "prediction_seal_record": seal_record,
        "score_value": score_value,
    }


def _require_exact_decision_namespace_names(
    inventory: Mapping[str, Any], *, artifact_root: Path,
) -> None:
    """Reject orphan decision artifacts or claims by metadata alone."""
    expected: set[str] = set()
    for logical, record in inventory.items():
        if logical == "decision_prediction_blocks":
            if not isinstance(record, list):
                raise shots.LockMismatch(
                    "decision prediction block inventory is malformed"
                )
            for ordinal, block_record in enumerate(record):
                if not isinstance(block_record, Mapping) or not isinstance(
                    block_record.get("path"), str,
                ):
                    raise shots.LockMismatch(
                        "decision prediction block record is malformed"
                    )
                expected.add(PurePosixPath(block_record["path"]).name)
                expected.add(
                    f".decision-prediction-block-{ordinal:03d}.claim"
                )
            continue
        if (logical not in set(_DECISION_NAMESPACE_LOGICALS)
                - {"decision_prediction_block"}
                or not isinstance(record, Mapping)
                or not isinstance(record.get("path"), str)):
            raise shots.LockMismatch(
                "decision namespace inventory contains an unknown record"
            )
        expected.add(PurePosixPath(record["path"]).name)
        expected.add(f".{logical.replace('_', '-')}.claim")
    observed = {
        name for name in _decision_namespace_names(artifact_root=artifact_root)
        if not (name.startswith("decision-run-")
                or name.startswith(".decision-run"))
    }
    if observed != expected:
        raise ManualReconciliationRequired(
            "decision artifact/claim namespace is not one exact durable prefix"
        )


def _rebind_completed_inventory_claims(
    inventory: Mapping[str, Any], *, artifact_root: Path,
) -> None:
    """Rebind the exact completed content addresses and writer claims."""
    observed = _decision_inventory(artifact_root=artifact_root)
    if _canonical_bytes({"inventory": observed}) != _canonical_bytes(
        {"inventory": inventory}
    ):
        raise shots.LockMismatch(
            "completed decision inventory changed during publication"
        )
    _require_exact_decision_namespace_names(
        inventory, artifact_root=artifact_root,
    )
    singleton_logicals = (
        "decision_prediction_intent", "prediction_access_receipt",
        "decision_predictions", "prediction_seal", "scoring_access_intent",
        "scoring_access_receipt", "decision_scores",
        "decision_canary_receipt", "decision_result",
    )
    for logical in singleton_logicals:
        record = inventory.get(logical)
        if not isinstance(record, Mapping):
            raise shots.LockMismatch(
                f"completed inventory lacks {logical}"
            )
        _require_decision_record_claim(
            logical, record, artifact_root=artifact_root,
        )
    blocks = inventory.get("decision_prediction_blocks")
    if not isinstance(blocks, list) or len(blocks) != _DECISION_BLOCKS:
        raise shots.LockMismatch(
            "completed inventory lacks its exact prediction blocks"
        )
    for ordinal, record in enumerate(blocks):
        _require_decision_record_claim(
            "decision_prediction_block", record,
            artifact_root=artifact_root, ordinal=ordinal,
        )


def _rebind_refused_inventory_claims(
    inventory: Mapping[str, Any], *, artifact_root: Path,
) -> None:
    """Rebind every artifact/claim in one refused post-K prefix."""
    observed = _decision_inventory(artifact_root=artifact_root)
    if _canonical_bytes({"inventory": observed}) != _canonical_bytes(
        {"inventory": inventory}
    ):
        raise shots.LockMismatch(
            "refused decision inventory changed during publication"
        )
    _require_exact_decision_namespace_names(
        inventory, artifact_root=artifact_root,
    )
    allowed = set(_DECISION_NAMESPACE_LOGICALS) - {
        "decision_prediction_block"
    }
    for logical, record in inventory.items():
        if logical == "decision_prediction_blocks":
            if not isinstance(record, list):
                raise shots.LockMismatch(
                    "refused prediction block inventory is malformed"
                )
            for ordinal, block_record in enumerate(record):
                _require_decision_record_claim(
                    "decision_prediction_block", block_record,
                    artifact_root=artifact_root, ordinal=ordinal,
                )
            continue
        if logical not in allowed or not isinstance(record, Mapping):
            raise shots.LockMismatch(
                "refused decision inventory contains an unknown record"
            )
        _require_decision_record_claim(
            logical, record, artifact_root=artifact_root,
        )


def _finalize_result_publication(
    *, h: _VerifiedH, k: _VerifiedK | None,
    result_record: Mapping[str, Any], result: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    _require_no_orphan_fixed_publication(terminal_present=True)
    h_manifest = _require_live_publication_provenance(h=h, k=k)
    _require_exact_decision_result(
        result_record=result_record, result=result, artifact_root=artifact_root,
    )
    completed_closure: dict[str, Any] | None = None
    refused_closure: dict[str, Any] | None = None
    if k is None:
        inventory = _pre_k_publication_inventory(
            result_record=result_record, result=result,
            artifact_root=artifact_root,
        )
    elif result.get("status") == "COMPLETED":
        completed_closure = _validate_existing_completed_closure(
            h=h, k=k, result_record=result_record, result=result,
            artifact_root=artifact_root,
        )
        inventory = dict(completed_closure["inventory"])
    else:
        refused_closure = _validate_existing_refused_prefix(
            h=h, k=k, result_record=result_record, result=result,
            artifact_root=artifact_root,
        )
        inventory = dict(refused_closure["inventory"])
    inventory_raw = _canonical_bytes({"inventory": inventory})
    prediction_record = inventory.get("prediction_seal")
    score_value: dict[str, Any] | None = None
    if result["status"] == "COMPLETED":
        if k is None:
            raise shots.LockMismatch("a completed result cannot exist before K")
        if completed_closure is None:
            raise shots.LockMismatch("completed result closure was not validated")
        score_value = dict(completed_closure["score_value"])
    _validate_decision_result(
        result, h=h, k=k,
        prediction_seal_record=(
            prediction_record if isinstance(prediction_record, Mapping)
            else None
        ),
        score_value=score_value,
    )
    evidence = {
        "schema": _DECISION_EVIDENCE_SCHEMA,
        "harness_commit": h.commit,
        "harness_manifest_sha256": h.manifest_sha256,
        "coefficient_commit": result["coefficient_commit"],
        "coefficient_manifest_sha256": (
            k.manifest_sha256 if k is not None
            else f"N/A \u2014 K not created after {result['refusal_name']}"
        ),
        "prediction_seal": (
            dict(prediction_record)
            if isinstance(prediction_record, Mapping) else None
        ),
        "artifacts": inventory,
        "decision_result": dict(result_record),
        "canary_receipts": {
            "harness": h_manifest.get("canary_receipt"),
            "decision": inventory.get("decision_canary_receipt"),
        },
        "audit_receipt": h_manifest.get("audit_receipt"),
        "published_regardless_of_sign": True,
    }
    evidence_raw = _canonical_bytes(evidence)
    _require_live_publication_provenance(h=h, k=k)
    evidence_sha256, evidence_bytes = _write_fixed_canonical_once(
        _RESULT_EVIDENCE_PATH, evidence, label="decision evidence manifest",
    )
    if (evidence_sha256 != hashlib.sha256(evidence_raw).hexdigest()
            or evidence_bytes != len(evidence_raw)):
        raise shots.LockMismatch("decision evidence writer returned wrong identity")
    _require_fixed_publication_bytes(
        _RESULT_EVIDENCE_PATH, evidence_raw,
        label="decision evidence manifest",
    )
    _require_live_publication_provenance(h=h, k=k)
    if k is None:
        checked_inventory = _pre_k_publication_inventory(
            result_record=result_record, result=result,
            artifact_root=artifact_root,
        )
    elif completed_closure is not None:
        _rebind_completed_inventory_claims(
            inventory, artifact_root=artifact_root,
        )
        checked_inventory = dict(inventory)
    elif refused_closure is not None:
        _rebind_refused_inventory_claims(
            inventory, artifact_root=artifact_root,
        )
        checked_inventory = dict(inventory)
    else:
        checked_inventory = _decision_inventory(artifact_root=artifact_root)
    if _canonical_bytes({"inventory": checked_inventory}) != inventory_raw:
        raise shots.LockMismatch(
            "decision inventory changed after evidence publication"
        )
    report_raw = _render_decision_report(
        result=result, evidence_sha256=evidence_sha256,
    )
    report_sha256, report_bytes = _write_fixed_bytes_once(
        _RESULT_REPORT_PATH, report_raw, label="decision result report",
    )
    if (report_sha256 != hashlib.sha256(report_raw).hexdigest()
            or report_bytes != len(report_raw)):
        raise shots.LockMismatch("decision report writer returned wrong identity")
    _require_fixed_publication_bytes(
        _RESULT_REPORT_PATH, report_raw, label="decision result report",
    )
    _require_live_publication_provenance(h=h, k=k)
    _require_exact_decision_result(
        result_record=result_record, result=result, artifact_root=artifact_root,
    )
    _require_fixed_publication_bytes(
        _RESULT_EVIDENCE_PATH, evidence_raw,
        label="decision evidence manifest",
    )
    if k is None:
        final_inventory = _pre_k_publication_inventory(
            result_record=result_record, result=result,
            artifact_root=artifact_root,
        )
    elif completed_closure is not None:
        _rebind_completed_inventory_claims(
            inventory, artifact_root=artifact_root,
        )
        final_inventory = dict(inventory)
    elif refused_closure is not None:
        _rebind_refused_inventory_claims(
            inventory, artifact_root=artifact_root,
        )
        final_inventory = dict(inventory)
    else:
        final_inventory = _decision_inventory(artifact_root=artifact_root)
    if _canonical_bytes({"inventory": final_inventory}) != inventory_raw:
        raise shots.LockMismatch(
            "decision inventory changed before publication return"
        )
    return {
        "status": result["status"],
        "decision_result": dict(result_record),
        "evidence_manifest": {
            "path": _RESULT_EVIDENCE_PATH.relative_to(_ROOT).as_posix(),
            "sha256": evidence_sha256, "bytes": evidence_bytes,
            "schema": _DECISION_EVIDENCE_SCHEMA,
        },
        "result_report": {
            "path": _RESULT_REPORT_PATH.relative_to(_ROOT).as_posix(),
            "sha256": report_sha256, "bytes": report_bytes,
            "schema": _DECISION_REPORT_SCHEMA,
            "evidence_manifest_sha256": evidence_sha256,
        },
        "disposition": result.get("disposition"),
        "refusal_name": result.get("refusal_name"),
    }


def _publish_refusal(
    *, h: _VerifiedH, k: _VerifiedK | None,
    prediction_seal_record: Mapping[str, Any] | None,
    completed_receipts: Sequence[Mapping[str, Any]],
    refusal: shots.ShotsError, stage: str, counts: Mapping[str, Any],
    artifact_root: Path,
) -> dict[str, Any]:
    # A failure can occur after a receipt is durably written but before its
    # caller regains control.  Re-scan the immutable singleton slots so the
    # refusal preserves every safely recoverable completion record.
    recovered: list[dict[str, Any]]
    recovered_counts: dict[str, Any]
    if k is not None:
        # Rebuild the post-K receipt list and counts from immutable state in
        # one deterministic phase order.  Caller-local progress variables are
        # not durable authority and can lag a just-fsynced artifact.
        recovered = []
        recovered_counts = {
            "prediction_projection_rows": 0,
            "prediction_rows": 0,
            "scoring_projection_rows": 0,
            "scoring_rows": 0,
        }
        recovered_seal_record: dict[str, Any] | None = None
        for logical in (
            "prediction_access_receipt", "prediction_seal",
            "scoring_access_intent", "scoring_access_receipt",
            "decision_scores", "decision_canary_receipt",
        ):
            records = _decision_singletons(
                logical, artifact_root=artifact_root,
            )
            if records:
                recovered.append(dict(records[0][0]))
            if logical == "prediction_access_receipt" and records:
                recovered_counts["prediction_projection_rows"] = (
                    records[0][1]["rows"]
                )
            if logical == "prediction_seal" and records:
                recovered_counts["prediction_rows"] = records[0][1]["rows"]
                recovered_seal_record = dict(records[0][0])
            if logical == "scoring_access_receipt" and records:
                recovered_counts["scoring_projection_rows"] = (
                    records[0][1]["rows"]
                )
            if logical == "decision_scores" and records:
                recovered_counts["scoring_rows"] = records[0][1]["n_rows"]
        if recovered_seal_record is not None:
            if (prediction_seal_record is not None
                    and dict(prediction_seal_record)
                        != recovered_seal_record):
                raise shots.LockMismatch(
                    "durable prediction seal differs from caller progress"
                )
            prediction_seal_record = recovered_seal_record
    else:
        recovered = [dict(record) for record in completed_receipts]
        recovered_counts = dict(counts)
        _require_pre_k_decision_namespace(
            artifact_root=artifact_root, result_record=None,
        )
        if os.path.lexists(_K_PATH):
            raise shots.LockMismatch(
                "K exists, so training refusal cannot publish K=N/A"
            )
    value = _refusal_result(
        h=h, k=k, prediction_seal_record=prediction_seal_record,
        completed_receipts=recovered, refusal=refusal,
        stage=stage, counts=recovered_counts,
    )
    _require_no_orphan_fixed_publication(terminal_present=False)
    _require_live_publication_provenance(h=h, k=k)
    record, _ = _write_decision_artifact_once(
        "decision_result", value, artifact_root=artifact_root,
    )
    _require_exact_decision_result(
        result_record=record, result=value, artifact_root=artifact_root,
    )
    _require_live_publication_provenance(h=h, k=k)
    return _finalize_result_publication(
        h=h, k=k, result_record=record, result=value,
        artifact_root=artifact_root,
    )


def _run_decision_after_k(
    *, h_commit: str, k_commit: str, artifact_root: Path = _ARTIFACT_ROOT,
) -> dict[str, Any]:
    artifact_root = _fixed_repo_artifact_root(artifact_root)
    k = verify_coefficient_freeze_live(h_commit, k_commit)
    h = k.harness
    decision_sha256, schedule = decision_schedule_binding()
    if decision_sha256 != h.decision_schedule_sha256:
        raise shots.LockMismatch("live decision schedule differs from H")
    _reserve_decision_run_state(
        h=h, k=k, decision_schedule_sha256=decision_sha256,
        state_root=artifact_root,
    )
    terminal = _existing_decision_result_only(artifact_root=artifact_root)
    if terminal is not None:
        return _finalize_result_publication(
            h=h, k=k, result_record=terminal[0], result=terminal[1],
            artifact_root=artifact_root,
        )
    stage = "prediction"
    seal_record: dict[str, Any] | None = None
    completed: list[dict[str, Any]] = []
    try:
        scaler, beta, moments_record, coefficients_record = (
            _load_decision_model(k)
        )
        seal_record, _, prediction_rows = _ensure_prediction_seal(
            h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
            moments_record=moments_record,
            coefficients_record=coefficients_record,
            artifact_root=artifact_root,
        )
        completed.append(dict(seal_record))
        # The full live H/K closure is checked again after the durable seal and
        # before the only outcome/market access intent can be created.
        checked_k = verify_coefficient_freeze_live(h.commit, k.commit)
        if checked_k != k:
            raise shots.LockMismatch("H/K identity changed after prediction seal")
        stage = "scoring_access"
        scoring_intent_record, scoring_access_record, score_record, score_value = (
            _ensure_decision_scores(
                h=h, k=k, schedule=schedule, scaler=scaler, beta=beta,
                prediction_seal_record=seal_record,
                prediction_rows=prediction_rows, artifact_root=artifact_root,
            )
        )
        completed.extend([
            dict(scoring_intent_record), dict(scoring_access_record),
            dict(score_record),
        ])
        stage = "canary"
        canary = _make_decision_canary_receipt(
            prediction_seal_record=seal_record,
            scoring_access_record=scoring_access_record,
            prediction_rows=prediction_rows, score_value=score_value,
        )
        canary_record, _ = _write_decision_artifact_once(
            "decision_canary_receipt", canary, artifact_root=artifact_root,
        )
        _validate_decision_canary_receipt(
            canary, prediction_seal_record=seal_record,
            scoring_access_record=scoring_access_record,
            score_record=score_record,
        )
        completed.append(dict(canary_record))
        stage = "result"
        result = _success_result(
            h=h, k=k, prediction_seal_record=seal_record,
            completed_receipts=completed, score_value=score_value,
        )
    except _PUBLISHABLE_SCIENTIFIC_REFUSALS as exc:
        return _publish_refusal(
            h=h, k=k, prediction_seal_record=seal_record,
            completed_receipts=completed, refusal=exc, stage=stage,
            counts={
                "prediction_rows": (
                    _DECISION_ROWS if seal_record is not None else 0
                ),
                "scoring_rows": 0,
            },
            artifact_root=artifact_root,
        )
    except shots.ShotsError as exc:
        raise ManualReconciliationRequired(
            "decision integrity failure is not an authorized publishable "
            "refusal"
        ) from exc
    # Terminal adoption/publication integrity is outside the scientific
    # refusal catch.  A stale H/K or an ambiguous immutable write must STOP;
    # it cannot be converted into a second contradictory refusal result.
    _require_no_orphan_fixed_publication(terminal_present=False)
    _require_live_publication_provenance(h=h, k=k)
    result_record, _ = _write_decision_artifact_once(
        "decision_result", result, artifact_root=artifact_root,
    )
    _require_exact_decision_result(
        result_record=result_record, result=result, artifact_root=artifact_root,
    )
    _require_live_publication_provenance(h=h, k=k)
    return _finalize_result_publication(
        h=h, k=k, result_record=result_record, result=result,
        artifact_root=artifact_root,
    )


def inspect_state(*, h_commit: str | None = None,
                  k_commit: str | None = None) -> LifecycleStatus:
    issues: list[str] = []
    h_ok = k_ok = False
    training_sha = decision_sha = ""
    try:
        training_sha, _ = _training_binding()
        decision_sha, _ = decision_schedule_binding()
    except (shots.ShotsError, NonPublishingRunStop) as exc:
        issues.append(f"schedule verification failed: {exc}")
    if h_commit:
        try: verify_harness_live(h_commit); h_ok = True
        except (shots.ShotsError, NonPublishingRunStop) as exc:
            issues.append(f"H verification failed: {exc}")
    elif _H_PATH.exists(): issues.append("H manifest exists but no H commit was supplied")
    if k_commit and h_commit:
        try: verify_coefficient_freeze_live(h_commit, k_commit); k_ok = True
        except (shots.ShotsError, NonPublishingRunStop) as exc:
            issues.append(f"K verification failed: {exc}")
    elif k_commit: issues.append("K verification requires H")
    elif _K_PATH.exists(): issues.append("K manifest exists but no K commit was supplied")
    manifest_present = _H_PATH.is_file()
    return LifecycleStatus(
        _live_build_state(manifest_present=manifest_present, h_verified=h_ok),
        H_READY, TRAINING_WORKER_READY,
        DECISION_WORKER_READY, manifest_present, _K_PATH.is_file(), h_ok, k_ok,
        training_sha, decision_sha, tuple(issues))


def _live_build_state(*, manifest_present: bool, h_verified: bool) -> str:
    """Derive the lifecycle reading from live gates, never a stored claim.

    Amendment 2 Rider 2: a bare inspection reports manifest presence without
    certifying it; only a successful live H verification for a supplied commit
    reads as frozen.
    """
    if h_verified:
        return "FROZEN_H_VERIFIED"
    if manifest_present:
        return "H_MANIFEST_PRESENT_UNVERIFIED"
    return "BUILT_UNFROZEN_PRE_H"


def _training_refusal_receipts(
    *, artifact_root: Path, strict: bool = False,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Recover bounded immutable training records for refusal publication."""
    records: list[dict[str, Any]] = []
    counts: dict[str, Any] = {
        "native_blocks": 0, "native_completions": 0,
        "native_refusals": 0,
        "optimizer_intents": 0, "optimizer_receipts": 0,
        "training_predictions": 0,
    }
    try:
        with _open_decision_state_directory(
            artifact_root, create=False,
        ) as (_, directory_fd):
            if directory_fd is None:
                return records, counts
            names = sorted(os.listdir(directory_fd))
            block_pattern = re.compile(
                r"native-block-[0-9]{3}-[0-9a-f]{64}\.json"
            )
            counts["native_blocks"] = sum(
                bool(block_pattern.fullmatch(name)) for name in names
            )
            for logical in (
                "native_intent", "native_completion", "native_refusal",
                "feature_moments",
                "optimizer_intent", "optimizer_receipt", "coefficients",
                "training_predictions",
            ):
                found = _optimizer_records_at(
                    logical, directory_fd=directory_fd,
                )
                records.extend(dict(record) for record, _ in found)
                if logical == "native_completion":
                    counts["native_completions"] = len(found)
                elif logical == "native_refusal":
                    counts["native_refusals"] = len(found)
                elif logical == "optimizer_intent":
                    counts["optimizer_intents"] = len(found)
                elif logical == "optimizer_receipt":
                    counts["optimizer_receipts"] = len(found)
                elif logical == "training_predictions":
                    counts["training_predictions"] = len(found)
    except (OSError, shots.ShotsError) as exc:
        # The original refusal remains authoritative when recovery itself is
        # unsafe.  Partial counts must not be represented as complete.
        if strict:
            raise shots.LockMismatch(
                "training refusal receipt recovery is unsafe"
            ) from exc
        return [], {key: 0 for key in counts}
    return records, counts


def _resume_pre_k_terminal(
    *, h: _VerifiedH, artifact_root: Path,
) -> dict[str, Any] | None:
    """Return an exact training terminal before any K/native/data action."""
    terminal = _existing_decision_result_only(artifact_root=artifact_root)
    if terminal is None:
        return None
    result_record, result = terminal
    if (result.get("schema") != _DECISION_RESULT_SCHEMA
            or result.get("harness_commit") != h.commit):
        raise shots.LockMismatch("existing terminal belongs to another H")
    if not _is_pre_k_refusal(result):
        raise RunnerNotReady(
            "the experiment already has a post-K terminal result"
        )
    if result.get("refusal_stage") != "training":
        raise shots.LockMismatch(
            "K=N/A terminal was not published at the training stage"
        )
    _require_pre_k_decision_namespace(
        artifact_root=artifact_root, result_record=result_record,
    )
    _validate_decision_result(
        result, h=h, k=None, prediction_seal_record=None,
    )
    return _finalize_result_publication(
        h=h, k=None, result_record=result_record, result=result,
        artifact_root=artifact_root,
    )


def run_training(*, h_commit: str) -> dict[str, Any]:
    """Run or resume the separately authorized post-H training transaction."""
    h = verify_harness_live(h_commit)
    with _experiment_transaction_lock(h=h, artifact_root=_ARTIFACT_ROOT):
        terminal = _resume_pre_k_terminal(h=h, artifact_root=_ARTIFACT_ROOT)
        if terminal is not None:
            return terminal
        _require_pre_k_decision_namespace(
            artifact_root=_ARTIFACT_ROOT, result_record=None,
        )
        _require_no_orphan_fixed_publication(terminal_present=False)
        try:
            return _run_training_after_h(h_commit=h.commit)
        except _PUBLISHABLE_TRAINING_REFUSALS as exc:
            completed, counts = _training_refusal_receipts(
                artifact_root=_ARTIFACT_ROOT, strict=True,
            )
            return _publish_refusal(
                h=h, k=None, prediction_seal_record=None,
                completed_receipts=completed, refusal=exc, stage="training",
                counts=counts, artifact_root=_ARTIFACT_ROOT,
            )
        except shots.ShotsError as exc:
            raise ManualReconciliationRequired(
                "training integrity failure is not an authorized publishable "
                "refusal"
            ) from exc


def run_decision(*, h_commit: str, k_commit: str) -> dict[str, Any]:
    """Run or resume the frozen decision transaction after exact live H/K."""
    # A pre-K refusal dominates forever and must be observed before K or any
    # decision corpus can be opened.  The supplied K is intentionally ignored
    # on this idempotent terminal path.
    h = verify_harness_live(h_commit)
    with _experiment_transaction_lock(h=h, artifact_root=_ARTIFACT_ROOT):
        terminal = _resume_pre_k_terminal(h=h, artifact_root=_ARTIFACT_ROOT)
        if terminal is not None:
            return terminal
        return _run_decision_after_k(h_commit=h_commit, k_commit=k_commit)


def main(argv: Sequence[str] | None = None) -> int:
    """Expose only fixed-path status and commit-addressed fail-closed actions."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    status = sub.add_parser("status")
    status.add_argument("--h")
    status.add_argument("--k")
    train = sub.add_parser("train")
    train.add_argument("--h", required=True)
    decide = sub.add_parser("decide")
    decide.add_argument("--h", required=True)
    decide.add_argument("--k", required=True)
    args = parser.parse_args(argv)
    try:
        if args.command == "status":
            print(json.dumps(
                inspect_state(h_commit=args.h, k_commit=args.k).as_dict(),
                sort_keys=True,
            ))
            return 0
        if args.command == "train":
            result = run_training(h_commit=args.h)
            print(json.dumps(result, sort_keys=True))
            return 0
        else:
            result = run_decision(h_commit=args.h, k_commit=args.k)
            print(json.dumps(result, sort_keys=True))
            return 0
    except NonPublishingRunStop as exc:
        print(f"INTERRUPTED {type(exc).__name__}: {exc}", file=sys.stderr)
        return 75
    except shots.ShotsError as exc:
        print(f"STOP {type(exc).__name__}: {exc}", file=sys.stderr)
        return 2
    raise AssertionError("unreachable lifecycle command state")


if __name__ == "__main__":
    raise SystemExit(main())
