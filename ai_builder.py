#!/usr/bin/env python3
"""
AI Builder — Recipe-driven Bits and Baubles assembly in Blender.

Reads JSON recipes and builds complete B&B structures by placing
mesh objects on a stud grid.  Can be used either:
  - As a standalone script (creates its own brick geometry), or
  - Alongside snap_system.py / brick_library.py (those modules
    provide the underlying placement engine and piece catalogue).

Run from within Blender:
    blender --python ai_builder.py
Or import and call individual builders:
    from ai_builder import AIBuilder, recipe_house
    builder = AIBuilder()
    assembly = builder.build_from_recipe(recipe_house(8, 6, 5))
"""
from __future__ import annotations

import bpy
import bmesh
import json
import math
import os
import sys
from typing import Dict, List, Optional, Tuple

# ---------------------------------------------------------------------------
# Attempt to import the external snap-system.  If it isn't present we fall
# back to an internal lightweight implementation so the script is always
# runnable.
# ---------------------------------------------------------------------------
try:
    from snap_system import Assembly, StudGrid, PlacementEngine  # type: ignore
    _HAS_SNAP_SYSTEM = True
except Exception:
    _HAS_SNAP_SYSTEM = False


# =====================================================================
# 1. CONSTANTS
# =====================================================================

# B&B-style unit dimensions (Blender units = mm at 1/10 scale for comfort)
STUD_SPACING = 0.8       # 8mm  -> 0.8 BU
PLATE_HEIGHT = 0.32      # 3.2mm plate
BRICK_HEIGHT = 0.96      # 9.6mm standard brick
STUD_RADIUS = 0.25       # 5mm diameter stud
STUD_HEIGHT = 0.18       # 1.8mm stud height
WALL_THICKNESS = 0.16    # 1.6mm wall thickness
TUBE_RADIUS = 0.18       # underside tube

# Piece-type catalogue --------------------------------------------------
# Each entry: ( studs_x , studs_z , height_type )
# height_type: "plate" | "brick" | "slope" | "tile" | "door"
PIECE_CATALOG: Dict[str, Tuple[int, int, str]] = {
    # Standard bricks
    "Brick_1x1":        (1, 1, "brick"),
    "Brick_1x2":        (1, 2, "brick"),
    "Brick_1x3":        (1, 3, "brick"),
    "Brick_1x4":        (1, 4, "brick"),
    "Brick_2x2":        (2, 2, "brick"),
    "Brick_2x3":        (2, 3, "brick"),
    "Brick_2x4":        (2, 4, "brick"),
    "Brick_2x6":        (2, 6, "brick"),
    "Brick_2x8":        (2, 8, "brick"),
    # Plates
    "Plate_1x1":        (1, 1, "plate"),
    "Plate_1x2":        (1, 2, "plate"),
    "Plate_1x3":        (1, 3, "plate"),
    "Plate_1x4":        (1, 4, "plate"),
    "Plate_2x2":        (2, 2, "plate"),
    "Plate_2x3":        (2, 3, "plate"),
    "Plate_2x4":        (2, 4, "plate"),
    "Plate_2x6":        (2, 6, "plate"),
    "Plate_2x8":        (2, 8, "plate"),
    "Plate_4x4":        (4, 4, "plate"),
    "Plate_4x6":        (4, 6, "plate"),
    "Plate_4x8":        (4, 8, "plate"),
    "Plate_6x6":        (6, 6, "plate"),
    "Plate_6x8":        (6, 8, "plate"),
    "Plate_8x8":        (8, 8, "plate"),
    "Plate_8x16":       (8, 16, "plate"),
    # Tiles
    "Tile_1x2":         (1, 2, "tile"),
    "Tile_2x2":         (2, 2, "tile"),
    "Tile_2x4":         (2, 4, "tile"),
    # Slopes
    "Slope_1x2":        (1, 2, "slope"),
    "Slope_1x3":        (1, 3, "slope"),
    "Slope_2x2_33":     (2, 2, "slope"),
    "Slope_2x2_45":     (2, 2, "slope"),
    "Slope_2x3":        (2, 3, "slope"),
    "Slope_2x4":        (2, 4, "slope"),
    # Special
    "Door_1x3x4":       (1, 3, "door"),
    "Wheel_2x2":        (2, 2, "wheel"),
}

# Named colour palette --------------------------------------------------
COLOR_PALETTE: Dict[str, str] = {
    "red":        "#CC3333",
    "blue":       "#3366CC",
    "green":      "#33AA33",
    "yellow":     "#FFCC00",
    "white":      "#EEEEEE",
    "black":      "#222222",
    "gray":       "#888888",
    "dark_gray":  "#555555",
    "light_gray": "#AAAAAA",
    "orange":     "#FF8800",
    "purple":     "#8833AA",
    "brown":      "#8B4513",
    "tan":        "#D2B48C",
    "pink":       "#FF88AA",
    "cyan":       "#33CCAA",
    "dark_green": "#226622",
    "olive":      "#6B8E23",
    "dark_red":   "#8B0000",
    "navy":       "#000080",
    "gold":       "#FFD700",
}


# =====================================================================
# 2. UTILITY FUNCTIONS
# =====================================================================

def hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    """Convert '#RRGGBB' to (r, g, b) floats in [0, 1]."""
    h = hex_str.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {hex_str}")
    return (
        int(h[0:2], 16) / 255.0,
        int(h[2:4], 16) / 255.0,
        int(h[4:6], 16) / 255.0,
    )


def resolve_color(value: str) -> str:
    """Turn a palette name or hex string into a guaranteed '#RRGGBB' value."""
    if not value:
        return "#CC3333"
    if value.startswith("#"):
        return value
    return COLOR_PALETTE.get(value.lower(), "#CC3333")


