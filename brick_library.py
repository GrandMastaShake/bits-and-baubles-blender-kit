#!/usr/bin/env python3
"""Bits and Baubles Brick Library for Blender
Generates 25 modular brick pieces organized into collections.
Run inside Blender's Scripting tab (Text Editor).

Author: BrickSmith - Modular Geometry Specialist
"""

import bpy
import bmesh
import math
import mathutils

# =============================================================================
# --- Constants ---
# =============================================================================
STUD = 0.008                    # 1 stud = 8mm
PLATE_HEIGHT = 0.004           # 3.2mm plate height
BRICK_HEIGHT = 0.012           # 9.6mm standard brick height
STUD_RADIUS = 0.003            # 2.4mm stud radius (4.8mm diameter)
STUD_HEIGHT = 0.002125         # 1.7mm stud height
WALL_THICKNESS = 0.0015        # 1.2mm wall thickness
INNER_WALL_OFFSET = 0.001      # 0.8mm inner wall offset

# Derived constants
STUD_DIAMETER = STUD_RADIUS * 2  # 0.006


# =============================================================================
# --- Utility Functions ---
# =============================================================================

def clear_scene():
    """Remove all mesh objects and custom collections, leaving a clean scene."""
    # Deselect all first
    bpy.ops.object.select_all(action='DESELECT')
    
    # Select and delete all mesh objects
    for obj in bpy.context.scene.objects:
        if obj.type in ('MESH', 'EMPTY', 'CURVE'):
            obj.select_set(True)
    bpy.ops.object.delete()
    
    # Remove all collections except the default Scene Collection
    for col in list(bpy.data.collections):
        if col.name not in ('Scene Collection', 'Master Collection'):
            for scene in bpy.data.scenes:
                if col.name in scene.collection.children:
                    scene.collection.children.unlink(col)
            bpy.data.collections.remove(col)
    
    # Clean up orphaned meshes and materials
    for mesh in list(bpy.data.meshes):
        if mesh.users == 0:
            bpy.data.meshes.remove(mesh)
    for mat in list(bpy.data.materials):
        if mat.users == 0:
            bpy.data.materials.remove(mat)


def create_material(name, color=(0.8, 0.15, 0.1)):
    """Create or retrieve a simple Principled BSDF material."""
    if name in bpy.data.materials:
        return bpy.data.materials[name]
    mat = bpy.data.materials.new(name=name)
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    # Clear default nodes
    for node in list(nodes):
        nodes.remove(node)
    # Add Principled BSDF
    bsdf = nodes.new(type='ShaderNodeBsdfPrincipled')
    bsdf.location = (0, 0)
    output = nodes.new(type='ShaderNodeOutputMaterial')
    output.location = (300, 0)
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])
    # Set color and properties
    bsdf.inputs['Base Color'].default_value = (color[0], color[1], color[2], 1.0)
    bsdf.inputs['Roughness'].default_value = 0.4
    bsdf.inputs['Specular'].default_value = 0.3
    return mat


def create_collection(name):
    """Create or retrieve a collection."""
    if name in bpy.data.collections:
        return bpy.data.collections[name]
    col = bpy.data.collections.new(name)
    bpy.context.scene.collection.children.link(col)
    return col


def set_origin_bottom_center(obj):
    """Set the object origin to the bottom-center of its bounding box."""
    # Calculate bounding box center and bottom
    bbox = [obj.matrix_world @ mathutils.Vector(corner) for corner in obj.bound_box]
    min_y = min(v.y for v in bbox)
    center_x = (min(v.x for v in bbox) + max(v.x for v in bbox)) / 2
    center_z = (min(v.z for v in bbox) + max(v.z for v in bbox)) / 2
    
    # Move object so bottom-center becomes the origin
    offset = mathutils.Vector((center_x, min_y, center_z))
    obj.location -= offset
    
    # Apply location to mesh (make origin = 0,0,0 in local space)
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.origin_set(type='ORIGIN_CURSOR', center='BOUNDS')
    # Reset cursor after
    bpy.context.scene.cursor.location = (0, 0, 0)


def apply_flat_shading(obj):
    """Apply flat shading to all mesh polygons."""
    mesh = obj.data
    for poly in mesh.polygons:
        poly.use_smooth = False
    mesh.update()


