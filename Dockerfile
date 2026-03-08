# syntax=docker/dockerfile:1

# --- Build stage ---
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS builder

WORKDIR /app

# Install dependencies first (cache layer)
COPY pyproject.toml uv.lock* ./
RUN uv sync --no-dev --no-install-project

# Copy source and install the project
COPY src/ src/
RUN uv sync --no-dev

# --- Runtime stage ---
FROM python:3.12-slim-bookworm AS runtime

WORKDIR /app

# Copy the virtual environment from builder
COPY --from=builder /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH"

# Create non-root user
RUN useradd -m dockmaster && chown -R dockmaster:dockmaster /app
USER dockmaster

EXPOSE 8001
CMD ["uvicorn", "dockmaster.main:app", "--host", "0.0.0.0", "--port", "8001"]
