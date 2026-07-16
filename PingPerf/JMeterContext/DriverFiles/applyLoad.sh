#!/bin/bash
cd $JMETER_HOME

echo jmeter -n -t simple_waittime.jmx -j /output/stats.txt -JHOST=$JHOST  -JPORT=$JPORT -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP -JTHINKTIME=$JTHINKTIME
exec jmeter -n -t simple_waittime.jmx -j /output/stats.txt -JHOST=$JHOST  -JPORT=$JPORT -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP -JTHINKTIME=$JTHINKTIME


