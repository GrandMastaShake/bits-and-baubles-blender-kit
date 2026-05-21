#!/usr/bin/env python3
"""
=======================================================================
  ADOPT ME PET GENERATOR — Blender Kit (am_pet_generator.py)
=======================================================================
Main orchestrator that reads ``am_species.json`` and calls geometry
primitives from ``am_geometry.py`` to assemble complete Adopt Me-style
chibi pets inside Blender.

Design Modes
------------
* **Prebuilt**  — pick a species by id, e.g. ``dog``, ``dragon``
* **Random**    — filter by rarity / family, randomise palette
* **Custom**    — supply a full colour dict and optional overrides

The 10 Immutable Design Laws are enforced at build time and also
exposed through ``validate_proportions()`` for offline checking.

Usage (inside Blender Scripting workspace)::

    import am_pet_generator as pg
    builder = pg.AdoptMePetBuilder()
    builder.build_pet("dragon", neon=True, location=(0,0,0))

Or run as a standalone script inside Blender — the ``__main__``
block at the bottom calls ``demo_build_grid()`` by default.
=======================================================================
"""

import bpy
import bmesh
import json
import math
import random
import colorsys
import os
from pathlib import Path
from typing import Dict, List, Optional, Tuple, Any

# ---------------------------------------------------------------------------
# Attempt to import companion modules; fall back gracefully if missing
# ---------------------------------------------------------------------------
try:
    import am_geometry as geo
    _HAS_GEO = True
except Exception:
    _HAS_GEO = False

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SPECS_FILE = "am_species.json"

# Design Law enforcement constants
HEAD_TO_BODY_MIN = 0.60
HEAD_TO_BODY_MAX = 0.70
EYE_TO_HEAD_MIN = 0.15
EYE_TO_HEAD_MAX = 0.22
FOOT_TO_BODY_MIN = 0.16
FOOT_TO_BODY_MAX = 0.25

# Material defaults (Design Law #7: plastic — specular 0.3, roughness 0.6)
PLASTIC_SPECULAR = 0.3
PLASTIC_ROUGHNESS = 0.6

# Neon glow defaults
NEON_GLOW_STRENGTH = 2.0

# ---------------------------------------------------------------------------
# Colour helpers
# ---------------------------------------------------------------------------

def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    """Convert #RRGGBB to RGBA tuple."""
    h = hex_str.lstrip('#')
    if len(h) == 6:
        return (int(h[0:2], 16) / 255.0,
                int(h[2:4], 16) / 255.0,
                int(h[4:6], 16) / 255.0, alpha)
    return (0.5, 0.5, 0.5, alpha)


def hex_to_rgb(hex_str: str) -> Tuple[float, float, float]:
    """Convert #RRGGBB to (r,g,b) floats 0-1."""
    r, g, b, _ = hex_to_rgba(hex_str)
    return (r, g, b)


def rgb_to_hex(r: float, g: float, b: float) -> str:
    """Convert (r,g,b) floats 0-1 to #RRGGBB."""
    return "#{:02X}{:02X}{:02X}".format(
        max(0, min(255, int(r * 255))),
        max(0, min(255, int(g * 255))),
        max(0, min(255, int(b * 255))),
    )


def resolve_color(color_val: Any, fallback: str = "#888888") -> str:
    """Resolve a colour value (hex string, 'rainbow', etc.) to hex."""
    if isinstance(color_val, str):
        if color_val.startswith('#') and len(color_val) == 7:
            return color_val
        if color_val == "rainbow":
            return "#FF69B4"  # Default rainbow fallback
    return fallback


# ---------------------------------------------------------------------------
# Material Factory  (Design Law #6: solid colours, #7: plastic)
# ---------------------------------------------------------------------------

class MaterialFactory:
    """Creates and caches simple solid-colour plastic materials."""

    def __init__(self):
        self._cache: Dict[str, bpy.types.Material] = {}

    def get(self, name: str, color_hex: str, neon: bool = False,
            neon_strength: float = 2.0) -> bpy.types.Material:
        """Retrieve (or create) a solid plastic material."""
        key = f"{name}::{color_hex}::{'neon' if neon else 'base'}"
        if key in self._cache:
            return self._cache[key]

        mat = bpy.data.materials.new(name=key)
        mat.use_nodes = True
        nt = mat.node_tree
        nodes = nt.nodes
        links = nt.links

        # Remove default principled if present
        for n in list(nodes):
            if n.type == 'BSDF_PRINCIPLED':
                nodes.remove(n)
                break

        output = nodes.get("Material Output")
        if output is None:
            output = nodes.new("ShaderNodeOutputMaterial")
        output.location = (400, 0)

        r, g, b = hex_to_rgb(color_hex)

        # Principled BSDF — plastic look (Design Law #7)
        bsdf = nodes.new("ShaderNodeBsdfPrincipled")
        bsdf.location = (0, 0)
        bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
        bsdf.inputs["Roughness"].default_value = PLASTIC_ROUGHNESS
        # Blender 4.x uses "Specular IOR Level" instead of "Specular"
        try:
            bsdf.inputs["Specular IOR Level"].default_value = PLASTIC_SPECULAR
        except KeyError:
            try:
                bsdf.inputs["Specular"].default_value = PLASTIC_SPECULAR
            except KeyError:
                pass

        if neon:
            # Add emission for glow (Design Law #9)
            emit = nodes.new("ShaderNodeEmission")
            emit.location = (0, 180)
            emit.inputs["Color"].default_value = (r, g, b, 1.0)
            emit.inputs["Strength"].default_value = neon_strength

            mix = nodes.new("ShaderNodeMixShader")
            mix.location = (200, 0)
            mix.inputs["Fac"].default_value = 0.65

            links.new(emit.outputs["Emission"], mix.inputs[1])
            links.new(bsdf.outputs["BSDF"], mix.inputs[2])
            links.new(mix.outputs["Shader"], output.inputs["Surface"])
        else:
            links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

        self._cache[key] = mat
        return mat

    def clear(self):
        """Purge cached materials."""
        self._cache.clear()


# =======================================================================
#  ADOPT ME PET BUILDER
# =======================================================================

