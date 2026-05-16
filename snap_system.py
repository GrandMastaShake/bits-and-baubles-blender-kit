#!/usr/bin/env python3
"""Bits and Baubles Snap System — Grid-based placement engine for Blender
Handles snapping, collision detection, height resolution, and undo.

Usage:
    1. Open Blender (or run with ``blender --python snap_system.py``)
    2. The demo will create a small stack of bricks automatically.
    3. Or import the module and use the Assembly class interactively.

    >>> from snap_system import Assembly
    >>> asm = Assembly("MyModel")
    >>> asm.add("Brick_2x4", 0, 0, 0, 0, "#CC3333")
    >>> asm.add("Brick_2x2", 0, 0, -1, 0, "#3366CC")  # auto-stack
"""

import bpy
import bmesh
import math
from typing import Dict, List, Tuple, Optional
from dataclasses import dataclass, field
from collections import defaultdict

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------
STUD = 0.008                  # 1 stud = 8 mm
PLATE_H = 0.004               # plate height (thin brick)
BRICK_H = 0.012               # standard brick height (3 plates)
STUD_RADIUS = 0.00145         # stud cylinder radius
STUD_HEIGHT = 0.0012          # stud cylinder height
WALL_THICKNESS = 0.0008       # brick wall thickness

# ---------------------------------------------------------------------------
# Data classes
# ---------------------------------------------------------------------------

@dataclass
class PlacedBrick:
    """Represents one placed instance of a brick."""
    instance_id: int
    brick_type: str             # e.g. "Brick_2x4"
    grid_x: int                 # grid position (stud units)
    grid_y: int                 # layer / height level
    grid_z: int                 # grid position (stud units)
    rotation: int = 0           # 0, 90, 180, 270 degrees
    color_hex: str = "#CC3333"
    obj_name: str = ""          # Blender object name

    @property
    def world_pos(self) -> Tuple[float, float, float]:
        """Convert grid coords to Blender world position (bottom-centre)."""
        return (self.grid_x * STUD,
                self.grid_y * PLATE_H,
                self.grid_z * STUD)


# ---------------------------------------------------------------------------
# StudGrid
# ---------------------------------------------------------------------------

