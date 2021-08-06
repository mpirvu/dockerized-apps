# set tradeDbHost to the address of the machine where DB2 is located and tradeDbPort to the db2 port value
docker run --rm -it -e JVM_ARGS="" -e tradeDbHost="192.168.1.7" -e tradeDbPort="50000" -e dbUser="db2inst1" -e dbPass="p@ssw0rd" -p 9080:9080 --name dt8  liberty-dt8:openj9_8_0.26.0
