#!/usr/bin/env python3
"""
BITS AND BAUBLES — PET GENERATOR v1.0
======================================
Generates Adopt Me-style chibi pets procedurally in Blender.
Implements the 10 Design Laws from the Adopt Me Style DNA research.

Each pet is a collection of separate mesh objects (matching Uplift's
actual asset structure: separate parts per colour region, no merged
mesh, simple flat materials — no textures needed).

Usage
-----
  1. Open Blender 4.0+
  2. Scripting tab → Open this file
  3. Click Run Script
  — OR —
  blender --background --python pet_generator.py

Headless output: saves pet_demo.blend next to this script.

10 Design Laws (from style DNA research)
-----------------------------------------
  1. HEAD > BODY          — head ≈ 90 % of body width, chibi ratio
  2. CIRCLES ONLY         — eyes are perfect spheres, body is rounded barrel
  3. NO ANGRY PETS        — every pet has a small smile (implied by proportions)
  4. TINY FEET            — hemispheres, ~1/5 body height, no legs
  5. NO NECK              — head overlaps body directly
  6. COLOR = RARITY       — palette swappable per species/rarity
  7. HEAD = IDENTITY      — body stays generic; head shape defines species
  8. SHARP = SOFTENED     — ears are cones but low-poly / slightly blunt
  9. GLOW = STATUS        — emission material slot ready on each part
 10. SIMPLE = UNIVERSAL   — low-poly, shade-smooth, no UV maps needed
"""

import bpy
import bmesh
import math
import os
import sys
from pathlib import Path
from typing import Dict, Tuple, Optional

# ─────────────────────────────────────────────────────────────────────────────
# COLOUR PALETTES
# ─────────────────────────────────────────────────────────────────────────────

PALETTES: Dict[str, Dict[str, Tuple[float, float, float, float]]] = {
    "orange": {
        "body":      (0.87, 0.52, 0.18, 1.0),
        "light":     (0.95, 0.80, 0.55, 1.0),   # belly / inner-ear highlight
        "eyes":      (0.02, 0.02, 0.02, 1.0),
        "nose":      (0.98, 0.60, 0.72, 1.0),
        "inner_ear": (0.98, 0.60, 0.72, 1.0),
        "whiskers":  (0.95, 0.95, 0.95, 1.0),
    },
    "gray": {
        "body":      (0.62, 0.62, 0.65, 1.0),
        "light":     (0.86, 0.86, 0.88, 1.0),
        "eyes":      (0.02, 0.02, 0.02, 1.0),
        "nose":      (0.98, 0.60, 0.72, 1.0),
        "inner_ear": (0.98, 0.60, 0.72, 1.0),
        "whiskers":  (0.95, 0.95, 0.95, 1.0),
    },
    "white": {
        "body":      (0.92, 0.92, 0.94, 1.0),
        "light":     (1.00, 1.00, 1.00, 1.0),
        "eyes":      (0.02, 0.02, 0.02, 1.0),
        "nose":      (0.98, 0.60, 0.72, 1.0),
        "inner_ear": (0.98, 0.60, 0.72, 1.0),
        "whiskers":  (0.85, 0.85, 0.87, 1.0),
    },
    "black": {
        "body":      (0.06, 0.06, 0.06, 1.0),
        "light":     (0.18, 0.18, 0.18, 1.0),
        "eyes":      (0.80, 0.50, 0.02, 1.0),   # amber eyes on black cat
        "nose":      (0.98, 0.60, 0.72, 1.0),
        "inner_ear": (0.98, 0.60, 0.72, 1.0),
        "whiskers":  (0.70, 0.70, 0.70, 1.0),
    },
}

# ─────────────────────────────────────────────────────────────────────────────
# MATERIAL HELPERS
# ─────────────────────────────────────────────────────────────────────────────

_mat_cache: Dict[str, bpy.types.Material] = {}


