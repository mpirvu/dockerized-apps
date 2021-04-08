docker run --rm -it --net=host -e JHOST=192.168.1.20 -e JPORT=8080 -e JTHREADS=100 -e JDURATION=300 -e JTHINKTIME=0 --name jmeter1 jmeterpetclinic:3.3 | tee results.txt

