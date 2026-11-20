# This extension uses the upstream application's indexing and retrieval code under Apache-2.0.
ARG RESEARCH_BASE=ghcr.io/modsetter/surfsense:2.3.1@sha256:106baa89d5f79168c1c5e9bce77655d3e99f2950250772a1d41508c04d73a4a0
FROM ${RESEARCH_BASE}
COPY docker/research/server.py /app/surfsense_local/backend/api/server.py
COPY docker/research/index_routes.py /app/surfsense_local/backend/api/workspaceai_index.py
