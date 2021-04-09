# set db2ip to the address of the machine where DB2 is located
docker run --rm -it -e db2ip="192.168.1.7"  -p 9080:9080 --name dt7 liberty-dt7:openj9_11
