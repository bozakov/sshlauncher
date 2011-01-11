#!/bin/bash
for ((i=1;i<=24;i++)); do
    echo "==== running test nr. $i ===="
    # calculate packets per second	
    let SL_PPS=${SL_I}*85
    export SL_PPS
    export SL_I=$i
    sshlauncher.py spruce.config
    scp zbozakov@node0.Dumbbell.Experiment.emulab.net:logs/*bz2 ./
done
