#!/bin/bash
bash -c 'while [[ "$(curl -s -o /dev/null -w ''%{http_code}'' localhost:9080/pingperf/ping/greeting)" != "200" ]]; do sleep .00001; done'
date +"%H:%M:%S:%N"
