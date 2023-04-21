import logging # https://www.machinelearningplus.com/python/python-logging-guide/
import shlex, subprocess
import time # for sleep
import re # for regular expressions
import math
import sys # for number of arguments
import queue
import os # for environment variables

# Set level to level=logging.DEBUG, level=logging.INFO or level=WARNING reduced level of verbosity
logging.basicConfig(level=logging.DEBUG, format='%(asctime)s :: %(levelname)s :: %(message)s',)
docker = 'podman'

################### Benchmark configuration #################
doColdRun       = False  # when True we clear the SCC before the first run. Set it to False for embedded SCC
appServerHost   = "9.46.116.36" # Cannot use localhost because JMeter runs in docker
username        = "" # for connecting remotely to the SUT. If this is empty we assume that local machine is going to be used
instanceName    = "petclinic"
appServerPort   = "8080"
appServerHttpsPort = "8443"
cpuAffinity     = "1"
memLimit        = "1G"
delayToStart    = 30 # seconds; waiting for the AppServer to start before checking for valid startup
extraDockerOpts = "-v /tmp:/tmp" # extra options to pass to docker run
netOpts         = "--network=slirp4netns" if docker == "podman" else "" # for podman we need to use slirp4netns if running as root.
############### SCC configuration #####################
useSCCVolume    = False  # set to true to have a SCC mounted in a volume; False for embedded SCC
appServerDir    = "/work" # This is the directory in the container instance
sccInstanceDir  = f"{appServerDir}/.classCache" # Location of the shared class cache in the instance
SCCVolumeName   = "scc_volume"
mountOpts       = f"--mount type=volume,src={SCCVolumeName},target={sccInstanceDir}" if useSCCVolume  else ""
############### JMeter CONFIG ###############
jmeterContainerName = "jmeter"
jmeterImage     = "localhost/jmeterpetclinic:3.3"
jmeterMachine   = "localhost"
jmeterUsername  = ""  # If this is empty, we assume that JMeter runs on the local machine
jmeterAffinity  = "2-3"
protocol        = "http" # http or https
################ Load CONFIG ###############
numRepetitionsOneClient = 0
numRepetitions50Clients = 2
durationOfOneClient     = 30 # seconds
durationOfOneRepetition = 300 # seconds
numClients              = 3
delayBetweenRepetitions = 10
numMeasurementTrials    = 1 # Last N trials are used in computation of throughput
thinkTime               = 0 # ms
############################# END CONFIG ####################################

# ENV VARS to use for all runs
TR_Options=""

jvmOptions = [
    "-Xmx1G",
]

appImages = [
    #"petclinic:11-0.29.0",
    "localhost/petclinic:J17-0.38.0",
]


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
    n = len(myList)
    if n <= 1:
        return math.nan
    tvalue = tDistributionValue95(n-1)
    avg, stdDev = nanmean(myList), nanstd(myList)
    marginOfError = tvalue * stdDev / math.sqrt(n)
    return 100.0*marginOfError/avg


def computeStats(myList):
    avg = nanmean(myList)
    stdDev = nanstd(myList)
    min = nanmin(myList)
    max = nanmax(myList)
    ci95 = meanConfidenceInterval95(myList)
    return avg, stdDev, min, max, ci95


def meanLastValues(myList, numLastValues):
    assert numLastValues > 0
    if numLastValues > len(myList):
        numLastValues = len(myList)
    return nanmean(myList[-numLastValues:])


def stopContainersFromImage(host, username, imageName):
    # Find all running containers from image
    remoteCmd = f"{docker} ps --quiet --filter ancestor={imageName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    for containerID in lines:
        remoteCmd = f"{docker} stop {containerID}"
        cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
        print("Stopping container: ", cmd)
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

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
        print("Removing container: ", cmd)
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

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
        if "java" in pid2cmd[pid]:
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


# Given a PID, return RSS and peakRSS for the process
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
        return [0, 0]  # wrong pid?
    i =  s.index("VmRSS:") # Find the position of the substring
    # Take everything from this position till the very end
    # Then split the string 3 times, taking first 3 "words" and putting them into a list
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [0, 0]  # invalid format
    rss = int(tokens[1]) * _scale[tokens[2]] // 1048576 # convert value to bytes and then to  MB

    # repeat for peak RSS
    i =  s.index("VmHWM:")
    tokens = s[i:].split(None, 3)
    if len(tokens) < 3:
        return [0, 0]  # invalid format
    peakRss = int(tokens[1]) * _scale[tokens[2]] // 1048576 # convert value to bytes and then to MB
    return rss, peakRss