def add_object_to_collection(obj, col):
    """Link object to target collection and unlink from scene collection."""
    if obj.name not in col.objects:
        col.objects.link(obj)
    if obj.name in bpy.context.scene.collection.objects:
        bpy.context.scene.collection.objects.unlink(obj)


def finalize_mesh(bme, name, collection):
    """Create a mesh object from a bmesh, clean up, and return it."""
    bmesh.ops.recalc_face_normals(bme, faces=bme.faces)
    mesh = bpy.data.meshes.new(name="MESH_" + name)
    bme.to_mesh(mesh)
    bme.free()
    mesh.update()
    obj = bpy.data.objects.new(name, mesh)
    bpy.context.collection.objects.link(obj)
    add_object_to_collection(obj, collection)
    return obj


def add_studs(bme, studs_x, studs_z, height, stud_radius=STUD_RADIUS,
              stud_height=STUD_HEIGHT, stud_spacing=STUD):
    """Add stud cylinders on top of a brick at stud grid positions."""
    start_x = -((studs_x - 1) * stud_spacing) / 2
    start_z = -((studs_z - 1) * stud_spacing) / 2
    
    for ix in range(studs_x):
        for iz in range(studs_z):
            x = start_x + ix * stud_spacing
            z = start_z + iz * stud_spacing
            bmesh.ops.create_cone(
                bme,
                cap_ends=True,
                cap_tris=False,
                segments=16,
                radius1=stud_radius,
                radius2=stud_radius,
                depth=stud_height,
                matrix=mathutils.Matrix.Translation((x, height + stud_height / 2, z))
            )
    return bme


def make_hollow_brick(name, width, height, depth, collection,
                      add_studs_flag=False, studs_x=1, studs_z=1):
    """
    Create a hollow box (bottom + walls, open top) for B&B bricks/plates.
    Manually builds the geometry for proper hollow underside.
    """
    bme = bmesh.new()
    hw = width / 2
    hd = depth / 2
    ht = height
    wt = WALL_THICKNESS
    
    # --- Vertices ---
    # Bottom face (y=0)
    v0 = bme.verts.new((-hw, 0, -hd))       # outer back-left
    v1 = bme.verts.new(( hw, 0, -hd))       # outer back-right
    v2 = bme.verts.new(( hw, 0,  hd))       # outer front-right
    v3 = bme.verts.new((-hw, 0,  hd))       # outer front-left
    
    v4 = bme.verts.new((-hw + wt, wt, -hd + wt))  # inner back-left
    v5 = bme.verts.new(( hw - wt, wt, -hd + wt))  # inner back-right
    v6 = bme.verts.new(( hw - wt, wt,  hd - wt))  # inner front-right
    v7 = bme.verts.new((-hw + wt, wt,  hd - wt))  # inner front-left
    
    # Top outer rim (y=height)
    v8  = bme.verts.new((-hw, ht, -hd))
    v9  = bme.verts.new(( hw, ht, -hd))
    v10 = bme.verts.new(( hw, ht,  hd))
    v11 = bme.verts.new((-hw, ht,  hd))
    
    # Top inner rim (y=height)
    v12 = bme.verts.new((-hw + wt, ht, -hd + wt))
    v13 = bme.verts.new(( hw - wt, ht, -hd + wt))
    v14 = bme.verts.new(( hw - wt, ht,  hd - wt))
    v15 = bme.verts.new((-hw + wt, ht,  hd - wt))
    
    # --- Faces ---
    # Bottom (outer ring + inner fill)
    bme.faces.new((v0, v1, v5, v4))   # bottom back strip
    bme.faces.new((v1, v2, v6, v5))   # bottom right strip
    bme.faces.new((v2, v3, v7, v6))   # bottom front strip
    bme.faces.new((v3, v0, v4, v7))   # bottom left strip
    bme.faces.new((v4, v5, v6, v7))   # bottom inner fill
    
    # Outer walls
    bme.faces.new((v0, v8,  v9,  v1))  # back
    bme.faces.new((v1, v9,  v10, v2))  # right
    bme.faces.new((v2, v10, v11, v3))  # front
    bme.faces.new((v3, v11, v8,  v0))  # left
    
    # Inner walls
    bme.faces.new((v5, v4, v12, v13))  # back inner
    bme.faces.new((v6, v5, v13, v14))  # right inner
    bme.faces.new((v7, v6, v14, v15))  # front inner
    bme.faces.new((v4, v7, v15, v12))  # left inner
    
    # Top rim
    bme.faces.new((v8,  v12, v13, v9))   # back rim
    bme.faces.new((v9,  v13, v14, v10))  # right rim
    bme.faces.new((v10, v14, v15, v11))  # front rim
    bme.faces.new((v11, v15, v12, v8))   # left rim
    
    # Add studs if requested
    if add_studs_flag and studs_x > 0 and studs_z > 0:
        bme = add_studs(bme, studs_x, studs_z, ht)
    
    obj = finalize_mesh(bme, name, collection)
    return obj


