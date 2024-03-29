FROM docker-dbc.artifacts.dbccloud.dk/dbc-python3

RUN apt update && apt install -y gcc g++ build-essential python3-dev

ENV NAMESPACES "namespaces-not-set"
ENV SLACK_TOKEN "slack-token-not-set"
ENV SLACK_CHANNEL "slack-channel-not-set"
ENV KUBE_CONFIG ""

RUN useradd -m python

USER python
WORKDIR /home/python

ENV PATH=/home/python/.local/bin:$PATH

COPY --chown=python setup.py setup.py
COPY --chown=python src src
COPY --chown=python docker/start.sh start.sh

RUN pip install --user pip && \
    pip install --user .

CMD ["./start.sh"]

LABEL NAMESPACES namespaces to monitor
LABEL SLACK_TOKEN token for slack bot
LABEL SLACK_CHANNEL slack channel to post message to
LABEL KUBE_CONFIG path to kubernetes config file [optional]