def getCompCPUFromContainer(host, username, instanceID):
    logging.debug("Computing CompCPU for AppServer instance {instanceID}".format(instanceID=instanceID))
    # Check that the indicated container still exists
    remoteCmd = f"{docker} ps -a --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("Liberty instance {instanceID} does not exist.".format(instanceID=instanceID))
        return math.nan

    threadTime = 0.0
    remoteCmd = f"{docker} logs --tail=50 {instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT) # I need to capture stderr as well
    liblines = output.splitlines()
    compTimePattern = re.compile("^Time spent in compilation thread =(\d+) ms")
    for line in liblines:
        print(line)
        m = compTimePattern.match(line)
        if m:
            threadTime += float(m.group(1))
    return threadTime if threadTime > 0 else math.nan


def clearSCC(host, username):
    logging.info("Clearing SCC")
    remoteCmd = f"{docker} volume rm --force {SCCVolumeName}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    subprocess.run(shlex.split(cmd), universal_newlines=True)
    # TODO: make sure volume does not exist

'''
return True if AppServer inside given container ID has started successfully; False otherwise
'''
def verifyAppServerInContainerIDStarted(instanceID, host, username):
    remoteCmd = f"{docker} ps --quiet --filter id={instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("AppServer container {instanceID} is not running").format(instanceID=instanceID)
        return False

    remoteCmd = f"{docker} logs --tail=100 {instanceID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    errPattern = re.compile('^.+ ERROR ')

    # 2023-01-21 23:41:45.449  INFO 1 --- [           main] o.s.s.petclinic.PetClinicApplication     : Started PetClinicApplication in 3.564 seconds (JVM running for 3.913)
    # 2023-01-24 11:06:59.960  INFO 1 --- [           main] o.s.boot.SpringApplication               : Started application in 6.355 seconds (JVM running for 7.04)
    readyPattern = re.compile('^(.+) INFO .+ Started (PetClinicApplication|application) in')

    for iter in range(10):
        output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.STDOUT)
        liblines = output.splitlines()
        for line in liblines:
            m = errPattern.match(line)
            if m:
                logging.error("AppServer container {instanceID} errored while starting: {line}").format(instanceID=instanceID,line=line)
                return False
            m1 = readyPattern.match(line)
            if m1:
                if logging.root.level <= logging.INFO:
                    print(line)
                return True # True means success
        time.sleep(1) # wait 1 sec and try again
        logging.warning("Checking again for app start")
    return False


def stopAppServerByID(host, username, containerID):
    remoteCmd = f"{docker} ps --quiet --filter id={containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Stopping container {containerID}".format(containerID=containerID))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("AppServer instance {containerID} does not exist. Might have crashed".format(containerID=containerID))
        return False
    remoteCmd = f"{docker} stop {containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    return True


def removeAppServerByID(host, username, containerID):
    remoteCmd = f"{docker} ps --all --quiet --filter id={containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Removing container {containerID}".format(containerID=containerID))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    lines = output.splitlines()
    if not lines:
        logging.warning("AppServer instance {containerID} does not exist. Might have crashed.".format(containerID=containerID))
        return False
    remoteCmd = f"{docker} rm {containerID}"
    cmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    return True


def startAppServerContainer(host, username, instanceName, image, port, httpsport, cpus, mem, jvmArgs):
    remoteCmd = f"{docker} run -d --cpuset-cpus={cpus} -m={mem} {mountOpts} {extraDockerOpts} {netOpts} -e TR_Options='{TR_Options}' -e _JAVA_OPTIONS='{jvmArgs}' -e TR_PrintCompTime=1  -p {port}:{port} -p {httpsport}:{httpsport} --name {instanceName} {image}"
    dockerRunCmd = f"ssh {username}@{host} \"{remoteCmd}\"" if username else remoteCmd
    logging.info("Starting AppServer instance {instanceName} with cmd: {cmd}".format(instanceName=instanceName,cmd=dockerRunCmd))
    output = subprocess.check_output(shlex.split(dockerRunCmd), universal_newlines=True)
    lines = output.splitlines()
    assert lines, "Error: docker run output is empty".format(l=lines)
    assert len(lines) == 1, f"Error: docker run output containes several lines: {lines}"
    if logging.root.level <= logging.DEBUG:
        print(lines)
    instanceID = lines[0] # ['2ccae49f3c03af57da27f5990af54df8a81c7ce7f7aace9a834e4c3dddbca97e']
    time.sleep(delayToStart) # delay to let application start
    started = verifyAppServerInContainerIDStarted(instanceID, host, username)
    if not started:
        logging.error("AppServer failed to start")
        stopAppServerByID(host, username, instanceID)
        return None
    return instanceID


