#!/usr/bin/env bash
# TrustSense TIA simulation runner
# Requires: ngspice, sky130A PDK (set PDK_ROOT), gnuplot (optional, for plots)
#
# Usage:
#   PDK_ROOT=/path/to/pdk ./run-tia-sim.sh
#
# If PDK_ROOT is not set, defaults to /usr/share/pdk (common volare/open_pdks
# install location). Edit if your PDK lives elsewhere.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

: "${PDK_ROOT:=/usr/share/pdk}"
export PDK_ROOT

NETLIST="tia.spice"
LOG="tia-sim.log"
RESULTS="tia-results.txt"

if ! command -v ngspice >/dev/null 2>&1; then
  echo "ERROR: ngspice not found on PATH." >&2
  echo "Install it (e.g. 'sudo dnf install ngspice' on Fedora) and re-run." >&2
  exit 1
fi

if [ ! -d "$PDK_ROOT/sky130A" ]; then
  echo "ERROR: sky130A PDK not found under PDK_ROOT=$PDK_ROOT" >&2
  echo "Install via 'pip install volare && volare enable <hash>' or open_pdks," >&2
  echo "then re-run with PDK_ROOT pointing at the install." >&2
  exit 1
fi

echo "Running ngspice on $NETLIST (PDK_ROOT=$PDK_ROOT)..."
ngspice -b "$NETLIST" 2>&1 | tee "$LOG"

echo ""
echo "Extracting measurements..."

extract() {
  # grabs the last "<name> = <value>" style line ngspice prints for a
  # given .measure result name
  grep -E "^${1}[[:space:]]*=" "$LOG" | tail -n1 | sed -E 's/[[:space:]]+/ /g'
}

{
  echo "TrustSense TIA -- simulation results"
  echo "Generated: $(date -u +'%Y-%m-%d %H:%M:%S UTC')"
  echo "Netlist:   $NETLIST"
  echo ""
  echo "-- DC / power ---------------------------------------------"
  extract "power_op"
  echo ""
  echo "-- AC (gain, bandwidth) ------------------------------------"
  extract "gain_dc"
  extract "gain_db_dc"
  extract "bw_3db"
  echo ""
  echo "-- Noise -----------------------------------------------------"
  extract "onoise_total"
  extract "inoise_total"
  echo ""
  echo "-- Transient (rise time, power) ------------------------------"
  extract "trise"
  extract "power_total"
} | tee "$RESULTS"

echo ""
echo "Full log:      $LOG"
echo "Results:       $RESULTS"
echo "Raw waveform:  tia.raw"
[ -f tia_tran.txt ] && echo "Transient data: tia_tran.txt"
[ -f tia_ac.txt ]   && echo "AC data:        tia_ac.txt"

if command -v gnuplot >/dev/null 2>&1 && [ -f tia_tran.txt ]; then
  echo ""
  echo "Plotting photodiode current vs. TIA output voltage -> tia-plots.png"
  gnuplot <<'EOF'
set terminal pngcairo size 1000,700
set output "tia-plots.png"
set multiplot layout 2,1 title "TrustSense TIA -- transient response"
set xlabel "time (s)"
set ylabel "I_ph (A)"
plot "tia_tran.txt" using 1:2 with lines title "photodiode current" lc rgb "#d9822b"
set ylabel "V_{out} (V)"
plot "tia_tran.txt" using 1:4 with lines title "tia\\_out" lc rgb "#2c7be5"
unset multiplot
EOF
  echo "Wrote tia-plots.png"
else
  echo ""
  echo "(gnuplot not found or tia_tran.txt missing -- skipping plot; ascii data still in tia_tran.txt / tia_ac.txt)"
fi

echo ""
echo "Done."
