docker run --rm -it -m=512m --cpus=1.0 -p 9080:9080  \
	--cap-add=CHECKPOINT_RESTORE --cap-add=SETPCAP --security-opt seccomp=unconfined  \
	--name pingperf liberty-pingperf:J17-instanton 

