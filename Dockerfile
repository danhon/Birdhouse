FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim

WORKDIR /app

# Install dependencies as a cached layer — only rebuilds when
# pyproject.toml or uv.lock changes, not on every source edit.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy source and install the project itself
COPY README.md ./
COPY src/ ./src/
RUN uv sync --frozen --no-dev

CMD ["uv", "run", "birdhouse"]