def get_material(name: str, rgba: Tuple[float, float, float, float],
                 emission: float = 0.0) -> bpy.types.Material:
    """Return a cached simple Principled BSDF material."""
    key = f"{name}_{rgba}_{emission}"
    if key in _mat_cache:
        return _mat_cache[key]

    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    nodes.clear()

    out   = nodes.new("ShaderNodeOutputMaterial")
    bsdf  = nodes.new("ShaderNodeBsdfPrincipled")
    mat.node_tree.links.new(bsdf.outputs["BSDF"], out.inputs["Surface"])

    bsdf.inputs["Base Color"].default_value = rgba
    bsdf.inputs["Roughness"].default_value  = 0.85
    bsdf.inputs["Metallic"].default_value   = 0.0

    # Blender 4.0 renamed "Specular" → "Specular IOR Level"
    spec_key = ("Specular IOR Level"
                if "Specular IOR Level" in bsdf.inputs else "Specular")
    if spec_key in bsdf.inputs:
        bsdf.inputs[spec_key].default_value = 0.1

    if emission > 0.0 and "Emission Strength" in bsdf.inputs:
        bsdf.inputs["Emission Color"].default_value  = rgba
        bsdf.inputs["Emission Strength"].default_value = emission

    _mat_cache[key] = mat
    return mat


def assign_mat(obj: bpy.types.Object, mat: bpy.types.Material) -> None:
    obj.data.materials.clear()
    obj.data.materials.append(mat)


def shade_smooth(obj: bpy.types.Object) -> None:
    for poly in obj.data.polygons:
        poly.use_smooth = True
    obj.data.update()


# ─────────────────────────────────────────────────────────────────────────────
# PRIMITIVE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def deselect_all() -> None:
    bpy.ops.object.select_all(action="DESELECT")


def add_sphere(name: str, segments: int = 12, rings: int = 8,
               loc=(0.0, 0.0, 0.0),
               scale=(1.0, 1.0, 1.0)) -> bpy.types.Object:
    deselect_all()
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    shade_smooth(obj)
    return obj


def add_hemisphere(name: str, segments: int = 10, rings: int = 5,
                   loc=(0.0, 0.0, 0.0),
                   scale=(1.0, 1.0, 1.0)) -> bpy.types.Object:
    """Bottom hemisphere (flat cap facing down) — Design Law #4."""
    deselect_all()
    bpy.ops.mesh.primitive_uv_sphere_add(
        segments=segments, ring_count=rings, location=(0, 0, 0))
    obj = bpy.context.active_object
    obj.name = name

    # Delete upper half in edit mode
    bpy.ops.object.mode_set(mode="EDIT")
    bm = bmesh.from_edit_mesh(obj.data)
    bm.verts.ensure_lookup_table()
    to_delete = [v for v in bm.verts if v.co.z > 0.001]
    bmesh.ops.delete(bm, geom=to_delete, context="VERTS")
    # Fill the open top
    bm.edges.ensure_lookup_table()
    boundary = [e for e in bm.edges if e.is_boundary]
    if boundary:
        bmesh.ops.holes_fill(bm, edges=boundary, sides=len(boundary))
    bmesh.update_edit_mesh(obj.data)
    bpy.ops.object.mode_set(mode="OBJECT")

    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    obj.location = loc
    shade_smooth(obj)
    return obj