def get_piece_dims(brick_type: str) -> Tuple[int, int, float]:
    """Return (studs_x, studs_z, height) for a known piece type.

    Falls back to 2x2 brick dimensions for unknown types.
    """
    if brick_type in PIECE_CATALOG:
        sx, sz, ht = PIECE_CATALOG[brick_type]
    else:
        # Try to parse "Prefix_NxM" pattern
        sx, sz, ht = 2, 2, "brick"
        parts = brick_type.split("_")
        for part in parts:
            if "x" in part:
                try:
                    a, b = part.split("x")
                    sx, sz = int(a), int(b)
                except Exception:
                    pass
            if part in ("plate", "tile", "slope", "door", "wheel", "brick"):
                ht = part
    height = {"plate": PLATE_HEIGHT, "tile": PLATE_HEIGHT,
              "brick": BRICK_HEIGHT, "slope": BRICK_HEIGHT,
              "door": BRICK_HEIGHT * 4, "wheel": BRICK_HEIGHT}.get(ht, BRICK_HEIGHT)
    return sx, sz, height


# =====================================================================
# 3. FALLBACK SNAP SYSTEM (self-contained)
# =====================================================================

class _StudGrid:
    """Lightweight stud grid used when snap_system.py is unavailable."""

    def __init__(self, spacing: float = STUD_SPACING):
        self.spacing = spacing

    def snap(self, x: float, z: float) -> Tuple[float, float]:
        return (round(x / self.spacing) * self.spacing,
                round(z / self.spacing) * self.spacing)


class _PlacementEngine:
    """Lightweight placement engine (no collision checking)."""

    def __init__(self, grid: _StudGrid):
        self.grid = grid

    def place(self, brick_type: str, gx: float, gz: float, y: float,
              rot: int = 0) -> Optional[Dict]:
        return {
            "type": brick_type,
            "x": gx,
            "z": gz,
            "y": y,
            "rot": rot,
        }


