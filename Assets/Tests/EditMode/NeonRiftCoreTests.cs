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
        public void DamageAndKnockbackNeverBecomeNegative()
        {
            Assert.That(GameBalance.CalculateDamage(-10f, -2f, false, false), Is.GreaterThanOrEqualTo(1f));
            Assert.That(GameBalance.KnockbackFor(0f, false, false), Is.GreaterThan(0f));
        }
    }
}
