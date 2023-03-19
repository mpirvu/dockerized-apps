#!/bin/bash
set -e 
set -o pipefail
set -x
ACMEAIR_DEFAULT_IMAGE_NAME="localhost/liberty-acmeair-ee8:J17-podman"
ACMEAIR_INSTANT_ON_IMAGE_NAME="localhost/liberty-acmeair-ee8:J17-instanton"

#!/bin/bash
podman build -m=1024m --cap-add=CHECKPOINT_RESTORE --cap-add=SETPCAP --security-opt seccomp=unconfined -f Dockerfile_acmeair_instanton -t $ACMEAIR_DEFAULT_IMAGE_NAME .
podman run --name my-container --privileged --env WLP_CHECKPOINT=applications $ACMEAIR_DEFAULT_IMAGE_NAME
echo "Comitting..."
podman commit my-container $ACMEAIR_INSTANT_ON_IMAGE_NAME
podman rm my-container


