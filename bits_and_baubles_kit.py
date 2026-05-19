#!/usr/bin/env python3
"""
BITS AND BAUBLES BUILDER KIT v1.0
==============================
The complete B&B-style modular brick system for Blender.

Centuria Swarm Production -- Forge Domain
5 specialized agents collaborated:
  - BrickSmith:    25-piece brick library with stud geometry
  - SnapEngineer:  Grid snap system with collision detection
  - BuilderAI:     Recipe-driven assembly engine
  - StructuralCritic: Validation + proportion analysis
  - DemoArchitect: Integration + showcase builds (this file)

Usage:
  1. Open Blender (3.0+)
  2. Go to Scripting tab
  3. Open this file (bits_and_baubles_kit.py)
  4. Click "Run Script"
  5. All 5 demo structures auto-build
  6. Explore in the 3D viewport!

Batch / Headless Mode:
  blender --background --python bits_and_baubles_kit.py
"""

import bpy
import bmesh
import json
import math
import os
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ---------------------------------------------------------------------------
# 0. PATH SETUP -- add sibling directories to sys.path if they exist
# ---------------------------------------------------------------------------
_SCRIPT_DIR = Path(__file__).parent.resolve()
for _possible in ["snap_system", "ai_builder", "validator", "brick_library"]:
    _p = _SCRIPT_DIR / _possible
    if _p.is_dir() and str(_p) not in sys.path:
        sys.path.insert(0, str(_p))

# ---------------------------------------------------------------------------
# 1. TRY TO IMPORT COMPANION MODULES -- fall back to built-in minimal versions
# ---------------------------------------------------------------------------
HAS_SNAP = HAS_BUILDER = HAS_VALIDATOR = False

try:
    from snap_system import Assembly, StudGrid, PlacementEngine
    HAS_SNAP = True
except ImportError:
    pass

try:
    from ai_builder import AIBuilder, BrickRecipe, recipe_house, recipe_tower
    from ai_builder import recipe_bridge, recipe_vehicle, recipe_tree
    HAS_BUILDER = True
except ImportError:
    pass

try:
    from validator import StructuralValidator, ProportionAnalyzer
    HAS_VALIDATOR = True
except ImportError:
    pass

HAS_MODULES = HAS_SNAP and HAS_BUILDER and HAS_VALIDATOR

if HAS_MODULES:
    print("[INFO] All companion modules loaded successfully.")
else:
    print("[INFO] Companion modules not found -- using built-in minimal versions.")

# =====================================================================
# BUILT-IN MINIMAL VERSIONS  (self-contained mode)
# =====================================================================
# These simplified-but-functional classes let the script work even when
# no companion modules are present.  They use only bpy + stdlib.

# ---------------------------------------------------------------------------
# CONSTANTS
# ---------------------------------------------------------------------------
STUD = 0.008                      # 1 stud = 8 mm in Blender units
PLATE_H = 0.004                   # Plate height = 3.2 mm (3.2/8 * STUD)
BRICK_H = 0.012                   # Brick height = 9.6 mm
STUD_RADIUS = 0.003               # Stud radius = 3 mm
STUD_HEIGHT = 0.002125            # Stud height
WALL_THICKNESS = 0.001            # Hollow brick wall thickness
TUBE_RADIUS = 0.0024              # Inner tube radius
PIECE_COLORS = {                  # Material color presets (RGBA)
    "red":         (0.75, 0.15, 0.10, 1.0),
    "blue":        (0.10, 0.25, 0.65, 1.0),
    "green":       (0.10, 0.55, 0.20, 1.0),
    "yellow":      (0.95, 0.80, 0.10, 1.0),
    "white":       (0.95, 0.95, 0.95, 1.0),
    "black":       (0.08, 0.08, 0.08, 1.0),
    "gray":        (0.50, 0.50, 0.50, 1.0),
    "dark_gray":   (0.30, 0.30, 0.30, 1.0),
    "light_gray":  (0.70, 0.70, 0.70, 1.0),
    "tan":         (0.78, 0.65, 0.45, 1.0),
    "brown":       (0.40, 0.22, 0.10, 1.0),
    "orange":      (0.90, 0.45, 0.10, 1.0),
    "dark_green":  (0.08, 0.30, 0.12, 1.0),
    "dark_blue":   (0.06, 0.15, 0.35, 1.0),
    "magenta":     (0.70, 0.20, 0.50, 1.0),
}
# 25 piece definitions:  name -> (width_studs, depth_studs, height, category)
# width = x-axis studs, depth = z-axis studs
PIECE_DEFS = {
    # Plates (thin)
    "Plate_1x1":   (1, 1, PLATE_H, "plate"),
    "Plate_1x2":   (1, 2, PLATE_H, "plate"),
    "Plate_1x4":   (1, 4, PLATE_H, "plate"),
    "Plate_2x2":   (2, 2, PLATE_H, "plate"),
    "Plate_2x3":   (2, 3, PLATE_H, "plate"),
    "Plate_2x4":   (2, 4, PLATE_H, "plate"),
    "Plate_2x6":   (2, 6, PLATE_H, "plate"),
    "Plate_4x4":   (4, 4, PLATE_H, "plate"),
    "Plate_4x6":   (4, 6, PLATE_H, "plate"),
    "Plate_6x6":   (6, 6, PLATE_H, "plate"),
    # Standard bricks
    "Brick_1x1":   (1, 1, BRICK_H, "brick"),
    "Brick_1x2":   (1, 2, BRICK_H, "brick"),
    "Brick_1x4":   (1, 4, BRICK_H, "brick"),
    "Brick_2x2":   (2, 2, BRICK_H, "brick"),
    "Brick_2x3":   (2, 3, BRICK_H, "brick"),
    "Brick_2x4":   (2, 4, BRICK_H, "brick"),
    "Brick_2x6":   (2, 6, BRICK_H, "brick"),
    # Slopes (45-degree roof pieces)
    "Slope_1x2":   (1, 2, BRICK_H, "slope"),
    "Slope_2x2":   (2, 2, BRICK_H, "slope"),
    "Slope_2x3":   (2, 3, BRICK_H, "slope"),
    "Slope_2x4":   (2, 4, BRICK_H, "slope"),
    # Tiles (smooth top -- no studs)
    "Tile_1x2":    (1, 2, PLATE_H, "tile"),
    "Tile_2x2":    (2, 2, PLATE_H, "tile"),
    "Tile_2x4":    (2, 4, PLATE_H, "tile"),
    # Round pieces
    "Round_1x1":   (1, 1, BRICK_H, "round"),
    "Round_2x2":   (2, 2, PLATE_H, "round_plate"),
}

