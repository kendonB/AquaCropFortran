#!/bin/sh
set -eu

# Invoked by `make -C src test`; all generated data stay outside the source tree.
executable=$(pwd)/aquacrop
unit_test=$(pwd)/temperature_endpoints_test
repo=$(cd .. && pwd)
test_dir=$(mktemp -d)
trap 'rm -rf "$test_dir"' EXIT HUP INT TERM
cd "$test_dir"
"$unit_test"

cp -R "$repo/testcase" full
mkdir -p full/OUTP
(cd full && "$executable" >run.log 2>&1) || {
    cat full/run.log >&2
    exit 1
}
cp -R "$repo/testcase" truncated
mkdir -p truncated/OUTP
head -n 1040 truncated/DATA/Ottawa.Tnx >weather.tmp
mv weather.tmp truncated/DATA/Ottawa.Tnx
(cd truncated && "$executable" >run.log 2>&1) || {
    cat truncated/run.log >&2
    exit 1
}

# Both runs cover the same 175 crop days, including 28 October 2016.
cmp full/SIMUL/TCrop.SIM truncated/SIMUL/TCrop.SIM
# The truncated record previously set the maturity threshold and cycle to -9.
awk '
    $1 == "RunNr" { for (i = 1; i <= NF; i++) column[$i] = i }
    $1 == "Tot(3)" {
        found = 1
        if ($(column["Cycle"]) != 175) exit 1
    }
    END { if (!found) exit 1 }
' truncated/OUTP/OttawaPRMseason.OUT
printf '%s\n' 'Ottawa final-weather-day regression passed'