class _Assembly:
    """Fallback Assembly that actually creates Blender mesh objects."""

    _mesh_cache: Dict[str, bpy.types.Mesh] = {}

    def __init__(self, name: str = "Assembly"):
        self.name = name
        self.pieces: List[Dict] = []
        self.collection = bpy.data.collections.new(name)
        bpy.context.scene.collection.children.link(self.collection)

    # ------------------------------------------------------------------
    @property
    def piece_count(self) -> int:
        return len(self.pieces)

    # ------------------------------------------------------------------
    def add(self, brick_type: str, gx: float, gz: float, y: float,
            rot: int = 0, color: str = "#CC3333") -> bool:
        """Create a brick mesh, place it, and assign a material."""
        sx, sz, height = get_piece_dims(brick_type)
        mesh_name = f"{brick_type}_{sx}x{sz}_h{height:.3f}"

        # Re-use or create mesh
        mesh = _Assembly._mesh_cache.get(mesh_name)
        if mesh is None:
            mesh = self._build_brick_mesh(brick_type, sx, sz, height, mesh_name)
            _Assembly._mesh_cache[mesh_name] = mesh

        obj = bpy.data.objects.new(f"{brick_type}_{len(self.pieces)}", mesh)
        self.collection.objects.link(obj)

        # Position: centre of the brick footprint
        cx = gx * STUD_SPACING + (sx - 1) * STUD_SPACING * 0.5
        cz = gz * STUD_SPACING + (sz - 1) * STUD_SPACING * 0.5
        obj.location = (cx, cz, y * PLATE_HEIGHT + height * 0.5)

        # Rotation
        if rot:
            obj.rotation_euler = (0, 0, math.radians(rot))

        # Material
        mat = _material_for_hex(color)
        if mat:
            obj.data.materials.append(mat)

        self.pieces.append({
            "type": brick_type, "x": gx, "z": gz,
            "y": y, "rot": rot, "color": color,
        })
        return True

    # ------------------------------------------------------------------
    @staticmethod
    def _build_brick_mesh(brick_type: str, sx: int, sz: int,
                          height: float, name: str) -> bpy.types.Mesh:
        """Procedurally generate a B&B-style brick mesh."""
        mesh = bpy.data.meshes.new(name)

        # Dimensions
        bw = sx * STUD_SPACING           # total width  (X)
        bd = sz * STUD_SPACING           # total depth  (Y)
        bh = height                       # total height (Z)
        wt = WALL_THICKNESS               # wall thickness
        half_w = bw * 0.5
        half_d = bd * 0.5

        verts = []
        faces = []

        def add_face(vi: List[int]) -> None:
            faces.append(vi)

        # ---- Hollow box (outer shell) ----
        # Bottom ring (z = -bh/2)
        b0 = len(verts); verts += [
            (-half_w, -half_d, -bh * 0.5), (half_w, -half_d, -bh * 0.5),
            (half_w, half_d, -bh * 0.5),   (-half_w, half_d, -bh * 0.5),
        ]
        # Inner bottom ring
        iw = half_w - wt
        id_ = half_d - wt
        b1 = len(verts); verts += [
            (-iw, -id_, -bh * 0.5), (iw, -id_, -bh * 0.5),
            (iw, id_, -bh * 0.5),   (-iw, id_, -bh * 0.5),
        ]
        # Top ring (z = +bh/2)
        t0 = len(verts); verts += [
            (-half_w, -half_d, bh * 0.5), (half_w, -half_d, bh * 0.5),
            (half_w, half_d, bh * 0.5),   (-half_w, half_d, bh * 0.5),
        ]
        # Inner top ring
        t1 = len(verts); verts += [
            (-iw, -id_, bh * 0.5), (iw, -id_, bh * 0.5),
            (iw, id_, bh * 0.5),   (-iw, id_, bh * 0.5),
        ]

        # Bottom face
        add_face([b0 + 0, b0 + 1, b1 + 1, b1 + 0])
        add_face([b0 + 1, b0 + 2, b1 + 2, b1 + 1])
        add_face([b0 + 2, b0 + 3, b1 + 3, b1 + 2])
        add_face([b0 + 3, b0 + 0, b1 + 0, b1 + 3])
        # Top face
        add_face([t0 + 0, t1 + 0, t1 + 1, t0 + 1])
        add_face([t0 + 1, t1 + 1, t1 + 2, t0 + 2])
        add_face([t0 + 2, t1 + 2, t1 + 3, t0 + 3])
        add_face([t0 + 3, t1 + 3, t1 + 0, t0 + 0])
        # Side walls
        add_face([b0 + 0, t0 + 0, t0 + 1, b0 + 1])  # front
        add_face([b0 + 1, t0 + 1, t0 + 2, b0 + 2])  # right
        add_face([b0 + 2, t0 + 2, t0 + 3, b0 + 3])  # back
        add_face([b0 + 3, t0 + 3, t0 + 0, b0 + 0])  # left
        # Inner walls
        add_face([b1 + 0, b1 + 1, t1 + 1, t1 + 0])
        add_face([b1 + 1, b1 + 2, t1 + 2, t1 + 1])
        add_face([b1 + 2, b1 + 3, t1 + 3, t1 + 2])
        add_face([b1 + 3, b1 + 0, t1 + 0, t1 + 3])

        # ---- Studs on top ----
        for ix in range(sx):
            for iz in range(sz):
                cx_s = -half_w + STUD_SPACING * 0.5 + ix * STUD_SPACING
                cy_s = -half_d + STUD_SPACING * 0.5 + iz * STUD_SPACING
                base = len(verts)
                # 8-vertex stud cylinder (approximation)
                for a in range(8):
                    ang = a * math.pi / 4.0
                    verts.append((cx_s + STUD_RADIUS * math.cos(ang),
                                  cy_s + STUD_RADIUS * math.sin(ang),
                                  bh * 0.5 + STUD_HEIGHT))
                # Top centre vertex
                top_v = len(verts)
                verts.append((cx_s, cy_s, bh * 0.5 + STUD_HEIGHT))
                # Side faces
                for a in range(8):
                    a2 = (a + 1) % 8
                    add_face([base + a, base + a2, top_v])
                # Stud bottom face (connects to brick top)
                add_face(list(range(base, base + 8)))

        # ---- Tubes on bottom (for bricks taller than plates) ----
        if height >= BRICK_HEIGHT and "plate" not in brick_type.lower() and "tile" not in brick_type.lower():
            for ix in range(sx - 1):
                for iz in range(sz - 1):
                    cx_t = -half_w + STUD_SPACING + ix * STUD_SPACING
                    cy_t = -half_d + STUD_SPACING + iz * STUD_SPACING
                    base = len(verts)
                    for a in range(8):
                        ang = a * math.pi / 4.0
                        verts.append((cx_t + TUBE_RADIUS * math.cos(ang),
                                      cy_t + TUBE_RADIUS * math.sin(ang),
                                      -bh * 0.5 + 0.05))
                    top_v = len(verts)
                    verts.append((cx_t, cy_t, -bh * 0.5))
                    for a in range(8):
                        a2 = (a + 1) % 8
                        add_face([base + a, top_v, base + a2])
                    add_face(list(range(base, base + 8)))

        # ---- Slope geometry ----
        if "slope" in brick_type.lower():
            # Shift top vertices to create angled face
            # Simple approach: shear the top ring in Z
            slope_angle = math.radians(33 if "33" in brick_type else 45)
            dz = math.tan(slope_angle) * bw
            for vi in [t0 + 0, t0 + 1, t1 + 0, t1 + 1]:
                if vi < len(verts):
                    v = verts[vi]
                    verts[vi] = (v[0], v[1], v[2] - dz * 0.5)
            for vi in [t0 + 2, t0 + 3, t1 + 2, t1 + 3]:
                if vi < len(verts):
                    v = verts[vi]
                    verts[vi] = (v[0], v[1], v[2] + dz * 0.5)

        # ---- Door geometry (taller, thin piece) ----
        if "door" in brick_type.lower():
            # Add a cutout by removing front face and adding door panel
            pass  # simplified — box shape already works

        # ---- Build mesh ----
        mesh.from_pydata(verts, [], faces)
        mesh.update(calc_edges=True)
        return mesh


# Material cache (shared across assemblies)
_MATERIAL_CACHE: Dict[str, bpy.types.Material] = {}


def _material_for_hex(color_hex: str) -> Optional[bpy.types.Material]:
    """Get or create a Blender material for a hex colour."""
    if color_hex in _MATERIAL_CACHE:
        return _MATERIAL_CACHE[color_hex]
    mat = bpy.data.materials.new(name=f"Brick_{color_hex.lstrip('#')}")
    mat.use_nodes = True
    tree = mat.node_tree
    principled = tree.nodes["Principled BSDF"]
    r, g, b = hex_to_rgb(color_hex)
    principled.inputs["Base Color"].default_value = (r, g, b, 1.0)
    principled.inputs["Roughness"].default_value = 0.35
    principled.inputs["Specular"].default_value = 0.2
    _MATERIAL_CACHE[color_hex] = mat
    return mat


# Expose the right classes
if _HAS_SNAP_SYSTEM:
    _Grid = StudGrid
    _Engine = PlacementEngine
    _AssemblyClass = Assembly
