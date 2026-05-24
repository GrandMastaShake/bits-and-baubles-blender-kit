"""
animate_cat.py
──────────────────────────────────────────────────────────────────────────────
Blender 4.x — Run AFTER rig_cat.py.
Creates three animation Actions on CatRig:

  "idle"   — 40-frame loop: gentle breathing (Body scale), tail lazy wag
  "bounce" — 60-frame loop: full-body happy hop, ear flap, head tilt
  "walk"   — 32-frame loop: simple quadruped walk (leg swing, body bob)

Each action can be previewed in the NLA editor or played with the Timeline.
The actions are also what you'd export to FBX and reference in Roblox via
Animation.AnimationId (once uploaded to Creator).
"""

import bpy
import math
from mathutils import Euler

# ─── Helpers ─────────────────────────────────────────────────────────────────

def get_rig():
    obj = bpy.data.objects.get("CatRig")
    if not obj or obj.type != 'ARMATURE':
        raise RuntimeError("[animate_cat] CatRig not found — run rig_cat.py first.")
    return obj

def set_frame(f):
    bpy.context.scene.frame_set(f)

def pose_bone(rig, name):
    pb = rig.pose.bones.get(name)
    if pb is None:
        print(f"[animate_cat] Warning: pose bone '{name}' not found, skipping.")
    return pb

def key_loc(rig, bone_name, frame, xyz):
    pb = pose_bone(rig, bone_name)
    if pb is None: return
    set_frame(frame)
    pb.location = xyz
    pb.keyframe_insert("location", frame=frame)

def key_rot(rig, bone_name, frame, xyz_deg):
    pb = pose_bone(rig, bone_name)
    if pb is None: return
    pb.rotation_mode = 'XYZ'
    pb.rotation_euler = Euler(
        [math.radians(d) for d in xyz_deg], 'XYZ'
    )
    pb.keyframe_insert("rotation_euler", frame=frame)

def key_scale(rig, bone_name, frame, xyz):
    pb = pose_bone(rig, bone_name)
    if pb is None: return
    set_frame(frame)
    pb.scale = xyz
    pb.keyframe_insert("scale", frame=frame)

def clear_pose(rig):
    """Reset all pose bones to rest."""
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')
    bpy.ops.pose.select_all(action='SELECT')
    bpy.ops.pose.transforms_clear()
    bpy.ops.object.mode_set(mode='OBJECT')

def new_action(rig, name, frame_end):
    """Create (or replace) a named Action on the rig and return it."""
    existing = bpy.data.actions.get(name)
    if existing:
        bpy.data.actions.remove(existing)
    action = bpy.data.actions.new(name)
    action.frame_end = frame_end
    action.use_cyclic = True
    rig.animation_data_create()
    rig.animation_data.action = action
    # Clear pose so each action starts clean
    clear_pose(rig)
    return action

def set_interpolation_linear(action):
    for fc in action.fcurves:
        for kp in fc.keyframe_points:
            kp.interpolation = 'BEZIER'
            kp.handle_left_type  = 'AUTO_CLAMPED'
            kp.handle_right_type = 'AUTO_CLAMPED'

# ─── 1. IDLE ─────────────────────────────────────────────────────────────────
# 40 frames @ 24 fps ≈ 1.67 s loop
# Body: gentle scale breathe in Z (1.0 → 1.04 → 1.0)
# Head: very slight tilt forward (0° → 3° → 0°)
# Tail_1: lazy side wag (0° → 12° → 0° → -12° → 0°)

def bake_idle(rig):
    print("\n[animate_cat] Baking: idle …")
    new_action(rig, "idle", 40)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Body breathe (scale Z)
    for fr, sz in [(1, 1.00), (10, 1.04), (20, 1.01), (30, 1.04), (40, 1.00)]:
        key_scale(rig, "Body", fr, (1.0, 1.0, sz))

    # Head gentle bob
    for fr, rx in [(1, 0), (10, 3), (20, 0), (30, -2), (40, 0)]:
        key_rot(rig, "Head", fr, (rx, 0, 0))

    # Tail wag (Y-rotation)
    for fr, ry in [(1, 0), (8, 14), (16, 0), (24, -14), (32, 0), (40, 0)]:
        key_rot(rig, "Tail_1", fr, (0, ry, 0))
    for fr, ry in [(1, 0), (12, 20), (24, -20), (36, 0), (40, 0)]:
        key_rot(rig, "Tail_2", fr, (0, ry, 0))

    # Ear micro-twitch
    for fr, rz in [(1, 0), (20, 5), (40, 0)]:
        key_rot(rig, "Ear_L", fr, (0, 0,  rz))
        key_rot(rig, "Ear_R", fr, (0, 0, -rz))

    bpy.ops.object.mode_set(mode='OBJECT')
    print("  → idle done (40 frames)")

# ─── 2. BOUNCE ───────────────────────────────────────────────────────────────
# 60 frames @ 24 fps ≈ 2.5 s loop
# Root: translate up (+1.5 Z) then squash on landing
# Head: happy tilt back on peak, forward on land
# Ears: flap up on ascent