# Run jmeter remotely
def applyLoad(duration, clients):
    port = appServerHttpsPort if protocol == "https" else appServerPort
    remoteCmd = f"{docker} run -d --net=host --cpuset-cpus={jmeterAffinity} -e JTHREADS={clients} -e JDURATION={duration} -e JPORT={port} -e JHOST={appServerHost} -e JTHINKTIME={thinkTime} --name {jmeterContainerName} {jmeterImage}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if username else remoteCmd
    logging.info("Apply load: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)
    logging.debug(f"{output}")


def stopJMeter():
    remoteCmd = f"{docker} rm {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Removing jmeter: {cmd}".format(cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)


def getJMeterSummary():
    logging.debug("Getting throughput info...")
    remoteCmd = f"{docker} logs --tail=100 {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if username else remoteCmd
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True, stderr=subprocess.DEVNULL)
    lines = output.splitlines()

    # Find the last line that contains
    # summary = 110757 in    30s = 3688.6/s Avg:    12 Min:     0 Max:   894 Err:     0 (0.00%)
    # or
    # summary = 233722 in 00:02:00 = 1947.4/s Avg:     0 Min:     0 Max:   582 Err:     0 (0.00%)

    elapsedTime = 0
    throughput = math.nan
    errs = 0
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

    pattern = re.compile('summary =\s+(\d+) in\s+(\d+\.*\d*)s =\s+(\d+\.\d+)/s.+Err:\s*(\d+)')
    m = pattern.match(lastSummaryLine)
    if m:
        # First group is the total number of transactions/pages that were processed
        totalTransactions = float(m.group(1))
        # Second group is the interval of time that passed
        elapsedTime = float(m.group(2))
        # Third group is the throughput value
        throughput = float(m.group(3))
        errs = int(m.group(4))
    else: # Check the second pattern
        pattern = re.compile('summary =\s+(\d+) in\s+(\d\d):(\d\d):(\d\d) =\s+(\d+\.\d+)/s.+Err:\s*(\d+)')
        m = pattern.match(lastSummaryLine)
        if m:
            # First group is the total number of transactions/pages that were processed
            totalTransactions = float(m.group(1))
            # Next 3 groups are the interval of time that passed
            elapsedTime = float(m.group(2))*3600 + float(m.group(3))*60 + float(m.group(4))
            # Fifth group is the throughput value
            throughput = float(m.group(5))
            errs = int(m.group(6))
    # Compute the peak throughput as the average of the last 3 throughput values
    peakThr = 0.0
    if len(queue) >= 3:
        queue = queue[-3:]
        peakThr = sum(queue)/3.0

    #print (str(elapsedTime), throughput, sep='\t')
    return throughput, elapsedTime, peakThr, errs


def runPhase(duration, clients):
    logging.debug("Sleeping for {n} sec".format(n=delayBetweenRepetitions))
    time.sleep(delayBetweenRepetitions)

    applyLoad(duration, clients)

    # Wait for load to finish
    remoteCmd = f"{docker} wait {jmeterContainerName}"
    cmd = f"ssh {jmeterUsername}@{jmeterMachine} \"{remoteCmd}\"" if username else remoteCmd
    logging.debug("Wait for {jmeter} to end: {cmd}".format(jmeter=jmeterContainerName, cmd=cmd))
    output = subprocess.check_output(shlex.split(cmd), universal_newlines=True)

    # Read throughput
    thr, elapsed, peakThr, errors = getJMeterSummary()

    stopJMeter()
    print("Throughput={thr:7.1f} duration={elapsed:6.1f} peak={peakThr:7.1f} errors={err:4d}".format(thr=thr,elapsed=elapsed,peakThr=peakThr,err=errors))
    if errors > 0:
        logging.error(f"JMeter encountered {errors} errors")
    return thr


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


