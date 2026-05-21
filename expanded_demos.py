#!/usr/bin/env python3
"""
EXPANDED DEMOS — 10 Build Recipes for Bits and Baubles
=======================================================
Original 5 + 5 new builds demonstrating the system's range.
All recipes use the same BrickRecipe format from ai_builder.py.

Usage:
    from expanded_demos import *
    builder = AIBuilder()
    
    # Build any recipe
    builder.build_from_recipe(recipe_space_station())
    builder.build_from_recipe(recipe_dragon(12, "red"), offset=(20, 0, 0))
    builder.build_from_recipe(recipe_treehouse(), offset=(-20, 0, 0))
"""

import json
from typing import List, Dict, Optional

# ============================================================
# COLOR PALETTE
# ============================================================

COLORS = {
    "red": "#CC3333", "blue": "#3366CC", "green": "#33AA33",
    "yellow": "#FFCC00", "white": "#EEEEEE", "black": "#222222",
    "gray": "#888888", "dark_gray": "#555555", "orange": "#FF8800",
    "purple": "#8833AA", "brown": "#8B4513", "tan": "#D2B48C",
    "pink": "#FF88AA", "cyan": "#33CCAA", "gold": "#CC9900",
    "silver": "#AAAAAA", "lime": "#88CC33", "navy": "#222266",
}

def hex_to_rgba(hex_str: str, alpha: float = 1.0):
    hex_str = hex_str.lstrip('#')
    return (int(hex_str[0:2], 16) / 255, int(hex_str[2:4], 16) / 255,
            int(hex_str[4:6], 16) / 255, alpha)


# ============================================================
# RECIPE BUILDER HELPERS
# ============================================================

def make_recipe(name: str, description: str, layers: list, colors: dict = None) -> dict:
    return {
        "name": name,
        "description": description,
        "layers": layers,
        "colors": colors or {"primary": "gray"}
    }

def layer(y: int, pieces: list) -> dict:
    return {"y": y, "pieces": pieces}

def piece(p_type: str, x: int, z: int, rot: int = 0, color: str = None) -> dict:
    p = {"type": p_type, "x": x, "z": z, "rot": rot}
    if color:
        p["color"] = color
    return p


# ============================================================
# ORIGINAL 5 BUILDS (enhanced)
# ============================================================

def recipe_house(width: int = 8, depth: int = 6, height: int = 5,
                 wall_color: str = "tan", roof_color: str = "brown") -> dict:
    """Cozy house with door, windows, pitched roof."""
    layers = []
    wc, rc = COLORS.get(wall_color, wall_color), COLORS.get(roof_color, roof_color)
    
    # Floor
    floor_pieces = []
    for fx in range(0, width, 2):
        for fz in range(0, depth, 4):
            z = min(fz, max(0, depth - 4))
            floor_pieces.append(piece("Plate_2x4", fx, z, 0, wc))
    layers.append(layer(0, floor_pieces))
    
    # Walls with door and windows
    for ly in range(1, height + 1):
        wall_pieces = []
        y_level = ly * 3
        for wx in range(0, width, 2):
            z_front = 0
            z_back = max(0, depth - 2)
            # Door cutout at front, center
            if ly in [1, 2] and wx == 2:
                pass  # door gap
            else:
                wall_pieces.append(piece("Brick_2x2", wx, z_front, 0, wc))
            wall_pieces.append(piece("Brick_2x2", wx, z_back, 0, wc))
        # Side walls
        for wz in range(2, max(2, depth - 2), 2):
            wall_pieces.append(piece("Brick_2x2", 0, wz, 0, wc))
            wall_pieces.append(piece("Brick_2x2", max(0, width - 2), wz, 0, wc))
        # Window at y=2, side wall
        if ly == 2 and depth > 4:
            wall_pieces.append(piece("Window_1x2x3", 0, 2, 0, "cyan"))
        layers.append(layer(y_level, wall_pieces))
    
    # Door
    door_pieces = [piece("Door_1x3x4", 2, 0, 0, COLORS.get("brown", "#8B4513"))]
    layers.append(layer(3, door_pieces))
    
    # Pitched roof
    roof_y = (height + 1) * 3
    roof_pieces = []
    for rx in range(0, width, 2):
        for rz in range(0, depth, 2):
            roof_pieces.append(piece("Slope_2x2_33", rx, rz, 0, rc))
    layers.append(layer(roof_y, roof_pieces))
    
    # Chimney
    chimney_x, chimney_z = width - 2, depth // 2
    for cy in range(height * 3, roof_y + 6, 3):
        layers.append(layer(cy, [piece("Brick_1x1", chimney_x, chimney_z, 0, "dark_gray")]))
    # Smoke
    layers.append(layer(roof_y + 9, [piece("Round_1x1", chimney_x, chimney_z, 0, "white")]))
    
    return make_recipe(
        f"House_{width}x{depth}x{height}",
        f"A cozy {width}x{depth} house with chimney, {height} bricks tall",
        layers,
        {"primary": wall_color, "roof": roof_color, "door": "brown", "window": "cyan"}
    )


