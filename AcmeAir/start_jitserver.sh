docker run -d --rm --network=mynet -m=2G --cpus=4  -p 38400:38400 -e _JAVA_OPTIONS="-XX:+JITServerLogConnections" --name jitserver jitserver:11

