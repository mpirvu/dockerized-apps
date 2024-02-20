#!/bin/bash
podman build -m=512m  -f Dockerfile_acmeair -t liberty-acmeair-ee8:J17-20240202 .

