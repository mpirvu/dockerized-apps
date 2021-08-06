#!/bin/bash

DT8EARFILE="$PWD/LibertyFiles/io.openliberty.sample.daytrader8.war"
URL="https://github.com/OpenLiberty/sample.daytrader8/releases/download/v1.2/io.openliberty.sample.daytrader8.war"
if [ ! -f "$DT8EARFILE" ]; then
    echo "$DT8EARFILE does not exist. Downloading $URL"
    if [[ `wget -S --spider $URL  2>&1 | grep 'HTTP/1.1 200 OK'` ]]; then
        wget -O $DT8EARFILE $URL
    else
        echo "$URL does not exist. Aborting"
        exit 1
    fi
fi

docker build  -f Dockerfile_websphereliberty_openj9_java8_dt8 -t liberty-dt8:openj9_8_0.26.0 .

