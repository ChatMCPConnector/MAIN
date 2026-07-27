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

    [Serializable]
    public sealed class SaveData
    {
        public int version = 3;
        public int bestRoom;
        public int completedRuns;
        public int lastSeed;
        public int lifetimeGold;
        public int metaShards;
        public int highestRaritySeen;
        public List<string> discoveredWeapons = new List<string>();
        public List<string> discoveredArmors = new List<string>();
    }

    public static class MetaProgression
    {
        public static void RecordDiscovery(SaveData data, ItemInstance item)
        {
            if (data == null || item == null) return;

            var definitionId = item.kind == ItemKind.Weapon
                ? GameCatalog.Weapons[item.catalogIndex].id
                : GameCatalog.Armors[item.catalogIndex].id;
            var discoveries = item.kind == ItemKind.Weapon
                ? data.discoveredWeapons
                : data.discoveredArmors;

            if (!discoveries.Contains(definitionId))
                discoveries.Add(definitionId);

            data.highestRaritySeen = Mathf.Max(
                data.highestRaritySeen,
                RarityUtility.Rank(item.rarity));
        }

        public static int CompleteRun(SaveData data, int runGold)
        {
            if (data == null) return 0;
            var earned = 3 + Mathf.Clamp(runGold / 75, 0, 5);
            data.metaShards += earned;
            return earned;
        }

        public static int RecordDefeat(SaveData data, int reachedRoom)
        {
            if (data == null || reachedRoom < 5) return 0;
            data.metaShards += 1;
            return 1;
        }

        public static ItemRarity HighestSeen(SaveData data)
        {
            if (data == null) return ItemRarity.Common;
            var rank = Mathf.Clamp(
                data.highestRaritySeen,
                0,
                RarityUtility.Rank(ItemRarity.Cursed));
            return (ItemRarity)rank;
        }
    }

    public static class SaveService
    {
        private static string PathName => Path.Combine(Application.persistentDataPath, "riftbound-save.json");
        private static string BackupName => PathName + ".bak";

        public static SaveData Load()
        {
            try
            {
                if (!File.Exists(PathName)) return Upgrade(new SaveData());
                var data = JsonUtility.FromJson<SaveData>(File.ReadAllText(PathName));
                return Upgrade(data);
            }
            catch
            {
                try
                {
                    if (!File.Exists(BackupName)) return Upgrade(new SaveData());
                    return Upgrade(JsonUtility.FromJson<SaveData>(File.ReadAllText(BackupName)));
                }
                catch
                {
                    return Upgrade(new SaveData());
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
            data.version = 3;
            data.discoveredWeapons ??= new List<string>();
            data.discoveredArmors ??= new List<string>();

            if (!data.discoveredWeapons.Contains(GameCatalog.Weapons[0].id))
                data.discoveredWeapons.Add(GameCatalog.Weapons[0].id);

            return data;
        }
    }
}
