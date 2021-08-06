* cd into LibertyContext and build the container for DT8
* cd into JMeterContext and build the container for jmeter to apply load
* Start DB2
* Edit run_liberty_dt8.sh to fit your needs (set tradeDbHost,tradeDbPort,dbUser,dbPass) and use it to launch a DT8 container
* Edit runJMeter.sh to fit your needs and use it to apply load to DT8