else:
    _Grid = _StudGrid
    _Engine = _PlacementEngine
    _AssemblyClass = _Assembly


# =====================================================================
# 4. BRICK RECIPE
# =====================================================================

class BrickRecipe:
    """Parsed recipe object — thin wrapper around the JSON dict."""

    def __init__(self, recipe_dict: dict):
        self.raw = recipe_dict
        self.name: str = recipe_dict.get("name", "Untitled")
        self.description: str = recipe_dict.get("description", "")
        self.dimensions: dict = recipe_dict.get("dimensions", {})
        self.layers: List[dict] = recipe_dict.get("layers", [])
        self.colors: dict = recipe_dict.get("colors", {})

    @classmethod
    def from_json(cls, json_str: str) -> "BrickRecipe":
        return cls(json.loads(json_str))

    @classmethod
    def from_file(cls, filepath: str) -> "BrickRecipe":
        with open(filepath, "r", encoding="utf-8") as f:
            return cls(json.load(f))

    def to_json(self) -> str:
        return json.dumps(self.raw, indent=2)


# =====================================================================
# 5. COLOR MANAGER
# =====================================================================

class ColorManager:
    """Manages Blender materials and colour application."""

    def __init__(self):
        self._materials: Dict[str, bpy.types.Material] = {}

    def get_material(self, color_hex: str) -> bpy.types.Material:
        """Get or create a material for a hex colour."""
        color_hex = resolve_color(color_hex)
        if color_hex in self._materials:
            return self._materials[color_hex]
        mat = bpy.data.materials.new(name=f"Brick_{color_hex.lstrip('#')}")
        mat.use_nodes = True
        tree = mat.node_tree
        principled = tree.nodes["Principled BSDF"]
        r, g, b = hex_to_rgb(color_hex)
        principled.inputs["Base Color"].default_value = (r, g, b, 1.0)
        principled.inputs["Roughness"].default_value = 0.35
        principled.inputs["Specular"].default_value = 0.2
        self._materials[color_hex] = mat
        return mat

    def resolve(self, name_or_hex: str) -> str:
        """Turn palette name or raw hex into a guaranteed '#RRGGBB' string."""
        return resolve_color(name_or_hex)


# =====================================================================
# 6. AI BUILDER
# =====================================================================

