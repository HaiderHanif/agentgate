# Minimal image for running agentgate in CI systems without a Python toolchain.
#
#   docker build -t agentgate .
#   docker run --rm -v "$PWD:/work" agentgate verify app.agent:run traces/flow.json

FROM python:3.12-slim AS build

WORKDIR /src
COPY pyproject.toml README.md LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir build \
    && python -m build --wheel --outdir /dist

FROM python:3.12-slim

LABEL org.opencontainers.image.title="agentgate" \
      org.opencontainers.image.description="Regression gating for AI agents" \
      org.opencontainers.image.source="https://github.com/HaiderHanif/agentgate" \
      org.opencontainers.image.licenses="MIT"

RUN useradd --create-home --uid 1000 agent
COPY --from=build /dist/*.whl /tmp/
RUN pip install --no-cache-dir /tmp/*.whl && rm -rf /tmp/*.whl

USER agent
WORKDIR /work

ENTRYPOINT ["agentgate"]
CMD ["--help"]
