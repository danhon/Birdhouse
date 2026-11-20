FROM python:3.12-slim-bookworm
# Astral stopped updating uv:python3.12-bookworm-slim on 2026-02-04, so a
# rebuild never got Debian's fixes (reverse-proxy python-apps.md). uv pinned
# by version, a release at least 3 days old (IMG-2).
COPY --from=ghcr.io/astral-sh/uv:0.13.6 /uv /uvx /bin/
ENV UV_PYTHON_DOWNLOADS=never

WORKDIR /app

# Install dependencies as a cached layer — only rebuilds when
# pyproject.toml or uv.lock changes, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself
COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

# The commit this image was built from (IMG-3, reverse-proxy#122): the
# nightly rebuild only rebuilds an image that records it.
ARG GIT_SHA=dev
ARG BUILD_TIME=
ENV BUILD_SHA="${GIT_SHA}" \
    BUILD_TIME="${BUILD_TIME}"

CMD ["uv", "run", "birdhouse"]
