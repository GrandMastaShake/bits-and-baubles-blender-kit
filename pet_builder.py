#!/usr/bin/env python3
"""
PET BUILDER — Modular Pet Assembly System
==========================================
Reads pet_parts_system.json and assembles creatures in Blender.
Mix-and-match parts, generate random pets, or build pre-designed ones.

Usage:
    from pet_builder import PetBuilder
    
    builder = PetBuilder()
    
    # Build a pre-designed pet
    builder.build_prebuilt("Golden Retriever", offset=(0, 0, 0))
    
    # Build a random pet
    builder.build_random("legendary", offset=(10, 0, 0))
    
    # Build from custom part selection
    builder.build_from_parts({
        "head": "head_round",
        "ears": "ears_floppy",
        "eyes": "eyes_sparkle",
        "body": "body_chubby",
        "tail": "tail_fluffy",
        "pattern": "pattern_galaxy"
    }, colors={"primary": "#FF69B4"}, offset=(20, 0, 0))
"""

import bpy
import json
import random
import math
from pathlib import Path
from typing import Dict, List, Optional, Tuple

# ============================================================
# CONSTANTS
# ============================================================

STUD = 0.008
PLATE_H = 0.004
BRICK_H = 0.012

COLOR_MAP = {
    "red": "#CC3333", "blue": "#3366CC", "green": "#33AA33",
    "yellow": "#FFCC00", "white": "#EEEEEE", "black": "#222222",
    "gray": "#888888", "dark_gray": "#555555", "orange": "#FF8800",
    "purple": "#8833AA", "brown": "#8B4513", "tan": "#D2B48C",
    "pink": "#FF88AA", "cyan": "#33CCAA", "gold": "#CC9900",
    "silver": "#AAAAAA", "lime": "#88CC33", "navy": "#222266",
}

def resolve_color(color_val) -> str:
    """Resolve color name or hex to hex string."""
    if isinstance(color_val, str):
        if color_val.startswith('#'):
            return color_val
        return COLOR_MAP.get(color_val.lower(), "#888888")
    return "#888888"

def hex_to_rgba(hex_str: str, alpha: float = 1.0) -> Tuple[float, float, float, float]:
    hex_str = hex_str.lstrip('#')
    return (int(hex_str[0:2], 16) / 255, int(hex_str[2:4], 16) / 255,
            int(hex_str[4:6], 16) / 255, alpha)


# ============================================================
# MATERIAL SYSTEM
# ============================================================

