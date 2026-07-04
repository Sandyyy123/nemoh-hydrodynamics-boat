"""
NEMOH hydrodynamic-coefficients pipeline for a boat hull.

End-to-end, driven from Python:
    boat geometry  ->  panel mesh  ->  Nemoh.cal input  ->  NEMOH solve  ->  coefficients -> CSV + plots

The ENGINE is NEMOH (open-source Fortran BEM solver, LHEEA / Ecole Centrale de
Nantes, v3). Python generates the mesh and the Nemoh.cal input file, launches the
NEMOH executable, and parses/plots the results.

If the NEMOH binary is not available on this machine, the script runs in
ILLUSTRATIVE mode: it produces physically-shaped coefficient curves so you can see
the exact outputs and file formats the real solve delivers, without compiling
Fortran. Set the environment variable NEMOH_BIN (or put `nemoh` on PATH) to run the
real solve.

Usage:
    python main.py
    NEMOH_BIN=/path/to/nemoh python main.py
"""
from __future__ import annotations

import os
from pathlib import Path

from hull import make_box_hull
from nemoh_driver import solve_with_nemoh
from postprocess import export_csv, plot_coefficients

# ----------------------------------------------------------------------------
# Problem definition (edit these for the real job)
# ----------------------------------------------------------------------------
CONFIG = {
    "length": 10.0,      # hull length overall [m]
    "beam": 3.0,         # hull beam [m]
    "draft": 1.2,        # draft [m]
    "nx": 30, "ny": 10, "nz": 8,   # panel resolution
    "rho": 1025.0,       # sea water density [kg/m^3]
    "g": 9.81,           # gravity [m/s^2]
    "water_depth": 0.0,  # 0.0 => infinite depth
    "omega_min": 0.2,    # rad/s
    "omega_max": 3.0,    # rad/s
    "n_omega": 40,
    "wave_direction": 0.0,  # deg (head seas)
    "dofs": ["Surge", "Heave", "Pitch"],
}

OUT = Path("outputs")


def main() -> None:
    OUT.mkdir(exist_ok=True)

    print("[1/4] Building hull mesh ...")
    hull = make_box_hull(
        length=CONFIG["length"], beam=CONFIG["beam"], draft=CONFIG["draft"],
        nx=CONFIG["nx"], ny=CONFIG["ny"], nz=CONFIG["nz"],
    )
    print(f"      {hull['n_nodes']} nodes, {hull['n_panels']} panels, "
          f"displaced volume ~ {hull['volume']:.2f} m^3")

    print("[2/4] Solving with NEMOH ...")
    result = solve_with_nemoh(hull, CONFIG, workdir=OUT / "nemoh_run")
    mode = "REAL NEMOH solve" if result["real_solver"] else "ILLUSTRATIVE mode (NEMOH binary not found)"
    print(f"      mode: {mode}")

    print("[3/4] Exporting coefficient tables ...")
    csv_paths = export_csv(result, OUT)
    for p in csv_paths:
        print(f"      wrote {p}")

    print("[4/4] Plotting ...")
    fig_path = plot_coefficients(result, OUT / "hydrodynamic_coefficients.png")
    print(f"      wrote {fig_path}")

    print("\nDone. See the 'outputs/' folder for CSVs and the summary figure.")
    if not result["real_solver"]:
        print("NOTE: illustrative curves. Set NEMOH_BIN=/path/to/nemoh for a real solve.")


if __name__ == "__main__":
    main()