def recipe_tower(diameter: int = 4, height: int = 10,
                 color: str = "gray", accent: str = "dark_gray") -> dict:
    """Castle tower with crenellations and arrow slits."""
    layers = []
    c, ac = COLORS.get(color, color), COLORS.get(accent, accent)
    
    # Base (wider for stability)
    for by in range(0, 3):
        base_pieces = []
        y = by * 3
        for bx in range(0, diameter + 2, 2):
            for bz in range(0, diameter + 2, 2):
                base_pieces.append(piece("Brick_2x2", bx, bz, 0, c))
        layers.append(layer(y, base_pieces))
    
    # Tower body
    for ly in range(1, height + 1):
        y = ly * 3
        wall_pieces = []
        for wx in range(0, diameter, 2):
            for wz in range(0, diameter, 2):
                # Arrow slit on one side
                if ly in [3, 6] and wz == 0 and wx == diameter // 2 - 1:
                    wall_pieces.append(piece("Window_1x2x3", wx, wz, 0, ac))
                else:
                    wall_pieces.append(piece("Brick_2x2", wx, wz, 0, c))
        layers.append(layer(y, wall_pieces))
    
    # Crenellations (battlements)
    cren_y = (height + 1) * 3
    cren_pieces = []
    for cx in range(0, diameter, 2):
        cren_pieces.append(piece("Brick_1x1", cx, 0, 0, c))
        cren_pieces.append(piece("Brick_1x1", cx, diameter - 1, 0, c))
    for cz in range(2, diameter - 2, 2):
        cren_pieces.append(piece("Brick_1x1", 0, cz, 0, c))
        cren_pieces.append(piece("Brick_1x1", diameter - 1, cz, 0, c))
    layers.append(layer(cren_y, cren_pieces))
    
    # Flag on top
    flag_y = cren_y + 3
    layers.append(layer(flag_y, [
        piece("Bar_1x2", diameter // 2, diameter // 2, 0, ac),
        piece("Tile_1x2", diameter // 2, diameter // 2 + 1, 90, "red")
    ]))
    
    return make_recipe(
        f"Tower_{diameter}x{height}",
        f"A {diameter}-stud castle tower, {height} bricks tall with crenellations and flag",
        layers,
        {"primary": color, "accent": accent, "flag": "red"}
    )


def recipe_bridge(length: int = 12, width: int = 4,
                  color: str = "gray", road_color: str = "dark_gray") -> dict:
    """Stone bridge with pillars and arched span."""
    layers = []
    c, rc = COLORS.get(color, color), COLORS.get(road_color, road_color)
    
    # Two pillars
    for pillar_z in [0, length - 4]:
        for py in range(0, 6):
            pillar_pieces = []
            for px in range(0, width, 2):
                for pz in range(0, 4, 2):
                    pillar_pieces.append(piece("Brick_2x2", px, pillar_z + pz, 0, c))
            layers.append(layer(py * 3, pillar_pieces))
    
    # Road surface (span between pillars)
    for rx in range(0, width, 2):
        for rz in range(2, length - 4, 4):
            layers.append(layer(15, [piece("Plate_2x4", rx, rz, 0, rc)]))
    
    # Railings
    for rz in range(0, length, 2):
        layers.append(layer(18, [
            piece("Bar_1x2", 0, rz, 0, c),
            piece("Bar_1x2", width - 2, rz, 0, c)
        ]))
    
    return make_recipe(
        f"Bridge_{length}x{width}",
        f"A {length}-stud stone bridge with twin pillars and railings",
        layers,
        {"primary": color, "road": road_color}
    )


def recipe_vehicle(width: int = 6, length: int = 10,
                   body_color: str = "green", wheel_color: str = "black") -> dict:
    """Off-road vehicle with wheels, cabin, and roll bars."""
    layers = []
    bc, wc = COLORS.get(body_color, body_color), COLORS.get(wheel_color, wheel_color)
    
    # Chassis (base layer)
    chassis_pieces = []
    for cx in range(0, width, 2):
        for cz in range(0, length, 4):
            chassis_pieces.append(piece("Plate_2x4", cx, cz, 0, bc))
    layers.append(layer(0, chassis_pieces))
    
    # Body sides
    for ly in range(1, 3):
        y = ly * 3
        body_pieces = []
        for bx in range(0, width, 2):
            body_pieces.append(piece("Brick_2x2", bx, 0, 0, bc))
            body_pieces.append(piece("Brick_2x2", bx, length - 2, 0, bc))
        for bz in range(2, length - 2, 2):
            body_pieces.append(piece("Brick_2x2", 0, bz, 0, bc))
            body_pieces.append(piece("Brick_2x2", width - 2, bz, 0, bc))
        layers.append(layer(y, body_pieces))
    
    # Hood and trunk (top layers)
    hood_pieces = []
    for hx in range(0, width, 2):
        for hz in range(2, length - 2, 2):
            hood_pieces.append(piece("Plate_2x2", hx, hz, 0, bc))
    layers.append(layer(9, hood_pieces))
    
    # 4 Wheels (placed at corners, slightly offset)
    wheel_positions = [
        (-1, 1, wc), (-1, length - 3, wc),
        (width - 1, 1, wc), (width - 1, length - 3, wc)
    ]
    for wx, wz, wc_hex in wheel_positions:
        layers.append(layer(-1, [piece("Wheel", wx, wz, 0, wc_hex)]))
    
    # Roll bars (open cabin)
    for rb_x in [0, width - 2]:
        layers.append(layer(12, [piece("Bar_1x2", rb_x, length // 2 - 1, 0, "silver")]))
    
    # Headlights
    layers.append(layer(6, [
        piece("Round_1x1", 0, 0, 0, "yellow"),
        piece("Round_1x1", width - 2, 0, 0, "yellow")
    ]))
    
    return make_recipe(
        f"Vehicle_{width}x{length}",
        f"An off-road vehicle with roll bars and 4 wheels",
        layers,
        {"body": body_color, "wheels": wheel_color, "lights": "yellow"}
    )


def recipe_tree(height: int = 8, foliage_color: str = "green",
                trunk_color: str = "brown") -> dict:
    """Park tree with layered canopy."""
    layers = []
    fc, tc = COLORS.get(foliage_color, foliage_color), COLORS.get(trunk_color, trunk_color)
    
    # Trunk
    for ty in range(0, height // 2):
        y = ty * 3
        layers.append(layer(y, [piece("Brick_1x1", 0, 0, 0, tc)]))
    
    # Canopy layers (expanding then contracting)
    canopy_start = height // 2
    canopy_radius = 1
    for cy in range(canopy_start, height + 2):
        y = cy * 3
        canopy_pieces = []
        # Expand then contract
        r = min(canopy_radius, 3)
        for cx in range(-r, r + 1):
            for cz in range(-r, r + 1):
                if abs(cx) + abs(cz) <= r + 1:
                    piece_type = "Plate_2x2" if (cx + cz) % 2 == 0 else "Round_1x1"
                    color = fc if cy < height else "lime"  # lighter top
                    canopy_pieces.append(piece(piece_type, cx * 2, cz * 2, 0, color))
        layers.append(layer(y, canopy_pieces))
        if cy < canopy_start + 2:
            canopy_radius += 1
        elif cy > canopy_start + 3:
            canopy_radius -= 1
    
    return make_recipe(
        f"Tree_H{height}",
        f"A {height}-layer park tree with tiered canopy",
        layers,
        {"trunk": trunk_color, "foliage": foliage_color}
    )


# ============================================================
# NEW BUILDS (5 additional)
# ============================================================

def recipe_space_station(size: int = 8, color: str = "white",
                         solar_color: str = "blue") -> dict:
    """Modular space station with solar panels and docking ports."""
    layers = []
    c, sc = COLORS.get(color, color), COLORS.get(solar_color, solar_color)
    
    # Central hub (3x3x3 core)
    for hy in range(0, 3):
        y = hy * 3
        hub_pieces = []
        for hx in range(0, 6, 2):
            for hz in range(0, 6, 2):
                hub_pieces.append(piece("Brick_2x2", hx, hz, 0, c))
        layers.append(layer(y, hub_pieces))
    
    # Solar panel arrays (extend from sides)
    for side in [-4, 8]:
        for sy in range(0, 6, 3):
            panel_pieces = []
            for px in range(0, 4):
                for pz in range(0, 6, 2):
                    panel_pieces.append(piece("Tile_1x2", side + px // 2 * 2, pz, 0, sc))
            layers.append(layer(sy, panel_pieces))
    
    # Docking port (top)
    layers.append(layer(12, [
        piece("Round_1x1", 2, 2, 0, "silver"),
        piece("Tile_1x1", 2, 3, 0, "red")  # marker light
    ]))
    
    # Antenna
    for ay in range(15, 24, 3):
        layers.append(layer(ay, [piece("Bar_1x2", 2, 2, 0, "silver")]))
    layers.append(layer(24, [piece("Round_1x1", 2, 2, 0, "red")]))
    
    return make_recipe(
        f"SpaceStation_{size}",
        "A modular space station with solar arrays and docking port",
        layers,
        {"primary": color, "solar": solar_color, "accent": "silver"}
    )


def recipe_dragon(length: int = 12, color: str = "red",
                  belly_color: str = "yellow") -> dict:
    """Low-poly dragon with segmented body, wings, and tail."""
    layers = []
    c, bc = COLORS.get(color, color), COLORS.get(belly_color, belly_color)
    
    # Head (blocky snout)
    for hy in range(0, 3):
        y = hy * 3
        head_pieces = []
        for hx in range(0, 4, 2):
            for hz in range(0, 4, 2):
                piece_color = bc if hy == 0 else c
                head_pieces.append(piece("Brick_2x2", hx, hz, 0, piece_color))
        layers.append(layer(y, head_pieces))
    # Eyes
    layers.append(layer(6, [
        piece("Round_1x1", 0, 2, 0, "green"),
        piece("Round_1x1", 2, 2, 0, "green")
    ]))
    # Horns
    layers.append(layer(9, [
        piece("Slope_2x1_45", 0, 0, 0, "white"),
        piece("Slope_2x1_45", 2, 0, 0, "white")
    ]))
    
    # Body segments (getting smaller toward tail)
    body_y = 0
    for seg in range(length // 2):
        seg_width = max(2, 4 - seg // 2)
        seg_pieces = []
        for sx in range(0, seg_width, 2):
            for sz in range(0, seg_width, 2):
                piece_color = bc if seg % 2 == 0 else c
                seg_pieces.append(piece("Brick_2x2", sx, 4 + seg * seg_width, 0, piece_color))
        layers.append(layer(body_y, seg_pieces))
        if seg % 2 == 0:
            body_y += 3
    
    # Wings (slopes on sides)
    for wy in [3, 6]:
        wing_pieces = []
        for wx in [-4, 4]:
            for wz in range(4, 8, 2):
                wing_pieces.append(piece("Slope_2x2_33", wx, wz, 0, c))
        layers.append(layer(wy, wing_pieces))
    
    # Tail (tapering)
    tail_z = 4 + (length // 2) * 2
    for ty in range(0, 4):
        y = ty * 3
        tail_size = max(1, 3 - ty)
        tail_pieces = []
        for tx in range(0, tail_size):
            tail_pieces.append(piece("Tile_1x1", tx, tail_z + ty * 2, 0, c))
        layers.append(layer(y, tail_pieces))
    
    return make_recipe(
        f"Dragon_L{length}",
        f"A low-poly dragon with wings, {length} segments long",
        layers,
        {"primary": color, "belly": belly_color, "eyes": "green", "horns": "white"}
    )


def recipe_treehouse(tree_height: int = 10, house_color: str = "tan",
                     tree_color: str = "brown") -> dict:
    """Tree with a house built into its canopy."""
    layers = []
    hc, tc = COLORS.get(house_color, house_color), COLORS.get(tree_color, tree_color)
    
    # Trunk
    for ty in range(0, tree_height // 2):
        y = ty * 3
        layers.append(layer(y, [piece("Brick_2x2", 4, 4, 0, tc)]))
    
    # Platform/floor
    plat_y = (tree_height // 2) * 3
    plat_pieces = []
    for px in range(0, 10, 2):
        for pz in range(0, 10, 2):
            if 2 <= px <= 6 and 2 <= pz <= 6:
                continue  # trunk hole
            plat_pieces.append(piece("Plate_2x2", px, pz, 0, tc))
    layers.append(layer(plat_y, plat_pieces))
    
    # House on platform
    for hy in range(1, 4):
        y = plat_y + hy * 3
        wall_pieces = []
        for wx in [0, 8]:
            for wz in range(0, 10, 2):
                wall_pieces.append(piece("Brick_2x2", wx, wz, 0, hc))
        for wz in [0, 8]:
            for wx in range(2, 8, 2):
                if hy == 2 and wx == 4 and wz == 8:
                    wall_pieces.append(piece("Door_1x3x4", wx, wz, 0, "brown"))
                else:
                    wall_pieces.append(piece("Brick_2x2", wx, wz, 0, hc))
        layers.append(layer(y, wall_pieces))
    
    # Roof
    roof_y = plat_y + 12
    roof_pieces = []
    for rx in range(0, 10, 2):
        for rz in range(0, 10, 2):
            roof_pieces.append(piece("Slope_2x2_33", rx, rz, 0, "green"))
    layers.append(layer(roof_y, roof_pieces))
    
    # Canopy around the house
    canopy_y = plat_y + 6
    for cx in [0, 8]:
        for cz in [0, 8]:
            layers.append(layer(canopy_y, [piece("Round_1x1", cx, cz, 0, "green")]))
    
    # Ladder
    for ly in range(0, plat_y, 3):
        layers.append(layer(ly, [piece("Bar_1x2", 4, 8, 0, "gray")]))
    
    return make_recipe(
        f"Treehouse_H{tree_height}",
        f"A treehouse built into a {tree_height}-layer tree with ladder and canopy",
        layers,
        {"house": house_color, "tree": tree_color, "roof": "green", "ladder": "gray"}
    )


def recipe_robot(height: int = 8, body_color: str = "silver",
                 eye_color: str = "cyan") -> dict:
    """Low-poly robot with head, torso, arms, and legs."""
    layers = []
    bc, ec = COLORS.get(body_color, body_color), COLORS.get(eye_color, eye_color)
    
    # Legs (two separate columns)
    for leg_x in [2, 6]:
        for ly in range(0, 3):
            y = ly * 3
            layers.append(layer(y, [piece("Brick_1x2", leg_x, 4, 0, "dark_gray")]))
    
    # Torso
    for ty in range(3, 6):
        y = ty * 3
        torso_pieces = []
        for tx in range(2, 8, 2):
            for tz in range(2, 8, 2):
                torso_pieces.append(piece("Brick_2x2", tx, tz, 0, bc))
        layers.append(layer(y, torso_pieces))
    
    # Chest plate
    layers.append(layer(18, [
        piece("Tile_2x2", 4, 4, 0, ec),
        piece("Round_1x1", 4, 2, 0, "red")  # button
    ]))
    
    # Arms (extending from sides)
    for arm_side in [0, 8]:
        for ay in [12, 15]:
            layers.append(layer(ay, [piece("Brick_1x2", arm_side, 4, 0, bc)]))
        # Hands
        layers.append(layer(9, [piece("Round_1x1", arm_side, 4, 0, "gray")]))
    
    # Head
    for hy in range(7, 9):
        y = hy * 3
        head_pieces = []
        for hx in range(2, 8, 2):
            for hz in range(2, 6, 2):
                head_pieces.append(piece("Brick_2x2", hx, hz, 0, bc))
        layers.append(layer(y, head_pieces))
    
    # Eyes
    layers.append(layer(27, [
        piece("Round_1x1", 2, 4, 0, ec),
        piece("Round_1x1", 6, 4, 0, ec)
    ]))
    
    # Antenna
    layers.append(layer(30, [piece("Bar_1x2", 4, 4, 0, "red")]))
    layers.append(layer(33, [piece("Round_1x1", 4, 4, 0, "red")]))
    
    return make_recipe(
        f"Robot_H{height}",
        f"A low-poly robot with articulated arms and glowing eyes",
        layers,
        {"body": body_color, "eyes": eye_color, "joints": "dark_gray", "accent": "red"}
    )


def recipe_castle(width: int = 12, depth: int = 10, height: int = 6,
                  wall_color: str = "gray", roof_color: str = "blue") -> dict:
    """Full castle with 4 towers, walls, gate, and keep."""
    layers = []
    wc, rc = COLORS.get(wall_color, wall_color), COLORS.get(roof_color, roof_color)
    
    # Four corner towers
    tower_positions = [(0, 0), (width - 2, 0), (0, depth - 2), (width - 2, depth - 2)]
    for tx, tz in tower_positions:
        for ty in range(0, height + 2):
            y = ty * 3
            t_pieces = [piece("Brick_2x2", tx, tz, 0, wc)]
            # Crenellations on top
            if ty == height + 1:
                t_pieces.append(piece("Brick_1x1", tx, tz, 0, wc))
            layers.append(layer(y, t_pieces))
    
    # Connecting walls
    for wy in range(0, height):
        y = wy * 3
        wall_pieces = []
        # Front wall with gate
        for wx in range(2, width - 2, 2):
            if wy < 2 and wx == width // 2 - 2:
                continue  # Gate opening
            wall_pieces.append(piece("Brick_2x2", wx, 0, 0, wc))
            wall_pieces.append(piece("Brick_2x2", wx, depth - 2, 0, wc))
        # Side walls
        for wz in range(2, depth - 2, 2):
            wall_pieces.append(piece("Brick_2x2", 0, wz, 0, wc))
            wall_pieces.append(piece("Brick_2x2", width - 2, wz, 0, wc))
        layers.append(layer(y, wall_pieces))
    
    # Gate (portcullis)
    gate_y = height * 3
    layers.append(layer(gate_y, [piece("Bar_1x2", width // 2 - 2, 0, 0, "silver")]))
    
    # Keep (central tower, taller)
    keep_x, keep_z = width // 2 - 1, depth // 2 - 1
    for ky in range(0, height + 4):
        y = ky * 3
        layers.append(layer(y, [piece("Brick_2x2", keep_x, keep_z, 0, wc)]))
    
    # Keep roof
    layers.append(layer((height + 4) * 3, [
        piece("Slope_2x2_33", keep_x, keep_z, 0, rc)
    ]))
    
    # Flag on keep
    layers.append(layer((height + 5) * 3, [
        piece("Bar_1x2", keep_x, keep_z, 0, "gold"),
        piece("Tile_1x1", keep_x + 1, keep_z, 0, "red")
    ]))
    
    return make_recipe(
        f"Castle_{width}x{depth}x{height}",
        f"A {width}x{depth} castle with 4 towers, walls, gate, and central keep",
        layers,
        {"walls": wall_color, "roof": roof_color, "flag": "red", "gate": "silver"}
    )


# ============================================================
# MASTER BUILD LIST
# ============================================================

ALL_RECIPES = [
    ("Cozy House", recipe_house),
    ("Castle Tower", recipe_tower),
    ("Stone Bridge", recipe_bridge),
    ("Off-Road Vehicle", recipe_vehicle),
    ("Park Tree", recipe_tree),
    ("Space Station", recipe_space_station),
    ("Dragon", recipe_dragon),
    ("Treehouse", recipe_treehouse),
    ("Robot", recipe_robot),
    ("Full Castle", recipe_castle),
]

def build_all(builder, spacing: int = 20):
    """Build all 10 recipes spaced apart on the grid.
    
    Args:
        builder: AIBuilder instance with build_from_recipe method
        spacing: Grid units between each build
    """
    offsets = [(i * spacing, 0, 0) for i in range(len(ALL_RECIPES))]
    for (name, recipe_fn), offset in zip(ALL_RECIPES, offsets):
        try:
            recipe = recipe_fn()
            if hasattr(builder, 'build_from_recipe'):
                builder.build_from_recipe(recipe, offset=offset)
            else:
                print(f"  [WARN] Builder missing build_from_recipe for {name}")
            print(f"  [OK] Built: {name}")
        except Exception as e:
            print(f"  [ERR] Failed: {name} — {e}")


if __name__ == "__main__":
    print("Bits and Baubles — Expanded Demos (10 builds)")
    print("Import and use with AIBuilder:")
    print("  from expanded_demos import build_all, recipe_dragon")
    print("  builder = AIBuilder()")
    print("  build_all(builder)")
    print("")
    for name, fn in ALL_RECIPES:
        r = fn()
        piece_count = sum(len(l["pieces"]) for l in r["layers"])
        print(f"  {name:20s} — {piece_count:3d} pieces — {r['description']}")
