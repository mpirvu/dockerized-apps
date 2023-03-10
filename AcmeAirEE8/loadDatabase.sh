# This command can be used to populate an acmeair database
# Both mongodb and liberty-acmeair containers must be up and running
# If mongodb container populates the acmaair database from a backup,
# then this command is not really needed
curl --ipv4 -v http://localhost:9080/rest/info/loader/load?numCustomers=10000

