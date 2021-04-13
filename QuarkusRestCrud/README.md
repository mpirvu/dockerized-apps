Based on https://github.com/johnaohara/quarkusRestCrudDemo
## Building Quarkus container
- Start postgres on the host network:\
`docker run --network=host -d --rm --name postgres-quarkus-rest-http-crud -e POSTGRES_USER=restcrud -e POSTGRES_PASSWORD=restcrud -e POSTGRES_DB=rest-crud postgres:10.5`
- `cd QuarkusContext`
- `./build-quarkus-openj9.sh`
- Shutdown postgres container: `docker stop postgres-quarkus-rest-http-crud`

## Building JMeter container
- `cd JMeterContext`
- `./build_jmeter.sh`

## Running Quarkus CRUD app
- Start postgres container: `./startPostgres.sh`
- Edit "startQuarkus.sh" to change the IP for the postgres container: `-e HOST=...`
- Optional: add any JVM options with `-e JAVA_OPTS="..."`
- Lanch quarkus container: `./startQuarkus.sh`
- Verify container started successfully by looking at the logs: `docker logs quarkus`

## Testing the app
Access the application at `http://host_ip/quarkuscrud/fruits` which should return a list of 3 fruits

## Applying load with JMeter
Edit `runJMeter.sh` to change:
- Host of the quarkus app: `JHOST=...`
- Port of the quarkus app: `JPORT=8080`
- Number of client threads: `JTHREADS=1`
- Duration of the test in seconds: `JDURATION=60`
- Number of seconds between JMeter thread starts: `JRAMP=0`
- "Think time for each JMeter thread (in ms): `JTHINKTIME=0`

Launch: `./runJMeter.sh`

