docker run --rm -d --name mongodb --network=my-net localhost/mongo-acmeair-ee8:5.0.15 --nojournal
sleep 1
./mongoRestore.sh
