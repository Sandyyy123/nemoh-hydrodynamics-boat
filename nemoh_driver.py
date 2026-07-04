"""
NEMOH driver.

Real path (when a NEMOH binary is available):
    1. write the mesh in NEMOH format
    2. write the Nemoh.cal control file (targets NEMOH v3 layout)
    3. run the NEMOH executable(s) via subprocess
    4. parse the added-mass / radiation-damping / excitation-force output

Illustrative path (no binary): produce physically-shaped coefficient curves so the
whole pipeline (CSV export, plotting) runs anywhere and the outputs can be inspected
before compiling Fortran.

The engine is NEMOH; this module is only the Python orchestration around it.
"""
from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

import numpy as np


# ---------------------------------------------------------------------------
# NEMOH input writers (used by the real path)
# ---------------------------------------------------------------------------
def write_nemoh_mesh(hull, path: Path) -> None:
    """Write nodes + quad panels in the NEMOH mesh format.

    Header: `2  <isym>` (2 = 3 coords per node; isym=0, no symmetry used here).
    Then node lines `id x y z`, a `0 0. 0. 0.` terminator, panel lines `n1 n2 n3 n4`,
    and a final `0 0 0 0` terminator.
    """
    nodes, panels = hull["nodes"], hull["panels"]
    with open(path, "w") as f:
        f.write("2 0\n")
        for i, (x, y, z) in enumerate(nodes, start=1):
            f.write(f"{i} {x:.6f} {y:.6f} {z:.6f}\n")
        f.write("0 0.000000 0.000000 0.000000\n")
        for (a, b, c, d) in panels:
            f.write(f"{a} {b} {c} {d}\n")
        f.write("0 0 0 0\n")


def write_cal_file(hull, cfg, path: Path, mesh_rel: str) -> None:
    """Write a NEMOH.cal control file for the requested DOFs and frequency sweep."""
    dof_axis = {
        "Surge": (1, 1, 0, 0), "Sway": (1, 0, 1, 0), "Heave": (1, 0, 0, 1),
        "Roll": (2, 1, 0, 0), "Pitch": (2, 0, 1, 0), "Yaw": (2, 0, 0, 1),
    }
    dofs = cfg["dofs"]
    xg, yg, zg = hull["cog"]
    depth = cfg["water_depth"]
    lines = []
    lines.append("--- Environment ---")
    lines.append(f"{cfg['rho']:.1f}\t\t! RHO\t\t! Fluid specific volume (KG/M**3)")
    lines.append(f"{cfg['g']:.2f}\t\t! G\t\t! Gravity (M/S**2)")
    lines.append(f"{depth:.1f}\t\t! DEPTH\t\t! Water depth (M), 0 = infinite")
    lines.append("0.\t0.\t\t! XEFF YEFF\t! Wave measurement point")
    lines.append("--- Description of floating bodies ---")
    lines.append("1\t\t\t! Number of bodies")
    lines.append("--- Body 1 ---")
    lines.append(f"{mesh_rel}\t\t! Name of mesh file")
    lines.append(f"{hull['n_nodes']} {hull['n_panels']}\t\t! Nodes Panels")
    lines.append(f"{len(dofs)}\t\t\t! Number of degrees of freedom")
    for d in dofs:
        t, ax, ay, az = dof_axis[d]
        lines.append(f"{t} {ax} {ay} {az} {xg:.3f} {yg:.3f} {zg:.3f}\t! {d}")
    lines.append(f"{len(dofs)}\t\t\t! Number of resulting generalised forces")
    for d in dofs:
        t, ax, ay, az = dof_axis[d]
        lines.append(f"{t} {ax} {ay} {az} {xg:.3f} {yg:.3f} {zg:.3f}\t! Force {d}")
    lines.append("0\t\t\t! Number of lines of additional information")
    lines.append("--- Load cases to be solved ---")
    lines.append(f"1 {cfg['n_omega']} {cfg['omega_min']:.3f} {cfg['omega_max']:.3f}\t! freq type, nfreq, min, max")
    lines.append(f"1 {cfg['wave_direction']:.1f} {cfg['wave_direction']:.1f}\t! nbeta, beta min, beta max")
    lines.append("--- Post processing ---")
    lines.append("1 0.1 10.\t\t! IRF calculation, time step, duration")
    lines.append("0\t\t\t! Show pressure")
    lines.append("0 0. 180.\t\t! Kochin function")
    lines.append("0 0 0. 0.\t\t! Free surface elevation grid")
    path.write_text("\n".join(lines) + "\n")


# ---------------------------------------------------------------------------
# Solve
# ---------------------------------------------------------------------------
def _find_nemoh() -> str | None:
    env = os.environ.get("NEMOH_BIN")
    if env and Path(env).exists():
        return env
    for name in ("nemoh", "Nemoh", "nemoh.exe"):
        found = shutil.which(name)
        if found:
            return found
    return None