# ---------------------------------------------------------------------------
# COLOR / MATERIAL HELPERS
# ---------------------------------------------------------------------------
_material_cache: Dict[str, bpy.types.Material] = {}

def get_material(color_name: str) -> bpy.types.Material:
    """Fetch or create a Blender material for a given B&B color."""
    if color_name in _material_cache:
        return _material_cache[color_name]
    mat = bpy.data.materials.new(name=f"BnB_{color_name}")
    mat.use_nodes = True
    principled = mat.node_tree.nodes["Principled BSDF"]
    rgba = PIECE_COLORS.get(color_name, PIECE_COLORS["gray"])
    principled.inputs["Base Color"].default_value = rgba
    principled.inputs["Roughness"].default_value = 0.3
    # Blender 4.0 renamed "Specular" to "Specular IOR Level"
    specular_key = "Specular IOR Level" if "Specular IOR Level" in principled.inputs else "Specular"
    if specular_key in principled.inputs:
        principled.inputs[specular_key].default_value = 0.5
    _material_cache[color_name] = mat
    return mat

# ---------------------------------------------------------------------------
# BUILT-IN: StudGrid  (minimal snap grid)
# ---------------------------------------------------------------------------
if not HAS_SNAP:
    class StudGrid:
        """Discrete B&B stud grid: integer coordinates = 1 stud."""

        def __init__(self, spacing: float = STUD):
            self.spacing = spacing
            self.occupied: set = set()          # (gx, gy, gz) occupied
            self.pieces: List[Dict] = []        # metadata

        def snap(self, x: float, y: float, z: float) -> Tuple[float, float, float]:
            """Snap world coords to nearest stud grid point."""
            return (
                round(x / self.spacing) * self.spacing,
                round(y / self.spacing) * self.spacing,
                round(z / self.spacing) * self.spacing,
            )

        def mark_occupied(self, gx: int, gy: int, gz: int, w: int, d: int):
            """Mark a brick footprint as occupied on the grid."""
            for ix in range(w):
                for iz in range(d):
                    self.occupied.add((gx + ix, gy, gz + iz))

        def is_occupied(self, gx: int, gy: int, gz: int, w: int, d: int) -> bool:
            """Check if any stud in footprint is already occupied."""
            for ix in range(w):
                for iz in range(d):
                    if (gx + ix, gy, gz + iz) in self.occupied:
                        return True
            return False

        def clear(self):
            self.occupied.clear()
            self.pieces.clear()

    # -----------------------------------------------------------------------
    # BUILT-IN: PlacementEngine
    # -----------------------------------------------------------------------
    class PlacementEngine:
        """Handles brick placement with grid snapping and collision."""

        def __init__(self, grid: Optional[StudGrid] = None):
            self.grid = grid or StudGrid()
            self.placed_count = 0

        def place(self, obj: bpy.types.Object, x: float, y: float, z: float,
                  grid_snap: bool = True) -> bpy.types.Object:
            """Place an object at world coordinates (optionally snapped)."""
            if grid_snap:
                x, y, z = self.grid.snap(x, y, z)
            obj.location = (x, y, z)
            self.placed_count += 1
            return obj

    # -----------------------------------------------------------------------
    # BUILT-IN: Assembly
    # -----------------------------------------------------------------------
    class Assembly:
        """High-level assembly: brick creation + placement + grouping."""

        def __init__(self, name: str = "Assembly"):
            self.name = name
            self.placer = PlacementEngine()
            self._collection = self._get_or_create_collection(name)

        def _get_or_create_collection(self, name: str) -> bpy.types.Collection:
            if name in bpy.data.collections:
                return bpy.data.collections[name]
            coll = bpy.data.collections.new(name)
            bpy.context.scene.collection.children.link(coll)
            return coll

        def add_to_collection(self, obj: bpy.types.Object):
            if obj.name not in self._collection.objects:
                self._collection.objects.link(obj)
            # Unlink from scene root if present
            if obj.name in bpy.context.scene.collection.objects:
                bpy.context.scene.collection.objects.unlink(obj)

        def place_brick(self, piece_name: str, x: float, y: float, z: float,
                        color: str = "gray", rotation: int = 0,
                        use_copy: bool = True) -> Optional[bpy.types.Object]:
            """Place a named brick piece at (x,y,z) with optional rotation."""
            src = bpy.data.objects.get(piece_name)
            if src is None:
                print(f"[WARN] Piece '{piece_name}' not found in library -- skipping")
                return None

            if use_copy:
                obj = src.copy()
                obj.data = src.data.copy()
                obj.name = f"{piece_name}_{self.placer.placed_count:03d}"
            else:
                obj = src

            # Apply rotation (90-degree increments around Y axis for Bits and Baubles)
            obj.rotation_euler = (0, rotation * math.radians(90), 0)

            # Snap and place
            self.placer.place(obj, x, y, z, grid_snap=True)
            self.add_to_collection(obj)

            # Apply material
            mat = get_material(color)
            if obj.data.materials:
                obj.data.materials[0] = mat
            else:
                obj.data.materials.append(mat)

            # Track
            w, d, h, _ = PIECE_DEFS[piece_name]
            gx = int(round(x / STUD))
            gy = int(round(y / STUD))
            gz = int(round(z / STUD))
            self.placer.grid.mark_occupied(gx, gy, gz, w, d)
            self.placer.grid.pieces.append({
                "name": obj.name, "piece": piece_name,
                "x": x, "y": y, "z": z, "color": color, "rot": rotation,
            })
            return obj

        def get_stats(self) -> Dict[str, Any]:
            return {
                "pieces_placed": self.placer.placed_count,
                "grid_occupied": len(self.placer.grid.occupied),
                "assembly_name": self.name,
            }