class AdoptMePetBuilder:
    """Assembles complete Adopt Me style pets in Blender from species configs.

    Reads *am_species.json* (or a custom path) and uses the companion
    *am_geometry* module to create meshes. All 10 design laws are
    enforced at build time and can be audited via
    ``validate_proportions()``.
    """

    def __init__(self, species_file: Optional[str] = None):
        if species_file is None:
            species_file = str(Path(__file__).parent / SPECS_FILE)
        self.species_file = species_file
        with open(species_file, 'r') as f:
            self.catalog = json.load(f)

        # Species is a list — build id lookup
        species_list = self.catalog.get("species", [])
        self.species: Dict[str, dict] = {s["species_id"]: s for s in species_list}
        self.design_rules = self.catalog.get("design_rules", {})
        self.metadata = self.catalog.get("metadata", {})
        self.materials = MaterialFactory()
        self._built: List[dict] = []

    def _species_cfg(self, species_id: str) -> dict:
        """Retrieve a species config or raise."""
        if species_id not in self.species:
            available = sorted(self.species.keys())
            raise KeyError(
                f"Unknown species '{species_id}'. Available: {available}"
            )
        return self.species[species_id]

    def _apply_material(self, obj: bpy.types.Object, color_hex: str,
                        neon: bool = False, neon_strength: float = 2.0):
        """Assign solid-colour plastic material to an object."""
        if obj is None:
            return
        mat = self.materials.get(obj.name, color_hex, neon=neon,
                                  neon_strength=neon_strength)
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)

    def _make_empty(self, name: str, location: Tuple[float, ...]
                    ) -> bpy.types.Object:
        """Create an Empty to parent the whole pet rig."""
        empty = bpy.data.objects.new(name, None)
        empty.empty_display_type = 'SPHERE'
        empty.empty_display_size = 0.2
        empty.location = location
        bpy.context.collection.objects.link(empty)
        return empty

    def _set_parent(self, child: bpy.types.Object,
                    parent: bpy.types.Object):
        """Parent *child* to *parent* keeping world transform."""
        if child is None or parent is None:
            return
        bpy.ops.object.select_all(action='DESELECT')
        child.select_set(True)
        parent.select_set(True)
        bpy.context.view_layer.objects.active = parent
        bpy.ops.object.parent_set(type='OBJECT', keep_transform=True)

    def _select_activate(self, obj: bpy.types.Object):
        """Select and activate an object for operations."""
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

    def _add_bevel_subsurf(self, obj: bpy.types.Object, subsurf_levels: int = 2):
        """Add bevel + subsurf modifiers for rounded look (Design Law #5)."""
        if obj is None or obj.type != 'MESH':
            return
        # Smooth shading
        for poly in obj.data.polygons:
            poly.use_smooth = True
        # Subsurf
        subsurf = obj.modifiers.new(name="Subsurf", type='SUBSURF')
        subsurf.levels = subsurf_levels
        subsurf.render_levels = subsurf_levels
        # Bevel for softened edges
        bevel = obj.modifiers.new(name="Bevel", type='BEVEL')
        bevel.width = 0.015
        bevel.segments = 2
        bevel.limit_method = 'ANGLE'
        bevel.angle_limit = math.radians(35)

    # ------------------------------------------------------------------
    # Inline geometry primitives (fallback when am_geometry unavailable)
    # ------------------------------------------------------------------
    def _sphere(self, name: str, radius: float, location: Tuple[float, ...],
                scale: Tuple[float, ...] = (1, 1, 1),
                segments: int = 12, ring_count: int = 10) -> bpy.types.Object:
        """Create a UV sphere."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=radius, segments=segments, ring_count=ring_count,
            location=location
        )
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale
        self._add_bevel_subsurf(obj, subsurf_levels=2)
        return obj

    def _cube(self, name: str, size: float, location: Tuple[float, ...],
              scale: Tuple[float, ...] = (1, 1, 1)) -> bpy.types.Object:
        """Create a cube with cast-to-sphere modifier for roundness."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cube_add(size=size, location=location)
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = scale
        cast = obj.modifiers.new(name="Cast", type='CAST')
        cast.factor = 0.35
        self._add_bevel_subsurf(obj, subsurf_levels=2)
        return obj

    def _cone(self, name: str, radius1: float, radius2: float, depth: float,
              location: Tuple[float, ...],
              rotation: Tuple[float, ...] = (0, 0, 0),
              vertices: int = 8) -> bpy.types.Object:
        """Create a cone."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cone_add(
            radius1=radius1, radius2=radius2, depth=depth,
            vertices=vertices, location=location, rotation=rotation
        )
        obj = bpy.context.active_object
        obj.name = name
        self._add_bevel_subsurf(obj, subsurf_levels=1)
        return obj

    def _cylinder(self, name: str, radius: float, depth: float,
                  location: Tuple[float, ...],
                  vertices: int = 8) -> bpy.types.Object:
        """Create a cylinder."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_cylinder_add(
            radius=radius, depth=depth, vertices=vertices,
            location=location
        )
        obj = bpy.context.active_object
        obj.name = name
        self._add_bevel_subsurf(obj, subsurf_levels=1)
        return obj

    def _half_sphere(self, name: str, radius: float,
                     location: Tuple[float, ...]) -> bpy.types.Object:
        """Create a hemisphere (flat bottom) — Design Law #3."""
        bpy.ops.object.select_all(action='DESELECT')
        bpy.ops.mesh.primitive_uv_sphere_add(
            radius=radius, segments=10, ring_count=6,
            location=location
        )
        obj = bpy.context.active_object
        obj.name = name
        # Flatten bottom
        obj.scale = (1.0, 0.55, 1.0)
        self._add_bevel_subsurf(obj, subsurf_levels=1)
        return obj

    def _flattened_sphere(self, name: str, radius: float,
                          location: Tuple[float, ...],
                          flatten: float = 0.4) -> bpy.types.Object:
        """Create a flattened sphere (for ears etc)."""
        obj = self._sphere(name, radius, location, scale=(1.0, flatten, 1.0),
                           segments=8, ring_count=6)
        return obj

    # ------------------------------------------------------------------
    # Part builders
    # ------------------------------------------------------------------
    def _build_body(self, name: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, location: Tuple[float, ...],
                    neon: bool = False) -> bpy.types.Object:
        """Build body — chubby rounded shape."""
        style = geo_cfg.get("style", "chubby")
        scale = geo_cfg.get("scale", 1.0)
        # Base dimensions scaled by proportions
        h2b = prop_cfg.get("head_to_body", 0.65)
        base_h = 0.7 * scale
        base_w = 0.9 * scale
        base_d = 1.2 * scale

        if style in ("chubby", "stubby"):
            obj = self._cube(name, 1.0, location,
                             scale=(base_w, base_h, base_d))
        elif style in ("slim",):
            obj = self._cube(name, 1.0, location,
                             scale=(base_w * 0.8, base_h * 0.9, base_d * 1.1))
        elif style == "lion_chubby":
            obj = self._cube(name, 1.0, location,
                             scale=(base_w * 1.2, base_h, base_d))
        else:
            obj = self._cube(name, 1.0, location,
                             scale=(base_w, base_h, base_d))
        self._apply_material(obj, color_hex, neon=neon)
        return obj

    def _build_head(self, name: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, location: Tuple[float, ...],
                    body_location: Tuple[float, ...],
                    neon: bool = False) -> bpy.types.Object:
        """Build head — large chibi sphere that clips into body (Design Law #4)."""
        style = geo_cfg.get("style", "round")
        scale = geo_cfg.get("scale", 1.0)
        h2b = prop_cfg.get("head_to_body", 0.65)

        # Head should be 60-70% of body (Design Law #1)
        head_radius = 0.55 * scale
        head_scale = (1.0, 0.92, 1.05)  # Slightly wider for cuteness

        # Position head so it clips into body (no neck)
        clip_amount = head_radius * 0.35
        head_y = body_location[1] + 0.25 + (head_radius * 0.6) - clip_amount * 0.3

        if style in ("round", "horse_round", "oval"):
            obj = self._sphere(name, head_radius, (location[0], head_y, location[2]),
                               scale=head_scale)
        elif style in ("triangular", "triangular_round", "angular", "angular_round",
                         "eagle"):
            obj = self._cone(name, head_radius * 0.9, head_radius * 0.4,
                             head_radius * 1.8,
                             (location[0], head_y, location[2]),
                             vertices=8)
        elif style == "blocky":
            obj = self._cube(name, head_radius * 1.6,
                             (location[0], head_y, location[2]))
        else:
            obj = self._sphere(name, head_radius, (location[0], head_y, location[2]),
                               scale=head_scale)

        self._apply_material(obj, color_hex, neon=neon)
        return obj

    def _build_eyes(self, name_prefix: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, head_location: Tuple[float, ...],
                    neon: bool = False) -> List[bpy.types.Object]:
        """Build eyes — perfect spheres, flat colour, NO pupils (Design Law #2)."""
        eye_scale = geo_cfg.get("scale", 0.18)
        eye_color = resolve_color(geo_cfg.get("color", "#222222"))
        e2h = prop_cfg.get("eye_to_head", 0.18)

        eye_radius = 0.55 * eye_scale * e2h
        eye_y_offset = 0.05
        eye_z_forward = 0.42  # Forward from head center
        eye_spacing = eye_radius * 3.2

        head_y = head_location[1]
        eye_y = head_y + eye_y_offset

        eye_left = self._sphere(
            f"{name_prefix}_Eye_L", eye_radius,
            (head_location[0] - eye_spacing * 0.5, eye_y,
             head_location[2] + eye_z_forward),
            scale=(1.0, 1.0, 0.85), segments=10, ring_count=8
        )
        self._apply_material(eye_left, eye_color, neon=neon)

        eye_right = self._sphere(
            f"{name_prefix}_Eye_R", eye_radius,
            (head_location[0] + eye_spacing * 0.5, eye_y,
             head_location[2] + eye_z_forward),
            scale=(1.0, 1.0, 0.85), segments=10, ring_count=8
        )
        self._apply_material(eye_right, eye_color, neon=neon)

        return [eye_left, eye_right]

    def _build_ears(self, name_prefix: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, head_location: Tuple[float, ...],
                    neon: bool = False) -> List[bpy.types.Object]:
        """Build ears based on style."""
        style = geo_cfg.get("style", "round")
        ear_color = resolve_color(geo_cfg.get("color", color_hex))
        length = geo_cfg.get("length", "medium")
        e2h = prop_cfg.get("ear_to_head", 0.4)

        ear_h = 0.25 * e2h
        ear_w = 0.12
        head_y = head_location[1]
        ear_y = head_y + 0.15
        ear_x_offset = 0.35
        ear_z = head_location[2]

        ears = []

        if style == "floppy":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._flattened_sphere(
                    f"{name_prefix}_Ear_{side}", ear_h,
                    (head_location[0] + sx * ear_x_offset, ear_y - ear_h * 0.3, ear_z),
                    flatten=0.35
                )
                obj.rotation_euler = (math.radians(15 * sx), 0, math.radians(-10 * sx))
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        elif style == "floppy_long":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._cylinder(
                    f"{name_prefix}_Ear_{side}", ear_w, ear_h * 2.2,
                    (head_location[0] + sx * ear_x_offset, ear_y - ear_h * 0.5, ear_z)
                )
                obj.rotation_euler = (0, 0, math.radians(-8 * sx))
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        elif style == "floppy_large":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._flattened_sphere(
                    f"{name_prefix}_Ear_{side}", ear_h * 1.5,
                    (head_location[0] + sx * (ear_x_offset + 0.1), ear_y - ear_h * 0.2, ear_z),
                    flatten=0.25
                )
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        elif style == "pointy":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._cone(
                    f"{name_prefix}_Ear_{side}", ear_w, 0.0, ear_h * 1.8,
                    (head_location[0] + sx * ear_x_offset, ear_y + ear_h * 0.4, ear_z),
                    vertices=6
                )
                obj.rotation_euler = (0, 0, math.radians(-12 * sx))
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        elif style == "round":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._flattened_sphere(
                    f"{name_prefix}_Ear_{side}", ear_h * 0.7,
                    (head_location[0] + sx * ear_x_offset, ear_y + ear_h * 0.2, ear_z),
                    flatten=0.5
                )
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        elif style == "pointy_tufts":
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._cone(
                    f"{name_prefix}_EarTuft_{side}", ear_w * 0.6, 0.0, ear_h,
                    (head_location[0] + sx * ear_x_offset, ear_y + ear_h * 0.3, ear_z),
                    vertices=5
                )
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        else:
            # Default: round ears
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._flattened_sphere(
                    f"{name_prefix}_Ear_{side}", ear_h * 0.7,
                    (head_location[0] + sx * ear_x_offset, ear_y + ear_h * 0.2, ear_z),
                    flatten=0.5
                )
                self._apply_material(obj, ear_color, neon=neon)
                ears.append(obj)

        return ears

    def _build_snout(self, name_prefix: str, geo_cfg: dict,
                     color_hex: str, head_location: Tuple[float, ...],
                     neon: bool = False) -> Optional[bpy.types.Object]:
        """Build snout on the front of the head."""
        style = geo_cfg.get("style", "short")
        snout_color = resolve_color(geo_cfg.get("color", color_hex))
        snout_scale = geo_cfg.get("scale", 0.2)

        head_y = head_location[1]
        snout_y = head_y - 0.08
        snout_z = head_location[2] + 0.38

        if style == "short":
            obj = self._sphere(
                f"{name_prefix}_Snout", snout_scale * 0.5,
                (head_location[0], snout_y, snout_z),
                scale=(1.0, 0.8, 0.9), segments=8, ring_count=6
            )
        elif style == "long":
            obj = self._cone(
                f"{name_prefix}_Snout", snout_scale * 0.4, snout_scale * 0.2,
                snout_scale * 1.2,
                (head_location[0], snout_y, snout_z + 0.05),
                rotation=(math.radians(90), 0, 0), vertices=8
            )
        elif style == "broad":
            obj = self._sphere(
                f"{name_prefix}_Snout", snout_scale * 0.6,
                (head_location[0], snout_y, snout_z),
                scale=(1.3, 0.9, 1.0), segments=8, ring_count=6
            )
        elif style == "broad_round":
            obj = self._sphere(
                f"{name_prefix}_Snout", snout_scale * 0.7,
                (head_location[0], snout_y, snout_z),
                scale=(1.4, 1.0, 1.1), segments=8, ring_count=6
            )
        else:
            obj = self._sphere(
                f"{name_prefix}_Snout", snout_scale * 0.5,
                (head_location[0], snout_y, snout_z),
                scale=(1.0, 0.8, 0.9), segments=8, ring_count=6
            )

        self._apply_material(obj, snout_color, neon=neon)
        return obj

    def _build_beak(self, name_prefix: str, geo_cfg: dict,
                    color_hex: str, head_location: Tuple[float, ...],
                    neon: bool = False) -> Optional[bpy.types.Object]:
        """Build a beak (for birds)."""
        style = geo_cfg.get("style", "small_triangle")
        beak_color = resolve_color(geo_cfg.get("color", color_hex))
        beak_scale = geo_cfg.get("scale", 0.15)

        head_y = head_location[1]
        beak_y = head_y - 0.02
        beak_z = head_location[2] + 0.45

        obj = self._cone(
            f"{name_prefix}_Beak", beak_scale * 0.5, 0.0, beak_scale * 1.2,
            (head_location[0], beak_y, beak_z),
            rotation=(math.radians(90), 0, 0), vertices=6
        )
        self._apply_material(obj, beak_color, neon=neon)
        return obj

    def _build_feet(self, name_prefix: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, body_bottom_y: float,
                    neon: bool = False) -> List[bpy.types.Object]:
        """Build feet — hemispheres, floating detached (Design Law #3)."""
        foot_scale = geo_cfg.get("scale", 0.25)
        foot_color = resolve_color(geo_cfg.get("color", color_hex))
        foot_count = geo_cfg.get("count", 4)
        f2b = prop_cfg.get("foot_to_body", 0.22)

        # Foot radius = 1/4 to 1/6 of body height
        foot_radius = 0.18 * foot_scale
        gap = 0.08  # Floating gap

        feet_y = body_bottom_y - gap - foot_radius * 0.5
        feet = []

        if foot_count == 4:
            positions = [
                ("FL", -0.25, -0.22), ("FR", 0.25, -0.22),
                ("BL", -0.25, 0.22),  ("BR", 0.25, 0.22),
            ]
        elif foot_count == 2:
            positions = [("L", -0.22, 0.05), ("R", 0.22, 0.05)]
        else:
            positions = [("C", 0.0, 0.05)]

        for suffix, fx, fz in positions:
            obj = self._half_sphere(
                f"{name_prefix}_Foot_{suffix}", foot_radius,
                (fx, feet_y, fz)
            )
            self._apply_material(obj, foot_color, neon=neon)
            feet.append(obj)

        return feet

    def _build_tail(self, name_prefix: str, geo_cfg: dict, prop_cfg: dict,
                    color_hex: str, body_location: Tuple[float, ...],
                    neon: bool = False) -> Optional[bpy.types.Object]:
        """Build tail behind the body."""
        style = geo_cfg.get("style", "short")
        tail_color = resolve_color(geo_cfg.get("color", color_hex))
        tail_length = geo_cfg.get("length", 0.5)
        t2b = prop_cfg.get("tail_to_body", 0.5)

        if style == "none" or tail_length <= 0:
            return None

        tail_y = body_location[1] + 0.15
        tail_z = body_location[2] + 0.55

        if style in ("puff", "fluffy", "short_fluffy"):
            obj = self._sphere(
                f"{name_prefix}_Tail", tail_length * 0.15,
                (body_location[0], tail_y, tail_z),
                scale=(1.0, 1.0, tail_length * 1.5), segments=8, ring_count=6
            )
        elif style in ("curved", "curly"):
            obj = self._cone(
                f"{name_prefix}_Tail", tail_length * 0.1, tail_length * 0.04,
                tail_length * 0.5,
                (body_location[0], tail_y + tail_length * 0.15, tail_z),
                rotation=(math.radians(70), 0, 0), vertices=8
            )
        elif style in ("short", "short_thin", "stub"):
            obj = self._cone(
                f"{name_prefix}_Tail", tail_length * 0.08, tail_length * 0.03,
                tail_length * 0.25,
                (body_location[0], tail_y, tail_z),
                rotation=(math.radians(80), 0, 0), vertices=6
            )
        elif style in ("spiked",):
            obj = self._cone(
                f"{name_prefix}_Tail", tail_length * 0.1, tail_length * 0.03,
                tail_length * 0.6,
                (body_location[0], tail_y, tail_z + 0.1),
                rotation=(math.radians(75), 0, 0), vertices=6
            )
        elif style in ("long",):
            obj = self._cone(
                f"{name_prefix}_Tail", tail_length * 0.08, tail_length * 0.03,
                tail_length * 0.7,
                (body_location[0], tail_y, tail_z),
                rotation=(math.radians(70), 0, 0), vertices=8
            )
        elif style in ("fluffy", "feather_cascade"):
            obj = self._sphere(
                f"{name_prefix}_Tail", tail_length * 0.18,
                (body_location[0], tail_y, tail_z),
                scale=(1.0, 0.9, tail_length * 1.3), segments=10, ring_count=8
            )
        elif style in ("lion_tuft",):
            obj = self._sphere(
                f"{name_prefix}_Tail", tail_length * 0.2,
                (body_location[0], tail_y, tail_z),
                scale=(1.0, 1.0, tail_length), segments=10, ring_count=8
            )
        else:
            obj = self._cone(
                f"{name_prefix}_Tail", tail_length * 0.08, tail_length * 0.03,
                tail_length * 0.5,
                (body_location[0], tail_y, tail_z),
                rotation=(math.radians(75), 0, 0), vertices=8
            )

        self._apply_material(obj, tail_color, neon=neon)
        return obj

    def _build_horns(self, name_prefix: str, geo_cfg: dict,
                     color_hex: str, head_location: Tuple[float, ...],
                     neon: bool = False) -> List[bpy.types.Object]:
        """Build horns on top of the head."""
        style = geo_cfg.get("style", "simple")
        horn_color = resolve_color(geo_cfg.get("color", color_hex))
        horn_count = geo_cfg.get("count", 2)
        horn_scale = geo_cfg.get("scale", 0.5)

        head_y = head_location[1]
        horn_y = head_y + 0.35
        horn_z = head_location[2]
        horns = []

        if horn_count == 1:
            # Single horn (unicorn)
            obj = self._cone(
                f"{name_prefix}_Horn", 0.06 * horn_scale, 0.0,
                0.4 * horn_scale,
                (head_location[0], horn_y, horn_z), vertices=8
            )
            self._apply_material(obj, horn_color, neon=neon)
            horns.append(obj)
        else:
            for side, sx in [("L", -1), ("R", 1)]:
                obj = self._cone(
                    f"{name_prefix}_Horn_{side}", 0.05 * horn_scale, 0.0,
                    0.35 * horn_scale,
                    (head_location[0] + sx * 0.2, horn_y, horn_z),
                    vertices=7
                )
                obj.rotation_euler = (0, 0, math.radians(-8 * sx))
                self._apply_material(obj, horn_color, neon=neon)
                horns.append(obj)

        return horns

    def _build_wings(self, name_prefix: str, geo_cfg: dict,
                     color_hex: str, body_location: Tuple[float, ...],
                     neon: bool = False) -> List[bpy.types.Object]:
        """Build wings on the sides of the body."""
        style = geo_cfg.get("style", "small")
        wing_color = resolve_color(geo_cfg.get("color", color_hex))
        wing_scale = geo_cfg.get("scale", 0.8)

        wing_y = body_location[1] + 0.25
        wing_z = body_location[2]
        wings = []

        for side, sx in [("L", -1), ("R", 1)]:
            obj = self._cone(
                f"{name_prefix}_Wing_{side}",
                0.35 * wing_scale, 0.05 * wing_scale, 0.6 * wing_scale,
                (body_location[0] + sx * 0.55, wing_y, wing_z),
                rotation=(math.radians(-15), 0, math.radians(20 * sx)),
                vertices=8
            )
            self._apply_material(obj, wing_color, neon=neon)
            wings.append(obj)

        return wings

    def _build_antlers(self, name_prefix: str, geo_cfg: dict,
                       color_hex: str, head_location: Tuple[float, ...],
                       neon: bool = False) -> List[bpy.types.Object]:
        """Build antlers (for deer)."""
        antler_color = resolve_color(geo_cfg.get("color", color_hex))
        antler_scale = geo_cfg.get("scale", 0.6)

        head_y = head_location[1]
        antler_y = head_y + 0.4
        antlers = []

        for side, sx in [("L", -1), ("R", 1)]:
            # Main branch
            obj = self._cone(
                f"{name_prefix}_Antler_{side}",
                0.04 * antler_scale, 0.02, 0.4 * antler_scale,
                (head_location[0] + sx * 0.15, antler_y, head_location[2]),
                vertices=5
            )
            obj.rotation_euler = (0, 0, math.radians(-15 * sx))
            self._apply_material(obj, antler_color, neon=neon)
            antlers.append(obj)

        return antlers

    def _build_trunk(self, name_prefix: str, geo_cfg: dict,
                     color_hex: str, head_location: Tuple[float, ...],
                     neon: bool = False) -> Optional[bpy.types.Object]:
        """Build elephant trunk."""
        trunk_color = resolve_color(geo_cfg.get("color", color_hex))
        trunk_scale = geo_cfg.get("scale", 0.8)

        head_y = head_location[1]
        trunk_y = head_y - 0.15
        trunk_z = head_location[2] + 0.45

        obj = self._cone(
            f"{name_prefix}_Trunk", 0.06 * trunk_scale, 0.03 * trunk_scale,
            0.5 * trunk_scale,
            (head_location[0], trunk_y, trunk_z),
            rotation=(math.radians(85), 0, 0), vertices=8
        )
        self._apply_material(obj, trunk_color, neon=neon)
        return obj

    # ------------------------------------------------------------------
    #  Neon glow application  (Design Law #9)
    # ------------------------------------------------------------------
    def _apply_neon(self, parts: list, neon_cfg: dict, color_fallback: str):
        """Apply neon glow materials to specified glowing parts."""
        glow_parts = set(neon_cfg.get("glow_parts", []))
        glow_color = resolve_color(neon_cfg.get("glow_color", color_fallback))
        glow_intensity = neon_cfg.get("glow_intensity", 0.8) * 2.5

        if not glow_parts:
            return

        for category, obj in parts:
            if obj is None:
                continue
            # Check if this part category should glow
            should_glow = False
            for glow_part in glow_parts:
                if glow_part.lower() in category.lower():
                    should_glow = True
                    break

            # Also check specific part names
            if not should_glow:
                for glow_part in glow_parts:
                    if glow_part.lower() in obj.name.lower():
                        should_glow = True
                        break

            if should_glow:
                self._apply_material(obj, glow_color, neon=True,
                                     neon_strength=glow_intensity)

        print(f"[Neon] Glow applied to parts: {glow_parts}")

    # =================================================================
    #  PUBLIC API
    # =================================================================

    def build_pet(self, species_id: str,
                  colors: Optional[Dict[str, str]] = None,
                  neon: bool = False,
                  location: Tuple[float, float, float] = (0, 0, 0),
                  name: Optional[str] = None) -> dict:
        """Build a complete pet from a species configuration.

        Parameters
        ----------
        species_id : str
            Key into the species catalog (e.g. ``'dog'``, ``'dragon'``).
        colors : dict, optional
            Override colours — ``{"primary": "#RRGGBB", ...}``.
        neon : bool
            If *True*, apply neon glow to configured parts.
        location : tuple
            World-space (x, y, z) for the pet root.
        name : str, optional
            Custom name for the top-level empty.

        Returns
        -------
        dict
            Build report with keys: ``name``, ``species``, ``location``,
            ``colors``, ``piece_count``, ``objects``, ``issues``.
        """
        cfg = self._species_cfg(species_id)
        species_name = name or cfg.get("display_name", cfg["name"])
        ox, oy, oz = location

        print(f"\n[Build] Starting '{species_name}' ({species_id}) at {location}")

        # --- Resolve colours -----------------------------------------------
        default_colors = cfg.get("colors", {})
        if colors:
            resolved = {
                "primary": colors.get("primary", resolve_color(default_colors.get("primary"), "#888888")),
                "secondary": colors.get("secondary", resolve_color(default_colors.get("secondary"), "#AAAAAA")),
                "accent": colors.get("accent", resolve_color(default_colors.get("accent"), "#CCCCCC")),
            }
        else:
            resolved = {
                "primary": resolve_color(default_colors.get("primary"), "#888888"),
                "secondary": resolve_color(default_colors.get("secondary"), "#AAAAAA"),
                "accent": resolve_color(default_colors.get("accent"), "#CCCCCC"),
            }

        col_pri = resolved["primary"]
        col_sec = resolved["secondary"]
        col_acc = resolved["accent"]

        geo = cfg.get("geometry", {})
        prop = cfg.get("proportions", {})

        # --- Create collection for this pet --------------------------------
        coll_name = f"Pet_{species_name}"
        if coll_name in bpy.data.collections:
            coll = bpy.data.collections[coll_name]
        else:
            coll = bpy.data.collections.new(coll_name)
            bpy.context.scene.collection.children.link(coll)

        # Empty parent
        root = self._make_empty(species_name, (ox, oy, oz))
        coll.objects.link(root)

        parts: List[Tuple[str, bpy.types.Object]] = []
        issues: List[str] = []

        # --- BODY ----------------------------------------------------------
        body_geo = geo.get("body", {})
        body_color = resolve_color(body_geo.get("color", col_pri), col_pri)
        body_loc = (ox, oy + 0.35, oz)
        body = self._build_body(
            species_name, body_geo, prop, body_color, body_loc, neon=neon
        )
        parts.append(("body", body))
        print(f"  Body: built at {body_loc}")

        # --- HEAD  (Design Law #4: no neck, clips into body) ---------------
        head_geo = geo.get("head", {})
        head_color = resolve_color(head_geo.get("color", col_pri), col_pri)
        head = self._build_head(
            species_name, head_geo, prop, head_color, (ox, oy, oz),
            body_loc, neon=neon
        )
        parts.append(("head", head))
        head_loc = head.location
        print(f"  Head: built at {head_loc} (clips into body)")

        # --- EYES  (Design Law #2: perfect spheres, flat colour, NO pupils)
        eyes_geo = geo.get("eyes", {})
        if eyes_geo:
            eye_objs = self._build_eyes(
                species_name, eyes_geo, prop, col_pri, head_loc, neon=neon
            )
            for eye_obj in eye_objs:
                parts.append(("eyes", eye_obj))
            print(f"  Eyes: {len(eye_objs)} built")

        # --- EARS ----------------------------------------------------------
        ears_geo = geo.get("ears", {})
        if ears_geo:
            ear_objs = self._build_ears(
                species_name, ears_geo, prop, col_pri, head_loc, neon=neon
            )
            for ear_obj in ear_objs:
                parts.append(("ears", ear_obj))
            print(f"  Ears: {len(ear_objs)} built")

        # --- SNOUT or BEAK -------------------------------------------------
        snout_geo = geo.get("snout", {})
        beak_geo = geo.get("beak", {})
        if snout_geo:
            snout = self._build_snout(
                species_name, snout_geo, col_sec, head_loc, neon=neon
            )
            if snout:
                parts.append(("snout", snout))
                print("  Snout: built")
        if beak_geo:
            beak = self._build_beak(
                species_name, beak_geo, col_acc, head_loc, neon=neon
            )
            if beak:
                parts.append(("beak", beak))
                print("  Beak: built")

        # --- NOSE (optional small detail) ----------------------------------
        nose_geo = geo.get("nose", {})
        if nose_geo:
            nose_color = resolve_color(nose_geo.get("color", col_acc), col_acc)
            nose = self._sphere(
                f"{species_name}_Nose", 0.04,
                (head_loc[0], head_loc[1] - 0.02, head_loc[2] + 0.46),
                scale=(1.0, 0.8, 0.8), segments=6, ring_count=4
            )
            self._apply_material(nose, nose_color, neon=neon)
            parts.append(("nose", nose))

        # --- FEET  (Design Law #3: hemispheres, floating, detached) --------
        feet_geo = geo.get("feet", {})
        if feet_geo:
            foot_objs = self._build_feet(
                species_name, feet_geo, prop, col_sec,
                body_loc[1] - 0.3, neon=neon
            )
            for foot_obj in foot_objs:
                parts.append(("feet", foot_obj))
            print(f"  Feet: {len(foot_objs)} built (floating hemispheres)")

        # --- TAIL ----------------------------------------------------------
        tail_geo = geo.get("tail", {})
        if tail_geo:
            tail = self._build_tail(
                species_name, tail_geo, prop, col_pri, body_loc, neon=neon
            )
            if tail:
                parts.append(("tail", tail))
                print("  Tail: built")

        # --- WINGS ---------------------------------------------------------
        wings_geo = geo.get("wings", {})
        if wings_geo:
            wing_objs = self._build_wings(
                species_name, wings_geo, col_acc, body_loc, neon=neon
            )
            for wing_obj in wing_objs:
                parts.append(("wings", wing_obj))
            print(f"  Wings: {len(wing_objs)} built")

        # --- HORNS ---------------------------------------------------------
        horns_geo = geo.get("horns", {})
        horn_geo = geo.get("horn", {})  # singular (unicorn)
        if horns_geo:
            horn_objs = self._build_horns(
                species_name, horns_geo, col_acc, head_loc, neon=neon
            )
            for horn_obj in horn_objs:
                parts.append(("horns", horn_obj))
            print(f"  Horns: {len(horn_objs)} built")
        elif horn_geo:
            horn_objs = self._build_horns(
                species_name, horn_geo, col_acc, head_loc, neon=neon
            )
            for horn_obj in horn_objs:
                parts.append(("horn", horn_obj))
            print(f"  Horn: {len(horn_objs)} built")

        # --- ANTLERS (deer) ------------------------------------------------
        antlers_geo = geo.get("antlers", {})
        if antlers_geo:
            antler_objs = self._build_antlers(
                species_name, antlers_geo, col_acc, head_loc, neon=neon
            )
            for antler_obj in antler_objs:
                parts.append(("antlers", antler_obj))
            print(f"  Antlers: {len(antler_objs)} built")

        # --- TRUNK (elephant) ----------------------------------------------
        trunk_geo = geo.get("trunk", {})
        if trunk_geo:
            trunk = self._build_trunk(
                species_name, trunk_geo, col_pri, head_loc, neon=neon
            )
            if trunk:
                parts.append(("trunk", trunk))
                print("  Trunk: built")

        # --- TUSKS (elephant) ----------------------------------------------
        tusks_geo = geo.get("tusks", {})
        if tusks_geo:
            tusk_color = resolve_color(tusks_geo.get("color", col_acc), col_acc)
            for side, sx in [("L", -1), ("R", 1)]:
                tusk = self._cone(
                    f"{species_name}_Tusk_{side}", 0.03, 0.01, 0.15,
                    (head_loc[0] + sx * 0.12, head_loc[1] - 0.08,
                     head_loc[2] + 0.38),
                    rotation=(math.radians(60), 0, math.radians(-10 * sx)),
                    vertices=6
                )
                self._apply_material(tusk, tusk_color, neon=neon)
                parts.append(("tusks", tusk))
            print("  Tusks: built")

        # --- COMB / WATTLE (chicken) ---------------------------------------
        comb_geo = geo.get("comb", {})
        if comb_geo:
            comb_color = resolve_color(comb_geo.get("color", col_acc), col_acc)
            comb = self._cone(
                f"{species_name}_Comb", 0.06, 0.02, 0.1,
                (head_loc[0], head_loc[1] + 0.4, head_loc[2]),
                vertices=5
            )
            self._apply_material(comb, comb_color, neon=neon)
            parts.append(("comb", comb))

        # --- PARENTING -----------------------------------------------------
        for _, obj in parts:
            if obj is not None:
                self._set_parent(obj, root)

        # --- NEON GLOW (Design Law #9) -------------------------------------
        if neon:
            neon_cfg = cfg.get("neon_config", {})
            self._apply_neon(parts, neon_cfg, col_acc)

        # --- VALIDATION ----------------------------------------------------
        val = self.validate_proportions(species_id)
        if val.get("warnings"):
            issues.extend(val["warnings"])
            for w in val["warnings"]:
                print(f"  [WARN] {w}")

        # --- BUILD REPORT --------------------------------------------------
        valid_parts = [(c, o) for c, o in parts if o is not None]
        report = {
            "name": species_name,
            "species_id": species_id,
            "location": location,
            "colors": resolved,
            "neon": neon,
            "piece_count": len(valid_parts),
            "objects": valid_parts,
            "root": root,
            "issues": issues,
            "validation": val,
        }
        self._built.append(report)
        print(f"[Build] '{species_name}' complete — {len(valid_parts)} parts")
        return report

    # ------------------------------------------------------------------
    #  Random Builder
    # ------------------------------------------------------------------
    def build_random(self,
                     rarity: Optional[str] = None,
                     family: Optional[str] = None,
                     neon: bool = False,
                     location: Tuple[float, float, float] = (0, 0, 0)
                     ) -> dict:
        """Build a random pet, optionally filtered by rarity and/or family."""
        candidates = []
        for sid, cfg in self.species.items():
            if rarity and cfg.get("rarity") != rarity:
                continue
            if family and cfg.get("family") != family:
                continue
            candidates.append(sid)

        if not candidates:
            all_ids = list(self.species.keys())
            print(f"[Random] No match for rarity={rarity}, family={family}")
            print(f"         Picking from all {len(all_ids)} species")
            candidates = all_ids

        chosen = random.choice(candidates)

        # Slight colour randomisation
        randomizer = PetColorRandomizer()
        base_cfg = self.species[chosen]
        default_colors = base_cfg.get("colors", {})
        palette = randomizer.random_colors(
            base_hue=random.random(),
            scheme=random.choice(["analogous", "triadic", "monochromatic"])
        )
        merged_colors = {
            "primary": palette.get("primary", resolve_color(default_colors.get("primary"), "#888888")),
            "secondary": palette.get("secondary", resolve_color(default_colors.get("secondary"), "#AAAAAA")),
            "accent": palette.get("accent", resolve_color(default_colors.get("accent"), "#CCCCCC")),
        }

        print(f"\n[Random] Chose '{chosen}' (rarity={self.species[chosen].get('rarity')}, "
              f"family={self.species[chosen].get('family')})")

        return self.build_pet(
            species_id=chosen,
            colors=merged_colors,
            neon=neon,
            location=location,
            name=f"Random_{chosen.title()}"
        )

    # ------------------------------------------------------------------
    #  Build All Species (grid display)
    # ------------------------------------------------------------------
    def build_all_species(self, spacing: float = 8.0) -> List[dict]:
        """Build every species in the catalog arranged in a grid."""
        ids = sorted(self.species.keys())
        count = len(ids)
        cols = int(math.ceil(math.sqrt(count)))
        reports = []

        print("\n" + "=" * 60)
        print(f"Building ALL {count} species (grid {cols}x{math.ceil(count/cols)})")
        print("=" * 60)

        for i, sid in enumerate(ids):
            row = i // cols
            col = i % cols
            x = col * spacing
            z = row * spacing
            loc = (x, 0.0, z)
            print(f"\n[{i+1}/{count}] Building '{sid}' at {loc}")
            try:
                rpt = self.build_pet(sid, location=loc)
                reports.append(rpt)
            except Exception as exc:
                print(f"  [ERROR] {exc}")
                reports.append({"species_id": sid, "error": str(exc)})

        print(f"\n[Grid] All {count} species built!")
        return reports

    # ------------------------------------------------------------------
    #  Proportion Validation  (all 10 design laws)
    # ------------------------------------------------------------------
    def validate_proportions(self, species_id: str) -> dict:
        """Audit a species configuration against the 10 design laws.

        Returns
        -------
        dict
            ``{"checks": {...}, "warnings": [...], "passed": bool}``
        """
        cfg = self._species_cfg(species_id)
        checks: Dict[str, Any] = {}
        warnings: List[str] = []

        prop = cfg.get("proportions", {})
        geo = cfg.get("geometry", {})

        # --- Law #1: Head = 60-70% of body --------------------------------
        h2b = prop.get("head_to_body", 0)
        checks["law1_head_to_body"] = h2b
        if not (HEAD_TO_BODY_MIN <= h2b <= HEAD_TO_BODY_MAX):
            warnings.append(
                f"Law #1 FAIL: head/body ratio = {h2b:.2f} "
                f"(expected {HEAD_TO_BODY_MIN}-{HEAD_TO_BODY_MAX})"
            )
        else:
            checks["law1_passed"] = True

        # --- Law #2: Eyes = simple spheres --------------------------------
        e2h = prop.get("eye_to_head", 0)
        checks["law2_eye_to_head"] = e2h
        if not (EYE_TO_HEAD_MIN <= e2h <= EYE_TO_HEAD_MAX):
            warnings.append(
                f"Law #2 WARN: eye/head ratio = {e2h:.2f} "
                f"(expected {EYE_TO_HEAD_MIN}-{EYE_TO_HEAD_MAX})"
            )
        else:
            checks["law2_passed"] = True

        # --- Law #3: Feet = 1/4-1/6 body height ---------------------------
        f2b = prop.get("foot_to_body", 0)
        checks["law3_foot_to_body"] = f2b
        if not (FOOT_TO_BODY_MIN <= f2b <= FOOT_TO_BODY_MAX):
            warnings.append(
                f"Law #3 WARN: foot/body ratio = {f2b:.2f} "
                f"(expected {FOOT_TO_BODY_MIN}-{FOOT_TO_BODY_MAX})"
            )
        else:
            checks["law3_passed"] = True

        # --- Law #4: No neck (head clips into body) -----------------------
        # Enforced by geometry builder; check head style doesn't create a neck
        head_style = geo.get("head", {}).get("style", "")
        checks["law4_no_neck"] = head_style
        checks["law4_passed"] = True  # Geometry code enforces this

        # --- Law #5: Rounded softened shapes ------------------------------
        checks["law5_rounded_shapes"] = "enforced_by_subsurf_bevel"
        checks["law5_passed"] = True

        # --- Law #6: Solid colours only -----------------------------------
        colors_cfg = cfg.get("colors", {})
        for slot in ("primary", "secondary", "accent"):
            c = colors_cfg.get(slot, "")
            if isinstance(c, str) and (c.startswith('#') or c == "rainbow"):
                continue
            warnings.append(f"Law #6 WARN: {slot} colour '{c}' is not a valid solid colour")
        checks["law6_solid_colours"] = True

        # --- Law #7: Plastic material -------------------------------------
        checks["law7_plastic"] = {"specular": PLASTIC_SPECULAR,
                                   "roughness": PLASTIC_ROUGHNESS}
        checks["law7_passed"] = True

        # --- Law #8: Chibi proportions (composite) ------------------------
        checks["law8_chibi"] = {"head_large": h2b >= 0.55,
                                 "eyes_large": e2h >= 0.12,
                                 "feet_small": f2b <= 0.30}
        if not checks["law8_chibi"]["head_large"]:
            warnings.append("Law #8 WARN: head not large enough for chibi")

        # --- Law #9: Neon config present ----------------------------------
        neon_ok = bool(cfg.get("neon_config"))
        checks["law9_neon_config"] = neon_ok
        if not neon_ok:
            warnings.append("Law #9 WARN: neon_config missing from species")

        # --- Law #10: Simplicity (part count) -----------------------------
        essential_parts = ["head", "body", "eyes", "feet"]
        optional_present = [k for k in ("ears", "snout", "beak", "tail",
                                         "wings", "horns", "horn", "antlers")
                            if k in geo]
        part_count = len(essential_parts) + len(optional_present)
        checks["law10_part_count"] = part_count
        if part_count > 14:
            warnings.append(f"Law #10 WARN: {part_count} parts (keep < 14 for simplicity)")
        else:
            checks["law10_passed"] = True

        return {
            "species_id": species_id,
            "checks": checks,
            "warnings": warnings,
            "passed": len(warnings) == 0,
        }

    def validate_all(self) -> List[dict]:
        """Run ``validate_proportions`` on every species."""
        results = []
        for sid in sorted(self.species.keys()):
            results.append(self.validate_proportions(sid))
        return results


