"""
ADOPT ME CAT — Clean Low-Poly Build
=====================================
Self-contained — no external imports needed.
Paste into Blender 4.x Scripting tab → Run Script (Alt+P)

Design rules enforced:
  HEAD > BODY  (head r=1.0, body r=0.62)
  BIG EYES     (eyes are 28% of head width — identity lives in the face)
  TINY FEET    (feet r=0.15, flat stubby)
  NO NECK      (head clips into body)
  CIRCLES ONLY (all parts are spheres/cones with shade smooth)
"""

import bpy
import math

# ── CLEAR ──────────────────────────────────────────────────────────────────
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete()
for m in bpy.data.materials:
    bpy.data.materials.remove(m)


# ── MATERIALS ──────────────────────────────────────────────────────────────
def mat(name, rgb, rough=0.65, emit_rgb=None, emit_str=0.0):
    m = bpy.data.materials.new(name)
    m.use_nodes = True
    b = m.node_tree.nodes["Principled BSDF"]
    b.inputs["Base Color"].default_value = (*rgb, 1.0)
    b.inputs["Roughness"].default_value = rough
    if emit_rgb:
        b.inputs["Emission Color"].default_value = (*emit_rgb, 1.0)
        b.inputs["Emission Strength"].default_value = emit_str
    return m

# Orange tabby palette
M_BODY   = mat("Body",      (0.91, 0.51, 0.22))   # warm orange
M_BELLY  = mat("Belly",     (0.97, 0.88, 0.73))   # cream
M_EAR_IN = mat("EarInner",  (0.98, 0.65, 0.72))   # pink
M_EYE_W  = mat("EyeWhite",  (0.95, 0.95, 0.95), rough=0.1)
M_EYE_B  = mat("EyePupil",  (0.05, 0.05, 0.05), rough=0.05)
M_SHINE  = mat("EyeShine",  (1.0,  1.0,  1.0),  rough=0.0)
M_NOSE   = mat("Nose",      (0.95, 0.55, 0.65))
M_STRIPE = mat("Stripe",    (0.65, 0.32, 0.08))   # dark tabby stripe


# ── HELPERS ────────────────────────────────────────────────────────────────
def assign(obj, material):
    obj.data.materials.clear()
    obj.data.materials.append(material)

def smooth(obj):
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.shade_smooth()
    # Auto smooth for clean shading
    obj.data.use_auto_smooth = False   # Blender 4.x: smooth by angle via modifier
    return obj

