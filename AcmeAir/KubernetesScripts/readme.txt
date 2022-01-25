Generate ingress
Generate mongo deployment
Load the database
Generate acmeair deployment and service
Apply load from outside teh cluster with something like 
docker run --rm --net=host  -e JTHREAD=1 -e JDURATION=60 -e JPORT=80 -e JUSERBOTTOM=0  -e JUSER=199 --name jmeter1 jmeter-acmeair:3.3 192.168.1.20
The port needs to be 80 because we use ingress with nginx