class PetMaterialSystem:
    """Manages materials for pet parts with pattern support."""
    
    def __init__(self):
        self._materials = {}
    
    def get_material(self, name: str, color_hex: str, pattern: str = "solid") -> bpy.types.Material:
        key = f"{name}_{color_hex}_{pattern}"
        if key in self._materials:
            return self._materials[key]
        
        mat = bpy.data.materials.new(name=key)
        mat.use_nodes = True
        nodes = mat.node_tree.nodes
        links = mat.node_tree.links
        
        principled = nodes["Principled BSDF"]
        r, g, b = hex_to_rgba(color_hex)
        principled.inputs["Base Color"].default_value = (r, g, b, 1.0)
        principled.inputs["Roughness"].default_value = 0.6
        
        # Pattern: stripes
        if pattern == "striped":
            tex_coord = nodes.new("ShaderNodeTexCoord")
            mapping = nodes.new("ShaderNodeMapping")
            mapping.inputs["Scale"].default_value = (1.0, 4.0, 1.0)
            wave = nodes.new("ShaderNodeTexWave")
            wave.wave_type = 'RINGS'
            color_ramp = nodes.new("ShaderNodeValToRGB")
            color_ramp.color_ramp.elements[0].color = (r, g, b, 1.0)
            color_ramp.color_ramp.elements[1].color = (r * 0.7, g * 0.7, b * 0.7, 1.0)
            
            links.new(tex_coord.outputs["Generated"], mapping.inputs["Vector"])
            links.new(mapping.outputs["Vector"], wave.inputs["Vector"])
            links.new(wave.outputs["Fac"], color_ramp.inputs["Fac"])
            links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])
        
        # Pattern: spotted
        elif pattern == "spotted":
            noise = nodes.new("ShaderNodeTexNoise")
            noise.inputs["Scale"].default_value = 8.0
            color_ramp = nodes.new("ShaderNodeValToRGB")
            color_ramp.color_ramp.elements[0].color = (r, g, b, 1.0)
            color_ramp.color_ramp.elements[1].color = (r * 0.5, g * 0.5, b * 0.5, 1.0)
            color_ramp.color_ramp.elements.new(0.3)
            color_ramp.color_ramp.elements[1].position = 0.6
            
            links.new(noise.outputs["Fac"], color_ramp.inputs["Fac"])
            links.new(color_ramp.outputs["Color"], principled.inputs["Base Color"])
        
        # Pattern: galaxy (legendary)
        elif pattern == "galaxy":
            noise1 = nodes.new("ShaderNodeTexNoise")
            noise1.inputs["Scale"].default_value = 3.0
            noise2 = nodes.new("ShaderNodeTexVoronoi")
            noise2.inputs["Scale"].default_value = 6.0
            
            mix = nodes.new("ShaderNodeMixRGB")
            mix.blend_type = 'ADD'
            mix.inputs["Fac"].default_value = 0.5
            
            emission = nodes.new("ShaderNodeEmission")
            emission.inputs["Color"].default_value = (r * 0.3, g * 0.3, b * 0.5, 1.0)
            emission.inputs["Strength"].default_value = 0.3
            
            mix_shader = nodes.new("ShaderNodeMixShader")
            
            links.new(noise1.outputs["Fac"], mix.inputs["Color1"])
            links.new(noise2.outputs["Distance"], mix.inputs["Color2"])
            links.new(mix.outputs["Color"], principled.inputs["Base Color"])
            links.new(principled.outputs["BSDF"], mix_shader.inputs[1])
            links.new(emission.outputs["Emission"], mix_shader.inputs[2])
            
            output = nodes["Material Output"]
            links.new(mix_shader.outputs["Shader"], output.inputs["Surface"])
        
        self._materials[key] = mat
        return mat


# ============================================================
# PART MESH GENERATOR
# ============================================================

class PartMeshGenerator:
    """Generates mesh geometry for each pet part type."""
    
    @staticmethod
    def create_primitive(piece_type: str, scale: List[float], color_hex: str,
                         location: Tuple[float, float, float],
                         rotation: Optional[Tuple[float, float, float]] = None,
                         name: str = "Part") -> bpy.types.Object:
        """Create a basic primitive mesh for a part."""
        
        mesh_types = {
            "Brick_1x1": ("cube", [STUD * 1, BRICK_H * 1, STUD * 1]),
            "Brick_1x2": ("cube", [STUD * 1, BRICK_H * 1, STUD * 2]),
            "Brick_2x2": ("cube", [STUD * 2, BRICK_H * 1, STUD * 2]),
            "Brick_2x4": ("cube", [STUD * 2, BRICK_H * 1, STUD * 4]),
            "Plate_1x1": ("cube", [STUD * 1, PLATE_H * 1, STUD * 1]),
            "Plate_1x2": ("cube", [STUD * 1, PLATE_H * 1, STUD * 2]),
            "Plate_2x2": ("cube", [STUD * 2, PLATE_H * 1, STUD * 2]),
            "Slope_2x1_45": ("cube", [STUD * 2, BRICK_H * 1, STUD * 1]),
            "Slope_2x2_33": ("cube", [STUD * 2, BRICK_H * 1, STUD * 2]),
            "Wedge_2x2": ("cube", [STUD * 2, BRICK_H * 1, STUD * 2]),
            "Round_1x1": ("uv_sphere", [STUD * 0.8, STUD * 0.8, STUD * 0.8]),
            "Tile_1x1": ("cube", [STUD * 1, PLATE_H * 0.5, STUD * 1]),
            "Tile_1x2": ("cube", [STUD * 1, PLATE_H * 0.5, STUD * 2]),
            "Tile_2x2": ("cube", [STUD * 2, PLATE_H * 0.5, STUD * 2]),
            "Bar_1x2": ("cylinder", [STUD * 0.3, BRICK_H * 0.5, STUD * 2]),
            "Macaroni_2x2": ("uv_sphere", [STUD * 2, BRICK_H * 1, STUD * 2]),
        }
        
        prim_type, base_dims = mesh_types.get(piece_type, ("cube", [STUD, STUD, STUD]))
        
        scaled_dims = [base_dims[i] * scale[i] for i in range(3)]
        
        if prim_type == "cube":
            bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        elif prim_type == "uv_sphere":
            bpy.ops.mesh.primitive_uv_sphere_add(radius=1, location=location, segments=8, ring_count=6)
        elif prim_type == "cylinder":
            bpy.ops.mesh.primitive_cylinder_add(radius=1, depth=1, location=location, vertices=8)
        else:
            bpy.ops.mesh.primitive_cube_add(size=1, location=location)
        
        obj = bpy.context.active_object
        obj.name = name
        obj.scale = (scaled_dims[0], scaled_dims[1], scaled_dims[2])
        
        if rotation:
            obj.rotation_euler = rotation
        
        return obj


