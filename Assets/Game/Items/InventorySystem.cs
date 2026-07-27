using System;
using System.Collections.Generic;
using UnityEngine;

namespace Riftbound
{
    public enum InventoryAddResult { Added, Filtered, Full }

    public sealed class RunInventory
    {
        private readonly List<ItemInstance> items = new List<ItemInstance>();

        public RunInventory(int capacity = 10)
        {
            Capacity = Mathf.Max(1, capacity);
        }

        public IReadOnlyList<ItemInstance> Items => items;
        public int Capacity { get; }
        public ItemRarity MinimumRarity { get; private set; } = ItemRarity.Common;

        public void Reset()
        {
            items.Clear();
            MinimumRarity = ItemRarity.Common;
        }

        public void Restore(IEnumerable<ItemInstance> restoredItems, ItemRarity minimumRarity)
        {
            items.Clear();
            MinimumRarity = Enum.IsDefined(typeof(ItemRarity), minimumRarity)
                ? minimumRarity
                : ItemRarity.Common;
            if (restoredItems == null) return;
            foreach (var item in restoredItems)
            {
                if (item == null || items.Count >= Capacity) continue;
                if (item.kind == ItemKind.Weapon)
                {
                    if (item.catalogIndex < 0 || item.catalogIndex >= GameCatalog.Weapons.Length) continue;
                }
                else if (item.catalogIndex < 0 || item.catalogIndex >= GameCatalog.Armors.Length)
                {
                    continue;
                }
                if (string.IsNullOrWhiteSpace(item.instanceId)) continue;
                items.Add(item.Clone());
            }
        }

        public void AddStarter(ItemInstance item)
        {
            if (item == null) return;
            item.locked = true;
            items.Add(item.Clone());
        }

        public InventoryAddResult TryAdd(ItemInstance item)
        {
            if (item == null) return InventoryAddResult.Full;
            if (RarityUtility.Rank(item.rarity) < RarityUtility.Rank(MinimumRarity))
                return InventoryAddResult.Filtered;
            if (items.Count >= Capacity)
                return InventoryAddResult.Full;

            items.Add(item.Clone());
            return InventoryAddResult.Added;
        }

        public bool Remove(string instanceId)
        {
            var index = items.FindIndex(item => item.instanceId == instanceId);
            if (index < 0) return false;
            items.RemoveAt(index);
            return true;
        }

        public void CycleFilter()
        {
            MinimumRarity = MinimumRarity switch
            {
                ItemRarity.Common => ItemRarity.Uncommon,
                ItemRarity.Uncommon => ItemRarity.Rare,
                ItemRarity.Rare => ItemRarity.Epic,
                ItemRarity.Epic => ItemRarity.Common,
                _ => ItemRarity.Common
            };
        }
    }

    public static class LootGenerator
    {
        public static ItemInstance CreateStarterWeapon()
        {
            return new ItemInstance
            {
                instanceId = "starter-iron-blade",
                kind = ItemKind.Weapon,
                catalogIndex = 0,
                rarity = ItemRarity.Common,
                powerMultiplier = 1f,
                sellValue = 0,
                salvageValue = 0,
                locked = true
            };
        }

        public static ItemInstance Generate(
            int seed,
            int roomIndex,
            int slot,
            bool treasure,
            ItemKind? forcedKind = null)
        {
            var mixedSeed = unchecked(seed * 486187739 + roomIndex * 16777619 + slot * 31);
            var rng = new System.Random(mixedSeed);
            var kind = forcedKind ?? (rng.Next(0, 2) == 0 ? ItemKind.Weapon : ItemKind.Armor);
            var rarity = RollRarity(rng, roomIndex + (treasure ? 2 : 0));
            var catalogIndex = kind == ItemKind.Weapon
                ? rng.Next(GameCatalog.Weapons.Length)
                : rng.Next(GameCatalog.Armors.Length);

            var power = RarityUtility.PowerMultiplier(rarity);
            var baseValue = CalculateBaseValue(kind, catalogIndex);
            var sellValue = Mathf.Max(1, Mathf.RoundToInt(baseValue * RarityUtility.PriceMultiplier(rarity) * .55f));

            return new ItemInstance
            {
                instanceId = $"{seed:x8}-{roomIndex}-{slot}-{(int)kind}-{catalogIndex}-{(int)rarity}",
                kind = kind,
                catalogIndex = catalogIndex,
                rarity = rarity,
                powerMultiplier = power,
                sellValue = sellValue,
                salvageValue = Mathf.Max(1, 2 + RarityUtility.Rank(rarity) * 3),
                locked = false
            };
        }

