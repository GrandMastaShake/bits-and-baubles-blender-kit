"""
BLENDER CAT DEMO — Bits and Baubles x Adopt Me
================================================
Paste this entire script into Blender's Scripting tab and press Run Script.

Builds:
  1. A standard orange tabby cat  (left)
  2. A neon version of the same cat  (right, +8 units)

Then frames the camera and renders to:
  C:/Users/alexa/Desktop/Death_Star/Ember/Professional/FASHION/BitsandBaubles/bits_and_baubles/output/

Tested with Blender 4.x and am_pet_generator.py v1.0
"""

import bpy
import sys
import os

# ── PATH SETUP ─────────────────────────────────────────────────────────────
# Make sure Python can find am_pet_generator and am_geometry
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
if SCRIPT_DIR not in sys.path:
    sys.path.insert(0, SCRIPT_DIR)

# Also works if you run from Blender's text editor without __file__:
# SCRIPT_DIR = r"C:\Users\alexa\Desktop\Death_Star\Ember\Professional\FASHION\BitsandBaubles\bits_and_baubles"
# sys.path.insert(0, SCRIPT_DIR)

print("=" * 60)
print("  Bits and Baubles — Cat Demo")
print(f"  Script dir: {SCRIPT_DIR}")
print("=" * 60)

# ── CLEAR SCENE ────────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()

# ── IMPORT PET BUILDER ─────────────────────────────────────────────────────
# Reload modules in case Blender has a stale cache
import importlib
import am_geometry
import am_pet_generator
importlib.reload(am_geometry)
importlib.reload(am_pet_generator)

from am_pet_generator import AdoptMePetBuilder

# ── BUILD PETS ─────────────────────────────────────────────────────────────
builder = AdoptMePetBuilder(
    species_file=os.path.join(SCRIPT_DIR, "am_species.json")
)

print("\n[1/2] Building standard cat...")
cat_normal = builder.build_pet("cat", neon=False, location=(0, 0, 0))

print("\n[2/2] Building NEON cat...")
cat_neon = builder.build_pet("cat", neon=True, location=(8, 0, 0))

print("\n[Validation] Checking proportions...")
builder.validate_proportions("cat")

# ── LIGHTING ───────────────────────────────────────────────────────────────
# Key light (warm, front-right)
bpy.ops.object.light_add(type='AREA', location=(5, -6, 8))
key = bpy.context.active_object
key.name = "Key_Light"
key.data.energy = 800
key.data.size = 3
key.rotation_euler = (0.9, 0.0, 0.5)
key.data.color = (1.0, 0.95, 0.85)

# Fill light (cool, left)
bpy.ops.object.light_add(type='AREA', location=(-6, -4, 5))
fill = bpy.context.active_object
fill.name = "Fill_Light"
fill.data.energy = 300
fill.data.size = 4
fill.data.color = (0.8, 0.9, 1.0)

# Rim light (back, above)
bpy.ops.object.light_add(type='SPOT', location=(0, 8, 10))
rim = bpy.context.active_object
rim.name = "Rim_Light"
rim.data.energy = 500
rim.data.spot_size = 0.8
rim.rotation_euler = (-1.0, 0, 3.14)

# ── CAMERA ─────────────────────────────────────────────────────────────────
bpy.ops.object.camera_add(location=(4, -14, 6))
cam = bpy.context.active_object
cam.name = "Demo_Camera"
cam.rotation_euler = (1.1, 0, 0)
cam.data.lens = 85  # portrait / telephoto — compresses chibi proportions nicely
bpy.context.scene.camera = cam

# ── WORLD / BACKGROUND ─────────────────────────────────────────────────────
world = bpy.context.scene.world
world.use_nodes = True
bg = world.node_tree.nodes["Background"]
bg.inputs["Color"].default_value = (0.12, 0.12, 0.18, 1.0)   # dark blue-gray studio
bg.inputs["Strength"].default_value = 0.3

# ── RENDERER ───────────────────────────────────────────────────────────────
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.samples = 64                 # fast preview
scene.render.resolution_x = 1920
scene.render.resolution_y = 1080

output_dir = os.path.join(SCRIPT_DIR, "output")
os.makedirs(output_dir, exist_ok=True)
scene.render.filepath = os.path.join(output_dir, "cat_demo_")
scene.render.image_settings.file_format = 'PNG'

# ── GROUND PLANE ───────────────────────────────────────────────────────────
bpy.ops.mesh.primitive_plane_add(size=30, location=(4, 0, -0.05))
ground = bpy.context.active_object
ground.name = "Ground"
mat = bpy.data.materials.new("Ground_Mat")
mat.use_nodes = True
mat.node_tree.nodes["Principled BSDF"].inputs["Base Color"].default_value = (0.15, 0.15, 0.2, 1.0)
mat.node_tree.nodes["Principled BSDF"].inputs["Roughness"].default_value = 0.9
ground.data.materials.append(mat)

# ── DONE ───────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print("  DONE!  Two cats in viewport:")
print("    Left  (x=0): Standard orange tabby")
print("    Right (x=8): Neon glowing version")
print(f"\n  Output path: {output_dir}")
print("\n  TO RENDER:")
print("    Render menu → Render Image  (or F12)")
print("    Renders save to output/ folder automatically")
print("\n  TO TAKE VIEWPORT SCREENSHOT:")
print("    Position the view you want, then:")
print("    Window menu → Save Screenshot")
print("=" * 60)
