#!/usr/bin/env python3

# https://github.com/kubernetes-client/python

import argparse
import collections
import concurrent.futures
import datetime
import logging
import sys
import typing

import kubernetes
import pyutils
import slack

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--kubeconfig")
    parser.add_argument("--slack-token", required=True)
    parser.add_argument("--slack-channel", required=True)
    parser.add_argument("namespace", nargs="+")
    return parser.parse_args()

def setup_logging():
    logger = logging.getLogger()
    handler = logging.StreamHandler()
    handler.setFormatter(pyutils.JSONFormatter())
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    return logger

logger = setup_logging()

SlackInfo = collections.namedtuple("SlackInfo", ["token", "channel"])

class Kubernetes(object):
    def __init__(self, slack_info: SlackInfo, config_file: typing.Optional[str] = None):
        if config_file is None:
            kubernetes.config.load_incluster_config()
        else:
            kubernetes.config.load_kube_config(config_file=config_file)
        self.apps = kubernetes.client.AppsV1Api()
        self.slack_info = slack_info
        self.slack_client = slack.WebClient(token=slack_info.token)

    def watch_for_changes(self, namespace: str):
        self.watch_for_deployment_changes(namespace)

    def watch_for_deployment_changes(self, namespace: str, wait: int = 5):
        logger.info("Watching namespace {}".format(namespace))
        events = {}
        watch = kubernetes.watch.Watch()
        items = self.apps.list_namespaced_deployment(namespace)
        resource_version = items.metadata.resource_version
        for event in watch.stream(self.apps.list_namespaced_deployment,
                namespace, resource_version=resource_version):
            kube_object = event["object"]
            if kube_object.status.replicas == kube_object.spec.replicas:
                name = kube_object.metadata.name
                # This condition checks how long it has been since a change
                # was observed for a particular deployment. This is to avoid
                # repporting all the individual stages a dployment goes
                # through when it's modified by a user.
                if name in events and (datetime.datetime.now() - events[name]) < datetime.timedelta(seconds=wait):
                    continue
                events[name] = datetime.datetime.now()
                s = "{} {} {}".format(namespace,
                    kube_object.spec.template.spec.containers[0].image,
                    event["type"])
                logger.info(s)
                notify_slack(self.slack_client, self.slack_info.channel, s)

def notify_slack(slack_client, channel: str, text: str):
    slack_client.chat_postMessage(channel=channel, text=text)

def main():
    args = setup_args()
    slack_info = SlackInfo(args.slack_token, args.slack_channel)
    kube = Kubernetes(slack_info, args.kubeconfig)
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