# =============================================================================
# --- Foundation: 5 Plates ---
# =============================================================================

def make_Plate_1x1(collection):
    """Plate 1x1: 1 stud, plate height (0.008 x 0.004 x 0.008)."""
    return make_hollow_brick("Plate_1x1", STUD, PLATE_HEIGHT, STUD,
                             collection, add_studs_flag=True, studs_x=1, studs_z=1)


def make_Plate_1x2(collection):
    """Plate 1x2: 1x2 studs, plate height (0.008 x 0.004 x 0.016)."""
    return make_hollow_brick("Plate_1x2", STUD, PLATE_HEIGHT, 2 * STUD,
                             collection, add_studs_flag=True, studs_x=1, studs_z=2)


def make_Plate_2x2(collection):
    """Plate 2x2: 2x2 studs, plate height (0.016 x 0.004 x 0.016)."""
    return make_hollow_brick("Plate_2x2", 2 * STUD, PLATE_HEIGHT, 2 * STUD,
                             collection, add_studs_flag=True, studs_x=2, studs_z=2)


def make_Plate_2x4(collection):
    """Plate 2x4: 2x4 studs, plate height (0.016 x 0.004 x 0.032)."""
    return make_hollow_brick("Plate_2x4", 2 * STUD, PLATE_HEIGHT, 4 * STUD,
                             collection, add_studs_flag=True, studs_x=2, studs_z=4)


def make_Plate_4x4(collection):
    """Plate 4x4: 4x4 studs, plate height (0.032 x 0.004 x 0.032)."""
    return make_hollow_brick("Plate_4x4", 4 * STUD, PLATE_HEIGHT, 4 * STUD,
                             collection, add_studs_flag=True, studs_x=4, studs_z=4)


# =============================================================================
# --- Standard Bricks: 5 Bricks ---
# =============================================================================

def make_Brick_1x1(collection):
    """Brick 1x1: 1 stud, standard height, hollow underside (0.008 x 0.012 x 0.008)."""
    return make_hollow_brick("Brick_1x1", STUD, BRICK_HEIGHT, STUD,
                             collection, add_studs_flag=True, studs_x=1, studs_z=1)


def make_Brick_1x2(collection):
    """Brick 1x2: 1x2 studs, standard height, hollow underside (0.008 x 0.012 x 0.016)."""
    return make_hollow_brick("Brick_1x2", STUD, BRICK_HEIGHT, 2 * STUD,
                             collection, add_studs_flag=True, studs_x=1, studs_z=2)


def make_Brick_1x4(collection):
    """Brick 1x4: 1x4 studs, standard height, hollow underside (0.008 x 0.012 x 0.032)."""
    return make_hollow_brick("Brick_1x4", STUD, BRICK_HEIGHT, 4 * STUD,
                             collection, add_studs_flag=True, studs_x=1, studs_z=4)


def make_Brick_2x2(collection):
    """Brick 2x2: 2x2 studs, standard height, hollow underside (0.016 x 0.012 x 0.016)."""
    return make_hollow_brick("Brick_2x2", 2 * STUD, BRICK_HEIGHT, 2 * STUD,
                             collection, add_studs_flag=True, studs_x=2, studs_z=2)


