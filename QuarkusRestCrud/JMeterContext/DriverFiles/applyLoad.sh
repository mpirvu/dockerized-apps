#!/bin/bash
cd $JMETER_HOME
exec jmeter -n -t jmeter_restcrud.quarkus.jmx -j /output/daytrader.stats -JHOST=$JHOST  -JPORT=$JPORT -JTHREADS=$JTHREADS -JDURATION=$JDURATION -JTHINKTIME=$JTHINKTIME -JRAMP=$JRAMP -JROOT=$JROOT

