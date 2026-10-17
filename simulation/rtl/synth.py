"""Synthesise an Amaranth module with yosys (generic gates) and estimate sky130_fd_sc_hd area.
Cell areas [um^2] from the sky130_fd_sc_hd datasheet values: inv_1 3.75, nand2_1/nor2_1 3.75, and2_0/or2_0 6.26,
xor2_1/xnor2_1 8.76, mux2_1 11.26, a/o-b variants ~7.5, dfxtp_1 (D flip-flop) 20.02, flip-flop with enable/reset mapped to dfxtp + mux.
This is a gate-count estimate, not a place-and-route result."""
import re, sys, subprocess, pathlib
from amaranth.back import rtlil

AREA = {"$_NOT_": 3.75, "$_AND_": 6.26, "$_NAND_": 3.75, "$_OR_": 6.26, "$_NOR_": 3.75, "$_XOR_": 8.76, "$_XNOR_": 8.76,
        "$_ANDNOT_": 7.51, "$_ORNOT_": 7.51, "$_MUX_": 11.26, "$_DFF_P_": 20.02, "$_DFFE_PP_": 20.02}  # enable flops assumed clock-gated (one ICG per register group)


def run_yosys(script):
    import yowasp_yosys
    r = subprocess.run([sys.executable, "-c", "import sys, yowasp_yosys; sys.exit(yowasp_yosys.run_yosys(sys.argv[1:]))", "-p", script],
                       capture_output=True, text=True)
    return r.stdout + r.stderr


def synth(module, ports, name, outdir=pathlib.Path(__file__).resolve().parent / "build"):
    outdir.mkdir(exist_ok=True)
    il = outdir / f"{name}.il"
    il.write_bytes(rtlil.convert(module, name=name, ports=ports).encode())
    out = run_yosys(f"read_rtlil {il.as_posix()}; synth -top {name} -flatten; dfflegalize -cell $_DFF_P_ 01 -cell $_DFFE_PP_ 01; "
                    f"abc -g AND,NAND,OR,NOR,XOR,XNOR,ANDNOT,ORNOT,MUX; opt_clean -purge; tee -o {(outdir/(name+".stat")).as_posix()} stat")
    stat = (outdir / f"{name}.stat").read_text()
    cells = {m.group(1): int(m.group(2)) for m in re.finditer(r"^\s+(\$_[A-Z_0-9]+_)\s+(\d+)\s*$", stat, re.M)}
    if not cells:
        cells = {m.group(2): int(m.group(1)) for m in re.finditer(r"^\s+(\d+)\s+(\$_[A-Z_0-9]+_)\s*$", stat, re.M)}
    tot = sum(AREA.get(k, 0) * v for k, v in cells.items())
    ffs = sum(v for k, v in cells.items() if "DFF" in k)
    gates = sum(v for k, v in cells.items() if "DFF" not in k)
    return dict(name=name, flops=ffs, gates=gates, area_um2=tot, cells=cells, log=out)


if __name__ == "__main__":
    from trivium_hw import Trivium
    d = Trivium()
    r = synth(d, [d.key, d.iv, d.start, d.en, d.ready, d.chip], "trivium")
    print(f"{r['name']}: {r['flops']} flip-flops, {r['gates']} gates, ~{r['area_um2']:.0f} um^2 (before placement utilisation)")
    print(r["cells"])
