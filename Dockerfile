# ---------- build stage ----------
FROM python:3.14-slim AS build

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /app

COPY pyproject.toml requirements.txt ./
RUN python -m pip install --upgrade pip \
 && pip install --prefix=/install -r requirements.txt

# ---------- runtime stage ----------
FROM python:3.14-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH=/install/bin:$PATH

WORKDIR /app

COPY --from=build /install /install
COPY src ./src
COPY tests ./tests
COPY fixtures ./fixtures
COPY scripts ./scripts
COPY pyproject.toml requirements.txt README.md LICENSE ./

RUN useradd --create-home --uid 1001 bench \
 && mkdir -p /app/results \
 && chown -R bench:bench /app
USER bench

VOLUME ["/app/results"]

ENTRYPOINT ["python", "-m", "scripts.run_bench"]
CMD ["--help"]
