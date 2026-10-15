#!/usr/bin/env bash
# TrustSense TIA simulation runner (Windows Git-Bash or Linux)
# Needs: ngspice, and a checkout of
#   https://github.com/google/skywater-pdk-libs-sky130_fd_pr
# Usage:
#   SKY130_FD_PR=/path/to/skywater-pdk-libs-sky130_fd_pr \
#   NGSPICE=/path/to/ngspice_con.exe ./run-tia-sim.sh [netlist.spice]
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NETLIST="${1:-tia.spice}"
: "${NGSPICE:=ngspice}"
: "${SKY130_FD_PR:?set SKY130_FD_PR to the skywater-pdk-libs-sky130_fd_pr checkout}"
BUILD="$SCRIPT_DIR/build"; mkdir -p "$BUILD"
P="$(cd "$SKY130_FD_PR" && pwd -W 2>/dev/null || (cd "$SKY130_FD_PR" && pwd))"
C="$P/cells"; M="$P/models"

# Minimal tt-corner library: only nfet_01v8, pfet_01v8, {n,p}fet_g5v0d10v5.
# (The full sky130.lib.spice pulls in nvt/esd models that ngspice rejects.)
cat > "$BUILD/sky130_min.lib" <<LIB
.include "$M/parameters/invariant.spice"
.include "$M/parameters/lod.spice"
.include "$C/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.corner.spice"
.include "$C/pfet_01v8/sky130_fd_pr__pfet_01v8__tt.corner.spice"
.include "$C/pfet_g5v0d10v5/sky130_fd_pr__pfet_g5v0d10v5__tt.corner.spice"
.include "$C/nfet_g5v0d10v5/sky130_fd_pr__nfet_g5v0d10v5__tt.corner.spice"
.include "$M/corners/tt/nonfet.spice"
.include "$C/nfet_01v8/sky130_fd_pr__nfet_01v8__mismatch.corner.spice"
.include "$C/pfet_01v8/sky130_fd_pr__pfet_01v8__mismatch.corner.spice"
.include "$C/nfet_g5v0d10v5/sky130_fd_pr__nfet_g5v0d10v5__mismatch.corner.spice"
.include "$C/pfet_g5v0d10v5/sky130_fd_pr__pfet_g5v0d10v5__mismatch.corner.spice"
.include "$M/r+c/res_typical__cap_typical.spice"
LIB

cd "$BUILD"
cp "$SCRIPT_DIR/$NETLIST" .
LOG="${NETLIST%.spice}.log"
"$NGSPICE" -b "$NETLIST" 2>&1 | grep -v "conductance reset" | tee "$LOG"
echo; echo "Results (from $BUILD/$LOG):"
grep -E "^(power_op|gain_dc|gain_db_dc|bw_3db|peaking_db|inoise_total|onoise_total|noise_rti|trise|power_total|vbase|vtop|peaking_db|vdb_max)[[:space:]]*=" "$LOG" || true
