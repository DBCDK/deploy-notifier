#!/usr/bin/env python3

from setuptools import setup

setup(name="deploy-notifier",
    version="0.1.0",
    package_dir={"": "src"},
    packages=["deploy_notifier"],
    description="Bot which notifies of new deployments",
    install_requires=["kubernetes", "slackclient"],
    entry_points = {
        "console_scripts": [
            "kube-monitor = deploy_notifier.kube_monitor:main",
        ]
    },
    test_suite="deploy_notifier.tests",
    provides=["deploy_notifier"],
    maintainer="ai",
    maintainer_email="ai@dbc.dk",
    zip_safe=False)
