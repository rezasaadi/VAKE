# syntax=docker/dockerfile:1

FROM rust:1.97.1-bookworm

ARG TARGETARCH
ARG LEAN_VERSION=4.34.1
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    CARGO_HOME=/usr/local/cargo \
    RUSTUP_HOME=/usr/local/rustup \
    VAKE_UI_PORT=8765 \
    VAKE_UI_TEST_LEAN=1

RUN apt-get update \
    && apt-get install -y --no-install-recommends \
       python3 ca-certificates curl zstd \
    && rm -rf /var/lib/apt/lists/*

RUN set -eux; \
    case "${TARGETARCH:-amd64}" in \
      amd64) lean_platform=linux; sha=47bf4bbd78f70c2e9670598ab7124d92b6efb7330ff33e5fbb4030f6fd72e4e4 ;; \
      arm64) lean_platform=linux_aarch64; sha=fdb974c2cdb4627e090d5d4007b913e09d13c4868720fb5594e22808b3de9e37 ;; \
      *) echo "Unsupported Docker architecture: ${TARGETARCH}" >&2; exit 1 ;; \
    esac; \
    archive="lean-${LEAN_VERSION}-${lean_platform}.tar.zst"; \
    curl --fail --location --retry 3 --retry-delay 3 \
      "https://github.com/leanprover/lean4/releases/download/v${LEAN_VERSION}/${archive}" \
      --output /tmp/lean.tar.zst; \
    printf '%s  %s\n' "$sha" /tmp/lean.tar.zst | sha256sum --check --status; \
    tar --use-compress-program=unzstd -xf /tmp/lean.tar.zst -C /opt; \
    ln -s "/opt/lean-${LEAN_VERSION}-${lean_platform}" /opt/lean; \
    rm /tmp/lean.tar.zst; \
    /opt/lean/bin/lean --version

RUN rustup toolchain install 1.97.1 --profile minimal --component clippy --component rustfmt

ENV PATH="/opt/lean/bin:${PATH}"
WORKDIR /opt/vake
COPY . .

RUN set -eux; \
    python3 -m ui.server --help | grep -q -- '--bind'; \
    python3 scripts/reproduce.py --stage all

RUN set -eux; \
    groupadd --gid 10001 vake; \
    useradd --uid 10001 --gid 10001 --create-home --shell /bin/bash vake; \
    mkdir -p reports/runs reports/ui-runs; \
    chown -R vake:vake /opt/vake /usr/local/cargo /usr/local/rustup; \
    chmod 0755 scripts/docker-entrypoint.sh

USER vake
EXPOSE 8765
HEALTHCHECK --interval=30s --timeout=5s --start-period=15s --retries=3 \
  CMD python3 -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8765/api/health', timeout=3)" || exit 1
ENTRYPOINT ["bash", "scripts/docker-entrypoint.sh"]
CMD ["ui"]
