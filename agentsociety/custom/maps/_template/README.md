# GOD Map Package Template

Copy this directory to `agentsociety/custom/maps/<your_map_id>/`, rename the
package, and replace `map.yaml`, `visuals/map.json`, and the assets.

The v1 contract expects a Tiled JSON map with a tile layer named `Collisions`.
In that layer, `0` means walkable and any non-zero tile means blocked.
