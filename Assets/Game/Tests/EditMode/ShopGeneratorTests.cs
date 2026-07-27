using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class ShopGeneratorTests
    {
        [Test]
        public void SameSeedProducesSameOffers()
        {
            var first = ShopGenerator.Generate(123, 3);
            var second = ShopGenerator.Generate(123, 3);

            Assert.That(first.Length, Is.EqualTo(second.Length));
            for (var i = 0; i < first.Length; i++)
            {
                Assert.That(first[i].item.instanceId, Is.EqualTo(second[i].item.instanceId));
                Assert.That(first[i].item.rarity, Is.EqualTo(second[i].item.rarity));
                Assert.That(first[i].price, Is.EqualTo(second[i].price));
            }
        }

        [Test]
        public void MerchantOffersAreUniqueAndPriced()
        {
            var offers = ShopGenerator.Generate(99, 2);
            Assert.That(offers, Has.Length.EqualTo(3));

            for (var i = 0; i < offers.Length; i++)
            {
                Assert.That(offers[i].item, Is.Not.Null);
                Assert.That(offers[i].price, Is.GreaterThan(0));
                Assert.That(offers[i].item.powerMultiplier, Is.GreaterThanOrEqualTo(1f));

                for (var j = i + 1; j < offers.Length; j++)
                    Assert.That(
                        $"{offers[i].item.kind}:{offers[i].item.catalogIndex}",
                        Is.Not.EqualTo($"{offers[j].item.kind}:{offers[j].item.catalogIndex}"));
            }
        }

        [Test]
        public void TreasureOffersAreFreeAndSlightlyLuckier()
        {
            var offers = ShopGenerator.GenerateTreasure(99, 2);
            Assert.That(offers, Has.Length.EqualTo(3));

            foreach (var offer in offers)
            {
                Assert.That(offer.price, Is.Zero);
                Assert.That(offer.item.sellValue, Is.GreaterThan(0));
            }
        }
    }
}
