#!/bin/bash

DT7EARFILE="$PWD/LibertyFiles/daytrader-ee7.ear"
URL="https://github.com/WASdev/sample.daytrader7/releases/download/v1.4/daytrader-ee7.ear"
if [ ! -f "$DT7EARFILE" ]; then
    echo "$DT7EARFILE does not exist. Downloading $URL"
    if [[ `wget -S --spider $URL  2>&1 | grep 'HTTP/1.1 200 OK'` ]]; then
        wget -O $DT7EARFILE $URL
    else
        echo "$URL does not exist. Aborting"
        exit 1
    fi
fi

docker build  -f Dockerfile_liberty_openj9_java11_dt7 -t liberty-dt7:openj9_11 .

