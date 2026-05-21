"""
am_geometry.py -- Adopt Me Style Geometry Library for Blender
===============================================================
Complete geometric primitive toolkit for building chibi pet models in the
style of Adopt Me (Roblox).  All meshes are built with *bmesh* for clean
topology and full programmatic control.

Design Rules (NEVER violate)
----------------------------
- Head = 60-70 % of body size (chibi proportions)
- Eyes = single-colour perfect spheres, NO pupils, 15-20 % of head
- Feet = perfect hemispheres (flat side down), 1/4-1/6 body height, floating
- NO neck -- head clips directly into body
- All shapes = rounded, softened -- never sharp edges
- Solid flat colours only -- no textures, no gradients
- Plastic material: specular 0.3, roughness 0.6

Usage
-----
Run inside Blender's Scripting editor::

    import am_geometry as am
    am.clear_scene()
    am.demo_all_primitives()

Or call individual functions::

    head = am.make_chibi_head("PandaHead", style="round", size=1.0,
                              color_hex="#333333")

Author  : GeometrySmith
Version : 1.0.0
"""

from __future__ import annotations

import math
import random
from typing import List, Tuple, Optional

import bpy
import bmesh
import mathutils
from mathutils import Vector, Matrix

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

PLASTIC_SPECULAR: float = 0.3
PLASTIC_ROUGHNESS: float = 0.6
PLASTIC_DIFFUSE: float = 0.7

# Chibi proportion constants
HEAD_TO_BODY_RATIO: float = 0.65
EYE_TO_HEAD_RATIO: float = 0.18
FOOT_TO_BODY_RATIO: float = 0.20

MERGE_THRESHOLD: float = 0.0001


# ============================================================================
# INTERNAL HELPERS
# ============================================================================

def _hex_to_rgb(color_hex: str) -> Tuple[float, float, float]:
    """Convert '#RRGGBB' or 'RRGGBB' to normalised RGB tuple."""
    h = color_hex.lstrip("#")
    if len(h) != 6:
        raise ValueError(f"Invalid hex colour: {color_hex}")
    r = int(h[0:2], 16) / 255.0
    g = int(h[2:4], 16) / 255.0
    b = int(h[4:6], 16) / 255.0
    return (r, g, b)


def _smooth_bm(bm: bmesh.types.BMesh) -> None:
    """Enable smooth shading on all faces in a bmesh."""
    for face in bm.faces:
        face.smooth = True


