#!/bin/bash
set -e
set -o pipefail
set -x
# The following is my normal image without instantON
ACMEAIR_DEFAULT_IMAGE_NAME="liberty-acmeair-ee8:J17-20240202"
# The following is my image with InstantON
ACMEAIR_INSTANT_ON_IMAGE_NAME="liberty-acmeair-ee8:J17-20240202-instanon"

podman run --name my-container -m 512m --cpus=1.0 -e _JAVA_OPTIONS="" -e MONGO_HOST="9.46.116.36" -e MONGO_PORT="27017" -e MONGO_DBNAME="acmeair" --privileged -e WLP_CHECKPOINT=afterAppStart $ACMEAIR_DEFAULT_IMAGE_NAME
podman commit my-container $ACMEAIR_INSTANT_ON_IMAGE_NAME
podman rm my-container

