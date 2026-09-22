# Multi-stage build: compile dependencies in a full image, run in a slim one.
# There was previously no Dockerfile at all in this repo — "run streamlit
# locally on your laptop" is not a deployment story for anything meant to run
# in production, so this is what actually lets `pwa` and the Streamlit UI run
# anywhere (Cloud Run, GKE, ECS, plain `docker run`) instead of only on the
# machine of whoever cloned the repo.

FROM python:3.11-slim AS builder

WORKDIR /build

# build-essential covers any dependency that needs to compile a C extension
# (most of this project's deps ship prebuilt wheels, but this keeps the
# builder stage robust to platform/wheel-availability differences).
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    && rm -rf /var/lib/apt/lists/*

COPY pyproject.toml README.md ./
COPY src ./src

# Install into a venv (not system site-packages) so the runtime stage can
# copy just this directory instead of reasoning about apt vs. pip layering.
RUN python -m venv /opt/venv
ENV PATH="/opt/venv/bin:$PATH"
RUN pip install --no-cache-dir --upgrade pip \
    && pip install --no-cache-dir .


FROM python:3.11-slim AS runtime

# Non-root: a container that can only run as whatever user it was given is a
# much smaller blast radius than one that defaults to root.
RUN groupadd --gid 1000 pwa && useradd --uid 1000 --gid pwa --shell /bin/bash --create-home pwa

WORKDIR /app
COPY --from=builder /opt/venv /opt/venv
COPY --chown=pwa:pwa src ./src
COPY --chown=pwa:pwa app.py ./
COPY --chown=pwa:pwa config ./config

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONPATH="/app/src" \
    PYTHONUNBUFFERED="1" \
    STREAMLIT_SERVER_HEADLESS="true" \
    STREAMLIT_SERVER_ADDRESS="0.0.0.0" \
    STREAMLIT_BROWSER_GATHER_USAGE_STATS="false"

USER pwa
EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8501/_stcore/health', timeout=3).status == 200 else 1)"

# Default: the Streamlit chat UI. Override the command to run `pwa <subcommand>`
# instead (e.g. `docker run <image> pwa warehouse run`) — both share this same
# image and Python environment, so there is exactly one thing to build and push.
CMD ["streamlit", "run", "app.py", "--server.port=8501"]
