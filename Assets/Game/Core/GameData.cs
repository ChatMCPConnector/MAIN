using System;

namespace Riftbound
{
    public enum EnemyKind { Grunt, Ranged, Elite, Boss }
    public enum RoomKind { Combat, Treasure, Merchant, Healing, Elite, Boss }
    public enum ItemKind { Weapon, Armor }

    [Serializable]
    public sealed class RoomDefinition
    {
        public int index;
        public string title;
        public RoomKind kind;
        public int difficulty;
        public int obstacleCount;
    }

    [Serializable]
    public sealed class CardDefinition
    {
        public string id;
        public string title;
        public string benefit;
        public string drawback;
        public float damageMultiplier = 1f;
        public float maxHealthMultiplier = 1f;
        public float moveSpeedMultiplier = 1f;
        public float attackRateMultiplier = 1f;
        public float cooldownMultiplier = 1f;
        public float incomingDamageMultiplier = 1f;
    }

    [Serializable]
    public sealed class WeaponDefinition
    {
        public string id;
        public string title;
        public float damage;
        public float attackRate;
        public float range;
    }

    [Serializable]
    public sealed class ArmorDefinition
    {
        public string id;
        public string title;
        public float maxHealth;
        public float damageReduction;
    }

    [Serializable]
    public sealed class ShopOffer
    {
        public ItemKind kind;
        public int catalogIndex;
        public int price;
        public string title;
        public string description;
    }

    [Serializable]
    public struct PlayerBuild
    {
        public float maxHealth;
        public float damage;
        public float moveSpeed;
        public float attackRate;
        public float abilityCooldown;
        public float incomingDamageMultiplier;
        public float damageReduction;

        public static PlayerBuild Default => new PlayerBuild
        {
            maxHealth = 100f,
            damage = 18f,
            moveSpeed = 5.4f,
            attackRate = .42f,
            abilityCooldown = 4f,
            incomingDamageMultiplier = 1f,
            damageReduction = 0f
        };
    }

    public static class GameCatalog
    {
        public static readonly RoomDefinition[] Rooms =
        {
            Room(0, "Zerbrochener Vorhof", RoomKind.Combat, 1, 0),
            Room(1, "Schmale Galerie", RoomKind.Combat, 1, 1),
            Room(2, "Kristallgrube", RoomKind.Combat, 2, 2),
            Room(3, "Aschenbrücke", RoomKind.Combat, 2, 1),
            Room(4, "Fluchkapelle", RoomKind.Combat, 3, 2),
            Room(5, "Schatzkammer", RoomKind.Treasure, 0, 0),
            Room(6, "Risshändler", RoomKind.Merchant, 0, 0),
            Room(7, "Heilbrunnen", RoomKind.Healing, 0, 0),
            Room(8, "Elite-Arena", RoomKind.Elite, 4, 2),
            Room(9, "Thronsaal", RoomKind.Boss, 5, 1)
        };

        public static readonly WeaponDefinition[] Weapons =
        {
            new WeaponDefinition { id = "iron_blade", title = "Eisenklinge", damage = 18f, attackRate = .42f, range = 1.65f },
            new WeaponDefinition { id = "ash_spear", title = "Aschenspeer", damage = 15f, attackRate = .36f, range = 2.2f },
            new WeaponDefinition { id = "storm_knuckles", title = "Sturmhandschuhe", damage = 11f, attackRate = .22f, range = 1.25f },
            new WeaponDefinition { id = "grave_hammer", title = "Grabhammer", damage = 27f, attackRate = .68f, range = 1.75f },
            new WeaponDefinition { id = "void_focus", title = "Leerenfokus", damage = 21f, attackRate = .5f, range = 2.6f }
        };

        public static readonly ArmorDefinition[] Armors =
        {
            new ArmorDefinition { id = "warden_helm", title = "Wächterhelm", maxHealth = 8f, damageReduction = .02f },
            new ArmorDefinition { id = "ash_plate", title = "Aschenpanzer", maxHealth = 16f, damageReduction = .05f },
            new ArmorDefinition { id = "swift_gloves", title = "Schnelle Handschuhe", maxHealth = 4f, damageReduction = .01f },
            new ArmorDefinition { id = "rift_boots", title = "Rissstiefel", maxHealth = 6f, damageReduction = .02f },
            new ArmorDefinition { id = "blood_charm", title = "Blutamulett", maxHealth = 12f, damageReduction = .03f }
        };

        public static readonly CardDefinition[] Cards =
        {
            Card("blood_pact", "Blutpakt", "+30 % Schaden", "-20 % maximale Leben", 1.30f, .80f, 1f, 1f, 1f, 1f),
            Card("overcharge", "Überladung", "+18 % Schaden", "+30 % Abklingzeit", 1.18f, 1f, 1f, 1f, 1.30f, 1f),
            Card("glass_cannon", "Glaskanone", "+40 % Schaden", "+25 % erlittener Schaden", 1.40f, 1f, 1f, 1f, 1f, 1.25f),
            Card("swift_step", "Flüchtiger Schritt", "+25 % Bewegung", "-10 % maximale Leben", 1f, .90f, 1.25f, 1f, 1f, 1f),
            Card("iron_heart", "Eisenherz", "+35 % maximale Leben", "-12 % Schaden", .88f, 1.35f, 1f, 1f, 1f, 1f),
            Card("frenzy", "Raserei", "+18 % Angriffstempo", "+10 % erlittener Schaden", 1f, 1f, 1.08f, .82f, 1f, 1.10f),
            Card("ritual_blade", "Ritualklinge", "+20 % Schaden", "-15 % Bewegung", 1.20f, 1f, .85f, 1f, 1f, 1f),
            Card("guardian_oath", "Wächterschwur", "-20 % erlittener Schaden", "-15 % Schaden", .85f, 1f, .92f, 1f, 1f, .80f),
            Card("volatile_core", "Instabiler Kern", "-25 % Fähigkeitsabklingzeit", "-15 % maximale Leben", 1f, .85f, 1f, 1f, .75f, 1f),
            Card("cursed_rebirth", "Verfluchte Wiedergeburt", "+50 % maximale Leben", "+20 % erlittener Schaden", 1f, 1.50f, .9f, 1f, 1f, 1.20f)
        };

        public static RoomDefinition GetRoom(int index)
        {
            if (index < 0 || index >= Rooms.Length) throw new ArgumentOutOfRangeException(nameof(index));
            return Rooms[index];
        }

        private static RoomDefinition Room(int index, string title, RoomKind kind, int difficulty, int obstacles)
        {
            return new RoomDefinition
            {
                index = index,
                title = title,
                kind = kind,
                difficulty = difficulty,
                obstacleCount = obstacles
            };
        }

        private static CardDefinition Card(
            string id,
            string title,
            string benefit,
            string drawback,
            float damage,
            float health,
            float move,
            float attackRate,
            float cooldown,
            float incoming)
        {
            return new CardDefinition
            {
                id = id,
                title = title,
                benefit = benefit,
                drawback = drawback,
                damageMultiplier = damage,
                maxHealthMultiplier = health,
                moveSpeedMultiplier = move,
                attackRateMultiplier = attackRate,
                cooldownMultiplier = cooldown,
                incomingDamageMultiplier = incoming
            };
        }
    }
}