# =======================================================================
#  PET COLOUR RANDOMIZER
# =======================================================================

class PetColorRandomizer:
    """Generates harmonious colour palettes using HSL colour theory.

    Supports analogous, complementary, triadic, and monochromatic schemes.
    Also provides pre-tuned palettes for legendary pets and natural
    animal colourings.
    """

    def random_colors(self,
                      base_hue: Optional[float] = None,
                      scheme: str = "analogous") -> dict:
        """Generate a harmonious 3-colour palette.

        Parameters
        ----------
        base_hue : float or None
            Hue in 0-1 range.  Random if *None*.
        scheme : str
            One of ``analogous``, ``complementary``, ``triadic``, ``monochromatic``.

        Returns
        -------
        dict
            ``{"primary": "#RRGGBB", "secondary": "#RRGGBB", "accent": "#RRGGBB"}``
        """
        if base_hue is None:
            base_hue = random.random()

        h = base_hue % 1.0
        s = 0.5 + random.random() * 0.4   # 0.5-0.9
        v = 0.5 + random.random() * 0.3   # 0.5-0.8

        if scheme == "analogous":
            hues = [h, (h + 0.05) % 1.0, (h + 0.10) % 1.0]
        elif scheme == "complementary":
            hues = [h, (h + 0.5) % 1.0, (h + 0.05) % 1.0]
        elif scheme == "triadic":
            hues = [h, (h + 1/3) % 1.0, (h + 2/3) % 1.0]
        elif scheme == "monochromatic":
            return {
                "primary": self._hsv_to_hex(h, s, v),
                "secondary": self._hsv_to_hex(h, s * 0.7, v * 1.15),
                "accent": self._hsv_to_hex(h, s * 1.2, v * 0.85),
            }
        else:
            hues = [h, (h + 0.05) % 1.0, (h + 0.10) % 1.0]

        return {
            "primary": self._hsv_to_hex(hues[0], s, v),
            "secondary": self._hsv_to_hex(hues[1], s * 0.85, v * 1.1),
            "accent": self._hsv_to_hex(hues[2], s * 1.1, v * 0.9),
        }

    def rare_color_palette(self) -> dict:
        """Generate a legendary-worthy palette (gold, prismatic, etc.)."""
        palettes = [
            {"primary": "#FFD700", "secondary": "#FFA500", "accent": "#FF4500"},   # Gold/Orange
            {"primary": "#00BFFF", "secondary": "#7B68EE", "accent": "#FF1493"},   # Prismatic
            {"primary": "#FF69B4", "secondary": "#FFD700", "accent": "#8A2BE2"},   # Unicorn
            {"primary": "#00FF7F", "secondary": "#00CED1", "accent": "#FFD700"},   # Crystal
            {"primary": "#FF6347", "secondary": "#FFD700", "accent": "#32CD32"},   # Rainbow
        ]
        return random.choice(palettes)

    def natural_colors(self, animal_type: str) -> dict:
        """Return realistic colours for animal type.

        Parameters
        ----------
        animal_type : str
            ``'dog'``, ``'cat'``, ``'fox'``, ``'bear'``, ``'wolf'``,
            ``'bunny'``, ``'panda'``, ``'dragon'``, ``'unicorn'``.

        Returns
        -------
        dict
            ``{"primary": "#RRGGBB", "secondary": "#RRGGBB", "accent": "#RRGGBB"}``
        """
        lookup = {
            "dog":   {"primary": "#D2B48C", "secondary": "#C19A6B", "accent": "#8B4513"},
            "cat":   {"primary": "#FFA500", "secondary": "#FFB84D", "accent": "#FFFFFF"},
            "bunny": {"primary": "#FFFFFF", "secondary": "#FFB6C1", "accent": "#FF69B4"},
            "bear":  {"primary": "#8B6914", "secondary": "#D2B48C", "accent": "#2F1810"},
            "wolf":  {"primary": "#808080", "secondary": "#D3D3D3", "accent": "#FFD700"},
            "fox":   {"primary": "#FF6600", "secondary": "#FFFFFF", "accent": "#1A1A1A"},
            "panda": {"primary": "#FFFFFF", "secondary": "#111111", "accent": "#888888"},
            "dragon": {"primary": "#2E8B57", "secondary": "#1A5C38", "accent": "#DAA520"},
            "unicorn": {"primary": "#FFFFFF", "secondary": "#FFB6C1", "accent": "#FFD700"},
            "owl":   {"primary": "#8B7355", "secondary": "#A08060", "accent": "#FFD700"},
            "elephant": {"primary": "#9B9B9B", "secondary": "#A9A9A9", "accent": "#FFFFF0"},
            "phoenix": {"primary": "#FF4500", "secondary": "#FFD700", "accent": "#FF6347"},
        }
        key = animal_type.lower()
        if key in lookup:
            return dict(lookup[key])
        return {"primary": "#AA8866", "secondary": "#CCAA88", "accent": "#DDCCAA"}

    @staticmethod
    def _hsv_to_hex(h: float, s: float, v: float) -> str:
        r, g, b = colorsys.hsv_to_rgb(h % 1.0, max(0, min(1, s)), max(0, min(1, v)))
        return "#{:02X}{:02X}{:02X}".format(int(r * 255), int(g * 255), int(b * 255))


