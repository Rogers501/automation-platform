# Enterprise automation testing platform - test runtime image.
# Build: docker build -f docker/Dockerfile -t automation-platform:dev .
# Run:   docker run --rm automation-platform:dev uv run pytest

# syntax=docker/dockerfile:1.7
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    UV_LINK_MODE=copy

RUN apt-get update \
    && apt-get install -y --no-install-recommends curl ca-certificates \
    && rm -rf /var/lib/apt/lists/*

FROM base AS deps
COPY --from=ghcr.io/astral-sh/uv:0.11.14 /uv /bin/uv
WORKDIR /app

# Copy manifests + lock first to cache the dependency layer.
COPY pyproject.toml uv.lock ./
COPY framework/pyproject.toml ./framework/pyproject.toml
RUN uv sync --frozen --no-install-project --no-install-package=framework

# Copy sources and finalise the install.
COPY framework/src ./framework/src
COPY conftest.py ./
COPY tests ./tests
RUN uv sync --frozen

# Run as a non-root user.
RUN useradd --create-home --uid 1000 tester && chown -R tester:tester /app
USER tester

CMD ["uv", "run", "pytest"]
