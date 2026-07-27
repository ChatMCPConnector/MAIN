using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Riftbound
{
    public static class RunPlanner
    {
        public const int RoomCount = 8;

        public static int[] Generate(int seed)
        {
            var rng = new System.Random(seed);
            var combatRooms = new List<int> { 0, 1, 2, 3, 4 };
            Shuffle(combatRooms, rng);

            var treasureFirst = rng.Next(0, 2) == 0;
            return new[]
            {
                combatRooms[0],
                treasureFirst ? 5 : 6,
                combatRooms[1],
                treasureFirst ? 6 : 5,
                combatRooms[2],
                7,
                8,
                9
            };
        }

        public static bool Validate(int[] rooms)
        {
            if (rooms == null || rooms.Length != RoomCount) return false;

            var counts = new Dictionary<RoomKind, int>();
            for (var i = 0; i < rooms.Length; i++)
            {
                if (rooms[i] < 0 || rooms[i] >= GameCatalog.Rooms.Length) return false;
                var kind = GameCatalog.GetRoom(rooms[i]).kind;
                counts[kind] = counts.TryGetValue(kind, out var value) ? value + 1 : 1;
            }

            if (GameCatalog.GetRoom(rooms[0]).kind != RoomKind.Combat) return false;
            if (GameCatalog.GetRoom(rooms[^2]).kind != RoomKind.Elite) return false;
            if (GameCatalog.GetRoom(rooms[^1]).kind != RoomKind.Boss) return false;

            return Count(counts, RoomKind.Combat) == 3
                && Count(counts, RoomKind.Treasure) == 1
                && Count(counts, RoomKind.Merchant) == 1
                && Count(counts, RoomKind.Healing) == 1
                && Count(counts, RoomKind.Elite) == 1
                && Count(counts, RoomKind.Boss) == 1;
        }

        public static PlayerBuild ApplyCard(PlayerBuild build, CardDefinition card)
        {
            build.damage *= card.damageMultiplier;
            build.maxHealth *= card.maxHealthMultiplier;
            build.moveSpeed *= card.moveSpeedMultiplier;
            build.attackRate *= card.attackRateMultiplier;
            build.abilityCooldown *= card.cooldownMultiplier;
            build.incomingDamageMultiplier *= card.incomingDamageMultiplier;
            return build;
        }

        private static int Count(Dictionary<RoomKind, int> counts, RoomKind kind)
        {
            return counts.TryGetValue(kind, out var value) ? value : 0;
        }

        private static void Shuffle<T>(IList<T> values, System.Random rng)
        {
            for (var i = values.Count - 1; i > 0; i--)
            {
                var swap = rng.Next(i + 1);
                (values[i], values[swap]) = (values[swap], values[i]);
            }
        }
    }

    public static class ShopGenerator
    {
        public static ShopOffer[] Generate(int seed, int roomIndex, int count = 3)
        {
            if (count <= 0) return Array.Empty<ShopOffer>();
            count = Math.Min(count, GameCatalog.Weapons.Length + GameCatalog.Armors.Length);

            var rng = new System.Random(unchecked(seed * 397) ^ roomIndex);
            var offers = new ShopOffer[count];
            var used = new HashSet<string>();

            for (var i = 0; i < offers.Length; i++)
            {
                ShopOffer offer;
                do
                {
                    offer = rng.Next(0, 2) == 0
                        ? WeaponOffer(rng.Next(GameCatalog.Weapons.Length))
                        : ArmorOffer(rng.Next(GameCatalog.Armors.Length));
                } while (!used.Add($"{offer.kind}:{offer.catalogIndex}"));

                offers[i] = offer;
            }

            return offers;
        }

        public static ShopOffer[] GenerateTreasure(int seed, int roomIndex)
        {
            var offers = Generate(seed ^ 0x5f3759df, roomIndex, 3);
            foreach (var offer in offers) offer.price = 0;
            return offers;
        }

        private static ShopOffer WeaponOffer(int index)
        {
            var weapon = GameCatalog.Weapons[index];
            return new ShopOffer
            {
                kind = ItemKind.Weapon,
                catalogIndex = index,
                price = Mathf.RoundToInt(18f + weapon.damage * 1.7f + weapon.range * 4f),
                title = weapon.title,
                description = $"Waffe · {weapon.damage:0} Schaden · {weapon.range:0.0} Reichweite"
            };
        }

        private static ShopOffer ArmorOffer(int index)
        {
            var armor = GameCatalog.Armors[index];
            return new ShopOffer
            {
                kind = ItemKind.Armor,
                catalogIndex = index,
                price = Mathf.RoundToInt(20f + armor.maxHealth * 1.6f + armor.damageReduction * 220f),
                title = armor.title,
                description = $"Rüstung · +{armor.maxHealth:0} Leben · {armor.damageReduction * 100f:0}% Schutz"
            };
        }
    }

    [Serializable]
    public sealed class SaveData
    {
        public int version = 2;
        public int bestRoom;
        public int completedRuns;
        public int lastSeed;
        public int lifetimeGold;
    }

    public static class SaveService
    {
        private static string PathName => Path.Combine(Application.persistentDataPath, "riftbound-save.json");
        private static string BackupName => PathName + ".bak";

        public static SaveData Load()
        {
            try
            {
                if (!File.Exists(PathName)) return new SaveData();
                var data = JsonUtility.FromJson<SaveData>(File.ReadAllText(PathName));
                return Upgrade(data);
            }
            catch
            {
                try
                {
                    if (!File.Exists(BackupName)) return new SaveData();
                    return Upgrade(JsonUtility.FromJson<SaveData>(File.ReadAllText(BackupName)));
                }
                catch
                {
                    return new SaveData();
                }
            }
        }

        public static void Save(SaveData data)
        {
            if (data == null) return;

            try
            {
                if (File.Exists(PathName)) File.Copy(PathName, BackupName, true);
                File.WriteAllText(PathName, JsonUtility.ToJson(data, true));
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Save failed: {exception.Message}");
            }
        }

        private static SaveData Upgrade(SaveData data)
        {
            data ??= new SaveData();
            data.version = 2;
            return data;
        }
    }
}
