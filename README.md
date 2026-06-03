# deploy-notifier

Bot which notifies of new kubernetes deployments. It works by watching a
list of kubernetes namespaces for events and posts to slack when something new
happens.

## Config
The deployment monitor needs a kubernetes config in order to access
kubernetes. This can be a local file such as `.kube/config`. Or it can be
supplied by the kubernetes cluster itself if the deployment monitor is
deployed in the cluster and a service account, using the `serviceAccountName`
attribute, is configured.

## Cache
The deployment monitor keeps a cache of events it has seen to avoid
reporting the same event multiple times in case of restarts. This cache
is stored as a JSON file in Artifactory.

### File location

The cache file is uploaded to and retrieved from Artifactory at:

```
<ARTIFACTORY_URL>/deployment-events-v<VERSION>-<OWN_NAMESPACE>-<namespace>.json
```

- `ARTIFACTORY_URL` — the Artifactory base URL configured for the service
- `VERSION` — the cache schema version (currently `2`); bumped whenever the format changes to prevent pods from reading a stale or incompatible cache
- `OWN_NAMESPACE` — the namespace the deploy-notifier itself runs in (from the `OWN_NAMESPACE` environment variable, defaulting to `default-namespace`)
- `namespace` — the kubernetes namespace being watched

Example filename for a notifier running in `platform` watching the `ai-prod` namespace:

```
deployment-events-v2-platform-ai-prod.json
```

### JSON format

```json
{
  "events": {
    "<deployment-name>": {
      "type": "<ADDED|MODIFIED|DELETED>",
      "object": {
        "spec": { ... },
        "metadata": null,
        "status": null
      }
    }
  }
}
```

Each key under `events` is the name of a Kubernetes Deployment. The `type`
field is the watch event type (`ADDED`, `MODIFIED`, or `DELETED`). The
`object` field is a snapshot of the deployment's spec as returned by the
Kubernetes API (`to_dict()`), with `metadata` and `status` set to `null` —
these fields are excluded because they change continuously as part of
Kubernetes reconciliation and would otherwise cause every reconciliation
loop to be reported as a new deployment.

The cache is read on startup and written after every event that triggers a
Slack notification. If the file is missing or cannot be parsed, the notifier
starts with an empty cache and behaves as if it has never seen any
deployments before.