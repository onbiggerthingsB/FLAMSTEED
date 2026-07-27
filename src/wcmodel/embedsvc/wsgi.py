"""Production WSGI entrypoint for the publisher embed gateway."""

from __future__ import annotations

import os

from wcmodel.embedsvc.app import make_app
from wcmodel.embedsvc.entitlements import load_registry


PUBLISHERS_FILE = os.environ["PUBLISHERS_FILE"]
BUNDLE_ROOT = os.environ["BUNDLE_ROOT"]
METER_PATH = os.environ["METER_PATH"]

application = make_app(
    registry=load_registry(PUBLISHERS_FILE),
    bundle_root=BUNDLE_ROOT,
    meter_path=METER_PATH,
)
