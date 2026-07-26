using System;
using System.Collections.Generic;
using UnityEngine;

namespace NeonRift
{
    public enum GameMode
    {
        StageRun,
        LocalVersus,
        TeamBattle,
        Training,
        Survival
    }

    public enum GameScreen
    {
        MainMenu,
        ModeSelect,
        CharacterSelect,
        ArenaSelect,
        Playing,
        Paused,
        Result,
        Controls
    }

    public enum FighterRole
    {
        Player,
        Ally,
        Enemy,
        Boss,
        TrainingDummy
    }

    [Serializable]
    public sealed class FighterSpec
    {
        public string Name;
        public string Tagline;
        public string ModelFile;
        public Color Primary;
        public Color Accent;
        public float MaxHealth;
        public float Speed;
        public float Power;
        public float SpecialPower;

        public FighterSpec(
            string name,
            string tagline,
            string modelFile,
            Color primary,
            Color accent,
            float maxHealth,
            float speed,
            float power,
            float specialPower)
        {
            Name = name;
            Tagline = tagline;
            ModelFile = modelFile;
            Primary = primary;
            Accent = accent;
            MaxHealth = maxHealth;
            Speed = speed;
            Power = power;
            SpecialPower = specialPower;
        }
    }

    [Serializable]
    public sealed class ArenaSpec
    {
        public string Name;
        public string Subtitle;
        public Color Sky;
        public Color Fog;
        public Color Ground;
        public Color Neon;
        public string[] PropKeywords;

        public ArenaSpec(
            string name,
            string subtitle,
            Color sky,
            Color fog,
            Color ground,
            Color neon,
            params string[] propKeywords)
        {
            Name = name;
            Subtitle = subtitle;
            Sky = sky;
            Fog = fog;
            Ground = ground;
            Neon = neon;
            PropKeywords = propKeywords;
        }
    }

    public static class NeonRiftCatalog
    {
        public static readonly IReadOnlyList<FighterSpec> Fighters = new[]
        {
            new FighterSpec(
                "Kira Volt", "Lightning duelist", "Knight.glb",
                new Color(0.13f, 0.72f, 1f), new Color(0.75f, 0.96f, 1f),
                110f, 7.6f, 1.0f, 1.2f),
            new FighterSpec(
                "Brakk Forge", "Armored powerhouse", "Barbarian.glb",
                new Color(1f, 0.35f, 0.13f), new Color(1f, 0.78f, 0.25f),
                145f, 5.6f, 1.28f, 1.32f),
            new FighterSpec(
                "Mira Bloom", "Arcane field medic", "Mage.glb",
                new Color(0.35f, 0.95f, 0.55f), new Color(0.8f, 1f, 0.8f),
                100f, 6.7f, 0.93f, 1.42f),
            new FighterSpec(
                "Nyx Shade", "Shadow rush specialist", "Rogue.glb",
                new Color(0.65f, 0.28f, 1f), new Color(1f, 0.32f, 0.8f),
                95f, 8.4f, 1.06f, 1.18f)
        };

        public static readonly IReadOnlyList<ArenaSpec> Arenas = new[]
        {
            new ArenaSpec(
                "Skyline Foundry", "Rain, steel and reactor light",
                new Color(0.015f, 0.035f, 0.09f), new Color(0.04f, 0.08f, 0.16f),
                new Color(0.09f, 0.11f, 0.15f), new Color(0.05f, 0.88f, 1f),
                "industrial", "crate", "barrel", "pipe", "lamp"),
            new ArenaSpec(
                "Verdant Metro", "An overgrown transit sanctuary",
                new Color(0.025f, 0.11f, 0.095f), new Color(0.05f, 0.16f, 0.12f),
                new Color(0.09f, 0.15f, 0.12f), new Color(0.36f, 1f, 0.56f),
                "tree", "plant", "rock", "bench", "arch"),
            new ArenaSpec(
                "Null Observatory", "A shattered arena above the void",
                new Color(0.035f, 0.015f, 0.09f), new Color(0.09f, 0.035f, 0.14f),
                new Color(0.09f, 0.07f, 0.16f), new Color(0.96f, 0.2f, 0.95f),
                "arena", "column", "banner", "statue", "wall")
        };

        public static readonly IReadOnlyList<string> Modes = new[]
        {
            "Stage Run",
            "Local Versus",
            "Team Battle",
            "Training",
            "Survival"
        };
    }

    public static class GameBalance
    {
        public static float CalculateDamage(float baseDamage, float attackerPower, bool heavy, bool special)
        {
            float multiplier = heavy ? 1.55f : 1f;
            if (special)
            {
                multiplier *= 1.75f;
            }

            return Mathf.Max(1f, baseDamage * Mathf.Max(0.2f, attackerPower) * multiplier);
        }

        public static float KnockbackFor(float damage, bool heavy, bool special)
        {
            float result = 2.2f + damage * 0.045f;
            if (heavy) result += 1.7f;
            if (special) result += 2.4f;
            return result;
        }
    }
}
