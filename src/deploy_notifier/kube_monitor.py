#!/usr/bin/env python3

# https://github.com/kubernetes-client/python

import argparse
import collections
import concurrent.futures
import json
import logging
import os
import sys
import typing

import kubernetes
from kubernetes.client.exceptions import ApiException
from kubernetes.client import Configuration
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
EVENTS_CACHE_VERSION = 2

def get_events_filename(namespace: str) -> str:
    return f"deployment-events-v{EVENTS_CACHE_VERSION}-{OWN_NAMESPACE}-{namespace}.json"

def snapshot_deployment(kube_object) -> dict:
    snapshot = kube_object.to_dict()
    # Ignore fields that change as part of Kubernetes reconciliation and watch progress.
    snapshot["metadata"] = None
    snapshot["status"] = None
    return snapshot

def serialize_events(events: dict) -> str:
    payload = {"events": {}}
    for name, event in events.items():
        payload["events"][name] = {"type": event.type, "object": event.object}
    return json.dumps(payload, sort_keys=True)

def deserialize_events(payload: str) -> dict:
    data = json.loads(payload)
    events = {}
    for name, event in data.get("events", {}).items():
        if "type" not in event or "object" not in event:
            logger.warning("Skipping malformed cached event for %s", name)
            continue
        events[name] = Event(event["type"], event["object"])
    return events

class Kubernetes(object):
    def __init__(self, slack_info: SlackInfo,
            config_file: typing.Optional[str] = None,
            artifactory_url: typing.Optional[str] = None,
            artifactory_login: typing.Optional[str] = None):
        if config_file is None:
            kubernetes.config.load_incluster_config()
        else:
            kubernetes.config.load_kube_config(config_file=config_file)

        # IMPORTANT: disable proxy for Kubernetes client, so internal kubernetes calls are not sent through proxy
        cfg = Configuration.get_default_copy()
        cfg.proxy = None
        cfg.proxy_headers = None
        Configuration.set_default(cfg)

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
        try:
            for event in watch.stream(self.apps.list_namespaced_deployment,
                    namespace, resource_version=resource_version):
                kube_object = event["object"]
                if kube_object.status is not None and kube_object.spec is not None \
                        and kube_object.status.replicas == kube_object.spec.replicas:
                    name = kube_object.metadata.name
                    team = None
                    logger.info(f"Found kube object with name {name} and {kube_object.spec.replicas} replicas")
                    if "app.dbc.dk/team" in kube_object.spec.template.metadata.labels:
                        team = kube_object.spec.template.metadata.labels["app.dbc.dk/team"]
                    deployment_snapshot = snapshot_deployment(kube_object)
                    # This condition checks how long it has been since a change
                    # was observed for a particular deployment. This is to avoid
                    # repporting all the individual stages a dployment goes
                    # through when it's modified by a user.
                    if name in events and (events[name].type == event["type"] and events[name].object == deployment_snapshot):
                        logger.info(f"Skipping {name} with type {events[name].type}")
                        continue
                    events[name] = Event(event["type"], deployment_snapshot)
                    if self.artifactory_login is not None:
                        self.upload_events_to_artifactory(namespace, events)
                    action = "deployed to" if event["type"] != "DELETED" else "deleted from"
                    image = kube_object.spec.template.spec.containers[0].image
                    msg = f"{name} {action} {namespace}\nImage: {image}"
                    if team is not None:
                        msg = f"{msg}\nTeam: {team}"
                    logger.info(msg)
                    notify_slack(self.slack_client, self.slack_info.channel, msg)
        except ApiException as e:
            if e.status == 410: # Resource too old
                logger.info(f"An error happened: {e} - Restarting watch.")
                return self.watch_for_changes(namespace)
            else:
                raise

    def get_events_file_from_artifactory(self, namespace: str) -> dict:
        if self.artifactory_login is not None:
            logger.info("getting events from artifactory")
            filename = get_events_filename(namespace)
            url = f"{self.artifactory_url}/{filename}"
            response = requests.get(url, auth=(self.artifactory_login.user,
                self.artifactory_login.password))
            if response.status_code == 200:
                try:
                    return deserialize_events(response.text)
                except (TypeError, ValueError) as error:
                    logger.warning("Ignoring invalid cached deployment events for %s: %s",
                        namespace, error)
        return {}

    def upload_events_to_artifactory(self, namespace: str, events: dict) -> None:
        filename = get_events_filename(namespace)
        url = f"{self.artifactory_url}/{filename}"
        payload = serialize_events(events)
        response = requests.put(url, auth=(self.artifactory_login.user,
            self.artifactory_login.password), data=payload,
            headers={"Content-Type": "application/json"})
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
