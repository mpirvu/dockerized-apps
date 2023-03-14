# Python script to drive a large number of JITClients
# Execute with python3 on ubuntu

# The script will launch M containers with mongo, 1 container with JITServer
# and L concurent containers with Liberty+AcmeAir (multiple Liberty containers can
# connect to a single mongo instance).
# Liberty containers are started in a staggered fashion with n seconds in-between
# consecutive instances.
# 10 seconds after Liberty container starts we apply load with JMeter.
# Each Liberty container has its own dedicated JMeter instance.
# Once the load for a Liberty instance ends, we shutdown that instance, start a new one
# and again apply load to it. Thus, we simulate short running JVM instances and
# at any given point there are L such instances in play.
# The script is multithreaded and the number of threads is L. Each thread starts a
# Liberty instance, applies load to it, stops the instance and repeats.

# To configure the benchmark for your needs change the following variables
# libertyImage
# JITServerImage
# jmeterImage
# mongoImage
# JITServerMachine: the IP of the machine where JITServer is supposed to run
# machines: Array of entries showing the IP of the machines for liberty, jmeter and mongo containers
# username:  This user must be able to ssh without a password to all machines
# numConcurrentInstances : The number of concurrent Liberty instances (L)
# numIter: How many times each thread will start-load-stop Liberty
# basePort: Starting port for Liberty instances (they will use startPort, startPort+1 ...)
# cpuLimit: CPU limit for Liberty instances
# memoryLimit: Memory limit for Liberty instances
# delayToStart: Delay from starting Liberty container and checking that it has started
# staggerDelay: Interval between starting 2 consecutive Liberty instances
# libertyJvmArgs: Additional arguments passed to Liberty JVM
# loadTime: Duration of JMeter load in seconds
# numClients: Number of JMeter threads
# maxUsers: Maximum number of simulated AcmeAir users

# Note that, at the moment, changing the CPU/memory limits or options for JITServer needs
# to be done by modifying `startJITServer` routine

import shlex, subprocess
import time # for sleep
import re # for regular expressions
import datetime # for datetime.datetime.now()
import sys # for exit
import threading
import logging # https://www.machinelearningplus.com/python/python-logging-guide/

# For using a JDK from outside containers we must map    -v MYJDK:/opt/java/openjdk
# For sharing the SCC among containers we must use volumes    --mount source=VolumeName:DirForSCC


############################### CONFIG ###############################################
docker = "docker" # Select between docker and podman
libertyImage   = "liberty-acmeair-ee8:J17"
JITServerImage = "icr.io/appcafe/open-liberty:beta-instanton"
jmeterImage    = "jmeter-acmeair:5.3"
mongoImage     = "mongo-acmeair-ee8:5.0.15"

useJITServer = False

JITServerMachine = "9.46.116.36"
machines=[
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          {"liberty":"9.46.81.11", "jmeter":"9.46.116.36", "mongo":"9.46.81.11"},
          #{}
] #machines
username="root" # this user must be able to ssh without a password to all machines
numConcurrentInstances = 8 # Number of Liberty instances to run in parallel
numIter = 10 # Number of iterations to run
lockStep = True # If true, parallel Liberty instances will wait at barrier until all have reached it
staggerDelay = 1 # Delay between starting each concurrent Liberty instance

# Liberty/AcmeAir configuration
basePort = 9080 # for AcmeAir
cpuLimit="1"
memoryLimit="512m"
delayToStart = 15 # Delay from starting Liberty container and checking that has started

