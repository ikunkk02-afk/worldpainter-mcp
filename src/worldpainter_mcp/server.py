from __future__ import annotations

from typing import Any

from mcp.server.fastmcp import FastMCP

from .project import ProjectService

mcp = FastMCP(
    "WorldPainter Terrain MCP",
    instructions=(
        "Use wp_get_world_info first. All modifications must follow plan -> preview -> apply. "
        "Never claim a world was changed until wp_apply_terrain_plan succeeds. Writes default to a new .world copy."
    ),
)
service = ProjectService()


@mcp.tool()
def wp_get_world_info(world_path: str) -> dict[str, Any]:
    """Read a .world project name, platform, dimensions, bounds, height ranges and layer names. Read-only."""
    return service.world_info(world_path)


@mcp.tool()
def wp_export_heightmap(world_path: str, dimension: str | None = None,
                        output_path: str | None = None) -> dict[str, Any]:
    """Export a dimension heightmap to PNG plus lossless bridge data. Dimension may be its selector, name or index."""
    return service.export_heightmap(world_path, dimension, output_path)


@mcp.tool()
def wp_analyze_terrain(world_path: str, dimension: str | None = None,
                       sea_level: float | None = None) -> dict[str, Any]:
    """Compute elevation and slope statistics, optional coast coverage, and a heightmap preview. Read-only."""
    return service.analyze(world_path, dimension, sea_level)


@mcp.tool()
def wp_plan_terrain_edit(
    world_path: str,
    dimension: str | None = None,
    height_operations: list[dict[str, Any]] | None = None,
    paint_operations: list[dict[str, Any]] | None = None,
    region: dict[str, Any] | None = None,
    mask_path: str | None = None,
) -> dict[str, Any]:
    """Create a non-writing edit plan.

    Height operation types: smooth(radius,passes,strength), erosion(iterations,talus,strength),
    ridge_valley(radius,scale,strength), raise_lower(delta,strength),
    slope_limit(max_slope,iterations,strength), coastline_soften(sea_level,width,radius,strength).
    Paint operation types: terrain(terrain), layer(layer,value), biome(biome_id),
    plants(layer, plants=[{name,weight}], density=0.25,seed=1),
    water(data_path): NPZ with equal 1D arrays x,y (absolute integer world coordinates),
    bed (float ground height), water (integer water level). Only lowers existing ground.
    Water does not clear plants or change terrain/biomes; add masked layer/terrain/biome operations.
    Plants creates a NEW native Custom Plants layer, with valid-block checks and no farmland.
    Each paint operation may have its own mask_path, intersected with the global mask.
    Use wp_get_world_info to see existing layer names; plants must use a new name.
    Region types: rectangle(x,y,width,height,feather), circle(center_x,center_y,radius,feather),
    or polygon(points,feather). mask_path may point to a grayscale image covering the full dimension.
    This tool never saves a .world file; preview is mandatory next.
    """
    return service.create_plan(world_path, dimension, height_operations, paint_operations, region, mask_path)


@mcp.tool()
def wp_preview_terrain_edit(plan_id: str) -> dict[str, Any]:
    """Generate before/after/delta PNGs and a one-time preview_id for a plan. Does not write a .world file."""
    return service.preview(plan_id)


@mcp.tool()
def wp_apply_terrain_plan(plan_id: str, preview_id: str, output_path: str | None = None,
                          overwrite_original: bool = False,
                          allow_overwrite_output: bool = False) -> dict[str, Any]:
    """Apply an already previewed plan via WorldPainter, snapshot first, and save a new copy by default."""
    return service.apply(plan_id, preview_id, output_path, overwrite_original, allow_overwrite_output)


@mcp.tool()
def wp_list_snapshots(world_path: str | None = None) -> dict[str, Any]:
    """List safety snapshots, optionally restricted to one original .world path."""
    return service.list_snapshots(world_path)


@mcp.tool()
def wp_rollback_snapshot(snapshot_id: str, output_path: str | None = None,
                         overwrite_original: bool = False) -> dict[str, Any]:
    """Restore a snapshot to a new .world copy by default; original overwrite requires explicit opt-in."""
    return service.rollback(snapshot_id, output_path, overwrite_original)
