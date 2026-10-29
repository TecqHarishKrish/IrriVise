cd "$(dirname "$0")"
run() { ps=${1#aug_}; ps=${ps%_*}; d=${1##*_}; python3 faultbench.py "g_$1" validation "{\"twin_bias\":{\"method\":\"augmented\",\"prior_std_m3m3\":$ps,\"drift_std_m3m3\":$d}}" > "g_$1.txt" 2>&1; }
export -f run
xargs -P "$(nproc)" -I{} bash -c 'run {}' < grid.txt
