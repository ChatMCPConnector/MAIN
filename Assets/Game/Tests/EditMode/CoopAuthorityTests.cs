using System.Collections.Generic;
using System.Globalization;
using NUnit.Framework;
using UnityEngine;

namespace Riftbound.Tests
{
    public sealed class CoopAuthorityTests
    {
        [Test]
        public void TargetingChoosesCloserLivingPlayer()
        {
            var target = CoopTargeting.SelectNearest(
                Vector3.zero,
                true,
                new Vector3(3f, 1f, 0f),
                true,
                new Vector3(1f, 1f, 0f),
                2);

            Assert.That(target.valid, Is.True);
            Assert.That(target.remote, Is.True);
            Assert.That(target.position.x, Is.EqualTo(1f));
        }

        [Test]
        public void TargetingFallsBackToOnlyLivingPlayer()
        {
            var target = CoopTargeting.SelectNearest(
                Vector3.zero,
                false,
                new Vector3(1f, 1f, 0f),
                true,
                new Vector3(4f, 1f, 0f),
                1);

            Assert.That(target.valid, Is.True);
            Assert.That(target.remote, Is.True);
        }

        [Test]
        public void EqualDistanceAggroIsSplitByEnemyId()
        {
            var even = CoopTargeting.SelectNearest(
                Vector3.zero,
                true,
                new Vector3(-1f, 1f, 0f),
                true,
                new Vector3(1f, 1f, 0f),
                20);
            var odd = CoopTargeting.SelectNearest(
                Vector3.zero,
                true,
                new Vector3(-1f, 1f, 0f),
                true,
                new Vector3(1f, 1f, 0f),
                21);

            Assert.That(even.remote, Is.False);
            Assert.That(odd.remote, Is.True);
        }

        [Test]
        public void ProjectilePacketRoundTripsUnderGermanCulture()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
                var snapshots = new List<CoopProjectileSnapshot>
                {
                    new CoopProjectileSnapshot
                    {
                        networkId = 44,
                        x = 1.25f,
                        y = .5f,
                        z = -2.75f,
                        damage = 18.5f,
                        radius = .14f
                    },
                    new CoopProjectileSnapshot
                    {
                        networkId = 45,
                        x = -1f,
                        y = .55f,
                        z = 3f,
                        damage = 22f,
                        radius = .18f
                    }
                };

                var payload = CoopAuthorityProtocol.EncodeProjectiles(
                    "0427",
                    "host-token",
                    9,
                    6,
                    snapshots);
                StringAssert.Contains("1.25", payload);
                Assert.That(
                    CoopAuthorityProtocol.TryDecodeProjectiles(
                        payload,
                        out var code,
                        out var token,
                        out var sequence,
                        out var room,
                        out var decoded),
                    Is.True);
                Assert.That(code, Is.EqualTo("0427"));
                Assert.That(token, Is.EqualTo("host-token"));
                Assert.That(sequence, Is.EqualTo(9));
                Assert.That(room, Is.EqualTo(6));
                Assert.That(decoded, Has.Count.EqualTo(2));
                Assert.That(decoded[0].damage, Is.EqualTo(18.5f).Within(.001f));
                Assert.That(decoded[0].radius, Is.EqualTo(.14f).Within(.001f));
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }

        [Test]
        public void EmptyProjectilePacketRoundTrips()
        {
            var payload = CoopAuthorityProtocol.EncodeProjectiles(
                "1111",
                "host",
                4,
                2,
                new List<CoopProjectileSnapshot>());
            Assert.That(
                CoopAuthorityProtocol.TryDecodeProjectiles(
                    payload,
                    out _,
                    out _,
                    out _,
                    out _,
                    out var decoded),
                Is.True);
            Assert.That(decoded, Is.Empty);
        }

        [Test]
        public void DuplicateProjectileIdsAreRejected()
        {
            var payload = "RB5H|PROJECTILES|1|1234|host|1|2|2|" +
                          "7,0,1,0,10,0.1;7,1,1,0,10,0.1";
            Assert.That(
                CoopAuthorityProtocol.TryDecodeProjectiles(
                    payload,
                    out _,
                    out _,
                    out _,
                    out _,
                    out _),
                Is.False);
        }

        [Test]
        public void DefensePacketRoundTrips()
        {
            var payload = CoopAuthorityProtocol.EncodeDefense(
                "2020",
                "client",
                new CoopDefenseState { sequence = 12, invulnerable = true });
            Assert.That(
                CoopAuthorityProtocol.TryDecodeDefense(
                    payload,
                    out var code,
                    out var token,
                    out var state),
                Is.True);
            Assert.That(code, Is.EqualTo("2020"));
            Assert.That(token, Is.EqualTo("client"));
            Assert.That(state.sequence, Is.EqualTo(12));
            Assert.That(state.invulnerable, Is.True);
        }

        [Test]
        public void DamagePacketRoundTripsAndRejectsInvalidAmounts()
        {
            var payload = CoopAuthorityProtocol.EncodeDamage(
                "3030",
                "host",
                new CoopDamageEvent
                {
                    sequence = 8,
                    amount = 24.5f,
                    kind = CoopDamageKind.Projectile
                });
            Assert.That(
                CoopAuthorityProtocol.TryDecodeDamage(
                    payload,
                    out _,
                    out _,
                    out var damageEvent),
                Is.True);
            Assert.That(damageEvent.amount, Is.EqualTo(24.5f).Within(.001f));
            Assert.That(damageEvent.kind, Is.EqualTo(CoopDamageKind.Projectile));

            Assert.That(
                CoopAuthorityProtocol.TryDecodeDamage(
                    "RB5H|DAMAGE|1|3030|host|9|9999|1",
                    out _,
                    out _,
                    out _),
                Is.False);
            Assert.That(CoopAuthorityValidation.IsValidDamage(float.NaN), Is.False);
            Assert.That(CoopAuthorityValidation.IsValidDamage(0f), Is.False);
            Assert.That(CoopAuthorityValidation.IsValidDamage(500f), Is.True);
        }

        [Test]
        public void MalformedAuthorityPacketsAreRejected()
        {
            Assert.That(
                CoopAuthorityProtocol.TryDecodeDefense(
                    "RB5H|DEFENSE|99|1234|client|1|1",
                    out _,
                    out _,
                    out _),
                Is.False);
            Assert.That(
                CoopAuthorityProtocol.TryDecodeProjectiles(
                    "RB5H|PROJECTILES|1|1234|host|1|2|1|broken",
                    out _,
                    out _,
                    out _,
                    out _,
                    out _),
                Is.False);
        }
    }
}