useSCCVolume    = False  # set to true to have a SCC mounted in a volume (instead of the embedded SCC)
SCCVolumeName   = "scc_volume" # Name of the volume to use for the SCC
sccInstanceDir  = "/opt/java/.scc" # Location of the shared class cache in the instance
mountOpts       = f"--mount type=volume,src={SCCVolumeName},target={sccInstanceDir}" if useSCCVolume  else ""
libertyJvmArgs = f""
#libertyJvmArgs = f"-XX:+UseJITServer -XX:JITServerAddress={JITServerMachine} -Xshareclasses:name=liberty,cacheDir=/output/.classCache/"
#libertyJvmArgs = f"-Xshareclasses:name=myscc,cacheDir={sccInstanceDir}"
# If verbose logs are needed, create a directory /tmp/vlogs and set permissions
# for everybody. The uncomment the following line and set -v /tmp/vlogs:/tmp/vlogs for Liberty container
#libertyJvmArgs = libertyJvmArgs + " -Xdump:directory=/tmp/vlogs -Xjit:verbose={compilePerformance},verbose={JITServer},verbose={failures},vlog=/tmp/vlogs/vlog.client.txt "

# JMeter configuration
loadTime = 300 # Duration of load
numClients = 2 # Number of JMeter threads
maxUsers = 200 # Maximum number of simulated AcmeAir users
numUsersPerJMeter = maxUsers//numConcurrentInstances
##################################### END CONFIG ######################################


# Given a list of dictionaries, compute the mean for each key individually
def dict_mean(dict_list):
    mean_dict = {}
    for key in dict_list[0].keys():
        mean_dict[key] = sum(d[key] for d in dict_list) / len(dict_list)
    return mean_dict

def getMainPIDFromContainer(host, username, instanceID):
    # Note: podman needs double curly brackets for format
    remoteCmd = f"{docker} inspect " + "--format='{{.State.Pid}}' " + instanceID
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    try:
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        lines = output.splitlines()
        return lines[0]
    except:
        return 0
    return 0

# Clear the volume of the SCC, if volumes are used
def clearSCC(host, username, SCCVolumeName):
    logging.info("Clearing SCC")
    remoteCmd = f"docker volume rm --force {SCCVolumeName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    subprocess.run(shlex.split(cmd), universal_newlines=True)
    # TODO: make sure volume does not exist

# Given a PID, return RSS and peakRSS for the process
def getRss(host, username, pid):
    _scale = {'kB': 1024, 'mB': 1024*1024, 'KB': 1024, 'MB': 1024*1024}
    # get pseudo file  /proc/<pid>/status
    filename = "/proc/" + pid + "/status"
    remoteCmd = f"cat {filename}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    try:
        s = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        #lines = s.splitlines()
    except IOError as ioe:
        logging.warning("Cannot open {filename}: {msg}".format(filename=filename,msg=str(ioe)))
        return [0, 0]  # wrong pid?
    i =  s.index("VmRSS:") # Find the position of the substring
    # Take everything from this position till the very end
    # Then split the string 3 times, taking first 3 "words" and putting them into a list
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [0, 0]  # invalid format
    rss = int(tokens[1]) * _scale[tokens[2]]  # convert value to bytes

    # repeat for peak RSS
    i =  s.index("VmHWM:")
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [0, 0]  # invalid format
    peakRss = int(tokens[1]) * _scale[tokens[2]]  # convert value to bytes
    return [rss, peakRss]

# Given a PID, return the proportional set size (PSS) of the process
# This command needs root permissions
def getPss(host, username, pid):
    _scale = {'kB': 1024, 'mB': 1024*1024, 'KB': 1024, 'MB': 1024*1024}
    # get pseudo file /prod/pid/smaps_rollup
    filename = "/proc/" + pid + "/smaps_rollup"
    remoteCmd = f"cat {filename}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    try:
        s = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        #lines = s.splitlines()
    except IOError as ioe:
        logging.warning("Cannot open {filename}: {msg}".format(filename=filename,msg=str(ioe)))
        return 0  # wrong pid?
    i =  s.index("Pss:") # Find the position of the substring
    # Take everything from this position till the very end
    # Then split the string 3 times, taking first 3 "words" and putting them into a list
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [0, 0]  # invalid format
    pss = int(tokens[1]) * _scale[tokens[2]]  # convert value to bytes
    return pss

