import unittest

from deploy_notifier.kube_monitor import snapshot_deployment


class TestSnapshotDeployment(unittest.TestCase):
    def test_ignores_metadata_and_status(self):
        class Deployment:
            def to_dict(self):
                return {
                    "metadata": {"name": "example"},
                    "spec": {"replicas": 2},
                    "status": {"available_replicas": 2},
                }

        snapshot = snapshot_deployment(Deployment())

        self.assertEqual(
            snapshot,
            {
                "metadata": None,
                "spec": {"replicas": 2},
                "status": None,
            },
        )


if __name__ == "__main__":
    unittest.main()
