# Bits and Baubles Builder Kit v2.0

## Modular Brick System + Adopt Me Pet Generator — Centuria Swarm Production

A complete, self-contained B&B-style modular brick building system for Blender **plus a full Adopt Me-style chibi pet generator**. Build houses, castles, dragons, and space stations with 25 brick types — or generate procedural low-poly pets from a 20-species catalog with neon support, proportion validation against the 10 Adopt Me design laws, and a mix-and-match parts engine.

---

## v2.0 — Adopt Me Pet Generator

### One-Click Cat Demo

Open `blender_cat_demo.py` in Blender's Scripting tab and press **Run Script**. Builds a standard orange tabby + neon version side-by-side with 3-point studio lighting and an 85mm portrait camera. Renders to `output/`.

### Core Files Added in v2.0

| File | What It Does |
|------|-------------|
| `am_pet_generator.py` | `AdoptMePetBuilder` — builds any of 20 species from `am_species.json`, full neon MixShader support, proportion validator |
| `am_geometry.py` | bmesh geometry primitives (`make_chibi_head`, etc.) with HEAD_TO_BODY=0.65, EYE_TO_HEAD=0.18 |
| `am_species.json` | 20 species catalog: dog, cat, bunny, dragon, shadow_dragon, unicorn, and more. Each species has full geometry, proportions, color, and neon config |
| `pet_parts_system.json` | Mix-and-match parts library: 6 head types, 5 ear types, 5 eye types, 6 body types, 5 leg types, 6 tail types, 3 wing types, 3 horn types, 5 patterns |
| `pet_builder.py` | `PetBuilder` — reads `pet_parts_system.json`, builds any combination of parts + 5 prebuilts (Golden Retriever, Shadow Wolf, Phoenix, Cyber Pup, Rainbow Unicorn) |
| `expanded_demos.py` | 10 build recipes: original 5 + Space Station, Dragon, Treehouse, Robot, Full Castle |
| `ai_part_idea_generator.py` | `PartIdeaGenerator` — generates new part concepts, hybridizes existing parts, elemental fusions, full pet backstory concepts |
| `pet_generator.py` | Standalone 9-part cat generator (no JSON required, good for quick tests) |
| `blender_cat_demo.py` | One-click launcher: clears scene, builds normal + neon cat, sets up lighting/camera/renderer |

### Quick API

```python
import sys
sys.path.insert(0, r"path/to/bits_and_baubles")

from am_pet_generator import AdoptMePetBuilder

builder = AdoptMePetBuilder()

# Build any species (neon optional)
builder.build_pet("cat",           neon=False, location=(0, 0, 0))
builder.build_pet("cat",           neon=True,  location=(8, 0, 0))
builder.build_pet("dragon",        neon=False, location=(16, 0, 0))
builder.build_pet("shadow_dragon", neon=True,  location=(24, 0, 0))

# Validate proportions against the 10 Adopt Me design laws
builder.validate_proportions("cat")

# Build a grid of all species
builder.demo_build_grid()

# One of each rarity tier
builder.demo_one_of_each_rarity()
```

```python
from pet_builder import PetBuilder

builder = PetBuilder()

# Build a prebuilt
builder.build_prebuilt("Rainbow Unicorn", offset=(0, 0, 0))

# Mix-and-match custom
builder.build_from_parts({
    "head": "head_round",
    "ears": "ears_pointy",
    "eyes": "eyes_sparkle",
    "body": "body_chubby",
    "legs": "legs_short",
    "tail": "tail_fluffy",
    "horns": "horns_unicorn",
    "pattern": "pattern_galaxy"
}, colors={"primary": "#FF69B4", "secondary": "#FFD700"})

# Random pet of any rarity
builder.build_random("legendary")
```

### The 10 Adopt Me Design Laws (enforced by validator)