def removeContainer(host, username, instanceName):
    remoteCmd = f"{docker} rm {instanceName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    logging.info("Removing container instance {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def removeForceContainer(instanceName):
    remoteCmd = f"{docker} rm -f {instanceName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    logging.info("Removing container instance {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopContainersFromImage(host, username, imageName):
    # Find all running containers from image
    remoteCmd = f"{docker} ps --quiet --filter ancestor={imageName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\""
        print("Stopping container: ", cmd)
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def removeContainersFromImage(host, username, imageName):
    # First stop running containers
    stopContainersFromImage(host, username, imageName)
    # Now remove stopped containes
    remoteCmd = f"{docker} ps -a --quiet --filter ancestor={imageName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} rm {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\""
        print("Removing container: ", cmd)
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

# start mongo on a remote machine
def startMongo(host, username, mongoImage):
    remoteCmd = f"{docker} run --rm -d --net=host --name mongodb {mongoImage} --nojournal"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    logging.info("Starting mongo: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    time.sleep(2)
    remoteCmd = f"{docker} exec mongodb mongorestore --drop /AcmeAirDBBackup"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    print(output)

# start a bunch of mongo instances (one per machine)
def startMongos(machines, numMachines, username, mongoImage):
    mongoMachines = {}
    for m in range(numMachines):
        entry = machines[m]
        mongoMachines[entry["mongo"]] = 1
    for machine in mongoMachines:
        startMongo(host=machine, username=username, mongoImage=mongoImage)

def stopMongo(host, username):
    # find the ID of the container, if any
    remoteCmd = f"{docker} ps --quiet --filter name=mongodb"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\""
        logging.info("Stopping mongo: {cmd}".format(cmd=cmd))
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopMongos(machines, numMachines, username):
    mongoMachines = {}
    for m in range(numMachines):
        entry = machines[m]
        mongoMachines[entry["mongo"]] = 1
    for machine in mongoMachines:
        stopMongo(host=machine, username=username)

def verifyLibertyHasStarted(instanceName, host, username):
    remoteCmd = f"{docker} ps --quiet --filter name={instanceName}" # Note that this can return any partial matches
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty container {instanceName} is not running").format(instanceName=instanceName)
        return False
    if len(lines) > 1:
        logging.error("More than one liberty instance has been found active")
    errPattern = re.compile('.+\[ERROR')
    readyPattern = re.compile(".+is ready to run a smarter planet")
    for containerID in lines:
        for iter in range(10):
            remoteCmd = f"{docker} logs --tail=100 {containerID}"
            cmd = f"ssh {username}@{host} \"{remoteCmd}\""
            output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
            liblines = output.splitlines()
            for line in liblines:
                m = errPattern.match(line)
                if m:
                    logging.warning("Liberty container {instanceName} errored while starting: {line}").format(instanceName=instanceName,line=line)
                    return False
                m1 = readyPattern.match(line)
                if m1:
                    return True # True means success
            time.sleep(1) # wait 1 sec and try again
        return False
    return False

def verifyLibertyContainerIDStarted(instanceID, host, username):
    remoteCmd = f"{docker} ps --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty container {instanceID} is not running").format(instanceID=instanceID)
        return False

    remoteCmd = f"{docker} logs --tail=100 {instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    errPattern = re.compile('.+\[ERROR')
    readyPattern = re.compile(".+is ready to run a smarter planet")
    for iter in range(10):
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        liblines = output.splitlines()
        for line in liblines:
            m = errPattern.match(line)
            if m:
                logging.warning("Liberty container {instanceID} errored while starting: {line}").format(instanceID=instanceID,line=line)
                return False
            m1 = readyPattern.match(line)
            if m1:
                print(line)
                return True # True means success
        time.sleep(1) # wait 1 sec and try again
        logging.warning("Checking again")
    return False

def startLiberty(host, username, instanceName, containerImage, port, cpus, mem, jvmargs, mountOpts, mongoMachine):
    # vlogs can be created in /tmp/vlogs -v /tmp/vlogs:/tmp/vlogs
    # JITOPTS = "\"verbose={compilePerformance},verbose={JITServer},vlog=/tmp/vlogs/vlog.client.txt\""
    remoteCmd = f"{docker} run -d --cpus={cpus} -m={mem} {mountOpts} -e JVM_ARGS='{jvmargs}' -e TR_PrintCompStats=1 -e TR_PrintCompTime=1 -e MONGO_HOST={mongoMachine} -e MONGO_PORT=27017 -e MONGO_DBNAME=acmeair -p {port}:9080 --name {instanceName} {containerImage}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    logging.info("Starting liberty instance {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        sys.exit("Error: docker run output is empty")
    if len(lines) > 1:
        print(lines)
        sys.exit("Error: docker run output containes several lines")
    return lines[0]

def stopLibertyByName(instanceName):
    cmd = f"{docker} ps --quiet --filter name={instanceName}"
    logging.info("Stopping container {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if lines:
        for containerID in lines:
            cmd = f"{docker} stop {containerID}"
            output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        return True
    else:
        logging.warning("Liberty instance {instanceName} does not exist. Might have crashed".format(instanceName=instanceName))
        return False

def stopLibertyByID(host, username, containerID):
    remoteCmd = f"{docker} ps --quiet --filter id={containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    logging.info("Stopping container {containerID}".format(containerID=containerID))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty instance {containerID} does not exist. Might have crashed".format(containerID=containerID))
        return False
    remoteCmd = f"{docker} stop {containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    return True

def getLibertyStartupTime(host, username, containerID, containerStartTimeMs):
    # Copy the log file from the container to the host
    # Weird thing that I cannot use /tmp to store the log file
    logFileOnHost = f"messages.log.{containerID}"
    localLogFile = logFileOnHost + ".local"
    remoteCmd = f"{docker} cp {containerID}:/logs/messages.log {logFileOnHost}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    # Copy the log file from the remote host to the local machine
    cmd = f"scp {username}@{host}:{logFileOnHost} {localLogFile}"
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    try:
        f = open(localLogFile, 'r')
        s = f.read() # read the entire file
        f.close()
    except IOError as ioe:
        logging.warning("Cannot open {filename}: {msg}".format(filename=localLogFile,msg=str(ioe)))
        return 0
    # must remove the logFile
    cmd = f"ssh {username}@{host} rm {logFileOnHost}"
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    cmd = f"rm {localLogFile}"
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    # [10/29/20, 23:18:49:468 UTC] 00000024 com.ibm.ws.kernel.feature.internal.FeatureManager            A CWWKF0011I: The defaultServer server is ready to run a smarter planet. The defaultServer server started in 2.885 seconds.
    lines = s.splitlines()
    readyPattern = re.compile('\[(.+)\] .+is ready to run a smarter planet')
    for line in lines:
        m = readyPattern.match(line)
        if m:
            timestamp = m.group(1)
            # [10/29/20, 17:53:03:894 EDT]
            pattern1 = re.compile("(\d+)\/(\d+)\/(\d+),? (\d+):(\d+):(\d+):(\d+) (.+)")
            m1 = pattern1.match(timestamp)
            if m1:
                # Ignore the hour to avoid time zone issues
                endTime = (int(m1.group(5)) * 60 + int(m1.group(6)))*1000 + int(m1.group(7))
                if endTime < containerStartTimeMs:
                    endTime = endTime + 3600*1000 # add one hour
                return endTime - containerStartTimeMs
            else:
                logging.warning("Liberty timestamp is in the wrong format: {timestamp}".format(timestamp=timestamp))
                return 0
    logging.warning("Liberty instance {containerID} may not have started correctly".format(containerID=containerID))
    return 0

def printLibertyOutput(host, username, instanceName):
    remoteCmd = f"{docker} logs {instanceName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    print(output)

def getCompCPUFromContainer(host, username, instanceID):
    logging.debug("Computing CompCPU for Liberty instance {instanceID}".format(instanceID=instanceID))
    remoteCmd = f"{docker} ps -a --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty instance {instanceID} does not exist.".format(instanceID=instanceID))
        return 0

    threadTime = 0
    remoteCmd = f"{docker} logs --tail=25 {instanceID}" # I need to capture stderr as well
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
    liblines = output.splitlines()
    compTimePattern = re.compile("Time spent in compilation thread =(\d+) ms")
    for line in liblines:
        m = compTimePattern.match(line)
        if m:
            threadTime += int(m.group(1))
    return threadTime

def startJITServer(containerName, JITServerImage, port, JITServerMachine, username):
    # -v /tmp/vlogs:/tmp/JITServer_vlog -e TR_Options=\"statisticsFrequency=10000,vlog=/tmp/vlogs/vlog.txt\"
    #JITOptions = "\"statisticsFrequency=10000,verbose={compilePerformance},verbose={JITServer},vlog=/tmp/vlogs/vlog.txt\""
    OTHEROPTIONS= "-Xdump:directory=/tmp/vlogs"
    JITOptions = ""
    # -v /tmp/vlogs:/tmp/vlogs
    remoteCmd = f"{docker} run -d -p {port}:38400 --rm --cpus=8.0 --memory=4G  -e TR_PrintCompMem=1 -e TR_PrintCompStats=1 -e TR_PrintCompTime=1 -e TR_PrintCodeCacheUsage=1 -e JAVA_OPTIONS={OTHEROPTIONS} -e TR_Options={JITOptions} --name {containerName} {JITServerImage} jitserver"
    cmd = f"ssh {username}@{JITServerMachine} \"{remoteCmd}\""
    print(datetime.datetime.now(), " Start JITServer:", cmd)
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopJITServer(containerName, JITServerMachine, username):
    # find the ID of the container, if any
    remoteCmd = f"{docker} ps --quiet --filter name={containerName}"
    cmd = f"ssh {username}@{JITServerMachine} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {username}@{JITServerMachine} \"{remoteCmd}\""
        print(datetime.datetime.now(), " Stop JITServer:", cmd)
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

# Run jmeter remotely
def applyLoad(containerName, jmeterImage, jmeterMachine, username, libertyMachine, port, numClients, duration, firstUser, lastUser):
    remoteCmd = f"{docker} run -d -e JTHREAD={numClients} -e JDURATION={duration} -e JUSERBOTTOM={firstUser} -e JUSER={lastUser} -e JHOST={libertyMachine} -e JPORT={port} --name {containerName} {jmeterImage}"
    cmd = f"ssh {username}@{jmeterMachine} \"{remoteCmd}\""
    logging.info("Apply load: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopJMeter(containerName, jmeterMachine, username):
    remoteCmd = f"{docker} rm {containerName}"
    cmd = f"ssh {username}@{jmeterMachine} \"{remoteCmd}\""
    logging.info("Removing jmeter: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def getJMeterSummary(containerName, jmeterMachine, username):
    logging.debug("Getting throughput info...")
    remoteCmd = f"{docker} logs --tail=100 {containerName}"
    cmd = f"ssh {username}@{jmeterMachine} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()

    # Find the last line that contains
    # summary = 110757 in    30s = 3688.6/s Avg:    12 Min:     0 Max:   894 Err:     0 (0.00%)
    # or
    # summary = 233722 in 00:02:00 = 1947.4/s Avg:     0 Min:     0 Max:   582 Err:     0 (0.00%)
    elapsedTime = 0
    throughput = 0
    totalTransactions = 0
    lastSummaryLine = ""
    queue = []
    pattern1 = re.compile('summary \+\s+(\d+) in\s+(\d+\.*\d*)s =\s+(\d+\.\d+)/s.+Finished: 0')
    pattern2 = re.compile('summary \+\s+(\d+) in\s+(\d\d):(\d\d):(\d\d) =\s+(\d+\.\d+)/s.+Finished: 0')
    for line in lines:
        # summary +  17050 in 00:00:06 = 2841.7/s Avg:     0 Min:     0 Max:    49 Err:     0 (0.00%) Active: 2 Started: 2 Finished: 0
        if line.startswith("summary +"):
            # Uncomment this line if we need to print rampup
            #print(line)
            m = pattern1.match(line)
            if m:
                thr = float(m.group(3))
                queue.append(thr)
            else:
                m = pattern2.match(line)
                if m:
                    thr = float(m.group(5))
                    queue.append(thr)

        if line.startswith("summary ="):
            lastSummaryLine = line

    pattern = re.compile('summary =\s+(\d+) in\s+(\d+\.*\d*)s =\s+(\d+\.\d+)/s')
    m = pattern.match(lastSummaryLine)
    if m:
        # First group is the total number of transactions/pages that were processed
        totalTransactions = float(m.group(1))
        # Second group is the interval of time that passed
        elapsedTime = float(m.group(2))
        # Third group is the throughput value
        throughput = float(m.group(3))
    else: # Check the second pattern
        pattern = re.compile('summary =\s+(\d+) in\s+(\d\d):(\d\d):(\d\d) =\s+(\d+\.\d+)/s')
        m = pattern.match(lastSummaryLine)
        if m:
            # First group is the total number of transactions/pages that were processed
            totalTransactions = float(m.group(1))
            # Next 3 groups are the interval of time that passed
            elapsedTime = float(m.group(2))*3600 + float(m.group(3))*60 + float(m.group(4))
            # Fifth group is the throughput value
            throughput = float(m.group(5))
    # Compute the peak throughput as the average of the last 3 throughput values
    peakThr = 0.0
    if len(queue) >= 3:
        queue = queue[-3:]
        peakThr = sum(queue)/3.0

    #print (str(elapsedTime), throughput, sep='\t')
    return throughput, elapsedTime, peakThr

def cleanup(machines, numSlots, JITServerMachine, username, libertyImage, jmeterImage, mongoImage):
    libertyMachineSet = set() # remebers the set of all liberty machines we are going to use
    jmeterMachineSet = set() # remebers the set of all jmeter machines we are going to use
    mongoMachineSet = set() # remebers the set of all mongo machines we are going to use
    for slot in range(numSlots):
        jmeterMachineSet.add(machines[slot]["jmeter"])
        libertyMachineSet.add(machines[slot]["liberty"])
        mongoMachineSet.add(machines[slot]["mongo"])
    for machine in libertyMachineSet:
        stopContainersFromImage(machine, username, libertyImage)
        # Prune any stopped containers on all machines we are going to use
        cmd = f"ssh {username}@{machine} \"{docker} container prune -f\""
        subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        if useSCCVolume:
            clearSCC(machine, username, SCCVolumeName)
    for machine in jmeterMachineSet:
        stopContainersFromImage(machine, username, jmeterImage)
        # Prune any stopped containers on all machines we are going to use
        cmd = f"ssh {username}@{machine} \"{docker} container prune -f\""
        subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    for machine in mongoMachineSet:
        stopContainersFromImage(machine, username, mongoImage)
        # Prune any stopped containers on all machines we are going to use
        cmd = f"ssh {username}@{machine} \"{docker} container prune -f\""
        subprocess.check_output(shlex.split(cmd), universal_newlines=True)

    if JITServerMachine:
        stopJITServer(containerName="server", JITServerMachine=JITServerMachine, username=username)
    time.sleep(3)


# Function executed by each thread
def threadFunction(id, username, numIter, libImage, libertyMachine, port, cpuLimit, memoryLimit, jvmArgs, mountOpts,
                   mongoMachine, jmeterImage, jmeterMachine, numClients, loadTime, firstUser, lastUser):
    libertyInstanceName = f"lib-{id}"
    jmeterInstanceName = f"jmeter{id}"

    for iter in range(numIter):
        logging.info("Starting iteration {a}".format(a=iter))
        crtTime = datetime.datetime.now()
        containerStartTimeMs = (crtTime.minute * 60 + crtTime.second)*1000 + crtTime.microsecond//1000
        # start Liberty
        containerID = startLiberty(host=libertyMachine, username=username, instanceName=libertyInstanceName, containerImage=libImage,
                                   port=port, cpus=cpuLimit, mem=memoryLimit, jvmargs=jvmArgs, mountOpts=mountOpts, mongoMachine=mongoMachine)
        time.sleep(delayToStart)
        # Verify Liberty is started
        started = verifyLibertyContainerIDStarted(instanceID=containerID, host=libertyMachine, username=username)
        if started:
            logging.debug("Started OK instance {containerID}".format(containerID=containerID))
            #logging.info("Loading database")
            #cmd = f"curl --ipv4 http://{libertyMachine}:{port}/rest/info/loader/load?numCustomers=10000"
            #output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

            # Apply load
            applyLoad(containerName=jmeterInstanceName, jmeterImage=jmeterImage, jmeterMachine=jmeterMachine, username=username,
                      libertyMachine=libertyMachine, port=port, numClients=numClients, duration=loadTime, firstUser=firstUser, lastUser=lastUser)

            # Wait for load to finish
            remoteCmd = f"{docker} wait {jmeterInstanceName}"
            cmd = f"ssh {username}@{jmeterMachine} \"{remoteCmd}\""
            logging.info("Wait for {jmeter} to end: {cmd}".format(jmeter=jmeterInstanceName, cmd=cmd))
            output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

            # Read throughput
            thr, elapsed, peakThr = getJMeterSummary(containerName=jmeterInstanceName, jmeterMachine=jmeterMachine, username=username)

            # Stop JMeter
            stopJMeter(containerName=jmeterInstanceName, jmeterMachine=jmeterMachine, username=username)
            logging.info("Throughput: {thr} {elapsed} {peakThr}".format(thr=thr,elapsed=elapsed,peakThr=peakThr))

            # Wait for all threads to finish if we want to work in lockstep
            if lockStep and (numConcurrentInstances > 1):
                barrier.wait()

            # Get memory information
            logging.debug("Obtaining footprint information")
            libPID = getMainPIDFromContainer(host=libertyMachine, username=username, instanceID=containerID)
            if int(libPID) > 0:
                [rss, peakRss] = getRss(host=libertyMachine, username=username, pid=libPID)
                pss            = getPss(host=libertyMachine, username=username, pid=libPID)
                logging.info("Memory: RSS={rss} PeakRSS={peak} PSS={pss}".format(rss=rss,peak=peakRss,pss=pss))
            startTimeMillis = getLibertyStartupTime(host=libertyMachine, username=username, containerID=containerID, containerStartTimeMs=containerStartTimeMs)
            logging.info("Startup time: {startup}".format(startup=startTimeMillis))

            # Stop Liberty
            success = stopLibertyByID(host=libertyMachine, username=username, containerID=containerID)
            if not success: # May have crashed already
                printLibertyOutput(host=libertyMachine, username=username, instanceName=libertyInstanceName)
            compCPU = getCompCPUFromContainer(host=libertyMachine, username=username, instanceID=containerID)
            removeContainer(host=libertyMachine, username=username, instanceName=libertyInstanceName)
            resultsLock.acquire()
            thrValues.append({'thr':thr, 'elapsed':elapsed, 'peakThr':peakThr, 'startup':startTimeMillis, 'cpu':compCPU, 'rss':(rss >> 10), 'peakrss':(peakRss >> 10), 'pss':(pss >> 10)})
            resultsLock.release()
        else:
            logging.error("Liberty instance {lib} cannot start in the alloted time".format(lib=libertyInstanceName))
            removeForceContainer(host=libertyMachine, username=username, instanceName=containerID)


thrValues = [] # list of throughput values; global so that threads can append to it
resultsLock = threading.Lock()
workers = [] # list of threads
barrier = threading.Barrier(numConcurrentInstances) # Barrier to make threads work in lockstep



#level=logging.DEBUG, logging.INFO, logging.WARNING
logging.basicConfig(level=logging.INFO,
                    format='%(asctime)s :: %(levelname)s :: (%(threadName)-6s) :: %(message)s',
                    )

if numConcurrentInstances > len(machines):
    sys.exit("Cannot have more concurrent JVM instances than machine definitions")

cleanup(machines, numConcurrentInstances, JITServerMachine if useJITServer else None, username, libertyImage, jmeterImage, mongoImage)
if useJITServer:
    startJITServer(containerName="server", JITServerImage=JITServerImage, port=38400, JITServerMachine=JITServerMachine, username=username)
startMongos(machines=machines, numMachines=numConcurrentInstances, username=username, mongoImage=mongoImage)
time.sleep(2)


firstUser = 0
lastUser = firstUser + numUsersPerJMeter - 1
# Start threads staggered
for slot in range(numConcurrentInstances):
    # id, username, numIter, libImage, libertyMachine, port,
    # cpuLimit, memoryLimit, jvmArgs, mountOpts, mongoMachine,
    # jmeterImage, jmeterMachine, numClients, loadTime, firstUser, lastUser
    worker = threading.Thread(target=threadFunction, name="Thr-"+str(slot),
                              args=(slot,username,numIter,libertyImage,machines[slot]["liberty"],basePort+slot,
                                    cpuLimit,memoryLimit,libertyJvmArgs,mountOpts,machines[slot]["mongo"],
                                    jmeterImage,machines[slot]["jmeter"],numClients,loadTime,
                                    firstUser, lastUser, ))
    workers.append(worker)
    worker.start()
    time.sleep(staggerDelay)
    # Determine users for next slot
    firstUser = lastUser + 1
    lastUser = firstUser + numUsersPerJMeter -1

for worker in workers:
    worker.join()

stopMongos(machines=machines, numMachines=numConcurrentInstances, username=username)
if useJITServer:
    stopJITServer(containerName="server", JITServerMachine=JITServerMachine, username=username)
#print("Throughput values:")
#print(*thrValues, sep = "\n")
print("Thr\tTime\tPeakThr\tStartup\t CPU\tRSS\tPeakRSS\tPSS")
for entry in thrValues:
    print("{thr:4.1f}\t{duration:4.0f}\t{peakThr:4.1f}\t{startup:5d}\t{cpu:5d}\t{rss:6d}\t{peakRss:7d}\t{pss:7d}".format(thr=entry.get('thr'),
        duration=entry.get('elapsed'), peakThr=entry.get('peakThr'), startup=entry.get('startup'), cpu=entry.get('cpu'), rss=entry.get('rss'),
        peakRss=entry.get('peakrss'), pss=entry.get('pss')))
# Compute averages
meanDict = dict_mean(thrValues)
print("Averages:")
print("{thr:4.1f}\t{duration:4.0f}\t{peakThr:4.1f}\t{startup:5.0f}\t{cpu:5.0f}\t{rss:6.0f}\t{peakRss:7.0f}\t{pss:7.0f}".format(thr=meanDict.get('thr'),
        duration=meanDict.get('elapsed'), peakThr=meanDict.get('peakThr'), startup=meanDict.get('startup'), cpu=meanDict.get('cpu'),
        rss=meanDict.get('rss'), peakRss=meanDict.get('peakrss'), pss=meanDict.get('pss')))

# Final cleanup
cleanup(machines, numConcurrentInstances, JITServerMachine if useJITServer else None, username, libertyImage, jmeterImage, mongoImage)
