# syntax=docker/dockerfile:1.7

# ─── Build stage ─────────────────────────────────────────────────────────────
# --platform=$BUILDPLATFORM: the builder always runs on the build machine's
# native architecture and cross-compiles the target architecture's binary via
# GOARCH. In multi-arch builds, if the builder followed the target platform,
# the arm64 build would compile under QEMU emulation — Go compilation is
# CPU-intensive and an order of magnitude slower.
FROM --platform=$BUILDPLATFORM golang:1.26-alpine AS builder

WORKDIR /src

# Cache deps separately for faster rebuilds
COPY go.mod go.sum ./
RUN go mod download

COPY . .

# TARGETARCH is injected by buildx (amd64 / arm64 ...). The classic builder
# doesn't inject it; fall back to amd64.
ARG TARGETARCH

# CGO disabled — modernc/sqlite is pure Go.
# -ldflags strip symbols to shave ~5MB off binary.
RUN CGO_ENABLED=0 GOOS=linux GOARCH=${TARGETARCH:-amd64} go build \
    -ldflags="-s -w" \
    -trimpath \
    -o /out/gemini-web2api .

# ─── Runtime stage ───────────────────────────────────────────────────────────
# distroless/static: ~2MB base, no shell, no package manager — minimal attack surface.
# We pre-create /data with nonroot ownership in the builder so distroless
# (which has no `mkdir`) doesn't choke at startup.
# Also pinned to the build machine's architecture: this layer is just
# mkdir + chown (numeric uid, architecture-independent) — no reason to
# pull a target-architecture alpine for it and go through QEMU.
FROM --platform=$BUILDPLATFORM alpine:3.20 AS prepare
RUN mkdir -p /out/data /out/app && chown -R 65532:65532 /out/data /out/app

FROM gcr.io/distroless/static-debian12:nonroot

# /data is owned by uid 65532 (nonroot) so sqlite can create gemini.db.
COPY --from=prepare --chown=65532:65532 /out/data /data
COPY --from=prepare --chown=65532:65532 /out/app /app

WORKDIR /app
COPY --from=builder /out/gemini-web2api /app/gemini-web2api

USER nonroot:nonroot

EXPOSE 8083

ENV DB_PATH=/data/gemini.db
ENTRYPOINT ["/app/gemini-web2api"]
CMD ["--db", "/data/gemini.db", "--port", "8083"]
