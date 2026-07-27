using System;
using System.Collections.Generic;
using System.Linq;
using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class BiomeSystemTests
    {
        [Test]
        public void SameSeedProducesSameBiomePlan()
        {
            CollectionAssert.AreEqual(
                BiomePlanner.Generate(81422),
                BiomePlanner.Generate(81422));
        }

        [Test]
        public void EveryRunVisitsAllThreeBiomes()
        {
            for (var seed = 0; seed < 2000; seed++)
            {
                var plan = BiomePlanner.Generate(seed);
                Assert.That(plan, Has.Length.EqualTo(RunPlanner.RoomCount));
                Assert.That(plan.Distinct().Count(), Is.EqualTo(3));

                var counts = plan
                    .GroupBy(value => value)
                    .Select(group => group.Count())
                    .OrderBy(value => value)
                    .ToArray();
                CollectionAssert.AreEqual(new[] { 2, 3, 3 }, counts);
            }
        }

        [Test]
        public void BossAlwaysUsesRiftstorm()
        {
            for (var seed = 0; seed < 1000; seed++)
                Assert.That(
                    ModifierPlanner.ForRoom(seed, RunPlanner.RoomCount - 1),
                    Is.EqualTo(RoomModifierKind.Riftstorm));
        }

        [Test]
        public void NonCombatRoomsHaveNoCombatModifier()
        {
            for (var seed = 0; seed < 1000; seed++)
            {
                var rooms = RunPlanner.Generate(seed);
                for (var roomIndex = 0; roomIndex < rooms.Length; roomIndex++)
                {
                    var kind = GameCatalog.GetRoom(rooms[roomIndex]).kind;
                    if (kind != RoomKind.Treasure &&
                        kind != RoomKind.Merchant &&
                        kind != RoomKind.Healing)
                        continue;

                    Assert.That(
                        ModifierPlanner.ForRoom(seed, roomIndex),
                        Is.EqualTo(RoomModifierKind.None));
                }
            }
        }

        [Test]
        public void CombatModifiersHaveVariety()
        {
            var seen = new HashSet<RoomModifierKind>();
            for (var seed = 0; seed < 2000; seed++)
            {
                var rooms = RunPlanner.Generate(seed);
                for (var roomIndex = 0; roomIndex < rooms.Length; roomIndex++)
                {
                    if (GameCatalog.GetRoom(rooms[roomIndex]).kind == RoomKind.Combat)
                        seen.Add(ModifierPlanner.ForRoom(seed, roomIndex));
                }
            }

            Assert.That(seen.Contains(RoomModifierKind.None), Is.True);
            Assert.That(seen.Contains(RoomModifierKind.Frenzy), Is.True);
            Assert.That(seen.Contains(RoomModifierKind.Fortified), Is.True);
            Assert.That(seen.Contains(RoomModifierKind.Volatile), Is.True);
            Assert.That(seen.Contains(RoomModifierKind.BloodMoon), Is.True);
        }

        [Test]
        public void EncounterTuningAlwaysProducesSafePositiveValues()
        {
            for (var seed = 0; seed < 1000; seed++)
            {
                for (var roomIndex = 0; roomIndex < RunPlanner.RoomCount; roomIndex++)
                {
                    var tuning = EncounterDirector.Create(seed, roomIndex);
                    Assert.That(tuning.Biome, Is.Not.Null);
                    Assert.That(tuning.Modifier, Is.Not.Null);
                    Assert.That(tuning.EnemyHealthMultiplier, Is.GreaterThan(0f));
                    Assert.That(tuning.EnemyDamageMultiplier, Is.GreaterThan(0f));
                    Assert.That(tuning.EnemySpeedMultiplier, Is.GreaterThan(0f));
                    Assert.That(tuning.ProjectileSpeedMultiplier, Is.GreaterThan(0f));
                    Assert.That(tuning.SpecialCooldownMultiplier, Is.GreaterThan(0f));
                }
            }
        }

        [Test]
        public void LateRunEncounterIsStrongerThanOpeningRoomWithoutModifiers()
        {
            var opening = EncounterDirector.Create(123, 0);
            var boss = EncounterDirector.Create(123, RunPlanner.RoomCount - 1);

            Assert.That(boss.EnemyHealthMultiplier, Is.GreaterThan(opening.EnemyHealthMultiplier));
            Assert.That(boss.EnemyDamageMultiplier, Is.GreaterThan(opening.EnemyDamageMultiplier));
        }
    }
}