def _create_mesh_object(
    name: str,
    bm: bmesh.types.BMesh,
    location: Tuple[float, float, float] = (0, 0, 0),
    rotation: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Finish a bmesh, write it to a new Mesh + Object, and link it."""
    mesh = bpy.data.meshes.new(name)
    bm.to_mesh(mesh)
    bm.free()
    obj = bpy.data.objects.new(name, mesh)
    obj.location = location
    obj.rotation_euler = rotation
    bpy.context.collection.objects.link(obj)
    # Shade smooth
    mesh.use_auto_smooth = True
    mesh.auto_smooth_angle = math.radians(30)
    for poly in mesh.polygons:
        poly.use_smooth = True
    return obj


def _apply_material(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    """Assign a material to an object."""
    if mat.name not in obj.data.materials:
        obj.data.materials.append(mat)


def _merge_by_distance(
    bm: bmesh.types.BMesh, dist: float = MERGE_THRESHOLD
) -> None:
    """Remove doubles / merge by distance inside bmesh."""
    bmesh.ops.remove_doubles(bm, verts=list(bm.verts), dist=dist)


def _recalc_normals(bm: bmesh.types.BMesh) -> None:
    """Recalculate face normals to be consistently outward."""
    bmesh.ops.recalc_face_normals(bm, faces=list(bm.faces))


def _make_rounded_box(
    bm: bmesh.types.BMesh,
    width: float,
    height: float,
    depth: float,
    radius: float,
    segs: int = 4,
) -> None:
    """Create a rounded box inside an existing bmesh.

    Uses bmesh.ops.create_cube then subdivide + proportional displacement
    to round the corners.
    """
    bmesh.ops.create_cube(bm, size=1.0)
    # Scale to desired dimensions
    for v in bm.verts:
        v.co.x *= width
        v.co.y *= depth
        v.co.z *= height
    # Subdivide edges
    for _ in range(segs):
        bmesh.ops.subdivide_edges(
            bm,
            edges=list(bm.edges),
            cuts=1,
            use_grid_fill=True,
        )
    # Round: push vertices toward centre
    for v in bm.verts:
        nx = abs(v.co.x) / (width * 0.5 + 0.0001)
        ny = abs(v.co.y) / (depth * 0.5 + 0.0001)
        nz = abs(v.co.z) / (height * 0.5 + 0.0001)
        factor = max(0.0, (nx + ny + nz - 2.0))
        factor = min(factor, 1.0)
        disp = factor * radius
        d = Vector((-v.co.x, -v.co.y, -v.co.z))
        if d.length > 0.0001:
            d.normalize()
            v.co += d * disp


# ============================================================================
# MATERIALS
# ============================================================================

def make_material(
    name: str,
    color_hex: str,
    neon: bool = False,
    glow_intensity: float = 0.5,
) -> bpy.types.Material:
    """Create a plastic-like material for pet parts.

    Standard (neon=False)
        Diffuse weight 0.7, specular 0.3, roughness 0.6 -- toy plastic.

    Neon (neon=True)
        Adds Emission mixed into Principled BSDF for glowing pets.

    Parameters
    ----------
    name : str
        Material datablock name.
    color_hex : str
        Base colour '#RRGGBB'.
    neon : bool
        Add emissive glow.
    glow_intensity : float
        Emission strength when neon=True.

    Returns
    -------
    bpy.types.Material
    """
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    out_node = nodes.new(type="ShaderNodeOutputMaterial")
    out_node.location = (400, 0)

    bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
    bsdf.location = (0, 0)
    r, g, b = _hex_to_rgb(color_hex)
    bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
    bsdf.inputs["Roughness"].default_value = PLASTIC_ROUGHNESS
    # Blender 4.x uses "Specular IOR Level" for specular
    if "Specular IOR Level" in bsdf.inputs:
        bsdf.inputs["Specular IOR Level"].default_value = PLASTIC_SPECULAR
    elif "Specular" in bsdf.inputs:
        bsdf.inputs["Specular"].default_value = PLASTIC_SPECULAR

    if neon:
        emit = nodes.new(type="ShaderNodeEmission")
        emit.location = (0, 200)
        emit.inputs["Color"].default_value = (r, g, b, 1.0)
        emit.inputs["Strength"].default_value = glow_intensity * 4.0

        add = nodes.new(type="ShaderNodeAddShader")
        add.location = (200, 100)

        links.new(bsdf.outputs["BSDF"], add.inputs[0])
        links.new(emit.outputs["Emission"], add.inputs[1])
        links.new(add.outputs["Shader"], out_node.inputs["Surface"])
    else:
        links.new(bsdf.outputs["BSDF"], out_node.inputs["Surface"])

    return mat


def make_neon_glow(
    name: str,
    parent_obj: bpy.types.Object,
    glow_color: str = "#00FF00",
    intensity: float = 0.5,
) -> bpy.types.Object:
    """Add a neon glow shell around an existing object.

    Creates a slightly-enlarged duplicate with an emissive material.

    Parameters
    ----------
    name : str
        Name for the glow shell.
    parent_obj : bpy.types.Object
        The mesh to receive glow.
    glow_color : str
        Hex colour of the glow.
    intensity : float
        Emission multiplier.

    Returns
    -------
    bpy.types.Object
        The glow shell object.
    """
    glow_obj = parent_obj.copy()
    glow_obj.name = f"{parent_obj.name}_neon"
    glow_obj.data = parent_obj.data.copy()
    glow_obj.scale = (
        parent_obj.scale[0] * 1.05,
        parent_obj.scale[1] * 1.05,
        parent_obj.scale[2] * 1.05,
    )
    bpy.context.collection.objects.link(glow_obj)

    mat = make_material(f"{name}_neon_mat", glow_color, neon=True,
                        glow_intensity=intensity)
    glow_obj.data.materials.clear()
    glow_obj.data.materials.append(mat)
    return glow_obj


# ============================================================================
# PRIMITIVES
# ============================================================================

def make_half_sphere(
    name: str,
    radius: float = 0.25,
    segments: int = 12,
    rings: int = 6,
    color_hex: str = "#888888",
    location: Tuple[float, float, float] = (0, 0, 0),
    rotation: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Half-sphere (hemisphere) with flat cap on the bottom.

    This is the **foot** primitive for Adopt Me pets.  The hemisphere is a
    sphere cut in half horizontally; the flat face points down (negative Z).

    Parameters
    ----------
    name : str
        Object name.
    radius : float
        Hemisphere radius.
    segments : int
        Meridian segments (longitude).
    rings : int
        Latitude rings in dome.
    color_hex : str
        Plastic colour.
    location : tuple
        World-space position.
    rotation : tuple
        Euler rotation in radians.

    Returns
    -------
    bpy.types.Object
    """
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=segments,
        v_segments=rings + 2,
        radius=radius,
    )
    # Remove bottom hemisphere: verts with Z < -epsilon
    to_delete = [v for v in bm.verts if v.co.z < -0.0001]
    bmesh.ops.delete(bm, geom=to_delete, context="VERTS")
    # Fill the open boundary
    boundary_edges = [e for e in bm.edges if e.is_boundary]
    if boundary_edges:
        bmesh.ops.holes_fill(bm, edges=boundary_edges)
    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    obj = _create_mesh_object(name, bm, location, rotation)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_sphere_eye(
    name: str,
    radius: float = 0.12,
    color_hex: str = "#000000",
    location: Tuple[float, float, float] = (0, 0, 0),
    highlight: bool = True,
) -> bpy.types.Object:
    """Perfect sphere eye -- single flat colour, optional kawaii highlight.

    The highlight is a tiny white sphere parented to the eye, offset
    toward the upper-left.

    Parameters
    ----------
    name : str
        Object name.
    radius : float
        Eye radius (15-20 % of head diameter).
    color_hex : str
        Eye colour.
    location : tuple
        World-space position.
    highlight : bool
        Add small white highlight dot.

    Returns
    -------
    bpy.types.Object
        The eye sphere object.
    """
    bm = bmesh.new()
    bmesh.ops.create_uvsphere(
        bm,
        u_segments=10,
        v_segments=8,
        radius=radius,
    )
    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    obj = _create_mesh_object(name, bm, location)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)

    if highlight:
        hl_radius = radius * 0.25
        hl_loc = (
            location[0] - radius * 0.35,
            location[1] + radius * 0.45,
            location[2] + radius * 0.40,
        )
        hl_bm = bmesh.new()
        bmesh.ops.create_uvsphere(
            hl_bm,
            u_segments=6,
            v_segments=4,
            radius=hl_radius,
        )
        _merge_by_distance(hl_bm)
        _recalc_normals(hl_bm)
        _smooth_bm(hl_bm)
        hl_obj = _create_mesh_object(f"{name}_highlight", hl_bm, hl_loc)
        hl_mat = make_material(f"{name}_hl_mat", "#FFFFFF")
        _apply_material(hl_obj, hl_mat)
        hl_obj.parent = obj

    return obj


