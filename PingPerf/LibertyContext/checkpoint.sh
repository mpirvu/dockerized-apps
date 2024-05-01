#!/bin/bash
set -e
set -o pipefail
set -x
# The following is my normal image without instantON
DEFAULT_IMAGE_NAME="liberty-pingperf:J17"
# The following is my image with InstantON
INSTANT_ON_IMAGE_NAME="liberty-pingperf:J17-instanton"

docker run --name my-container -m 512m --cpus=1.0 -e _JAVA_OPTIONS=""  --privileged -e WLP_CHECKPOINT=afterAppStart $DEFAULT_IMAGE_NAME
docker commit my-container $INSTANT_ON_IMAGE_NAME
docker rm my-container

