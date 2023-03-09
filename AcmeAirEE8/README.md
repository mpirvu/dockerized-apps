AcmeAir source code: https://github.com/blueperf/acmeair-monolithic-java

How to run:
* cd into LibertyContext and build the container for AcmeAir
* cd into JMeterContext and build the container for jmeter to apply load
* Edit startAcmeAir.sh to fit your needs and use it to launch a mongo and AcmeAir container
* Load the database with loadDatabase.sh script
* Edit runJMeter.sh to fit your needs and use it to apply load to AcmeAir
* Stop AcmeAir and mongo containers when done 