def make_chibi_head(
    name: str,
    style: str = "round",
    size: float = 1.0,
    color_hex: str = "#D2B48C",
    location: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Chibi head in three styles.

    - ``round``: UV sphere, slightly flattened on Y for egg-shaped face.
    - ``square``: Rounded cube (bevelled box).
    - ``triangular``: Cone with rounded tip.

    Parameters
    ----------
    name : str
        Object name.
    style : {"round", "square", "triangular"}
        Head shape style.
    size : float
        Scale multiplier.
    color_hex : str
        Fur/skin colour.
    location : tuple
        World-space position.

    Returns
    -------
    bpy.types.Object
    """
    bm = bmesh.new()
    base_size = 0.5

    if style == "round":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=14,
            v_segments=10,
            radius=base_size,
        )
        for v in bm.verts:
            v.co.y *= 0.85  # flatten front-to-back

    elif style == "square":
        _make_rounded_box(
            bm,
            width=base_size * 1.6,
            height=base_size * 1.4,
            depth=base_size * 1.4,
            radius=base_size * 0.35,
            segs=2,
        )

    elif style == "triangular":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=12,
            radius1=base_size * 0.9,
            radius2=0.0,
            depth=base_size * 1.8,
            calc_uvs=True,
        )
        for _ in range(2):
            bmesh.ops.subdivide_edges(
                bm,
                edges=list(bm.edges),
                cuts=1,
                use_grid_fill=True,
            )
        for v in bm.verts:
            d = math.sqrt(v.co.x ** 2 + v.co.y ** 2)
            if d > base_size * 0.3:
                v.co *= 1.0 + (d / base_size) * 0.05

    else:
        raise ValueError(f"Unknown head style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    obj = _create_mesh_object(name, bm, location)
    obj.scale = (size, size, size)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_chibi_body(
    name: str,
    style: str = "chubby",
    size: float = 1.0,
    color_hex: str = "#D2B48C",
    location: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Chibi body in three styles.

    - ``chubby``: Wide rounded capsule (fat pear torso).
    - ``slim``: Tall narrow rounded box.
    - ``long``: Elongated rounded capsule (dachshund-like).

    Parameters
    ----------
    name : str
        Object name.
    style : {"chubby", "slim", "long"}
        Body shape style.
    size : float
        Scale multiplier.
    color_hex : str
        Fur/skin colour.
    location : tuple
        World-space position.

    Returns
    -------
    bpy.types.Object
    """
    bm = bmesh.new()
    base_w, base_h, base_d = 0.4, 0.5, 0.35

    if style == "chubby":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=14,
            v_segments=10,
            radius=base_w,
        )
        for v in bm.verts:
            v.co.x *= 1.3
            v.co.z *= 0.7
            v.co.y *= 0.9

    elif style == "slim":
        _make_rounded_box(
            bm,
            width=base_w * 1.0,
            height=base_h * 1.6,
            depth=base_d * 0.8,
            radius=base_w * 0.25,
            segs=2,
        )

    elif style == "long":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=14,
            v_segments=8,
            radius=base_d,
        )
        for v in bm.verts:
            v.co.x *= 2.0
            v.co.z *= 0.6
            v.co.y *= 0.8

    else:
        raise ValueError(f"Unknown body style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    obj = _create_mesh_object(name, bm, location)
    obj.scale = (size, size, size)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_ears(
    name: str,
    style: str = "floppy",
    color_hex: str = "#D2B48C",
    location: Tuple[float, float, float] = (0, 0, 0),
    side: str = "left",
) -> bpy.types.Object:
    """Ears in five styles.

    - ``floppy``: Thin elongated plane, angled down (puppy).
    - ``pointy``: Cone shape, angled up (cat/fox).
    - ``round``: Small sphere, sticking out (bear/mouse).
    - ``long``: Long thin plane, straight up (rabbit).
    - ``feathered``: Flat plane with feather-like segments (bird/owl).

    Parameters
    ----------
    name : str
        Object name.
    style : {"floppy", "pointy", "round", "long", "feathered"}
        Ear shape style.
    color_hex : str
        Ear colour.
    location : tuple
        Attachment point.
    side : {"left", "right"}
        Mirror side.

    Returns
    -------
    bpy.types.Object
    """
    side_mult = -1.0 if side == "right" else 1.0
    bm = bmesh.new()

    if style == "floppy":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.06
            v.co.y *= 0.25
            v.co.z *= 0.50
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=3, use_grid_fill=True
        )
        for v in bm.verts:
            if v.co.z < -0.1:
                v.co.x += side_mult * 0.08 * abs(v.co.z)
        rot = (math.radians(15), 0, math.radians(20 * side_mult))

    elif style == "pointy":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=8,
            radius1=0.12,
            radius2=0.0,
            depth=0.5,
            calc_uvs=True,
        )
        rot = (math.radians(-30), 0, math.radians(25 * side_mult))

    elif style == "round":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=8,
            v_segments=6,
            radius=0.12,
        )
        rot = (0, 0, 0)

    elif style == "long":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.08
            v.co.y *= 0.10
            v.co.z *= 0.70
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=2, use_grid_fill=True
        )
        for v in bm.verts:
            v.co.x *= 0.5 + 0.5 * (1.0 - abs(v.co.z) / 0.7)
        rot = (0, 0, math.radians(10 * side_mult))

    elif style == "feathered":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.06
            v.co.y *= 0.30
            v.co.z *= 0.12
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=2, use_grid_fill=True
        )
        for v in bm.verts:
            v.co.z += 0.03 * math.sin(v.co.y * 15)
        rot = (math.radians(-10), 0, math.radians(15 * side_mult))

    else:
        raise ValueError(f"Unknown ear style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    loc = (
        location[0] + side_mult * 0.25,
        location[1],
        location[2] + 0.15,
    )
    obj = _create_mesh_object(name, bm, loc, rot)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj



