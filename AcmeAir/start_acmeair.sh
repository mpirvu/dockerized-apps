# The AcmeAir container assumes that a mongo database is available on a machine named mongodb
# We simulate this by running the acmeair container and the 
# mongo container (named mongodb) on the same network
# /tmp/vlogs directory can be used to store vlogs (-v /tmp/vlogs:/tmp/vlogs -e JVM_ARGS="-Xjit:verbose,vlog=/tmp/vlogs/vlog.txt" )
# Note that we must have write permissions for the directory on the host

docker network create mynet
docker run --rm -d --network=mynet --name mongodb mongo-acmeair --nojournal
sleep 2
docker exec -it mongodb mongorestore --drop /AcmeAirDBBackup
sleep 1
echo "Starting liberty-acmeair"
docker run -d --rm --network=mynet -m=512m --cpus=4  -p 9092:9090 -e JVM_ARGS="" --name acmeair liberty-acmeair:openj9_11
