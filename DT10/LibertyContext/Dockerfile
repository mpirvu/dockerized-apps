FROM icr.io/appcafe/open-liberty:full-java25-openj9-ubi-minimal

COPY --chown=1001:0 LibertyFiles/server.xml /config/server.xml

# Install required features 
RUN features.sh

# Copy the required files
COPY --chown=1001:0 LibertyFiles/server.env /config/server.env
COPY --chown=1001:0 LibertyFiles/io.openliberty.sample.daytrader10.war /config/apps/
COPY --chown=1001:0 LibertyFiles/bootstrap.properties /config/bootstrap.properties

#Derby
COPY --chown=1001:0 LibertyFiles/derby-10.14.2.0.jar /opt/ol/wlp/usr/shared/resources/DerbyLibs/derby-10.14.2.0.jar
COPY --chown=1001:0 LibertyFiles/data /opt/ol/wlp/usr/shared/resources/

ENV VERBOSE=true
RUN configure.sh