class StudGrid:
    """Manages the stud grid and occupancy tracking.

    Occupancy is stored per cell as a list of tuples::

        occupied[x][z] = [(y_bottom, height_units, instance_id), ...]

    This allows precise collision detection when multiple bricks overlap
    vertically (e.g. a plate on top of a brick with matching studs).
    """

    def __init__(self, size: int = 32):
        self.size = size
        # occupied[x][z] = list of (y_bottom, height_units, instance_id)
        self.occupied: Dict[int, Dict[int, List[Tuple[int, int, int]]]] = \
            defaultdict(lambda: defaultdict(list))

    # ---- coordinate conversions ------------------------------------------------

    def snap(self, x: float, z: float) -> Tuple[int, int]:
        """Snap world X/Z coordinates to the nearest grid cell."""
        gx = round(x / STUD)
        gz = round(z / STUD)
        return (max(0, min(gx, self.size - 1)),
                max(0, min(gz, self.size - 1)))

    def world_to_grid(self, wx: float, wy: float, wz: float) -> Tuple[int, int, int]:
        """Convert world coordinates to grid coordinates."""
        gx, gz = self.snap(wx, wz)
        gy = round(wy / PLATE_H)
        return (gx, gy, gz)

    def grid_to_world(self, gx: int, gy: int, gz: int) -> Tuple[float, float, float]:
        """Convert grid coordinates to world position (bottom-centre)."""
        return (gx * STUD, gy * PLATE_H, gz * STUD)

    # ---- occupancy helpers ----------------------------------------------------

    def get_height_at(self, gx: int, gz: int) -> int:
        """Return the highest occupied y-level (top) at a grid cell.

        The value returned is the *top* y-level (bottom + height_units).
        If the cell is empty, returns 0.
        """
        cell = self.occupied.get(gx, {}).get(gz, [])
        if not cell:
            return 0
        return max(y_bottom + h_units for y_bottom, h_units, _ in cell)

    def occupies_cells(self, gx: int, gz: int, width: int, depth: int,
                       rotation: int) -> List[Tuple[int, int]]:
        """Return every grid cell (x, z) that a brick would occupy.

        Parameters
        ----------
        gx, gz : int
            Bottom-left corner (before rotation) in grid units.
        width, depth : int
            Brick dimensions in studs.
        rotation : int
            Rotation in degrees (0, 90, 180, 270).

        Returns
        -------
        List[Tuple[int, int]]
            Sorted list of (x, z) grid cells.
        """
        # Normalise rotation to 0/90/180/270
        rot = rotation % 360
        if rot < 0:
            rot += 360

        # For 90deg and 270deg swap width and depth
        if rot in (90, 270):
            width, depth = depth, width

        cells = []
        for dx in range(width):
            for dz in range(depth):
                cells.append((gx + dx, gz + dz))
        return sorted(set(cells))

    def is_clear(self, cells: List[Tuple[int, int]], y_bottom: int,
                 height_units: int) -> bool:
        """Check whether *all* cells are free for the given height range.

        A cell is considered occupied if an existing brick overlaps in the
        vertical span ``[y_bottom, y_bottom + height_units)``.
        """
        y_top = y_bottom + height_units
        for cx, cz in cells:
            cell_entries = self.occupied.get(cx, {}).get(cz, [])
            for existing_yb, existing_h, _ in cell_entries:
                existing_yt = existing_yb + existing_h
                # Overlap test: ranges intersect
                if y_bottom < existing_yt and y_top > existing_yb:
                    return False
        return True

    def place_brick(self, brick: PlacedBrick, width: int, depth: int):
        """Record a brick placement in the occupancy grid."""
        cells = self.occupies_cells(brick.grid_x, brick.grid_z,
                                    width, depth, brick.rotation)
        for cx, cz in cells:
            self.occupied[cx][cz].append((brick.grid_y, brick.height_units,
                                          brick.instance_id))

    def remove_brick(self, brick: PlacedBrick, width: int, depth: int):
        """Remove a brick from the occupancy grid."""
        cells = self.occupies_cells(brick.grid_x, brick.grid_z,
                                    width, depth, brick.rotation)
        for cx, cz in cells:
            entries = self.occupied.get(cx, {}).get(cz, [])
            self.occupied[cx][cz] = [
                e for e in entries if e[2] != brick.instance_id
            ]
            # Clean empty dicts
            if not self.occupied[cx][cz]:
                del self.occupied[cx][cz]
            if not self.occupied[cx]:
                del self.occupied[cx]

    def find_stack_y(self, cells: List[Tuple[int, int]],
                     height_units: int) -> int:
        """Find the lowest y-level where a brick of *height_units* can sit.

        The algorithm places the brick so that its bottom is at the maximum
        ``top_y`` across all covered cells.  This produces the expected Bits and Baubles
        stacking behaviour.
        """
        max_top = 0
        for cx, cz in cells:
            top = self.get_height_at(cx, cz)
            if top > max_top:
                max_top = top
        return max_top


# ---------------------------------------------------------------------------
# PlacementEngine
# ---------------------------------------------------------------------------

