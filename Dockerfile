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

EXPOSE 8000

ENV FLASK_APP=main.py \
    PYTHONPATH=/app

CMD ["gunicorn", "-b", "0.0.0.0:8000", "--worker-class", "gthread", "--threads", "4", "--timeout", "60", "--log-level", "info", "main:app"]
