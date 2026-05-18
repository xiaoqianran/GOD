# Peking University Yanyuan Map Package

This package is a self-contained GOD v1 map package for a stylized Peking University Yanyuan campus. The visual layer is built from package-local imagegen assets and keeps the same Tiled/tileset shape as `custom/maps/the_ville`: exterior tilesets, room builder, five interior sheets, block sheets, and 32px character spritesheets.

It is not a surveyed GIS map. The layout preserves simulation-friendly PKU semantics: West Gate, East Gate, South Gate, Weiming Lake, Boya Pagoda, PKU Library, Centennial Hall, teaching buildings, dormitory, canteen, gym, lab, offices, and a campus green.

## Files

- `map.yaml` - semantic manifest with spawn points, locations, aliases, interactions, and asset paths.
- `visuals/map.json` - orthogonal Tiled JSON, 140x100 tiles, 32px tile size.
- `visuals/map_assets/cute_rpg_word_VXAce/tilesets/*.png` - generated PKU exterior tilesets matching The Ville's tileset names and dimensions.
- `visuals/map_assets/v1/Room_Builder_32x32.png` and `visuals/map_assets/v1/interiors_pt*.png` - generated PKU interior/room tilesets.
- `visuals/map_assets/blocks/*.png` - generated interaction/collision block tilesets.
- `visuals/map_assets/pku_generated/pku_full_map_tileset.png` - high-detail PKU campus render sliced into a 32px Tiled tileset for the assembled replay map.
- `characters/*.png` - generated 32px PKU character spritesheets.

## Validation

```bash
uv run python scripts/validate_map_package.py custom/maps/pku
```

## Notes

Location anchors are placed on walkable paths adjacent to landmark footprints so agents can route to them. Replay marker overlays are intentionally not used, matching The Ville's visual presentation.
