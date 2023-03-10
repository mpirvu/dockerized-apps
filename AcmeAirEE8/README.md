AcmeAir source code: https://github.com/blueperf/acmeair-monolithic-java

How to run:
* cd into MongoContext and build the mongodb container image
* cd into LibertyContext and build the container image for AcmeAir
* cd into JMeterContext and build the container image for jmeter to apply load
* Edit startAcmeAir.sh to fit your needs and use it to launch a mongo and AcmeAir container
* Edit runJMeter.sh to fit your needs and use it to apply load to AcmeAir
* Stop AcmeAir and mongo containers when done 


