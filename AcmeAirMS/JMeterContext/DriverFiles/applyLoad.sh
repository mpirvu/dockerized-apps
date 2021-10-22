#!/bin/bash
cd $JMETER_HOME

echo jmeter -n -DusePureIDs=true -t AcmeAir-microservices-mpJwt.jmx -j /output/acmeair.stats.0 -JHOST=$JHOST -JPORT=$JPORT -JUSERBOTTOM=$JUSERBOTTOM -JUSER=$JUSER -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP 
exec jmeter -n -DusePureIDs=true -t AcmeAir-microservices-mpJwt.jmx -j /output/acmeair.stats.0 -JHOST=$JHOST -JPORT=$JPORT -JUSERBOTTOM=$JUSERBOTTOM -JUSER=$JUSER -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP

