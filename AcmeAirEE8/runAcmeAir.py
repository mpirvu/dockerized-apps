# Python script to run AcmeAirEE8
# The script can run the same configuration multiple times and compute stats
# on performance metrics like: start-up time, throughput for first N minutes
# of load, peak throughput over a period of time, RSS, peak RSS, compCPU
# Each configuration is defined as a container image to run together with
# associated command line arguments or environment variables.
# If command line arguments indicates that the JVM is running in client mode,
# a JITServer will be launched automatically
from collections import deque
import datetime # for datetime.datetime.now()
import logging # https://www.machinelearningplus.com/python/python-logging-guide/
import math
import queue
import re # for regular expressions
import shlex, subprocess
import sys # for exit
import time # for sleep

############################### CONFIG ###############################################
#level=logging.DEBUG, logging.INFO, logging.WARNING
logging.basicConfig(level=logging.INFO, format='%(asctime)s :: %(levelname)s :: (%(threadName)-6s) :: %(message)s',)

docker = "podman" # Select between docker and podman
netOpts = "--network=slirp4netns" if docker == "podman" else "" # for podman we need to use slirp4netns if running as root. This will be added to Liberty. mongo uses host network. Does JITServer needed it?

################### Benchmark configuration #################
doColdRun = True
appServerMachine = "9.46.116.36"
username = "" # for connecting remotely to the SUT; leave empty to connect without ssh
containerName = "acmeair"
appServerPort   = "9080"
cpuLimit        = "--cpus=1.0" # This can also be used to specify CPU affinity if so desired
memLimit        = "-m=512m"
delayToStart    = 15 # seconds; waiting for the AppServer to start before checking for valid startup
extraDockerOpts = "" # extra options to pass to docker run
instantOnRestore= False # Set to true to add --cap-add=CHECKPOINT_RESTORE to docker run command
doApplyLoad     = True # Set to false to skip load generation
getFirstResponseTime = False # Set to true to get the first response time
firstResponseHelperScript = "./loop_curl.sh" # Script to get the first response time

############### SCC configuration #####################
useSCCVolume    = False  # set to true to have a SCC mounted in a volume (instead of the embedded SCC)
SCCVolumeName   = "scc_volume" # Name of the volume to use for the SCC
sccInstanceDir  = "/opt/java/.scc" # Location of the shared class cache in the instance
mountOpts       = f"--mount type=volume,src={SCCVolumeName},target={sccInstanceDir}" if useSCCVolume  else ""

############### Database configuration #########
mongoMachine       = "9.46.116.36"
mongoUsername      = "" # To connect to mongoMachine remotely; leave empty to connect without ssh
mongoImage         = "mongo-acmeair-ee8:5.0.15"
mongoAffinity      = ""
mongoInstanceName  = "mongodb1"

############### JMeter CONFIG ###############
jmeterMachine       = "9.46.116.36"
jmeterUsername      = "" # To connect to JMeter machine; leave empty to connect without ssh
jmeterImage         = "jmeter-acmeair:5.3"
jmeterContainerName = "jmeter"
jmeterAffinity      = "2-3"
printRampup         = True # If True, print all JMeter throughput values to plot rampup curve

################ Load CONFIG ###############
numRepetitionsOneClient = 1
numRepetitions50Clients = 0
durationOfOneClient     = 60 # seconds
durationOfOneRepetition = 180 # seconds
numClients              = 10 # Number of JMeter threads
delayBetweenRepetitions = 10
numMeasurementTrials    = 1 # Last N trials are used in computation of throughput
thinkTime               = 0 # ms
maxUsers                = 199 # Maximum number of simulated AcmeAir users

################# JITServer CONFIG ###############
# JITServer is automatically launched if the JVM option include -XX:+UseJITServer
JITServerMachine = "9.46.116.36" # if applicable
JITServerUsername = "" # To connect to JITServerMachine; leave empty for connecting without ssh
JITServerImage   = "localhost/liberty-acmeair-ee8:J17-20240202"
JITServerContainerName = "jitserver"


# List of configs to run
# Each entry is a dictionary with "image" and "args" as keys
configs = [
    #{"image":"localhost/liberty-acmeair-ee8:J17-20240202", "args":""},
    #{"image":"localhost/liberty-acmeair-ee8:23.0.0.6-J17", "args":""},
    #{"image":"localhost/liberty-acmeair-ee8:J17-20240202-instanon", "args":""},
    {"image":"localhost/liberty-acmeair-ee8:23.0.0.6-J17-instanton", "args":""},
#    {"image":"", "args":""},
]

def nancount(myList):
    count = 0
    for i in range(len(myList)):
        if not math.isnan(myList[i]):
            count += 1
    return count

def nanmean(myList):
    total = 0
    numValidElems = 0
    for i in range(len(myList)):
        if not math.isnan(myList[i]):
            total += myList[i]
            numValidElems += 1
    return total/numValidElems if numValidElems > 0 else math.nan

def nanstd(myList):
    total = 0
    numValidElems = 0
    for i in range(len(myList)):
        if not math.isnan(myList[i]):
            total += myList[i]
            numValidElems += 1

    if numValidElems == 0:
        return math.nan
    if numValidElems == 1:
        return 0
    else:
        mean = total/numValidElems
        total = 0
        for i in range(len(myList)):
            if not math.isnan(myList[i]):
                total += (myList[i] - mean)**2
        return math.sqrt(total/(numValidElems-1))

def nanmin(myList):
    min = math.inf
    for i in range(len(myList)):
        if not math.isnan(myList[i]) and myList[i] < min:
            min = myList[i]
    return min

def nanmax(myList):
    max = -math.inf
    for i in range(len(myList)):
        if not math.isnan(myList[i]) and myList[i] > max:
            max = myList[i]
    return max

def tDistributionValue95(degreeOfFreedom):
    if degreeOfFreedom < 1:
        return math.nan
        #import scipy.stats as stats
        #  stats.t.ppf(0.975, degreesOfFreedom))
    tValues = [12.706, 4.303, 3.182, 2.776, 2.571, 2.447, 2.365, 2.306, 2.262, 2.228,
               2.201, 2.179, 2.160, 2.145, 2.131, 2.120, 2.110, 2.101, 2.093, 2.086,
               2.080, 2.074, 2.069, 2.064, 2.060, 2.056, 2.052, 2.048, 2.045, 2.042,]
    if degreeOfFreedom <= 30:
        return tValues[degreeOfFreedom-1]
    else:
        if degreeOfFreedom <= 60:
            return 2.042 - 0.001 * (degreeOfFreedom - 30)
        else:
            return 1.96

# Confidence intervals tutorial
# mean +- t * std / sqrt(n)
# For 95% confidence interval, t = 1.96 if we have many samples
def meanConfidenceInterval95(myList):
    cnt = nancount(myList)
    if cnt <= 1:
        return math.nan
    tvalue = tDistributionValue95(cnt-1)
    avg, stdDev = nanmean(myList), nanstd(myList)
    marginOfError = tvalue * stdDev / math.sqrt(cnt)
    return 100.0*marginOfError/avg

def computeStats(myList):
    avg = nanmean(myList)
    stdDev = nanstd(myList)
    min = nanmin(myList)
    max = nanmax(myList)
    ci95 = meanConfidenceInterval95(myList)
    samples = nancount(myList)
    return avg, stdDev, min, max, ci95, samples

def printStats(myList, name):
    avg, stdDev, min, max, ci95, samples = computeStats(myList)
    print("{name:<17} Avg={avg:7.1f}  StdDev={stdDev:7.1f}  Min={min:7.1f}  Max={max:7.1f}  Max/Min={maxmin:7.1f} CI95={ci95:7.1f}%  samples={n}".
            format(name=name, avg=avg, stdDev=stdDev, min=min, max=max, maxmin=max/min, ci95=ci95, n=samples))

def meanLastValues(myList, numLastValues):
    assert numLastValues > 0
    if numLastValues > len(myList):
        numLastValues = len(myList)
    return nanmean(myList[-numLastValues:])

def getMainPIDFromContainer(host, username, instanceID):
    remoteCmd = f"{docker} inspect " + "--format='{{.State.Pid}}' " + instanceID
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    try:
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        lines = output.splitlines()
        return lines[0]
    except:
        return 0
    return 0

# Given a container ID, find all the Java processes running in it
# If there is only one Java process, return its PID
def getJavaPIDFromContainer(host, username, instanceID):
    mainPID = getMainPIDFromContainer(host, username, instanceID)
    if mainPID == 0:
        return 0 # Error
    logging.debug("Main PID from container is {mainPID}".format(mainPID=mainPID))
    # Find all PIDs running on host
    remoteCmd = "ps -eo ppid,pid,cmd --no-headers"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\""
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    pattern = re.compile("^\s*(\d+)\s+(\d+)\s+(\S+)")
    # Construct a dictionary with key=PPID and value a list of PIDs (for its children)
    ppid2pid = {}
    pid2cmd = {}
    for line in lines:
        m = pattern.match(line)
        if m:
            ppid = m.group(1)
            pid = m.group(2)
            cmd = m.group(3)
            if ppid in ppid2pid:
                ppid2pid[ppid].append(pid)
            else:
                ppid2pid[ppid] = [pid]
            pid2cmd[pid] = cmd
    # Do a breadth-first search to find all Java processes. Use a queue.
    javaPIDs = []
    pidQueue = queue.Queue()
    pidQueue.put(mainPID)
    while not pidQueue.empty():
        pid = pidQueue.get()
        # If this PID is a Java process, add it to the list
        if "/java" in pid2cmd[pid]:
            javaPIDs.append(pid)
        if pid in ppid2pid: # If my PID has children
            for childPID in ppid2pid[pid]:
                pidQueue.put(childPID)
    if len(javaPIDs) == 0:
        logging.error("Could not find any Java process in container {instanceID}".format(instanceID=instanceID))
        return 0
    if len(javaPIDs) > 1:
        logging.error("Found more than one Java process in container {instanceID}".format(instanceID=instanceID))
        return 0
    return javaPIDs[0]

# Given a container ID, find all the Java processes running in it
# If there is only one Java process, return its PID
def getJavaPIDFromContainer(host, username, instanceID):
    mainPID = getMainPIDFromContainer(host, username, instanceID)
    if mainPID == 0:
        return 0 # Error
    logging.debug("Main PID from container is {mainPID}".format(mainPID=mainPID))
    # Find all PIDs running on host
    remoteCmd = "ps -eo ppid,pid,cmd --no-headers"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    pattern = re.compile("^\s*(\d+)\s+(\d+)\s+(\S+)")
    # Construct a dictionary with key=PPID and value a list of PIDs (for its children)
    ppid2pid = {}
    pid2cmd = {}
    for line in lines:
        m = pattern.match(line)
        if m:
            ppid = m.group(1)
            pid = m.group(2)
            cmd = m.group(3)
            if ppid in ppid2pid:
                ppid2pid[ppid].append(pid)
            else:
                ppid2pid[ppid] = [pid]
            pid2cmd[pid] = cmd
    # Do a breadth-first search to find all Java processes. Use a queue.
    javaPIDs = []
    pidQueue = queue.Queue()
    pidQueue.put(mainPID)
    while not pidQueue.empty():
        pid = pidQueue.get()
        # If this PID is a Java process, add it to the list
        if "/java" in pid2cmd[pid]:
            javaPIDs.append(pid)
        if pid in ppid2pid: # If my PID has children
            for childPID in ppid2pid[pid]:
                pidQueue.put(childPID)
    if len(javaPIDs) == 0:
        logging.error("Could not find any Java process in container {instanceID}".format(instanceID=instanceID))
        return 0
    if len(javaPIDs) > 1:
        logging.error("Found more than one Java process in container {instanceID}".format(instanceID=instanceID))
        return 0
    return javaPIDs[0]

def removeForceContainer(host, username, instanceName):
    remoteCmd = f"{docker} rm -f {instanceName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Removing container instance {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopContainersFromImage(host, username, imageName):
    # Find all running containers from image
    remoteCmd = f"{docker} ps --quiet --filter ancestor={imageName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
        logging.debug(f"Stopping container: {cmd}")
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopAppServerByID(host, username, containerID):
    logging.debug("Stopping AppServer container {containerID}".format(containerID=containerID))
    # Check that the container is still running
    remoteCmd = f"{docker} ps --quiet --filter id={containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("AppServer instance {containerID} does not exist. Might have crashed".format(containerID=containerID))
        return False
    remoteCmd = f"{docker} stop {containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    return True

def removeContainersFromImage(host, username, imageName):
    # First stop running containers
    stopContainersFromImage(host, username, imageName)
    # Now remove stopped containes
    remoteCmd = f"{docker} ps -a --quiet --filter ancestor={imageName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} rm {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
        logging.debug(f"Removing container: {cmd}")
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

# Restore database from backup
def restoreDatabase(host, username, mongoImage):
    remoteCmd = f"{docker} exec {mongoInstanceName} mongorestore --drop /AcmeAirDBBackup"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug(f"Restoring database: {cmd}")
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
    logging.debug(output)

# start mongo on a remote machine
def startMongo(host, username, mongoImage):
    remoteCmd = f"{docker} run --rm -d --net=host --name {mongoInstanceName} {mongoImage} --nojournal"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.info("Starting mongo: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

# Given a PID, return RSS and peakRSS in MB for the process
def getRss(host, username, pid):
    _scale = {'kB': 1024, 'mB': 1024*1024, 'KB': 1024, 'MB': 1024*1024}
    # get pseudo file  /proc/<pid>/status
    filename = "/proc/" + pid + "/status"
    remoteCmd = f"cat {filename}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    try:
        s = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        #lines = s.splitlines()
    except IOError as ioe:
        logging.warning("Cannot open {filename}: {msg}".format(filename=filename,msg=str(ioe)))
        return [math.nan, math.nan]  # wrong pid?
    i =  s.index("VmRSS:") # Find the position of the substring
    # Take everything from this position till the very end
    # Then split the string 3 times, taking first 3 "words" and putting them into a list
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [math.nan, math.nan]  # invalid format
    rss = float(tokens[1]) * _scale[tokens[2]] / 1048576.0 # convert value to bytes and then to MB

    # repeat for peak RSS
    i =  s.index("VmHWM:")
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [math.nan, math.nan]  # invalid format
    peakRss = float(tokens[1]) * _scale[tokens[2]] / 1048576.0 # convert value to bytes and then to MB
    return [rss, peakRss]

def clearSCC(host, username):
    logging.info("Clearing SCC")
    remoteCmd = f"{docker} volume rm --force {SCCVolumeName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.run(shlex.split(cmd), universal_newlines=True, stderr=subprocess.DEVNULL)
    # TODO: make sure volume does not exist

def verifyAppServerInContainerIDStarted(instanceID, host, username):
    remoteCmd = f"{docker} ps --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty container {instanceID} is not running").format(instanceID=instanceID)
        return False

    remoteCmd = f"{docker} logs --tail=100 {instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    errPattern = re.compile('.+\[ERROR')
    readyPattern = re.compile(".+is ready to run a smarter planet")
    for iter in range(15):
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        liblines = output.splitlines()
        for line in liblines:
            m = errPattern.match(line)
            if m:
                logging.warning("Liberty container {instanceID} errored while starting: {line}").format(instanceID=instanceID,line=line)
                return False
            m1 = readyPattern.match(line)
            if m1:
                if logging.root.level <= logging.DEBUG:
                   print(lines)
                return True # True means success
        time.sleep(1) # wait 1 sec and try again
        logging.warning("Checking again")
    return False

def startAppServerContainer(host, username, instanceName, image, port, cpus, mem, jvmArgs, mountOpts, mongoMachine):
    # vlogs can be created in /tmp/vlogs -v /tmp/vlogs:/tmp/vlogs
    #JITOPTS = "\"verbose={compilePerformance},verbose={JITServer}\""
    instantONOpts = f"--cap-add=CHECKPOINT_RESTORE --security-opt seccomp=unconfined" if instantOnRestore else ""
    remoteCmd = f"{docker} run -d {cpuLimit} {memLimit} {mountOpts} {instantONOpts} {netOpts} -e JVM_ARGS='{jvmArgs}' -e TR_PrintCompStats=1 -e TR_PrintCompTime=1 -e MONGO_HOST={mongoMachine} -e MONGO_PORT=27017 -e MONGO_DBNAME=acmeair -p {port}:9080 --name {instanceName} {image}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.info("Starting liberty instance {instanceName}: {cmd}".format(instanceName=instanceName,cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    assert lines, "Error: docker run output is empty".format(l=lines)
    assert len(lines) == 1, f"Error: docker run output containes several lines: {lines}"
    if logging.root.level <= logging.DEBUG:
        print(lines)
    instanceID = lines[0] # ['2ccae49f3c03af57da27f5990af54df8a81c7ce7f7aace9a834e4c3dddbca97e']
    time.sleep(delayToStart)
    started = verifyAppServerInContainerIDStarted(instanceID, host, username)
    if not started:
        logging.error(f"Liberty instance {instanceName} from {image} cannot start in the alloted time")
        removeForceContainer(host=host, username=username, instanceName=instanceName)
        return None
    return instanceID

def checkAppServerForErrors(instanceID, host, username):
    remoteCmd = f"{docker} ps --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("AppServer container {instanceID} is not running").format(instanceID=instanceID)
        return False

    remoteCmd = f"{docker} logs --tail=200 {instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    errPattern = re.compile('^.+ERROR')
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
    liblines = output.splitlines()
    for line in liblines:
        if errPattern.match(line):
            logging.error("AppServer errored: {line}".format(line=line))
            return False
    return True

