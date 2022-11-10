#!/usr/bin/env bash

KUBE_CONFIG_ARG=
if test "$KUBE_CONFIG" != ""; then
	KUBE_CONFIG_ARG="-c $KUBE_CONFIG"
fi

ARTIFACTORY_DEST=
if test "$ARTIFACTORY_URL" != ""; then
	ARTIFACTORY_DEST="--artifactory-url $ARTIFACTORY_URL"
fi

ARTIFACTORY_ARG=
if test "$ARTIFACTORY_LOGIN" != ""; then
	ARTIFACTORY_ARG="--artifactory-login $ARTIFACTORY_LOGIN"
fi

kube-monitor $NAMESPACES $KUBE_CONFIG_ARG --slack-token $SLACK_TOKEN --slack-channel $SLACK_CHANNEL $ARTIFACTORY_DEST $ARTIFACTORY_ARG
