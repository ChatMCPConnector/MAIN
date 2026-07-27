using System;
using System.Globalization;
using System.Text;

namespace Riftbound
{
    public enum CoopRole { Offline, Host, Client }
    public enum CoopConnectionState { Offline, Discovering, Hosting, Connecting, Connected, Reconnecting, Rejected }

    [Serializable]
    public sealed class CoopSessionAdvertisement
    {
        public string address;
        public int port;
        public string sessionCode;
        public int seed;
        public int roomIndex;
        public int playerCount;
        public bool joinable;
        public double lastSeenSeconds;

        public string Key => $"{address}:{port}:{sessionCode}";
    }

    [Serializable]
    public sealed class CoopPeerState
    {
        public long sequence;
        public string token;
        public int seed;
        public int roomIndex;
        public float x;
        public float y;
        public float z;
        public float health;
        public float maxHealth;
        public bool downed;
        public bool ready;
    }

    public static class CoopProtocol
    {
        public const string Prefix = "RB5";
        public const int Version = 1;

        public static string EncodeDiscovery(CoopSessionAdvertisement value)
        {
            if (value == null) throw new ArgumentNullException(nameof(value));
            return Join(
                Prefix,
                "DISC",
                Version,
                Sanitize(value.sessionCode),
                value.port,
                value.seed,
                value.roomIndex,
                value.playerCount,
                value.joinable ? 1 : 0);
        }

        public static bool TryDecodeDiscovery(string payload, string address, out CoopSessionAdvertisement value)
        {
            value = null;
            var parts = Split(payload, "DISC", 9);
            if (parts == null ||
                !TryInt(parts[2], out var version) || version != Version ||
                !TryInt(parts[4], out var port) ||
                !TryInt(parts[5], out var seed) ||
                !TryInt(parts[6], out var roomIndex) ||
                !TryInt(parts[7], out var playerCount) ||
                !TryInt(parts[8], out var joinable))
                return false;

            if (string.IsNullOrWhiteSpace(parts[3]) || port <= 0 || port > 65535)
                return false;

            value = new CoopSessionAdvertisement
            {
                address = string.IsNullOrWhiteSpace(address) ? "127.0.0.1" : address,
                port = port,
                sessionCode = parts[3],
                seed = seed,
                roomIndex = Math.Max(0, roomIndex),
                playerCount = Math.Clamp(playerCount, 1, 2),
                joinable = joinable != 0
            };
            return true;
        }

        public static string EncodeHello(string sessionCode, string token)
        {
            return Join(Prefix, "HELLO", Version, Sanitize(sessionCode), Sanitize(token));
        }

        public static bool TryDecodeHello(string payload, out string sessionCode, out string token)
        {
            sessionCode = token = null;
            var parts = Split(payload, "HELLO", 5);
            if (parts == null || !TryInt(parts[2], out var version) || version != Version)
                return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        public static string EncodeWelcome(string sessionCode, string token, int seed, int roomIndex)
        {
            return Join(
                Prefix,
                "WELCOME",
                Version,
                Sanitize(sessionCode),
                Sanitize(token),
                seed,
                Math.Max(0, roomIndex));
        }

        public static bool TryDecodeWelcome(
            string payload,
            out string sessionCode,
            out string token,
            out int seed,
            out int roomIndex)
        {
            sessionCode = token = null;
            seed = roomIndex = 0;
            var parts = Split(payload, "WELCOME", 7);
            if (parts == null ||
                !TryInt(parts[2], out var version) || version != Version ||
                !TryInt(parts[5], out seed) ||
                !TryInt(parts[6], out roomIndex))
                return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        public static string EncodeState(CoopPeerState value)
        {
            if (value == null) throw new ArgumentNullException(nameof(value));
            return Join(
                Prefix,
                "STATE",
                Version,
                value.sequence,
                Sanitize(value.token),
                value.seed,
                value.roomIndex,
                Float(value.x),
                Float(value.y),
                Float(value.z),
                Float(value.health),
                Float(value.maxHealth),
                value.downed ? 1 : 0,
                value.ready ? 1 : 0);
        }

        public static bool TryDecodeState(string payload, out CoopPeerState value)
        {
            value = null;
            var parts = Split(payload, "STATE", 14);
            if (parts == null ||
                !TryInt(parts[2], out var version) || version != Version ||
                !long.TryParse(parts[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out var sequence) ||
                !TryInt(parts[5], out var seed) ||
                !TryInt(parts[6], out var roomIndex) ||
                !TryFloat(parts[7], out var x) ||
                !TryFloat(parts[8], out var y) ||
                !TryFloat(parts[9], out var z) ||
                !TryFloat(parts[10], out var health) ||
                !TryFloat(parts[11], out var maxHealth) ||
                !TryInt(parts[12], out var downed) ||
                !TryInt(parts[13], out var ready))
                return false;

            if (string.IsNullOrWhiteSpace(parts[4]) || maxHealth < 0f)
                return false;

            value = new CoopPeerState
            {
                sequence = sequence,
                token = parts[4],
                seed = seed,
                roomIndex = Math.Max(0, roomIndex),
                x = x,
                y = y,
                z = z,
                health = Math.Max(0f, health),
                maxHealth = Math.Max(0f, maxHealth),
                downed = downed != 0,
                ready = ready != 0
            };
            return true;
        }

        public static string EncodeCommand(string command, string token)
        {
            return Join(Prefix, "CMD", Version, Sanitize(command).ToUpperInvariant(), Sanitize(token));
        }

        public static bool TryDecodeCommand(string payload, out string command, out string token)
        {
            command = token = null;
            var parts = Split(payload, "CMD", 5);
            if (parts == null || !TryInt(parts[2], out var version) || version != Version)
                return false;
            command = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(command) && !string.IsNullOrWhiteSpace(token);
        }

        public static string EncodeReject(string reason)
        {
            return Join(Prefix, "REJECT", Version, Sanitize(reason));
        }

        public static bool TryDecodeReject(string payload, out string reason)
        {
            reason = null;
            var parts = Split(payload, "REJECT", 4);
            if (parts == null || !TryInt(parts[2], out var version) || version != Version)
                return false;
            reason = parts[3];
            return true;
        }

        private static string[] Split(string payload, string type, int expected)
        {
            if (string.IsNullOrWhiteSpace(payload)) return null;
            var parts = payload.Split('|');
            if (parts.Length != expected || parts[0] != Prefix || parts[1] != type)
                return null;
            return parts;
        }

        private static string Join(params object[] values)
        {
            var builder = new StringBuilder(128);
            for (var i = 0; i < values.Length; i++)
            {
                if (i > 0) builder.Append('|');
                builder.Append(Convert.ToString(values[i], CultureInfo.InvariantCulture));
            }
            return builder.ToString();
        }

        private static string Float(float value)
        {
            return value.ToString("0.###", CultureInfo.InvariantCulture);
        }

        private static string Sanitize(string value)
        {
            return (value ?? string.Empty).Replace("|", string.Empty).Trim();
        }

        private static bool TryInt(string value, out int result)
        {
            return int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out result);
        }

        private static bool TryFloat(string value, out float result)
        {
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result) &&
                   !float.IsNaN(result) &&
                   !float.IsInfinity(result);
        }
    }

