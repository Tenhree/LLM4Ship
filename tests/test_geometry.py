"""Analytical synthetic geometry checks; no trained model is replaced or mocked."""

from __future__ import annotations

from pathlib import Path
import struct
import sys
import tempfile
import unittest

import numpy as np


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
from hullexplore.geometry import (  # noqa: E402
    compute_volume,
    export_stl,
    points_from_grid,
    validate_half_cloud,
)


def synthetic_prism(length=3.0, beam=0.6, depth=0.4, wedge=False):
    x = np.broadcast_to(np.linspace(0, length, 50), (20, 50)).copy()
    z = np.broadcast_to(np.linspace(0, depth, 20)[:, None], (20, 50)).copy()
    y = np.full((20, 50), beam / 2)
    if wedge:
        y *= z / depth
    return np.stack((x, y, z), axis=-1).reshape(1000, 3)


def binary_stl_triangles(path):
    content = Path(path).read_bytes()
    count = struct.unpack("<I", content[80:84])[0]
    if len(content) != 84 + 50 * count:
        raise AssertionError("Invalid binary STL byte count")
    return np.asarray([
        struct.unpack("<12fH", content[84 + 50 * index:134 + 50 * index])[3:12]
        for index in range(count)
    ]).reshape(-1, 3, 3)


