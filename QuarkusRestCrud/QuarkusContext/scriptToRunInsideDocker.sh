#!/bin/sh
date +"%H:%M:%S:%N" && java $JAVA_OPTS -Djava.net.preferIPv4Stack=true -jar rest-http-crud-quarkus-1.0.0.Alpha1-SNAPSHOT-runner.jar 