def make_Brick_2x4(collection):
    """Brick 2x4: 2x4 studs, standard height, hollow underside (0.016 x 0.012 x 0.032)."""
    return make_hollow_brick("Brick_2x4", 2 * STUD, BRICK_HEIGHT, 4 * STUD,
                             collection, add_studs_flag=True, studs_x=2, studs_z=4)


# =============================================================================
# --- Slopes: 4 Angled Pieces ---
# =============================================================================

def make_Slope_2x1_45(collection):
    """
    Slope 2x1 45: 2 studs wide (X), 1 stud deep (Z), 45-degree sloped face.
    Dimensions: 0.016 x 0.012 x 0.008
    Back edge at full height, front slopes to ground.
    """
    bme = bmesh.new()
    w = 2 * STUD
    d = 1 * STUD
    h = BRICK_HEIGHT
    hw = w / 2
    hd = d / 2
    
    v0 = bme.verts.new((-hw, 0, -hd))   # back-left bottom
    v1 = bme.verts.new(( hw, 0, -hd))   # back-right bottom
    v2 = bme.verts.new(( hw, h, -hd))   # back-right top
    v3 = bme.verts.new((-hw, h, -hd))   # back-left top
    v4 = bme.verts.new((-hw, 0,  hd))   # front-left bottom
    v5 = bme.verts.new(( hw, 0,  hd))   # front-right bottom
    
    # Bottom
    bme.faces.new((v0, v1, v5, v4))
    # Back face
    bme.faces.new((v0, v3, v2, v1))
    # Left face (triangle)
    bme.faces.new((v3, v0, v4))
    # Right face (triangle)
    bme.faces.new((v1, v2, v5))
    # Slope face (top)
    bme.faces.new((v2, v3, v4, v5))
    
    # Add 2 studs along the back at standard positions
    for ix in range(2):
        x = -STUD / 2 + ix * STUD
        z = -hd / 2
        bmesh.ops.create_cone(
            bme, cap_ends=True, cap_tris=False, segments=16,
            radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
            matrix=mathutils.Matrix.Translation((x, h + STUD_HEIGHT / 2, z))
        )
    
    return finalize_mesh(bme, "Slope_2x1_45", collection)


def make_Slope_2x2_33(collection):
    """
    Slope 2x2 33: 2 studs wide, 2 studs deep, ~33-degree slope.
    Dimensions: 0.016 x 0.012 x 0.016
    """
    bme = bmesh.new()
    w = 2 * STUD
    d = 2 * STUD
    h = BRICK_HEIGHT
    hw = w / 2
    hd = d / 2
    
    front_h = max(0.001, h - d * math.tan(math.radians(33)))
    
    v0 = bme.verts.new((-hw, 0, -hd))       # back-left bottom
    v1 = bme.verts.new(( hw, 0, -hd))       # back-right bottom
    v2 = bme.verts.new(( hw, h, -hd))       # back-right top
    v3 = bme.verts.new((-hw, h, -hd))       # back-left top
    v4 = bme.verts.new((-hw, front_h, hd))  # front-left top
    v5 = bme.verts.new(( hw, front_h, hd))  # front-right top
    v6 = bme.verts.new((-hw, 0, hd))        # front-left bottom
    v7 = bme.verts.new(( hw, 0, hd))        # front-right bottom
    
    bme.faces.new((v0, v1, v7, v6))   # bottom
    bme.faces.new((v0, v3, v2, v1))   # back
    bme.faces.new((v0, v6, v4, v3))   # left
    bme.faces.new((v1, v2, v5, v7))   # right
    bme.faces.new((v6, v7, v5, v4))   # front
    bme.faces.new((v2, v3, v4, v5))   # slope top
    
    # Add 2x2 studs at standard positions (on flat back portion)
    for ix in range(2):
        for iz in range(2):
            x = -STUD / 2 + ix * STUD
            z = -STUD / 2 + iz * STUD
            bmesh.ops.create_cone(
                bme, cap_ends=True, cap_tris=False, segments=16,
                radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
                matrix=mathutils.Matrix.Translation((x, h + STUD_HEIGHT / 2, z))
            )
    
    return finalize_mesh(bme, "Slope_2x2_33", collection)