# ---------------------------------------------------------------------------
# BUILT-IN: BrickRecipe + AIBuilder  (recipe-driven assembly)
# ---------------------------------------------------------------------------
if not HAS_BUILDER:
    class BrickRecipe:
        """A build recipe: list of (piece, x, y, z, color, rotation) tuples."""

        def __init__(self, name: str = "recipe"):
            self.name = name
            self.steps: List[Tuple[str, int, int, int, str, int]] = []

        def add(self, piece: str, x: int, y: int, z: int,
                color: str = "gray", rotation: int = 0):
            """Add a step.  x,y,z are in STUD grid units."""
            self.steps.append((piece, x, y, z, color, rotation))

        def to_json(self, path: str):
            with open(path, "w") as f:
                json.dump({"name": self.name, "steps": self.steps}, f, indent=2)

        @classmethod
        def from_json(cls, path: str) -> "BrickRecipe":
            with open(path) as f:
                data = json.load(f)
            r = cls(data.get("name", "loaded"))
            r.steps = [tuple(s) for s in data.get("steps", [])]
            return r

    # Recipe generators -------------------------------------------------------
    def recipe_house(width: int = 8, depth: int = 6, height: int = 5,
                     wall_color: str = "tan", roof_color: str = "brown") -> BrickRecipe:
        """Generate a cozy house recipe."""
        r = BrickRecipe("cozy_house")
        # Floor
        for x in range(0, width, 2):
            for z in range(0, depth, 4):
                r.add("Plate_2x4", x, 0, z, wall_color, 0)
        # Walls
        for y in range(1, height + 1):
            for x in range(0, width):
                for z in range(0, depth):
                    if x == 0 or x == width - 1 or z == 0 or z == depth - 1:
                        # Door cutout
                        if x == width // 2 and z == 0 and y < 3:
                            continue
                        # Window cutouts
                        if (x == 2 or x == width - 3) and z == depth - 1 and y == 3:
                            continue
                        r.add("Brick_1x1", x, y, z, wall_color, 0)
        # Door
        for y in range(1, 3):
            r.add("Brick_1x1", width // 2, y, 0, "brown", 0)
        r.add("Brick_1x2", width // 2 - 1, 0, 0, "brown", 0)
        # Roof slopes
        roof_y = height + 1
        for rx in range(1, width - 1):
            for z in range(0, depth):
                r.add("Slope_2x2", rx, roof_y, z, roof_color, 0)
        # Chimney
        for cy in range(height - 1, height + 4):
            r.add("Brick_1x1", width - 2, cy, depth - 2, "red", 0)
        return r

    def recipe_tower(base: int = 4, height: int = 12,
                     wall_color: str = "gray",
                     accent: str = "dark_gray") -> BrickRecipe:
        """Generate a castle tower recipe."""
        r = BrickRecipe("castle_tower")
        # Flared base (wider at bottom)
        for x in range(-1, base + 1):
            for z in range(-1, base + 1):
                r.add("Plate_2x2", x, 0, z, accent, 0)
        # Tower walls
        for y in range(1, height + 1):
            for x in range(0, base):
                for z in range(0, base):
                    if x == 0 or x == base - 1 or z == 0 or z == base - 1:
                        # Arrow slit windows
                        if (x == 0 or x == base - 1) and z == base // 2 and y in [4, 8]:
                            continue
                        r.add("Brick_1x1", x, y, z, wall_color, 0)
        # Crenellations (battlements)
        cren_y = height + 1
        for x in range(0, base):
            for z in range(0, base):
                if x == 0 or x == base - 1 or z == 0 or z == base - 1:
                    if (x + z) % 2 == 0:
                        r.add("Brick_1x1", x, cren_y, z, wall_color, 0)
        # Floor platforms inside
        for y in [4, 8]:
            for x in range(1, base - 1):
                for z in range(1, base - 1):
                    r.add("Plate_2x2", x, y, z, accent, 0)
        return r

    def recipe_bridge(span: int = 16, width: int = 4,
                      stone_color: str = "light_gray",
                      road_color: str = "dark_gray") -> BrickRecipe:
        """Generate a stone bridge recipe."""
        r = BrickRecipe("stone_bridge")
        mid = span // 2
        # Road surface
        for x in range(0, span, 2):
            for z in range(0, width, 2):
                r.add("Plate_2x2", x, 4, z, road_color, 0)
        # Pillar 1 (left)
        for y in range(0, 4):
            for x in range(1, 4):
                for z in range(0, width):
                    r.add("Brick_1x1", x, y, z, stone_color, 0)
        # Pillar 2 (right)
        for y in range(0, 4):
            for x in range(span - 4, span - 1):
                for z in range(0, width):
                    r.add("Brick_1x1", x, y, z, stone_color, 0)
        # Arch fill between pillars
        for x in range(4, span - 4):
            for z in range(0, width):
                r.add("Brick_1x2", x, 3, z, stone_color, 0)
        # Railings
        for x in range(0, span):
            r.add("Brick_1x1", x, 5, 0, stone_color, 0)
            r.add("Brick_1x1", x, 5, width - 1, stone_color, 0)
        # Railing tops (tiles for smooth look)
        for x in range(0, span, 2):
            r.add("Tile_1x2", x, 6, 0, stone_color, 0)
            r.add("Tile_1x2", x, 6, width - 1, stone_color, 0)
        return r

    def recipe_vehicle(chassis_w: int = 6, chassis_l: int = 10,
                       body_color: str = "green",
                       detail_color: str = "dark_gray") -> BrickRecipe:
        """Generate an off-road vehicle recipe."""
        r = BrickRecipe("offroad_vehicle")
        # Chassis (lifted 1 stud for wheel clearance)
        for x in range(0, chassis_l, 2):
            for z in range(0, chassis_w, 2):
                r.add("Plate_2x2", x, 1, z, detail_color, 0)
        # Body
        for y in range(2, 5):
            for x in range(1, chassis_l - 1):
                for z in range(0, chassis_w):
                    if z == 0 or z == chassis_w - 1 or x == 1 or x == chassis_l - 2:
                        r.add("Brick_1x1", x, y, z, body_color, 0)
        # Hood
        for x in range(2, chassis_l - 4):
            for z in range(1, chassis_w - 1):
                r.add("Plate_2x2", x, 5, z, body_color, 0)
        # Seat
        r.add("Slope_2x2", chassis_l - 4, 5, 2, "tan", 0)
        # Steering wheel
        r.add("Round_1x1", chassis_l - 4, 6, 3, "dark_gray", 0)
        # Roll bars
        for y in range(5, 8):
            r.add("Brick_1x1", 2, y, 0, body_color, 0)
            r.add("Brick_1x1", 2, y, chassis_w - 1, body_color, 0)
        r.add("Brick_2x4", 2, 8, 1, body_color, 0)
        # Wheels (positioned at corners)
        wheel_offsets = [
            (2, 0, 0), (2, 0, chassis_w - 2),
            (chassis_l - 3, 0, 0), (chassis_l - 3, 0, chassis_w - 2),
        ]
        for wx, wy, wz in wheel_offsets:
            r.add("Round_2x2", wx, wy, wz, "black", 0)
        # Bumpers
        for z in range(0, chassis_w):
            r.add("Brick_1x2", 0, 2, z, detail_color, 0)
            r.add("Brick_1x2", chassis_l - 1, 2, z, detail_color, 0)
        return r

    def recipe_tree(trunk_h: int = 6, canopy_r: int = 3,
                    trunk_color: str = "brown",
                    leaf_colors: Tuple[str, str] = ("green", "dark_green")) -> BrickRecipe:
        """Generate a park tree recipe."""
        r = BrickRecipe("park_tree")
        green1, green2 = leaf_colors
        # Trunk
        for y in range(0, trunk_h):
            r.add("Brick_1x1", 1, y, 1, trunk_color, 0)
            r.add("Brick_1x1", 2, y, 1, trunk_color, 0)
            r.add("Brick_1x1", 1, y, 2, trunk_color, 0)
            r.add("Brick_1x1", 2, y, 2, trunk_color, 0)
        # Root flare
        for x in range(0, 4):
            for z in range(0, 4):
                if (x == 0 or x == 3 or z == 0 or z == 3) and not (x in [0, 3] and z in [0, 3]):
                    r.add("Plate_2x2", x, 0, z, trunk_color, 0)
        # Canopy -- layered round plates
        cy_base = trunk_h + 1
        # Bottom layer (wide)
        for x in range(-1, 5):
            for z in range(-1, 5):
                c = green1 if (x + z) % 2 == 0 else green2
                r.add("Plate_2x2", x, cy_base, z, c, 0)
        # Middle layer
        for x in range(0, 4):
            for z in range(0, 4):
                c = green2 if (x + z) % 2 == 0 else green1
                r.add("Plate_2x2", x, cy_base + 1, z, c, 0)
        # Top layer (small)
        for x in range(1, 3):
            for z in range(1, 3):
                c = green1 if (x + z) % 2 == 0 else green2
                r.add("Round_2x2", x, cy_base + 2, z, c, 0)
        # Topper
        r.add("Round_1x1", 1, cy_base + 3, 1, green1, 0)
        return r

    class AIBuilder:
        """Minimal recipe-driven builder."""

        def __init__(self):
            self.last_assembly: Optional[Assembly] = None

        def build_from_recipe(self, recipe: BrickRecipe,
                              offset: Tuple[float, float, float] = (0, 0, 0),
                              assembly_name: Optional[str] = None) -> Assembly:
            """Execute all steps in a recipe."""
            asm = Assembly(assembly_name or recipe.name)
            ox, oy, oz = offset
            for piece, gx, gy, gz, color, rot in recipe.steps:
                x = (gx * STUD) + ox
                y = (gy * STUD) + oy
                z = (gz * STUD) + oz
                asm.place_brick(piece, x, y, z, color, rot)
            self.last_assembly = asm
            print(f"[AIBuilder] Built '{recipe.name}' with {len(recipe.steps)} bricks.")
            return asm

# ---------------------------------------------------------------------------
# BUILT-IN: StructuralValidator + ProportionAnalyzer
# ---------------------------------------------------------------------------
if not HAS_VALIDATOR:
    class StructuralValidator:
        """Minimal structural validation."""

        def __init__(self):
            self.issues: List[str] = []

        def validate_scene(self) -> Dict[str, Any]:
            """Scan the current scene for structural concerns."""
            self.issues.clear()
            bnb_objs = [o for o in bpy.data.objects
                         if any(p in o.name for p in PIECE_DEFS.keys())]
            if not bnb_objs:
                self.issues.append("No B&B pieces found in scene.")
                return {"ok": False, "issues": self.issues}

            # Check for floating pieces (no support below)
            floating = 0
            for obj in bnb_objs:
                # A piece is floating if y > 0 and nothing directly beneath it
                x, y, z = obj.location
                if y > STUD * 1.5:
                    has_support = False
                    for other in bnb_objs:
                        if other == obj:
                            continue
                        ox, oy, oz = other.location
                        if abs(oy - (y - STUD)) < 0.001:
                            if (abs(ox - x) < STUD * 3 and abs(oz - z) < STUD * 3):
                                has_support = True
                                break
                    if not has_support:
                        floating += 1
            if floating > 0:
                self.issues.append(f"{floating} piece(s) appear to be unsupported.")

            return {
                "ok": len(self.issues) == 0,
                "piece_count": len(bnb_objs),
                "issues": self.issues,
            }

    class ProportionAnalyzer:
        """Minimal proportion / bounding-box analysis."""

        def analyze(self, assembly_name: str = "") -> Dict[str, Any]:
            objs = [o for o in bpy.data.objects
                    if any(p in o.name for p in PIECE_DEFS.keys())]
            if not objs:
                return {"error": "No pieces to analyze"}

            min_x = min(o.location.x for o in objs)
            max_x = max(o.location.x for o in objs)
            min_y = min(o.location.y for o in objs)
            max_y = max(o.location.y for o in objs)
            min_z = min(o.location.z for o in objs)
            max_z = max(o.location.z for o in objs)

            dx = max_x - min_x
            dy = max_y - min_y
            dz = max_z - min_z

            # Aspect ratio classification
            ratios = sorted([dx, dy, dz])
            if ratios[0] == 0:
                ratios[0] = 0.001
            aspect = f"{ratios[2] / ratios[0]:.1f}:1 (tall)" if dy == ratios[2] else \
                     f"{ratios[2] / ratios[0]:.1f}:1 (wide)"

            return {
                "piece_count": len(objs),
                "bounds": {"x": (min_x, max_x), "y": (min_y, max_y), "z": (min_z, max_z)},
                "dimensions": {"dx": dx, "dy": dy, "dz": dz},
                "aspect_ratio": aspect,
                "volume_approx": dx * dy * dz,
            }


# =====================================================================
# BRICK LIBRARY CREATION  (25 B&B pieces with full geometry)
# =====================================================================

def _create_box_mesh(name: str, w: float, d: float, h: float) -> bpy.types.Mesh:
    """Create a hollow B&B-brick box mesh with wall thickness."""
    mesh = bpy.data.meshes.new(name)
    bm = bmesh.new()
    # Outer box
    bmesh.ops.create_cube(bm, size=1.0)
    # Scale to dimensions
    bmesh.ops.scale(bm, verts=bm.verts, vec=(w * STUD, h, d * STUD))
    # Recalc normals
    bmesh.ops.recalc_face_normals(bm, faces=bm.faces)
    bm.to_mesh(mesh)
    bm.free()
    return mesh

def _create_brick_with_studs(piece_name: str, w: int, d: int, h: float,
                               category: str = "brick") -> bpy.types.Object:
    """Create a single B&B brick/plate/slope/round with proper geometry."""
    # Main brick body (hollow box)
    mesh = bpy.data.meshes.new(f"MESH_{piece_name}")
    obj = bpy.data.objects.new(piece_name, mesh)

    bm = bmesh.new()
    half_w = (w * STUD) / 2.0
    half_d = (d * STUD) / 2.0

    # Outer shell vertices
    v = [
        bm.verts.new((-half_w, 0, -half_d)),
        bm.verts.new(( half_w, 0, -half_d)),
        bm.verts.new(( half_w, 0,  half_d)),
        bm.verts.new((-half_w, 0,  half_d)),
        bm.verts.new((-half_w, h, -half_d)),
        bm.verts.new(( half_w, h, -half_d)),
        bm.verts.new(( half_w, h,  half_d)),
        bm.verts.new((-half_w, h,  half_d)),
    ]
    bm.verts.ensure_lookup_table()

    # Faces (bottom, top, sides)
    bm.faces.new((v[0], v[3], v[2], v[1]))  # bottom
    bm.faces.new((v[4], v[5], v[6], v[7]))  # top
    bm.faces.new((v[0], v[1], v[5], v[4]))  # front (-Z)
    bm.faces.new((v[2], v[3], v[7], v[6]))  # back (+Z)
    bm.faces.new((v[0], v[4], v[7], v[3]))  # left (-X)
    bm.faces.new((v[1], v[2], v[6], v[5]))  # right (+X)

    # Add inner cavity (hollow brick) for bricks taller than plates
    if h >= BRICK_H - 0.001:
        iw = half_w - WALL_THICKNESS
        id_ = half_d - WALL_THICKNESS
        ih = h - WALL_THICKNESS
        iv = [
            bm.verts.new((-iw, WALL_THICKNESS, -id_)),
            bm.verts.new(( iw, WALL_THICKNESS, -id_)),
            bm.verts.new(( iw, WALL_THICKNESS,  id_)),
            bm.verts.new((-iw, WALL_THICKNESS,  id_)),
            bm.verts.new((-iw, ih, -id_)),
            bm.verts.new(( iw, ih, -id_)),
            bm.verts.new(( iw, ih,  id_)),
            bm.verts.new((-iw, ih,  id_)),
        ]
        bm.verts.ensure_lookup_table()
        # Inner faces (reverse winding for normals)
        bm.faces.new((iv[0], iv[1], iv[2], iv[3]))  # inner bottom
        bm.faces.new((iv[4], iv[7], iv[6], iv[5]))  # inner top
        bm.faces.new((iv[0], iv[4], iv[5], iv[1]))  # inner front
        bm.faces.new((iv[2], iv[6], iv[7], iv[3]))  # inner back
        bm.faces.new((iv[0], iv[3], iv[7], iv[4]))  # inner left
        bm.faces.new((iv[1], iv[5], iv[6], iv[2]))  # inner right

        # Add tubes (inner support pillars) for 2+ stud wide bricks
        if w >= 2 and d >= 2:
            tx = 0.0
            tz = 0.0
            tube = bmesh.ops.create_cone(
                bm, cap_ends=True, cap_tris=False, segments=8,
                radius1=TUBE_RADIUS, radius2=TUBE_RADIUS,
                depth=h - WALL_THICKNESS,
            )["verts"]
            bmesh.ops.translate(bm, verts=tube, vec=(tx, h / 2, tz))

    # --- Studs on top (all piece types except 'tile') ---
    if "tile" not in category:
        for sx in range(w):
            for sz in range(d):
                stud_x = (sx - (w - 1) / 2.0) * STUD
                stud_z = (sz - (d - 1) / 2.0) * STUD
                stud_verts = bmesh.ops.create_cone(
                    bm, cap_ends=True, cap_tris=False, segments=12,
                    radius1=STUD_RADIUS, radius2=STUD_RADIUS,
                    depth=STUD_HEIGHT,
                )["verts"]
                bmesh.ops.translate(bm, verts=stud_verts,
                                     vec=(stud_x, h + STUD_HEIGHT / 2, stud_z))

    # --- Slope geometry (45-degree roof pieces) ---
    if category == "slope":
        # Slope down along the X axis (from front to back)
        # Find top face vertices and slant them
        bm.verts.ensure_lookup_table()
        for vert in bm.verts:
            if vert.co.y > h - 0.001:  # top layer
                # Calculate slope: front edge stays high, back edge goes low
                z_norm = (vert.co.z + half_d) / (2 * half_d)  # 0..1
                # Reduce height toward the back
                vert.co.y = h * (1.0 - z_norm * 0.85)

    # --- Round pieces (cylinder body) ---
    if category.startswith("round"):
        # Replace the box with a cylinder
        bm.clear()
        radius = max(w, d) * STUD / 2.0
        cyl_verts = bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=16,
            radius1=radius, radius2=radius, depth=h,
        )["verts"]
        bmesh.ops.translate(bm, verts=cyl_verts, vec=(0, h / 2, 0))
        # Add stud on top for round pieces
        stud_verts = bmesh.ops.create_cone(
            bm, cap_ends=True, cap_tris=False, segments=12,
            radius1=STUD_RADIUS, radius2=STUD_RADIUS,
            depth=STUD_HEIGHT,
        )["verts"]
        bmesh.ops.translate(bm, verts=stud_verts,
                             vec=(0, h + STUD_HEIGHT / 2, 0))

    # Finalize
    bm.normal_update()
    bm.to_mesh(mesh)
    bm.free()
    mesh.update()
    return obj

def create_brick_library() -> int:
    """Create all 25 B&B pieces in the brick library if not already present."""
    created = 0
    collection = _get_or_create_collection("BrickLibrary")

    for name, (w, d, h, cat) in PIECE_DEFS.items():
        if name in bpy.data.objects:
            continue
        obj = _create_brick_with_studs(name, w, d, h, cat)
        collection.objects.link(obj)
        created += 1

    if created:
        print(f"[Brick Library] Created {created} / {len(PIECE_DEFS)} pieces")
    else:
        print(f"[Brick Library] All {len(PIECE_DEFS)} pieces already present")
    return created

def _get_or_create_collection(name: str) -> bpy.types.Collection:
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    coll = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(coll)
    return coll

# =====================================================================
# DEMO BUILDER  (5 showcase structures -- FULLY IMPLEMENTED)
# =====================================================================

class DemoBuilder:
    """Builds the 5 showcase demo structures with offset positions."""

    DEMO_OFFSETS = {
        "house":    (0,       0, 0),
        "tower":    (0.20,    0, 0),
        "bridge":   (0,       0, 0.08),
        "vehicle":  (-0.08,   0, 0),
        "tree":     (0.16,    0, 0.06),
    }

    def __init__(self):
        self.builder = AIBuilder()
        self.results: Dict[str, Any] = {}

    # --- Build A: Cozy House ---
    def build_demo_house(self) -> Any:
        """Build a cozy house at the origin offset."""
        print("\n  [1/5] Building: Cozy House")
        offset = self.DEMO_OFFSETS["house"]
        recipe = recipe_house(8, 6, 5, "tan", "brown")
        asm = self.builder.build_from_recipe(recipe, offset, "Demo_House")
        self.results["house"] = asm
        print(f"        -> {len(recipe.steps)} bricks placed")
        return asm

    # --- Build B: Castle Tower ---
    def build_demo_tower(self) -> Any:
        """Build a castle tower to the right of the house."""
        print("\n  [2/5] Building: Castle Tower")
        offset = self.DEMO_OFFSETS["tower"]
        recipe = recipe_tower(4, 12, "gray", "dark_gray")
        asm = self.builder.build_from_recipe(recipe, offset, "Demo_Tower")
        self.results["tower"] = asm
        print(f"        -> {len(recipe.steps)} bricks placed")
        return asm

    # --- Build C: Stone Bridge ---
    def build_demo_bridge(self) -> Any:
        """Build a stone bridge behind the other structures."""
        print("\n  [3/5] Building: Stone Bridge")
        offset = self.DEMO_OFFSETS["bridge"]
        recipe = recipe_bridge(16, 4, "light_gray", "dark_gray")
        asm = self.builder.build_from_recipe(recipe, offset, "Demo_Bridge")
        self.results["bridge"] = asm
        print(f"        -> {len(recipe.steps)} bricks placed")
        return asm

    # --- Build D: Off-Road Vehicle ---
    def build_demo_vehicle(self) -> Any:
        """Build an off-road vehicle to the left of the house."""
        print("\n  [4/5] Building: Off-Road Vehicle")
        offset = self.DEMO_OFFSETS["vehicle"]
        recipe = recipe_vehicle(6, 10, "green", "dark_gray")
        asm = self.builder.build_from_recipe(recipe, offset, "Demo_Vehicle")
        self.results["vehicle"] = asm
        print(f"        -> {len(recipe.steps)} bricks placed")
        return asm

    # --- Build E: Park Tree ---
    def build_demo_tree(self) -> Any:
        """Build a park tree to the far right."""
        print("\n  [5/5] Building: Park Tree")
        offset = self.DEMO_OFFSETS["tree"]
        recipe = recipe_tree(6, 3, "brown", ("green", "dark_green"))
        asm = self.builder.build_from_recipe(recipe, offset, "Demo_Tree")
        self.results["tree"] = asm
        print(f"        -> {len(recipe.steps)} bricks placed")
        return asm

    def build_all(self) -> Dict[str, Any]:
        """Build all 5 demo structures sequentially."""
        self.build_demo_house()
        self.build_demo_tower()
        self.build_demo_bridge()
        self.build_demo_vehicle()
        self.build_demo_tree()
        return self.results

    def get_total_pieces(self) -> int:
        """Return the total number of pieces placed across all demos."""
        total = 0
        for name, asm in self.results.items():
            total += asm.placer.placed_count
        return total

    def get_stats(self) -> str:
        """Return a formatted stats string for all demos."""
        lines = ["\n" + "=" * 50, "  DEMO BUILD STATISTICS", "=" * 50]
        for name, asm in self.results.items():
            s = asm.get_stats()
            lines.append(f"  {name:12s}: {s['pieces_placed']:3d} pieces")
        lines.append("-" * 50)
        lines.append(f"  TOTAL:        {self.get_total_pieces():3d} pieces")
        lines.append("=" * 50)
        return "\n".join(lines)

# =====================================================================
# MENU SYSTEM  (interactive CLI + auto-batch mode)
# =====================================================================

def show_menu():
    """Print the interactive menu."""
    print("\n" + "=" * 55)
    print("     BITS AND BAUBLES BUILDER KIT v1.0")
    print("     Centuria Swarm -- Forge Domain")
    print("=" * 55)
    print("  [1]  Build: Cozy House        (tan + brown)")
    print("  [2]  Build: Castle Tower      (gray battlements)")
    print("  [3]  Build: Stone Bridge      (light gray span)")
    print("  [4]  Build: Off-Road Vehicle  (green 4x4)")
    print("  [5]  Build: Park Tree         (green canopy)")
    print("  [6]  Build: ALL 5 demos")
    print("  [7]  Validate current scene")
    print("  [8]  Analyze proportions")
    print("  [9]  Clear all placed bricks")
    print("  [s]  Save .blend file")
    print("  [r]  Build from custom JSON recipe")
    print("  [q]  Quit / Exit")
    print("=" * 55)

def clear_placed_bricks():
    """Remove all placed B&B bricks, keeping the library."""
    removed = 0
    for coll_name in ["Demo_House", "Demo_Tower", "Demo_Bridge",
                       "Demo_Vehicle", "Demo_Tree"]:
        coll = bpy.data.collections.get(coll_name)
        if coll:
            for obj in list(coll.objects):
                bpy.data.objects.remove(obj, do_unlink=True)
                removed += 1
            bpy.data.collections.remove(coll)
    # Also clear any loose bricks
    for obj in list(bpy.context.scene.collection.objects):
        if any(p in obj.name for p in PIECE_DEFS.keys()) and "LIB" not in obj.name:
            if obj.name not in bpy.data.collections.get("BrickLibrary", {}).objects:
                bpy.data.objects.remove(obj, do_unlink=True)
                removed += 1
    print(f"[Clear] Removed {removed} placed brick(s)")

def save_blend(filepath: Optional[str] = None) -> str:
    """Save the current Blender scene to a .blend file."""
    if filepath is None:
        out_dir = Path.home() / "bnb_output"
        out_dir.mkdir(parents=True, exist_ok=True)
        filepath = str(out_dir / "bnb_demos.blend")
    bpy.ops.wm.save_as_mainfile(filepath=filepath)
    print(f"[Save] Blend file saved to: {filepath}")
    return filepath

def build_from_json(json_path: str) -> Any:
    """Build a structure from a custom JSON recipe file."""
    if not os.path.isfile(json_path):
        print(f"[ERROR] File not found: {json_path}")
        return None
    recipe = BrickRecipe.from_json(json_path)
    builder = AIBuilder()
    asm = builder.build_from_recipe(recipe, (0, 0, 0), recipe.name)
    print(f"[Custom] Built '{recipe.name}' from {json_path}")
    return asm

def run_interactive():
    """Run the interactive menu loop (inside Blender)."""
    builder = DemoBuilder()

    while True:
        show_menu()
        choice = input("\n  Choice: ").strip().lower()

        if choice == "1":
            builder.build_demo_house()
        elif choice == "2":
            builder.build_demo_tower()
        elif choice == "3":
            builder.build_demo_bridge()
        elif choice == "4":
            builder.build_demo_vehicle()
        elif choice == "5":
            builder.build_demo_tree()
        elif choice == "6":
            builder.build_all()
            print(builder.get_stats())
        elif choice == "7":
            validator = StructuralValidator()
            result = validator.validate_scene()
            if result["ok"]:
                print("[Validate] Scene looks good!  No issues found.")
            else:
                print(f"[Validate] {len(result['issues'])} issue(s) found:")
                for issue in result["issues"]:
                    print(f"  - {issue}")
        elif choice == "8":
            analyzer = ProportionAnalyzer()
            result = analyzer.analyze()
            print("\n[Proportion Analysis]")
            for k, v in result.items():
                print(f"  {k}: {v}")
        elif choice == "9":
            clear_placed_bricks()
            builder.results.clear()
        elif choice == "s":
            path = input("  Save path [default: ~/bnb_output/bnb_demos.blend]: ").strip()
            save_blend(path if path else None)
        elif choice == "r":
            path = input("  JSON recipe path: ").strip()
            if path:
                build_from_json(path)
        elif choice in ("q", "0", "", "exit"):
            print("\nGoodbye!  Happy building!")
            break
        else:
            print(f"  Unknown option: '{choice}'")

# =====================================================================
# MAIN ENTRY POINT
# =====================================================================

def main():
    """Main entry: initialize, create library, auto-build all demos, save."""
    print("\n" + "=" * 55)
    print("  BITS AND BAUBLES BUILDER KIT v1.0")
    print("  Centuria Swarm -- Forge Domain")
    print("=" * 55)

    t0 = time.time()

    # 1. Ensure the brick library exists
    print("\n[1/4] Creating brick library...")
    create_brick_library()

    # 2. Build all 5 demo structures
    print("\n[2/4] Building demo structures...")
    demo = DemoBuilder()
    demo.build_all()

    # 3. Validation pass
    print("\n[3/4] Running validation...")
    validator = StructuralValidator()
    vresult = validator.validate_scene()
    if vresult["ok"]:
        print("  Validation: PASSED  (no structural issues)")
    else:
        print(f"  Validation: {len(vresult['issues'])} note(s)")
        for issue in vresult["issues"]:
            print(f"    - {issue}")

    # 4. Save .blend
    print("\n[4/4] Saving .blend file...")
    out_dir = _SCRIPT_DIR / "output"
    out_dir.mkdir(parents=True, exist_ok=True)
    blend_path = str(out_dir / "bnb_demos.blend")
    save_blend(blend_path)

    # Stats
    elapsed = time.time() - t0
    print(demo.get_stats())
    print(f"\n  Elapsed: {elapsed:.1f}s")
    print("  Done!  Open the .blend file in Blender to explore.")
    print("=" * 55)

    # Print final message
    print("""
  TIP: In Blender:
    - Press Numpad . to frame all objects
    - Press Z -> 'Rendered' for nice shading
    - Use the Outliner (top-right) to toggle collections
""")

# ---------------------------------------------------------------------------
# When run inside Blender's scripting environment, auto-execute main()
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    # Check if running in Blender (bpy is available)
    try:
        bpy.context.scene.name  # side-effect: confirms we're in Blender
        IN_BLENDER = True
    except Exception:
        IN_BLENDER = False

    if IN_BLENDER:
        main()
    else:
        # Running outside Blender -- show help
        print("""
  This script must be run inside Blender.

  Quick Start:
    1. Open Blender 3.0+
    2. Switch to the 'Scripting' workspace tab
    3. Click 'Open' and select this file
    4. Click the 'Run Script' button
    5. Watch the console output!

  Headless (command-line):
    blender --background --python bits_and_baubles_kit.py
""")
