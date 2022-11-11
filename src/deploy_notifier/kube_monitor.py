#!/usr/bin/env python3

# https://github.com/kubernetes-client/python

import argparse
import collections
import concurrent.futures
import io
import logging
import os
import pickle
import sys
import typing

import kubernetes
from dbc_pyutils import JSONFormatter
import requests
import slack

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--kubeconfig")
    parser.add_argument("--slack-token", required=True)
    parser.add_argument("--slack-channel", required=True)
    parser.add_argument("--artifactory-url", required=True)
    parser.add_argument("--artifactory-login", help="artifactory login in user:password format")
    parser.add_argument("namespace", nargs="+")
    return parser.parse_args()

def setup_logging():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logging()

SlackInfo = collections.namedtuple("SlackInfo", ["token", "channel"])
Event = collections.namedtuple("Event", ["type", "object"])
ArtifactoryLogin = collections.namedtuple("ArtifactoryLogin", ["user", "password"])

OWN_NAMESPACE = os.getenv("OWN_NAMESPACE", "default-namespace")

class Kubernetes(object):
    def __init__(self, slack_info: SlackInfo,
            config_file: typing.Optional[str] = None,
            artifactory_url: typing.Optional[str] = None,
            artifactory_login: typing.Optional[str] = None):
        if config_file is None:
            kubernetes.config.load_incluster_config()
        else:
            kubernetes.config.load_kube_config(config_file=config_file)
        self.apps = kubernetes.client.AppsV1Api()
        self.slack_info = slack_info
        # slack only supports http proxies
        if os.getenv("http_proxy") is not None:
            self.slack_client = slack.WebClient(token=slack_info.token,
                proxy=os.getenv("http_proxy"))
        else:
            self.slack_client = slack.WebClient(token=slack_info.token)
        self.artifactory_login = None
        self.artifactory_url = artifactory_url
        if artifactory_login is not None:
            parts = artifactory_login.split(":")
            if len(parts) != 2:
                logger.warning(
                    "Artifactory login har wrong format. Split resulted in parts: {}"
                    .format(parts))
            else:
                self.artifactory_login = ArtifactoryLogin(parts[0], parts[1])

    def watch_for_changes(self, namespace: str):
        self.watch_for_deployment_changes(namespace)

    def watch_for_deployment_changes(self, namespace: str, wait: int = 5):
        logger.info("Watching namespace {}".format(namespace))
        events = self.get_events_file_from_artifactory(namespace)
        watch = kubernetes.watch.Watch()
        items = self.apps.list_namespaced_deployment(namespace)
        resource_version = items.metadata.resource_version
        for event in watch.stream(self.apps.list_namespaced_deployment,
                namespace, resource_version=resource_version):
            kube_object = event["object"]
            logger.info(f"Watching {kube_object.metadata.name}")
            if kube_object.status is not None and kube_object.spec is not None \
                    and kube_object.status.replicas == kube_object.spec.replicas:
                name = kube_object.metadata.name
                team = None
                logger.info(f"Found kube object with name {name} and {kube_object.spec.replicas} replicas")
                try:
                    if "app.dbc.dk/team" in kube_object.spec.template.metadata.labels:
                        team = kube_object.spec.template.metadata.labels["app.dbc.dk/team"]
                except Exception as err:
                    logger.error(f"Error - {err}")
                # the status object contains information on different
                # update transitions and number of ready replicas, etc.,
                # so it isn't used when comparing different deployment versions
                kube_object.status = None
                kube_object.metadata = None
                # This condition checks how long it has been since a change
                # was observed for a particular deployment. This is to avoid
                # repporting all the individual stages a dployment goes
                # through when it's modified by a user.
                if name in events and (events[name].type == event["type"] and events[name].object == kube_object):
                    logger.info(f"Skipping {name} with type {events[name].type}")
                    continue
                events[name] = Event(event["type"], kube_object)
                if self.artifactory_login is not None:
                    self.upload_events_to_artifactory(namespace, events)
                action = "deployed to" if event["type"] != "DELETED" else "deleted from"
                image = kube_object.spec.template.spec.containers[0].image
                msg = f"{name} {action} {namespace}\nImage: {image}"
                if team is not None:
                    msg = f"{msg}\nTeam: {team}"
                logger.info(msg)
                notify_slack(self.slack_client, self.slack_info.channel, msg)

    def get_events_file_from_artifactory(self, namespace: str) -> dict:
        if self.artifactory_login is not None:
            logger.info("getting events from artifactory")
            filename = f"deployment-events-{OWN_NAMESPACE}-{namespace}.pickle"
            url = f"{self.artifactory_url}/{filename}"
            response = requests.get(url, auth=(self.artifactory_login.user,
                self.artifactory_login.password))
            if response.status_code == 200:
                return pickle.load(io.BytesIO(response.content))
        return {}

    def upload_events_to_artifactory(self, namespace: str, events: dict) -> None:
        filename = f"deployment-events-{OWN_NAMESPACE}-{namespace}.pickle"
        url = f"{self.artifactory_url}/{filename}"
        fp = io.BytesIO()
        pickle.dump(events, fp)
        fp.seek(0)
        response = requests.put(url, auth=(self.artifactory_login.user,
            self.artifactory_login.password), data=fp)
        if response.status_code != 201:
            logger.error("Error uploading events to artifactory: {} - {}",
                response.status_code, response.reason)

def notify_slack(slack_client, channel: str, text: str):
    slack_client.chat_postMessage(channel=channel, text=text)

def main():
    args = setup_args()
    slack_info = SlackInfo(args.slack_token, args.slack_channel)
    kube = Kubernetes(slack_info, args.kubeconfig, args.artifactory_url, args.artifactory_login)
    # multiprocessing doesn't work very well here because the kube object
    # cannot be shared between processes because of it's ssl connection
    # and having different kube objects for each process results in an error
    # where a temporary file goes out of scope before being accessed when
    # setting the kube config.
    executor = concurrent.futures.ThreadPoolExecutor(max_workers=len(args.namespace))
    futures = []
    for n in args.namespace:
        futures.append(executor.submit(kube.watch_for_changes, n))
    concurrent.futures.wait(futures)
    error_happened = False
    for f in futures:
        error = f.exception()
        if error is not None:
            error_happened = True
            logger.error("An error happened: {}".format(error))
    if error_happened:
        sys.exit(1)

if __name__ == "__main__":
    main()