class GeometryTests(unittest.TestCase):
    def test_grid_scaling_keeps_every_original_sample(self):
        station = np.linspace(0.0, 1.0, 50)[None, :]
        layer = np.linspace(0.0, 1.0, 20)[:, None]
        x = 0.05 + 0.03 * layer + (0.87 + 0.02 * layer) * station
        y = (0.1 + 0.8 * layer) * (0.5 + 0.5 * np.sin(np.pi * station))
        y[:, 0] = 0.0
        y[0] = 0.0
        points = points_from_grid(x, y, 90.0, 15.6, 7.5)
        grid = points.reshape(20, 50, 3)
        np.testing.assert_allclose(grid[:, :, 0], (x - x.min()) / np.ptp(x) * 90.0)
        np.testing.assert_allclose(grid[:, :, 1], y / y.max() * 7.8)
        np.testing.assert_allclose(points.max(axis=0), [90.0, 7.8, 7.5])
        np.testing.assert_allclose(points.min(axis=0), [0.0, 0.0, 0.0])
        with tempfile.TemporaryDirectory() as folder:
            report = export_stl(points, Path(folder) / "synthetic_curved_endpoints.stl")
            self.assertTrue(report["watertight"])
            self.assertTrue(report["winding_consistent"])
            self.assertFalse(report["resampling_performed"])

    def test_analytical_box_and_wedge_immersed_volume(self):
        length, beam, depth = 3.0, 0.6, 0.4
        box = synthetic_prism(length, beam, depth)
        wedge = synthetic_prism(length, beam, depth, wedge=True)
        for draft in (0.0, 0.13, depth):
            self.assertAlmostEqual(compute_volume(box, draft), length * beam * draft, places=12)
            self.assertAlmostEqual(compute_volume(wedge, draft), length * beam * draft**2 / (2 * depth), places=12)
        with self.assertRaises(ValueError):
            compute_volume(box, depth + 0.01)

    def test_export_closed_symmetric_prisms_with_correct_volume(self):
        for wedge in (False, True):
            with self.subTest(wedge=wedge), tempfile.TemporaryDirectory() as folder:
                points = synthetic_prism(wedge=wedge)
                preserved = points.copy()
                output = Path(folder) / "synthetic_prism.stl"
                report = export_stl(points, output)
                expected_volume = 3.0 * 0.6 * 0.4 * (0.5 if wedge else 1.0)
                self.assertAlmostEqual(report["volume"], expected_volume, places=7)
                self.assertTrue(report["watertight"])
                self.assertTrue(report["winding_consistent"])
                self.assertEqual(report["boundary_edges"], 0)
                self.assertEqual(report["nonmanifold_edges"], 0)
                triangles = binary_stl_triangles(output)
                unique = np.unique(triangles.reshape(-1, 3), axis=0)
                vertex_set = {tuple(vertex) for vertex in unique}
                for x, y, z in unique:
                    self.assertIn((x, -y, z), vertex_set)
                # Independently check directed-edge cancellation in the written STL.
                edges = {}
                for triangle in triangles:
                    for a, b in zip(triangle, np.roll(triangle, -1, axis=0)):
                        a, b = tuple(a), tuple(b)
                        key = tuple(sorted((a, b)))
                        edges.setdefault(key, []).append(1 if a < b else -1)
                self.assertTrue(all(len(signs) == 2 and sum(signs) == 0 for signs in edges.values()))
                np.testing.assert_array_equal(points, preserved)

    def test_duplicate_padding_is_welded_and_reported(self):
        points = synthetic_prism().reshape(20, 50, 3)
        points[:, 1] = points[:, 0]
        with tempfile.TemporaryDirectory() as folder:
            report = export_stl(points.reshape(1000, 3), Path(folder) / "synthetic_padding.stl")
            self.assertGreater(report["duplicate_vertices_merged"], 0)
            self.assertGreater(report["zero_area_faces_removed"], 0)
            self.assertTrue(report["watertight"])

    def test_headerless_unstructured_input_is_preserved(self):
        points = synthetic_prism()
        shuffled = points[np.random.default_rng(11).permutation(len(points))]
        with tempfile.TemporaryDirectory() as folder:
            source = Path(folder) / "synthetic_unstructured.csv"
            np.savetxt(source, shuffled, delimiter=",", fmt="%.17g")
            loaded = validate_half_cloud(source)
            np.testing.assert_array_equal(loaded, shuffled)
            with self.assertRaises(ValueError):
                compute_volume(loaded, 0.2)

    def test_invalid_csv_is_rejected_without_repair(self):
        base = synthetic_prism()
        invalid = {}
        invalid["count"] = base[:-1]
        invalid["columns"] = np.column_stack((base, np.ones(1000)))
        invalid["negative_y"] = base.copy()
        invalid["negative_y"][100, 1] *= -1
        invalid["nan"] = base.copy()
        invalid["nan"][100, 0] = np.nan
        invalid["translated_x"] = base + [0.1, 0.0, 0.0]
        invalid["translated_z"] = base + [0.0, 0.0, 0.1]
        with tempfile.TemporaryDirectory() as folder:
            for name, values in invalid.items():
                with self.subTest(name=name):
                    source = Path(folder) / f"synthetic_{name}.csv"
                    np.savetxt(source, values, delimiter=",")
                    before = source.read_bytes()
                    with self.assertRaises(ValueError):
                        validate_half_cloud(source)
                    self.assertEqual(source.read_bytes(), before)
            header = Path(folder) / "synthetic_header.csv"
            np.savetxt(header, base, delimiter=",", header="x,y,z", comments="")
            with self.assertRaises(ValueError):
                validate_half_cloud(header)

    def test_bad_waterline_never_overwrites_existing_export(self):
        points = synthetic_prism().reshape(20, 50, 3)
        points[5, 10, 0] = points[5, 9, 0] - 0.1
        with tempfile.TemporaryDirectory() as folder:
            destination = Path(folder) / "keep.stl"
            destination.write_bytes(b"existing file")
            with self.assertRaises(ValueError):
                export_stl(points.reshape(1000, 3), destination)
            self.assertEqual(destination.read_bytes(), b"existing file")

    def test_multivalued_waterline_is_rejected(self):
        # A real decoder can lose a tiny X increment to float32 rounding while
        # its Y changes substantially. Such a candidate must not be repaired.
        points = synthetic_prism().reshape(20, 50, 3)
        points[12, 10, 0] = points[12, 9, 0]
        points[12, 10, 1] += 0.06
        with self.assertRaisesRegex(ValueError, "different half-breadths"):
            compute_volume(points.reshape(1000, 3), 0.2)


if __name__ == "__main__":
    unittest.main()