def make_Wedge_2x2(collection):
    """
    Wedge 2x2: Triangular wedge shape.
    Full height at back, tapering to a ridge at front center.
    Dimensions: 0.016 x 0.012 x 0.016
    """
    bme = bmesh.new()
    w = 2 * STUD
    d = 2 * STUD
    h = BRICK_HEIGHT
    hw = w / 2
    hd = d / 2
    
    v0 = bme.verts.new((-hw, 0, -hd))    # back-left bottom
    v1 = bme.verts.new(( hw, 0, -hd))    # back-right bottom
    v2 = bme.verts.new(( hw, h, -hd))    # back-right top
    v3 = bme.verts.new((-hw, h, -hd))    # back-left top
    v4 = bme.verts.new((0, h / 2, hd))   # front ridge mid
    v5 = bme.verts.new((0, 0, hd))       # front ridge bottom
    
    bme.faces.new((v0, v1, v5))       # bottom (tri)
    bme.faces.new((v0, v3, v2, v1))   # back
    bme.faces.new((v0, v5, v4, v3))   # left slope
    bme.faces.new((v1, v2, v4, v5))   # right slope
    bme.faces.new((v3, v4, v2))       # top (tri)
    
    # Single stud at back center
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, -hd / 2))
    )
    
    return finalize_mesh(bme, "Wedge_2x2", collection)


def make_Corner_Slope_2x2(collection):
    """
    Corner Slope 2x2: Corner piece with slopes on two adjacent faces.
    0.016 x 0.012 x 0.016. Slopes meet at front-left corner.
    """
    bme = bmesh.new()
    w = 2 * STUD
    d = 2 * STUD
    h = BRICK_HEIGHT
    hw = w / 2
    hd = d / 2
    
    v0 = bme.verts.new((-hw, 0, -hd))   # back-left
    v1 = bme.verts.new(( hw, 0, -hd))   # back-right
    v2 = bme.verts.new(( hw, h, -hd))   # back-right top
    v3 = bme.verts.new(( hw, 0,  hd))   # front-right
    v4 = bme.verts.new(( hw, h,  hd))   # front-right top
    v5 = bme.verts.new((-hw, 0,  hd))   # front-left (lowest corner)
    v6 = bme.verts.new((-hw, h, -hd))   # back-left top
    
    bme.faces.new((v0, v1, v3, v5))     # bottom
    bme.faces.new((v0, v6, v2, v1))     # back
    bme.faces.new((v1, v2, v4, v3))     # right (vertical)
    bme.faces.new((v3, v4, v5))         # front (slope triangle)
    bme.faces.new((v0, v5, v6))         # left (slope triangle)
    bme.faces.new((v2, v6, v5, v4))     # diagonal slope
    
    # Two studs at the back-right corner area
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((hw / 2, h + STUD_HEIGHT / 2, -hd / 2))
    )
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((hw / 2, h + STUD_HEIGHT / 2, hd / 2))
    )
    
    return finalize_mesh(bme, "Corner_Slope_2x2", collection)


# =============================================================================
# --- Details: 6 Flat/Round Pieces ---
# =============================================================================

def make_Round_1x1(collection):
    """
    Round 1x1: Cylindrical brick, 1 stud diameter, standard brick height.
    Dimensions: 0.008 diameter x 0.012 height.
    """
    bme = bmesh.new()
    r = STUD / 2
    h = BRICK_HEIGHT
    
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=24,
        radius1=r, radius2=r, depth=h,
        matrix=mathutils.Matrix.Translation((0, h / 2, 0))
    )
    # Stud on top
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, 0))
    )
    
    return finalize_mesh(bme, "Round_1x1", collection)


