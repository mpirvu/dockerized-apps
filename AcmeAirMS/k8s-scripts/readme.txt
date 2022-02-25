1. Modify all yaml files to match your environment (only once)
   In particular, change the image names for the application containers
2. If needed, start the Horizonal Pod Autoscalers with "kubectl apply -f Autoscaler.yaml"
3. Create all ingresses (only once)
4. Deploy all applications with ./deployEverything.sh
5. Check that all pods have been deployed with "kubectl get pods"
6. Load the databases with ./loadDatabases.sh
7. Apply load from outside the kubernetes cluster with something like
docker run -it --rm  -e JHOST=192.168.1.26 -e JPORT=80 -e JDURATION=600 -e JTHREAD=8 --network=host jmeter-acmeair-ms:3.3 | tee g.txt
8. Use ./deleteEvereything.sh to delete all deployments

