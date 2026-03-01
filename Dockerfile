# ─── Stage 1: React build ─────────────────────────────────────────────────────
FROM node:20-alpine AS react-build

WORKDIR /react

# Copy package files first for better layer caching
COPY asu-unity-react/package.json asu-unity-react/package-lock.json* ./

# Copy .npmrc for @asu scoped registry auth
COPY asu-unity-react/.npmrc ./

# Install JS dependencies (NPM_AUTH_TOKEN must be passed as a build arg)
ARG NPM_AUTH_TOKEN
RUN NPM_AUTH_TOKEN=${NPM_AUTH_TOKEN} npm install

# Copy the rest of the React source
COPY asu-unity-react/ .

# Build the production bundle
RUN NPM_AUTH_TOKEN=${NPM_AUTH_TOKEN} npm run build

# ─── Stage 2: Python production ───────────────────────────────────────────────
FROM python:3.12-slim AS base

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /app

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        build-essential \
        libffi-dev \
        libssl-dev \
        libxml2 \
        libxml2-dev \
        libxmlsec1 \
        libxmlsec1-dev \
        libxmlsec1-openssl \
        openssh-client \
        pkg-config \
        xmlsec1 \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

COPY . .

# Copy React build from Stage 1
COPY --from=react-build /react/dist /app/react-dist

EXPOSE 8000

ENV FLASK_APP=main.py \
    PYTHONPATH=/app \
    REACT_BUILD_DIR=/app/react-dist

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--worker-class", "gthread", "--threads", "4", "--timeout", "60", "--log-level", "info", "main:app"]