def make_tail(
    name: str,
    style: str = "puff",
    color_hex: str = "#D2B48C",
    location: Tuple[float, float, float] = (0, 0, 0),
    length: float = 1.0,
) -> bpy.types.Object:
    """Tail in five styles.

    - ``puff``: Single sphere (bunny/hamster).
    - ``curved``: Tube bent upward (cat/dog).
    - ``long``: Elongated tapered capsule (fox/wolf).
    - ``fluffy``: Cluster of spheres (Pomeranian/squirrel).
    - ``spiked``: Cone pointing up (dinosaur/dragon).

    Parameters
    ----------
    name : str
        Object name.
    style : {"puff", "curved", "long", "fluffy", "spiked"}
        Tail shape style.
    color_hex : str
        Tail colour.
    location : tuple
        Rear attachment point.
    length : float
        Length multiplier.

    Returns
    -------
    bpy.types.Object
    """
    bm = bmesh.new()

    if style == "puff":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=10,
            v_segments=8,
            radius=0.12 * length,
        )
        rot = (math.radians(90), 0, 0)

    elif style == "curved":
        # Sphere stretched and bent upward
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=10,
            v_segments=8,
            radius=0.07 * length,
        )
        for v in bm.verts:
            v.co.z = v.co.z * 2.5 * length - 0.1
            v.co.x -= v.co.z * v.co.z * 0.3  # bend
        rot = (math.radians(45), 0, 0)

    elif style == "long":
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=10,
            v_segments=8,
            radius=0.08,
        )
        for v in bm.verts:
            v.co.z *= 2.5 * length
            if v.co.z > 0:
                taper = 1.0 - (v.co.z / (0.2 + 0.3 * length)) * 0.5
                v.co.x *= max(taper, 0.3)
                v.co.y *= max(taper, 0.3)
        rot = (math.radians(80), 0, 0)

    elif style == "fluffy":
        # Single sphere with lumpy distortion for fluffy look
        bmesh.ops.create_uvsphere(
            bm,
            u_segments=10,
            v_segments=8,
            radius=0.13 * length,
        )
        for v in bm.verts:
            noise = math.sin(v.co.x * 12) * math.sin(v.co.y * 12) * 0.02
            v.co *= 1.0 + noise
        rot = (math.radians(90), 0, 0)

    elif style == "spiked":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=8,
            radius1=0.06 * length,
            radius2=0.0,
            depth=0.4 * length,
            calc_uvs=True,
        )
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=1, use_grid_fill=True
        )
        rot = (math.radians(-60), 0, 0)

    else:
        raise ValueError(f"Unknown tail style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    loc = (location[0], location[1] - 0.15, location[2] + 0.05)
    obj = _create_mesh_object(name, bm, loc, rot)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_snout(
    name: str,
    style: str = "short",
    color_hex: str = "#8B4513",
    location: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Snout / muzzle in three styles.

    - ``short``: Small rounded box (cat/bear).
    - ``long``: Elongated rounded box (dog).
    - ``broad``: Wide flat box (bear/panda).

    Parameters
    ----------
    name : str
        Object name.
    style : {"short", "long", "broad"}
        Snout shape style.
    color_hex : str
        Snout colour.
    location : tuple
        Position on the front of the face.

    Returns
    -------
    bpy.types.Object
    """
    bm = bmesh.new()

    if style == "short":
        _make_rounded_box(
            bm,
            width=0.22,
            height=0.16,
            depth=0.14,
            radius=0.05,
            segs=1,
        )

    elif style == "long":
        _make_rounded_box(
            bm,
            width=0.18,
            height=0.30,
            depth=0.16,
            radius=0.06,
            segs=1,
        )

    elif style == "broad":
        _make_rounded_box(
            bm,
            width=0.35,
            height=0.18,
            depth=0.12,
            radius=0.04,
            segs=1,
        )

    else:
        raise ValueError(f"Unknown snout style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    obj = _create_mesh_object(name, bm, location)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_wings(
    name: str,
    style: str = "small",
    color_hex: str = "#CC3333",
    location: Tuple[float, float, float] = (0, 0, 0),
    side: str = "left",
) -> bpy.types.Object:
    """Wings in three styles.

    - ``small``: Small pointed plane (bird-like).
    - ``large``: Large curved plane (dragon/bat).
    - ``butterfly``: Rounded butterfly shape.

    Parameters
    ----------
    name : str
        Object name.
    style : {"small", "large", "butterfly"}
        Wing shape style.
    color_hex : str
        Wing colour.
    location : tuple
        Attachment point on the body.
    side : {"left", "right"}
        Mirror side.

    Returns
    -------
    bpy.types.Object
    """
    side_mult = -1.0 if side == "right" else 1.0
    bm = bmesh.new()

    if style == "small":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.02
            v.co.y *= 0.35
            v.co.z *= 0.25
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=2, use_grid_fill=True
        )
        for v in bm.verts:
            factor = max(0, v.co.y)
            v.co.z *= 1.0 - factor * 1.2

    elif style == "large":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.02
            v.co.y *= 0.70
            v.co.z *= 0.40
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=3, use_grid_fill=True
        )
        for v in bm.verts:
            y_norm = (v.co.y + 0.35) / 0.7
            v.co.z += y_norm * y_norm * 0.25
            taper = 1.0 - y_norm * 0.6
            v.co.z *= taper

    elif style == "butterfly":
        bmesh.ops.create_cube(bm, size=1.0)
        for v in bm.verts:
            v.co.x *= 0.02
            v.co.y *= 0.55
            v.co.z *= 0.50
        bmesh.ops.subdivide_edges(
            bm, edges=list(bm.edges), cuts=3, use_grid_fill=True
        )
        for v in bm.verts:
            y = v.co.y
            z = v.co.z
            dist = math.sqrt(y * y * 1.5 + z * z)
            if dist > 0.3:
                scale = 0.3 / max(dist, 0.001)
                v.co.y *= scale
                v.co.z *= scale
            v.co.x += 0.01 * math.sin(y * 12) * math.cos(z * 8)

    else:
        raise ValueError(f"Unknown wing style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    loc = (
        location[0] + side_mult * 0.15,
        location[1] - 0.05,
        location[2] + 0.25,
    )
    rot = (
        math.radians(10),
        math.radians(-10 * side_mult),
        math.radians(20 * side_mult),
    )
    obj = _create_mesh_object(name, bm, loc, rot)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


def make_horns(
    name: str,
    style: str = "simple",
    color_hex: str = "#CC9900",
    location: Tuple[float, float, float] = (0, 0, 0),
    side: str = "left",
) -> bpy.types.Object:
    """Horns in three styles.

    - ``simple``: Single cone pointing up (devil/bull).
    - ``unicorn``: Single long spiral cone (centred).
    - ``antlers``: Branching structure (deer/reindeer).

    Parameters
    ----------
    name : str
        Object name.
    style : {"simple", "unicorn", "antlers"}
        Horn shape style.
    color_hex : str
        Horn colour.
    location : tuple
        Top-of-head attachment.
    side : {"left", "right", "center"}
        Which side.

    Returns
    -------
    bpy.types.Object
    """
    if style == "unicorn":
        side = "center"

    side_mult = 0.0 if side == "center" else (-1.0 if side == "right" else 1.0)
    bm = bmesh.new()

    if style == "simple":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=8,
            radius1=0.06,
            radius2=0.02,
            depth=0.35,
            calc_uvs=True,
        )
        rot = (
            math.radians(-15),
            0,
            math.radians(20 * side_mult),
        )

    elif style == "unicorn":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=10,
            radius1=0.05,
            radius2=0.01,
            depth=0.70,
            calc_uvs=True,
        )
        for v in bm.verts:
            z_factor = (v.co.z + 0.35) / 0.7
            twist = z_factor * math.radians(180)
            x = v.co.x
            y = v.co.y
            v.co.x = x * math.cos(twist) - y * math.sin(twist)
            v.co.y = x * math.sin(twist) + y * math.cos(twist)
        rot = (math.radians(-5), 0, 0)

    elif style == "antlers":
        bmesh.ops.create_cone(
            bm,
            cap_ends=True,
            cap_tris=False,
            segments=6,
            radius1=0.04,
            radius2=0.015,
            depth=0.35,
            calc_uvs=True,
        )
        for v in bm.verts:
            if v.co.z > 0:
                v.co.x += 0.04 * math.sin(v.co.z * 12)
        rot = (
            math.radians(-10),
            0,
            math.radians(10 * side_mult) if side_mult != 0 else 0,
        )

    else:
        raise ValueError(f"Unknown horn style: {style}")

    _merge_by_distance(bm)
    _recalc_normals(bm)
    _smooth_bm(bm)

    loc = (
        location[0] + side_mult * 0.15,
        location[1],
        location[2] + 0.30,
    )
    obj = _create_mesh_object(name, bm, loc, rot)
    mat = make_material(f"{name}_mat", color_hex)
    _apply_material(obj, mat)
    return obj


# ============================================================================
# SCENE UTILITIES
# ============================================================================

def make_collection(name: str) -> bpy.types.Collection:
    """Create a new Blender collection, or return existing one.

    Parameters
    ----------
    name : str
        Collection name.

    Returns
    -------
    bpy.types.Collection
    """
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def clear_scene() -> None:
    """Remove every mesh object and clean up unused data-blocks.

    Uses the low-level API (not bpy.ops) so it is safe to call from
    background/batch scripts.
    """
    # Remove mesh objects via the data API
    scene = bpy.context.scene
    for obj in list(scene.objects):
        if obj.type == "MESH":
            # Unlink from all collections
            for col in obj.users_collection:
                col.objects.unlink(obj)
            # Remove from data
            mesh_data = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            # Remove the mesh if nobody else uses it
            if mesh_data.users == 0:
                bpy.data.meshes.remove(mesh_data)

    # Purge unused materials
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def parent_to_empty(
    name: str,
    objects: List[bpy.types.Object],
    location: Tuple[float, float, float] = (0, 0, 0),
) -> bpy.types.Object:
    """Create an Empty and parent a list of objects to it.

    Parameters
    ----------
    name : str
        Empty object name.
    objects : list
        Objects to parent.
    location : tuple
        World-space position for the empty.

    Returns
    -------
    bpy.types.Object
        The newly created empty.
    """
    empty = bpy.data.objects.new(name, None)
    empty.empty_display_type = "PLAIN_AXES"
    empty.empty_display_size = 0.5
    empty.location = location
    bpy.context.collection.objects.link(empty)
    for obj in objects:
        obj.parent = empty
    return empty


def place_pet_in_scene(
    pet_name: str,
    location: Tuple[float, float, float] = (0, 0, 0),
    rotation: Tuple[float, float, float] = (0, 0, 0),
) -> None:
    """Place an assembled pet at a location in the scene.

    This is a convenience stub.  In practice, build the pet from
    primitives, collect the objects, and call :func:`parent_to_empty`.

    Parameters
    ----------
    pet_name : str
        Name of the pet group.
    location : tuple
        World-space position.
    rotation : tuple
        Euler rotation in radians.
    """
    print(
        f"[am_geometry] Placeholder: pet '{pet_name}' at {location}, "
        f"rot {rotation}"
    )


# ============================================================================
# DEMO / TEST
# ============================================================================

def demo_all_primitives() -> None:
    """Build every primitive in a neat grid for visual verification.

    Layout (each row is on the Y axis, spacing 1.5 units):

    Row 0 (Z=1.0):  half_sphere | sphere_eye | chibi_head_round |
                      chibi_head_square | chibi_head_triangular
    Row 1 (Z=0.0):  chibi_body_chubby | chibi_body_slim | chibi_body_long
    Row 2 (Z=-1.0): ears_floppy | ears_pointy | ears_round |
                      ears_long | ears_feathered
    Row 3 (Z=-2.0): tail_puff | tail_curved | tail_long |
                      tail_fluffy | tail_spiked
    Row 4 (Z=-3.0): snout_short | snout_long | snout_broad
    Row 5 (Z=-4.0): wings_small | wings_large | wings_butterfly
    Row 6 (Z=-5.0): horns_simple | horns_unicorn | horns_antlers
    Row 7 (Z=-6.0): neon_glow example
    """
    clear_scene()

    spacing = 1.5
    created: List[bpy.types.Object] = []

    # ---- Row 0: Feet, Eyes, Heads ----
    rz = 1.0
    x = -3.0
    created.append(
        make_half_sphere("Foot", radius=0.25, color_hex="#888888",
                         location=(x, 0, rz))
    )
    x += spacing
    created.append(
        make_sphere_eye("Eye", radius=0.15, color_hex="#111111",
                        location=(x, 0, rz), highlight=True)
    )
    x += spacing
    created.append(
        make_chibi_head("Head_Round", style="round", size=1.0,
                        color_hex="#D2B48C", location=(x, 0, rz))
    )
    x += spacing
    created.append(
        make_chibi_head("Head_Square", style="square", size=1.0,
                        color_hex="#8B4513", location=(x, 0, rz))
    )
    x += spacing
    created.append(
        make_chibi_head("Head_Triangular", style="triangular", size=1.0,
                        color_hex="#FF9966", location=(x, 0, rz))
    )

    # ---- Row 1: Bodies ----
    rz = 0.0
    x = -2.0
    created.append(
        make_chibi_body("Body_Chubby", style="chubby", size=1.0,
                        color_hex="#D2B48C", location=(x, 0, rz))
    )
    x += spacing
    created.append(
        make_chibi_body("Body_Slim", style="slim", size=1.0,
                        color_hex="#D2B48C", location=(x, 0, rz))
    )
    x += spacing
    created.append(
        make_chibi_body("Body_Long", style="long", size=1.0,
                        color_hex="#D2B48C", location=(x, 0, rz))
    )

    # ---- Row 2: Ears ----
    rz = -1.0
    x = -3.0
    for st in ("floppy", "pointy", "round", "long", "feathered"):
        created.append(
            make_ears(f"Ear_{st.title()}", style=st,
                      color_hex="#D2B48C", location=(x, 0, rz),
                      side="left")
        )
        x += spacing

    # ---- Row 3: Tails ----
    rz = -2.0
    x = -3.0
    for st in ("puff", "curved", "long", "fluffy", "spiked"):
        created.append(
            make_tail(f"Tail_{st.title()}", style=st,
                      color_hex="#D2B48C", location=(x, 0, rz),
                      length=1.0)
        )
        x += spacing

    # ---- Row 4: Snouts ----
    rz = -3.0
    x = -1.5
    for st in ("short", "long", "broad"):
        created.append(
            make_snout(f"Snout_{st.title()}", style=st,
                       color_hex="#8B4513", location=(x, 0, rz))
        )
        x += spacing

    # ---- Row 5: Wings ----
    rz = -4.0
    x = -1.5
    for st in ("small", "large", "butterfly"):
        created.append(
            make_wings(f"Wing_{st.title()}", style=st,
                       color_hex="#CC3333", location=(x, 0, rz),
                       side="left")
        )
        x += spacing

    # ---- Row 6: Horns ----
    rz = -5.0
    x = -1.5
    for st in ("simple", "unicorn", "antlers"):
        s = "center" if st == "unicorn" else "left"
        created.append(
            make_horns(f"Horn_{st.title()}", style=st,
                       color_hex="#CC9900", location=(x, 0, rz),
                       side=s)
        )
        x += spacing

    # ---- Row 7: Neon glow example ----
    rz = -6.0
    obj = make_chibi_head("NeonHead", style="round", size=1.0,
                          color_hex="#00FF00", location=(0, 0, rz))
    created.append(obj)
    glow = make_neon_glow("NeonGlow", obj, glow_color="#00FF00",
                          intensity=0.8)
    created.append(glow)

    # Parent everything under a single empty
    parent_to_empty("AM_Demo_Root", created, location=(0, 0, 0))
    print(
        f"[am_geometry] demo_all_primitives() complete -- "
        f"{len(created)} objects created."
    )


# ============================================================================
# SELF-TEST ENTRY POINT (Blender only)
# ============================================================================

if __name__ == "__main__":
    demo_all_primitives()