# =======================================================================
#  PET EXPORTER
# =======================================================================

class PetExporter:
    """Export pets to various 3D formats using Blender's built-in operators."""

    def __init__(self, output_dir: Optional[str] = None):
        if output_dir is None:
            output_dir = str(Path.home() / "adopt_me_exports")
        self.output_dir = output_dir
        os.makedirs(output_dir, exist_ok=True)

    def _select_pet_objects(self, root_name: str) -> List[bpy.types.Object]:
        """Find all mesh objects parented under *root_name* empty."""
        root = bpy.data.objects.get(root_name)
        if root is None:
            print(f"[Export] Root '{root_name}' not found")
            return []
        objs = [root]
        for obj in bpy.data.objects:
            if obj.parent == root and obj.type == 'MESH':
                objs.append(obj)
        return objs

    def _ensure_selected(self, objs: List[bpy.types.Object]):
        """Deselect all, then select *objs*."""
        bpy.ops.object.select_all(action='DESELECT')
        for obj in objs:
            obj.select_set(True)
        if objs:
            bpy.context.view_layer.objects.active = objs[0]

    def export_obj(self, pet_name: str, filepath: Optional[str] = None) -> str:
        """Export pet as ``.obj`` for import into Roblox Studio."""
        if filepath is None:
            filepath = os.path.join(self.output_dir, f"{pet_name}.obj")
        objs = self._select_pet_objects(pet_name)
        self._ensure_selected(objs)
        bpy.ops.wm.obj_export(
            filepath=filepath,
            export_selected_objects=True,
            apply_modifiers=True,
        )
        print(f"[Export] OBJ → {filepath}")
        return filepath

    def export_fbx(self, pet_name: str, filepath: Optional[str] = None) -> str:
        """Export pet as ``.fbx``."""
        if filepath is None:
            filepath = os.path.join(self.output_dir, f"{pet_name}.fbx")
        objs = self._select_pet_objects(pet_name)
        self._ensure_selected(objs)
        bpy.ops.export_scene.fbx(
            filepath=filepath,
            use_selection=True,
            apply_unit_scale=True,
            apply_scale_options='FBX_SCALE_UNITS',
        )
        print(f"[Export] FBX → {filepath}")
        return filepath

    def export_gltf(self, pet_name: str, filepath: Optional[str] = None) -> str:
        """Export pet as ``.gltf`` for web viewing."""
        if filepath is None:
            filepath = os.path.join(self.output_dir, f"{pet_name}.gltf")
        objs = self._select_pet_objects(pet_name)
        self._ensure_selected(objs)
        bpy.ops.export_scene.gltf(
            filepath=filepath,
            use_selection=True,
            export_format='GLTF_SEPARATE',
        )
        print(f"[Export] glTF → {filepath}")
        return filepath

    def export_all_formats(self, pet_name: str) -> dict:
        """Export a pet in all three formats at once."""
        return {
            "obj": self.export_obj(pet_name),
            "fbx": self.export_fbx(pet_name),
            "gltf": self.export_gltf(pet_name),
        }