        public static ItemRarity RollRarity(System.Random rng, int luck)
        {
            if (rng == null) throw new ArgumentNullException(nameof(rng));

            var cursedChance = Mathf.Clamp(16 + luck * 4, 16, 64);
            if (rng.Next(1000) < cursedChance)
                return ItemRarity.Cursed;

            var roll = rng.Next(1000);
            if (roll < 12 + luck * 3) return ItemRarity.Legendary;
            if (roll < 58 + luck * 7) return ItemRarity.Epic;
            if (roll < 210 + luck * 12) return ItemRarity.Rare;
            if (roll < 540 + luck * 16) return ItemRarity.Uncommon;
            return ItemRarity.Common;
        }

        private static int CalculateBaseValue(ItemKind kind, int catalogIndex)
        {
            if (kind == ItemKind.Weapon)
            {
                var weapon = GameCatalog.Weapons[catalogIndex];
                return Mathf.RoundToInt(18f + weapon.damage * 1.8f + weapon.range * 5f);
            }

            var armor = GameCatalog.Armors[catalogIndex];
            return Mathf.RoundToInt(20f + armor.maxHealth * 1.8f + armor.damageReduction * 260f);
        }
    }

    public static class ShopGenerator
    {
        public static ShopOffer[] Generate(int seed, int roomIndex, int count = 3)
        {
            if (count <= 0) return Array.Empty<ShopOffer>();
            count = Mathf.Min(count, GameCatalog.Weapons.Length + GameCatalog.Armors.Length);

            var offers = new ShopOffer[count];
            var used = new HashSet<string>();
            var slot = 0;

            for (var i = 0; i < count; i++)
            {
                ItemInstance item;
                do
                {
                    item = LootGenerator.Generate(seed ^ 0x2c9277b5, roomIndex + 1, slot++, false);
                } while (!used.Add($"{item.kind}:{item.catalogIndex}"));

                offers[i] = CreateOffer(item, false);
            }

            return offers;
        }

        public static ShopOffer[] GenerateTreasure(int seed, int roomIndex)
        {
            var offers = new ShopOffer[3];
            var used = new HashSet<string>();
            var slot = 0;

            for (var i = 0; i < offers.Length; i++)
            {
                ItemInstance item;
                do
                {
                    item = LootGenerator.Generate(seed ^ 0x5f3759df, roomIndex, slot++, true);
                } while (!used.Add($"{item.kind}:{item.catalogIndex}"));

                offers[i] = CreateOffer(item, true);
            }

            return offers;
        }

        private static ShopOffer CreateOffer(ItemInstance item, bool free)
        {
            var title = ItemText.Title(item);
            return new ShopOffer
            {
                item = item,
                price = free ? 0 : Mathf.Max(1, Mathf.RoundToInt(item.sellValue * 1.65f)),
                title = title,
                description = ItemText.Description(item)
            };
        }
    }

    public static class ItemText
    {
        public static string Title(ItemInstance item)
        {
            if (item == null) return "Unbekannter Gegenstand";
            return $"<color={RarityUtility.Hex(item.rarity)}>{GameCatalog.GetItemTitle(item)}</color>";
        }

        public static string PlainTitle(ItemInstance item)
        {
            if (item == null) return "Unbekannt";
            return $"{GameCatalog.GetItemTitle(item)} [{RarityUtility.DisplayName(item.rarity)}]";
        }

        public static string Description(ItemInstance item)
        {
            if (item == null) return "";
            var rarity = RarityUtility.DisplayName(item.rarity);
            var drawback = item.rarity == ItemRarity.Cursed
                ? "\n<color=#FF718C>Fluch: +12 % erlittener Schaden beim Ausrüsten</color>"
                : "";

            if (item.kind == ItemKind.Weapon)
            {
                var weapon = GameCatalog.Weapons[item.catalogIndex];
                return $"{rarity} · Waffe\n" +
                       $"{weapon.damage * item.powerMultiplier:0} Schaden · " +
                       $"{weapon.range * (1f + (item.powerMultiplier - 1f) * .15f):0.0} Reichweite" +
                       drawback;
            }

            var armor = GameCatalog.Armors[item.catalogIndex];
            return $"{rarity} · Rüstung\n" +
                   $"+{armor.maxHealth * item.powerMultiplier:0} Leben · " +
                   $"{armor.damageReduction * item.powerMultiplier * 100f:0}% Schutz" +
                   drawback;
        }
    }
}
