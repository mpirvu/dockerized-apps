# Add JRAMP=NNN JMAXTHINKTIME=NNN to control 'thinkTime' between requests
docker run -it --rm --net=host -e JHOST=192.168.1.9 -e JPORT=9080 -e JTHREADS=50 -e JDURATION=600 -e JSTOCKS=9999 -e JBOTID=0 -e JTOPID=14999 --name jmeter1 jmeter_dt8:3.3 


