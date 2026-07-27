using System;
using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class InventoryTests
    {
        [Test]
        public void StarterItemIsLockedAndStored()
        {
            var inventory = new RunInventory(3);
            inventory.AddStarter(LootGenerator.CreateStarterWeapon());

            Assert.That(inventory.Items, Has.Count.EqualTo(1));
            Assert.That(inventory.Items[0].locked, Is.True);
        }

        [Test]
        public void CapacityPreventsAdditionalLoot()
        {
            var inventory = new RunInventory(1);
            var first = LootGenerator.Generate(10, 1, 0, false);
            var second = LootGenerator.Generate(10, 1, 1, false);

            Assert.That(inventory.TryAdd(first), Is.EqualTo(InventoryAddResult.Added));
            Assert.That(inventory.TryAdd(second), Is.EqualTo(InventoryAddResult.Full));
        }

        [Test]
        public void LootFilterRejectsLowerRarity()
        {
            var inventory = new RunInventory(3);
            inventory.CycleFilter();

            var common = new ItemInstance
            {
                instanceId = "common",
                kind = ItemKind.Weapon,
                catalogIndex = 0,
                rarity = ItemRarity.Common,
                powerMultiplier = 1f
            };

            Assert.That(inventory.MinimumRarity, Is.EqualTo(ItemRarity.Uncommon));
            Assert.That(inventory.TryAdd(common), Is.EqualTo(InventoryAddResult.Filtered));
        }

        [Test]
        public void GeneratedLootIsDeterministic()
        {
            var first = LootGenerator.Generate(1234, 4, 2, true);
            var second = LootGenerator.Generate(1234, 4, 2, true);

            Assert.That(first.instanceId, Is.EqualTo(second.instanceId));
            Assert.That(first.rarity, Is.EqualTo(second.rarity));
            Assert.That(first.powerMultiplier, Is.EqualTo(second.powerMultiplier));
        }

        [Test]
        public void RarityPowerNeverDecreases()
        {
            var values = new[]
            {
                ItemRarity.Common,
                ItemRarity.Uncommon,
                ItemRarity.Rare,
                ItemRarity.Epic,
                ItemRarity.Legendary,
                ItemRarity.Cursed
            };

            for (var i = 1; i < values.Length; i++)
                Assert.That(
                    RarityUtility.PowerMultiplier(values[i]),
                    Is.GreaterThan(RarityUtility.PowerMultiplier(values[i - 1])));
        }

        [Test]
        public void RarityRollProducesMultipleTiers()
        {
            var seen = new bool[Enum.GetValues(typeof(ItemRarity)).Length];
            for (var seed = 0; seed < 5000; seed++)
            {
                var rarity = LootGenerator.RollRarity(new Random(seed), 4);
                seen[(int)rarity] = true;
            }

            Assert.That(seen[(int)ItemRarity.Common], Is.True);
            Assert.That(seen[(int)ItemRarity.Uncommon], Is.True);
            Assert.That(seen[(int)ItemRarity.Rare], Is.True);
            Assert.That(seen[(int)ItemRarity.Epic], Is.True);
            Assert.That(seen[(int)ItemRarity.Cursed], Is.True);
        }

        [Test]
        public void MetaProgressionRecordsDiscoveriesWithoutDuplicates()
        {
            var data = new SaveData();
            var item = LootGenerator.Generate(42, 5, 0, true, ItemKind.Weapon);

            MetaProgression.RecordDiscovery(data, item);
            MetaProgression.RecordDiscovery(data, item);

            Assert.That(data.discoveredWeapons, Has.Count.EqualTo(1));
            Assert.That(data.highestRaritySeen, Is.EqualTo(RarityUtility.Rank(item.rarity)));
        }
    }
}