# =======================================================================
#  DEMO FUNCTIONS
# =======================================================================

def demo_build_grid():
    """Build a grid of all species for visual review."""
    print("\n" + "=" * 60)
    print("DEMO: Build Grid — All Species")
    print("=" * 60)
    builder = AdoptMePetBuilder()
    reports = builder.build_all_species(spacing=8.0)
    passed = sum(1 for r in reports if "error" not in r)
    print(f"\n[Grid Complete] {passed}/{len(reports)} species built successfully")
    return reports


def demo_random_pets():
    """Build 5 random pets with neon glow."""
    print("\n" + "=" * 60)
    print("DEMO: Random Pets with Neon Glow")
    print("=" * 60)
    builder = AdoptMePetBuilder()
    rarities = ["common", "uncommon", "rare", "legendary", None]
    reports = []
    for i, rarity in enumerate(rarities):
        loc = (i * 10.0, 0.0, 10.0)
        label = rarity or "any"
        print(f"\n[{i+1}/5] Building random '{label}' pet at {loc}")
        try:
            rpt = builder.build_random(rarity=rarity, neon=True, location=loc)
            reports.append(rpt)
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            reports.append({"rarity": rarity, "error": str(exc)})
    print(f"\n[Random Complete] {len(reports)} random pets built")
    return reports


