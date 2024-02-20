podman run --rm -it -m=512m --cpus=1.0 -p 9080:9080 -e MONGO_HOST="mongodb" -e MONGO_PORT="27017" -e MONGO_DBNAME="acmeair" \
	--cap-add=CHECKPOINT_RESTORE --cap-add=SETPCAP --security-opt seccomp=unconfined  \
	--name acmeair localhost/liberty-acmeair-ee8:J17-20240202-instanon 