    public static class CoopBalance
    {
        public static int ScaleEnemyCount(int baseCount, int playerCount, RoomKind roomKind)
        {
            baseCount = Math.Max(0, baseCount);
            if (playerCount <= 1 || roomKind == RoomKind.Boss) return baseCount;
            var bonus = roomKind == RoomKind.Elite ? 2 : Math.Max(1, (int)Math.Ceiling(baseCount * .55f));
            return baseCount + bonus;
        }

        public static float EnemyHealthMultiplier(int playerCount, EnemyKind kind)
        {
            if (playerCount <= 1) return 1f;
            return kind switch
            {
                EnemyKind.Boss => 1.48f,
                EnemyKind.Elite => 1.34f,
                _ => 1.22f
            };
        }

        public static float EnemyDamageMultiplier(int playerCount)
        {
            return playerCount <= 1 ? 1f : 1.08f;
        }

        public static int LootChoiceCount(int playerCount)
        {
            return playerCount <= 1 ? 3 : 4;
        }
    }

    public sealed class CoopReadyGate
    {
        public bool LocalReady { get; private set; }
        public bool RemoteReady { get; private set; }

        public void SetLocal(bool value) => LocalReady = value;
        public void SetRemote(bool value) => RemoteReady = value;

        public bool TryConsume()
        {
            if (!LocalReady || !RemoteReady) return false;
            LocalReady = false;
            RemoteReady = false;
            return true;
        }

        public void Reset()
        {
            LocalReady = false;
            RemoteReady = false;
        }
    }

    public sealed class CoopReviveState
    {
        public bool LocalDowned { get; private set; }
        public bool RemoteDowned { get; private set; }
        public bool PartyDefeated => LocalDowned && RemoteDowned;
        public bool CanReviveRemote => !LocalDowned && RemoteDowned;

        public void SetLocalDowned(bool value) => LocalDowned = value;
        public void SetRemoteDowned(bool value) => RemoteDowned = value;
        public void Reset()
        {
            LocalDowned = false;
            RemoteDowned = false;
        }
    }

    public static class CoopReconnectPolicy
    {
        public const double GraceSeconds = 20d;

        public static bool CanReconnect(string expectedToken, string suppliedToken, double secondsSinceDisconnect)
        {
            return !string.IsNullOrWhiteSpace(expectedToken) &&
                   string.Equals(expectedToken, suppliedToken, StringComparison.Ordinal) &&
                   secondsSinceDisconnect >= 0d &&
                   secondsSinceDisconnect <= GraceSeconds;
        }
    }

    public static class CoopSessionCode
    {
        public static string FromToken(string token)
        {
            unchecked
            {
                var hash = 17;
                foreach (var character in token ?? string.Empty)
                    hash = hash * 31 + character;
                var value = Math.Abs(hash % 10000);
                return value.ToString("0000", CultureInfo.InvariantCulture);
            }
        }
    }

    public static class CoopRuntimeState
    {
        public static CoopRole Role { get; private set; } = CoopRole.Offline;
        public static bool Connected { get; private set; }
        public static int ActivePlayerCount => Connected ? 2 : 1;

        public static void Set(CoopRole role, bool connected)
        {
            Role = role;
            Connected = connected && role != CoopRole.Offline;
        }

        public static void Reset()
        {
            Role = CoopRole.Offline;
            Connected = false;
        }
    }
}