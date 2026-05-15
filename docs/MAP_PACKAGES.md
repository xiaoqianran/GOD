# GOD Map Packages

GOD map packages are local folders under:

```text
agentsociety/custom/maps/<map_id>/
```

Drop a new folder there, restart or refresh the setup page, and the map appears
in the experiment setup wizard.

## Required Layout

```text
map.yaml
README.md
ATTRIBUTION.md
visuals/
  map.json
  map_assets/**/*.png
characters/
  atlas.json optional
  *.png
location_assets/ optional
  *.png
```

`map.yaml` is the semantic manifest. `visuals/map.json` is a Tiled JSON map.
Tileset image paths inside the Tiled JSON must be relative paths that stay
inside the map package folder.

## Manifest Fields

Minimum `map.yaml`:

```yaml
schema_version: 1
map_id: your_map_id
display_name: Your Map Name
tiled_map_path: visuals/map.json
tile_size: 32
character_root: characters
spawn_points:
  - id: resident_start
    location_id: plaza
locations:
  - id: plaza
    name: Plaza
    aliases: [plaza]
    anchor_tile: {x: 1, y: 1}
    interaction_ids: [wait]
interactions:
  - id: wait
    name: Wait
    allowed_location_ids: [plaza]
```

Recommended optional fields:

- `default_location_order`: preferred fallback order for generated agents.
- `bounds`: `{x, y, w, h}` region for a location.
- `scene_type`: compact category such as `home`, `school`, `market`.
- `visual_asset`: relative path to an icon in `location_assets/`.
- `effects`: interaction output fields such as `action`, `status`, `emotion`,
  and `latest_event`.

## Tiled JSON Rules

v1 supports only orthogonal Tiled JSON maps:

- `orientation` should be `orthogonal`.
- `tilewidth` and `tileheight` should match `tile_size`.
- The map must include a tile layer named `Collisions`.
- In `Collisions`, `0` means walkable and any non-zero tile means blocked.
- Tileset images must be PNG files inside the map package.
- TMX, external tileset files, remote images, and single-background-image maps
  are not supported in v1.

## Validation

Run:

```bash
cd agentsociety
uv run python scripts/validate_map_package.py custom/maps/<map_id>
```

The validator checks required fields, resource paths, Tiled JSON shape, tileset
images, `Collisions`, location anchors, and interaction references. The old
The Ville semantic check still exists as:

```bash
uv run python scripts/validate_the_ville_map.py
```

## Existing Template

Use `agentsociety/custom/maps/the_ville/` as the complete working example and
`agentsociety/custom/maps/_template/` as the minimal package starter.