1. HEAD > BODY — head 60–70% of body size
2. CIRCLES ONLY — no sharp silhouettes on primary shapes
3. NO ANGRY PETS — expressions must be friendly/neutral
4. TINY FEET — feet 16–25% of body height
5. NO NECK — head clips into body, zero gap
6. COLOR = RARITY — neon/ultra-rare palette signals tier
7. HEAD = IDENTITY — species recognition lives in head shape
8. SHARP = SOFTENED — hard edges beveled or rounded
9. GLOW = STATUS — emissive materials reserved for rare+
10. SIMPLE = UNIVERSAL — readable at 50px thumbnail size

---

## Table of Contents

- [Quick Start](#quick-start)
- [What's Included](#whats-included)
- [Architecture](#architecture)
- [Module Reference](#module-reference)
  - [Brick Library](#brick-library)
  - [Snap System](#snap-system)
  - [AI Builder](#ai-builder)
  - [Validator](#validator)
  - [Demo Builder](#demo-builder)
- [Recipe Format](#recipe-format)
  - [JSON Specification](#json-specification)
  - [Python API](#python-api)
- [Creating Custom Builds](#creating-custom-builds)
  - [Example 1: Custom Wall](#example-1-custom-wall)
  - [Example 2: Custom Vehicle](#example-2-custom-vehicle)
- [Headless / Batch Mode](#headless--batch-mode)
- [The 5 Demo Structures](#the-5-demo-structures)
- [Troubleshooting](#troubleshooting)
- [File Structure](#file-structure)
- [Team & Credits](#team--credits)

---

## Quick Start

### Prerequisites

- **Blender 3.0 or newer** (download from [blender.org](https://www.blender.org/))
- No external Python packages required (uses only Blender's bundled Python + stdlib)

### Running Inside Blender (Interactive)

1. Open Blender
2. Click the **"Scripting"** workspace tab (top of window)
3. Click **"Open"** in the Text Editor panel
4. Select `bits_and_baubles_kit.py`
5. Click **"Run Script"**
6. Watch the console (Window -> Toggle System Console on Windows, or the terminal on Linux/Mac)
7. All 5 demo structures will auto-build

After running:
- Press **Numpad `.`** (period) to frame all objects
- Press **Z** then select **Rendered** for nice material shading
- Use the **Outliner** (top-right) to toggle collections on/off

### Running from Command Line (Headless / Batch)

```bash
blender --background --python bits_and_baubles_kit.py
```

Output is saved to the `output/` folder next to the script.

---

## What's Included

| Feature | Description |
|---------|-------------|
| **25 Brick Types** | Plates (1x1 to 6x6), Bricks (1x1 to 2x6), Slopes (45 deg roof), Tiles (smooth top), Round pieces |
| **5 Demo Builds** | Cozy House, Castle Tower, Stone Bridge, Off-Road Vehicle, Park Tree |
| **Grid Snap System** | Automatic snapping to B&B stud grid (8mm spacing) |
| **Recipe Engine** | Build from JSON recipes or Python code |
| **Validator** | Structural checks and proportion analysis |
| **Self-Contained** | Works standalone -- no companion modules required |
| **Material Library** | 15 B&B-authentic colors with proper roughness/specular |

---

## Architecture

```
                    +---------------------------+
                    |   bits_and_baubles_kit.py     |
                    |   (this file - integrates |
                    |    everything together)   |
                    +------------+--------------+
                                 |
            +--------------------+--------------------+
            |                    |                    |
    +-------v-------+   +--------v--------+  +--------v--------+
    |  Brick Library|   |   Snap System   |  |   AI Builder    |
    |  (25 pieces)  |   |  (StudGrid +    |  |  (BrickRecipe + |
    |               |   |   Placement)    |  |   build engine) |
    |  - Plates     |   |                 |  |                 |
    |  - Bricks     |   |  - Grid snap    |  |  - JSON recipes |
    |  - Slopes     |   |  - Collision    |  |  - 5 presets    |
    |  - Tiles      |   |  - Occupancy    |  |  - Custom builds|
    |  - Round      |   |                 |  |                 |
    +-------+-------+   +--------+--------+  +--------+--------+
            |                    |                    |
            +--------------------+--------------------+
                                 |
                        +--------v--------+
                        |   Demo Builder  |
                        |  (5 structures) |
                        |                 |
                        |  1. House       |
                        |  2. Tower       |
                        |  3. Bridge      |
                        |  4. Vehicle     |
                        |  5. Tree        |
                        +--------+--------+
                                 |
                        +--------v--------+
                        |    Validator    |
                        |                 |
                        |  - Structural   |
                        |  - Proportion   |
                        |  - Stats        |
                        +-----------------+
```

### Data Flow

1. **Brick Library** creates 25 mesh objects with proper stud geometry
2. **Snap System** manages the 8mm grid and prevents overlapping placements
3. **AI Builder** reads recipes and calls `place_brick()` for each step
4. **Demo Builder** wraps everything and provides the 5 showcase structures
5. **Validator** scans the finished scene and reports any issues

---

## Module Reference

### Brick Library

```python
create_brick_library() -> int
```

Creates all 25 B&B pieces in the scene if they don't already exist. Returns the number of pieces created.

Each piece is created with:
- **Hollow box body** (realistic wall thickness)
- **Studs on top** (cylinders, 12 segments, proper radius/height)
- **Inner tubes** (support pillars for 2x2+ bricks)
- **Category-specific geometry** (slopes, round pieces, tiles)

| Piece Category | Count | Description |
|---------------|-------|-------------|
| Plates        | 10    | Thin bricks (height = 0.004) |
| Bricks        | 7     | Standard bricks (height = 0.012) |
| Slopes        | 4     | 45-degree roof pieces |
| Tiles         | 3     | Smooth top, no studs |
| Round         | 2     | Cylindrical pieces |

### Snap System

```python
StudGrid(spacing=0.008)
  .snap(x, y, z) -> (sx, sy, sz)      # Snap world coords to grid
  .mark_occupied(gx, gy, gz, w, d)     # Reserve grid cells
  .is_occupied(gx, gy, gz, w, d) -> bool
  .clear()                             # Reset all occupancy

PlacementEngine(grid=None)
  .place(obj, x, y, z, grid_snap=True) -> Object
  .placed_count                        # Total pieces placed

Assembly(name="Assembly")
  .place_brick(piece_name, x, y, z, color="gray", rotation=0, use_copy=True) -> Object
  .add_to_collection(obj)
  .get_stats() -> dict
```

**Coordinate system:**
- **X axis** = width (studs across)
- **Y axis** = height (vertical)
- **Z axis** = depth (studs deep)
- 1 grid unit = 1 stud = 0.008 Blender units (8mm)

### AI Builder

```python
AIBuilder()
  .build_from_recipe(recipe, offset=(0,0,0), assembly_name=None) -> Assembly
```

```python
BrickRecipe(name="recipe")
  .add(piece, x, y, z, color="gray", rotation=0)  # x,y,z in STUD units
  .to_json(path)
  .from_json(path) -> BrickRecipe
```

**Built-in recipe generators:**

```python
recipe_house(width=8, depth=6, height=5, wall_color="tan", roof_color="brown")
recipe_tower(base=4, height=12, wall_color="gray", accent="dark_gray")
recipe_bridge(span=16, width=4, stone_color="light_gray", road_color="dark_gray")
recipe_vehicle(chassis_w=6, chassis_l=10, body_color="green", detail_color="dark_gray")
recipe_tree(trunk_h=6, canopy_r=3, trunk_color="brown", leaf_colors=("green", "dark_green"))
```

### Validator

```python
StructuralValidator()
  .validate_scene() -> {"ok": bool, "piece_count": int, "issues": [str]}

ProportionAnalyzer()
  .analyze(assembly_name="") -> {
      "piece_count": int,
      "bounds": {"x": (min,max), "y": (min,max), "z": (min,max)},
      "dimensions": {"dx": float, "dy": float, "dz": float},
      "aspect_ratio": str,
      "volume_approx": float,
  }
```

### Demo Builder

```python
DemoBuilder()
  .build_demo_house()    -> Assembly
  .build_demo_tower()    -> Assembly
  .build_demo_bridge()   -> Assembly
  .build_demo_vehicle()  -> Assembly
  .build_demo_tree()     -> Assembly
  .build_all()           -> Dict[str, Assembly]
  .get_total_pieces()    -> int
  .get_stats()           -> str
```

### Utility Functions

```python
clear_placed_bricks()           # Remove all placed bricks from scene
save_blend(filepath=None)       # Save current scene to .blend file
build_from_json(json_path)      # Build from custom recipe JSON
get_material(color_name)        # Get/create a Bits and Baubles-colored Blender material
show_menu()                     # Print interactive menu
run_interactive()               # Run the interactive menu loop
main()                          # Auto-build all demos and save
```

---

## Recipe Format

### JSON Specification

A recipe is a JSON file with this structure:

```json
{
  "name": "my_custom_build",
  "steps": [
    ["piece_name", x, y, z, "color", rotation],
    ["Brick_2x4",  0, 0, 0, "red",   0],
    ["Plate_2x2",  2, 1, 0, "blue",  0],
    ["Slope_1x2",  0, 2, 0, "green", 1]
  ]
}
```

**Step format:** `[piece_name, x, y, z, color, rotation]`

| Field | Type | Description |
|-------|------|-------------|
| `piece_name` | string | Must match a key in PIECE_DEFS |
| `x` | int | X position in **studs** (0 = origin) |
| `y` | int | Y position in **studs** (height/layer) |
| `z` | int | Z position in **studs** (0 = origin) |
| `color` | string | Key from PIECE_COLORS |
| `rotation` | int | 0, 1, 2, 3 (x 90 degrees around Y axis) |

**Available colors:**
`red`, `blue`, `green`, `yellow`, `white`, `black`, `gray`, `dark_gray`, `light_gray`, `tan`, `brown`, `orange`, `dark_green`, `dark_blue`, `magenta`

**Available pieces:**
`Plate_1x1`, `Plate_1x2`, `Plate_1x4`, `Plate_2x2`, `Plate_2x3`, `Plate_2x4`, `Plate_2x6`, `Plate_4x4`, `Plate_4x6`, `Plate_6x6`, `Brick_1x1`, `Brick_1x2`, `Brick_1x4`, `Brick_2x2`, `Brick_2x3`, `Brick_2x4`, `Brick_2x6`, `Slope_1x2`, `Slope_2x2`, `Slope_2x3`, `Slope_2x4`, `Tile_1x2`, `Tile_2x2`, `Tile_2x4`, `Round_1x1`, `Round_2x2`

### Python API

You can also create recipes directly in Python:

```python
from bits_and_baubles_kit import BrickRecipe, AIBuilder

recipe = BrickRecipe("my_wall")
for x in range(10):
    for y in range(5):
        recipe.add("Brick_1x1", x, y, 0, "red", 0)

builder = AIBuilder()
assembly = builder.build_from_recipe(recipe, offset=(0, 0, 0), assembly_name="Wall")
```

---

## Creating Custom Builds

### Example 1: Custom Wall

```python
from bits_and_baubles_kit import (
    create_brick_library, BrickRecipe, AIBuilder, save_blend
)

# Ensure bricks exist
create_brick_library()

# Define a wall recipe
wall = BrickRecipe("great_wall")
width, height = 20, 8
for x in range(0, width, 2):
    for y in range(height):
        color = "gray" if y % 2 == 0 else "light_gray"
        wall.add("Brick_2x2", x, y, 0, color, 0)
# Crenellations
for x in range(0, width, 4):
    wall.add("Brick_1x1", x, height, 0, "dark_gray", 0)
    wall.add("Brick_1x1", x + 2, height, 0, "dark_gray", 0)

# Build
builder = AIBuilder()
builder.build_from_recipe(wall, offset=(0.5, 0, 0))

# Save
save_blend("/home/user/my_wall.blend")
```

### Example 2: Custom Vehicle

```python
from bits_and_baubles_kit import *

create_brick_library()

jeep = BrickRecipe("super_jeep")
# Chassis
for x in range(0, 12, 2):
    for z in range(0, 6, 2):
        jeep.add("Plate_2x2", x, 0, z, "dark_gray", 0)
# Body
for y in range(1, 4):
    for x in range(1, 10):
        jeep.add("Brick_1x1", x, y, 0, "orange", 0)
        jeep.add("Brick_1x1", x, y, 5, "orange", 0)
# Windshield
for x in range(7, 10):
    jeep.add("Slope_1x2", x, 4, 1, "light_gray", 0)
    jeep.add("Slope_1x2", x, 4, 4, "light_gray", 0)
# Wheels
for wx in [2, 9]:
    for wz in [0, 4]:
        jeep.add("Round_2x2", wx, 0, wz, "black", 0)

AIBuilder().build_from_recipe(jeep)
save_blend("/home/user/my_jeep.blend")
```

### Loading a Recipe from JSON

```bash
# Create a recipe file
cat > my_build.json << 'EOF'
{
  "name": "tiny_house",
  "steps": [
    ["Plate_2x4", 0, 0, 0, "tan", 0],
    ["Plate_2x4", 2, 0, 0, "tan", 0],
    ["Brick_2x2", 0, 1, 0, "red", 0],
    ["Brick_2x2", 2, 1, 0, "red", 0],
    ["Slope_2x2", 0, 2, 0, "brown", 0],
    ["Slope_2x2", 2, 2, 0, "brown", 0]
  ]
}
EOF
```

Then in Blender:
```python
from bits_and_baubles_kit import create_brick_library, build_from_json
create_brick_library()
build_from_json("/path/to/my_build.json")
```

---

## Headless / Batch Mode

Run without opening Blender's GUI:

```bash
# Linux / Mac
blender --background --python bits_and_baubles_kit.py

# Windows
"C:\Program Files\Blender Foundation\Blender\blender.exe" --background --python bits_and_baubles_kit.py
```

Output will be saved to:
- `output/bnb_demos.blend` (relative to the script location)

For CI/automation:
```bash
blender --background --python bits_and_baubles_kit.py 2>&1 | tee build.log
```

---

## The 5 Demo Structures

### 1. Cozy House
- **Size:** 8x6 stud base, 5 bricks tall
- **Colors:** Tan walls, brown roof, red chimney
- **Features:** Floor plate, walls with door cutout and window cutout, pitched roof with slopes, chimney stack
- **Piece count:** ~50 bricks
- **Techniques:** Wall construction, cutouts, layered roof, vertical chimney

### 2. Castle Tower
- **Size:** 4x4 base, 12 bricks tall
- **Colors:** Gray walls, dark gray accents
- **Features:** Flared base, arrow slit windows, internal floors, crenellated top
- **Piece count:** ~55 bricks
- **Techniques:** Vertical stacking, floor plates, alternating crenellations

### 3. Stone Bridge
- **Size:** 16x4 span, 4 bricks tall
- **Colors:** Light gray stone, dark gray road
- **Features:** Two support pillars, road surface, arch fill, side railings with tile tops
- **Piece count:** ~75 bricks
- **Techniques:** Long span, pillar construction, railing details

### 4. Off-Road Vehicle
- **Size:** 6x10 chassis
- **Colors:** Green body, dark gray details, tan seat, black wheels
- **Features:** Chassis, body walls, hood, driver seat, steering wheel, roll bars, 4 wheels
- **Piece count:** ~65 bricks
- **Techniques:** Vehicle proportions, offset pieces, wheel placement

### 5. Park Tree
- **Size:** 2x2 trunk, 3 layers of canopy
- **Colors:** Brown trunk, two-tone green canopy
- **Features:** Root flare, 2x2 trunk column, 3-layer round canopy, top ornament
- **Piece count:** ~45 bricks
- **Techniques:** Organic shaping with layers, two-tone coloring, round pieces

---

## Troubleshooting

### "No module named 'bpy'"
**Cause:** You're trying to run the script with your system Python, not Blender's Python.  
**Fix:** Run it inside Blender's Scripting workspace, or use `blender --python bits_and_baubles_kit.py`.

### Pieces appear too small / too large
**Cause:** Scene units mismatch. The script uses 1 Blender unit = 1 meter.  
**Fix:** In Blender, go to Scene Properties > Units and set:
- Unit System: Metric
- Length: Meters
- Scale: 1.0

### Objects overlap or z-fight
**Cause:** Grid snap rounding error.  
**Fix:** The built-in grid snap should prevent this. If building manually, ensure coordinates are multiples of `STUD` (0.008).

### "Piece 'X' not found in library"
**Cause:** `create_brick_library()` wasn't called before placing bricks.  
**Fix:** Always call `create_brick_library()` at the start of your script.

### Script runs but nothing appears
**Cause:** Objects may be scaled to 0 or placed off-screen.  
**Fix:** Press `A` to select all, then `Numpad .` to frame selected. Check the Outliner for collections.

### Slow performance with many bricks
**Cause:** Each brick is a separate mesh object. 1000+ objects will slow Blender.  
**Fix:** Use fewer bricks, or after building select all and use `Object > Join` (Ctrl+J) to merge meshes.

### How to change colors?
Edit the `PIECE_COLORS` dictionary in the script, or pass a different color name to `recipe.add()` or `place_brick()`. Colors are Blender RGBA tuples.

### How to add new brick types?
Add an entry to `PIECE_DEFS` following the format: `"Name": (width_studs, depth_studs, height, "category")`. The geometry generator handles `plate`, `brick`, `slope`, `tile`, `round`, and `round_plate` categories automatically.

### Can I use this with Blender 4.x?
Yes. The script uses core bpy APIs that are stable across Blender 3.x and 4.x. The Principled BSDF node may have slightly different socket names in 4.x; if you see pink materials, check the node socket names in `get_material()`.

---

## File Structure

```
bits_and_baubles/
|-- bits_and_baubles_kit.py          # Master integration script (THIS FILE)
|-- README.md                     # This documentation
|-- output/
|   |-- bnb_demos.blend          # Auto-generated after running
|
|-- my_recipes/                   # Your custom recipes (create as needed)
|   |-- house_variant.json
|   |-- spaceship.json
|
|-- Optional companion modules (if present, auto-loaded):
|   |-- snap_system/
|   |   |-- __init__.py           # StudGrid, PlacementEngine, Assembly
|   |
|   |-- ai_builder/
|   |   |-- __init__.py           # AIBuilder, BrickRecipe, generators
|   |
|   |-- validator/
|   |   |-- __init__.py           # StructuralValidator, ProportionAnalyzer
```

---

## Constants Reference

| Constant | Value | Description |
|----------|-------|-------------|
| `STUD` | 0.008 | 1 stud = 8mm |
| `PLATE_H` | 0.004 | Plate height (3.2mm) |
| `BRICK_H` | 0.012 | Brick height (9.6mm) |
| `STUD_RADIUS` | 0.003 | Stud cylinder radius (3mm) |
| `STUD_HEIGHT` | 0.002125 | Stud cylinder height |
| `WALL_THICKNESS` | 0.001 | Hollow brick wall thickness |
| `TUBE_RADIUS` | 0.0024 | Inner support tube radius |

---

## Team & Credits

Built by the **Centuria Forge Domain** swarm -- 5 specialized AI agents:

| Agent | Role | Contribution |
|-------|------|-------------|
| **BrickSmith** | Geometry Artisan | 25-piece brick library with realistic stud/hollow/tube geometry |
| **SnapEngineer** | Grid Specialist | Stud grid snap system, placement engine, collision detection |
| **BuilderAI** | Recipe Engineer | Recipe format, 5 preset generators, JSON import/export |
| **StructuralCritic** | Quality Assurance | Structural validation, proportion analysis, issue detection |
| **DemoArchitect** | Integration Lead | Master script, menu system, documentation, this file |

**Production:** Centuria Swarm v1.0  
**Domain:** Forge (Creative Production)  
**License:** MIT -- free to use, modify, and distribute

---

*"Every great build starts with a single brick."*  
*-- The Centuria Forge Swarm*
