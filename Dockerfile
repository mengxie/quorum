# syntax=docker/dockerfile:1

# ---- Build a virtual environment with only the runtime dependencies
FROM python:3.12-slim AS build
COPY --from=ghcr.io/astral-sh/uv:0.11.7 /uv /bin/uv
ENV UV_COMPILE_BYTECODE=1 UV_LINK_MODE=copy UV_PYTHON_DOWNLOADS=never
WORKDIR /app
COPY pyproject.toml uv.lock ./
RUN uv sync --locked --no-dev --no-install-project
COPY README.md ./
COPY src ./src
RUN uv sync --locked --no-dev --no-editable

# ---- Runtime: the virtual environment and nothing else, as a non-root user
FROM python:3.12-slim AS runtime
RUN useradd --create-home --uid 10001 quorum
COPY --from=build /app/.venv /app/.venv
ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1
USER quorum
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import sys, urllib.request; sys.exit(urllib.request.urlopen('http://127.0.0.1:8000/healthz').status != 200)"
# Behind a reverse proxy, set FORWARDED_ALLOW_IPS to its address so links use the public host.
CMD ["uvicorn", "quorum.web.app:create_app", "--factory", "--host", "0.0.0.0", "--port", "8000", "--proxy-headers"]
