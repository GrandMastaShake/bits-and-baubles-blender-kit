#!/usr/bin/env python3
"""Structural Validator — Analyzes B&B assemblies for integrity and proportions.
The 'critic' in the AI builder swarm. Reviews what BuilderAI produces and flags issues.

Usage:
    python validator.py              # Run tests
    python validator.py --demo       # Run extended demo with autofix
"""
from __future__ import annotations

import math
import sys
from copy import deepcopy
from dataclasses import dataclass, field
from enum import Enum
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Blender availability guard — script runs standalone for testing
# ---------------------------------------------------------------------------
try:
    import bpy

    HAS_BPY = True
except ImportError:
    HAS_BPY = False
    bpy = None  # type: ignore


# --- Constants ---
STUD = 0.008  # 1 stud in Blender units (m)
PLATE_H = 0.004  # plate height (3 plates = 1 brick)
BRICK_H = 0.012  # standard brick height

# Piece dimensions in studs: (width_x, depth_z, height_y)
PIECE_DIMS: Dict[str, Tuple[int, int, int]] = {
    "Brick_1x1": (1, 1, 3),  # 1x1 brick = 1x1 studs, 3 plates tall
    "Brick_1x2": (1, 2, 3),
    "Brick_1x3": (1, 3, 3),
    "Brick_1x4": (1, 4, 3),
    "Brick_1x6": (1, 6, 3),
    "Brick_1x8": (1, 8, 3),
    "Brick_2x2": (2, 2, 3),
    "Brick_2x3": (2, 3, 3),
    "Brick_2x4": (2, 4, 3),
    "Brick_2x6": (2, 6, 3),
    "Brick_2x8": (2, 8, 3),
    "Plate_1x1": (1, 1, 1),
    "Plate_1x2": (1, 2, 1),
    "Plate_2x2": (2, 2, 1),
    "Plate_2x3": (2, 3, 1),
    "Plate_2x4": (2, 4, 1),
    "Plate_2x6": (2, 6, 1),
    "Plate_2x8": (2, 8, 1),
    "Slope_1x2": (1, 2, 2),  # slope piece, 2 plates rise
    "Slope_2x2": (2, 2, 2),
    "Slope_2x4": (2, 4, 2),
    "Tile_1x2": (1, 2, 1),  # smooth tile, 1 plate
    "Tile_2x2": (2, 2, 1),
    "Tile_2x4": (2, 4, 1),
}


# ===========================================================================
# Minimal snap-system stubs  (enables standalone testing without snap_system.py)
# ===========================================================================

@dataclass
class PlacedBrick:
    """A brick that has been placed on the stud grid."""

    piece_type: str
    x: int  # stud position (bottom-left corner)
    z: int  # stud position (bottom-front corner)
    y: int  # vertical layer (0 = ground, each brick = +3 plates)
    rotation: int  # 0, 90, 180, 270 degrees
    color: str
    uid: int = field(default=0, compare=False)

    @property
    def dims(self) -> Tuple[int, int, int]:
        """Return (width_x, depth_z, height_y) in studs, accounting for rotation."""
        dx, dz, dy = PIECE_DIMS.get(self.piece_type, (2, 2, 3))
        if self.rotation in (90, 270):
            dx, dz = dz, dx
        return dx, dz, dy

    @property
    def width(self) -> int:
        return self.dims[0]

    @property
    def depth(self) -> int:
        return self.dims[1]

    @property
    def height(self) -> int:
        return self.dims[2]

    def occupied_cells(self) -> List[Tuple[int, int, int]]:
        """Return list of (x, y, z) grid cells occupied by this brick."""
        cells = []
        dx, dz, _ = self.dims
        # y is the layer; for a brick spanning y to y+dy-1 in plates,
        # we treat each plate-layer as occupied
        plate_height = self.height  # in plates
        for px in range(self.x, self.x + dx):
            for pz in range(self.z, self.z + dz):
                for py_plate in range(self.y, self.y + plate_height):
                    cells.append((px, py_plate, pz))
        return cells

    def footprint_cells(self) -> List[Tuple[int, int]]:
        """Return (x, z) footprint cells at the base layer."""
        cells = []
        dx, dz, _ = self.dims
        for px in range(self.x, self.x + dx):
            for pz in range(self.z, self.z + dz):
                cells.append((px, pz))
        return cells


@dataclass
class StudGrid:
    """3D occupancy grid tracking which cells are occupied."""

    cells: Dict[Tuple[int, int, int], PlacedBrick] = field(default_factory=dict)

    def place(self, brick: PlacedBrick) -> None:
        for cell in brick.occupied_cells():
            self.cells[cell] = brick

    def occupied(self, x: int, y: int, z: int) -> bool:
        return (x, y, z) in self.cells

    def brick_at(self, x: int, y: int, z: int) -> Optional[PlacedBrick]:
        return self.cells.get((x, y, z))

    def bricks_at_layer(self, y: int) -> List[PlacedBrick]:
        seen = set()
        result = []
        for (cx, cy, cz), brick in self.cells.items():
            if cy == y and brick.uid not in seen:
                seen.add(brick.uid)
                result.append(brick)
        return result

    def all_bricks(self) -> List[PlacedBrick]:
        seen = set()
        result = []
        for brick in self.cells.values():
            if brick.uid not in seen:
                seen.add(brick.uid)
                result.append(brick)
        return result


