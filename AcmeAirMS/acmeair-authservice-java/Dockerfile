FROM open-liberty:full

# Config
COPY --chown=1001:0 server.xml /config/server.xml
COPY --chown=1001:0 server.env /config/server.env
COPY --chown=1001:0 jvm.options /config/jvm.options
COPY --chown=1001:0 bootstrap.properties /config/bootstrap.properties

# key.p12 - all auth services need the same key.
COPY --chown=1001:0 key.p12 /output/resources/security/key.p12

# App
COPY --chown=1001:0 acmeair-authservice-java-4.0.war /config/apps/

# Logging vars
ENV LOGGING_FORMAT=simple
ENV ACCESS_LOGGING_ENABLED=false
ENV TRACE_SPEC=*=info

# Build SCC?
ARG CREATE_OPENJ9_SCC=true
ENV OPENJ9_SCC=${CREATE_OPENJ9_SCC}

RUN configure.sh


