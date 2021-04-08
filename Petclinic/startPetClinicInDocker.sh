export IMAGE_NAME="petclinic:openj9_11"
# Use JAVA_OPTS env var to apply command line options to the JVM
docker run -it --rm --cpus=4 -m=512m -p 8080:8080 -v /tmp/vlogDir:/tmp/vlogDir -e SERVER_SERVLET_CONTEXT_PATH="/petclinic" -e JAVA_OPTS="-Xtune:virtualized" --name petclinic $IMAGE_NAME
