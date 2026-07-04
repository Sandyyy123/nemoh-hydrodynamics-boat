"""CSV export + summary plotting for the NEMOH coefficients."""
from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402


def export_csv(result, out_dir: Path):
    out_dir.mkdir(exist_ok=True)
    omega = result["omega"]
    dofs = result["dofs"]
    paths = []

    def _frame(field):
        df = pd.DataFrame({"omega_rad_s": omega})
        for d in dofs:
            df[d] = result[field][d]
        return df

    for field, fname in [
        ("added_mass", "added_mass.csv"),
        ("radiation_damping", "radiation_damping.csv"),
        ("excitation", "excitation_force.csv"),
    ]:
        p = out_dir / fname
        _frame(field).to_csv(p, index=False)
        paths.append(p)

    # single wide table too
    wide = pd.DataFrame({"omega_rad_s": omega})
    for d in dofs:
        wide[f"A_{d}"] = result["added_mass"][d]
        wide[f"B_{d}"] = result["radiation_damping"][d]
        wide[f"Fexc_{d}"] = result["excitation"][d]
    p = out_dir / "coefficients_all.csv"
    wide.to_csv(p, index=False)
    paths.append(p)
    return paths


def plot_coefficients(result, path: Path):
    omega = result["omega"]
    dofs = result["dofs"]
    fields = [
        ("added_mass", "Added mass  A(ω)", "A [kg or kg·m²]"),
        ("radiation_damping", "Radiation damping  B(ω)", "B [kg/s or kg·m²/s]"),
        ("excitation", "Wave excitation  |F(ω)|", "|F| [N or N·m]"),
    ]
    fig, axes = plt.subplots(1, 3, figsize=(15, 4.2))
    tag = "REAL NEMOH" if result["real_solver"] else "illustrative"
    for ax, (field, title, ylab) in zip(axes, fields):
        for d in dofs:
            ax.plot(omega, result[field][d], marker="o", ms=3, label=d)
        ax.set_title(title)
        ax.set_xlabel("ω [rad/s]")
        ax.set_ylabel(ylab)
        ax.grid(True, alpha=0.3)
        ax.legend(fontsize=8)
    fig.suptitle(f"Hydrodynamic coefficients ({tag})", fontsize=13)
    fig.tight_layout(rect=(0, 0, 1, 0.95))
    fig.savefig(path, dpi=130)
    plt.close(fig)
    return path
