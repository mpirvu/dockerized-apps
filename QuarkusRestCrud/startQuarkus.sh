#-e JAVA_OPTS="-XX:+useJITserver"
docker run --rm -d -e HOST="192.168.1.9" -p 8080:8080 --name quarkus rest-crud-quarkus:openj9_11
