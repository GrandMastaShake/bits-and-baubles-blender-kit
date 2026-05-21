#!/usr/bin/env python3
"""
AI PART IDEA GENERATOR
======================
Generates new pet part concepts using creative combinatorics.
No neural network required — pure creative pattern matching.
Mixes existing part attributes, applies morphological rules,
and produces novel part ideas with full specifications.

Usage:
    from ai_part_idea_generator import PartIdeaGenerator
    
    gen = PartIdeaGenerator()
    
    # Generate new part ideas
    ideas = gen.generate("head", count=5)
    for idea in ideas:
        print(f"  {idea['name']}: {idea['description']}")
    
    # Hybrid: combine two existing parts
    hybrid = gen.hybridize("head_round", "head_triangular")
    print(f"  Hybrid: {hybrid['name']}")
    
    # Full pet concept
    pet = gen.generate_pet_concept("legendary")
    print(f"  {pet['name']}: {pet['description']}")
"""

import json
import random
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass


# ============================================================
# CREATIVE SEEDS — base patterns for generating new ideas
# ============================================================

CREATIVE_SEEDS = {
    "head": {
        "shapes": ["heart", "diamond", "star", "crescent", "spiral", "cloud", "teardrop", "hexagon", "flower"],
        "textures": ["fuzzy", "smooth", "scaly", "crystalline", "metallic", "wooden", "velvet", "glowing"],
        "families": ["celestial", "elemental", "crystal", "shadow", "light", "nature", "tech", "mythic"],
        "expressions": ["mysterious", "fierce", "serene", "playful", "wise", "mischievous", "noble", "ethereal"]
    },
    "ears": {
        "styles": ["feathered", "fin-like", "leaf-shaped", "crystal", "flame-shaped", "cloud-like", "star-tipped", "bat-wing"],
        "behaviors": ["flutter", "glow", "sparkle", "change_color", "vibrate", "fold", "extend", "curl"],
        "materials": ["soft_plush", "metallic", "translucent", "bioluminescent", "chitin", "flower_petal"]
    },
    "eyes": {
        "styles": ["compound", "heterochromia", "swirling", "starry", "void", "prismatic", "lantern", "jeweled"],
        "effects": ["glow_pulse", "trail_sparkles", "change_color", "project_light", "hypnotic_spin", "tear_gem"],
        "colors": ["#00FFFF", "#FF00FF", "#FFD700", "#FF4500", "#7B68EE", "#00FF7F", "#FF1493"]
    },
    "body": {
        "shapes": ["pebble", "crystal_cluster", "cloud_puff", "moss_ball", "star_core", "geode", "mushroom_cap"],
        "textures": ["iridescent", "bioluminescent_stripes", "stardust", "magma_veins", "frost_crystals", "living_vine"],
        "special": ["floating_orbs", "mini_planets", "aurora_aura", "elemental_core", "time_warp"]
    },
    "tail": {
        "styles": ["comet_trail", "vine_whip", "crystal_shard", "smoke_wisp", "lightning_bolt", "feather_cascade"],
        "animations": ["orbit_body", "draw_shapes", "emit_particles", "morph_shape", "leave_trail"],
        "materials": ["nebula_gas", "liquid_metal", "solid_light", "living_ice", "solar_plasma"]
    },
    "wings": {
        "styles": ["dragon_webbed", "butterfly_painted", "angel_feathered", "bat_tattered", "crystal_prismatic", "cloud_mist"],
        "effects": ["leave_sparkle_trail", "create_wind_burst", "cast_light_beams", "summon_petals", "freeze_air"],
        "sizes": ["tiny_buzzing", "small_flutter", "medium_soar", "large_glide", "massive_eclipse"]
    },
    "horns": {
        "styles": ["tree_branch", "lightning_antler", "crystal_spire", "corkscrew_ram", "crown_tipped", "stardust_ram"],
        "effects": ["channel_energy", "grow_flowers", "emit_sound", "cast_shadows", "glow_runes"],
        "counts": [1, 2, 3, 4, 6]
    },
    "legs": {
        "styles": ["spring_coil", "hover_disc", "ghost_wisp", "vine_tendril", "crystal_stilt", "cloud_puff"],
        "gaits": ["float_hover", "bounce_spring", "skate_slide", "phase_blink", "roll_ball"],
        "counts": [0, 2, 4, 6, 8]
    }
}