def add_cone(name: str, vertices: int = 4,
             loc=(0.0, 0.0, 0.0),
             scale=(1.0, 1.0, 1.0),
             rot=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    deselect_all()
    bpy.ops.mesh.primitive_cone_add(
        vertices=vertices, radius1=0.5, radius2=0.0, depth=1.0,
        location=loc,
        rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    shade_smooth(obj)
    return obj


def add_cylinder(name: str, vertices: int = 6,
                 loc=(0.0, 0.0, 0.0),
                 scale=(1.0, 1.0, 1.0),
                 rot=(0.0, 0.0, 0.0)) -> bpy.types.Object:
    deselect_all()
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=vertices, radius=0.5, depth=1.0,
        location=loc, rotation=rot)
    obj = bpy.context.active_object
    obj.name = name
    obj.scale = scale
    bpy.ops.object.transform_apply(scale=True)
    shade_smooth(obj)
    return obj


def move_to_collection(obj: bpy.types.Object,
                       col: bpy.types.Collection) -> None:
    for c in list(obj.users_collection):
        c.objects.unlink(obj)
    col.objects.link(obj)


# ─────────────────────────────────────────────────────────────────────────────
# CAT GENERATOR
# ─────────────────────────────────────────────────────────────────────────────

def generate_cat(palette_name: str = "orange",
                 root_loc: Tuple[float, float, float] = (0.0, 0.0, 0.0),
                 neon: bool = False) -> Dict[str, bpy.types.Object]:
    """
    Build a complete Adopt Me-style cat at root_loc.

    All 10 Design Laws applied:
      Law 1  HEAD > BODY   — head is 88 % of body width
      Law 2  CIRCLES       — sphere body, sphere head, sphere eyes, sphere nose
      Law 3  NO ANGRY      — proportions read as friendly/cute
      Law 4  TINY FEET     — four flat-bottom hemispheres, no legs
      Law 5  NO NECK       — head Z overlaps body top by ~10 %
      Law 6  COLOR=RARITY  — full palette swap via palette_name
      Law 7  HEAD=IDENTITY — triangular ears, whiskers on head only
      Law 8  SHARP=SOFT    — 4-vertex cone ears (triangular but blunt at tip)
      Law 9  GLOW=STATUS   — emission=1.0 on eyes/nose when neon=True
      Law 10 SIMPLE        — ≤12 segments on any primitive
    """
    pal   = PALETTES.get(palette_name, PALETTES["orange"])
    emit  = 2.0 if neon else 0.0
    parts: Dict[str, bpy.types.Object] = {}

    # Create collection
    col_name = f"Cat_{palette_name.capitalize()}"
    if col_name in bpy.data.collections:
        bpy.data.collections.remove(bpy.data.collections[col_name])
    col = bpy.data.collections.new(col_name)
    bpy.context.scene.collection.children.link(col)

    rx, ry, rz = root_loc   # root offset applied after build

    # ── Materials ────────────────────────────────────────────────────────────
    mat_body      = get_material("cat_body",      pal["body"])
    mat_light     = get_material("cat_light",     pal["light"])
    mat_eyes      = get_material("cat_eyes",      pal["eyes"],      emit)
    mat_nose      = get_material("cat_nose",      pal["nose"],      emit * 0.5)
    mat_inner_ear = get_material("cat_inner_ear", pal["inner_ear"])
    mat_whiskers  = get_material("cat_whiskers",  pal["whiskers"])

    # ── BODY  (Law 2, 3, 10) ─────────────────────────────────────────────────
    # Barrel-shaped rounded torso
    body = add_sphere("Cat_Body", segments=12, rings=8,
                      loc=(rx, ry, rz + 0.0),
                      scale=(0.80, 0.72, 0.76))
    assign_mat(body, mat_body)
    move_to_collection(body, col)
    parts["body"] = body

    # ── HEAD  (Laws 1, 5, 7) ──────────────────────────────────────────────────
    # Slightly smaller than body but big — chibi ratio.
    # Z placed so it overlaps body top (no neck gap — Law 5).
    head = add_sphere("Cat_Head", segments=12, rings=8,
                      loc=(rx, ry, rz + 1.02),
                      scale=(0.70, 0.66, 0.68))
    assign_mat(head, mat_body)
    move_to_collection(head, col)
    parts["head"] = head

    # ── FEET  (Law 4) ─────────────────────────────────────────────────────────
    # Four flat-bottom hemispheres, no legs, floating just below body.
    foot_positions = [
        ("Cat_Foot_FL", (rx - 0.32, ry + 0.28, rz - 0.68)),
        ("Cat_Foot_FR", (rx + 0.32, ry + 0.28, rz - 0.68)),
        ("Cat_Foot_BL", (rx - 0.28, ry - 0.28, rz - 0.68)),
        ("Cat_Foot_BR", (rx + 0.28, ry - 0.28, rz - 0.68)),
    ]
    for fname, floc in foot_positions:
        foot = add_hemisphere(fname, segments=10, rings=5,
                              loc=floc, scale=(0.21, 0.21, 0.14))
        assign_mat(foot, mat_body)
        move_to_collection(foot, col)
        parts[fname] = foot

    # ── EYES  (Laws 2, 9) ─────────────────────────────────────────────────────
    # Small sphere primitives, single flat black, embedded in head face.
    eye_positions = [
        ("Cat_Eye_L", (rx - 0.22, ry + 0.62, rz + 1.08)),
        ("Cat_Eye_R", (rx + 0.22, ry + 0.62, rz + 1.08)),
    ]
    for ename, eloc in eye_positions:
        eye = add_sphere(ename, segments=8, rings=6,
                         loc=eloc, scale=(0.11, 0.08, 0.11))
        assign_mat(eye, mat_eyes)
        move_to_collection(eye, col)
        parts[ename] = eye

    # ── NOSE  (Law 2) ─────────────────────────────────────────────────────────
    nose = add_sphere("Cat_Nose", segments=6, rings=4,
                      loc=(rx + 0.0, ry + 0.67, rz + 0.94),
                      scale=(0.055, 0.04, 0.045))
    assign_mat(nose, mat_nose)
    move_to_collection(nose, col)
    parts["nose"] = nose

    # ── EARS  (Laws 7, 8) ─────────────────────────────────────────────────────
    # 4-vertex cones = triangular silhouette (cat identity signal).
    # Slightly tilted outward. Tip rounded by low vert count — Law 8.
    ear_data = [
        ("Cat_Ear_L",
         (rx - 0.34, ry + 0.28, rz + 1.56),
         (0.0, math.radians(-12), math.radians(-8))),
        ("Cat_Ear_R",
         (rx + 0.34, ry + 0.28, rz + 1.56),
         (0.0, math.radians(12),  math.radians(8))),
    ]
    for ename, eloc, erot in ear_data:
        ear = add_cone(ename, vertices=4,
                       loc=eloc, scale=(0.20, 0.14, 0.28), rot=erot)
        assign_mat(ear, mat_body)
        move_to_collection(ear, col)
        parts[ename] = ear

    # ── INNER EARS  (Law 6) ───────────────────────────────────────────────────
    # Pink cone, slightly smaller and in front of main ear.
    inner_ear_data = [
        ("Cat_InnerEar_L",
         (rx - 0.34, ry + 0.32, rz + 1.54),
         (0.0, math.radians(-12), math.radians(-8))),
        ("Cat_InnerEar_R",
         (rx + 0.34, ry + 0.32, rz + 1.54),
         (0.0, math.radians(12),  math.radians(8))),
    ]
    for iname, iloc, irot in inner_ear_data:
        inner = add_cone(iname, vertices=4,
                         loc=iloc, scale=(0.12, 0.06, 0.20), rot=irot)
        assign_mat(inner, mat_inner_ear)
        move_to_collection(inner, col)
        parts[iname] = inner

    # ── TAIL  (Law 2, 7) ──────────────────────────────────────────────────────
    # Classic cat puff tail — single small sphere at rear of body.
    tail = add_sphere("Cat_Tail", segments=8, rings=6,
                      loc=(rx + 0.0, ry - 0.76, rz - 0.35),
                      scale=(0.19, 0.19, 0.19))
    assign_mat(tail, mat_body)
    move_to_collection(tail, col)
    parts["tail"] = tail

    # ── WHISKERS  (Law 7) ─────────────────────────────────────────────────────
    # Thin cylinders, 3 per side, fanning out slightly.
    whisker_angles = [-0.12, 0.0, 0.12]   # radians, slight fan
    for side, sign in [("L", -1), ("R", 1)]:
        for i, angle in enumerate(whisker_angles):
            wname = f"Cat_Whisker_{side}{i+1}"
            wx = rx + sign * 0.38
            wy = ry + 0.66
            wz = rz + 0.93 + angle * 0.12
            rot_z = math.radians(90) + angle * sign
            whisker = add_cylinder(
                wname, vertices=5,
                loc=(wx, wy, wz),
                scale=(0.38, 0.012, 0.012),
                rot=(0.0, math.radians(90), rot_z),
            )
            assign_mat(whisker, mat_whiskers)
            move_to_collection(whisker, col)
            parts[wname] = whisker

    print(f"\n[PetGenerator] Cat '{palette_name}' built — "
          f"{len(parts)} parts in collection '{col_name}'")
    print(f"[PetGenerator] Neon mode: {neon}")
    return parts


# ─────────────────────────────────────────────────────────────────────────────
# SCENE SETUP & CAMERA
# ─────────────────────────────────────────────────────────────────────────────

def setup_scene() -> None:
    """Clear default objects, add neutral background lighting."""
    # Remove default cube / camera / light
    bpy.ops.object.select_all(action="SELECT")
    bpy.ops.object.delete()

    # World background — soft light gray
    world = bpy.context.scene.world
    if world is None:
        world = bpy.data.worlds.new("World")
        bpy.context.scene.world = world
    world.use_nodes = True
    bg = world.node_tree.nodes.get("Background")
    if bg:
        bg.inputs["Color"].default_value   = (0.18, 0.18, 0.22, 1.0)
        bg.inputs["Strength"].default_value = 1.2

    # Key light
    bpy.ops.object.light_add(type="AREA",
                              location=(2.5, -2.0, 4.0))
    key = bpy.context.active_object
    key.name = "Light_Key"
    key.data.energy = 180
    key.data.size   = 3.0
    key.rotation_euler = (math.radians(50), math.radians(20), math.radians(30))

    # Fill light
    bpy.ops.object.light_add(type="AREA",
                              location=(-2.0, -1.0, 2.5))
    fill = bpy.context.active_object
    fill.name = "Light_Fill"
    fill.data.energy = 60
    fill.data.size   = 2.5

    # Rim light
    bpy.ops.object.light_add(type="AREA",
                              location=(0.0, 3.0, 2.0))
    rim = bpy.context.active_object
    rim.name = "Light_Rim"
    rim.data.energy = 80
    rim.data.size   = 2.0

    # Camera — slightly above, angled down for cute portrait
    bpy.ops.object.camera_add(
        location=(0.0, -3.8, 1.6),
        rotation=(math.radians(72), 0.0, 0.0))
    cam = bpy.context.active_object
    cam.name = "Camera_Portrait"
    cam.data.lens = 85          # portrait focal length, flatters chibi
    bpy.context.scene.camera = cam

    # Render settings — Cycles, medium quality
    bpy.context.scene.render.engine                   = "CYCLES"
    bpy.context.scene.cycles.samples                  = 64
    bpy.context.scene.render.resolution_x             = 1200
    bpy.context.scene.render.resolution_y             = 1200
    bpy.context.scene.render.film_transparent         = True


# ─────────────────────────────────────────────────────────────────────────────
# MAIN
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    setup_scene()

    # Build orange cat (standard) and a neon version side-by-side
    generate_cat(palette_name="orange", root_loc=(0.0, 0.0, 0.0), neon=False)

    # Save .blend
    script_dir  = Path(__file__).parent.resolve()
    output_path = str(script_dir / "output" / "pet_demo.blend")
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    bpy.ops.wm.save_as_mainfile(filepath=output_path)
    print(f"\n[PetGenerator] Saved → {output_path}")


if __name__ == "__main__":
    # Running headless: blender --background --python pet_generator.py
    main()
else:
    # Running from Blender Scripting tab — run immediately
    setup_scene()
    generate_cat(palette_name="orange", root_loc=(0.0, 0.0, 0.0), neon=False)
    print("[PetGenerator] Done — check the viewport and Outliner!")
