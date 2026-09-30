# gitmole from PyPI and the three tools it runs, at the versions that release pins.
#
#   docker build --build-arg GITMOLE_VERSION=0.41.0 -t gitmole .
#   docker run --rm -v "$PWD:/repo" gitmole .
#
# Builds for linux/amd64 and linux/arm64: every pinned tool publishes both (gitmole/tools.py). Before 0.39.0
# git-sizer, which has no Linux arm64 build, held the image to amd64.
# The base is pinned by digest, python:3.12-slim-bookworm as of 28 Sep 2026.
ARG BASE=python:3.12-slim-bookworm@sha256:392307d22300de8b5986851a12d9176dfc0fc073e65bf6523ebd7dcbeb23564e

FROM ${BASE} AS build
ARG GITMOLE_VERSION=0.41.0
ENV GITMOLE_TOOLS=/opt/gitmole/tools
RUN python -m venv /opt/gitmole/venv \
 && /opt/gitmole/venv/bin/pip install --no-cache-dir --disable-pip-version-check "gitmole==${GITMOLE_VERSION}" \
 && /opt/gitmole/venv/bin/gitmole --install-tools \
 && mkdir /opt/gitmole/bin \
 && ln -s /opt/gitmole/tools/*/* /opt/gitmole/bin/

FROM ${BASE}
# a mounted repository belongs to the host's user, not to the container's: without safe.directory git refuses
# it. /osv is osv-scanner's database directory, open to any user so a run with --user and no database there
# says "not scanned" rather than failing to create it.
RUN apt-get update \
 && apt-get install -y --no-install-recommends git \
 && rm -rf /var/lib/apt/lists/* \
 && git config --system --add safe.directory '*' \
 && mkdir -m 1777 /osv
COPY --from=build /opt/gitmole /opt/gitmole
# GITMOLE_TOOLS is where gitmole looks for the tools it installed; /opt/gitmole/bin links them onto PATH for a
# shell, or for osv-scanner run by hand to fetch the vulnerability database (docs/cli.md#docker). The caches go
# under /tmp so that a run with --user, which has no home here, can still write them.
ENV GITMOLE_TOOLS=/opt/gitmole/tools \
    PATH=/opt/gitmole/venv/bin:/opt/gitmole/bin:$PATH \
    XDG_CACHE_HOME=/tmp/cache \
    OSV_SCANNER_LOCAL_DB_CACHE_DIRECTORY=/osv \
    GITMOLE_NO_FEEDBACK=1
RUN gitmole --doctor
WORKDIR /repo
ENTRYPOINT ["gitmole"]
CMD ["."]
