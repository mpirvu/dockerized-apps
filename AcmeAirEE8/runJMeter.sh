#!/bin/bash
# Output is written to  /output/acmeair.stats.0 inside the container
# -e JURL="/" 
docker run --rm -it --net=my-net  -e JTHREAD=10 -e JDURATION=60 -e JHOST="acmeair" -e JPORT=9080  -e JUSER=999 -e JRAMP=0 --name jmeter1 jmeter-acmeair:5.3


