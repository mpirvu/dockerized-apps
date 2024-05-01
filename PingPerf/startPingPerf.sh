#!/bin/bash
date +"%H:%M:%S:%N"
docker run --rm -it -m=256m --cpus=4.0 --name pingperf -p 9080:9080  liberty-pingperf:J17