class AIBuilder:
    """Main builder — reads recipes and constructs Blender assemblies."""

    def __init__(self):
        self.assembly: Optional[_AssemblyClass] = None
        self.colors = ColorManager()
        self.grid = _Grid()
        self.engine = _Engine(self.grid)

    # ------------------------------------------------------------------
    # Core recipe interpreter
    # ------------------------------------------------------------------
    def build_from_recipe(self, recipe: BrickRecipe) -> _AssemblyClass:
        """Build a complete structure from a recipe."""
        self.assembly = _AssemblyClass(name=recipe.name)

        # Resolve colour palette
        palette: Dict[str, str] = {}
        for key, val in recipe.colors.items():
            palette[key] = resolve_color(val)

        # Build layer by layer
        for layer in recipe.layers:
            y_level = layer.get("y", 0)
            for piece_spec in layer.get("pieces", []):
                brick_type = piece_spec["type"]
                gx = piece_spec["x"]
                gz = piece_spec["z"]
                rot = piece_spec.get("rot", 0)

                # Resolve colour
                color = piece_spec.get("color")
                if not color:
                    color = palette.get("primary", "#CC3333")
                color = resolve_color(color)

                self.assembly.add(brick_type, gx, gz, y_level, rot, color)

        print(f"[AIBuilder] Built '{recipe.name}': {self.assembly.piece_count} pieces")
        return self.assembly

    # ------------------------------------------------------------------
    # Helpers: running-bond wall placement
    # ------------------------------------------------------------------
    def _wall_row(self, x: int, z: int, width: int, y: int,
                  brick_type: str, color: str, rot: int = 0,
                  skip_fn=None) -> List[bool]:
        """Place one row of a wall."""
        results: List[bool] = []
        sx, sz, _ = get_piece_dims(brick_type)
        effective_len = sz if rot in (0, 180) else sx
        step = effective_len
        pos = z
        end = z + width
        # Stagger offset for running bond
        stagger = (y // 3) % 2  # every brick-height layer
        if stagger:
            pos -= step // 2

        while pos < end:
            if skip_fn and skip_fn(pos, y):
                pos += 1
                continue
            actual_z = max(pos, z)
            if actual_z >= end:
                break
            ok = self.assembly.add(brick_type, x, actual_z, y, rot, color)
            results.append(ok)
            pos += step
        return results

    # ------------------------------------------------------------------
    # build_wall
    # ------------------------------------------------------------------
    def build_wall(self, x: int, z: int, width: int, height: int,
                   brick_type: str = "Brick_2x4", color: str = "#CC3333",
                   rot: int = 0) -> List[bool]:
        """Build a wall segment from (x, z) going +width in +z direction.

        Uses a running-bond (staggered) pattern.  *height* is given in
        plate layers (i.e. 1 brick = 3 plates).
        """
        results: List[bool] = []
        color = resolve_color(color)
        y = 0
        plate_layers = 0
        _, _, bh = get_piece_dims(brick_type)
        # bh is in BU; convert to plate layers (1 plate = PLATE_HEIGHT)
        brick_plates = max(1, round(bh / PLATE_HEIGHT))

        while y < height:
            layer_results = self._wall_row(
                x, z, width, y, brick_type, color, rot,
            )
            results.extend(layer_results)
            y += brick_plates
        return results

    # ------------------------------------------------------------------
    # build_floor
    # ------------------------------------------------------------------
    def build_floor(self, x: int, z: int, width: int, depth: int,
                    plate_type: str = "Plate_2x4", color: str = "#8B4513") -> List[bool]:
        """Build a floor / platform covering a rectangular area."""
        results: List[bool] = []
        color = resolve_color(color)
        sx, sz, _ = get_piece_dims(plate_type)
        # Lay plates in rows along Z, stepping by plate depth
        step_z = sz
        step_x = sx
        fz = z
        while fz < z + depth:
            fx = x
            while fx < x + width:
                # If remaining strip is narrower, try rotating
                remaining_z = (z + depth) - fz
                remaining_x = (x + width) - fx
                use_rot = 0
                actual_type = plate_type
                if remaining_z < sz and remaining_x >= sz:
                    use_rot = 90
                # Clamp placement to not exceed bounds
                ok = self.assembly.add(actual_type, fx, fz, 0, use_rot, color)
                results.append(ok)
                fx += step_x if use_rot == 0 else step_z
            fz += step_z
        return results

    # ------------------------------------------------------------------
    # build_column
    # ------------------------------------------------------------------
    def build_column(self, x: int, z: int, height: int,
                     brick_type: str = "Brick_2x2", color: str = "#888888") -> List[bool]:
        """Build a vertical column of the given height (plate layers)."""
        results: List[bool] = []
        color = resolve_color(color)
        _, _, bh = get_piece_dims(brick_type)
        brick_plates = max(1, round(bh / PLATE_HEIGHT))
        y = 0
        while y < height:
            ok = self.assembly.add(brick_type, x, z, y, 0, color)
            results.append(ok)
            y += brick_plates
        return results

    # ------------------------------------------------------------------
    # build_roof_pyramid
    # ------------------------------------------------------------------
    def build_roof_pyramid(self, x: int, z: int, base_width: int,
                           color: str = "#CC3333") -> List[bool]:
        """Build a pyramid roof using slope bricks.

        Starts with *base_width* and each successive layer narrows by 2
        studs until it closes at the peak.
        """
        results: List[bool] = []
        color = resolve_color(color)
        bw = base_width
        y = 0
        cx = x + base_width // 2 - 1
        cz = z + base_width // 2 - 1
        while bw > 0:
            half = bw // 2
            for dx in range(-half, half + 1, 2):
                for dz in range(-half, half + 1, 2):
                    px = cx + dx
                    pz = cz + dz
                    # Only place on the perimeter of this layer
                    if abs(dx) == half or abs(dz) == half:
                        ok = self.assembly.add("Slope_2x2_45", px, pz, y, 0, color)
                        results.append(ok)
            bw -= 2
            y += 3  # each layer is one brick tall
        return results

    # ------------------------------------------------------------------
    # build_roof_pitched
    # ------------------------------------------------------------------
    def build_roof_pitched(self, x: int, z: int, width: int, depth: int,
                           color: str = "#8B4513") -> List[bool]:
        """Build a pitched / gable roof.

        Ridge runs along the X axis in the centre; slopes descend on
        both sides along the Z axis.
        """
        results: List[bool] = []
        color = resolve_color(color)
        y = 0
        ridge_z = z + depth // 2 - 1
        current_depth = depth
        z_start = z
        while current_depth > 0:
            half = current_depth // 2
            # Place slope row on each side of ridge
            for fx in range(x, x + width, 2):
                if current_depth > 2:
                    ok1 = self.assembly.add("Slope_2x2_45", fx, z_start, y, 0, color)
                    ok2 = self.assembly.add("Slope_2x2_45", fx, z_start + current_depth - 2, y, 180, color)
                    results.extend([ok1, ok2])
                else:
                    # Ridge line
                    ok = self.assembly.add("Tile_2x2", fx, ridge_z, y, 0, color)
                    results.append(ok)
            z_start += 1
            current_depth -= 2
            y += 3
        return results

    # ------------------------------------------------------------------
    # build_rect_structure
    # ------------------------------------------------------------------
    def build_rect_structure(self, x: int, z: int, w: int, d: int, h: int,
                             color: str = "#EEEEEE",
                             floor_color: str = "#8B4513",
                             door: bool = True) -> List[bool]:
        """Build a complete rectangular hollow structure.

        Four walls, a floor, open top.  A doorway is cut into the centre
        of the front wall when *door* is True.
        """
        results: List[bool] = []
        wall_color = resolve_color(color)
        floor_c = resolve_color(floor_color)
        door_x = x + w // 2 - 1  # centre of front wall

        # --- Floor ---
        self.assembly = _AssemblyClass(name="RectStructure")
        results.extend(self.build_floor(x, z, w, d, "Plate_2x4", floor_c))

        # --- Walls ---
        # Front wall (Z = z) with optional door cutout
        def front_skip(pos: int, y: int) -> bool:
            if not door:
                return False
            # Door cutout: centred, 2 studs wide, 4 plates tall
            return (pos == door_x or pos == door_x + 1) and y < 4

        y = 1
        while y < h:
            layer_pieces = []
            # Front wall
            for wx in range(x, x + w, 2):
                if front_skip(wx, y):
                    continue
                ok = self.assembly.add("Brick_2x2", wx, z, y, 0, wall_color)
                layer_pieces.append(ok)
            # Back wall
            for wx in range(x, x + w, 2):
                ok = self.assembly.add("Brick_2x2", wx, z + d - 2, y, 0, wall_color)
                layer_pieces.append(ok)
            # Side walls
            for wz in range(z + 2, z + d - 2, 2):
                ok1 = self.assembly.add("Brick_2x2", x, wz, y, 0, wall_color)
                ok2 = self.assembly.add("Brick_2x2", x + w - 2, wz, y, 0, wall_color)
                layer_pieces.extend([ok1, ok2])
            results.extend(layer_pieces)
            y += 3  # next brick layer

        return results


# =====================================================================
# 7. RECIPE GENERATORS
# =====================================================================

def recipe_house(width: int = 8, depth: int = 6, height: int = 5,
                 color: str = "tan", roof_color: str = "brown") -> BrickRecipe:
    """Generate a recipe for a simple house with floor, walls, door, and roof."""
    layers: List[dict] = []
    wall_c = resolve_color(color)
    roof_c = resolve_color(roof_color)
    door_c = resolve_color("brown")
    floor_c = resolve_color("brown")

    # Layer 0: floor
    floor_pieces = []
    for fx in range(0, width, 4):
        for fz in range(0, depth, 2):
            floor_pieces.append({
                "type": "Plate_2x4", "x": fx, "z": fz,
                "rot": 90, "color": floor_c,
            })
    layers.append({"y": 0, "pieces": floor_pieces})

    # Door position (centre of front wall)
    door_x = width // 2 - 1

    # Layers 1..height: walls (each brick = 3 plate layers)
    for layer_idx in range(height):
        y = 1 + layer_idx * 3
        wall_pieces = []
        # Front wall (Z = 0) with door cutout on layer 0..1
        for wx in range(0, width, 2):
            if layer_idx < 2 and (wx == door_x or wx == door_x + 1):
                continue  # door cutout
            wall_pieces.append({"type": "Brick_2x2", "x": wx, "z": 0,
                                "rot": 0, "color": wall_c})
        # Back wall
        for wx in range(0, width, 2):
            wall_pieces.append({"type": "Brick_2x2", "x": wx, "z": depth - 2,
                                "rot": 0, "color": wall_c})
        # Left wall
        for wz in range(2, depth - 2, 2):
            wall_pieces.append({"type": "Brick_2x2", "x": 0, "z": wz,
                                "rot": 0, "color": wall_c})
        # Right wall
        for wz in range(2, depth - 2, 2):
            wall_pieces.append({"type": "Brick_2x2", "x": width - 2, "z": wz,
                                "rot": 0, "color": wall_c})
        layers.append({"y": y, "pieces": wall_pieces})

    # Door piece (placed at the cutout)
    door_piece = {"type": "Door_1x3x4", "x": door_x, "z": 0,
                  "rot": 0, "color": door_c}
    layers[1]["pieces"].append(door_piece)

    # Roof: pitched roof
    roof_pieces = []
    ridge_y = 1 + height * 3
    half_depth = depth // 2
    for row in range(half_depth + 1):
        y = ridge_y + row * 3
        z_front = row
        z_back = depth - 2 - row
        for rx in range(0, width, 2):
            if row == half_depth or z_front == z_back:
                # Ridge line
                roof_pieces.append({"type": "Tile_2x2", "x": rx, "z": z_front,
                                    "rot": 0, "color": roof_c})
            else:
                # Front and back slopes
                roof_pieces.append({"type": "Slope_2x2_45", "x": rx, "z": z_front,
                                    "rot": 0, "color": roof_c})
                roof_pieces.append({"type": "Slope_2x2_45", "x": rx, "z": z_back,
                                    "rot": 180, "color": roof_c})
    layers.append({"y": ridge_y, "pieces": roof_pieces})

    return BrickRecipe({
        "name": f"House_{width}x{depth}x{height}",
        "description": f"A {width}x{depth} stud house, {height} bricks tall",
        "dimensions": {"width": width, "depth": depth, "height": height},
        "layers": layers,
        "colors": {"primary": wall_c, "roof": roof_c},
    })


def recipe_tower(diameter: int = 4, height: int = 8,
                 color: str = "gray") -> BrickRecipe:
    """Generate a recipe for a castle tower with crenellations.

    The tower is a square *diameter* x *diameter* structure with
    alternating brick layers and a crenellated parapet on top.
    """
    layers: List[dict] = []
    wall_c = resolve_color(color)
    floor_c = resolve_color("dark_gray")
    d = diameter

    # Floor
    floor_pieces = []
    for fx in range(0, d, 2):
        for fz in range(0, d, 2):
            floor_pieces.append({"type": "Plate_2x2", "x": fx, "z": fz,
                                 "rot": 0, "color": floor_c})
    layers.append({"y": 0, "pieces": floor_pieces})

    # Wall layers
    for layer_idx in range(height):
        y = 1 + layer_idx * 3
        wall_pieces = []
        stagger = layer_idx % 2  # alternate bonding pattern
        # All four sides
        for i in range(d):
            # Front
            if not (stagger and i == d - 1):
                wall_pieces.append({"type": "Brick_1x2", "x": i, "z": 0,
                                    "rot": 0, "color": wall_c})
            # Back
            if not (stagger and i == 0):
                wall_pieces.append({"type": "Brick_1x2", "x": i, "z": d - 1,
                                    "rot": 0, "color": wall_c})
            # Left
            if 0 < i < d - 1:
                wall_pieces.append({"type": "Brick_1x2", "x": 0, "z": i,
                                    "rot": 90, "color": wall_c})
            # Right
            if 0 < i < d - 1:
                wall_pieces.append({"type": "Brick_1x2", "x": d - 1, "z": i,
                                    "rot": 90, "color": wall_c})
        layers.append({"y": y, "pieces": wall_pieces})

    # Crenellations (parapet)
    cren_y = 1 + height * 3
    cren_pieces = []
    for i in range(0, d, 2):
        cren_pieces.append({"type": "Brick_1x1", "x": i, "z": 0,
                            "rot": 0, "color": wall_c})
        cren_pieces.append({"type": "Brick_1x1", "x": i, "z": d - 1,
                            "rot": 0, "color": wall_c})
        if 0 < i < d - 1:
            cren_pieces.append({"type": "Brick_1x1", "x": 0, "z": i,
                                "rot": 0, "color": wall_c})
            cren_pieces.append({"type": "Brick_1x1", "x": d - 1, "z": i,
                                "rot": 0, "color": wall_c})
    layers.append({"y": cren_y, "pieces": cren_pieces})

    return BrickRecipe({
        "name": f"Tower_{d}x{height}",
        "description": f"A {d}x{d} tower, {height} bricks tall with crenellations",
        "dimensions": {"diameter": d, "height": height},
        "layers": layers,
        "colors": {"primary": wall_c},
    })


def recipe_bridge(length: int = 12, width: int = 4,
                  color: str = "gray") -> BrickRecipe:
    """Generate a recipe for a stone bridge with two pillars and an arch span.

    The bridge has a road surface, two support pillars at each end,
    and sloped approach ramps.
    """
    layers: List[dict] = []
    stone_c = resolve_color(color)
    road_c = resolve_color("dark_gray")

    # Road surface (span between pillars)
    road_pieces = []
    for rz in range(0, length, 4):
        for rx in range(0, width, 2):
            road_pieces.append({"type": "Plate_2x4", "x": rx, "z": rz,
                                "rot": 90, "color": road_c})
    layers.append({"y": 6, "pieces": road_pieces})  # raised 2 bricks

    # Left and right railings
    rail_pieces = []
    for rz in range(0, length, 2):
        rail_pieces.append({"type": "Brick_1x2", "x": 0, "z": rz,
                            "rot": 0, "color": stone_c})
        rail_pieces.append({"type": "Brick_1x2", "x": width - 1, "z": rz,
                            "rot": 0, "color": stone_c})
    layers.append({"y": 7, "pieces": rail_pieces})

    # Support pillars (two at ends, one in middle)
    pillar_positions = [1, length // 2 - 1, length - 3]
    for pz in pillar_positions:
        for layer_idx in range(2):
            y = layer_idx * 3
            pillar_pieces = []
            for px in range(0, width, 2):
                pillar_pieces.append({"type": "Brick_2x2", "x": px, "z": pz,
                                      "rot": 0, "color": stone_c})
            layers.append({"y": y, "pieces": pillar_pieces})

    # Approach ramps (slopes at each end)
    ramp_pieces = []
    # Start ramp
    for rx in range(0, width, 2):
        ramp_pieces.append({"type": "Slope_2x2_33", "x": rx, "z": -2,
                            "rot": 0, "color": stone_c})
    # End ramp
    for rx in range(0, width, 2):
        ramp_pieces.append({"type": "Slope_2x2_33", "x": rx, "z": length,
                            "rot": 180, "color": stone_c})
    layers.append({"y": 3, "pieces": ramp_pieces})

    # Re-sort layers by Y so they are in order
    layers.sort(key=lambda L: L["y"])

    return BrickRecipe({
        "name": f"Bridge_{length}x{width}",
        "description": f"A {length}-stud stone bridge, {width} studs wide",
        "dimensions": {"length": length, "width": width},
        "layers": layers,
        "colors": {"primary": stone_c, "road": road_c},
    })


def recipe_vehicle(width: int = 6, length: int = 10,
                   color: str = "green") -> BrickRecipe:
    """Generate a recipe for a simple jeep-style vehicle.

    Includes a chassis, four wheel wells, roll bars, and a sloped hood.
    """
    layers: List[dict] = []
    body_c = resolve_color(color)
    wheel_c = resolve_color("black")
    glass_c = resolve_color("cyan")
    axle_c = resolve_color("gray")

    # Chassis (bottom layer)
    chassis_pieces = []
    for cz in range(0, length, 4):
        for cx in range(0, width, 2):
            chassis_pieces.append({"type": "Plate_2x4", "x": cx, "z": cz,
                                   "rot": 90, "color": body_c})
    layers.append({"y": 0, "pieces": chassis_pieces})

    # Wheel wells — cutouts on layer 1
    well_z = [1, length - 3]
    well_x = [0, width - 2]
    layer1_pieces = []
    for cz in range(0, length, 2):
        for cx in range(0, width, 2):
            # Skip wheel well positions
            is_well = (cz in well_z and cx in well_x)
            if not is_well:
                layer1_pieces.append({"type": "Brick_2x2", "x": cx, "z": cz,
                                      "rot": 0, "color": body_c})
    layers.append({"y": 1, "pieces": layer1_pieces})

    # Wheels
    wheel_pieces = []
    for wz in well_z:
        for wx in well_x:
            wheel_pieces.append({"type": "Wheel_2x2", "x": wx, "z": wz,
                                 "rot": 0, "color": wheel_c})
    # Axles
    axle_pieces = []
    for wz in well_z:
        axle_pieces.append({"type": "Brick_1x4", "x": 1, "z": wz + 1,
                            "rot": 0, "color": axle_c})
    layers.append({"y": 0, "pieces": wheel_pieces + axle_pieces})

    # Hood (front)
    hood_pieces = []
    for cz in range(length - 4, length, 2):
        for cx in range(1, width - 1, 2):
            hood_pieces.append({"type": "Slope_2x2_33", "x": cx, "z": cz,
                                "rot": 0, "color": body_c})
    layers.append({"y": 4, "pieces": hood_pieces})

    # Cabin (rear half)
    cabin_pieces = []
    for cz in range(0, length // 2, 2):
        for cx in range(0, width, 2):
            cabin_pieces.append({"type": "Brick_2x2", "x": cx, "z": cz,
                                 "rot": 0, "color": body_c})
    layers.append({"y": 4, "pieces": cabin_pieces})

    # Windshield
    windshield_pieces = []
    for cx in range(1, width - 1, 2):
        windshield_pieces.append({"type": "Slope_2x3", "x": cx, "z": length // 2 - 1,
                                  "rot": 0, "color": glass_c})
    layers.append({"y": 7, "pieces": windshield_pieces})

    # Roll bars
    rollbar_pieces = []
    rb_z = [0, length // 2 - 2]
    for rbz in rb_z:
        rollbar_pieces.append({"type": "Brick_1x1", "x": 0, "z": rbz,
                               "rot": 0, "color": body_c})
        rollbar_pieces.append({"type": "Brick_1x1", "x": width - 1, "z": rbz,
                               "rot": 0, "color": body_c})
    # Cross bar
    for cx in range(0, width, 1):
        rollbar_pieces.append({"type": "Brick_1x1", "x": cx, "z": 0,
                               "rot": 0, "color": body_c})
    layers.append({"y": 10, "pieces": rollbar_pieces})

    # Re-sort by Y
    layers.sort(key=lambda L: L["y"])

    return BrickRecipe({
        "name": f"Vehicle_{width}x{length}",
        "description": f"A jeep-style vehicle, {width}x{length} studs",
        "dimensions": {"width": width, "length": length},
        "layers": layers,
        "colors": {"primary": body_c, "wheels": wheel_c, "glass": glass_c},
    })


def recipe_tree(height: int = 8, trunk_color: str = "brown",
                leaf_color: str = "green") -> BrickRecipe:
    """Generate a recipe for a tree with a trunk and layered canopy.

    The trunk is a vertical column; each canopy layer is a wider ring of
    leaf-coloured bricks that gets narrower toward the top.
    """
    layers: List[dict] = []
    trunk_c = resolve_color(trunk_color)
    leaf_c = resolve_color(leaf_color)

    # Trunk layers
    trunk_layers = height // 2
    for layer_idx in range(trunk_layers):
        y = layer_idx * 3
        trunk_pieces = [
            {"type": "Brick_1x2", "x": 0, "z": 0, "rot": 0, "color": trunk_c},
        ]
        layers.append({"y": y, "pieces": trunk_pieces})

    # Canopy layers — each layer is a concentric ring of leaves
    canopy_start = trunk_layers - 1
    canopy_layers = (height + 1) // 2
    for ci in range(canopy_layers):
        y = (canopy_start + ci) * 3
        radius = max(1, (canopy_layers - ci) // 2 + 1)
        leaf_pieces = []
        for dx in range(-radius, radius + 1):
            for dz in range(-radius, radius + 1):
                # Ring shape — only perimeter
                if abs(dx) == radius or abs(dz) == radius:
                    lx = dx * 2
                    lz = dz * 2
                    leaf_pieces.append({"type": "Brick_2x2", "x": lx, "z": lz,
                                        "rot": 0, "color": leaf_c})
                # Fill centre for lower layers
                elif ci < canopy_layers // 2:
                    lx = dx * 2
                    lz = dz * 2
                    leaf_pieces.append({"type": "Brick_2x2", "x": lx, "z": lz,
                                        "rot": 0, "color": leaf_c})
        layers.append({"y": y, "pieces": leaf_pieces})

    # Top tuft
    top_y = (canopy_start + canopy_layers) * 3
    top_pieces = [
        {"type": "Brick_2x2", "x": -1, "z": -1, "rot": 0, "color": leaf_c},
        {"type": "Brick_2x2", "x": 1, "z": -1, "rot": 0, "color": leaf_c},
        {"type": "Brick_2x2", "x": -1, "z": 1, "rot": 0, "color": leaf_c},
        {"type": "Brick_2x2", "x": 1, "z": 1, "rot": 0, "color": leaf_c},
    ]
    layers.append({"y": top_y, "pieces": top_pieces})

    return BrickRecipe({
        "name": f"Tree_h{height}",
        "description": f"A tree {height} layers tall",
        "dimensions": {"height": height},
        "layers": layers,
        "colors": {"trunk": trunk_c, "leaves": leaf_c},
    })


# =====================================================================
# 8. MAIN — demo builds
# =====================================================================

def main():
    """Build all 5 demo recipes and report statistics."""
    # Clean scene (optional — keep existing objects so multiple runs stack)
    # Uncomment the next line to start fresh each time:
    # bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete()

    builder = AIBuilder()
    recipes: List[Tuple[str, BrickRecipe]] = [
        ("House",    recipe_house(8, 6, 5, "tan", "brown")),
        ("Tower",    recipe_tower(4, 10, "gray")),
        ("Bridge",   recipe_bridge(12, 4, "gray")),
        ("Vehicle",  recipe_vehicle(6, 10, "green")),
        ("Tree",     recipe_tree(10, "brown", "green")),
    ]

    x_offset = 0
    total_pieces = 0
    for name, recipe in recipes:
        assembly = builder.build_from_recipe(recipe)
        # Shift the whole collection so demos don't overlap
        if assembly.collection:
            for obj in assembly.collection.objects:
                obj.location.x += x_offset * STUD_SPACING * 3
        print(f"  -> {name}: {assembly.piece_count} pieces placed")
        total_pieces += assembly.piece_count
        x_offset += 20

    print("\n[AIBuilder] All 5 demo recipes built successfully!")
    print(f"  Snap system active: {_HAS_SNAP_SYSTEM}")
    print(f"  Total pieces: {total_pieces}")


if __name__ == "__main__":
    main()