def getCompCPUFromContainer(host, username, instanceID):
    logging.debug("Computing CompCPU for Liberty instance {instanceID}".format(instanceID=instanceID))
    # Check that the indicated container still exists
    remoteCmd = f"{docker} ps -a --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty instance {instanceID} does not exist.".format(instanceID=instanceID))
        return math.nan

    threadTime = 0.0
    remoteCmd = f"{docker} logs --tail=25 {instanceID}" # I need to capture stderr as well
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
    liblines = output.splitlines()
    compTimePattern = re.compile("^Time spent in compilation thread =(\d+) ms")
    for line in liblines:
        m = compTimePattern.match(line)
        if m:
            threadTime += float(m.group(1))
    return threadTime if threadTime > 0 else math.nan

def getAppServerStartupTime(host, username, containerID, containerStartTimeMs, curlProcess):
    logging.debug("Computing startup time for Liberty instance {instanceID}".format(instanceID=containerID))
    startupTime = math.nan
    firstResponseTime = math.nan
    # Check that the indicated container still exists
    remoteCmd = f"{docker} ps -a --quiet --filter id={containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty instance {instanceID} does not exist.".format(instanceID=containerID))
        return startupTime, firstResponseTime
    # Copy the log file from the container to the host
    # Weird thing that I cannot use /tmp to store the log file
    logFileOnHost = f"messages.log.{containerID}"
    localLogFile = logFileOnHost + ".local"
    if username:
        remoteCmd = f"{docker} cp {containerID}:/logs/messages.log {logFileOnHost}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\""
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
        # Copy the log file from the remote host to the local machine
        cmd = f"scp {username}@{host}:{logFileOnHost} {localLogFile}"
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    else: # Running locally
        remoteCmd = f"{docker} cp {containerID}:/logs/messages.log {localLogFile}"
        output = subprocess.check_output(shlex.split(remoteCmd), universal_newlines=True)
    try:
        f = open(localLogFile, 'r')
        s = f.read() # read the entire file
        f.close()
    except IOError as ioe:
        logging.warning("Cannot open {filename}: {msg}".format(filename=localLogFile,msg=str(ioe)))
        return startupTime, firstResponseTime
    # must remove the logFile
    if username:
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
                startupTime = float(endTime - containerStartTimeMs)
                break
            else:
                logging.warning("Liberty timestamp is in the wrong format: {timestamp}".format(timestamp=timestamp))
                break
    if startupTime == math.nan:
        logging.warning("Liberty instance {containerID} did not start correctly".format(containerID=containerID))

    if curlProcess: # We intend to get the firstResponse time
        outs = None
        errs = None
        try:
            outs, errs = curlProcess.communicate(timeout=15)
        except subprocess.TimeoutExpired:
            curlProcess.kill()
            outs, errs = curlProcess.communicate()

        if curlProcess.returncode == 0:
            firstResponseTimeString = outs #curlProcess.stdout
            # my output coming from `date +"%H:%M:%S:%N"` is in the format HH:MM:SS:NNNNNNNNN
            logging.debug(f"Computing first response time. End time is {firstResponseTimeString}")
            tpattern = re.compile("(\d+):(\d+):(\d+):(\d\d\d)")
            m2 = tpattern.match(firstResponseTimeString)
            if m2:
                # Ignore the hour to avoid time zone issues
                endTimeMs = (int(m2.group(2))*60 + int(m2.group(3)))*1000 + int(m2.group(4))
                if endTimeMs < containerStartTimeMs:
                    endTimeMs = endTimeMs + 3600*1000 # add one hour
                firstResponseTime = endTimeMs - containerStartTimeMs
            else:
                logging.warning("First response time is in the wrong format: {firstResponseTimeString}".format(firstResponseTimeString=firstResponseTimeString))

    return startupTime, firstResponseTime