def bake_bounce(rig):
    print("[animate_cat] Baking: bounce …")
    new_action(rig, "bounce", 60)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Root translate (jump arc)
    # Frame 1 = ground, 15 = peak, 22 = land+squash, 30 = recover, 60 = loop
    for fr, z in [(1, 0), (5, 0.2), (15, 1.6), (22, -0.05), (28, 0), (60, 0)]:
        key_loc(rig, "Root", fr, (0, 0, z))

    # Body squash/stretch (scale Z)
    for fr, sz in [(1, 1.0), (5, 0.88), (15, 1.18), (22, 0.82), (28, 1.04), (35, 1.0), (60, 1.0)]:
        key_scale(rig, "Body", fr, (1.0, 1.0, sz))

    # Head tilt (happy)
    for fr, rx in [(1, 0), (10, -15), (15, -20), (22, 8), (30, 0), (60, 0)]:
        key_rot(rig, "Head", fr, (rx, 0, 0))

    # Ears flap up on ascent, down on land
    for fr, rx in [(1, 0), (8, -30), (15, -45), (22, 20), (30, 0), (60, 0)]:
        key_rot(rig, "Ear_L", fr, (rx, 0, 0))
        key_rot(rig, "Ear_R", fr, (rx, 0, 0))

    # Tail whip (forward on peak, back on land)
    for fr, rx in [(1, 0), (15, -60), (22, 40), (35, 0), (60, 0)]:
        key_rot(rig, "Tail_1", fr, (rx, 0, 0))
        key_rot(rig, "Tail_2", fr, (rx * 0.7, 0, 0))

    bpy.ops.object.mode_set(mode='OBJECT')
    print("  → bounce done (60 frames)")

# ─── 3. WALK ─────────────────────────────────────────────────────────────────
# 32 frames @ 24 fps ≈ 1.33 s loop
# Classic diagonal-pair gait: FL+BR swing together, FR+BL together.
# Body bobs up/down every 8 frames.
# Leg rotation is around X axis (swing forward = negative X in Blender).

WALK_SWING = 25   # degrees leg swings forward from rest
WALK_BACK  = -15  # degrees leg swings back

def bake_walk(rig):
    print("[animate_cat] Baking: walk …")
    new_action(rig, "walk", 32)
    bpy.context.view_layer.objects.active = rig
    bpy.ops.object.mode_set(mode='POSE')

    # Diagonal pair A: FL swings forward, BR swings back at frame 1
    # Diagonal pair B: FR swings forward, BL swings back at frame 1
    #
    # Key frames: 1, 9, 17, 25, 33(=1)
    #  Pair A forward at  1, neutral at 9,  back at 17, neutral at 25, forward at 33
    #  Pair B back    at  1, neutral at 9, forward at 17, neutral at 25, back    at 33

    pair_a_bones = ["Leg_FL", "Leg_BR"]
    pair_b_bones = ["Leg_FR", "Leg_BL"]

    a_angles = [(1, WALK_SWING), (9, 0), (17, WALK_BACK), (25, 0), (33, WALK_SWING)]
    b_angles = [(1, WALK_BACK),  (9, 0), (17, WALK_SWING), (25, 0), (33, WALK_BACK)]

    for bone_name in pair_a_bones:
        for fr, deg in a_angles:
            key_rot(rig, bone_name, fr, (-deg, 0, 0))

    for bone_name in pair_b_bones:
        for fr, deg in b_angles:
            key_rot(rig, bone_name, fr, (-deg, 0, 0))

    # Body up/down bob (every 8 frames, half-cycle of leg swing)
    for fr, tz in [(1, 0.0), (5, 0.08), (9, 0.0), (13, 0.08),
                   (17, 0.0), (21, 0.08), (25, 0.0), (29, 0.08), (33, 0.0)]:
        key_loc(rig, "Body", fr, (0, 0, tz))

    # Head follow (slight pitch following body bob)
    for fr, rx in [(1, 0), (5, -3), (9, 0), (13, -3),
                   (17, 0), (21, -3), (25, 0), (29, -3), (33, 0)]:
        key_rot(rig, "Head", fr, (rx, 0, 0))

    # Tail counter-swing (looks natural)
    for fr, ry in [(1, 10), (9, -10), (17, 10), (25, -10), (33, 10)]:
        key_rot(rig, "Tail_1", fr, (0, ry, 0))

    bpy.ops.object.mode_set(mode='OBJECT')
    print("  → walk done (32 frames)")

# ─── Run all three ────────────────────────────────────────────────────────────

rig = get_rig()

bake_idle(rig)
bake_bounce(rig)
bake_walk(rig)

# Leave the rig in OBJECT mode with the idle action active for playback
rig.animation_data.action = bpy.data.actions["idle"]
bpy.context.scene.frame_start = 1
bpy.context.scene.frame_end   = 40
bpy.context.scene.frame_set(1)

print("\n[animate_cat] All three actions created:")
print("  idle   — 40 frames (play in Timeline)")
print("  bounce — 60 frames")
print("  walk   — 32 frames")
print("\nTo switch action: Properties > Object Data > Animation > Action dropdown")
print("To export: File > Export > FBX  (check 'Selected Objects' + 'Armature' + 'Animation')")
