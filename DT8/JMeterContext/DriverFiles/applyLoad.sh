#!/bin/bash
cd $JMETER_HOME

echo jmeter -n -t daytrader8.jmx -j /output/daytrader.stats -JHOST=$JHOST  -JPORT=$JPORT -JSTOCKS=$JSTOCKS -JBOTUID=$JBOTUID -JTOPUID=$JTOPUID -JTHREADS=$JTHREADS -JDURATION=$JDURATION -JRAMP=$JRAMP -JMAXTHINKTIME=$JMAXTHINKTIME
exec jmeter -n -t daytrader8.jmx -j /output/daytrader.stats -JHOST=$JHOST  -JPORT=$JPORT -JSTOCKS=$JSTOCKS -JBOTUID=$JBOTUID -JTOPUID=$JTOPUID -JTHREADS=$JTHREADS -JDURATION=$JDURATION -JRAMP=$JRAMP -JMAXTHINKTIME=$JMAXTHINKTIME

