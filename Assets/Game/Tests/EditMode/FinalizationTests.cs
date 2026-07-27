using System;
using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using UnityEngine;

namespace Riftbound.Tests
{
    public sealed class FinalizationTests
    {
        [Test]
        public void ReliableProtocolRoundTripsUnicodePayloadUnderGermanCulture()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
                var envelope = new CoopCriticalEnvelope
                {
                    id = 42,
                    kind = CoopCriticalKind.Decision,
                    payload = "Händler, Auswahl | bestätigt ✓"
                };
                var encoded = CoopReliableProtocol.EncodeMessage("1234", "client-token", envelope);
                Assert.That(
                    CoopReliableProtocol.TryDecodeMessage(
                        encoded,
                        out var code,
                        out var token,
                        out var decoded),
                    Is.True);
                Assert.That(code, Is.EqualTo("1234"));
                Assert.That(token, Is.EqualTo("client-token"));
                Assert.That(decoded.id, Is.EqualTo(42));
                Assert.That(decoded.kind, Is.EqualTo(CoopCriticalKind.Decision));
                Assert.That(decoded.payload, Is.EqualTo(envelope.payload));
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }

        [Test]
        public void ReliableLedgerRetriesAcknowledgesAndDeduplicates()
        {
            var ledger = new CoopReliableLedger();
            var message = ledger.Create(CoopCriticalKind.Damage, "12.5,1");
            Assert.That(ledger.PendingCount, Is.EqualTo(1));
            Assert.That(ledger.CollectDue(0d, .2d, 5), Has.Count.EqualTo(1));
            Assert.That(ledger.CollectDue(.1d, .2d, 5), Is.Empty);
            Assert.That(ledger.CollectDue(.21d, .2d, 5), Has.Count.EqualTo(1));
            Assert.That(ledger.AcceptIncoming(message.id), Is.True);
            Assert.That(ledger.AcceptIncoming(message.id), Is.False);
            Assert.That(ledger.Acknowledge(message.id), Is.True);
            Assert.That(ledger.PendingCount, Is.Zero);
        }

        [Test]
        public void DecisionCodecAndLedgerPreventDuplicateApplication()
        {
            var original = new CoopDecision(991, 3, CoopDecisionType.MerchantBuy, 2, 47);
            Assert.That(CoopDecisionCodec.TryDecode(CoopDecisionCodec.Encode(original), out var decoded), Is.True);
            Assert.That(decoded.seed, Is.EqualTo(991));
            Assert.That(decoded.roomIndex, Is.EqualTo(3));
            Assert.That(decoded.type, Is.EqualTo(CoopDecisionType.MerchantBuy));
            Assert.That(decoded.optionIndex, Is.EqualTo(2));
            Assert.That(decoded.hostGold, Is.EqualTo(47));

            var ledger = new CoopTransactionLedger();
            Assert.That(ledger.TryApply(decoded.Key), Is.True);
            Assert.That(ledger.TryApply(decoded.Key), Is.False);
        }

        [Test]
        public void EconomyCodecRequiresPositiveRevision()
        {
            var payload = CoopDecisionCodec.EncodeEconomy(5, 2, 83, 7);
            Assert.That(
                CoopDecisionCodec.TryDecodeEconomy(
                    payload,
                    out var seed,
                    out var room,
                    out var gold,
                    out var revision),
                Is.True);
            Assert.That(seed, Is.EqualTo(5));
            Assert.That(room, Is.EqualTo(2));
            Assert.That(gold, Is.EqualTo(83));
            Assert.That(revision, Is.EqualTo(7));
            Assert.That(
                CoopDecisionCodec.TryDecodeEconomy("5,2,83,0", out _, out _, out _, out _),
                Is.False);
        }

