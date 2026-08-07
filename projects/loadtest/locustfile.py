"""Locust entry point for load testing.

Run from this directory:
    locust                          # Web UI at http://localhost:8089
    locust --headless -t 30s        # CLI (shape-driven; profile in config/)

Scenarios are loaded from scenarios/<APP_ENV>/login.yaml (data-driven,
environment-isolated). Framework config (config/envs/*.yaml) provides
base_url and HTTP settings. config/load_profile.yaml drives ramp stages
and SLA assertions (optional -- falls back to --users/--spawn-rate CLI).
"""

from __future__ import annotations

import os

from runner import build_shape_class, build_user_class

# Active environment selects both config YAML and scenario directory.
# SCENARIO_FILE env var overrides the default path (e.g. scenarios/cost/cost_calculate.yaml).
_ENV = os.environ.get("APP_ENV", "dev")
_SCENARIO_FILE = os.environ.get("SCENARIO_FILE", os.path.join("scenarios", _ENV, "login.yaml"))

# Build the Locust HttpUser subclass from YAML scenarios.
# This is the single object Locust discovers (must be module-level).
JmsLoadUser = build_user_class(_SCENARIO_FILE)

# Optional: YAML-driven load shape (overrides --users/--spawn-rate).
# Only assigned at module level when a profile exists, so Locust discovers it.
_shape_class = build_shape_class()
if _shape_class is not None:
    YamlLoadTestShape = _shape_class
