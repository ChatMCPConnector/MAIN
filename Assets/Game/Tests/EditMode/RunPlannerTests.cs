using System.Linq;
using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class RunPlannerTests
    {
        [Test]
        public void SameSeedProducesSameRun()
        {
            CollectionAssert.AreEqual(
                RunPlanner.Generate(123456),
                RunPlanner.Generate(123456));
        }

        [Test]
        public void GeneratedRunsAreAlwaysValid()
        {
            for (var seed = 0; seed < 10000; seed++)
                Assert.That(
                    RunPlanner.Validate(RunPlanner.Generate(seed)),
                    Is.True,
                    $"Invalid seed {seed}");
        }

        [Test]
        public void RunContainsRequiredSpecialRooms()
        {
            var rooms = RunPlanner.Generate(42)
                .Select(GameCatalog.GetRoom)
                .ToArray();

            Assert.That(rooms.Count(room => room.kind == RoomKind.Treasure), Is.EqualTo(1));
            Assert.That(rooms.Count(room => room.kind == RoomKind.Merchant), Is.EqualTo(1));
            Assert.That(rooms.Count(room => room.kind == RoomKind.Healing), Is.EqualTo(1));
            Assert.That(rooms[^2].kind, Is.EqualTo(RoomKind.Elite));
            Assert.That(rooms[^1].kind, Is.EqualTo(RoomKind.Boss));
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
