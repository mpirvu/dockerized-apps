if [ ! -z "$1" ]; then
	export APP_MACHINE="$1"
else
	export APP_MACHINE=192.168.1.9
fi

curl http://$APP_MACHINE/booking/loader/load
curl http://$APP_MACHINE/flight/loader/load
curl http://$APP_MACHINE/customer/loader/load?numCustomers=10000