def make_Tile_1x1(collection):
    """Tile 1x1: 0.008 x 0.004 x 0.008, NO stud (smooth top)."""
    bme = bmesh.new()
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(STUD, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(PLATE_HEIGHT, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(STUD, 4, (0, 0, 1))
    )
    return finalize_mesh(bme, "Tile_1x1", collection)


def make_Tile_1x2(collection):
    """Tile 1x2: 0.008 x 0.004 x 0.016, NO studs (smooth top)."""
    bme = bmesh.new()
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(STUD, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(PLATE_HEIGHT, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(2 * STUD, 4, (0, 0, 1))
    )
    return finalize_mesh(bme, "Tile_1x2", collection)


def make_Tile_2x2(collection):
    """Tile 2x2: 0.016 x 0.004 x 0.016, NO studs (smooth top)."""
    bme = bmesh.new()
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(2 * STUD, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(PLATE_HEIGHT, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(2 * STUD, 4, (0, 0, 1))
    )
    return finalize_mesh(bme, "Tile_2x2", collection)


def make_Bar_1x2(collection):
    """
    Bar 1x2: Thin bar/grille piece, 0.008 x 0.004 x 0.016.
    Has a small raised ridge on top for detail.
    """
    bme = bmesh.new()
    w = STUD
    d = 2 * STUD
    h = PLATE_HEIGHT
    
    # Main body
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Raised ridge
    ridge_h = PLATE_HEIGHT * 0.4
    ridge_w = w * 0.5
    ridge_d = d * 0.85
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, h + ridge_h / 2, 0)) @
               mathutils.Matrix.Scale(ridge_w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(ridge_h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(ridge_d, 4, (0, 0, 1))
    )
    
    return finalize_mesh(bme, "Bar_1x2", collection)


def make_Jumper_2x2(collection):
    """
    Jumper 2x2: 0.016 x 0.004 x 0.016, single centered stud.
    Used for half-stud offset connections.
    """
    bme = bmesh.new()
    w = 2 * STUD
    d = 2 * STUD
    h = PLATE_HEIGHT
    
    # Base plate
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Single centered stud
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, 0))
    )
    
    return finalize_mesh(bme, "Jumper_2x2", collection)


# =============================================================================
# --- Special: 5 Pieces ---
# =============================================================================

def make_Column_1x1x5(collection):
    """
    Column 1x1x5: Tall column, 1 stud square, 5 brick heights.
    0.008 x 0.060 x 0.008 with a stud on top.
    """
    bme = bmesh.new()
    w = STUD
    d = STUD
    h = 5 * BRICK_HEIGHT  # 0.060
    
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Stud on top
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, 0))
    )
    
    return finalize_mesh(bme, "Column_1x1x5", collection)


def make_Macaroni_2x2(collection):
    """
    Macaroni 2x2: Quarter-cylinder curved brick.
    Outer radius 2 studs, inner radius 1 stud, standard brick height.
    0.016 x 0.012 x 0.016 (bounding box).
    """
    bme = bmesh.new()
    outer_r = 2 * STUD
    inner_r = 1 * STUD
    h = BRICK_HEIGHT
    segments = 16
    
    outer_vb = []
    outer_vt = []
    inner_vb = []
    inner_vt = []
    
    for i in range(segments + 1):
        angle = math.radians(90 * i / segments)
        ca = math.cos(angle)
        sa = math.sin(angle)
        
        ox = outer_r * sa
        oz = -outer_r * ca
        outer_vb.append(bme.verts.new((ox, 0, oz)))
        outer_vt.append(bme.verts.new((ox, h, oz)))
        
        ix = inner_r * sa
        iz = -inner_r * ca
        inner_vb.append(bme.verts.new((ix, 0, iz)))
        inner_vt.append(bme.verts.new((ix, h, iz)))
    
    for i in range(segments):
        # Outer curved face
        bme.faces.new((outer_vb[i], outer_vb[i + 1], outer_vt[i + 1], outer_vt[i]))
        # Inner curved face (reversed winding)
        bme.faces.new((inner_vb[i + 1], inner_vb[i], inner_vt[i], inner_vt[i + 1]))
        # Top face
        bme.faces.new((outer_vt[i], outer_vt[i + 1], inner_vt[i + 1], inner_vt[i]))
        # Bottom face
        bme.faces.new((outer_vb[i + 1], outer_vb[i], inner_vb[i], inner_vb[i + 1]))
    
    # End caps
    bme.faces.new((outer_vb[0], outer_vt[0], inner_vt[0], inner_vb[0]))
    bme.faces.new((inner_vb[-1], inner_vt[-1], outer_vt[-1], outer_vb[-1]))
    
    # Stud at the outer corner area
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation(((outer_r + inner_r) / 2, h + STUD_HEIGHT / 2, -(outer_r + inner_r) / 2))
    )
    
    return finalize_mesh(bme, "Macaroni_2x2", collection)


