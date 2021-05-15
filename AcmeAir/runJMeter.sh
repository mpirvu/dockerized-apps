#!/bin/bash
# The last parameter in the line below is the IP of the machine where liberty runs
# Output is written to  /output/acmeair.stats.0 inside the container
docker run --rm --net=host  -e JTHREAD=1 -e JDURATION=60 -e JPORT=9092 -e JUSERBOTTOM=0  -e JUSER=199 --name jmeter1 jmeter-acmeair:3.3 192.168.1.9


