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
                Assert.That(first[i].kind, Is.EqualTo(second[i].kind));
                Assert.That(first[i].catalogIndex, Is.EqualTo(second[i].catalogIndex));
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
                Assert.That(offers[i].price, Is.GreaterThan(0));
                for (var j = i + 1; j < offers.Length; j++)
                    Assert.That(
                        $"{offers[i].kind}:{offers[i].catalogIndex}",
                        Is.Not.EqualTo($"{offers[j].kind}:{offers[j].catalogIndex}"));
            }
        }

        [Test]
        public void TreasureOffersAreFree()
        {
            var offers = ShopGenerator.GenerateTreasure(99, 2);
            Assert.That(offers, Has.Length.EqualTo(3));
            foreach (var offer in offers)
                Assert.That(offer.price, Is.Zero);
        }
    }
}
