#!/usr/bin/env bash

source ENV/bin/activate

KUBE_CONFIG_ARG=
if test "$KUBE_CONFIG" != ""; then
	KUBE_CONFIG_ARG="-c $KUBE_CONFIG"
fi

kube-monitor $NAMESPACES $KUBE_CONFIG_ARG --slack-token $SLACK_TOKEN --slack-channel $SLACK_CHANNEL
