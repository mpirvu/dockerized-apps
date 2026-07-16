docker run --rm -it -e JPORT=9080 -e JHOST=localhost -e JURL=/pingperf/ping/greeting -e JTHREAD=10 -e JTHINKTIME=0 -e JDURATION=600 --net=host --name jmeter jmeter_simple:5.5