def startJITServer():
    # -v /tmp/vlogs:/tmp/JITServer_vlog -e TR_Options=\"statisticsFrequency=10000,vlog=/tmp/vlogs/vlog.txt\"
    #JITOptions = "\"statisticsFrequency=10000,verbose={compilePerformance},verbose={JITServer},vlog=/tmp/vlogs/vlog.txt\""
    OTHEROPTIONS= "'-Xdump:directory=/tmp/vlogs'"
    JITOptions = ""
    # -v /tmp/vlogs:/tmp/vlogs
    remoteCmd = f"{docker} run -d -p 38400:38400 -p 38500:38500 --rm --cpus=8.0 --memory=4G {netOpts} -e TR_PrintCompMem=1 -e TR_PrintCompStats=1 -e TR_PrintCompTime=1 -e TR_PrintCodeCacheUsage=1 -e _JAVA_OPTIONS={OTHEROPTIONS} -e TR_Options={JITOptions} --name {JITServerContainerName} {JITServerImage} jitserver"
    cmd = f"ssh {JITServerUsername}@{JITServerMachine} \"{remoteCmd}\"" if JITServerUsername else remoteCmd
    logging.info(f"Start JITServer: {cmd}")
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def stopJITServer():
    # find the ID of the container, if any
    remoteCmd = f"{docker} ps --quiet --filter name={JITServerContainerName}"
    cmd = f"ssh {JITServerUsername}@{JITServerMachine} \"{remoteCmd}\"" if JITServerUsername else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {JITServerUsername}@{JITServerMachine} \"{remoteCmd}\"" if JITServerUsername else remoteCmd
        logging.debug(f"Stop JITServer: {cmd}")
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

################################ cleanup ######################################
def cleanup():
    removeContainersFromImage(jmeterMachine, jmeterUsername, jmeterImage)
    for config in configs:
        removeContainersFromImage(appServerMachine, username, config["image"])
    stopContainersFromImage(mongoMachine, mongoUsername, mongoImage)
    stopContainersFromImage(JITServerMachine, JITServerUsername, JITServerImage)

