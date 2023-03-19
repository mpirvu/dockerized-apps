podman run --rm -it -m=1G --cpus=4.0 -p 9080:9080 -e MONGO_HOST="mongodb" -e MONGO_PORT="27017" -e MONGO_DBNAME="acmeair" --name acmeair \
   --cap-add=CHECKPOINT_RESTORE  --security-opt seccomp=unconfined  localhost/liberty-acmeair-ee8:J17-instanton 