class PlacementEngine:
    """Handles brick placement, duplication, and positioning in Blender."""

    # (width_studs, depth_studs, height_units)
    BRICK_DIMS: Dict[str, Tuple[int, int, int]] = {
        "Plate_1x1": (1, 1, 1),   "Plate_1x2": (1, 2, 1),
        "Plate_2x2": (2, 2, 1),   "Plate_2x4": (2, 4, 1),
        "Plate_4x4": (4, 4, 1),
        "Brick_1x1": (1, 1, 3),   "Brick_1x2": (1, 2, 3),
        "Brick_1x4": (1, 4, 3),   "Brick_2x2": (2, 2, 3),
        "Brick_2x4": (2, 4, 3),
        "Slope_2x1_45": (2, 1, 3), "Slope_2x2_33": (2, 2, 3),
        "Wedge_2x2": (2, 2, 3),   "Corner_Slope_2x2": (2, 2, 3),
        "Round_1x1": (1, 1, 3),   "Tile_1x1": (1, 1, 1),
        "Tile_1x2": (1, 2, 1),    "Tile_2x2": (2, 2, 1),
        "Bar_1x2": (1, 2, 1),     "Jumper_2x2": (2, 2, 1),
        "Column_1x1x5": (1, 1, 15),"Macaroni_2x2": (2, 2, 3),
        "Door_1x3x4": (1, 3, 12), "Window_1x2x3": (1, 2, 9),
        "Wheel": (1, 1, 1),
    }

    _counter = 0

    def __init__(self, grid: StudGrid):
        self.grid = grid
        self.placed: Dict[int, PlacedBrick] = {}
        self.history: List[int] = []          # ordered instance_ids for undo

    # ---- public API ----------------------------------------------------------

    def get_dims(self, brick_type: str) -> Tuple[int, int, int]:
        """Get (width, depth, height_units) for a brick type.

        Falls back to (2, 2, 3) for unknown types.
        """
        return self.BRICK_DIMS.get(brick_type, (2, 2, 3))

    def place(self, brick_type: str, grid_x: int, grid_z: int,
              grid_y: int = -1, rotation: int = 0,
              color_hex: str = "#CC3333") -> Optional[PlacedBrick]:
        """Place a brick at grid position.

        Parameters
        ----------
        brick_type : str
            Key in ``BRICK_DIMS`` (e.g. ``"Brick_2x4"``).
        grid_x, grid_z : int
            Horizontal grid position.
        grid_y : int
            Vertical layer.  If ``-1``, the brick is auto-stacked on top
            of whatever already occupies the footprint.
        rotation : int
            Rotation in degrees (0, 90, 180, 270).
        color_hex : str
            Hex colour string (e.g. ``"#CC3333"``).

        Returns
        -------
        PlacedBrick or None
            The placed brick info, or *None* if placement failed.
        """
        # 1. Dimensions
        width, depth, height_units = self.get_dims(brick_type)

        # 2. Normalise rotation
        rot = rotation % 360
        if rot < 0:
            rot += 360
        if rot not in (0, 90, 180, 270):
            rot = round(rot / 90) * 90

        # 3. Compute footprint cells
        cells = self.grid.occupies_cells(grid_x, grid_z, width, depth, rot)

        # Bounds check
        for cx, cz in cells:
            if cx < 0 or cx >= self.grid.size or cz < 0 or cz >= self.grid.size:
                print(f"[SnapSystem] Placement out of bounds: ({cx}, {cz})")
                return None

        # 4. Resolve height (auto-stack)
        if grid_y == -1:
            grid_y = self.grid.find_stack_y(cells, height_units)

        # 5. Collision check
        if not self.grid.is_clear(cells, grid_y, height_units):
            print(f"[SnapSystem] Collision at ({grid_x}, {grid_y}, {grid_z}) "
                  f"for {brick_type}")
            return None

        # 6. Create instance
        PlacementEngine._counter += 1
        instance_id = PlacementEngine._counter

        # Build PlacedBrick (set height_units as a dynamic attr for grid)
        brick = PlacedBrick(
            instance_id=instance_id,
            brick_type=brick_type,
            grid_x=grid_x,
            grid_y=grid_y,
            grid_z=grid_z,
            rotation=rot,
            color_hex=color_hex,
        )
        # Attach height_units so grid can use it without re-querying dims
        brick.height_units = height_units  # type: ignore[attr-defined]

        # 7. Duplicate template in Blender
        obj = self._duplicate_template(brick_type, instance_id)
        if obj is None:
            print(f"[SnapSystem] Failed to create template for {brick_type}")
            return None

        brick.obj_name = obj.name

        # 8. Position in world
        wx, wy, wz = brick.world_pos
        # Adjust for brick centre: the brick extends width/2 and depth/2
        # The grid origin is the bottom-left-back corner
        rot_cells = self.grid.occupies_cells(grid_x, grid_z, width, depth, rot)
        if rot_cells:
            min_cx = min(c[0] for c in rot_cells)
            max_cx = max(c[0] for c in rot_cells)
            min_cz = min(c[1] for c in rot_cells)
            max_cz = max(c[1] for c in rot_cells)
        else:
            min_cx = max_cx = grid_x
            min_cz = max_cz = grid_z

        # Centre offset: brick centre is at (width-1)/2 * STUD from origin
        # But the template is built centred at origin, so shift by centre offset
        cx_off = ((min_cx + max_cx) / 2) * STUD
        cz_off = ((min_cz + max_cz) / 2) * STUD
        cy_off = (height_units * PLATE_H) / 2

        obj.location = (cx_off, wy + cy_off, cz_off)

        # 9. Apply rotation around the vertical (Y) axis
        if rot != 0:
            obj.rotation_euler = (0.0, math.radians(rot), 0.0)
        else:
            obj.rotation_euler = (0.0, 0.0, 0.0)

        # 10. Colour
        self._apply_color(obj, color_hex)

        # 11. Record
        self.grid.place_brick(brick, width, depth)
        self.placed[instance_id] = brick
        self.history.append(instance_id)

        print(f"[SnapSystem] Placed {brick_type} #{instance_id} at "
              f"({grid_x}, {grid_y}, {grid_z}) rot={rot}")
        return brick

    def undo(self) -> bool:
        """Remove the last placed brick.  Returns *True* if successful."""
        if not self.history:
            print("[SnapSystem] Nothing to undo")
            return False

        last_id = self.history.pop()
        brick = self.placed.pop(last_id, None)
        if brick is None:
            return False

        width, depth, _ = self.get_dims(brick.brick_type)
        self.grid.remove_brick(brick, width, depth)

        # Remove from Blender scene
        obj = bpy.data.objects.get(brick.obj_name)
        if obj:
            # Remove mesh data too (since each instance has unique mesh)
            mesh = obj.data
            bpy.data.objects.remove(obj, do_unlink=True)
            if mesh and mesh.users == 0:
                bpy.data.meshes.remove(mesh)

        print(f"[SnapSystem] Undid {brick.brick_type} #{last_id}")
        return True

    def clear(self):
        """Remove all placed bricks, keep library templates."""
        for brick in list(self.placed.values()):
            obj = bpy.data.objects.get(brick.obj_name)
            if obj:
                mesh = obj.data
                bpy.data.objects.remove(obj, do_unlink=True)
                if mesh and mesh.users == 0:
                    bpy.data.meshes.remove(mesh)

        self.placed.clear()
        self.history.clear()
        # Reset occupancy
        self.grid.occupied.clear()
        print("[SnapSystem] All bricks cleared")

    def get_placement_info(self) -> dict:
        """Return statistics about the current assembly.

        Returns
        -------
        dict
            Keys: ``total_pieces``, ``by_type`` (counter dict),
            ``bounds`` (min/max grid coords), ``total_layers``.
        """
        if not self.placed:
            return {
                "total_pieces": 0,
                "by_type": {},
                "bounds": (0, 0, 0, 0, 0, 0),
                "total_layers": 0,
            }

        xs = [b.grid_x for b in self.placed.values()]
        ys = [b.grid_y for b in self.placed.values()]
        zs = [b.grid_z for b in self.placed.values()]

        by_type: Dict[str, int] = defaultdict(int)
        for b in self.placed.values():
            by_type[b.brick_type] += 1

        # Compute max top layer
        max_layer = 0
        for b in self.placed.values():
            top = b.grid_y + getattr(b, "height_units", 3)
            if top > max_layer:
                max_layer = top

        return {
            "total_pieces": len(self.placed),
            "by_type": dict(by_type),
            "bounds": (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs)),
            "total_layers": max_layer,
        }

    # ---- internal helpers ----------------------------------------------------

    def _duplicate_template(self, brick_type: str,
                            instance_id: int) -> Optional[bpy.types.Object]:
        """Duplicate the template mesh for this brick type.

        If the template object does not exist in the scene, a procedural
        stand-in is generated automatically.
        """
        template_obj = bpy.data.objects.get(brick_type)
        if template_obj is None:
            template_obj = self._create_procedural_brick(brick_type)
            if template_obj is None:
                return None

        # Duplicate object + mesh (make single-user)
        new_mesh = template_obj.data.copy()
        new_name = f"Placed_{brick_type}_{instance_id:03d}"
        new_obj = bpy.data.objects.new(new_name, new_mesh)
        bpy.context.collection.objects.link(new_obj)
        return new_obj

    def _create_procedural_brick(self, brick_type: str) -> Optional[bpy.types.Object]:
        """Create a procedural brick mesh from primitive cubes/cylinders.

        This is used as a fallback when no pre-modelled template exists.
        The geometry is simplistic but dimensionally accurate.
        """
        width, depth, height_units = self.get_dims(brick_type)
        brick_height = height_units * PLATE_H
        brick_width = width * STUD
        brick_depth = depth * STUD

        # Deselect all
        bpy.ops.object.select_all(action="DESELECT")

        # Base cube
        bpy.ops.mesh.primitive_cube_add(size=2.0, location=(0, 0, 0))
        base_obj = bpy.context.active_object
        base_obj.name = brick_type
        base_obj.scale = (
            brick_width / 2 - 0.0002,   # X: slightly undersized for gaps
            brick_height / 2,            # Y: half-height (Blender Y = up)
            brick_depth / 2 - 0.0002,   # Z
        )
        bpy.ops.object.transform_apply(scale=True)

        # Add studs on top
        stud_count_x = width
        stud_count_z = depth
        for sx in range(stud_count_x):
            for sz in range(stud_count_z):
                x_pos = (sx - (stud_count_x - 1) / 2) * STUD
                z_pos = (sz - (stud_count_z - 1) / 2) * STUD
                y_pos = brick_height / 2 + STUD_HEIGHT / 2

                bpy.ops.mesh.primitive_cylinder_add(
                    radius=STUD_RADIUS,
                    depth=STUD_HEIGHT,
                    location=(x_pos, y_pos, z_pos),
                )
                stud_obj = bpy.context.active_object
                stud_obj.name = f"{brick_type}_Stud_{sx}_{sz}"

                # Join stud to base
                bpy.ops.object.select_all(action="DESELECT")
                base_obj.select_set(True)
                stud_obj.select_set(True)
                bpy.context.view_layer.objects.active = base_obj
                bpy.ops.object.join()

        # Clean up
        base_obj.select_set(False)
        return base_obj

    def _apply_color(self, obj: bpy.types.Object, color_hex: str):
        """Create and apply a material with the given hex colour."""
        # Parse hex
        color_hex = color_hex.lstrip("#")
        if len(color_hex) == 6:
            r = int(color_hex[0:2], 16) / 255.0
            g = int(color_hex[2:4], 16) / 255.0
            b = int(color_hex[4:6], 16) / 255.0
        else:
            r = g = b = 0.8

        mat_name = f"BnBMat_{color_hex}"
        mat = bpy.data.materials.get(mat_name)
        if mat is None:
            mat = bpy.data.materials.new(name=mat_name)
            mat.use_nodes = True
            # Clear default nodes
            nodes = mat.node_tree.nodes
            links = mat.node_tree.links
            nodes.clear()

            # Create principled BSDF
            bsdf = nodes.new(type="ShaderNodeBsdfPrincipled")
            bsdf.location = (0, 0)
            bsdf.inputs["Base Color"].default_value = (r, g, b, 1.0)
            bsdf.inputs["Roughness"].default_value = 0.3
            bsdf.inputs["Specular IOR Level"].default_value = 0.5

            output = nodes.new(type="ShaderNodeOutputMaterial")
            output.location = (300, 0)
            links.new(bsdf.outputs["BSDF"], output.inputs["Surface"])

        # Assign material
        if obj.data:
            obj.data.materials.clear()
            obj.data.materials.append(mat)


