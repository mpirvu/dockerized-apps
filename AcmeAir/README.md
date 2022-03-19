* cd into MongoContext and the build the mongo container
* cd into LibertyContext and build the container for AcmeAir
* cd into JMeterContext and build the container for jmeter to apply load
* Edit start_acmeair.sh to fit your needs and use it to launch a mongo and AcmeAir container
* Edit runJMeter.sh to fit your needs and use it to apply load to AcmeAir
* Stop AcmeAir and mongo containers when done 

Note: To offload JIT compilations to an OpenJ9 JITServer, build the JITServer
container by going into JITServerContext directory and execute the corresponding
build command. Important: the OpenJ9 version from the JITServer container must match
the OpenJ9 version from the Liberty container.
Connect the Liberty container to JITServer by providing additional options to
the Liberty container
 -e JVM_ARGS="-XX:+UseJITServer -XX:JITServerAddress=jitserver_machine -XX:+JITServerLogConnections"
The option -XX:+JITServerLogConnections will make the JVM from the Liberty
container to output a message to stderr every time a connection to the 
JITServer is established. E.g.:
#JITServer: t=     0 Connected to a server (serverUID=5533460445728875299)