def runBenchmarkOnce(image, javaOpts):
    # Will apply load in small bursts
    maxPulses = numRepetitionsOneClient + numRepetitions50Clients
    thrResults = [math.nan for i in range(maxPulses)] # np.full((maxPulses), fill_value=np.nan, dtype=np.float)
    rss, peakRss = math.nan, math.nan

    instanceID = startAppServerContainer(host=appServerHost, username=username, instanceName=instanceName, image=image, port=appServerPort, httpsport=appServerHttpsPort, cpus=cpuAffinity, mem=memLimit, jvmArgs=javaOpts)
    if instanceID is None:
        return thrResults, rss

    for pulse in range(maxPulses):
        if pulse >= numRepetitionsOneClient:
            cli = numClients
            duration = durationOfOneRepetition
        else:
            cli = 1
            duration = durationOfOneClient
        thrResults[pulse] = runPhase(duration, cli)

    # Collect RSS at end of run
    serverPID = getJavaPIDFromContainer(host=appServerHost, username=username, instanceID=instanceID)

    if int(serverPID) > 0:
        rss, peakRss = getRss(host=appServerHost, username=username, pid=serverPID)
        logging.debug("Memory: RSS={rss} PeakRSS={peak}".format(rss=rss,peak=peakRss))
    else:
        logging.warning("Cannot get server PID. RSS will not be available")
    time.sleep(2)

    # If there were errors during the run, invalidate throughput results
    if not checkAppServerForErrors(instanceID, appServerHost, username):
        thrResults = [math.nan for i in range(maxPulses)] #np.full((maxPulses), fill_value=np.nan, dtype=np.float) # Reset any throughput values

    # stop container
    success = stopAppServerByID(appServerHost, username, instanceID)
    if success:
        # read CompCPU
        cpu = getCompCPUFromContainer(appServerHost, username, instanceID)
        success = removeAppServerByID(appServerHost, username, instanceID)
        if not success:
            logging.error("Cannot remove container {id}".format(id=instanceID))
            sys.exit(-1)
    else:
        sys.exit(-1)

    # return throughput as an array of throughput values for each burst and also the RSS
    return thrResults, rss, peakRss, float(cpu/1000.0)


def runBenchmarkIteratively(numIter, image, javaOpts):
    # Initialize stats; 2D array of throughput results
    numPulses = numRepetitionsOneClient + numRepetitions50Clients
    thrResults = [] # List of lists
    rssResults = [] # Just a list
    cpuResults = []

    # clear SCC if needed (by destroying the SCC volume)
    if doColdRun:
        clearSCC(appServerHost, username)

    for iter in range(numIter):
        thrList, rss, peakRss, cpu = runBenchmarkOnce(image, javaOpts)
        lastThr = meanLastValues(thrList, numMeasurementTrials) # average for last N pulses
        print(f"Run {iter}: Thr={lastThr:6.1f} RSS={rss:6.1f} MB  PeakRSS={peakRss:6.1f} MB  CPU={cpu:4.1f} sec".format(lastThr=lastThr,rss=rss,peakRss=peakRss,cpu=cpu))
        thrResults.append(thrList) # copy all the pulses
        rssResults.append(rss)
        cpuResults.append(cpu)

    # print stats
    print(f"\nResults for image: {image} and opts: {javaOpts}")
    thrAvgResults = [math.nan for i in range(numIter)] # np.full((numIter), fill_value=np.nan, dtype=np.float)
    for iter in range(numIter):
        print("Run", iter, end="")
        for pulse in range(numPulses):
            print("\t{thr:7.1f}".format(thr=thrResults[iter][pulse]), end="")
        thrAvgResults[iter] = meanLastValues(thrResults[iter], numMeasurementTrials) #np.nanmean(thrResults[iter][-numMeasurementTrials:])
        print("\tAvg={thr:7.1f}  RSS={rss:7d} MB  CompCPU={cpu:5.1f} sec".format(thr=thrAvgResults[iter], rss=rssResults[iter], cpu=cpuResults[iter]))

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
    print("\tAvg={avgThr:7.1f}  RSS={rss:7.0f} MB  CompCPU={cpu:5.1f}".format(avgThr=nanmean(thrAvgResults), rss=nanmean(rssResults), cpu=nanmean(cpuResults)))
    # Throughput stats
    avg, stdDev, min, max, ci95 = computeStats(thrAvgResults)
    print("Throughput stats: Avg={avg:7.1f}  StdDev={stdDev:7.1f}  Min={min:7.1f}  Max={max:7.1f}  Max/Min={maxmin:7.1f} CI95={ci95:7.1f}%".
                        format(avg=avg, stdDev=stdDev, min=min, max=max, maxmin=max/min, ci95=ci95))


############################ MAIN ##################################
if  len(sys.argv) < 2:
    print ("Program must have an argument: the number of iterations\n")
    sys.exit(-1)

# Clean-up from a previous possible bad run
for appServerImage in appImages:
    removeContainersFromImage(appServerHost, username, appServerImage)
removeContainersFromImage(jmeterMachine, jmeterUsername, jmeterImage)

if doColdRun:
    print("Will do a cold run before each set")

for jvmOpts in jvmOptions:
    for appServerImage in appImages:
        runBenchmarkIteratively(numIter=int(sys.argv[1]), image=appServerImage, javaOpts=jvmOpts)

