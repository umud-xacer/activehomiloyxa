# deployment/docker/realtime.Dockerfile -- the realtime gateway container (Task P-10, DEC-11;
# Infra Sec 6 "realtime | python:3.13-slim + FastAPI"). The FIRST application Dockerfile in this
# repository -- every prior task's own Compose file explicitly excluded api/web/realtime/worker
# containers pending "the task that first has code to build" (deployment/README.md). Scoped to
# only the `realtime` service; api/web/worker containers for other modules remain out of scope.
#
# Multi-stage (DevSecOps Sec 9): a build stage installs the toolchain and dependencies into a
# venv; the runtime stage copies only that venv plus application source, never the build
# toolchain itself. Non-root, minimal packages (DevSecOps Sec 9 "non-root & hardening").
#
# Build (from the repo root): docker build -f deployment/docker/realtime.Dockerfile -t
# active-home/realtime .

FROM python:3.13-slim AS build

WORKDIR /build

# System build deps for the packages with C extensions (argon2-cffi, Pillow) that
# `apps/backend`'s own dependency set pulls in transitively via active-home-shared/contracts.
RUN apt-get update \
    && apt-get install -y --no-install-recommends build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY packages/shared/ packages/shared/
COPY contracts/ contracts/
COPY apps/backend/ apps/backend/

RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir \
    ./packages/shared \
    ./contracts \
    ./apps/backend

FROM python:3.13-slim AS runtime

RUN groupadd --system app && useradd --system --gid app --no-create-home app

COPY --from=build /opt/venv /opt/venv
COPY apps/backend/src /app/src

WORKDIR /app/src
ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1

USER app

EXPOSE 8000

CMD ["uvicorn", "realtime_main:app", "--host", "0.0.0.0", "--port", "8000"]