def sphere(name, r, loc, seg=10, rings=7, mat=None, scale=None):
    bpy.ops.mesh.primitive_uv_sphere_add(
        radius=r, segments=seg, ring_count=rings, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    if scale:
        obj.scale = scale
        bpy.ops.object.transform_apply(scale=True)
    smooth(obj)
    if mat:
        assign(obj, mat)
    return obj

def cone(name, r1, r2, depth, loc, rot=(0,0,0), verts=8, mat=None):
    bpy.ops.mesh.primitive_cone_add(
        vertices=verts, radius1=r1, radius2=r2,
        depth=depth, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = rot
    bpy.ops.object.transform_apply(rotation=True)
    smooth(obj)
    if mat:
        assign(obj, mat)
    return obj

def cyl(name, r, depth, loc, rot=(0,0,0), verts=8, mat=None):
    bpy.ops.mesh.primitive_cylinder_add(
        vertices=verts, radius=r, depth=depth, location=loc)
    obj = bpy.context.active_object
    obj.name = name
    obj.rotation_euler = rot
    bpy.ops.object.transform_apply(rotation=True)
    smooth(obj)
    if mat:
        assign(obj, mat)
    return obj


# ══════════════════════════════════════════════════════════════════════════
#  CAT PARTS  (all coordinates in Blender units, Y = forward, Z = up)
# ══════════════════════════════════════════════════════════════════════════

# ── HEAD  (r=1.0, slightly squished front-to-back) ─────────────────────
head = sphere("Head", r=1.0, loc=(0, 0, 0), seg=12, rings=9,
              mat=M_BODY, scale=(1.0, 0.92, 1.0))

# ── BODY  (r=0.62 → ~62% of head, clips into head — NO NECK) ──────────
body = sphere("Body", r=0.62, loc=(0, 0.28, -0.88), seg=10, rings=7,
              mat=M_BODY, scale=(1.0, 0.88, 1.05))

# Belly patch (cream oval on front of body)
belly = sphere("Belly", r=0.45, loc=(0, -0.22, -0.84), seg=8, rings=6,
               mat=M_BELLY, scale=(0.7, 0.18, 0.85))

# ── EARS  (pointy low-poly cones, angled outward) ─────────────────────
# Outer ear shell
ear_l = cone("Ear_L", r1=0.26, r2=0.02, depth=0.42,
             loc=(-0.46, -0.16, 0.90),
             rot=(0.18, -0.22, -0.08), verts=6, mat=M_BODY)
ear_r = cone("Ear_R", r1=0.26, r2=0.02, depth=0.42,
             loc=( 0.46, -0.16, 0.90),
             rot=(0.18,  0.22,  0.08), verts=6, mat=M_BODY)
# Inner pink ear (slightly inset)
ear_li = cone("Ear_L_Inner", r1=0.15, r2=0.01, depth=0.26,
              loc=(-0.46, -0.20, 0.92),
              rot=(0.18, -0.22, -0.08), verts=6, mat=M_EAR_IN)
ear_ri = cone("Ear_R_Inner", r1=0.15, r2=0.01, depth=0.26,
              loc=( 0.46, -0.20, 0.92),
              rot=(0.18,  0.22,  0.08), verts=6, mat=M_EAR_IN)

# ── EYES  (BIG — 30% of head, the whole personality) ──────────────────
for side, x in [("L", -0.34), ("R", 0.34)]:
    ey = 0.08      # Y depth into head (sit on surface)

    # White sclera — squished flat against head
    sclera = sphere(f"Eye_{side}_Sclera", r=0.21,
                    loc=(x, -0.90, 0.08), seg=10, rings=8,
                    mat=M_EYE_W, scale=(1.0, 0.22, 1.0))

    # Pupil — sits proud of sclera
    pupil = sphere(f"Eye_{side}_Pupil", r=0.145,
                   loc=(x, -0.97, 0.08), seg=8, rings=6,
                   mat=M_EYE_B, scale=(1.0, 0.18, 1.0))

    # Shine dot (top-right of pupil)
    shine = sphere(f"Eye_{side}_Shine", r=0.045,
                   loc=(x + 0.07, -1.01, 0.17), seg=6, rings=4,
                   mat=M_SHINE, scale=(1.0, 0.15, 1.0))

# ── NOSE  (tiny pink triangle blob) ───────────────────────────────────
nose = sphere("Nose", r=0.07, loc=(0, -1.01, -0.10), seg=8, rings=5,
              mat=M_NOSE, scale=(1.3, 0.3, 0.8))

# ── CHEEK PUFFS  (subtle roundness either side of nose) ───────────────
chk_l = sphere("Cheek_L", r=0.18, loc=(-0.22, -0.93, -0.12), seg=8, rings=6,
               mat=M_BELLY, scale=(1.0, 0.25, 0.9))
chk_r = sphere("Cheek_R", r=0.18, loc=( 0.22, -0.93, -0.12), seg=8, rings=6,
               mat=M_BELLY, scale=(1.0, 0.25, 0.9))

# ── FEET  (4 small squished spheres — tiny per design law) ────────────
foot_locs = [
    (-0.30, -0.12, -1.46),   # front-left
    ( 0.30, -0.12, -1.46),   # front-right
    (-0.24,  0.30, -1.44),   # rear-left
    ( 0.24,  0.30, -1.44),   # rear-right
]
for i, loc in enumerate(foot_locs):
    sphere(f"Foot_{i+1}", r=0.17, loc=loc, seg=8, rings=5,
           mat=M_BODY, scale=(1.0, 1.15, 0.62))

# ── TAIL  (curved — base cylinder + round tip) ────────────────────────
tail_base = cyl("Tail_Base", r=0.10, depth=0.55,
                loc=(0.55, 0.52, -1.08),
                rot=(0.3, 0.55, 0.1), verts=8, mat=M_BODY)
tail_tip  = sphere("Tail_Tip", r=0.16, loc=(0.78, 0.72, -0.84),
                   seg=8, rings=6, mat=M_BODY)

# ── TABBY STRIPES  (3 subtle dark lines on head top) ──────────────────
stripe_locs = [
    (0,     -0.08, 1.0),
    (-0.28, -0.06, 0.96),
    ( 0.28, -0.06, 0.96),
]
for i, loc in enumerate(stripe_locs):
    s = sphere(f"Stripe_{i+1}", r=0.06, loc=loc, seg=6, rings=4,
               mat=M_STRIPE, scale=(1.8, 0.15, 0.4))


# ══════════════════════════════════════════════════════════════════════════
#  LIGHTING  (minimal — sun + soft fill)
# ══════════════════════════════════════════════════════════════════════════

bpy.ops.object.light_add(type='SUN', location=(4, -6, 8))
sun = bpy.context.active_object
sun.name = "Sun"
sun.data.energy = 4.0
sun.data.angle = 0.15
sun.rotation_euler = (0.85, 0.0, 0.45)

bpy.ops.object.light_add(type='AREA', location=(-4, -2, 3))
fill = bpy.context.active_object
fill.name = "Fill"
fill.data.energy = 250
fill.data.size = 6
fill.data.color = (0.82, 0.88, 1.0)


# ══════════════════════════════════════════════════════════════════════════
#  CAMERA
# ══════════════════════════════════════════════════════════════════════════

bpy.ops.object.camera_add(location=(0.0, -5.8, 0.15))
cam = bpy.context.active_object
cam.name = "Camera"
cam.rotation_euler = (math.radians(90), 0, 0)
cam.data.lens = 85
bpy.context.scene.camera = cam


# ══════════════════════════════════════════════════════════════════════════
#  WORLD
# ══════════════════════════════════════════════════════════════════════════

world = bpy.context.scene.world
world.use_nodes = True
world.node_tree.nodes["Background"].inputs["Color"].default_value = (0.12, 0.13, 0.18, 1.0)
world.node_tree.nodes["Background"].inputs["Strength"].default_value = 0.4


# ══════════════════════════════════════════════════════════════════════════
#  FRAME VIEW
# ══════════════════════════════════════════════════════════════════════════

bpy.ops.object.select_all(action='SELECT')
# Frame all objects in viewport
for area in bpy.context.screen.areas:
    if area.type == 'VIEW_3D':
        with bpy.context.temp_override(area=area):
            bpy.ops.view3d.view_selected()
        break

print("=" * 55)
print("  Cat built! Tips:")
print("  Z → Material Preview  — see the orange colours")
print("  Numpad 0              — look through camera")
print("  F12                   — render")
print("=" * 55)