ELEMENTAL_FUSIONS = [
    ("fire", "water", "steam"),
    ("earth", "air", "dust"),
    ("light", "shadow", "twilight"),
    ("ice", "fire", "obsidian"),
    ("nature", "tech", "biomech"),
    ("cosmic", "earth", "meteorite"),
    ("ocean", "lightning", "storm"),
    ("crystal", "shadow", "void_crystal"),
]

MYTHIC_PREFIXES = [
    "Ancient", "Ethereal", "Prismatic", "Celestial", "Eldritch",
    "Verdant", "Astral", "Umbral", "Radiant", "Tempest",
    "Crystalline", "Phantasmal", "Solstice", "Luminous", "Obsidian"
]

MYTHIC_SUFFIXES = [
    "of the Void", "of Starlight", "the Everlasting", "of Dreams",
    "the Warden", "of Infinite Skies", "the Primordial", "of Whispered Winds",
    "the Luminescent", "of Shattered Realms"
]


# ============================================================
# PART IDEA GENERATOR
# ============================================================

class PartIdeaGenerator:
    """Generates creative new pet part ideas through combinatorial creativity."""
    
    def __init__(self, parts_file: str = None):
        if parts_file is None:
            parts_file = str(Path(__file__).parent / "pet_parts_system.json")
        
        with open(parts_file, 'r') as f:
            self.data = json.load(f)
        
        self.parts = self.data["parts"]
        self.existing_ids = set()
        for cat, part_list in self.parts.items():
            for p in part_list:
                self.existing_ids.add(p["id"])
    
    def _unique_id(self, base: str) -> str:
        """Generate a unique ID not in existing parts."""
        if base not in self.existing_ids:
            return base
        i = 1
        while f"{base}_{i}" in self.existing_ids:
            i += 1
        return f"{base}_{i}"
    
    def generate(self, category: str, count: int = 3, 
                 element: str = None, rarity_bias: str = None) -> List[dict]:
        """Generate new part ideas for a category.
        
        Args:
            category: Part category (head, ears, eyes, body, tail, wings, horns, legs)
            count: Number of ideas to generate
            element: Optional elemental theme (fire, water, earth, air, light, shadow, ice, nature)
            rarity_bias: Favor certain rarity ('common', 'rare', 'legendary')
        
        Returns:
            List of part idea dictionaries
        """
        seeds = CREATIVE_SEEDS.get(category, {})
        ideas = []
        
        for _ in range(count):
            idea = self._create_idea(category, seeds, element, rarity_bias)
            ideas.append(idea)
        
        return ideas
    
    def _create_idea(self, category: str, seeds: dict, 
                     element: str = None, rarity_bias: str = None) -> dict:
        """Create a single part idea."""
        
        # Determine element
        if element is None:
            elements = ["fire", "water", "earth", "air", "light", "shadow", "ice", "nature", "cosmic", "crystal"]
            element = random.choice(elements)
        
        # Determine rarity
        if rarity_bias:
            rarity = rarity_bias
        else:
            rarity = random.choices(
                ["common", "uncommon", "rare", "legendary"],
                weights=[40, 30, 20, 10]
            )[0]
        
        # Build name
        shape = random.choice(seeds.get("shapes", ["unique"]))
        texture = random.choice(seeds.get("textures", ["special"]))
        
        if rarity == "legendary":
            prefix = random.choice(MYTHIC_PREFIXES)
            name = f"{prefix} {shape.title()} {category.title()}"
        elif rarity == "rare":
            name = f"{element.title()} {shape.title()} {category.title()}"
        else:
            name = f"{texture.title()} {shape.title()} {category.title()}"
        
        # Build description
        family = random.choice(seeds.get("families", ["mystery"])) if "families" in seeds else "unknown"
        expression = random.choice(seeds.get("expressions", ["enigmatic"])) if "expressions" in seeds else "neutral"
        
        description = f"A {texture} {shape}-shaped {category} "
        if rarity == "legendary":
            suffix = random.choice(MYTHIC_SUFFIXES)
            description += f"from the {family} realm {suffix}. "
            description += f"Those who gaze upon it feel {expression}."
        elif rarity == "rare":
            description += f"infused with {element} energy. "
            description += f"It appears {expression} to those nearby."
        else:
            description += f"with a {texture} finish. Common but charming."
        
        # Build geometry spec
        base_types = {
            "head": "Brick_2x2", "ears": "Plate_1x2", "eyes": "Round_1x1",
            "body": "Brick_2x4", "tail": "Brick_1x2", "wings": "Tile_2x2",
            "horns": "Slope_2x1_45", "legs": "Brick_1x1"
        }
        
        # Scale based on rarity
        scale_base = {"common": 1.0, "uncommon": 1.1, "rare": 1.3, "legendary": 1.5}
        base_scale = scale_base.get(rarity, 1.0)
        scale_var = [base_scale + random.uniform(-0.2, 0.3) for _ in range(3)]
        
        # Special effects for rare+
        special = {}
        if rarity in ["rare", "legendary"]:
            effects_key = f"{category}_effects" if f"{category}_effects" in seeds else "effects"
            all_effects = seeds.get("effects", seeds.get("animations", ["glow"]))
            if all_effects:
                special["effect"] = random.choice(all_effects)
            special["element"] = element
        
        if rarity == "legendary":
            special["emissive"] = True
            special["glow_color"] = random.choice([
                "#FFD700", "#FF69B4", "#00FFFF", "#FF4500", "#9370DB"
            ])
            if "sparkle" in seeds.get("effects", []):
                special["sparkle"] = True
        
        idea = {
            "id": self._unique_id(f"{category}_{shape}_{element}"),
            "name": name,
            "category": category,
            "rarity": rarity,
            "element": element,
            "family": family,
            "description": description,
            "expression": expression,
            "geometry": {
                "type": base_types.get(category, "Brick_2x2"),
                "scale": [round(s, 2) for s in scale_var],
                **special
            },
            "concept_tags": [shape, texture, element, family, rarity],
        }
        
        return idea
    
    def hybridize(self, part_id_a: str, part_id_b: str) -> Optional[dict]:
        """Create a hybrid by combining two existing parts.
        
        Args:
            part_id_a: First parent part ID
            part_id_b: Second parent part ID
        
        Returns:
            Hybrid part idea or None if parents not found
        """
        # Find the parts
        parent_a = None
        parent_b = None
        cat_a = cat_b = None
        
        for cat, part_list in self.parts.items():
            for p in part_list:
                if p["id"] == part_id_a:
                    parent_a = p
                    cat_a = cat
                if p["id"] == part_id_b:
                    parent_b = p
                    cat_b = cat
        
        if not parent_a or not parent_b:
            missing = []
            if not parent_a:
                missing.append(part_id_a)
            if not parent_b:
                missing.append(part_id_b)
            print(f"[Hybridizer] Could not find: {missing}")
            return None
        
        # Build hybrid
        a_name = parent_a["name"].split()[0]
        b_name = parent_b["name"].split()[-1]
        hybrid_name = f"{a_name}-{b_name} Hybrid {cat_a.title()}"
        
        # Combine scales
        geo_a = parent_a.get("geometry", {})
        geo_b = parent_b.get("geometry", {})
        scale_a = geo_a.get("scale", [1, 1, 1])
        scale_b = geo_b.get("scale", [1, 1, 1])
        hybrid_scale = [round((scale_a[i] + scale_b[i]) / 2, 2) for i in range(3)]
        
        # Inherit rarity (higher of two + 1)
        rarity_order = {"common": 0, "uncommon": 1, "rare": 2, "legendary": 3}
        rarities = [parent_a.get("rarity", "common"), parent_b.get("rarity", "common")]
        max_rarity = max(rarities, key=lambda r: rarity_order.get(r, 0))
        hybrid_rarity_idx = min(rarity_order[max_rarity] + 1, 3)
        hybrid_rarity = list(rarity_order.keys())[hybrid_rarity_idx]
        
        # Combine expressions
        expr_a = parent_a.get("expression", "neutral")
        expr_b = parent_b.get("expression", "neutral")
        
        description = f"A fascinating fusion of {parent_a['name']} and {parent_b['name']}. "
        description += f"It exhibits {expr_a} tendencies with {expr_b} undertones. "
        
        if hybrid_rarity == "legendary":
            description += "This hybrid is said to appear only once in a generation."
        elif hybrid_rarity == "rare":
            description += "A rare combination that collectors seek."
        
        hybrid = {
            "id": self._unique_id(f"hybrid_{part_id_a}_{part_id_b}"),
            "name": hybrid_name,
            "category": cat_a,
            "rarity": hybrid_rarity,
            "parents": [part_id_a, part_id_b],
            "description": description,
            "geometry": {
                "type": geo_a.get("type", "Brick_2x2"),
                "scale": hybrid_scale,
            },
            "expression": f"{expr_a}-{expr_b}",
            "hybrid": True
        }
        
        return hybrid
    
    def elemental_fusion(self, element_a: str, element_b: str) -> str:
        """Determine the fusion element of two elements."""
        for a, b, result in ELEMENTAL_FUSIONS:
            if (element_a == a and element_b == b) or (element_a == b and element_b == a):
                return result
        # Default: combine names
        return f"{element_a}_{element_b}"
    
    def generate_pet_concept(self, rarity: str = None) -> dict:
        """Generate a complete pet concept — name, parts, colors, backstory.
        
        Returns:
            Dict with full pet concept
        """
        if rarity is None:
            rarity = random.choice(["common", "uncommon", "rare", "legendary"])
        
        # Pick element
        elements = ["fire", "water", "earth", "air", "light", "shadow", "ice", "nature"]
        element = random.choice(elements)
        
        # Generate name
        if rarity == "legendary":
            prefix = random.choice(MYTHIC_PREFIXES)
            noun = random.choice(["Dragon", "Phoenix", "Guardian", "Spirit", "Titan"])
            suffix = random.choice(MYTHIC_SUFFIXES)
            name = f"{prefix} {noun} {suffix}"
        elif rarity == "rare":
            adj = random.choice(["Ember", "Frost", "Storm", "Crystal", "Shadow"])
            noun = random.choice(["Wolf", "Fox", "Owl", "Bear", "Hawk"])
            name = f"{adj} {noun}"
        else:
            adj = random.choice(["Little", "Tiny", "Cute", "Fluffy", "Bright"])
            noun = random.choice(["Pup", "Kit", "Bunny", "Cub", "Chick"])
            name = f"{adj} {noun}"
        
        # Generate backstory
        habitats = {
            "fire": "volcanic caverns where lava flows like rivers",
            "water": "coral kingdoms beneath crystal-clear oceans",
            "earth": "ancient forests where the oldest trees whisper secrets",
            "air": "cloud citadels floating above the highest peaks",
            "light": "prismatic valleys where dawn lasts forever",
            "shadow": "twilight groves where light and dark dance together",
            "ice": "frozen tundras beneath aurora-filled skies",
            "nature": "enchanted meadows where flowers sing at dusk"
        }
        
        personalities = {
            "common": ["playful", "friendly", "curious", "loyal"],
            "uncommon": ["mischievous", "brave", "gentle", "swift"],
            "rare": ["mysterious", "noble", "fierce", "wise"],
            "legendary": ["otherworldly", "primordial", "celestial", "transcendent"]
        }
        
        habitat = habitats.get(element, "unknown realms")
        personality = random.choice(personalities.get(rarity, ["mysterious"]))
        
        backstory = (
            f"Born in the {habitat}, {name} is known for its {personality} nature. "
            f"Trainers who earn its trust find a companion of {rarity} quality."
        )
        
        if rarity == "legendary":
            backstory += (
                f" Legends say {name} appears only when the {element} realm "
                f"is in peril, bringing balance with its {personality} presence."
            )
        
        # Generate color palette based on element
        element_colors = {
            "fire": ("#FF4500", "#FFD700", "#8B0000"),
            "water": ("#3366CC", "#00FFFF", "#00008B"),
            "earth": ("#8B4513", "#D2B48C", "#556B2F"),
            "air": ("#87CEEB", "#FFFFFF", "#B0C4DE"),
            "light": ("#FFD700", "#FFFFFF", "#FFFACD"),
            "shadow": ("#2C2C2C", "#800080", "#000000"),
            "ice": ("#00FFFF", "#E0FFFF", "#4682B4"),
            "nature": ("#33AA33", "#FFD700", "#8B4513"),
        }
        
        primary, secondary, accent = element_colors.get(element, ("#888888", "#AAAAAA", "#666666"))
        
        return {
            "name": name,
            "rarity": rarity,
            "element": element,
            "personality": personality,
            "backstory": backstory,
            "habitat": habitat,
            "suggested_parts": {
                "head": random.choice([p["id"] for p in self.parts.get("head", [])]),
                "ears": random.choice([p["id"] for p in self.parts.get("ears", [])]),
                "eyes": random.choice([p["id"] for p in self.parts.get("eyes", [])]),
                "body": random.choice([p["id"] for p in self.parts.get("body", [])]),
                "legs": random.choice([p["id"] for p in self.parts.get("legs", [])]),
                "tail": random.choice([p["id"] for p in self.parts.get("tail", [])]),
            },
            "colors": {
                "primary": primary,
                "secondary": secondary,
                "accent": accent
            },
            "concept_tags": [element, rarity, personality]
        }
    
    def batch_generate(self, categories: List[str] = None, 
                       count_per_category: int = 3) -> Dict[str, List[dict]]:
        """Generate ideas for all categories at once.
        
        Args:
            categories: List of categories, or None for all
            count_per_category: Ideas per category
        
        Returns:
            Dict of {category: [ideas]}
        """
        if categories is None:
            categories = ["head", "ears", "eyes", "body", "tail", "wings", "horns", "legs"]
        
        results = {}
        for cat in categories:
            results[cat] = self.generate(cat, count_per_category)
        
        return results


