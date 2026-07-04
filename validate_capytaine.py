"""
OPTIONAL independent cross-check with Capytaine.

Capytaine is a separate, Python-native BEM solver in the same potential-flow family
as NEMOH. It is NOT NEMOH - it is used here only to independently reproduce the same
box-hull coefficients so the NEMOH result can be sanity-checked against a second
implementation. Run only if capytaine is installed (`pip install capytaine`).

    python validate_capytaine.py
"""
from __future__ import annotations

import numpy as np

from hull import make_box_hull


def run():
    try:
        import capytaine as cpt
        import xarray as xr
    except ImportError:
        print("capytaine not installed - skipping cross-check "
              "(`pip install capytaine` to enable).")
        return

    hull = make_box_hull()
    mesh = cpt.Mesh(vertices=hull["nodes"], faces=hull["panels"] - 1)  # 0-based
    body = cpt.FloatingBody(mesh=mesh, name="boat")
    body.add_all_rigid_body_dofs()
    body = body.immersed_part()

    solver = cpt.BEMSolver()
    test_matrix = xr.Dataset(coords={
        "omega": np.linspace(0.2, 3.0, 40),
        "wave_direction": [0.0],
        "radiating_dof": list(body.dofs),
    })
    ds = solver.fill_dataset(test_matrix, body)

    print("Capytaine cross-check complete.")
    print("Heave added mass at ω=1.0:",
          float(ds["added_mass"].sel(omega=1.0, method="nearest",
                                     radiating_dof="Heave", influenced_dof="Heave")))
    print("Compare these against the NEMOH Results/ tables from main.py.")


if __name__ == "__main__":
    run()
