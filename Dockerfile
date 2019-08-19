FROM docker.dbc.dk/dbc-python3

ENV NAMESPACES "namespaces-not-set"
ENV SLACK_TOKEN "slack-token-not-set"
ENV SLACK_CHANNEL "slack-channel-not-set"
ENV KUBE_CONFIG ""

RUN mkdir kube-monitor
WORKDIR kube-monitor

COPY setup.py setup.py
COPY src src
COPY docker/start.sh start.sh

RUN bash -c 'python3 -m venv ENV && \
	source ENV/bin/activate && \
	pip install -U pip && \
	pip install .'

CMD ["./start.sh"]

LABEL NAMESPACES namespaces to monitor
LABEL SLACK_TOKEN token for slack bot
LABEL SLACK_CHANNEL slack channel to post message to
LABEL KUBE_CONFIG path to kubernetes config file [optional]
