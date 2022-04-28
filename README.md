# deploy-notifier

Bot which notifies of new kubernetes deployments. It works by watching a
list of kubernetes namespaces for events and posts to slack when something new
happens.

## Config
The deployment monitor needs a kubernetes config in order to access
kubernetes. This can be a local file such as .kube/config. Or it can be
supplied by the kubernetes cluster itself if the deployment monitor is
deployed in the cluster and a service account, using the `serviceAccountName`
attribute, is configured.

## Cache
The deployment monitor keeps a cache of events it has seen to avoid
reporting the same event multiple times in case of restarts. This cache
is kept in a pickle file uploaded to artifactory.
