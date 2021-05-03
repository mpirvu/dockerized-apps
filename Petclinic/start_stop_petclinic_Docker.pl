use warnings; 
use strict;
# Perl script to measure start-up time and footprint of Petclinic app running in docker containers
# Run as:  "perl start_stop_petclinic_Docker.pl NumIterations"
# The JVM is embedded inside the container, thus we only to specify the container image
# and not the JVM to run with

my $verbose = 1;
my $doColdRun = 1; # destroy the SCC volume. Will not look at first (cold) run
my $waitTime = 15; # wait time for app to startup before reading the logs

# !! Please select the docker image you want to use !!
#my $imageName = "petclinic:openj9-java11-0.20"; # which docker image to use
#my $imageName = "petclinic:openj9-java11-0.23";
my $imageName = "petclinic:openj9-java11-0.23-mlscc";
#my $imageName = "petclinic:openj9-java11-nightly-mlscc-noportablescc";
#my $imageName = "petclinic:openj9-java11-nightly-slscc";
#my $imageName = "petclinic:openj9-java11-nightly"; # which docker image to use
#my $imageName = "petclinic:hotspot-java11-nightly"; # which docker image to use
my $numCPUs = 4; # limit for the container
my $memLimit = "512m"; # limit for the container
my $instanceName = "petclinic";

my $appVolume = "petclinicvolume";

# Additional options passed to the JVM
my @jvmOptions = (
    #"-Xshareclasses:name=petclinicscc,cacheDir=/tmp,groupAccess",
    #"-XX:+ClassRelationshipVerifier",
    #"-Xshareclasses:none -XX:+ClassRelationshipVerifier",
    "-Xtune:virtualized",
    #"-Xshareclasses:none",
); # jvmOptions                 



if (@ARGV != 1) {
    die "need number of iterations\n";
}
my $numIter = shift(@ARGV);
$| = 1; # auto-flush stdout

foreach my $jvmOpts (@jvmOptions) {
    # run the benchmark n times
    runBenchmarkIteratively($jvmOpts);
}

# How to use   &UpdateStats($value, @array);
# First param is the value of the sample; the second array is a param with
# the following configuration:   my @arrayName= (0,0,0,10000000,0); # samples, sum, max, min, sumsq
sub UpdateStats {
    $_[1] += 1;           # update samples
    $_[2] += $_[0];       # update sum
    $_[5] += $_[0]*$_[0]; # update sumsq
    if ($_[0] > $_[3]) {  #update MAX
        $_[3] = $_[0];
    }
    if ($_[0] < $_[4]) {  #update MIN
        $_[4] = $_[0];
    }
}

# subroutine to print the stats for an array
sub PrintStats {
    my($text, $samples, $sum, $maxVal, $minVal, $sumsq) = @_;
    my $confidenceInterval = 0;
    if ($samples > 0) {
        my $stddev = 0;
        if ($samples > 1) {
            my $variance = (($sumsq-$sum*$sum/$samples)/($samples-1));
            $stddev = sqrt($variance);
            $confidenceInterval = tdistribution($samples-1)*$stddev/sqrt($samples)*100.0/($sum/$samples);
        }
        printf "$text\tavg=%.2f\tmin=%.2f\tmax=%.2f\tstdDev=%.1f\tmaxVar=%.2f%%\tconfInt=%.2f%%\tsamples=%2d\n", $sum/$samples, $minVal, $maxVal, $stddev, (100.0*$maxVal/$minVal-100.0), $confidenceInterval, $samples;
    }
}

sub tdistribution {
    my $degreesOfFreedom = shift;
    my @table = (6.314, 2.92, 2.353, 2.132, 2.015, 1.943, 1.895, 1.860, 1.833, 1.812, 1.796, 1.782, 1.771, 1.761, 1.753, 1.746, 1.740, 1.734, 1.729, 1.725);

    if ($degreesOfFreedom < 1) { return -1;}
    elsif ($degreesOfFreedom <= 20) { return $table[$degreesOfFreedom-1]; }
    else {
        if($degreesOfFreedom < 30)   { return 1.697; }
        if($degreesOfFreedom < 40)   { return 1.684; }
        if($degreesOfFreedom < 50)   { return 1.676; }
        if($degreesOfFreedom < 60)   { return 1.671; }
        if($degreesOfFreedom < 70)   { return 1.667; }
        if($degreesOfFreedom < 80)   { return 1.664; }
        if($degreesOfFreedom < 90)   { return 1.662; }
        if($degreesOfFreedom < 100)  { return 1.660; }
        return 1.65;
    }
}

sub getContainerMemory {
    my $instanceName = shift;
    my @dockerStats = `docker stats --no-stream $instanceName`;
    my $memoryInfo = $dockerStats[1];
    print("Memory info: $memoryInfo\n") if $verbose >= 3; 
    if ($memoryInfo =~ /\S+\s+\S+\s+\S+\s+(\d+\.?\d+)MiB/) {
       return $1;
    } else {
       return 0;
    }
}

##################################################################################
sub getPIDOnHost {
    my $instanceName = shift;
    my $javaPid = 0;
    print("Finding PID of java process in container $instanceName\n") if $verbose >= 5;

    # docker top may show 1 or 2 processes; we are looking for the one with bin/java
    #UID                 PID                 PPID                C                   STIME               TTY                 TIME                CMD
    #root                18183               18165               0                   13:51               ?                   00:00:00            /bin/sh /work/scriptToRunInsideDocker.sh
    #root                18200               18183               6                   13:51               ?                   00:00:01            java -Xtune:virtualized -jar application.jar
    my @lines = `docker top $instanceName`;
    foreach my $line (@lines) {
        printf $line if $verbose >= 5;
        if ($line =~ /^(\w+)\s+(\d+)\s+\d+.+java /) {
            $javaPid = $2;
            last;
        }
    }
    print("Found PID of java process in container: $javaPid\n") if $verbose >= 5;
    return $javaPid;
}