def make_Door_1x3x4(collection):
    """
    Door 1x3x4: Door frame with cutout.
    0.008 wide x 0.048 tall x 0.024 deep.
    U-shaped frame with open center.
    """
    bme = bmesh.new()
    w = 1 * STUD
    d = 3 * STUD
    h = 4 * BRICK_HEIGHT
    hw = w / 2
    hd = d / 2
    wt = WALL_THICKNESS
    
    door_h = 3 * BRICK_HEIGHT
    
    # Bottom sill
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt / 2, 0)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Left jamb
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt + door_h / 2, -hd + wt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(door_h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 0, 1))
    )
    # Right jamb
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt + door_h / 2, hd - wt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(door_h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 0, 1))
    )
    # Top lintel
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, h - wt / 2, 0)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Back panel (thin wall)
    bt = wt * 0.5
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, h / 2, -hd + bt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(bt, 4, (0, 0, 1))
    )
    # Stud on top
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, 0))
    )
    
    return finalize_mesh(bme, "Door_1x3x4", collection)


def make_Window_1x2x3(collection):
    """
    Window 1x2x3: Window frame with opening.
    0.008 wide x 0.036 tall x 0.016 deep.
    """
    bme = bmesh.new()
    w = 1 * STUD
    d = 2 * STUD
    h = 3 * BRICK_HEIGHT
    hd = d / 2
    wt = WALL_THICKNESS
    
    win_h = 2 * BRICK_HEIGHT
    
    # Bottom sill
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt / 2, 0)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Left jamb
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt + win_h / 2, -hd + wt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(win_h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 0, 1))
    )
    # Right jamb
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt + win_h / 2, hd - wt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(win_h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 0, 1))
    )
    # Top lintel
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, h - wt / 2, 0)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(wt, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d, 4, (0, 0, 1))
    )
    # Crossbar (mullion)
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, wt + win_h / 2, 0)) @
               mathutils.Matrix.Scale(w * 0.7, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(wt * 0.5, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(d * 0.75, 4, (0, 0, 1))
    )
    # Back panel
    bt = wt * 0.5
    bmesh.ops.create_cube(
        bme, size=1.0,
        matrix=mathutils.Matrix.Translation((0, h / 2, -hd + bt / 2)) @
               mathutils.Matrix.Scale(w, 4, (1, 0, 0)) @
               mathutils.Matrix.Scale(h, 4, (0, 1, 0)) @
               mathutils.Matrix.Scale(bt, 4, (0, 0, 1))
    )
    # Stud on top
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=STUD_RADIUS, radius2=STUD_RADIUS, depth=STUD_HEIGHT,
        matrix=mathutils.Matrix.Translation((0, h + STUD_HEIGHT / 2, 0))
    )
    
    return finalize_mesh(bme, "Window_1x2x3", collection)


def make_Wheel(collection):
    """
    Wheel: Standalone round wheel piece.
    Diameter 0.012 (1.5 studs), width 0.004 (half stud).
    Includes a hub cap detail.
    """
    bme = bmesh.new()
    wheel_r = 0.006
    wheel_w = 0.004
    
    # Main wheel (cylinder oriented on X axis for rolling)
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=24,
        radius1=wheel_r, radius2=wheel_r, depth=wheel_w,
        matrix=mathutils.Matrix.Translation((0, wheel_r, 0)) @
               mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
    )
    # Hub cap (smaller cylinder in center)
    hub_r = wheel_r * 0.35
    hub_w = wheel_w * 1.3
    bmesh.ops.create_cone(
        bme, cap_ends=True, cap_tris=False, segments=16,
        radius1=hub_r, radius2=hub_r, depth=hub_w,
        matrix=mathutils.Matrix.Translation((0, wheel_r, 0)) @
               mathutils.Matrix.Rotation(math.radians(90), 4, 'Y')
    )
    
    return finalize_mesh(bme, "Wheel", collection)


# =============================================================================
# --- Main ---
# =============================================================================

