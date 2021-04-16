#!/bin/bash
# Example https://github.com/OpenLiberty/ci.docker/blob/master/releases/latest/full/helpers/build/populate_scc.sh

# Safer bash script
# -e means exit immediately when a command fails
# using -e without -E will cause an ERR trap to not fire in certain scenarios.
# -o pipefail   sets the exit code of a pipeline to that of the rightmost command to exit with a non-zero status, or to zero if all commands of the pipeline exit successfully.
# -u treat unset variables as an error and exit immediately.
# -x print each command before executing it.
set -Eeuox pipefail

SCC_SIZE="45m"  # Default size of the SCC layer.
ITERATIONS=2    # Number of iterations to run to populate it.

echo $PWD

export OPENJ9_JAVA_OPTIONS="-Xshareclasses:name=openj9_system_scc,cacheDir=/opt/java/.scc"
CREATE_LAYER="$OPENJ9_JAVA_OPTIONS,createLayer,groupAccess"
DESTROY_LAYER="$OPENJ9_JAVA_OPTIONS,destroy"
PRINT_LAYER_STATS="$OPENJ9_JAVA_OPTIONS,printTopLayerStats"

while getopts ":i:s:tdh" OPT
do
  case "$OPT" in
    i)
      ITERATIONS="$OPTARG"
      ;;
    s)
      [ "${OPTARG: -1}" == "m" ] || ( echo "Missing m suffix." && exit 1 )
      SCC_SIZE="$OPTARG"
      ;;
    h)
      echo \
"Usage: $0 [-i iterations] [-s size]
  -i <iterations> Number of iterations to run to populate the SCC. (Default: $ITERATIONS)
  -s <size>       Size of the SCC in megabytes (m suffix required). (Default: $SCC_SIZE)"
      exit 1
      ;;
    \?)
      echo "Unrecognized option: $OPTARG" 1>&2
      exit 1
      ;;
    :)
      echo "Missing argument for option: $OPTARG" 1>&2
      exit 1
      ;;
  esac
done

OLD_UMASK=`umask`
umask 002 # 002 is required to provide group rw permission to the cache when `-Xshareclasses:groupAccess` options is used

# Explicity create a class cache layer for this image layer here
java $CREATE_LAYER -Xscmx$SCC_SIZE -version

# Populate the newly created class cache layer.
for ((i=0; i<$ITERATIONS; i++))
do
  java -jar application.jar &
  JAVA_PID=$!
  sleep 10 
  echo "Killing process $JAVA_PID"
  kill -9 $JAVA_PID
done

# restore umask
umask ${OLD_UMASK}

# Tell the user how full the final layer is.
FULL=`( java $PRINT_LAYER_STATS || true ) 2>&1 | awk '/^Cache is [0-9.]*% .*full/ {print substr($3, 1, length($3)-1)}'`
echo "SCC layer is $FULL% full."

