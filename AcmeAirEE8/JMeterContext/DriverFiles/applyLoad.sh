#!/bin/bash
cd $JMETER_HOME

if [ ! -z "$JHOST" ]
  then
    sed -i 's/localhost/'$JHOST'/g' hosts.csv
fi
echo jmeter -n -DusePureIDs=true -t AcmeAir-v5.jmx -j /output/acmeair.stats.0 -JHOST=$JHOST -JPORT=$JPORT -JUSERBOTTOM=$JUSERBOTTOM -JUSER=$JUSER -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP 
exec jmeter -n -DusePureIDs=true -t AcmeAir-v5.jmx -j /output/acmeair.stats.0 -JHOST=$JHOST -JPORT=$JPORT -JUSERBOTTOM=$JUSERBOTTOM -JUSER=$JUSER -JURL=$JURL -JTHREAD=$JTHREAD -JDURATION=$JDURATION -JRAMP=$JRAMP 

