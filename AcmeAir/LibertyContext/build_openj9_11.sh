#!/bin/bash
# Note: a mongo-acmeair image must already exist on the system
ACMEAIR_CONTAINER_NAME="liberty-acmeair:openj9_11"
DOCKERFILE="Dockerfile_openj9_11_acmeair"
NET_NAME="my-net"

function startMongo() 
{
  docker run --rm -d --name mongodb --network=$NET_NAME mongo-acmeair --nojournal && \
    sleep 1 && \
    docker exec mongodb mongorestore --drop /AcmeAirDBBackup		
}
function stopMongo()
{
  echo "Stopping mongodb container ..."
  docker stop mongodb
}

docker network create $NET_NAME
networkCreated=$?
stopMongo
sleep 1
startMongo
if [[ $? -eq 0 ]]; then
  docker build -m=1024m --network=$NET_NAME -f $DOCKERFILE -t $ACMEAIR_CONTAINER_NAME .
  stopMongo
else
  echo "liberty-acmeair container not created"
fi
# If a new network was created, delete it now
if [[ $networkCreated -eq 0 ]]; then 
  echo "Deleting docker network $NET_NAME"
  docker network rm $NET_NAME
fi


