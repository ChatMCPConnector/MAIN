# Asset sources and licenses

The Unity project keeps third-party binary art out of Git and downloads selected files into ignored directories. This avoids accidentally republishing proprietary Asset Store content and makes each source auditable.

## Official Unity packages

| Package | Version or pin | Purpose | License channel |
|---|---:|---|---|
| Unity Universal Render Pipeline | 17.3.0 | Lighting, shadows and post-processing | Unity Package Manager |
| Unity Input System | 1.17.0 | Keyboard and gamepad input | Unity Package Manager |
| Unity Test Framework | 1.6.0 | EditMode tests | Unity Package Manager |
| Unity UI | 2.0.0 | Unity runtime UI dependency | Unity Package Manager |
| glTFast | Commit `66aa58252bafe6f7f48031f4906f807f95a3f396` | Runtime and Editor glTF/GLB import | Apache-2.0 |

## KayKit Character Pack: Adventurers

- Author: Kay Lousberg / KayKit
- License: Creative Commons CC0 1.0 Universal
- Source repository: `KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0`
- Pinned commit: `672074b73ba276876a19e8816ecdc5241817ab47`
- Selected files: `Knight.glb`, `Barbarian.glb`, `Mage.glb`, `Rogue.glb`
- Editor import destination: `Assets/Resources/Community/KayKit/`

Pinned download base:

```text
https://cdn.jsdelivr.net/gh/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0@672074b73ba276876a19e8816ecdc5241817ab47/addons/kaykit_character_pack_adventures/Characters/gltf/
```

## KayKit Character Pack: Skeletons

- Author: Kay Lousberg / KayKit
- License: Creative Commons CC0 1.0 Universal
- Source repository: `KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0`
- Pinned commit: `15b62b9bad122f72926c10fb14d622c73819fa54`
- Selected files: `Skeleton_Warrior.glb`, `Skeleton_Rogue.glb`, `Skeleton_Mage.glb`, `Skeleton_Minion.glb`
- Editor import destination: `Assets/Resources/Community/KayKit/`

Pinned download base:

```text
https://cdn.jsdelivr.net/gh/KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0@15b62b9bad122f72926c10fb14d622c73819fa54/addons/kaykit_character_pack_skeletons/Characters/gltf/
```

## Kenney Mini Arena

- Author: Kenney
- License: Creative Commons CC0 1.0 Universal
- Download archive:

```text
https://kenney.nl/media/pages/assets/mini-arena/88f977a0cb-1709220730/kenney_mini-arena.zip
```

## Kenney City Kit Industrial

- Author: Kenney
- License: Creative Commons CC0 1.0 Universal
- Download archive:

```text
https://kenney.nl/media/pages/assets/city-kit-industrial/5fcb837741-1750838303/kenney_city-kit-industrial_1.0.zip
```

## Fallback art

Every fighter, arena and visual effect has a code-generated fallback made from Unity primitives and original materials. The fallback source is covered by this repository's MIT license.

## Excluded content

The project does not include Little Fighter 2 files, names, characters, graphics, audio, code or data. It also does not redistribute Unity Asset Store packages whose licenses require acquisition through an individual Unity account.
