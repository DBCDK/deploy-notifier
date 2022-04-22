#! groovy

def workerNode = "xp-build-i01"

pipeline {
	agent { label workerNode }
	environment {
		ARTIFACTORY_LOGIN = credentials("artifactory_login")
		DOCKER_TAG = "${env.BRANCH_NAME}-${env.BUILD_NUMBER}"
		GITLAB_PRIVATE_TOKEN = credentials("ai-gitlab-api-token")
	}
    triggers {
	upstream(upstreamProjects: 'Docker-base-python3,Docker-base-python3-bump-trigger', threshold: hudson.model.Result.SUCCESS)
    }
    stages {
		stage("test") {
			agent {
				docker {
					label workerNode
					image "docker-dbc.artifacts.dbccloud.dk/build-env"
					alwaysPull true
				}
			}
			steps {
				sh """#!/usr/bin/env bash
					set -xe
					rm -rf env
					python3 -m venv env
					source env/bin/activate
					pip install --upgrade pip
					pip install pytest-cov
					pip install .
					make-build-info
				"""
			}
		}
		stage("upload wheel package") {
			agent {
				docker {
					label workerNode
					image "docker-dbc.artifacts.dbccloud.dk/build-env"
					alwaysPull true
				}
			}
			when {
				branch "master"
			}
			steps {
				// unstash "build-stash"
				sh """#!/usr/bin/env bash
					set -xe
					rm -rf dist
					make-build-info
					python3 setup.py egg_info --tag-build=${env.BUILD_NUMBER} bdist_wheel
					twine upload -u $ARTIFACTORY_LOGIN_USR -p $ARTIFACTORY_LOGIN_PSW --repository-url https://artifactory.dbc.dk/artifactory/api/pypi/pypi-dbc dist/*
				"""
			}
		}
		stage('build'){
			steps {
				script {
					def tag = 'deploy-notifier'
					app = docker.build("$tag:${DOCKER_TAG}", "--pull --no-cache --build-arg BRANCH_NAME=${BRANCH_NAME} .")
				}
			}
		}
		stage('push') {
			steps {
				script {
					docker.withRegistry('https://docker-ai.artifacts.dbccloud.dk', 'docker') {
						app.push()
						app.push('latest')
					}
				}
			}
		}
		stage("update staging version number") {
			agent {
				docker {
					label workerNode
					image "docker-dbc.artifacts.dbccloud.dk/build-env"
					alwaysPull true
				}
			}
			when {
				branch "master"
			}
			steps {
				sh "set-new-version deploy-notifier-1-0.yml ${env.GITLAB_PRIVATE_TOKEN} ai/deploy-notifier-secrets ${env.DOCKER_TAG} -b staging"
				build job: "ai/deploy-notifier-deploy/staging", wait: true
			}
		}
		stage("update prod version number") {
			agent {
				docker {
					label workerNode
					image "docker-dbc.artifacts.dbccloud.dk/build-env"
					alwaysPull true
				}
			}
			when {
				branch "master"
			}
			steps {
				sh "set-new-version deploy-notifier-1-0.yml ${env.GITLAB_PRIVATE_TOKEN} ai/deploy-notifier-secrets ${env.DOCKER_TAG} -b prod"
				build job: "ai/deploy-notifier-deploy/prod", wait: true
			}
		}

	}
}
