"""Geometry utilities for the 20-waterline, 50-point half-hull representation.

Numerical geometry uses NumPy and the Python standard library only. Plotting
dependencies are imported only by :func:`preview`. Generated point clouds keep
the decoder's original point correspondence: no interpolation or resampling is
performed. Uploaded prediction clouds may be unstructured and are never repaired.
"""

from __future__ import annotations

import os
from pathlib import Path
import struct
import tempfile
from typing import Any

import numpy as np


NUM_WATERLINES = 20
POINTS_PER_WATERLINE = 50
NUM_POINTS = NUM_WATERLINES * POINTS_PER_WATERLINE


def _trapz(values: np.ndarray, coordinates: np.ndarray, axis: int = -1) -> np.ndarray:
    function = getattr(np, "trapezoid", None)
    if function is None:
        function = np.trapz
    return function(values, x=coordinates, axis=axis)


def _positive_scalar(value: float, name: str) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must be a positive finite number.") from exc
    if not np.isfinite(result) or result <= 0:
        raise ValueError(f"{name} must be a positive finite number.")
    return result


def _cloud_values(points: np.ndarray) -> np.ndarray:
    try:
        array = np.asarray(points, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError("Point coordinates must be numeric.") from exc
    if array.shape != (NUM_POINTS, 3):
        raise ValueError(f"Expected exactly {NUM_POINTS} XYZ points; got {array.shape}.")
    if not np.isfinite(array).all():
        raise ValueError("Point coordinates must all be finite.")
    maxima = array.max(axis=0)
    minima = array.min(axis=0)
    if np.any(maxima <= 0):
        raise ValueError("The cloud must have positive length, half-breadth, and depth.")
    negative_tolerance = max(float(maxima[0]) * 1e-7, 1e-10)
    if np.any(minima < -negative_tolerance):
        raise ValueError("Expected a nonnegative XYZ half-hull; a full or reflected hull is not accepted.")
    if abs(float(minima[0])) > max(float(maxima[0]) * 1e-3, 1e-9):
        raise ValueError("The bow reference must be near X=0; coordinates are not automatically translated.")
    if abs(float(minima[2])) > max(float(maxima[2]) * 1e-3, negative_tolerance):
        raise ValueError("The bottom reference must be near Z=0; provide the complete-depth half-hull.")
    if np.any(np.ptp(array, axis=0)[[0, 2]] <= negative_tolerance):
        raise ValueError("The point cloud has a degenerate length or depth span.")
    return array


def validate_half_cloud(path: str | Path) -> np.ndarray:
    """Read a headerless, finite, nonnegative 1000-by-3 XYZ prediction cloud.

    Row order is preserved, including for an unstructured cloud. Numerical
    checks establish the coordinate envelope, not the provenance of a complete
    hull: a deliberately cropped cloud cannot be identified from extrema alone.
    The caller must supply a complete-depth half-hull with the documented axes.
    Small signed roundoff is tolerated but is returned unchanged.
    """
    try:
        points = np.loadtxt(
            Path(path), delimiter=",", dtype=np.float64, comments=None,
            encoding="utf-8-sig", ndmin=2,
        )
    except (OSError, UnicodeError, ValueError) as exc:
        raise ValueError("Could not read the cloud: use a headerless CSV containing numeric X,Y,Z columns.") from exc
    return _cloud_values(points)


def _check_waterline_x_y(x: np.ndarray, y: np.ndarray) -> None:
    """Reject folded or multivalued waterlines; permit identical endpoint padding."""
    for row in range(NUM_WATERLINES):
        differences = np.diff(x[row])
        if np.any(differences < 0):
            raise ValueError(f"Waterline {row} is not monotone from bow to stern.")
        if x[row, -1] <= x[row, 0]:
            raise ValueError(f"Waterline {row} has no longitudinal extent.")
        duplicates = differences == 0
        if np.any(duplicates & (np.diff(y[row]) != 0)):
            raise ValueError(f"Waterline {row} has different half-breadths at the same X coordinate.")


def points_from_grid(X: np.ndarray, Y: np.ndarray, L: float, B: float, D: float) -> np.ndarray:
    """Scale a decoder grid into a physical half-hull without changing its points.

    X and Y must each have shape (20, 50). B is the FULL beam. X is shifted by
    its global minimum and divided by its global span; Y is divided by its
    global maximum. Z has 20 uniformly spaced levels from zero to D. This is
    the RL bridge's point2hull coordinate scaling, without its STL interpolator.
    """
    length = _positive_scalar(L, "L")
    beam = _positive_scalar(B, "B")
    depth = _positive_scalar(D, "D")
    x = np.asarray(X, dtype=np.float64)
    y = np.asarray(Y, dtype=np.float64)
    expected = (NUM_WATERLINES, POINTS_PER_WATERLINE)
    if x.shape != expected or y.shape != expected:
        raise ValueError(f"X and Y must both have shape {expected}.")
    if not np.isfinite(x).all() or not np.isfinite(y).all():
        raise ValueError("Decoder coordinates must all be finite.")
    if np.any(x < 0) or np.any(y < 0):
        raise ValueError("Decoder X and Y coordinates must be nonnegative.")
    _check_waterline_x_y(x, y)
    x_span = float(np.max(x) - np.min(x))
    y_max = float(np.max(y))
    if x_span <= 0 or y_max <= 0:
        raise ValueError("The decoder produced a degenerate hull.")
    physical_x = (x - np.min(x)) / x_span * length
    physical_y = y / y_max * (beam / 2.0)
    z = np.broadcast_to(np.linspace(0.0, depth, NUM_WATERLINES)[:, None], expected)
    return np.stack((physical_x, physical_y, z), axis=-1).reshape(NUM_POINTS, 3)


def _structured_rows(points: np.ndarray) -> tuple[np.ndarray, np.ndarray]:
    array = _cloud_values(points)
    rows = array.reshape(NUM_WATERLINES, POINTS_PER_WATERLINE, 3)
    tolerance = max(float(array[:, 2].max()) * 1e-7, 1e-10)
    heights = rows[:, 0, 2]
    if np.any(np.ptp(rows[:, :, 2], axis=1) > tolerance):
        raise ValueError("This operation requires 20 consecutive waterlines of 50 points each.")
    if np.any(np.diff(heights) <= 0):
        raise ValueError("Structured waterlines must run from bottom to deck with increasing Z.")
    if abs(float(heights[0])) > tolerance:
        raise ValueError("Structured hulls must start at Z=0.")
    _check_waterline_x_y(rows[:, :, 0], rows[:, :, 1])
    return rows, heights


def compute_volume(points: np.ndarray, draft: float) -> float:
    """Estimate full-hull immersed volume by physical waterline integration.

    Each half-waterline area is integrated as 2*trapezoid(Y, X). The area is
    linearly interpolated in Z at the requested draft before vertical trapezoid
    integration. Units are m3 for coordinates and draft in metres. This is a
    waterline approximation, not an exact submerged-polyhedron calculation.
    """
    rows, heights = _structured_rows(points)
    try:
        immersion = float(draft)
    except (TypeError, ValueError) as exc:
        raise ValueError("Draft must be finite and between zero and hull depth.") from exc
    if not np.isfinite(immersion) or immersion < 0 or immersion > float(heights[-1]):
        raise ValueError("Draft must be finite and between zero and hull depth.")
    if immersion == 0:
        return 0.0
    areas = 2.0 * _trapz(rows[:, :, 1], rows[:, :, 0], axis=1)
    below = heights < immersion
    integration_z = np.concatenate((heights[below], [immersion]))
    integration_area = np.concatenate((areas[below], [np.interp(immersion, heights, areas)]))
    result = float(_trapz(integration_area, integration_z))
    if not np.isfinite(result) or result <= 0:
        raise ValueError("The requested draft has no positive finite immersed volume.")
    return result


def _face_orientation(vertices: np.ndarray, faces: np.ndarray) -> tuple[np.ndarray, int]:
    """Orient a closed indexed surface consistently across every shared edge."""
    edges: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for face_index, face in enumerate(faces):
        for start, end in ((face[0], face[1]), (face[1], face[2]), (face[2], face[0])):
            start, end = int(start), int(end)
            key = (min(start, end), max(start, end))
            edges.setdefault(key, []).append((face_index, 1 if start < end else -1))
    boundary = sum(len(items) == 1 for items in edges.values())
    nonmanifold = sum(len(items) != 2 and len(items) != 1 for items in edges.values())
    if boundary or nonmanifold:
        raise ValueError(f"Hull mesh is not closed: {boundary} boundary and {nonmanifold} nonmanifold edges.")
    adjacency: list[list[tuple[int, int]]] = [[] for _ in faces]
    for incidences in edges.values():
        (left, left_sign), (right, right_sign) = incidences
        relation = -left_sign * right_sign
        adjacency[left].append((right, relation))
        adjacency[right].append((left, relation))
    signs = np.zeros(len(faces), dtype=np.int8)
    components = 0
    for seed in range(len(faces)):
        if signs[seed]:
            continue
        components += 1
        signs[seed] = 1
        pending = [seed]
        while pending:
            current = pending.pop()
            for neighbour, relation in adjacency[current]:
                expected = int(signs[current]) * relation
                if signs[neighbour] == 0:
                    signs[neighbour] = expected
                    pending.append(neighbour)
                elif signs[neighbour] != expected:
                    raise ValueError("Hull mesh has inconsistent, non-orientable connectivity.")
    if components != 1:
        raise ValueError(f"Expected one connected hull surface; found {components}.")
    oriented = faces.copy()
    oriented[signs < 0] = oriented[signs < 0][:, [0, 2, 1]]
    return oriented, len(edges)


def _mesh(points: np.ndarray) -> tuple[np.ndarray, np.ndarray, dict[str, Any]]:
    rows, heights = _structured_rows(points)
    original = rows.reshape(NUM_POINTS, 3)
    mirrored = original.copy()
    mirrored[:, 1] *= -1
    raw_vertices = np.vstack((original, mirrored))
    # Welding the actual float32 STL coordinates also catches collapse on export.
    with np.errstate(over="ignore", invalid="ignore"):
        stored_vertices = raw_vertices.astype(np.float32).astype(np.float64)
    if not np.isfinite(stored_vertices).all():
        raise ValueError("Coordinates cannot be represented by the binary STL format.")
    vertices, inverse = np.unique(stored_vertices, axis=0, return_inverse=True)
    positive = np.arange(NUM_POINTS).reshape(NUM_WATERLINES, POINTS_PER_WATERLINE)
    negative = positive + NUM_POINTS
    raw_faces: list[list[int]] = []

    def quad(a: int, b: int, c: int, d: int) -> None:
        raw_faces.extend(([int(a), int(b), int(c)], [int(a), int(c), int(d)]))

    for row in range(NUM_WATERLINES - 1):
        for column in range(POINTS_PER_WATERLINE - 1):
            quad(positive[row, column], positive[row + 1, column], positive[row + 1, column + 1], positive[row, column + 1])
            quad(negative[row, column], negative[row, column + 1], negative[row + 1, column + 1], negative[row + 1, column])
    for column in range(POINTS_PER_WATERLINE - 1):
        quad(positive[0, column], positive[0, column + 1], negative[0, column + 1], negative[0, column])
        quad(positive[-1, column], negative[-1, column], negative[-1, column + 1], positive[-1, column + 1])
    for row in range(NUM_WATERLINES - 1):
        quad(positive[row, 0], negative[row, 0], negative[row + 1, 0], positive[row + 1, 0])
        quad(positive[row, -1], positive[row + 1, -1], negative[row + 1, -1], negative[row, -1])

    faces = inverse[np.asarray(raw_faces, dtype=np.int64)]
    triangles = vertices[faces]
    doubled_areas = np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1)
    zero_area = doubled_areas == 0
    faces = faces[~zero_area]
    if not len(faces):
        raise ValueError("The hull contains no non-degenerate surface triangles.")

    # Opposite faces on the symmetry plane bound zero volume. Cancel such pairs;
    # any other coincident faces indicate overlapping or otherwise invalid input.
    groups: dict[tuple[int, int, int], list[int]] = {}
    for index, face in enumerate(faces):
        groups.setdefault(tuple(sorted(map(int, face))), []).append(index)
    cancelled: set[int] = set()
    for key, indices in groups.items():
        if len(indices) == 1:
            continue
        if len(indices) == 2 and np.all(vertices[np.asarray(key), 1] == 0):
            pair = vertices[faces[np.asarray(indices)]]
            normals = np.cross(pair[:, 1] - pair[:, 0], pair[:, 2] - pair[:, 0])
            if float(np.dot(normals[0], normals[1])) < 0:
                cancelled.update(indices)
                continue
        raise ValueError("The hull contains overlapping duplicate triangles.")
    if cancelled:
        faces = faces[np.asarray([index not in cancelled for index in range(len(faces))])]
    if not len(faces):
        raise ValueError("The hull has no positive-volume surface after symmetry-plane cleanup.")
    faces, edge_count = _face_orientation(vertices, faces)
    used, remap = np.unique(faces, return_inverse=True)
    unused_count = len(vertices) - len(used)
    unique_before_cleanup = len(vertices)
    vertices = vertices[used]
    faces = remap.reshape(-1, 3)
    reference = vertices.mean(axis=0)
    triangles = vertices[faces] - reference
    signed_volume = float(np.einsum("ij,ij->i", triangles[:, 0], np.cross(triangles[:, 1], triangles[:, 2])).sum() / 6.0)
    if not np.isfinite(signed_volume) or signed_volume == 0:
        raise ValueError("The closed mesh has zero or non-finite enclosed volume.")
    if signed_volume < 0:
        faces = faces[:, [0, 2, 1]]
    mesh_volume = abs(signed_volume)
    triangles = vertices[faces]
    surface_area = float(np.linalg.norm(np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0]), axis=1).sum() / 2.0)
    waterline_volume = compute_volume(points, float(heights[-1]))
    quality: dict[str, Any] = {
        "input_half_points": NUM_POINTS,
        "vertices": int(len(vertices)),
        "faces": int(len(faces)),
        "edges": int(edge_count),
        "watertight": True,
        "winding_consistent": True,
        "connected_components": 1,
        "boundary_edges": 0,
        "nonmanifold_edges": 0,
        "duplicate_vertices_merged": int(len(raw_vertices) - unique_before_cleanup),
        "unused_vertices_removed": int(unused_count),
        "zero_area_faces_removed": int(zero_area.sum()),
        "symmetry_plane_faces_cancelled": len(cancelled),
        "volume": mesh_volume,
        "volume_units": "m3",
        "volume_method": "signed_tetrahedra_at_full_depth",
        "waterline_volume_at_full_depth": waterline_volume,
        "mesh_vs_waterline_volume_relative_difference": abs(mesh_volume - waterline_volume) / waterline_volume,
        "surface_area": surface_area,
        "surface_area_units": "m2",
        "self_intersection_test_performed": False,
        "resampling_performed": False,
    }
    return vertices, faces, quality


