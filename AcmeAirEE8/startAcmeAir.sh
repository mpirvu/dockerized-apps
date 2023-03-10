#!/bin/bash
# Note: a mongo-acmeair image must already exist on the system
ACMEAIR_IMAGE_NAME="liberty-acmeair-ee8:J17"
MONGO_IMAGE="mongo-acmeair-ee8:5.0.15"
NET_NAME="my-net"

function startMongo()
{
  docker run --rm -d --name mongodb --network=$NET_NAME $MONGO_IMAGE --nojournal && 
  sleep 1 && \
  docker exec -it mongodb mongorestore --drop /AcmeAirDBBackup
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
  # -e MONGO_MANUAL="true"
  docker run --rm -it -m=1G --cpus=4.0 --network=$NET_NAME --name acmeair -p 9080:9080 -e MONGO_HOST="mongodb" -e MONGO_PORT="27017" -e MONGO_DBNAME="acmeair" $ACMEAIR_IMAGE_NAME
  stopMongo
else
  echo "liberty-acmeair container not created"
fi
# If a new network was created, delete it now
if [[ $networkCreated -eq 0 ]]; then
  echo "Deleting docker network $NET_NAME"
  docker network rm $NET_NAME
fi

