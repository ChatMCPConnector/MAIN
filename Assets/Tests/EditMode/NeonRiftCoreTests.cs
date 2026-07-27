using System;
using System.Linq;
using NUnit.Framework;

namespace NeonRift.Tests
{
    public sealed class NeonRiftCoreTests
    {
        [Test]
        public void CatalogContainsAllRequiredContent()
        {
            Assert.That(NeonRiftCatalog.Fighters.Count, Is.EqualTo(4));
            Assert.That(NeonRiftCatalog.Arenas.Count, Is.EqualTo(3));
            Assert.That(NeonRiftCatalog.Modes.Count, Is.EqualTo(5));
            Assert.That(NeonRiftCatalog.Modes.Count, Is.EqualTo(Enum.GetValues(typeof(GameMode)).Length));
        }

        [Test]
        public void FighterCatalogHasUniqueUsableEntries()
        {
            Assert.That(NeonRiftCatalog.Fighters.Select(fighter => fighter.Name).Distinct().Count(),
                Is.EqualTo(NeonRiftCatalog.Fighters.Count));

            foreach (FighterSpec fighter in NeonRiftCatalog.Fighters)
            {
                Assert.Multiple(() =>
                {
                    Assert.That(fighter.Name, Is.Not.Empty);
                    Assert.That(fighter.ModelFile, Is.Not.Empty);
                    Assert.That(fighter.MaxHealth, Is.GreaterThan(0f));
                    Assert.That(fighter.Speed, Is.GreaterThan(0f));
                    Assert.That(fighter.Power, Is.GreaterThan(0f));
                });
            }
        }

        [Test]
        public void ArenaCatalogHasUniqueUsableEntries()
        {
            Assert.That(NeonRiftCatalog.Arenas.Select(arena => arena.Name).Distinct().Count(),
                Is.EqualTo(NeonRiftCatalog.Arenas.Count));

            foreach (ArenaSpec arena in NeonRiftCatalog.Arenas)
            {
                Assert.Multiple(() =>
                {
                    Assert.That(arena.Name, Is.Not.Empty);
                    Assert.That(arena.Subtitle, Is.Not.Empty);
                    Assert.That(arena.PropKeywords, Is.Not.Null.And.Not.Empty);
                });
            }
        }

        [Test]
        public void HeavySpecialDamageScalesAboveLightDamage()
        {
            float light = GameBalance.CalculateDamage(9f, 1f, false, false);
            float heavy = GameBalance.CalculateDamage(9f, 1f, true, false);
            float special = GameBalance.CalculateDamage(9f, 1f, false, true);
            Assert.That(heavy, Is.GreaterThan(light));
            Assert.That(special, Is.GreaterThan(heavy));
        }

        [Test]
        public void DamageScalesMonotonicallyWithPower()
        {
            float weak = GameBalance.CalculateDamage(5f, 0.8f, false, false);
            float normal = GameBalance.CalculateDamage(5f, 1f, false, false);
            float strong = GameBalance.CalculateDamage(5f, 1.4f, false, false);
            Assert.That(normal, Is.GreaterThan(weak));
            Assert.That(strong, Is.GreaterThan(normal));
        }

        [Test]
        public void DamageAndKnockbackNeverBecomeNegative()
        {
            Assert.That(GameBalance.CalculateDamage(-10f, -2f, false, false), Is.GreaterThanOrEqualTo(1f));
            Assert.That(GameBalance.KnockbackFor(0f, false, false), Is.GreaterThan(0f));
        }
    }
}
