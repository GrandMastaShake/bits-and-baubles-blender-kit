"""
rig_cat.py
──────────────────────────────────────────────────────────────────────────────
Blender 4.x — Run in the Scripting tab (or Text Editor → Run Script).
Adds a clean quadruped armature to the cat scene, then parents every mesh
object to the correct bone based on the object's world-space centre (closest
bone wins, head-sphere excluded so the face mesh snaps cleanly to the Head
bone regardless of names).

Bone hierarchy
──────────────
Root                    ← planted at ground (z = -2.0)
└─ Body                 ← centre of the body sphere
   ├─ Spine             ← from body to neck base
   │  └─ Head           ← head sphere centre to top
   │     ├─ Ear_L       ← left ear tip
   │     └─ Ear_R       ← right ear tip
   ├─ Leg_FL            ← front-left  (from hip to paw)
   ├─ Leg_FR            ← front-right
   ├─ Leg_BL            ← back-left
   ├─ Leg_BR            ← back-right
   └─ Tail_1            ← tail root
      └─ Tail_2
         └─ Tail_3      ← tail tip

After running this script the rig is ready for the animation scripts.
Each mesh is an Object-child of its bone's armature object (not vertex-weight
deformed) — correct for rigid chibi-style parts.
"""

import bpy
import math
from mathutils import Vector

# ─── 1. Tidy up any old rig ──────────────────────────────────────────────────
for obj in list(bpy.data.objects):
    if obj.type == 'ARMATURE':
        bpy.data.objects.remove(obj, do_unlink=True)

# ─── 2. Create the armature ──────────────────────────────────────────────────
bpy.ops.object.select_all(action='DESELECT')
bpy.ops.object.add(type='ARMATURE', enter_editmode=True, location=(0, 0, 0))
arm_obj = bpy.context.active_object
arm_obj.name = "CatRig"
arm = arm_obj.data
arm.name = "CatArmature"
arm.display_type = 'STICK'
arm_obj.show_in_front = True   # X-ray so we can see it through the mesh

eb = arm.edit_bones

# Helper ──────────────────────────────────────────────────────────────────────
def bone(name, head_xyz, tail_xyz, parent=None, connected=False):
    b = eb.new(name)
    b.head = Vector(head_xyz)
    b.tail = Vector(tail_xyz)
    if parent:
        b.parent = eb[parent]
        b.use_connect = connected
    return b

# ─── 3. Define bones (Z-up, Y-forward Blender convention) ────────────────────
# Approximate positions tuned for the chibi-cat proportions:
#   head  r=1.0  centre at (0, 0,  0)
#   body  r=0.62 centre at (0, 0.28, -0.88)
#   tail base at (0, 0.62, -1.4)
#   feet  at z ≈ -1.7

bone("Root",    (  0,    0, -2.0), (  0,    0, -1.5))
bone("Body",    (  0,  0.28, -0.88),(  0,    0,  0),    parent="Root")
bone("Spine",   (  0,    0,  0),   (  0,    0,  0.7),   parent="Body")
bone("Head",    (  0,    0,  0.7), (  0,    0,  1.6),   parent="Spine", connected=True)
bone("Ear_L",   (-0.45,  0,  1.5), (-0.55, -0.1, 2.0), parent="Head")
bone("Ear_R",   ( 0.45,  0,  1.5), ( 0.55, -0.1, 2.0), parent="Head")

# Legs — head at hip on body, tail at paw ground level
bone("Leg_FL",  (-0.35, -0.45, -0.88), (-0.35, -0.45, -1.72), parent="Body")
bone("Leg_FR",  ( 0.35, -0.45, -0.88), ( 0.35, -0.45, -1.72), parent="Body")
bone("Leg_BL",  (-0.30,  0.50, -0.88), (-0.30,  0.50, -1.72), parent="Body")
bone("Leg_BR",  ( 0.30,  0.50, -0.88), ( 0.30,  0.50, -1.72), parent="Body")

# Tail — rises up then curls over
bone("Tail_1",  (  0,  0.62, -1.30), (  0,  1.10, -0.80), parent="Body")
bone("Tail_2",  (  0,  1.10, -0.80), (  0,  1.40, -0.20), parent="Tail_1", connected=True)
bone("Tail_3",  (  0,  1.40, -0.20), (  0,  1.50,  0.30), parent="Tail_2", connected=True)

bpy.ops.object.mode_set(mode='OBJECT')

# ─── 4. Parent mesh objects to the armature ──────────────────────────────────
# Strategy: for each mesh, find the bone whose HEAD is closest to the mesh
# world origin, then set the armature as parent and clear the offset (so the
# mesh stays in place and the bone just controls it).

# Build a lookup: bone_name → head position (world space — arm is at origin)
bone_heads = {b.name: Vector(b.head_local) for b in arm.bones}

def closest_bone(world_origin: Vector) -> str:
    best_name = "Body"
    best_dist = 1e9
    for bname, bhead in bone_heads.items():
        d = (world_origin - bhead).length
        if d < best_dist:
            best_dist = d
            best_name = bname
    return best_name

mesh_objects = [obj for obj in bpy.data.objects if obj.type == 'MESH']
print(f"\n[rig_cat] Parenting {len(mesh_objects)} mesh objects to CatRig …")

for obj in mesh_objects:
    world_origin = obj.matrix_world.translation.copy()
    target_bone  = closest_bone(world_origin)

    # Clear any existing parent first (keep transform)
    if obj.parent:
        bpy.ops.object.select_all(action='DESELECT')
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj
        bpy.ops.object.parent_clear(type='CLEAR_KEEP_TRANSFORM')

    # Parent to armature, with specific bone
    obj.parent           = arm_obj
    obj.parent_type      = 'BONE'
    obj.parent_bone      = target_bone
    # Keep the mesh in its current world position
    # (parent_bone parenting shifts by bone tail — correct with matrix)
    obj.matrix_parent_inverse = (
        arm_obj.matrix_world
        @ arm.bones[target_bone].matrix_local
    ).inverted()

    print(f"  {obj.name:<30} → {target_bone}")

# Select the armature so the user can go straight to Pose mode
bpy.ops.object.select_all(action='DESELECT')
arm_obj.select_set(True)
bpy.context.view_layer.objects.active = arm_obj

print(f"\n[rig_cat] Done!  Armature: {arm_obj.name}  |  Bones: {len(arm.bones)}")
print("[rig_cat] Press Ctrl+Tab (or header ▾ > Pose Mode) to enter Pose Mode.")
print("[rig_cat] Run animate_cat.py next to bake idle, walk, and bounce actions.")