# ---------------------------------------------------------------------------
# Assembly
# ---------------------------------------------------------------------------

class Assembly:
    """High-level assembly manager.

    Provides a convenient interface for building B&B models programmatically.
    """

    def __init__(self, name: str = "Untitled"):
        self.name = name
        self.grid = StudGrid(size=64)
        self.engine = PlacementEngine(self.grid)
        self.bricks: List[PlacedBrick] = []

    def add(self, brick_type: str, gx: int, gz: int, gy: int = -1,
            rot: int = 0, color: str = "#CC3333") -> bool:
        """Add a brick to the assembly.

        Parameters
        ----------
        brick_type : str
            Key in ``PlacementEngine.BRICK_DIMS``.
        gx, gz : int
            Grid position on the X-Z plane.
        gy : int
            Vertical layer.  ``-1`` enables auto-stacking.
        rot : int
            Rotation in degrees.
        color : str
            Hex colour string.

        Returns
        -------
        bool
            *True* if placement succeeded.
        """
        brick = self.engine.place(brick_type, gx, gz, gy, rot, color)
        if brick:
            self.bricks.append(brick)
            return True
        return False

    def undo(self):
        """Undo the last placement."""
        if self.engine.undo():
            if self.bricks:
                self.bricks.pop()

    def clear(self):
        """Remove all placed bricks."""
        self.engine.clear()
        self.bricks = []

    @property
    def piece_count(self) -> int:
        """Total number of bricks currently in the assembly."""
        return len(self.bricks)

    @property
    def bounds(self) -> Tuple[int, int, int, int, int, int]:
        """Return ``(min_x, max_x, min_y, max_y, min_z, max_z)`` in grid units.

        Returns all zeros if the assembly is empty.
        """
        if not self.bricks:
            return (0, 0, 0, 0, 0, 0)
        xs = [b.grid_x for b in self.bricks]
        ys = [b.grid_y for b in self.bricks]
        zs = [b.grid_z for b in self.bricks]
        return (min(xs), max(xs), min(ys), max(ys), min(zs), max(zs))

    def print_summary(self):
        """Print a human-readable summary of the assembly."""
        info = self.engine.get_placement_info()
        print("=" * 50)
        print(f"Assembly: {self.name}")
        print(f"  Pieces : {info['total_pieces']}")
        print(f"  Layers : {info['total_layers']}")
        print(f"  Bounds : {info['bounds']}")
        if info["by_type"]:
            print("  Breakdown:")
            for bt, cnt in sorted(info["by_type"].items()):
                print(f"    {bt:20s} x{cnt}")
        print("=" * 50)


