using System.Globalization;
using NUnit.Framework;

namespace Riftbound.Tests
{
    public sealed class CoopSystemTests
    {
        [Test]
        public void DiscoveryPacketRoundTrips()
        {
            var advertisement = new CoopSessionAdvertisement
            {
                port = 47781,
                sessionCode = "0427",
                seed = -18422,
                roomIndex = 5,
                playerCount = 1,
                joinable = true
            };

            var payload = CoopProtocol.EncodeDiscovery(advertisement);
            Assert.That(
                CoopProtocol.TryDecodeDiscovery(payload, "192.168.1.25", out var decoded),
                Is.True);
            Assert.That(decoded.address, Is.EqualTo("192.168.1.25"));
            Assert.That(decoded.port, Is.EqualTo(advertisement.port));
            Assert.That(decoded.sessionCode, Is.EqualTo(advertisement.sessionCode));
            Assert.That(decoded.seed, Is.EqualTo(advertisement.seed));
            Assert.That(decoded.roomIndex, Is.EqualTo(advertisement.roomIndex));
            Assert.That(decoded.joinable, Is.True);
        }

        [Test]
        public void StatePacketUsesInvariantNumbersUnderGermanCulture()
        {
            var previous = CultureInfo.CurrentCulture;
            try
            {
                CultureInfo.CurrentCulture = CultureInfo.GetCultureInfo("de-DE");
                var state = new CoopPeerState
                {
                    sequence = 91,
                    token = "client-token",
                    seed = 700,
                    roomIndex = 4,
                    x = 1.25f,
                    y = 1f,
                    z = -2.75f,
                    health = 63.5f,
                    maxHealth = 112.75f,
                    downed = false,
                    ready = true
                };

                var payload = CoopProtocol.EncodeState(state);
                StringAssert.Contains("1.25", payload);
                Assert.That(CoopProtocol.TryDecodeState(payload, out var decoded), Is.True);
                Assert.That(decoded.sequence, Is.EqualTo(state.sequence));
                Assert.That(decoded.x, Is.EqualTo(state.x).Within(.001f));
                Assert.That(decoded.z, Is.EqualTo(state.z).Within(.001f));
                Assert.That(decoded.health, Is.EqualTo(state.health).Within(.001f));
                Assert.That(decoded.ready, Is.True);
            }
            finally
            {
                CultureInfo.CurrentCulture = previous;
            }
        }

        [Test]
        public void HelloWelcomeAndCommandsRoundTrip()
        {
            var hello = CoopProtocol.EncodeHello("1234", "client");
            Assert.That(CoopProtocol.TryDecodeHello(hello, out var code, out var client), Is.True);
            Assert.That(code, Is.EqualTo("1234"));
            Assert.That(client, Is.EqualTo("client"));

            var welcome = CoopProtocol.EncodeWelcome("1234", "host", 8891, 3);
            Assert.That(
                CoopProtocol.TryDecodeWelcome(
                    welcome,
                    out var welcomeCode,
                    out var host,
                    out var seed,
                    out var room),
                Is.True);
            Assert.That(welcomeCode, Is.EqualTo("1234"));
            Assert.That(host, Is.EqualTo("host"));
            Assert.That(seed, Is.EqualTo(8891));
            Assert.That(room, Is.EqualTo(3));

            var command = CoopProtocol.EncodeCommand("revive", "client");
            Assert.That(CoopProtocol.TryDecodeCommand(command, out var action, out var token), Is.True);
            Assert.That(action, Is.EqualTo("REVIVE"));
            Assert.That(token, Is.EqualTo("client"));
        }

        [Test]
        public void ReadyGateRequiresBothPlayersAndResetsAfterUse()
        {
            var gate = new CoopReadyGate();
            gate.SetLocal(true);
            Assert.That(gate.TryConsume(), Is.False);
            gate.SetRemote(true);
            Assert.That(gate.TryConsume(), Is.True);
            Assert.That(gate.LocalReady, Is.False);
            Assert.That(gate.RemoteReady, Is.False);
        }

        [Test]
        public void ReconnectRequiresSameTokenWithinGraceWindow()
        {
            Assert.That(CoopReconnectPolicy.CanReconnect("abc", "abc", 0d), Is.True);
            Assert.That(
                CoopReconnectPolicy.CanReconnect(
                    "abc",
                    "abc",
                    CoopReconnectPolicy.GraceSeconds),
                Is.True);
            Assert.That(CoopReconnectPolicy.CanReconnect("abc", "other", 1d), Is.False);
            Assert.That(
                CoopReconnectPolicy.CanReconnect(
                    "abc",
                    "abc",
                    CoopReconnectPolicy.GraceSeconds + .01d),
                Is.False);
        }

        [Test]
        public void CoopScalingAddsVarietyWithoutDoublingEverything()
        {
            var solo = CoopBalance.ScaleEnemyCount(4, 1, RoomKind.Combat);
            var coop = CoopBalance.ScaleEnemyCount(4, 2, RoomKind.Combat);
            Assert.That(solo, Is.EqualTo(4));
            Assert.That(coop, Is.GreaterThan(solo));
            Assert.That(coop, Is.LessThan(solo * 2));
            Assert.That(CoopBalance.ScaleEnemyCount(1, 2, RoomKind.Boss), Is.EqualTo(1));
            Assert.That(CoopBalance.EnemyHealthMultiplier(2, EnemyKind.Boss), Is.GreaterThan(1f));
            Assert.That(CoopBalance.EnemyHealthMultiplier(2, EnemyKind.Boss), Is.LessThan(2f));
            Assert.That(CoopBalance.LootChoiceCount(2), Is.EqualTo(4));
        }

        [Test]
        public void ReviveStateDetectsAvailableReviveAndPartyDefeat()
        {
            var state = new CoopReviveState();
            state.SetRemoteDowned(true);
            Assert.That(state.CanReviveRemote, Is.True);
            Assert.That(state.PartyDefeated, Is.False);
            state.SetLocalDowned(true);
            Assert.That(state.CanReviveRemote, Is.False);
            Assert.That(state.PartyDefeated, Is.True);
        }

        [Test]
        public void SessionCodeIsAlwaysFourDigitsAndStable()
        {
            var first = CoopSessionCode.FromToken("device-token-42");
            var second = CoopSessionCode.FromToken("device-token-42");
            Assert.That(first, Is.EqualTo(second));
            Assert.That(first, Does.Match("^[0-9]{4}$"));
        }
    }
}