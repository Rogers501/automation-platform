#!/bin/sh
# CI entrypoint: single source of truth for pipeline commands.
# Used by .gitlab-ci.yml and Jenkinsfile so neither duplicates command logic.
#
# Usage: sh scripts/ci/ci.sh <command>
#   install         uv sync --frozen + allure-pytest (the pytest plugin)
#   install-allure  install allure CLI + JRE (debian; needs root) -- skip if present
#   lint            ruff check + ruff format --check + mypy
#   smoke           pytest -m smoke -n auto (critical-path gate, parallel)
#   regression      pytest -m regression -n auto (comprehensive, parallel)
#   report          allure generate <results> -> <report> (HTML)
#   clean           remove allure results + report
#
# Env:
#   ALLURE_RESULTS  (default allure-results)
#   ALLURE_REPORT   (default allure-report)
#   ALLURE_VERSION  (default 2.30.0)
#   UV_VERSION      (default 0.11.14)

set -eu

ALLURE_RESULTS="${ALLURE_RESULTS:-allure-results}"
ALLURE_REPORT="${ALLURE_REPORT:-allure-report}"
ALLURE_VERSION="${ALLURE_VERSION:-2.30.0}"
UV_VERSION="${UV_VERSION:-0.11.14}"
# Number of parallel workers for pytest-xdist ("auto" = CPU count).
XDIST_WORKERS="${XDIST_WORKERS:-auto}"
JUNIT="${JUNIT:-reports/junit.xml}"

ensure_uv() {
    if ! command -v uv >/dev/null 2>&1; then
        pip install "uv==${UV_VERSION}"
    fi
}

cmd_install() {
    ensure_uv
    uv sync --frozen
    # allure-pytest is an optional CI dependency (not locked) so the framework
    # stays installable without it; install it here to emit --alluredir results.
    uv pip install allure-pytest
}

cmd_install_allure() {
    if command -v allure >/dev/null 2>&1; then
        echo "allure CLI already installed: $(allure --version)"
        return 0
    fi
    if ! command -v apt-get >/dev/null 2>&1; then
        echo "error: apt-get not found; install allure CLI manually on this image." >&2
        exit 1
    fi
    apt-get update
    apt-get install -y --no-install-recommends openjdk-17-jre-headless curl ca-certificates
    tmp="$(mktemp -d)"
    curl -fsSL "https://github.com/allure-framework/allure2/releases/download/${ALLURE_VERSION}/allure-${ALLURE_VERSION}.tgz" \
        -o "${tmp}/allure.tgz"
    tar -xzf "${tmp}/allure.tgz" -C /opt
    ln -sf "/opt/allure-${ALLURE_VERSION}/bin/allure" /usr/local/bin/allure
    rm -rf "${tmp}"
    allure --version
}

cmd_lint() {
    ensure_uv
    uv run ruff check .
    uv run ruff format --check .
    uv run mypy
}

cmd_smoke() {
    ensure_uv
    mkdir -p "$(dirname "${JUNIT}")"
    uv run pytest -m smoke -n "${XDIST_WORKERS}" --alluredir="${ALLURE_RESULTS}" --clean-alluredir --junitxml="${JUNIT}"
}

cmd_regression() {
    ensure_uv
    mkdir -p "$(dirname "${JUNIT}")"
    uv run pytest -m regression -n "${XDIST_WORKERS}" --alluredir="${ALLURE_RESULTS}" --junitxml="${JUNIT}"
}

cmd_report() {
    if ! command -v allure >/dev/null 2>&1; then
        echo "error: allure CLI not found. Run 'ci.sh install-allure' first." >&2
        exit 1
    fi
    allure generate "${ALLURE_RESULTS}" -o "${ALLURE_REPORT}" --clean
}

cmd_clean() {
    rm -rf "${ALLURE_RESULTS}" "${ALLURE_REPORT}"
}

case "${1:-}" in
    install) cmd_install ;;
    install-allure) cmd_install_allure ;;
    lint) cmd_lint ;;
    smoke) cmd_smoke ;;
    regression) cmd_regression ;;
    report) cmd_report ;;
    clean) cmd_clean ;;
    *)
        echo "usage: $0 {install|install-allure|lint|smoke|regression|report|clean}" >&2
        exit 2
        ;;
esac