        [Test]
        public void CheckpointValidityRejectsStaleOrBrokenRuns()
        {
            var now = new DateTime(2026, 7, 27, 12, 0, 0, DateTimeKind.Utc);
            var valid = new RunCheckpointData
            {
                seed = 12,
                roomIndex = 4,
                runGold = 50,
                health = 70f,
                savedUtcTicks = now.AddHours(-2).Ticks,
                items = new List<ItemInstance> { LootGenerator.CreateStarterWeapon() },
                cardIndexes = new List<int> { 1 }
            };
            Assert.That(RunCheckpointService.IsUsable(valid, now), Is.True);
            valid.savedUtcTicks = now.AddHours(-25).Ticks;
            Assert.That(RunCheckpointService.IsUsable(valid, now), Is.False);
            valid.savedUtcTicks = now.AddHours(-1).Ticks;
            valid.health = 0f;
            Assert.That(RunCheckpointService.IsUsable(valid, now), Is.False);
        }

        [Test]
        public void InventoryRestoreClonesValidItemsAndHonorsCapacity()
        {
            var inventory = new RunInventory(2);
            var starter = LootGenerator.CreateStarterWeapon();
            var armor = LootGenerator.Generate(123, 2, 0, true, ItemKind.Armor);
            var third = LootGenerator.Generate(123, 2, 1, true, ItemKind.Weapon);
            inventory.Restore(new[] { starter, armor, third }, ItemRarity.Rare);
            Assert.That(inventory.Items, Has.Count.EqualTo(2));
            Assert.That(inventory.MinimumRarity, Is.EqualTo(ItemRarity.Rare));
            Assert.That(inventory.Items[0], Is.Not.SameAs(starter));
        }

        [Test]
        public void HazardPlanIsDeterministicAndLateRoomsContainTwoHazards()
        {
            var first = CoopHazardPlanner.Create(8080, 7);
            var repeat = CoopHazardPlanner.Create(8080, 7);
            Assert.That(first, Has.Length.EqualTo(2));
            Assert.That(repeat, Has.Length.EqualTo(first.Length));
            Assert.That(repeat[0].hazardId, Is.EqualTo(first[0].hazardId));
            Assert.That(repeat[0].position.x, Is.EqualTo(first[0].position.x).Within(.0001f));
            Assert.That(repeat[0].kind, Is.EqualTo(first[0].kind));
        }

        [Test]
        public void PulseAndLaserHitMathUsesFlatArenaDistance()
        {
            Assert.That(
                CoopHazardMath.Hits(
                    CoopHazardKind.Pulse,
                    Vector3.zero,
                    0f,
                    2f,
                    new Vector3(1f, 10f, 1f)),
                Is.True);
            Assert.That(
                CoopHazardMath.Hits(
                    CoopHazardKind.Pulse,
                    Vector3.zero,
                    0f,
                    1f,
                    new Vector3(2f, 0f, 0f)),
                Is.False);
            Assert.That(
                CoopHazardMath.Hits(
                    CoopHazardKind.Laser,
                    Vector3.zero,
                    0f,
                    4f,
                    new Vector3(.2f, 4f, 2f)),
                Is.True);
            Assert.That(
                CoopHazardMath.Hits(
                    CoopHazardKind.Laser,
                    Vector3.zero,
                    0f,
                    4f,
                    new Vector3(1.2f, 0f, 2f)),
                Is.False);
        }

        [Test]
        public void HazardCodecRejectsInvalidRadiusAndRoundTrips()
        {
            var value = new CoopHazardEvent(
                99,
                3,
                31,
                CoopHazardKind.Laser,
                CoopHazardPhase.Warning,
                new Vector3(1.25f, .1f, -2f),
                45f,
                4.5f,
                15f);
            Assert.That(CoopHazardCodec.TryDecode(CoopHazardCodec.Encode(value), out var decoded), Is.True);
            Assert.That(decoded.hazardId, Is.EqualTo(31));
            Assert.That(decoded.radius, Is.EqualTo(4.5f).Within(.001f));
            Assert.That(
                CoopHazardCodec.TryDecode("HZ,99,3,31,0,1,0,0,0,0,99,15", out _),
                Is.False);
        }
    }
}