def solve_with_nemoh(hull, cfg, workdir: Path):
    workdir.mkdir(parents=True, exist_ok=True)
    omega = np.linspace(cfg["omega_min"], cfg["omega_max"], cfg["n_omega"])
    binary = _find_nemoh()

    if binary is not None:
        return _real_solve(hull, cfg, workdir, omega, binary)
    return _illustrative_solve(hull, cfg, omega)


def _real_solve(hull, cfg, workdir: Path, omega, binary):
    mesh_dir = workdir / "mesh"
    mesh_dir.mkdir(exist_ok=True)
    mesh_path = mesh_dir / "boat.dat"
    write_nemoh_mesh(hull, mesh_path)
    write_cal_file(hull, cfg, workdir / "Nemoh.cal", mesh_rel="mesh/boat.dat")

    # NEMOH v3 runs as a single executable staged in the case directory.
    subprocess.run([binary], cwd=workdir, check=True)

    added, damping, excitation = _parse_nemoh_output(workdir, cfg["dofs"], omega)
    return {
        "real_solver": True, "omega": omega, "dofs": cfg["dofs"],
        "added_mass": added, "radiation_damping": damping,
        "excitation": excitation, "config": cfg, "hull": hull,
    }


def _parse_nemoh_output(workdir: Path, dofs, omega):
    """Parse NEMOH's Results/*.tec tables into {dof: array over omega}."""
    res = workdir / "Results"
    added = {d: np.full(len(omega), np.nan) for d in dofs}
    damping = {d: np.full(len(omega), np.nan) for d in dofs}
    excitation = {d: np.full(len(omega), np.nan) for d in dofs}
    ca = res / "CA.dat"
    cm = res / "CM.dat"     # added mass
    ef = res / "ExcitationForce.tec"
    # Layout varies slightly by NEMOH version; a tolerant column reader is used.
    try:
        if cm.exists():
            data = np.loadtxt(cm, comments=("#", "Z", "V"))
            for i, d in enumerate(dofs):
                added[d] = data[:, 1 + i]
        if ca.exists():
            data = np.loadtxt(ca, comments=("#", "Z", "V"))
            for i, d in enumerate(dofs):
                damping[d] = data[:, 1 + i]
        if ef.exists():
            data = np.loadtxt(ef, comments=("#", "Z", "V", "T"))
            for i, d in enumerate(dofs):
                excitation[d] = np.abs(data[:, 1 + 2 * i])
    except Exception as exc:  # noqa: BLE001
        print(f"      WARNING: output parse issue ({exc}); check Results/ layout.")
    return added, damping, excitation


def _illustrative_solve(hull, cfg, omega):
    """Physically-shaped coefficients for a heaving/pitching box hull.

    NOT a NEMOH solve - shaped so the CSVs and plots look and behave like the real
    output (added mass drops then asymptotes; radiation damping is a bell; wave
    excitation is largest for long waves and decays at high frequency).
    """
    rho, g = cfg["rho"], cfg["g"]
    L, B, T = hull["length"], hull["beam"], hull["draft"]
    Awp = L * B                     # waterplane area
    vol = hull["volume"]
    added, damping, excitation = {}, {}, {}

    # rough per-DOF scales so the numbers are order-of-magnitude sensible
    scale = {
        "Surge": dict(a0=0.9 * rho * vol, ainf=0.5 * rho * vol, wp=1.1, bpk=0.25 * rho * vol,
                      f0=rho * g * B * T, wc=1.6),
        "Heave": dict(a0=1.8 * rho * vol, ainf=1.1 * rho * vol, wp=1.4, bpk=0.9 * rho * vol,
                      f0=rho * g * Awp, wc=1.2),
        "Pitch": dict(a0=0.08 * rho * vol * L * L, ainf=0.05 * rho * vol * L * L, wp=1.5,
                      bpk=0.04 * rho * vol * L * L, f0=rho * g * Awp * L / 12.0, wc=1.3),
    }
    for d in cfg["dofs"]:
        s = scale.get(d, scale["Heave"])
        added[d] = s["ainf"] + (s["a0"] - s["ainf"]) / (1.0 + (omega / s["wp"]) ** 2)
        damping[d] = s["bpk"] * np.exp(-((omega - s["wp"]) / (0.55 * s["wp"])) ** 2)
        excitation[d] = s["f0"] * np.exp(-(omega / s["wc"]) ** 2)

    return {
        "real_solver": False, "omega": omega, "dofs": cfg["dofs"],
        "added_mass": added, "radiation_damping": damping,
        "excitation": excitation, "config": cfg, "hull": hull,
    }
