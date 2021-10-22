Steps to build AcmeAir Microservices and run the application using docker-compose (reference https://github.com/blueperf)

1. Install docker and docker-compose
Example:
```
sudo curl -L "https://github.com/docker/compose/releases/download/1.29.2/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
sudo chmod +x /usr/local/bin/docker-compose
```

2. Create docker network:
```
    docker network create --driver bridge my-net
```

3. Build containers: This will build all the micro-services, mongo db instances, and an nginx proxy.
```
    cd acmeair-mainservice-java
    docker-compose  build
```
4. Build JMeter container:
```
cd JMeterContext
./build_jmeter.sh
```
Note: Steps 1-4 should be done only once

5. Start containers: 
```
./startAcmeAirMS.sh
```
Internally, this will change the directory to `acmeair-mainservice-java` and call `NETWORK=my-net docker-compose up -d`

6. Verify that application started correctly.
From `acmeair-mainservice-java` directory execute:
```
    docker-compose ps
    docker-compose logs
```

7. Optional: Verify everything is ok by accesing:    http://localhost/acmeair

8. Load the Database (replace MACHINE_IP with IP of the machine where app is running)
```
./loadDatabases.sh MACHINE_IP
```

9. Modify `runJMeter.sh` script as appropriate and run it to apply load on the application.
In particular, JHOST needs to be set to the IP of the machine where the application is running

