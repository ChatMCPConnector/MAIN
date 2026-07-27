using System;
using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Riftbound
{
    public enum BiomeKind { SunkenRuins, AshenWastes, CrystalDepths }
    public enum RoomModifierKind { None, Frenzy, Fortified, Volatile, BloodMoon, Riftstorm }

    [Serializable]
    public sealed class BiomeDefinition
    {
        public BiomeKind kind;
        public string title;
        public Color floorColor;
        public Color wallColor;
        public Color accentColor;
        public Color skyColor;
        public float enemyHealthMultiplier = 1f;
        public float enemyDamageMultiplier = 1f;
        public float enemySpeedMultiplier = 1f;
        public float projectileSpeedMultiplier = 1f;
    }

    [Serializable]
    public sealed class RoomModifierDefinition
    {
        public RoomModifierKind kind;
        public string title;
        public string description;
        public Color accentColor;
        public float enemyHealthMultiplier = 1f;
        public float enemyDamageMultiplier = 1f;
        public float enemySpeedMultiplier = 1f;
        public float projectileSpeedMultiplier = 1f;
        public float specialCooldownMultiplier = 1f;
    }

    public readonly struct EncounterTuning
    {
        public EncounterTuning(
            BiomeDefinition biome,
            RoomModifierDefinition modifier,
            float health,
            float damage,
            float speed,
            float projectileSpeed,
            float specialCooldown)
        {
            Biome = biome;
            Modifier = modifier;
            EnemyHealthMultiplier = health;
            EnemyDamageMultiplier = damage;
            EnemySpeedMultiplier = speed;
            ProjectileSpeedMultiplier = projectileSpeed;
            SpecialCooldownMultiplier = specialCooldown;
        }

        public BiomeDefinition Biome { get; }
        public RoomModifierDefinition Modifier { get; }
        public float EnemyHealthMultiplier { get; }
        public float EnemyDamageMultiplier { get; }
        public float EnemySpeedMultiplier { get; }
        public float ProjectileSpeedMultiplier { get; }
        public float SpecialCooldownMultiplier { get; }
    }

    public static class BiomeCatalog
    {
        public static readonly BiomeDefinition[] Biomes =
        {
            new BiomeDefinition
            {
                kind = BiomeKind.SunkenRuins,
                title = "Versunkene Ruinen",
                floorColor = new Color(.10f, .14f, .18f),
                wallColor = new Color(.18f, .23f, .28f),
                accentColor = new Color(.22f, .78f, .72f),
                skyColor = new Color(.025f, .07f, .09f),
                enemyHealthMultiplier = 1.04f
            },
            new BiomeDefinition
            {
                kind = BiomeKind.AshenWastes,
                title = "Aschenöde",
                floorColor = new Color(.20f, .10f, .07f),
                wallColor = new Color(.30f, .16f, .10f),
                accentColor = new Color(1f, .34f, .08f),
                skyColor = new Color(.12f, .035f, .025f),
                enemyDamageMultiplier = 1.08f,
                enemySpeedMultiplier = 1.08f
            },
            new BiomeDefinition
            {
                kind = BiomeKind.CrystalDepths,
                title = "Kristalltiefen",
                floorColor = new Color(.08f, .09f, .22f),
                wallColor = new Color(.15f, .16f, .34f),
                accentColor = new Color(.48f, .42f, 1f),
                skyColor = new Color(.025f, .025f, .12f),
                enemyHealthMultiplier = 1.12f,
                projectileSpeedMultiplier = 1.12f
            }
        };

        public static readonly RoomModifierDefinition[] Modifiers =
        {
            Modifier(RoomModifierKind.None, "Keine Anomalie", "Standardbedingungen", new Color(.55f, .62f, .72f)),
            Modifier(RoomModifierKind.Frenzy, "Rasende Jagd", "+22 % Gegnertempo", new Color(1f, .58f, .12f), 1f, 1.08f, 1.22f, 1f, .84f),
            Modifier(RoomModifierKind.Fortified, "Verstärkte Hüllen", "+35 % Gegnerleben", new Color(.62f, .74f, 1f), 1.35f),
            Modifier(RoomModifierKind.Volatile, "Instabile Geschosse", "+35 % Projektiltempo", new Color(.94f, .32f, 1f), 1f, 1.10f, 1f, 1.35f, .9f),
            Modifier(RoomModifierKind.BloodMoon, "Blutmond", "+22 % Gegnerschaden", new Color(1f, .12f, .24f), .94f, 1.22f, 1.04f),
            Modifier(RoomModifierKind.Riftstorm, "Risssturm", "Boss-Anomalie: alle Werte erhöht", new Color(.24f, .92f, 1f), 1.15f, 1.15f, 1.10f, 1.25f, .75f)
        };

        public static BiomeDefinition GetBiome(BiomeKind kind)
        {
            return Biomes[(int)kind];
        }

        public static RoomModifierDefinition GetModifier(RoomModifierKind kind)
        {
            return Modifiers[(int)kind];
        }

        private static RoomModifierDefinition Modifier(
            RoomModifierKind kind,
            string title,
            string description,
            Color accent,
            float health = 1f,
            float damage = 1f,
            float speed = 1f,
            float projectile = 1f,
            float cooldown = 1f)
        {
            return new RoomModifierDefinition
            {
                kind = kind,
                title = title,
                description = description,
                accentColor = accent,
                enemyHealthMultiplier = health,
                enemyDamageMultiplier = damage,
                enemySpeedMultiplier = speed,
                projectileSpeedMultiplier = projectile,
                specialCooldownMultiplier = cooldown
            };
        }
    }

    public static class BiomePlanner
    {
        public static BiomeKind[] Generate(int seed)
        {
            var order = new[]
            {
                BiomeKind.SunkenRuins,
                BiomeKind.AshenWastes,
                BiomeKind.CrystalDepths
            };
            var rng = new System.Random(unchecked(seed ^ 0x6e624eb7));
            for (var i = order.Length - 1; i > 0; i--)
            {
                var swap = rng.Next(i + 1);
                (order[i], order[swap]) = (order[swap], order[i]);
            }

            return new[]
            {
                order[0], order[0], order[0],
                order[1], order[1], order[1],
                order[2], order[2]
            };
        }

        public static BiomeKind ForRoom(int seed, int roomIndex)
        {
            var plan = Generate(seed);
            return plan[Mathf.Clamp(roomIndex, 0, plan.Length - 1)];
        }
    }

    public static class ModifierPlanner
    {
        public static RoomModifierKind ForRoom(int seed, int roomIndex)
        {
            var rooms = RunPlanner.Generate(seed);
            var safeIndex = Mathf.Clamp(roomIndex, 0, rooms.Length - 1);
            var room = GameCatalog.GetRoom(rooms[safeIndex]);

            if (room.kind == RoomKind.Treasure ||
                room.kind == RoomKind.Merchant ||
                room.kind == RoomKind.Healing)
                return RoomModifierKind.None;
            if (room.kind == RoomKind.Boss)
                return RoomModifierKind.Riftstorm;

            var rng = new System.Random(unchecked(seed * 92821 + safeIndex * 68917));
            if (room.kind == RoomKind.Combat && rng.Next(100) < 24)
                return RoomModifierKind.None;

            return (RoomModifierKind)rng.Next(
                (int)RoomModifierKind.Frenzy,
                (int)RoomModifierKind.BloodMoon + 1);
        }
    }

    public static class EncounterDirector
    {
        public static EncounterTuning Create(int seed, int roomIndex)
        {
            var rooms = RunPlanner.Generate(seed);
            var safeIndex = Mathf.Clamp(roomIndex, 0, rooms.Length - 1);
            var room = GameCatalog.GetRoom(rooms[safeIndex]);
            var biome = BiomeCatalog.GetBiome(BiomePlanner.ForRoom(seed, safeIndex));
            var modifier = BiomeCatalog.GetModifier(ModifierPlanner.ForRoom(seed, safeIndex));

            var progressionHealth = 1f + safeIndex * .09f + room.difficulty * .035f;
            var progressionDamage = 1f + safeIndex * .065f + room.difficulty * .025f;
            var progressionSpeed = 1f + Mathf.Min(.14f, safeIndex * .018f);

            return new EncounterTuning(
                biome,
                modifier,
                progressionHealth * biome.enemyHealthMultiplier * modifier.enemyHealthMultiplier,
                progressionDamage * biome.enemyDamageMultiplier * modifier.enemyDamageMultiplier,
                progressionSpeed * biome.enemySpeedMultiplier * modifier.enemySpeedMultiplier,
                biome.projectileSpeedMultiplier * modifier.projectileSpeedMultiplier,
                modifier.specialCooldownMultiplier);
        }
    }

    public sealed class BiomeRuntimeController : MonoBehaviour
    {
        private readonly List<GameObject> decorations = new List<GameObject>();
        private GameBootstrap game;
        private int lastSeed = int.MinValue;
        private int lastRoom = -1;
        private int generation;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<BiomeRuntimeController>() != null) return;
            var root = new GameObject("Biome Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<BiomeRuntimeController>();
        }

        private void Update()
        {
            if (game == null)
            {
                game = FindFirstObjectByType<GameBootstrap>();
                if (game == null) return;
            }

            if (game.Seed == lastSeed && game.RoomIndex == lastRoom) return;
            lastSeed = game.Seed;
            lastRoom = game.RoomIndex;
            generation++;
            StartCoroutine(ApplyAfterRoomLoad(generation, lastSeed, lastRoom));
        }

        private IEnumerator ApplyAfterRoomLoad(int token, int seed, int roomIndex)
        {
            yield return new WaitForSecondsRealtime(.32f);
            if (token != generation || game == null) yield break;

            var tuning = EncounterDirector.Create(seed, roomIndex);
            ApplyLighting(tuning.Biome);
            TintRoom(tuning.Biome, tuning.Modifier);
            BuildDecorations(tuning.Biome, tuning.Modifier);

            var hud = FindFirstObjectByType<TouchHud>();
            hud?.ShowMessage(
                $"{tuning.Biome.title}\n{tuning.Modifier.title}",
                1.8f);
        }

        private static void ApplyLighting(BiomeDefinition biome)
        {
            if (Camera.main != null)
                Camera.main.backgroundColor = biome.skyColor;

            var key = GameObject.Find("Key Light")?.GetComponent<Light>();
            if (key != null)
            {
                key.color = Color.Lerp(Color.white, biome.accentColor, .32f);
                key.intensity = 1.15f;
            }

            var fill = GameObject.Find("Fill Light")?.GetComponent<Light>();
            if (fill != null)
            {
                fill.color = biome.accentColor;
                fill.intensity = 3.6f;
            }
        }

        private static void TintRoom(
            BiomeDefinition biome,
            RoomModifierDefinition modifier)
        {
            var renderers = FindObjectsByType<Renderer>(FindObjectsSortMode.None);
            foreach (var renderer in renderers)
            {
                if (renderer == null) continue;
                switch (renderer.gameObject.name)
                {
                    case "Floor":
                        renderer.sharedMaterial = WorldFactory.GetLitMaterial(
                            Color.Lerp(biome.floorColor, modifier.accentColor, .10f));
                        break;
                    case "Wall":
                        renderer.sharedMaterial = WorldFactory.GetLitMaterial(biome.wallColor);
                        break;
                    case "Obstacle":
                        renderer.sharedMaterial = WorldFactory.GetLitMaterial(
                            Color.Lerp(biome.wallColor, biome.accentColor, .25f));
                        break;
                }
            }
        }

        private void BuildDecorations(
            BiomeDefinition biome,
            RoomModifierDefinition modifier)
        {
            foreach (var decoration in decorations)
                if (decoration != null) Destroy(decoration);
            decorations.Clear();

            var positions = new[]
            {
                new Vector3(-3.5f, .45f, -1.8f),
                new Vector3(3.5f, .45f, -1.8f),
                new Vector3(-3.5f, .45f, 3.8f),
                new Vector3(3.5f, .45f, 3.8f)
            };

            foreach (var position in positions)
            {
                var primitive = biome.kind == BiomeKind.AshenWastes
                    ? PrimitiveType.Cylinder
                    : biome.kind == BiomeKind.CrystalDepths
                        ? PrimitiveType.Cube
                        : PrimitiveType.Cylinder;
                var scale = biome.kind == BiomeKind.CrystalDepths
                    ? new Vector3(.35f, 1.5f, .35f)
                    : biome.kind == BiomeKind.AshenWastes
                        ? new Vector3(.55f, .18f, .55f)
                        : new Vector3(.55f, .9f, .55f);
                AddDecoration(primitive, position, scale, biome.accentColor);
            }

            if (modifier.kind != RoomModifierKind.None)
            {
                AddDecoration(
                    PrimitiveType.Cylinder,
                    new Vector3(0f, .035f, 1f),
                    new Vector3(1.1f, .035f, 1.1f),
                    modifier.accentColor);
            }
        }

        private void AddDecoration(
            PrimitiveType primitive,
            Vector3 position,
            Vector3 scale,
            Color color)
        {
            var decoration = WorldFactory.CreatePrimitive(
                "BiomeDecoration",
                primitive,
                position,
                scale,
                color);
            var collider = decoration.GetComponent<Collider>();
            if (collider != null) collider.enabled = false;
            decorations.Add(decoration);
        }
    }
}
