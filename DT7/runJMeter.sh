# Add JRAMP=NNN JMAXTHINKTIME=NNN to control thread rampup and 'thinkTime' between requests
docker run -it --rm --net=host -e JHOST=192.168.1.9 -e JPORT=9080 -e JTHREADS=50 -e JDURATION=600 --name jmeter1 jmeter_dt7