def export_stl(points: np.ndarray, path: str | Path) -> dict[str, Any]:
    """Write a checked, mirrored, closed binary STL and return mesh quality.

    All original grid nodes are used apart from exact duplicate welding and
    unused degenerate nodes. Bow, stern, bottom, and deck are capped as needed.
    Validation completes before the destination file is atomically replaced.
    Edge closure and consistent winding are checked; no general-purpose
    triangle-intersection test is claimed.
    """
    vertices, faces, quality = _mesh(points)
    triangles = vertices[faces]
    normals = np.cross(triangles[:, 1] - triangles[:, 0], triangles[:, 2] - triangles[:, 0])
    normals /= np.linalg.norm(normals, axis=1, keepdims=True)
    output = Path(path)
    temporary: str | None = None
    try:
        output.parent.mkdir(parents=True, exist_ok=True)
        with tempfile.NamedTemporaryFile(mode="wb", dir=output.parent, prefix=f".{output.name}.", suffix=".tmp", delete=False) as handle:
            temporary = handle.name
            header = b"WhutOceanShip structured half-hull; metres; checked closed surface"
            handle.write(header.ljust(80, b" ")[:80])
            handle.write(struct.pack("<I", len(faces)))
            for normal, triangle in zip(normals, triangles):
                handle.write(struct.pack("<12fH", *normal, *triangle.reshape(-1), 0))
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, output)
        temporary = None
    except (OSError, OverflowError, struct.error) as exc:
        raise ValueError(f"Could not write a valid binary STL to {output}.") from exc
    finally:
        if temporary is not None:
            Path(temporary).unlink(missing_ok=True)
    return {**quality, "path": str(output.resolve())}