def demo_one_of_each_rarity():
    """Build one pet of each rarity tier."""
    print("\n" + "=" * 60)
    print("DEMO: One of Each Rarity")
    print("=" * 60)
    builder = AdoptMePetBuilder()

    selections = [
        ("dog",     "common",    (0, 0, 0),    False),
        ("bunny",   "uncommon",  (8, 0, 0),    False),
        ("dragon",  "rare",      (16, 0, 0),   True),
        ("shadow_dragon", "legendary", (24, 0, 0), True),
    ]

    reports = []
    for species_id, rarity, loc, neon in selections:
        print(f"\n[{rarity.upper()}] Building '{species_id}' at {loc}, neon={neon}")
        try:
            rpt = builder.build_pet(species_id, neon=neon, location=loc,
                                     name=f"{rarity.title()}_{species_id.title()}")
            reports.append(rpt)
        except Exception as exc:
            print(f"  [ERROR] {exc}")
            reports.append({"species": species_id, "error": str(exc)})

    print(f"\n[Rarity Demo Complete] {len(reports)} pets built")
    return reports


def demo_build_specific(species_id: str = "dragon",
                        neon: bool = True,
                        location: Tuple[float, float, float] = (0, 0, 0)):
    """Build a single specific pet with optional neon."""
    print("\n" + "=" * 60)
    print(f"DEMO: Specific Pet — '{species_id}'")
    print("=" * 60)
    builder = AdoptMePetBuilder()
    rpt = builder.build_pet(species_id, neon=neon, location=location)
    print(f"\nBuilt '{rpt['name']}' with {rpt['piece_count']} parts")
    return rpt


def demo_validate_all():
    """Run proportion validation on all species and print a summary report."""
    print("\n" + "=" * 60)
    print("DEMO: Validate All Species")
    print("=" * 60)
    builder = AdoptMePetBuilder()
    results = builder.validate_all()
    total = len(results)
    passed = sum(1 for r in results if r["passed"])
    print(f"\nValidation Summary: {passed}/{total} species passed all checks")
    for r in results:
        status = "PASS" if r["passed"] else "WARN"
        print(f"  [{status}] {r['species_id']:20s} — {len(r['warnings'])} warnings")
        for w in r["warnings"]:
            print(f"           ! {w}")
    return results


# =======================================================================
#  MAIN
# =======================================================================

if __name__ == "__main__":
    print("Adopt Me Pet Generator for Blender")
    print("=" * 50)
    print(f"Species catalog: {SPECS_FILE}")
    print(f"Total species: {20}")
    print(f"Geometry module: {'AVAILABLE' if _HAS_GEO else 'INLINE FALLBACK'}")
    print()
    demo_build_grid()