# ============================================================
# PET BUILDER
# ============================================================

class PetBuilder:
    """Main pet assembly system. Builds creatures from part definitions."""
    
    def __init__(self, parts_file: str = None):
        if parts_file is None:
            parts_file = str(Path(__file__).parent / "pet_parts_system.json")
        
        with open(parts_file, 'r') as f:
            self.data = json.load(f)
        
        self.parts = self.data["parts"]
        self.prebuilt = self.data["prebuilt_pets"]
        self.rules = self.data["generation_rules"]
        self.compat = self.data.get("compatibility_matrix", {})
        self.materials = PetMaterialSystem()
        self._id_counter = 0
    
    def _next_id(self) -> int:
        self._id_counter += 1
        return self._id_counter
    
    def _find_part(self, category: str, part_id: str) -> Optional[dict]:
        """Find a part definition by category and ID."""
        for part in self.parts.get(category, []):
            if part["id"] == part_id:
                return part
        return None
    
    def _apply_material(self, obj: bpy.types.Object, color: str, pattern: str):
        """Apply colored material to an object."""
        mat = self.materials.get_material(obj.name, color, pattern)
        if obj.data.materials:
            obj.data.materials[0] = mat
        else:
            obj.data.materials.append(mat)
    
    def _place_part(self, part_def: dict, position: Tuple[float, float, float],
                    color: str, pattern: str = "solid", suffix: str = "") -> bpy.types.Object:
        """Place a single part mesh in the scene."""
        geo = part_def["geometry"]
        piece_type = geo.get("type", "Brick_2x2")
        scale = geo.get("scale", [1.0, 1.0, 1.0])
        
        obj = PartMeshGenerator.create_primitive(
            piece_type, scale, color, position,
            name=f"{part_def['id']}_{suffix}_{self._next_id()}"
        )
        
        self._apply_material(obj, color, pattern)
        return obj
    
    def build_prebuilt(self, pet_name: str, offset: Tuple[float, float, float] = (0, 0, 0)) -> dict:
        """Build a pre-designed pet by name."""
        pet = None
        for p in self.prebuilt:
            if p["name"].lower() == pet_name.lower():
                pet = p
                break
        
        if not pet:
            available = [p["name"] for p in self.prebuilt]
            print(f"[PetBuilder] Unknown pet '{pet_name}'. Available: {available}")
            return None
        
        return self.build_from_parts(pet["parts"], pet.get("colors", {}), offset, pet["name"])
    
    def build_from_parts(self, part_selection: dict, colors: dict = None,
                         offset: Tuple[float, float, float] = (0, 0, 0),
                         pet_name: str = "Custom") -> dict:
        """Build a pet from a part selection dictionary.
        
        Args:
            part_selection: Dict of {category: part_id}
            colors: Dict of {color_name: hex_or_name}
            offset: World position offset
            pet_name: Name for the creature
        
        Returns:
            Dict with build info: name, parts used, position, stats
        """
        if colors is None:
            colors = {"primary": "#888888"}
        
        primary_color = resolve_color(colors.get("primary", "#888888"))
        secondary_color = resolve_color(colors.get("secondary", primary_color))
        accent_color = resolve_color(colors.get("accent", secondary_color))
        pattern = part_selection.get("pattern", "solid")
        
        placed = []
        ox, oy, oz = offset
        
        # === BODY (center, base) ===
        body_def = self._find_part("body", part_selection.get("body", "body_medium"))
        if body_def:
            body_y = oy + BRICK_H * body_def["geometry"]["scale"][1] / 2
            body_obj = self._place_part(body_def, (ox, body_y, oz), primary_color, pattern, "body")
            placed.append(("body", body_obj))
            body_height = BRICK_H * body_def["geometry"]["scale"][1]
        else:
            body_height = BRICK_H
        
        # === HEAD (on top of body) ===
        head_def = self._find_part("head", part_selection.get("head", "head_round"))
        if head_def:
            head_geo = head_def["geometry"]
            head_y = oy + body_height + BRICK_H * head_geo.get("scale", [1, 1, 1])[1] / 2
            head_z = oz + STUD * head_geo.get("scale", [1, 1, 1])[2] * 0.3
            head_obj = self._place_part(head_def, (ox, head_y, head_z), primary_color, pattern, "head")
            placed.append(("head", head_obj))
            head_top = head_y + BRICK_H * head_geo.get("scale", [1, 1, 1])[1] / 2
        else:
            head_top = oy + body_height
        
        # === EYES (on front of head) ===
        eyes_def = self._find_part("eyes", part_selection.get("eyes", "eyes_round"))
        if eyes_def and head_def:
            eye_y = head_y
            eye_z = head_z + STUD * head_def["geometry"].get("scale", [1, 1, 1])[2] * 0.4
            eye_offset = STUD * 0.5
            left_eye = self._place_part(eyes_def, (ox - eye_offset, eye_y, eye_z), "white", "solid", "eye_L")
            right_eye = self._place_part(eyes_def, (ox + eye_offset, eye_y, eye_z), "white", "solid", "eye_R")
            placed.extend([("eyes", left_eye), ("eyes", right_eye)])
            
            # Pupils
            pupil_z = eye_z + STUD * 0.2
            pupil_obj = PartMeshGenerator.create_primitive(
                "Round_1x1", [0.15, 0.15, 0.15], "black",
                (ox, eye_y, pupil_z), name=f"pupil_{self._next_id()}"
            )
            placed.append(("pupils", pupil_obj))
        
        # === SNOUT (below eyes, front of head) ===
        snout_def = self._find_part("snout", part_selection.get("snout", "snout_short"))
        if snout_def:
            snout_y = head_y - BRICK_H * 0.3
            snout_z = head_z + STUD * 0.5
            snout_obj = self._place_part(snout_def, (ox, snout_y, snout_z), secondary_color, "solid", "snout")
            placed.append(("snout", snout_obj))
        
        # === EARS (on sides of head) ===
        ears_def = self._find_part("ears", part_selection.get("ears", "ears_round"))
        if ears_def and head_def:
            head_scale = head_def["geometry"].get("scale", [1, 1, 1])
            ear_y = head_y + BRICK_H * head_scale[1] * 0.3
            ear_offset = STUD * head_scale[0] * 0.6
            left_ear = self._place_part(ears_def, (ox - ear_offset, ear_y, head_z), primary_color, "solid", "ear_L")
            right_ear = self._place_part(ears_def, (ox + ear_offset, ear_y, head_z), primary_color, "solid", "ear_R")
            placed.extend([("ears", left_ear), ("ears", right_ear)])
        
        # === LEGS (4, on bottom corners of body) ===
        legs_def = self._find_part("legs", part_selection.get("legs", "legs_short"))
        if legs_def and body_def:
            body_scale = body_def["geometry"].get("scale", [1, 1, 1])
            leg_length = BRICK_H * legs_def["geometry"]["scale"][1]
            leg_y = oy - leg_length / 2
            leg_offset_x = STUD * body_scale[0] * 0.3
            leg_offset_z = STUD * body_scale[2] * 0.3
            
            leg_positions = [
                (ox - leg_offset_x, leg_y, oz - leg_offset_z, "FL"),
                (ox + leg_offset_x, leg_y, oz - leg_offset_z, "FR"),
                (ox - leg_offset_x, leg_y, oz + leg_offset_z, "BL"),
                (ox + leg_offset_x, leg_y, oz + leg_offset_z, "BR"),
            ]
            
            for lx, ly, lz, suffix in leg_positions:
                leg_obj = self._place_part(legs_def, (lx, ly, lz), secondary_color, "solid", f"leg_{suffix}")
                placed.append(("legs", leg_obj))
        
        # === TAIL (rear of body) ===
        tail_def = self._find_part("tail", part_selection.get("tail", "tail_short"))
        if tail_def and body_def:
            body_scale = body_def["geometry"].get("scale", [1, 1, 1])
            tail_y = oy + body_height * 0.7
            tail_z = oz + STUD * body_scale[2] * 0.6
            tail_obj = self._place_part(tail_def, (ox, tail_y, tail_z), primary_color, "solid", "tail")
            placed.append(("tail", tail_obj))
        
        # === WINGS (if present, on top/sides of body) ===
        if "wings" in part_selection:
            wings_def = self._find_part("wings", part_selection["wings"])
            if wings_def and body_def:
                body_scale = body_def["geometry"].get("scale", [1, 1, 1])
                wing_y = oy + body_height * 0.8
                wing_offset = STUD * body_scale[0] * 0.8
                left_wing = self._place_part(wings_def, (ox - wing_offset, wing_y, oz), accent_color, "solid", "wing_L")
                right_wing = self._place_part(wings_def, (ox + wing_offset, wing_y, oz), accent_color, "solid", "wing_R")
                placed.extend([("wings", left_wing), ("wings", right_wing)])
        
        # === HORNS (if present, on top of head) ===
        if "horns" in part_selection:
            horns_def = self._find_part("horns", part_selection["horns"])
            if horns_def and head_def:
                horn_y = head_top + BRICK_H * 0.2
                head_scale = head_def["geometry"].get("scale", [1, 1, 1])
                horn_count = horns_def.get("count", 2)
                
                if horn_count == 1:
                    # Single horn (unicorn) — center
                    horn_obj = self._place_part(horns_def, (ox, horn_y, head_z), accent_color, "solid", "horn")
                    placed.append(("horns", horn_obj))
                else:
                    # Pair of horns
                    horn_offset = STUD * head_scale[0] * 0.3
                    left_horn = self._place_part(horns_def, (ox - horn_offset, horn_y, head_z), accent_color, "solid", "horn_L")
                    right_horn = self._place_part(horns_def, (ox + horn_offset, horn_y, head_z), accent_color, "solid", "horn_R")
                    placed.extend([("horns", left_horn), ("horns", right_horn)])
        
        result = {
            "name": pet_name,
            "parts_used": {k: v for k, v in part_selection.items()},
            "position": offset,
            "piece_count": len(placed),
            "placed_objects": placed
        }
        
        print(f"[PetBuilder] Built '{pet_name}': {len(placed)} parts at {offset}")
        return result
    
    def build_random(self, rarity: str = None, offset: Tuple[float, float, float] = (0, 0, 0)) -> dict:
        """Generate and build a random pet of given rarity.
        
        Args:
            rarity: 'common', 'uncommon', 'rare', 'legendary', or None for random
            offset: World position
        """
        if rarity is None:
            weights = self.rules["rarity_weights"]
            rarities = list(weights.keys())
            r_weights = [weights[r] for r in rarities]
            rarity = random.choices(rarities, weights=r_weights)[0]
        
        # Select random parts for each category
        part_selection = {}
        
        # Required categories
        required = ["head", "body", "legs", "tail"]
        for cat in required:
            available = [p["id"] for p in self.parts.get(cat, [])]
            if available:
                part_selection[cat] = random.choice(available)
        
        # Optional categories (more likely at higher rarities)
        optional = ["ears", "eyes", "snout"]
        if rarity in ["uncommon", "rare", "legendary"]:
            for cat in optional:
                available = [p["id"] for p in self.parts.get(cat, [])]
                if available and random.random() < 0.8:
                    part_selection[cat] = random.choice(available)
        
        # Special parts (rare/legendary only)
        if rarity in ["rare", "legendary"]:
            if random.random() < 0.5:
                wings_avail = [p["id"] for p in self.parts.get("wings", [])]
                if wings_avail:
                    part_selection["wings"] = random.choice(wings_avail)
        
        if rarity == "legendary":
            if random.random() < 0.6:
                horns_avail = [p["id"] for p in self.parts.get("horns", [])]
                if horns_avail:
                    part_selection["horns"] = random.choice(horns_avail)
        
        # Pattern
        patterns = [p["id"] for p in self.parts.get("pattern", [])]
        rarity_pattern_map = {
            "common": ["pattern_solid", "pattern_striped", "pattern_spotted"],
            "uncommon": ["pattern_striped", "pattern_spotted", "pattern_gradient"],
            "rare": ["pattern_gradient", "pattern_spotted"],
            "legendary": ["pattern_gradient", "pattern_galaxy"]
        }
        valid_patterns = rarity_pattern_map.get(rarity, patterns)
        valid_patterns = [p for p in valid_patterns if p in patterns]
        if valid_patterns:
            part_selection["pattern"] = random.choice(valid_patterns)
        
        # Random colors
        hue = random.random()
        saturation = 0.5 + random.random() * 0.5
        value = 0.4 + random.random() * 0.4
        
        def hsv_to_hex(h, s, v):
            import colorsys
            r, g, b = colorsys.hsv_to_rgb(h, s, v)
            return f"#{int(r*255):02X}{int(g*255):02X}{int(b*255):02X}"
        
        primary = hsv_to_hex(hue, saturation, value)
        secondary = hsv_to_hex((hue + 0.15) % 1.0, saturation * 0.8, value * 1.1)
        accent = hsv_to_hex((hue + 0.3) % 1.0, saturation * 1.2, value * 1.2)
        
        colors = {
            "primary": primary,
            "secondary": secondary,
            "accent": accent
        }
        
        # Generate name
        adj = random.choice(self.rules["name_generation"]["adjectives"])
        noun = random.choice(self.rules["name_generation"]["nouns"])
        pet_name = f"{adj} {noun}"
        
        return self.build_from_parts(part_selection, colors, offset, pet_name)
    
    def list_prebuilt(self) -> List[str]:
        """Return list of available prebuilt pet names."""
        return [p["name"] for p in self.prebuilt]
    
    def list_parts(self, category: str = None) -> dict:
        """Return available parts, optionally filtered by category."""
        if category:
            return {category: [(p["id"], p["name"], p.get("rarity", "common")) for p in self.parts.get(category, [])]}
        return {cat: [(p["id"], p["name"], p.get("rarity", "common")) for p in parts] 
                for cat, parts in self.parts.items()}


# ============================================================
# DEMO
# ============================================================

def demo_build_all_prebuilt():
    """Build all 5 pre-designed pets spaced apart."""
    print("=" * 60)
    print("Bits and Baubles — Pet Builder Demo")
    print("=" * 60)
    
    builder = PetBuilder()
    
    # Build all prebuilt pets
    names = builder.list_prebuilt()
    for i, name in enumerate(names):
        offset = (i * 8, 0, 0)
        builder.build_prebuilt(name, offset)
    
    # Build some random pets
    print("\n[Random Generation]")
    for i in range(3):
        offset = (i * 8, 0, 10)
        rarity = ["common", "rare", "legendary"][i]
        builder.build_random(rarity, offset)
    
    print(f"\n[Demo Complete] Built {len(names)} pre-designed + 3 random pets")


if __name__ == "__main__":
    demo_build_all_prebuilt()
