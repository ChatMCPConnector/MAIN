using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using UnityEngine;

namespace Riftbound.Tests
{
    public sealed class CoopCombatTests
    {
        [Test]
        public void EnemySnapshotPacketRoundTripsUnderGermanCulture()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
                var snapshots = new List<CoopEnemySnapshot>
                {
                    new CoopEnemySnapshot
                    {
                        networkId = 1201,
                        kind = EnemyKind.Ranged,
                        x = 1.25f,
                        y = 1f,
                        z = -2.75f,
                        yaw = 92.5f,
                        health = 31.5f,
                        maxHealth = 48.75f,
                        bossPhase = 1
                    },
                    new CoopEnemySnapshot
                    {
                        networkId = 1202,
                        kind = EnemyKind.Boss,
                        x = 0f,
                        y = 1.35f,
                        z = 2.5f,
                        yaw = 180f,
                        health = 180f,
                        maxHealth = 420f,
                        bossPhase = 2
                    }
                };

                var payload = CoopCombatProtocol.EncodeEnemies("0427", "host-token", 8, 6, snapshots);
                StringAssert.Contains("1.25", payload);
                Assert.That(
                    CoopCombatProtocol.TryDecodeEnemies(
                        payload,
                        out var code,
                        out var token,
                        out var sequence,
                        out var room,
                        out var decoded),
                    Is.True);
                Assert.That(code, Is.EqualTo("0427"));
                Assert.That(token, Is.EqualTo("host-token"));
                Assert.That(sequence, Is.EqualTo(8));
                Assert.That(room, Is.EqualTo(6));
                Assert.That(decoded, Has.Count.EqualTo(2));
                Assert.That(decoded[0].x, Is.EqualTo(1.25f).Within(.001f));
                Assert.That(decoded[1].bossPhase, Is.EqualTo(2));
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }

        [Test]
        public void EmptyEnemySnapshotMarksClearedRoom()
        {
            var payload = CoopCombatProtocol.EncodeEnemies(
                "9999",
                "host",
                11,
                4,
                new List<CoopEnemySnapshot>());
            Assert.That(
                CoopCombatProtocol.TryDecodeEnemies(
                    payload,
                    out _,
                    out _,
                    out _,
                    out var room,
                    out var decoded),
                Is.True);
            Assert.That(room, Is.EqualTo(4));
            Assert.That(decoded, Is.Empty);
        }

        [Test]
        public void AttackPacketRoundTripsAndSanitizesToken()
        {
            var intent = new CoopAttackIntent
            {
                sequence = 17,
                kind = CoopAttackKind.Ability,
                origin = new Vector3(1f, 1f, -2f),
                direction = new Vector3(.25f, 0f, 1f),
                damage = 42.5f,
                range = 1f
            };
            var payload = CoopCombatProtocol.EncodeAttack("1234", "bad|token,field", intent);
            Assert.That(payload, Does.Not.Contain("bad|token"));
            Assert.That(
                CoopCombatProtocol.TryDecodeAttack(
                    payload,
                    out var code,
                    out var token,
                    out var decoded),
                Is.True);
            Assert.That(code, Is.EqualTo("1234"));
            Assert.That(token, Is.EqualTo("badtokenfield"));
            Assert.That(decoded.sequence, Is.EqualTo(17));
            Assert.That(decoded.damage, Is.EqualTo(42.5f).Within(.001f));
        }

        [Test]
        public void SequenceValidationRejectsDuplicatesAndOlderPackets()
        {
            long last = 0;
            Assert.That(CoopCombatValidation.IsFresh(2, ref last), Is.True);
            Assert.That(last, Is.EqualTo(2));
            Assert.That(CoopCombatValidation.IsFresh(2, ref last), Is.False);
            Assert.That(CoopCombatValidation.IsFresh(1, ref last), Is.False);
            Assert.That(CoopCombatValidation.IsFresh(3, ref last), Is.True);
        }

        [Test]
        public void AttackValidationPinsOriginAndEnforcesCooldowns()
        {
            var nextMelee = 0f;
            var nextAbility = 0f;
            var intent = new CoopAttackIntent
            {
                sequence = 1,
                kind = CoopAttackKind.Melee,
                origin = Vector3.zero,
                direction = Vector3.forward,
                damage = 25f,
                range = 1.8f
            };

            Assert.That(
                CoopCombatValidation.IsValidAttack(
                    intent,
                    new Vector3(.1f, 0f, .1f),
                    10f,
                    ref nextMelee,
                    ref nextAbility),
                Is.True);
            Assert.That(
                CoopCombatValidation.IsValidAttack(
                    intent,
                    Vector3.zero,
                    10.05f,
                    ref nextMelee,
                    ref nextAbility),
                Is.False);

            intent.origin = new Vector3(20f, 0f, 20f);
            Assert.That(
                CoopCombatValidation.IsValidAttack(
                    intent,
                    Vector3.zero,
                    11f,
                    ref nextMelee,
                    ref nextAbility),
                Is.False);
        }

        [Test]
        public void NetworkIdsAreStableAndSeparateSpawnPositions()
        {
            var first = CoopCombatWorld.CreateNetworkId(
                3,
                EnemyKind.Grunt,
                new Vector3(-2.25f, 1f, 1.75f));
            var repeat = CoopCombatWorld.CreateNetworkId(
                3,
                EnemyKind.Grunt,
                new Vector3(-2.25f, 1f, 1.75f));
            var second = CoopCombatWorld.CreateNetworkId(
                3,
                EnemyKind.Grunt,
                new Vector3(2.25f, 1f, 1.75f));

            Assert.That(first, Is.EqualTo(repeat));
            Assert.That(first, Is.GreaterThan(0));
            Assert.That(second, Is.Not.EqualTo(first));
        }

        [Test]
        public void MalformedSnapshotsAreRejected()
        {
            Assert.That(
                CoopCombatProtocol.TryDecodeEnemies(
                    "RB5C|ENEMIES|1|1234|host|1|2|1|bad-entry",
                    out _,
                    out _,
                    out _,
                    out _,
                    out _),
                Is.False);
            Assert.That(
                CoopCombatProtocol.TryDecodeAttack(
                    "RB5C|ATTACK|99|1234|client|1|0|0|0|0|0|0|1|20|1",
                    out _,
                    out _,
                    out _),
                Is.False);
        }
    }
}
