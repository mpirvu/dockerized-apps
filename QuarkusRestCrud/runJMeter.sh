docker run --rm -it --net=host -e JHOST=192.168.1.9 -e JPORT=8080 -e JTHREADS=1 -e JDURATION=60 -e JRAMP=0 -e JTHINKTIME=0  --name jmeter1 jmeterquark:3.3