# Run jmeter remotely
def applyLoad(duration, numClients):
    remoteCmd = f"{docker} run -d --network=host -e JTHREAD={numClients} -e JDURATION={duration} -e JUSER={maxUsers} -e JHOST={appServerMachine} -e JPORT={appServerPort} --name {jmeterContainerName} {jmeterImage}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if jmeterUsername else remoteCmd
    logging.info("Apply load: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def getJMeterSummary():
    logging.debug("Getting throughput info...")
    remoteCmd = f"{docker} logs --tail=200 {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if jmeterUsername else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.DEVNULL)
    lines = output.splitlines()

    # Find the last line that contains
    # summary = 110757 in    30s = 3688.6/s Avg:    12 Min:     0 Max:   894 Err:     0 (0.00%)
    # or
    # summary = 233722 in 00:02:00 = 1947.4/s Avg:     0 Min:     0 Max:   582 Err:     0 (0.00%)
    elapsedTime = 0
    throughput = 0
    errs = 0
    totalTransactions = 0
    lastSummaryLine = ""
    slidingWindow = deque([0.0, 0.0, 0.0])
    pattern1 = re.compile('summary \+\s+(\d+) in\s+(\d+\.*\d*)s =\s+(\d+\.\d+)/s.+Finished: 0')
    pattern2 = re.compile('summary \+\s+(\d+) in\s+(\d\d):(\d\d):(\d\d) =\s+(\d+\.\d+)/s.+Finished: 0')
    for line in lines:
        # summary +  17050 in 00:00:06 = 2841.7/s Avg:     0 Min:     0 Max:    49 Err:     0 (0.00%) Active: 2 Started: 2 Finished: 0
        if line.startswith("summary +"):
            if printRampup:
                print(line)
            m = pattern1.match(line)
            if m:
                thr = float(m.group(3))
                slidingWindow.pop()
                slidingWindow.appendleft(thr)
            else:
                m = pattern2.match(line)
                if m:
                    thr = float(m.group(5))
                    slidingWindow.pop()
                    slidingWindow.appendleft(thr)

        if line.startswith("summary ="):
            lastSummaryLine = line

    pattern = re.compile('summary =\s+(\d+) in\s+(\d+\.*\d*)s =\s+(\d+\.\d+)/s.+Err:\s*(\d+)')
    m = pattern.match(lastSummaryLine)
    if m:
        totalTransactions = float(m.group(1)) # First group is the total number of transactions/pages that were processed
        elapsedTime = float(m.group(2)) # Second group is the interval of time that passed
        throughput = float(m.group(3)) # Third group is the throughput value
        errs = int(m.group(4))  # Fourth group is the number of errors
    else: # Check the second pattern
        pattern = re.compile('summary =\s+(\d+) in\s+(\d\d):(\d\d):(\d\d) =\s+(\d+\.\d+)/s.+Err:\s*(\d+)')
        m = pattern.match(lastSummaryLine)
        if m:
            totalTransactions = float(m.group(1))  # First group is the total number of transactions/pages that were processed
            # Next 3 groups are the interval of time that passed
            elapsedTime = float(m.group(2))*3600 + float(m.group(3))*60 + float(m.group(4))
            throughput = float(m.group(5))  # Fifth group is the throughput value
            errs = int(m.group(6)) # Sixth group is the number of errors
    # Compute the peak throughput as a sliding window of 3 consecutive entries
    peakThr = sum(slidingWindow)/len(slidingWindow)

    #print (str(elapsedTime), throughput, sep='\t')
    if errs > 0:
        logging.error("JMeter Errors: {n}".format(n=errs))
    return throughput, elapsedTime, peakThr, errs

def stopJMeter():
    remoteCmd = f"{docker} rm {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if jmeterUsername else remoteCmd
    logging.debug("Removing jmeter: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

def runPhase(duration, numClients):
    logging.debug("Sleeping for {n} sec".format(n=delayBetweenRepetitions))
    time.sleep(delayBetweenRepetitions)

    applyLoad(duration, numClients)

    # Wait for load to finish
    remoteCmd = f"{docker} wait {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Wait for {jmeter} to end: {cmd}".format(jmeter=jmeterContainerName, cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

    # Read throughput
    thr, elapsed, peakThr, errors = getJMeterSummary()

    stopJMeter()
    if logging.root.level <= logging.DEBUG:
        print("Throughput={thr:7.1f} duration={elapsed:6.1f} peak={peakThr:7.1f} errors={err:4d}".format(thr=thr,elapsed=elapsed,peakThr=peakThr,err=errors))
    if errors > 0:
        logging.error(f"JMeter encountered {errors} errors")
    return thr, elapsed, peakThr, errors

def runBenchmarkOnce(image, javaOpts):
    # Will apply load in small bursts
    maxPulses = numRepetitionsOneClient + numRepetitions50Clients
    thrResults = [math.nan for i in range(maxPulses)] # np.full((maxPulses), fill_value=np.nan, dtype=np.float)
    rss, peakRss, cpu = math.nan, math.nan, math.nan
    peakThroughput = 0
    curlProcess = None

    restoreDatabase(mongoMachine, mongoUsername, mongoImage)

    # Start an external program called curl_loop in background
    # This program will keep sending requests to the app server until it responds with 200 once
    if getFirstResponseTime:
        curlCmd = f"{firstResponseHelperScript}"
        curlProcess = subprocess.Popen(shlex.split(curlCmd), universal_newlines=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)

    crtTime = datetime.datetime.now()
    containerStartTimeMs = (crtTime.minute * 60 + crtTime.second)*1000 + crtTime.microsecond//1000

    instanceID = startAppServerContainer(host=appServerMachine, username=username, instanceName=containerName, image=image, port=appServerPort, cpus=cpuLimit, mem=memLimit, jvmArgs=javaOpts, mountOpts=mountOpts, mongoMachine=mongoMachine)
    if instanceID is None:
        return thrResults, rss, peakRss, cpu

    # We know the app started successfuly

    if doApplyLoad:
        for pulse in range(maxPulses):
            if pulse >= numRepetitionsOneClient:
                cli = numClients
                duration = durationOfOneRepetition
            else:
                cli = 1
                duration = durationOfOneClient
            thrResults[pulse], elapsed, peakThr, errors = runPhase(duration, cli)
            if errors == 0:
                peakThroughput = max(peakThroughput, peakThr)

    # Collect RSS at end of run
    serverPID = getJavaPIDFromContainer(host=appServerMachine, username=username, instanceID=instanceID)

    if int(serverPID) > 0:
        rss, peakRss = getRss(host=appServerMachine, username=username, pid=serverPID)
        logging.debug("Memory: RSS={rss} MB  PeakRSS={peak} MB".format(rss=rss,peak=peakRss))
    else:
        logging.warning("Cannot get server PID. RSS will not be available")
    time.sleep(2)

    # If there were errors during the run, invalidate throughput results
    if doApplyLoad:
        if not checkAppServerForErrors(instanceID, appServerMachine, username):
            thrResults = [math.nan for i in range(maxPulses)] #np.full((maxPulses), fill_value=np.nan, dtype=np.float) # Reset any throughput values

    # stop container and read CompCPU
    rc = stopAppServerByID(appServerMachine, username, instanceID)
    cpu = getCompCPUFromContainer(appServerMachine, username, instanceID)
    startTimeMillis, firstResponseTime = getAppServerStartupTime(appServerMachine, username, instanceID, containerStartTimeMs, curlProcess)
    removeForceContainer(host=appServerMachine, username=username, instanceName=containerName)

    # return throughput as an array of throughput values for each burst and also the RSS
    return thrResults, peakThroughput, rss, peakRss, float(cpu/1000.0), startTimeMillis, firstResponseTime

####################### runBenchmarksIteratively ##############################
def runBenchmarkIteratively(numIter, image, javaOpts):
    # Initialize stats; 2D array of throughput results
    numPulses = numRepetitionsOneClient + numRepetitions50Clients
    thrResults = [] # List of lists
    rssResults = [] # Just a list
    peakRssResults = []
    cpuResults = []
    startupResults = []
    firstResponseResults = []

    # clear SCC if needed (by destroying the SCC volume)
    if doColdRun:
        clearSCC(appServerMachine, username)

    useJITServer = "-XX:+UseJITServer" in javaOpts
    if useJITServer:
        startJITServer()
        time.sleep(1) # Give JITServer some time to start

    for iter in range(numIter):
        thrList, peakThroughput, rss, peakRss, cpu, startupTime, firstResponseTime = runBenchmarkOnce(image, javaOpts)
        lastThr = meanLastValues(thrList, numMeasurementTrials) # average for last N pulses
        print("Run {iter}: Thr={lastThr:6.1f} RSS={rss:6.0f} MB  PeakRSS={peakRss:6.0f} MB  CPU={cpu:6.1f} sec  PeakThroughput={pt:6.1f}".
              format(iter=iter, lastThr=lastThr, rss=rss, peakRss=peakRss, cpu=cpu, pt=peakThroughput))
        thrResults.append(thrList) # copy all the pulses
        rssResults.append(rss)
        peakRssResults.append(peakRss)
        cpuResults.append(cpu)
        startupResults.append(startupTime)
        firstResponseResults.append(firstResponseTime)

    # print stats
    print(f"\nResults for image: {image} and opts: {javaOpts}")
    thrAvgResults = [math.nan for i in range(numIter)] # np.full((numIter), fill_value=np.nan, dtype=np.float)
    for iter in range(numIter):
        print("Run", iter, end="")
        for pulse in range(numPulses):
            print("\t{thr:7.1f}".format(thr=thrResults[iter][pulse]), end="")
        thrAvgResults[iter] = meanLastValues(thrResults[iter], numMeasurementTrials) #np.nanmean(thrResults[iter][-numMeasurementTrials:])
        print("\tAvg={thr:7.1f}  RSS={rss:7.0f} MB  PeakRSS={peakRss:7.0f} MB  CPU={cpu:7.1f} sec".
             format(thr=thrAvgResults[iter], rss=rssResults[iter], peakRss=peakRssResults[iter], cpu=cpuResults[iter]))

    verticalAverages = []  #verticalAverages = np.nanmean(thrResults, axis=0)
    for pulse in range(numPulses):
        total = 0
        numValidEntries = 0
        for iter in range(numIter):
            if not math.isnan(thrResults[iter][pulse]):
                total += thrResults[iter][pulse]
                numValidEntries += 1
        verticalAverages.append(total/numValidEntries if numValidEntries > 0 else math.nan)

    print("Avg:", end="")
    for pulse in range(numPulses):
        print("\t{thr:7.1f}".format(thr=verticalAverages[pulse]), end="")
    print("\tAvg={avgThr:7.1f}  RSS={rss:7.0f} MB  PeakRSS={peakRss:7.0f} MB  CPU={cpu:7.1f} sec".
          format(avgThr=nanmean(thrAvgResults), rss=nanmean(rssResults), peakRss=nanmean(peakRssResults), cpu=nanmean(cpuResults)))

    printStats(thrAvgResults, "Thr stats:")
    printStats(rssResults, "RSS stats:")
    printStats(peakRssResults, "Peak RSS stats:")
    printStats(cpuResults, "CompCPU stats:")
    printStats(startupResults, "StartTime stats:")
    if getFirstResponseTime:
        printStats(firstResponseResults, "FirstResp stats:")

    if useJITServer:
        stopJITServer()

############################ MAIN ##################################
def mainRoutine():
    if  len(sys.argv) < 2:
        print ("Program must have an argument: the number of iterations\n")
        sys.exit(-1)

    cleanup() # Clean-up from a previous possible bad run

    startMongo(mongoMachine, mongoUsername, mongoImage)

    if doColdRun:
        logging.warning("Will do a cold run before each set")

    for config in configs:
        runBenchmarkIteratively(numIter=int(sys.argv[1]), image=config["image"], javaOpts=config["args"])

    # Execute final clean-up step
    cleanup()

mainRoutine()