def main():
    """Create the full Bits and Baubles brick library: 25 pieces in 5 collections."""
    print("=" * 60)
    print("  Bits and Baubles Brick Library Generator")
    print("  Creating 25 modular brick pieces...")
    print("=" * 60)
    
    clear_scene()
    
    brick_mat = create_material("BrickPlastic", (0.8, 0.15, 0.1))
    
    col_foundation = create_collection("Foundation")
    col_bricks = create_collection("Bricks")
    col_slopes = create_collection("Slopes")
    col_details = create_collection("Details")
    col_special = create_collection("Special")
    
    pieces = []
    
    # --- Foundation (5 plates) ---
    print("Creating Foundation plates (5 pieces)...")
    pieces.append(make_Plate_1x1(col_foundation))
    pieces.append(make_Plate_1x2(col_foundation))
    pieces.append(make_Plate_2x2(col_foundation))
    pieces.append(make_Plate_2x4(col_foundation))
    pieces.append(make_Plate_4x4(col_foundation))
    
    # --- Standard Bricks (5 pieces) ---
    print("Creating Standard bricks (5 pieces)...")
    pieces.append(make_Brick_1x1(col_bricks))
    pieces.append(make_Brick_1x2(col_bricks))
    pieces.append(make_Brick_1x4(col_bricks))
    pieces.append(make_Brick_2x2(col_bricks))
    pieces.append(make_Brick_2x4(col_bricks))
    
    # --- Slopes (4 pieces) ---
    print("Creating Slopes (4 pieces)...")
    pieces.append(make_Slope_2x1_45(col_slopes))
    pieces.append(make_Slope_2x2_33(col_slopes))
    pieces.append(make_Wedge_2x2(col_slopes))
    pieces.append(make_Corner_Slope_2x2(col_slopes))
    
    # --- Details (6 pieces) ---
    print("Creating Detail pieces (6 pieces)...")
    pieces.append(make_Round_1x1(col_details))
    pieces.append(make_Tile_1x1(col_details))
    pieces.append(make_Tile_1x2(col_details))
    pieces.append(make_Tile_2x2(col_details))
    pieces.append(make_Bar_1x2(col_details))
    pieces.append(make_Jumper_2x2(col_details))
    
    # --- Special (5 pieces) ---
    print("Creating Special pieces (5 pieces)...")
    pieces.append(make_Column_1x1x5(col_special))
    pieces.append(make_Macaroni_2x2(col_special))
    pieces.append(make_Door_1x3x4(col_special))
    pieces.append(make_Window_1x2x3(col_special))
    pieces.append(make_Wheel(col_special))
    
    # --- Post-processing ---
    print("Applying post-processing (shading, materials, origins)...")
    for obj in pieces:
        if obj is None:
            continue
        apply_flat_shading(obj)
        # Set origin: move object so its bottom-center is at world origin
        # then snap the origin there
        set_origin_bottom_center(obj)
        # Assign material
        if len(obj.data.materials) == 0:
            obj.data.materials.append(brick_mat)
        else:
            obj.data.materials[0] = brick_mat
    
    # Layout pieces in a grid for viewing
    print("Arranging pieces in preview grid...")
    categories = [
        (col_foundation, 0),
        (col_bricks, 1),
        (col_slopes, 2),
        (col_details, 3),
        (col_special, 4),
    ]
    spacing = 0.05
    for col, col_idx in categories:
        for row_idx, obj in enumerate(col.objects):
            if obj.type == 'MESH':
                obj.location.x = col_idx * spacing
                obj.location.z = row_idx * spacing
                # Y stays at 0 (origin is at bottom)
    
    print()
    print("=" * 60)
    print("  SUCCESS: 25 B&B pieces created!")
    print("=" * 60)
    print()
    print(f"  Foundation : {len(col_foundation.objects)} pieces")
    print(f"  Bricks     : {len(col_bricks.objects)} pieces")
    print(f"  Slopes     : {len(col_slopes.objects)} pieces")
    print(f"  Details    : {len(col_details.objects)} pieces")
    print(f"  Special    : {len(col_special.objects)} pieces")
    print()
    print("  Run inside Blender's Scripting tab (Text Editor).")
    print("  Press 'Run Script' to generate all pieces.")
    print("=" * 60)


if __name__ == "__main__":
    main()