# ============================================================
# DEMO
# ============================================================

def demo_idea_generator():
    """Run the AI Part Idea Generator demo."""
    print("=" * 70)
    print("  AI PART IDEA GENERATOR — Bits and Baubles")
    print("  Generating creative new pet part concepts...")
    print("=" * 70)
    
    gen = PartIdeaGenerator()
    
    # 1. Generate ideas for each category
    print("\n[1] NEW PART IDEAS BY CATEGORY")
    print("-" * 50)
    
    categories = ["head", "ears", "eyes", "body", "tail", "wings"]
    for cat in categories:
        ideas = gen.generate(cat, count=2, rarity_bias="rare")
        print(f"\n  {cat.upper()}:")
        for idea in ideas:
            print(f"    [{idea['rarity'].upper()}] {idea['name']}")
            print(f"             {idea['description'][:80]}...")
            print(f"             Tags: {', '.join(idea['concept_tags'][:3])}")
    
    # 2. Hybrid parts
    print("\n\n[2] HYBRID PARTS")
    print("-" * 50)
    
    hybrids = [
        ("head_round", "head_triangular"),
        ("tail_long", "tail_fluffy"),
        ("ears_pointy", "ears_feathered"),
    ]
    
    for a, b in hybrids:
        hybrid = gen.hybridize(a, b)
        if hybrid:
            print(f"\n  {a} + {b} =")
            print(f"    [{hybrid['rarity'].upper()}] {hybrid['name']}")
            print(f"             Scale: {hybrid['geometry']['scale']}")
            print(f"             {hybrid['description'][:80]}")
    
    # 3. Elemental fusions
    print("\n\n[3] ELEMENTAL FUSIONS")
    print("-" * 50)
    
    fusions = [
        ("fire", "water"), ("earth", "air"), ("light", "shadow"),
        ("ice", "fire"), ("nature", "tech")
    ]
    
    for a, b in fusions:
        result = gen.elemental_fusion(a, b)
        print(f"  {a.title()} + {b.title()} = {result.title()}")
    
    # 4. Full pet concepts
    print("\n\n[4] PET CONCEPTS")
    print("-" * 50)
    
    for rarity in ["common", "rare", "legendary"]:
        pet = gen.generate_pet_concept(rarity)
        print(f"\n  [{rarity.upper()}] {pet['name']}")
        print(f"       Element: {pet['element'].title()} | Personality: {pet['personality'].title()}")
        print(f"       {pet['backstory'][:100]}...")
    
    # 5. Batch generation summary
    print("\n\n[5] BATCH GENERATION SUMMARY")
    print("-" * 50)
    
    batch = gen.batch_generate(count_per_category=2)
    total = sum(len(v) for v in batch.values())
    print(f"  Generated {total} part ideas across {len(batch)} categories:")
    for cat, ideas in batch.items():
        rarities = {}
        for idea in ideas:
            r = idea['rarity']
            rarities[r] = rarities.get(r, 0) + 1
        rarity_str = ", ".join(f"{k}:{v}" for k, v in rarities.items())
        print(f"    {cat:12s} — {len(ideas)} ideas ({rarity_str})")
    
    print("\n" + "=" * 70)
    print(f"  Total unique ideas generated: {total + len(hybrids) + len(fusions) + 3}")
    print("=" * 70)


if __name__ == "__main__":
    demo_idea_generator()
