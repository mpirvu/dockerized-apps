#!/bin/bash
# Note: a postgress container that listens on port 5432 needs to be running. Start it with
# docker run  --network=host -d --rm --memory-swappiness=0 --name postgres-quarkus-rest-http-crud -e POSTGRES_USER=restcrud -e POSTGRES_PASSWORD=restcrud -e POSTGRES_DB=rest-crud -p 5432:5432 postgres:10.5


QUARKUSLIB="$PWD/QuarkusFiles/lib.tar.gz"
QUARKUSLIBURL="https://github.com/mpirvu/dockerized-apps/files/6299870/lib.tar.gz"
if [ ! -f "$QUARKUSLIB" ]; then
    echo "$QUARKUSLIB does not exist. Downloading $QUARKUSLIBURL"
    if [[ `wget -S --spider $QUARKUSLIBURL  2>&1 | grep 'HTTP/1.1 200 OK'` ]]; then
        wget -O $QUARKUSLIB $QUARKUSLIBURL 
    else
        echo "$QUARKUSLIBURL does not exist. Aborting"
        exit 1
    fi
fi

QUARKUSAPP="$PWD/QuarkusFiles/rest-http-crud-quarkus-1.0.0.Alpha1-SNAPSHOT-runner.jar.tar.gz" 
QUARKUSAPPURL="https://github.com/mpirvu/dockerized-apps/files/6300029/rest-http-crud-quarkus-1.0.0.Alpha1-SNAPSHOT-runner.jar.tar.gz"
if [ ! -f "$QUARKUSAPP" ]; then
    echo "$QUARKUSAPP does not exist. Downloading $QUARKUSAPPURL"
    if [[ `wget -S --spider $QUARKUSAPPURL  2>&1 | grep 'HTTP/1.1 200 OK'` ]]; then
        wget -O $QUARKUSAPP $QUARKUSAPPURL
    else
        echo "$QUARKUSAPPURL does not exist. Aborting"
        exit 1
    fi
fi



docker build --network=host -f Dockerfile-quarkus-openj9-java11 -t rest-crud-quarkus:openj9_11 .
