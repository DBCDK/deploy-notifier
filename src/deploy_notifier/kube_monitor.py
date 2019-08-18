#!/usr/bin/env python3

# https://github.com/kubernetes-client/python

import argparse
import concurrent.futures
import datetime
import typing

import kubernetes

def setup_args():
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--kubeconfig")
    parser.add_argument("namespace", nargs="+")
    return parser.parse_args()

class Kubernetes(object):
    def __init__(self, config_file: typing.Optional[str] = None):
        if config_file is None:
            kubernetes.config.load_incluster_config()
        else:
            kubernetes.config.load_kube_config(config_file=config_file)
        self.apps = kubernetes.client.AppsV1Api()

    def watch_for_changes(self, namespace: str):
        self.watch_for_deployment_changes(namespace)

    def watch_for_deployment_changes(self, namespace: str, wait: int = 5):
        print("Watching namespace {}".format(namespace))
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
                print(namespace, kube_object.spec.template.spec.containers[0].image, event["type"])

def main():
    args = setup_args()
    kube = Kubernetes(args.kubeconfig)
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

if __name__ == "__main__":
    main()