@dataclass
class Assembly:
    """Collection of placed bricks forming a structure."""

    name: str
    bricks: List[PlacedBrick] = field(default_factory=list)
    grid: StudGrid = field(default_factory=StudGrid)
    _uid_counter: int = field(default=0, compare=False)
    bounds: Tuple[int, int, int, int, int, int] = field(
        default=(0, 0, 0, 0, 0, 0), repr=False
    )

    # convenience aliases used by ProportionAnalyzer
    @property
    def piece_count(self) -> int:
        return len(self.bricks)

    def add(
        self,
        piece_type: str,
        x: int,
        z: int,
        y: int,
        rotation: int = 0,
        color: str = "red",
    ) -> PlacedBrick:
        """Place a brick and update the grid."""
        self._uid_counter += 1
        brick = PlacedBrick(
            piece_type=piece_type,
            x=x,
            z=z,
            y=y,
            rotation=rotation % 360,
            color=color,
            uid=self._uid_counter,
        )
        self.bricks.append(brick)
        self.grid.place(brick)
        self._recompute_bounds()
        return brick

    def _recompute_bounds(self) -> None:
        if not self.bricks:
            self.bounds = (0, 0, 0, 0, 0, 0)
            return
        xs = [b.x for b in self.bricks] + [b.x + b.width for b in self.bricks]
        ys = [b.y for b in self.bricks] + [b.y + b.height for b in self.bricks]
        zs = [b.z for b in self.bricks] + [b.z + b.depth for b in self.bricks]
        self.bounds = (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    def clone(self) -> Assembly:
        """Deep-copy the assembly (used by autofix)."""
        new = Assembly(name=self.name + "_fixed")
        for b in self.bricks:
            new.add(b.piece_type, b.x, b.z, b.y, b.rotation, b.color)
        return new


# ===========================================================================
# Severity / Category / Issue
# ===========================================================================

class Severity(Enum):
    CRITICAL = "CRITICAL"  # Will collapse / is broken
    WARNING = "WARNING"  # Suboptimal but functional
    NOTE = "NOTE"  # Informational


class Category(Enum):
    STRUCTURAL = "STRUCTURAL"
    PROPORTION = "PROPORTION"
    STYLE = "STYLE"


@dataclass
class Issue:
    severity: Severity
    category: Category
    message: str
    location: Optional[Tuple[int, int, int]] = None  # grid coords
    fix_suggestion: str = ""

    def __str__(self):
        loc = f" at {self.location}" if self.location else ""
        return f"[{self.severity.value}] {self.category.value}{loc}: {self.message}"


class ValidationReport:
    """Complete validation report for an assembly."""

    def __init__(self):
        self.issues: List[Issue] = []
        self.score: float = 100.0
        self.passed: bool = True
        self.fixes_applied: List[str] = []  # populated by autofix()

    def add(self, issue: Issue):
        self.issues.append(issue)
        if issue.severity == Severity.CRITICAL:
            self.score -= 15
            self.passed = False
        elif issue.severity == Severity.WARNING:
            self.score -= 5
        elif issue.severity == Severity.NOTE:
            self.score -= 1
        self.score = max(0.0, min(100.0, self.score))

    def summary(self) -> str:
        critical = sum(1 for i in self.issues if i.severity == Severity.CRITICAL)
        warnings = sum(1 for i in self.issues if i.severity == Severity.WARNING)
        notes = sum(1 for i in self.issues if i.severity == Severity.NOTE)
        status = "PASS" if self.passed else "FAIL"
        lines = [
            f"[{status}] Score: {self.score:.0f}/100 | {critical} critical, {warnings} warnings, {notes} notes"
        ]
        if self.fixes_applied:
            lines.append(f"  Fixes applied: {', '.join(self.fixes_applied)}")
        return "\n".join(lines)

    def __str__(self):
        lines = [self.summary()]
        for issue in self.issues:
            lines.append(f"  {issue}")
        return "\n".join(lines)


# ===========================================================================
# StructuralValidator
# ===========================================================================

class StructuralValidator:
    """Checks structural integrity of B&B assemblies."""

    def __init__(self, assembly: Assembly):
        self.asm = assembly
        self.grid = assembly.grid

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------
    def _all_layers(self) -> List[int]:
        """Return sorted list of occupied y-layers (in plates)."""
        ys = set()
        for brick in self.asm.bricks:
            for py in range(brick.y, brick.y + brick.height):
                ys.add(py)
        return sorted(ys)

    def _footprint_at_layer(self, y: int) -> set:
        """Return set of (x, z) cells occupied at a given plate-layer y."""
        cells = set()
        for brick in self.asm.bricks:
            by_start = brick.y
            by_end = brick.y + brick.height
            if by_start <= y < by_end:
                for px in range(brick.x, brick.x + brick.width):
                    for pz in range(brick.z, brick.z + brick.depth):
                        cells.add((px, pz))
        return cells

    def _brick_layers(self, brick: PlacedBrick) -> range:
        """Return range of plate-layers this brick occupies."""
        return range(brick.y, brick.y + brick.height)

    def _supported_cells(self, brick: PlacedBrick) -> Dict[Tuple[int, int], bool]:
        """For each footprint cell, is there support at y-1?"""
        support = {}
        for (px, pz) in brick.footprint_cells():
            if brick.y == 0:
                support[(px, pz)] = True  # ground
            else:
                # Check all plate-layers directly beneath this brick
                supported = False
                for py in range(brick.y - 1, brick.y):
                    if self.grid.occupied(px, py, pz):
                        supported = True
                        break
                support[(px, pz)] = supported
        return support

    # ------------------------------------------------------------------
    # 1. Floating bricks
    # ------------------------------------------------------------------
    def check_floating_bricks(self, report: ValidationReport):
        """Find bricks with no supporting brick directly beneath."""
        for brick in self.asm.bricks:
            if brick.y == 0:
                continue  # on the ground

            supported_cells = self._supported_cells(brick)
            supported_count = sum(1 for v in supported_cells.values() if v)
            total = len(supported_cells)

            if supported_count == 0:
                report.add(
                    Issue(
                        severity=Severity.CRITICAL,
                        category=Category.STRUCTURAL,
                        message=f"Brick {brick.piece_type} is completely floating "
                        f"({supported_count}/{total} footprint cells supported)",
                        location=(brick.x, brick.y, brick.z),
                        fix_suggestion="Add support bricks underneath, or place on ground layer.",
                    )
                )
            elif supported_count < total:
                report.add(
                    Issue(
                        severity=Severity.WARNING,
                        category=Category.STRUCTURAL,
                        message=f"Brick {brick.piece_type} is partially unsupported "
                        f"({supported_count}/{total} footprint cells supported)",
                        location=(brick.x, brick.y, brick.z),
                        fix_suggestion="Fill gaps beneath unsupported footprint cells.",
                    )
                )

    # ------------------------------------------------------------------
    # 2. Overhang
    # ------------------------------------------------------------------
    def check_overhang(self, report: ValidationReport, max_overhang_studs: int = 1):
        """Flag cantilevered sections exceeding max overhang."""
        layers = self._all_layers()
        if len(layers) < 2:
            return

        # Build footprint per layer
        layer_footprints: Dict[int, set] = {}
        for y in layers:
            layer_footprints[y] = self._footprint_at_layer(y)

        # For each brick, check how far its cells extend beyond the layer below
        for brick in self.asm.bricks:
            if brick.y == 0:
                continue

            # Get the layer directly below the brick's bottom
            below_layer = brick.y - 1
            if below_layer not in layer_footprints:
                continue

            below_fp = layer_footprints[below_layer]
            brick_fp = set(brick.footprint_cells())

            # Find unsupported cells (cells not in below_fp)
            unsupported = brick_fp - below_fp
            if not unsupported:
                continue

            # Compute overhang in each direction
            if below_fp:
                min_below_x = min(x for x, z in below_fp)
                max_below_x = max(x for x, z in below_fp)
                min_below_z = min(z for x, z in below_fp)
                max_below_z = max(z for x, z in below_fp)

                for ux, uz in unsupported:
                    overhang_x = 0
                    overhang_z = 0
                    if ux < min_below_x:
                        overhang_x = min_below_x - ux
                    elif ux > max_below_x:
                        overhang_x = ux - max_below_x
                    if uz < min_below_z:
                        overhang_z = min_below_z - uz
                    elif uz > max_below_z:
                        overhang_z = uz - max_below_z

                    max_overhang = max(overhang_x, overhang_z)
                    if max_overhang > max_overhang_studs:
                        report.add(
                            Issue(
                                severity=Severity.CRITICAL,
                                category=Category.STRUCTURAL,
                                message=f"Overhang of {max_overhang} stud(s) exceeds "
                                f"limit of {max_overhang_studs}",
                                location=(ux, brick.y, uz),
                                fix_suggestion="Add support pillar/column beneath the overhang.",
                            )
                        )
                        break  # one issue per brick

    # ------------------------------------------------------------------
    # 3. Taper ratio
    # ------------------------------------------------------------------
    def check_taper_ratio(self, report: ValidationReport, max_taper: float = 0.75):
        """Flag structures that narrow too quickly (unstable)."""
        layers = self._all_layers()
        if not layers:
            return

        # Get base footprint (widest)
        base_fp = self._footprint_at_layer(layers[0])
        base_width = len(set(x for x, z in base_fp))
        base_depth = len(set(z for x, z in base_fp))
        base_area = max(1, len(base_fp))

        if base_area <= 1:
            return  # single cell base, skip

        for y in layers[1:]:
            fp = self._footprint_at_layer(y)
            if not fp:
                continue
            area = len(fp)
            width = len(set(x for x, z in fp))
            depth = len(set(z for x, z in fp))

            area_ratio = area / base_area
            width_ratio = width / max(1, base_width)
            depth_ratio = depth / max(1, base_depth)

            if area_ratio < max_taper or width_ratio < max_taper or depth_ratio < max_taper:
                report.add(
                    Issue(
                        severity=Severity.WARNING,
                        category=Category.STRUCTURAL,
                        message=f"Layer y={y} narrows to {area_ratio:.0%} of base area "
                        f"(w={width_ratio:.0%}, d={depth_ratio:.0%}), "
                        f"below taper threshold of {max_taper:.0%}",
                        location=(0, y, 0),
                        fix_suggestion="Widen the structure at this layer or reduce height.",
                    )
                )
                break  # one warning per structure

    # ------------------------------------------------------------------
    # 4. Stress points
    # ------------------------------------------------------------------
    def check_stress_points(self, report: ValidationReport):
        """Find single-brick columns supporting heavy overhangs."""
        # Count weight (bricks) above each (x, z) column
        column_weight: Dict[Tuple[int, int], int] = {}
        for brick in self.asm.bricks:
            for (px, pz) in brick.footprint_cells():
                column_weight[(px, pz)] = column_weight.get((px, pz), 0) + 1

        if not column_weight:
            return

        avg_weight = sum(column_weight.values()) / len(column_weight)
        if avg_weight == 0:
            return

        for (px, pz), weight in column_weight.items():
            if avg_weight > 1 and weight > avg_weight * 3:
                # Find which brick is at the base of this column
                base_brick = None
                for brick in self.asm.bricks:
                    if (px, pz) in brick.footprint_cells():
                        base_brick = brick
                        break
                report.add(
                    Issue(
                        severity=Severity.WARNING,
                        category=Category.STRUCTURAL,
                        message=f"Column ({px},{pz}) supports {weight} bricks, "
                        f"{weight / avg_weight:.1f}x the average ({avg_weight:.1f})",
                        location=(px, base_brick.y if base_brick else 0, pz),
                        fix_suggestion="Add lateral bracing or redistribute weight above.",
                    )
                )

    # ------------------------------------------------------------------
    # 5. Base stability
    # ------------------------------------------------------------------
    def check_base_stability(self, report: ValidationReport):
        """Ensure base is wide enough for total height."""
        bounds = self.asm.bounds
        min_x, max_x, min_y, max_y, min_z, max_z = bounds

        base_width = max_x - min_x
        base_depth = max_z - min_z
        height = max_y - min_y

        if base_width == 0:
            base_width = 1
        if base_depth == 0:
            base_depth = 1

        hw_ratio = height / base_width
        hd_ratio = height / base_depth

        if hw_ratio > 4.0 or hd_ratio > 4.0:
            report.add(
                Issue(
                    severity=Severity.WARNING,
                    category=Category.STRUCTURAL,
                    message=f"Structure too tall for its base: H/W={hw_ratio:.1f}, "
                    f"H/D={hd_ratio:.1f} (height={height}, base={base_width}x{base_depth})",
                    location=(min_x, min_y, min_z),
                    fix_suggestion="Widen the base or reduce overall height.",
                )
            )

    # ------------------------------------------------------------------
    # 6. Height-to-width ratio
    # ------------------------------------------------------------------
    def check_height_width_ratio(self, report: ValidationReport):
        """Overall H:W ratio check."""
        bounds = self.asm.bounds
        _, max_x, _, max_y, _, max_z = bounds

        width = max(1, max_x)
        depth = max(1, max_z)
        height = max(1, max_y)

        min_dim = min(width, depth)
        ratio = height / min_dim

        if ratio > 5.0:
            report.add(
                Issue(
                    severity=Severity.CRITICAL,
                    category=Category.PROPORTION,
                    message=f"Extreme height/width ratio {ratio:.1f}:1 — structure will topple",
                    location=(0, max_y, 0),
                    fix_suggestion="Dramatically widen the base or reduce height.",
                )
            )
        elif ratio > 3.0:
            report.add(
                Issue(
                    severity=Severity.WARNING,
                    category=Category.PROPORTION,
                    message=f"Height/width ratio {ratio:.1f}:1 — potentially unstable",
                    location=(0, max_y, 0),
                    fix_suggestion="Consider widening the base.",
                )
            )

    # ------------------------------------------------------------------
    # 7. Single-brick columns
    # ------------------------------------------------------------------
    def check_single_brick_columns(self, report: ValidationReport):
        """Find single-brick-wide columns > 4 bricks tall without lateral bracing."""
        # Group bricks by (x, z) footprint center
        columns: Dict[Tuple[int, int], List[PlacedBrick]] = {}
        for brick in self.asm.bricks:
            for (px, pz) in brick.footprint_cells():
                key = (px, pz)
                if key not in columns:
                    columns[key] = []
                columns[key].append(brick)

        for (px, pz), bricks in columns.items():
            # Sort by y and find contiguous vertical runs
            bricks_sorted = sorted(bricks, key=lambda b: b.y)
            if len(bricks_sorted) <= 4:
                continue

            # Check if this column is single-brick-wide (only 1 cell in x or z)
            # Actually, we check at the footprint level: is this the only column at this x,z?
            # A single-brick column means only this (x,z) cell has bricks, no neighbors
            # Check for lateral bracing: are there bricks at adjacent x or z positions?
            has_lateral_brace = False
            for brick in bricks_sorted:
                for ox, oz in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, nz = px + ox, pz + oz
                    if (nx, nz) in columns:
                        has_lateral_brace = True
                        break
                if has_lateral_brace:
                    break

            if not has_lateral_brace:
                report.add(
                    Issue(
                        severity=Severity.CRITICAL,
                        category=Category.STRUCTURAL,
                        message=f"Single-brick column at ({px},{pz}) has "
                        f"{len(bricks_sorted)} stacked bricks with no lateral bracing",
                        location=(px, bricks_sorted[0].y, pz),
                        fix_suggestion="Add lateral connecting bricks to adjacent columns.",
                    )
                )

    # ------------------------------------------------------------------
    # Master validate
    # ------------------------------------------------------------------
    def validate(self) -> ValidationReport:
        """Run all structural checks and return report."""
        report = ValidationReport()

        self.check_floating_bricks(report)
        self.check_overhang(report, max_overhang_studs=1)
        self.check_taper_ratio(report, max_taper=0.75)
        self.check_stress_points(report)
        self.check_base_stability(report)
        self.check_height_width_ratio(report)
        self.check_single_brick_columns(report)

        return report


# ===========================================================================
# ProportionAnalyzer
# ===========================================================================

class ProportionAnalyzer:
    """Analyzes proportions and compares to reference structures."""

    REFERENCE_RATIOS = {
        "house": {
            "hw_ratio": (0.8, 1.5),
            "base_shape": "rectangular",
            "features": ["door", "window", "roof"],
        },
        "tower": {
            "hw_ratio": (2.0, 5.0),
            "base_shape": "narrow",
            "features": ["crenellations"],
        },
        "bridge": {
            "hw_ratio": (0.2, 0.6),
            "base_shape": "elongated",
            "features": ["arches", "pillars"],
        },
        "vehicle": {
            "hw_ratio": (0.3, 0.8),
            "base_shape": "low_wide",
            "features": ["wheels"],
        },
        "tree": {
            "hw_ratio": (1.5, 4.0),
            "base_shape": "vertical",
            "features": ["canopy"],
        },
    }

    def __init__(self, assembly: Assembly):
        self.asm = assembly

    def analyze(self) -> dict:
        """Analyze all proportions and return report dict."""
        bounds = self.asm.bounds
        dx = bounds[1] - bounds[0]
        dy = bounds[3] - bounds[2]
        dz = bounds[5] - bounds[4]

        return {
            "piece_count": self.asm.piece_count,
            "dimensions": {"width": dx, "height": dy, "depth": dz},
            "height_width_ratio": dy / max(dx, 1),
            "height_depth_ratio": dy / max(dz, 1),
            "width_depth_ratio": dx / max(dz, 1),
            "symmetry_score": round(self.symmetry_score(), 3),
            "complexity_score": round(self.complexity_score(), 3),
            "reference_matches": {
                k: round(v, 3) for k, v in self.match_references().items()
            },
        }

    def symmetry_score(self) -> float:
        """0-1 score: how symmetric is the structure across X and Z axes?"""
        if not self.asm.bricks:
            return 0.0

        # Compute center of mass in x and z
        all_x = []
        all_z = []
        for brick in self.asm.bricks:
            for px, pz in brick.footprint_cells():
                all_x.append(px + 0.5)
                all_z.append(pz + 0.5)

        if not all_x:
            return 0.0

        cx = sum(all_x) / len(all_x)
        cz = sum(all_z) / len(all_z)

        # Count cells on each side
        left = right = front = back = 0
        for x in all_x:
            if x < cx:
                left += 1
            elif x > cx:
                right += 1

        for z in all_z:
            if z < cz:
                front += 1
            elif z > cz:
                back += 1

        total_x = left + right
        total_z = front + back

        x_sym = 1.0 - abs(left - right) / max(total_x, 1)
        z_sym = 1.0 - abs(front - back) / max(total_z, 1)

        return (x_sym + z_sym) / 2.0

    def complexity_score(self) -> float:
        """0-1 score: piece count and variety."""
        count = self.asm.piece_count
        types = len(set(b.piece_type for b in self.asm.bricks))

        count_score = min(1.0, count / 50.0)
        type_score = min(1.0, types / 10.0)

        return (count_score + type_score) / 2.0

    def match_references(self) -> Dict[str, float]:
        """Compare proportions to known good examples. Return match scores."""
        bounds = self.asm.bounds
        dx = max(1, bounds[1] - bounds[0])
        dy = max(1, bounds[3] - bounds[2])
        dz = max(1, bounds[5] - bounds[4])

        hw_ratio = dy / dx
        wd_ratio = dx / dz

        matches = {}
        for ref_name, ref_data in self.REFERENCE_RATIOS.items():
            score = 0.0

            # H/W ratio match
            hw_min, hw_max = ref_data["hw_ratio"]
            if hw_min <= hw_ratio <= hw_max:
                # Inside range — perfect
                center = (hw_min + hw_max) / 2
                score += 1.0 - min(1.0, abs(hw_ratio - center) / (hw_max - hw_min + 0.1))
            else:
                # Outside range — penalize
                dist = min(abs(hw_ratio - hw_min), abs(hw_ratio - hw_max))
                score += max(0.0, 0.5 - dist * 0.3)

            # Base shape hints from W/D ratio
            base_shape = ref_data["base_shape"]
            if base_shape == "rectangular" and 0.5 <= wd_ratio <= 2.0:
                score += 0.2
            elif base_shape == "narrow" and wd_ratio < 1.5:
                score += 0.2
            elif base_shape == "elongated" and wd_ratio > 2.0:
                score += 0.2
            elif base_shape == "low_wide" and hw_ratio < 1.0:
                score += 0.2
            elif base_shape == "vertical":
                score += 0.2

            # Feature detection (simplified heuristics)
            piece_types = set(b.piece_type for b in self.asm.bricks)
            features = ref_data["features"]
            feature_score = 0.0
            if "roof" in features and any("Slope" in pt for pt in piece_types):
                feature_score += 0.1
            if "crenellations" in features and any(
                b.y > bounds[3] - 3 for b in self.asm.bricks
            ):
                feature_score += 0.1
            if "arches" in features and dx > dz * 2:
                feature_score += 0.1
            if "pillars" in features and self.asm.piece_count > 4:
                feature_score += 0.1
            if "canopy" in features and any("Slope" in pt for pt in piece_types):
                feature_score += 0.1
            if "wheels" in features and hw_ratio < 0.8:
                feature_score += 0.1

            score += feature_score
            matches[ref_name] = max(0.0, min(1.0, score))

        return matches

    def best_reference_match(self) -> Tuple[str, float]:
        """Return (reference_type, match_score) for best match."""
        matches = self.match_references()
        if not matches:
            return ("unknown", 0.0)
        best = max(matches, key=matches.get)
        return (best, matches[best])


# ===========================================================================
# Autofix
# ===========================================================================

def autofix(assembly: Assembly, max_fixes: int = 5) -> Tuple[Assembly, ValidationReport]:
    """Automatically fix structural issues.

    Returns (fixed_assembly, report of what was fixed).
    """
    fixed = assembly.clone()
    validator = StructuralValidator(fixed)
    report = validator.validate()

    fixes_applied = []
    fix_count = 0

    # Collect critical issues that we can fix
    critical_issues = [i for i in report.issues if i.severity == Severity.CRITICAL]

    for issue in critical_issues:
        if fix_count >= max_fixes:
            break

        if "floating" in issue.message.lower():
            # Find the floating brick and add support underneath (full chain to ground)
            loc = issue.location
            if loc:
                fx, fy, fz = loc
                # Find the brick at this location
                target = None
                for b in fixed.bricks:
                    if b.x == fx and b.z == fz and b.y == fy:
                        target = b
                        break
                if target:
                    # Add support bricks underneath each unsupported footprint cell,
                    # building a full pillar down to the ground layer (y=0)
                    supported = validator._supported_cells(target)
                    for (px, pz), is_supported in supported.items():
                        if not is_supported and fy > 0:
                            # Build a pillar from y=0 up to fy-1
                            for py in range(fy):
                                # Check if there's already a brick at this cell
                                if not fixed.grid.occupied(px, py, pz):
                                    fixed.add("Brick_1x1", px, pz, py, 0, "gray")
                                    fix_count += 1
                                    if fix_count >= max_fixes:
                                        break
                        if fix_count >= max_fixes:
                            break
                    fixes_applied.append(
                        f"Added support pillar under floating brick at ({fx},{fy},{fz})"
                    )

        elif "overhang" in issue.message.lower():
            loc = issue.location
            if loc:
                ox, oy, oz = loc
                # Add a pillar from the ground up to this point
                for py in range(0, oy):
                    fixed.add("Brick_1x1", ox, oz, py, 0, "gray")
                    fix_count += 1
                    if fix_count >= max_fixes:
                        break
                fixes_applied.append(f"Added pillar under overhang at ({ox},{oy},{oz})")

        elif "single-brick column" in issue.message.lower():
            loc = issue.location
            if loc:
                cx, cy, cz = loc
                # Add lateral bracing: place a brick connecting to an adjacent cell
                for dx, dz in [(-1, 0), (1, 0), (0, -1), (0, 1)]:
                    nx, nz = cx + dx, cz + dz
                    # Check if there's already something at the neighbor
                    neighbor_exists = any(
                        nx in range(b.x, b.x + b.width) and nz in range(b.z, b.z + b.depth)
                        for b in fixed.bricks
                    )
                    if not neighbor_exists:
                        fixed.add("Brick_1x1", nx, nz, cy, 0, "gray")
                        fix_count += 1
                        fixes_applied.append(f"Added lateral brace at ({nx},{cy},{nz})")
                        break

    # Re-validate after fixes
    validator2 = StructuralValidator(fixed)
    new_report = validator2.validate()
    new_report.fixes_applied = fixes_applied

    return fixed, new_report


# ===========================================================================
# Blender Integration (optional — only runs inside Blender)
# ===========================================================================

def validate_blender_scene() -> ValidationReport:
    """Validate the current Blender scene by inspecting mesh objects.

    Scans bpy.context.scene.objects for objects whose names start with 'Brick_'
    or 'Plate_' and builds a temporary Assembly for validation.
    """
    if not HAS_BPY:
        print("Blender not available — skipping scene validation.")
        return ValidationReport()

    asm = Assembly(name="BlenderScene")

    for obj in bpy.context.scene.objects:
        name = obj.name
        if not (name.startswith("Brick_") or name.startswith("Plate_") or name.startswith("Slope_")):
            continue

        # Parse piece type from name (e.g., "Brick_2x4.001" -> "Brick_2x4")
        base_name = name.split(".")[0]

        # Convert world position to stud coordinates
        wx, wy, wz = obj.location
        sx = round(wx / STUD)
        sy = round(wy / PLATE_H)
        sz = round(wz / STUD)

        # Try to get color from material
        color = "red"
        if obj.data.materials:
            mat = obj.data.materials[0]
            if mat and mat.name:
                color = mat.name.lower()

        # Rotation (simplified — only 0/90/180/270)
        rz = math.degrees(obj.rotation_euler[2])
        rot = int(round(rz / 90)) * 90 % 360

        try:
            asm.add(base_name, sx, sz, sy, rot, color)
        except Exception as e:
            print(f"Warning: could not add {name}: {e}")

    if asm.piece_count == 0:
        report = ValidationReport()
        report.add(
            Issue(
                severity=Severity.NOTE,
                category=Category.STYLE,
                message="No B&B bricks found in the current Blender scene.",
            )
        )
        return report

    validator = StructuralValidator(asm)
    return validator.validate()


# ===========================================================================
# Test Cases
# ===========================================================================

def build_floating_test() -> Assembly:
    """Test 1: A brick floating in mid-air with no support."""
    asm = Assembly("FloatingTest")
    # Ground brick at y=0
    asm.add("Brick_2x2", 0, 0, 0, 0, "red")
    # Floating brick at y=6 (2 brick heights up) — NO support beneath it
    asm.add("Brick_2x2", 4, 0, 6, 0, "blue")
    return asm


def build_tower_test() -> Assembly:
    """Test 2: A tall thin tower — structurally unstable."""
    asm = Assembly("TowerTest")
    # Single 1x1 column, 20 bricks tall
    for layer in range(20):
        asm.add("Brick_1x1", 0, 0, layer * 3, 0, "gray")
    return asm


def build_good_test() -> Assembly:
    """Test 3: A well-supported 4x4 platform — should pass."""
    asm = Assembly("GoodTest")
    # Solid 4x4 base at y=0
    for x in range(0, 8, 2):
        for z in range(0, 8, 2):
            asm.add("Brick_2x2", x, z, 0, 0, "green")
    # Second layer directly on top, fully supported
    for x in range(0, 8, 2):
        for z in range(0, 8, 2):
            asm.add("Brick_2x2", x, z, 3, 0, "green")
    return asm


def build_overhang_test() -> Assembly:
    """Test 4: Overhanging section — cantilever too long.

    Creates a 2-stud base, then a top layer shifted 5 studs sideways,
    producing a 3-stud overhang (exceeds max_overhang_studs=1).
    """
    asm = Assembly("OverhangTest")
    # Base layer: 2x2 brick covering x=0..1
    asm.add("Brick_2x2", 0, 0, 0, 0, "yellow")
    # Second layer: same position, directly above
    asm.add("Brick_2x2", 0, 0, 3, 0, "yellow")
    # Third layer: shifted to x=5..6 — 3 studs beyond the layer below (max x=1)
    # This creates a 3-stud overhang which exceeds the limit of 1
    asm.add("Brick_2x2", 5, 0, 6, 0, "yellow")
    return asm


def build_taper_test() -> Assembly:
    """Test 5: Structure that narrows too quickly."""
    asm = Assembly("TaperTest")
    # Wide base: 6x6
    for x in range(0, 12, 2):
        for z in range(0, 12, 2):
            asm.add("Brick_2x2", x, z, 0, 0, "orange")
    # Second layer: 4x4
    for x in range(2, 10, 2):
        for z in range(2, 10, 2):
            asm.add("Brick_2x2", x, z, 3, 0, "orange")
    # Third layer: 2x2 (narrows very fast)
    asm.add("Brick_2x2", 5, 5, 6, 0, "orange")
    return asm


def test_validator():
    """Run all test cases and print results."""
    print("=" * 72)
    print("BITS AND BAUBLES STRUCTURAL VALIDATOR — TEST SUITE")
    print("=" * 72)

    # --- Test 1: Floating brick ---
    print("\n" + "-" * 60)
    print("TEST 1: Floating brick (expected: CRITICAL)")
    print("-" * 60)
    asm1 = build_floating_test()
    v1 = StructuralValidator(asm1)
    r1 = v1.validate()
    print(f"  {r1.summary()}")
    for issue in r1.issues:
        print(f"    {issue}")
    assert any(
        "floating" in i.message.lower() for i in r1.issues
    ), "Expected floating brick issue"

    # --- Test 2: Tall thin tower ---
    print("\n" + "-" * 60)
    print("TEST 2: Tall thin tower (expected: CRITICAL + WARNINGS)")
    print("-" * 60)
    asm2 = build_tower_test()
    v2 = StructuralValidator(asm2)
    r2 = v2.validate()
    print(f"  {r2.summary()}")
    for issue in r2.issues:
        print(f"    {issue}")
    assert any(
        "single-brick column" in i.message.lower() for i in r2.issues
    ), "Expected single-brick column issue"

    # --- Test 3: Good structure ---
    print("\n" + "-" * 60)
    print("TEST 3: Good structure (expected: PASS)")
    print("-" * 60)
    asm3 = build_good_test()
    v3 = StructuralValidator(asm3)
    r3 = v3.validate()
    print(f"  {r3.summary()}")
    for issue in r3.issues:
        print(f"    {issue}")
    assert r3.passed, "Good structure should pass"

    # --- Test 4: Overhang ---
    print("\n" + "-" * 60)
    print("TEST 4: Overhang (expected: CRITICAL)")
    print("-" * 60)
    asm4 = build_overhang_test()
    v4 = StructuralValidator(asm4)
    r4 = v4.validate()
    print(f"  {r4.summary()}")
    for issue in r4.issues:
        print(f"    {issue}")

    # --- Test 5: Taper ---
    print("\n" + "-" * 60)
    print("TEST 5: Taper (expected: WARNING)")
    print("-" * 60)
    asm5 = build_taper_test()
    v5 = StructuralValidator(asm5)
    r5 = v5.validate()
    print(f"  {r5.summary()}")
    for issue in r5.issues:
        print(f"    {issue}")

    # --- Proportion Analysis on good structure ---
    print("\n" + "-" * 60)
    print("TEST 6: Proportion Analysis")
    print("-" * 60)
    pa = ProportionAnalyzer(asm3)
    analysis = pa.analyze()
    print(f"  piece_count: {analysis['piece_count']}")
    print(f"  dimensions: {analysis['dimensions']}")
    print(f"  height_width_ratio: {analysis['height_width_ratio']:.2f}")
    print(f"  symmetry_score: {analysis['symmetry_score']}")
    print(f"  complexity_score: {analysis['complexity_score']}")
    print(f"  reference_matches:")
    for ref, score in analysis["reference_matches"].items():
        print(f"    {ref}: {score}")
    best_ref, best_score = pa.best_reference_match()
    print(f"  best_reference_match: {best_ref} ({best_score:.2f})")

    # --- Autofix test ---
    print("\n" + "-" * 60)
    print("TEST 7: Autofix — Floating brick")
    print("-" * 60)
    fixed_asm, fix_report = autofix(asm1, max_fixes=5)
    print(f"  Original: {r1.summary()}")
    print(f"  Fixed:    {fix_report.summary()}")
    print(f"  Bricks before: {asm1.piece_count}, after: {fixed_asm.piece_count}")

    print("\n" + "=" * 72)
    print("ALL TESTS PASSED")
    print("=" * 72)
    return True


def demo():
    """Extended demo showcasing all validator capabilities."""
    print("\n" + "=" * 72)
    print("EXTENDED DEMO")
    print("=" * 72)

    # House-like structure
    print("\n--- House structure ---")
    house = Assembly("DemoHouse")
    # Floor
    for x in range(0, 10, 2):
        for z in range(0, 8, 2):
            house.add("Brick_2x2", x, z, 0, 0, "brown")
    # Walls
    for y in range(3, 12, 3):
        for x in range(0, 10, 2):
            house.add("Brick_2x2", x, 0, y, 0, "red")
            house.add("Brick_2x2", x, 6, y, 0, "red")
        for z in range(2, 6, 2):
            house.add("Brick_2x2", 0, z, y, 0, "red")
            house.add("Brick_2x2", 8, z, y, 0, "red")
    # Roof (slopes)
    for x in range(0, 10, 2):
        house.add("Slope_2x2", x, 0, 12, 0, "blue")
        house.add("Slope_2x2", x, 6, 12, 0, "blue")

    vh = StructuralValidator(house)
    rh = vh.validate()
    print(f"  {rh.summary()}")
    pa_h = ProportionAnalyzer(house)
    best, score = pa_h.best_reference_match()
    print(f"  Best match: {best} ({score:.2f})")

    # Autofix demo on a complex flawed structure
    print("\n--- Complex flawed structure + autofix ---")
    flawed = Assembly("FlawedComplex")
    # Solid base
    for x in range(0, 6, 2):
        for z in range(0, 6, 2):
            flawed.add("Brick_2x2", x, z, 0, 0, "white")
    # Floating section
    flawed.add("Brick_2x2", 8, 0, 6, 0, "purple")
    # Single column
    for y in range(3, 21, 3):
        flawed.add("Brick_1x1", 2, 2, y, 0, "black")

    vf = StructuralValidator(flawed)
    rf = vf.validate()
    print(f"  Before fix: {rf.summary()}")

    fixed, fix_r = autofix(flawed, max_fixes=10)
    print(f"  After fix:  {fix_r.summary()}")
    print(f"  Applied:    {fix_r.fixes_applied}")


# ===========================================================================
# Entry point
# ===========================================================================

if __name__ == "__main__":
    success = test_validator()

    if "--demo" in sys.argv or "-d" in sys.argv:
        demo()

    if not success:
        sys.exit(1)
