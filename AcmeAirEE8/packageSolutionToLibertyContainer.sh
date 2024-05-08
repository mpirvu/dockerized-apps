# Script to take the code for a JDK, zip it up and containerize it together with Open Libertyy and AcmeAirEE8.
# Pre-requisites:
# - Need to clone the semeru-containers repo: https://github.com/ibmruntimes/semeru-containers.git
#   - Need to change oe of the Dockerfiles in there to copy the zipped JDK into /tmp (in container) instead
#     of downloading the JDK from internet. CRIU may need similar treatment
# - Need to clone the Liberty containers repo: https://github.com/OpenLiberty/ci.docker.git
#     Note that the version you cloned my not have a Dockerfile for the intended Liberty version

set -Eeox pipefail

# Modify the following environment variables as appropriate
export JDK_IMAGE="/home/mpirvu/FullJava17/openj9-openjdk-jdk17/build/linux-x86_64-server-release/images"
export SEMERU_CONTAINERS_DIR="/home/mpirvu/gitrepo/semeru-containers/17/jdk/ubi/ubi9"
export OPENJ9_TAG="J17-20240505"
export LIBERTY_RELEASE="24.0.0.3"
export LIBERTY_CONTAINERS_DIR="/home/mpirvu/gitrepo/LibertyCustomContainers/ci.docker/releases/$LIBERTY_RELEASE/kernel-slim"
export LIBERTY_ACMEAIR_DIR="/home/mpirvu/gitrepo/dockerized-apps/AcmeAirEE8/LibertyContext"

# The following are automatically determined
export OPENJ9_IMAGE_NAME="openj9:$OPENJ9_TAG"
export LIBERTY_TAG="$LIBERTY_RELEASE-$OPENJ9_TAG"
export LIBERTY_IMAGE_NAME="liberty:$LIBERTY_TAG"
export ACMEAIR_IMAGE_NAME="acmeairee8:$LIBERTY_TAG"
export ACMEAIR_INSTANTON_IMAGE_NAME="acmeairee8:$LIBERTY_TAG-instanton"

# Go the images directory and zip my jdk
cd $JDK_IMAGE
tar cvfz jdk.tar.gz jdk

# Move the JDK under the Semeru Containers and create the Semeru container
cd $SEMERU_CONTAINERS_DIR
mv $JDK_IMAGE/jdk.tar.gz .
docker build --progress plain -f Dockerfile.open.releases.full.local -t $OPENJ9_IMAGE_NAME .

# Create the Liberty container
cd $LIBERTY_CONTAINERS_DIR
# Replace what comes after "FROM" with image name $OPENJ9_IMAGE_NAME
# The pattern is:  FROM followed by whitespace followed by non-whitespace
sed -i "s/^FROM[[:space:]]\+[^[:space:]]\+/FROM $OPENJ9_IMAGE_NAME/g"  Dockerfile.ubi.openjdk17
docker build --progress=plain -f Dockerfile.ubi.openjdk17 -t $LIBERTY_IMAGE_NAME .

# Create the acmeair container
cd $LIBERTY_ACMEAIR_DIR
sed -i "s/^FROM[[:space:]]\+[^[:space:]]\+/FROM $LIBERTY_IMAGE_NAME/g"  Dockerfile_acmeair
docker build --progress=plain -m=512m  -f Dockerfile_acmeair -t $ACMEAIR_IMAGE_NAME .

#Create the InstantON image
#-e _JAVA_OPTIONS="-Dopenj9.internal.criu.ghostFileLimit=2097152"
#docker run --name my-container -m 512m --cpus=1.0 -e MONGO_HOST="localhost" -e MONGO_PORT="27017" -e MONGO_DBNAME="acmeair" --privileged -e WLP_CHECKPOINT=afterAppStart $ACMEAIR_IMAGE_NAME
#docker commit my-container $ACMEAIR_INSTANTON_IMAGE_NAME
#docker rm my-container


# Delete the old image from Kubernetes and tag the new one
#microk8s ctr images delete localhost:32000/$ACMEAIR_IMAGE_NAME
#docker tag $ACMEAIR_IMAGE_NAME localhost:32000/$ACMEAIR_IMAGE_NAME
#docker push localhost:32000/$ACMEAIR_IMAGE_NAME