def preview(points: np.ndarray, output_dir: str | Path, basename: str) -> dict[str, str]:
    """Save equal-scale PNG and standalone, rotatable Plotly HTML point views.

    Both views show the supplied coordinates and their Y reflection, without
    resampling or invented geometry. Matplotlib and Plotly are required here.
    """
    array = _cloud_values(points)
    if not basename or basename in {".", ".."} or any(character in basename for character in ("/", "\\", "\x00")):
        raise ValueError("Preview basename must be a filename stem without path separators.")
    try:
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        from matplotlib.ticker import MaxNLocator
        import plotly.graph_objects as go
    except ImportError as exc:
        raise ValueError("PNG and HTML previews require both matplotlib and plotly.") from exc
    reflected = array.copy()
    reflected[:, 1] *= -1
    complete = np.unique(np.vstack((array, reflected)), axis=0)
    directory = Path(output_dir)
    png = directory / f"{basename}.png"
    html = directory / f"{basename}.html"
    temporary_paths: list[Path] = []
    figure = None
    try:
        directory.mkdir(parents=True, exist_ok=True)
        for suffix in (".png", ".html"):
            with tempfile.NamedTemporaryFile(dir=directory, prefix=f".{basename}.", suffix=suffix, delete=False) as handle:
                temporary_paths.append(Path(handle.name))
        figure = plt.figure(figsize=(12, 6.5), dpi=160)
        axis = figure.add_subplot(111, projection="3d")
        axis.scatter(complete[:, 0], complete[:, 1], complete[:, 2], c=complete[:, 2], cmap="viridis", s=5, alpha=0.85, linewidths=0)
        minima, maxima = complete.min(axis=0), complete.max(axis=0)
        spans = maxima - minima
        for index, setter in enumerate((axis.set_xlim, axis.set_ylim, axis.set_zlim)):
            pad = spans[index] * 0.04
            setter(minima[index] - pad, maxima[index] + pad)
        axis.set_box_aspect(tuple(spans))
        axis.xaxis.set_major_locator(MaxNLocator(nbins=5))
        axis.yaxis.set_major_locator(MaxNLocator(nbins=3))
        axis.zaxis.set_major_locator(MaxNLocator(nbins=3))
        axis.tick_params(labelsize=8, pad=2)
        axis.set_xlabel("X (m)", labelpad=7, fontsize=10)
        axis.set_ylabel("Y (m)", labelpad=7, fontsize=10)
        axis.set_zlabel("Z (m)", labelpad=7, fontsize=10)
        axis.view_init(elev=19, azim=-65)
        axis.set_title("Full hull point cloud | equal physical scale")
        figure.tight_layout()
        figure.savefig(temporary_paths[0], dpi=160, facecolor="white")
        interactive = go.Figure(data=[go.Scatter3d(
            x=complete[:, 0], y=complete[:, 1], z=complete[:, 2], mode="markers",
            marker={"size": 2, "color": complete[:, 2], "colorscale": "Viridis", "opacity": 0.9},
            hovertemplate="X: %{x:.6g} m<br>Y: %{y:.6g} m<br>Z: %{z:.6g} m<extra></extra>",
        )])
        interactive.update_layout(
            title="Full hull point cloud | drag to rotate", template="plotly_white",
            scene={"aspectmode": "data", "xaxis_title": "X (m)", "yaxis_title": "Y (m)", "zaxis_title": "Z (m)"},
            margin={"l": 0, "r": 0, "t": 55, "b": 0},
        )
        interactive.write_html(str(temporary_paths[1]), include_plotlyjs=True, full_html=True, auto_open=False)
        os.replace(temporary_paths[0], png)
        os.replace(temporary_paths[1], html)
    except (OSError, ValueError) as exc:
        raise ValueError(f"Could not create PNG and standalone HTML previews in {directory}.") from exc
    finally:
        if figure is not None:
            plt.close(figure)
        for temporary_path in temporary_paths:
            temporary_path.unlink(missing_ok=True)
    return {"png": str(png.resolve()), "html": str(html.resolve())}
