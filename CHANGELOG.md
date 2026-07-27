# Changelog

## 2.1.0 — CC0 arena visual upgrade

- Added curated Poly Haven and ambientCG PBR materials for arena floors, walls, props and skyline facades.
- Added a Poly Haven panoramic HDRI for environment lighting and reflections.
- Added deterministic Unity import settings for normal, mask, color and HDR textures.
- Reduced atmospheric particle load while preserving the neon arena mood.
- Kept all procedural fallbacks active when external assets are unavailable.

## 2.0.0 — Unity conversion

- Rebuilt the game as a Unity 6.3 LTS project.
- Added URP 17.3 lighting, bloom, ACES tonemapping, fog and emissive arena materials.
- Added KayKit CC0 adventurers and skeletons through pinned downloads.
- Added Kenney Mini Arena and City Kit Industrial CC0 environment sources.
- Reimplemented combat, AI, five modes, menus, keyboard and gamepad input in C#.
- Added dynamic camera framing, camera shake, projectiles and impact particle effects.
- Added procedural visual fallbacks for offline or failed asset downloads.
- Added Unity EditMode tests, Windows player smoke testing and conditional GameCI builds.
- Removed the former Godot source tree and Godot build workflow.
