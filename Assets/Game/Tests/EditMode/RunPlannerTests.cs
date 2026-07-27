using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class RunPlannerTests
    {
        [Test]
        public void SameSeedProducesSameRun()
        {
            CollectionAssert.AreEqual(RunPlanner.Generate(123456), RunPlanner.Generate(123456));
        }

        [Test]
        public void GeneratedRunIsAlwaysValid()
        {
            for (var seed = 0; seed < 5000; seed++)
                Assert.That(RunPlanner.Validate(RunPlanner.Generate(seed)), Is.True, $"Invalid seed {seed}");
        }

        [Test]
        public void BossAndEliteAreAtTheEnd()
        {
            var rooms = RunPlanner.Generate(42);
            Assert.That(rooms[^2], Is.EqualTo(8));
            Assert.That(rooms[^1], Is.EqualTo(9));
        }

        [Test]
        public void CardAppliesBenefitAndDrawback()
        {
            var initial = PlayerBuild.Default;
            var updated = RunPlanner.ApplyCard(initial, GameCatalog.Cards[0]);
            Assert.That(updated.damage, Is.GreaterThan(initial.damage));
            Assert.That(updated.maxHealth, Is.LessThan(initial.maxHealth));
        }
    }
}
