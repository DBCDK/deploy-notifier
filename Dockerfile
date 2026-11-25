FROM docker-dbc.artifacts.dbccloud.dk/dbc-python3

RUN apt update && apt install -y gcc g++ build-essential python3-dev

ENV NAMESPACES "namespaces-not-set"
ENV SLACK_TOKEN "slack-token-not-set"
ENV SLACK_CHANNEL "slack-channel-not-set"
ENV KUBE_CONFIG ""

RUN useradd -m python

USER python
WORKDIR /home/python

# uv: precompile .pyc, copy (not hardlink) into the venv, no cache in the image,
# and use the base image python
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_NO_CACHE=1 \
    UV_PYTHON_DOWNLOADS=never

# Copy project metadata and lock file
COPY --chown=python pyproject.toml uv.lock ./

# Install dependencies only (not the local package) so this layer is cached.
RUN uv sync --locked --no-dev --no-install-project

# Copy source last so dependency layer is reused on source-only changes
COPY --chown=python src src

# Install the local package now that source is present
RUN uv sync --locked --no-dev --no-editable

# Ensure the venv is first in PATH
ENV PATH="/home/python/.venv/bin:${PATH}"

COPY --chown=python docker/start.sh start.sh

CMD ["./start.sh"]

LABEL NAMESPACES namespaces to monitor
LABEL SLACK_TOKEN token for slack bot
LABEL SLACK_CHANNEL slack channel to post message to
LABEL KUBE_CONFIG path to kubernetes config file [optional]