# ---------------------------------------------------------------------------
# Demo
# ---------------------------------------------------------------------------

def demo_snap_system():
    """Quick demo: place a small model to test the snap system.

    Creates a 2x4 foundation with a couple of stacked bricks on top.
    """
    asm = Assembly("SnapDemo")

    # Row of 2x4 bricks along Z
    asm.add("Brick_2x4", 0, 0, 0, 0, "#CC3333")   # red
    asm.add("Brick_2x4", 0, 4, 0, 0, "#CC3333")   # red

    # Stack a 2x2 blue brick on top (auto-stacks to y=3)
    asm.add("Brick_2x2", 0, 0, -1, 0, "#3366CC")  # blue, auto-stack
    asm.add("Brick_2x2", 0, 4, -1, 0, "#3366CC")  # blue, auto-stack

    # A 1x4 plate on top of the blue bricks
    asm.add("Plate_2x4", 0, 0, -1, 0, "#33CC33")  # green, auto-stack to y=6

    # A rotated 2x2 plate bridging the gap
    asm.add("Plate_2x2", 2, 3, -1, 90, "#FFCC00") # yellow, rotated

    asm.print_summary()
    return asm


def demo_wall():
    """Demo: build a simple wall from 1x2 bricks."""
    asm = Assembly("DemoWall")
    for row in range(6):
        y = row * 3
        offset = 0 if row % 2 == 0 else 1
        for col in range(0, 8, 2):
            gx = col + offset
            gz = 0
            color = "#CC3333" if row % 2 == 0 else "#CC6633"
            asm.add("Brick_1x2", gx, gz, y, 0, color)
    asm.print_summary()
    return asm


if __name__ == "__main__":
    print("[SnapSystem] Running demo...")
    demo_snap_system()
