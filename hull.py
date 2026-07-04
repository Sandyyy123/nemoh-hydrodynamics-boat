"""
Hull geometry -> panel mesh.

For the demo we generate a simple box barge (a legitimate stand-in for the client's
real boat model). For the paid job this is replaced by importing the client's file
(STL / STEP / IGES / hull offsets) via meshmagick or trimesh, clipping it at the
waterline, and checking the displaced volume against the expected displacement.

The mesh is returned in a plain dict of NumPy arrays so the NEMOH driver can write
it out in NEMOH's mesh format without depending on any particular mesh library.
"""
from __future__ import annotations

import numpy as np


def make_box_hull(length=10.0, beam=3.0, draft=1.2, nx=30, ny=10, nz=8):
    """Build the wetted (immersed) surface of a rectangular box hull.

    Only the part below the waterline (z <= 0) is panelised, which is what NEMOH
    needs. Returns nodes (Nx3) and quad panels (Mx4, 1-based node indices, the
    convention NEMOH uses).
    """
    L, B, T = length, beam, draft
    x0, x1 = -L / 2, L / 2
    y0, y1 = -B / 2, B / 2
    z0, z1 = -T, 0.0

    nodes: list[tuple[float, float, float]] = []
    index: dict[tuple[float, float, float], int] = {}

    def node(x, y, z):
        key = (round(x, 6), round(y, 6), round(z, 6))
        if key not in index:
            nodes.append(key)
            index[key] = len(nodes)  # 1-based
        return index[key]

    panels: list[tuple[int, int, int, int]] = []

    def add_face(pts):
        panels.append(tuple(node(*p) for p in pts))

    xs = np.linspace(x0, x1, nx + 1)
    ys = np.linspace(y0, y1, ny + 1)
    zs = np.linspace(z0, z1, nz + 1)

    # Bottom (z = z0)
    for i in range(nx):
        for j in range(ny):
            add_face([(xs[i], ys[j], z0), (xs[i + 1], ys[j], z0),
                      (xs[i + 1], ys[j + 1], z0), (xs[i], ys[j + 1], z0)])
    # Two sides (y = y0 and y = y1)
    for i in range(nx):
        for k in range(nz):
            add_face([(xs[i], y0, zs[k]), (xs[i + 1], y0, zs[k]),
                      (xs[i + 1], y0, zs[k + 1]), (xs[i], y0, zs[k + 1])])
            add_face([(xs[i], y1, zs[k]), (xs[i], y1, zs[k + 1]),
                      (xs[i + 1], y1, zs[k + 1]), (xs[i + 1], y1, zs[k])])
    # Two ends (x = x0 and x = x1)
    for j in range(ny):
        for k in range(nz):
            add_face([(x0, ys[j], zs[k]), (x0, ys[j], zs[k + 1]),
                      (x0, ys[j + 1], zs[k + 1]), (x0, ys[j + 1], zs[k])])
            add_face([(x1, ys[j], zs[k]), (x1, ys[j + 1], zs[k]),
                      (x1, ys[j + 1], zs[k + 1]), (x1, ys[j], zs[k + 1])])

    node_arr = np.array(nodes, dtype=float)
    panel_arr = np.array(panels, dtype=int)

    return {
        "nodes": node_arr,
        "panels": panel_arr,
        "n_nodes": len(node_arr),
        "n_panels": len(panel_arr),
        "volume": L * B * T,           # box displacement
        "length": L, "beam": B, "draft": T,
        "cog": np.array([0.0, 0.0, -T / 2]),  # centre of gravity (demo)
    }