######################################################################
sub computeWorkingSet {
    my $javaPid = shift;

    my $ws = `ps  -orss,vsz,cputime --no-headers --pid $javaPid`;
    if ($ws =~ /^(\d+)\s+(\d+)\s+(\d+):(\d+):(\d+)/) {
        return $1;
    } else {
        print "Warning: WS for PID ${javaPid} is 0\n";
        return 0;
    }
}

sub runOnce {
    my $jvmOptions = shift;
    my $elapsed = 0.0;
    my $elapsed1 = 0.0;
    
    # read start time
    my $startTime = 0.0;
    my $startTimeString = `date +"%H:%M:%S:%N"`;

    if ($startTimeString =~ /^(\d\d):(\d\d):(\d\d):(\d\d\d)/) {
        $startTime = $2*60.0 + $3 + $4/1000.0;
    } else {
        print("Cannot parse current time");
        exit;
    }

    # launch docker container
    # If using volumes for the SCC, add:  --mount source=$appVolume,target=/tmp/.classCache 
    my $cmd = "docker run -d --cpus=${numCPUs} -m=${memLimit} --rm -v /tmp/vlogDir:/tmp/vlogDir -e JAVA_OPTS=\"${jvmOptions}\" --name $instanceName $imageName";
    print "+ Lanching petclinic with: $cmd" if $verbose >= 3; 
    `$cmd`;


    # wait few seconds, then read stdout from the container
    sleep $waitTime;
    my @lines = `docker logs --tail=100 $instanceName`;

    # parsing the output
    # 20:08:40:825286540
    # 2020-10-20 22:39:59.590  INFO 7 --- [           main] o.s.s.petclinic.PetClinicApplication     : Started PetClinicApplication in 4.93 seconds (JVM running for 5.351)
    print("Start time is $startTimeString\n") if $verbose >= 3;
    my $startTimeInsideContainer = 0.0;
    foreach my $line (@lines) {
        print $line if $verbose >= 5;
        if ($line =~ /^(\d\d):(\d\d):(\d\d):(\d\d\d)/) {
            # This is the start time from inside container
            $startTimeInsideContainer = $2*60.0 + $3 + $4/1000.0;
            if ($startTimeInsideContainer < $startTime) {
                $startTimeInsideContainer += 3600; # add an extra hour
            }
	    print("Found start time inside container $line = $startTimeInsideContainer\n") if $verbose >= 3;
        }
        elsif ($line =~ /.+ (\d\d):(\d\d):(\d\d)\.(\d\d\d)\s+INFO.+Started PetClinicApplication in/) {
            # This is the end time
            my $endTime = $2*60.0 + $3 + $4/1000.0;
            if ($endTime < $startTime) {
                $endTime += 3600; # add an extra hour
            }
            print("Found end time $line = $endTime\n") if $verbose >= 5; 
            $elapsed = $endTime - $startTimeInsideContainer unless $startTimeInsideContainer==0.0;
            $elapsed1 = $endTime - $startTime unless $startTimeInsideContainer==0.0;
            printf("Start time excluding container prep=%.3f\n", $elapsed) unless $startTimeInsideContainer==0.0;
            printf("Start time including container prep=%.3f\n", $elapsed1) unless $startTimeInsideContainer==0.0;
            last;
        } 
    } 
    # read the memory taken as seen by docker
    my $footprint = getContainerMemory("$instanceName");
    print("rss docker=$footprint\n") if $verbose >=2 ;

    # read RSS
    my $javaPID = getPIDOnHost("$instanceName");
    my $rss = computeWorkingSet($javaPID);
    print("Stop $instanceName\n") if $verbose >= 3;
    `docker stop $instanceName`;
    sleep 3;
    print("$elapsed $elapsed1 $footprint $rss\n") if $verbose >= 3;
    return ($elapsed, $elapsed1, $footprint, $rss);
}


sub runBenchmarkIteratively {
    #my $javaHome   = shift;
    my $jvmOptions = shift;
    my @startWithoutContainerStats  = (0,0,0,10000000,0);
    my @startWithContainerStats     = (0,0,0,10000000,0);
    my @footprintStats              = (0,0,0,10000000,0);
    my @rssStats                    = (0,0,0,10000000,0);

    if ($doColdRun) {
       my $res = `docker volume rm ${appVolume}`;
       print $res if $verbose >= 3;
    }
    print("Running $numIter iterations with JAVA_OPTS=$jvmOptions\n") if $verbose >= 1;

    # iterate n times
    for (my $i=0; $i < $numIter; $i++) {
        my ($elapsed, $elapsed1, $footprint, $rss) = runOnce($jvmOptions);

        if ($elapsed == 0.0 || $elapsed1 == 0.0) {
            next;
        }
        if ($doColdRun && $i == 0) { # skip the cold run
            next;
        }
        # collect throughput stats
        UpdateStats($elapsed, @startWithoutContainerStats);
        UpdateStats($elapsed1, @startWithContainerStats);
        UpdateStats($footprint, @footprintStats) unless $footprint <= 0;
        UpdateStats($rss, @rssStats) unless $rss <= 0;
    }
    print("Results for image=$imageName numCPUs=$numCPUs memLimit=$memLimit JAVA_OPTS=$jvmOptions\n");
    &PrintStats("Startup time no container overhead:", @startWithoutContainerStats);
    &PrintStats("Startup time  + container overhead:", @startWithContainerStats);
    &PrintStats("Resident set size from docker:     ", @footprintStats);
    &PrintStats("Resident set size from OS:         ", @rssStats);
}

