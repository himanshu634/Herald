# Herald images. One file, many targets; the build context is the repo root because both
# the uv workspace and the pnpm workspace need it. Dockerfile.dockerignore next to this
# file is the ignore list for that context.
#
#   docker build -f infra/Dockerfile --target server .
#
#   server      API and worker for production (the worker overrides the command)
#   server-dev  API and worker with dev deps, run against a bind-mounted checkout
#   web         nginx serving the built SPA and proxying /api to the API
#   web-dev     Vite dev server, run against a bind-mounted checkout

ARG PYTHON_VERSION=3.13
ARG NODE_VERSION=22
ARG UV_VERSION=0.11.17
ARG PNPM_VERSION=11.2.2

# ---------- Python ----------

FROM ghcr.io/astral-sh/uv:${UV_VERSION} AS uv

FROM python:${PYTHON_VERSION}-slim AS server-base
COPY --from=uv /uv /uvx /usr/local/bin/
# The venv lives outside /app so a bind-mounted checkout (dev) cannot shadow it with the
# host's .venv, which holds macOS binaries.
ENV UV_PROJECT_ENVIRONMENT=/opt/venv \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never \
    PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app
COPY pyproject.toml uv.lock ./
COPY packages/core/pyproject.toml packages/core/
COPY apps/server/pyproject.toml apps/server/

FROM server-base AS server-build
# Third-party deps first, so code changes do not reinstall them.
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package herald-server --no-install-workspace
COPY packages/core/src packages/core/src
COPY apps/server/src apps/server/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --package herald-server --no-editable

FROM python:${PYTHON_VERSION}-slim AS server
ENV PYTHONUNBUFFERED=1 \
    PATH=/opt/venv/bin:$PATH
RUN useradd --system --uid 10001 --no-create-home herald
COPY --from=server-build /opt/venv /opt/venv
USER herald
EXPOSE 8000
HEALTHCHECK --interval=10s --timeout=3s --start-period=10s --retries=5 \
    CMD ["python", "-c", "import urllib.request; urllib.request.urlopen('http://localhost:8000/api/health')"]
# --proxy-headers trusts X-Forwarded-* from nginx, which is the only thing that reaches it.
CMD ["uvicorn", "herald_server.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--proxy-headers", "--forwarded-allow-ips", "*"]

FROM server-base AS server-dev
# Editable install: uv_build checks the package exists, so the src must be here at sync
# time. Compose then bind-mounts the checkout over /app and the venv follows the edits.
COPY packages/core/src packages/core/src
COPY apps/server/src apps/server/src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --all-packages
EXPOSE 8000
# The timeout cuts open SSE streams on reload. Without it a reload waits for them forever and
# the API hangs (see UVICORN in the Makefile).
CMD ["uvicorn", "herald_server.api.main:app", "--host", "0.0.0.0", "--port", "8000", \
     "--reload", "--reload-dir", "apps/server/src", "--reload-dir", "packages/core/src", \
     "--timeout-graceful-shutdown", "2"]

# ---------- Web ----------

FROM node:${NODE_VERSION}-slim AS web-base
ARG PNPM_VERSION
ENV CI=true
RUN npm install -g pnpm@${PNPM_VERSION}
WORKDIR /app
# pnpm-workspace.yaml carries allowBuilds; without it pnpm 11 skips esbuild's install
# script and Vite cannot start.
COPY package.json pnpm-lock.yaml pnpm-workspace.yaml ./
COPY apps/web/package.json apps/web/
RUN --mount=type=cache,target=/root/.local/share/pnpm/store \
    pnpm install --frozen-lockfile

FROM web-base AS web-dev
COPY apps/web apps/web
EXPOSE 5173
CMD ["pnpm", "-C", "apps/web", "exec", "vite", "dev", "--host", "0.0.0.0", "--port", "5173"]

FROM web-base AS web-build
COPY apps/web apps/web
RUN pnpm -C apps/web build

FROM nginx:1.27-alpine AS web
COPY infra/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=web-build /app/apps/web/build /usr/share/nginx/html
EXPOSE 80
