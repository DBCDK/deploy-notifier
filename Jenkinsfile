#! groovy

def workerNode = "xp-build-i01"

@Library('ai') _

pipeline {
	options {
		disableConcurrentBuilds()
	}
	agent { label workerNode }
	environment {
		ARTIFACTORY_LOGIN = credentials("artifactory_login")
		DOCKER_TAG = "${env.BRANCH_NAME}-${env.BUILD_NUMBER}"
		GITLAB_PRIVATE_TOKEN = credentials("ai-gitlab-api-token")
		SLACK_CHANNEL = "${env.BRANCH_NAME == 'main' ? '#ai-jenkins-warnings' : '#ai-jenkins-warnings-debug'}"
		PACKAGE="deploy-notifier"
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
				uvtest()
			}
		}
		stage("docker build") {
			steps {
                		buildImage()
			}
		}
		stage("set gitops variables for ai-staging") {
			when {
				branch "main"
			}
			steps {
				script {
					setGitopsVersion("ai-staging", "DEPLOY_NOTIFIER_1_0_VERSION", "${env.DOCKER_TAG}")
				}
			}
		}
		stage("set gitops variables for ai-prod") {
			when {
				branch "main"
			}
			steps {
				script {
					setGitopsVersion("ai-prod", "DEPLOY_NOTIFIER_1_0_VERSION", "${env.DOCKER_TAG}")
				}
			}
		}
	}
	post {
		unstable {
			slackSend message: "build became unstable for ${env.JOB_NAME}: ${env.BUILD_URL}", channel: env.SLACK_CHANNEL
		}
		failure {
			slackSend message: "build failed for ${env.JOB_NAME}: ${env.BUILD_URL}", channel: env.SLACK_CHANNEL
		}
	}
}
