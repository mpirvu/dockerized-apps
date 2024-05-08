# Dockerfile used for creating a container capable to run pingperf
FROM icr.io/appcafe/open-liberty:kernel-slim-java17-openj9-ubi

COPY --chown=1001:0 LibertyFiles/server.xml /config/server.xml
COPY --chown=1001:0 LibertyFiles/pingperf.war /config/apps/
EXPOSE 9080
RUN features.sh

#ENV OPENJ9_SCC=false
#ENV WARM_ENDPOINT=true
ENV VERBOSE=true
RUN configure.sh

