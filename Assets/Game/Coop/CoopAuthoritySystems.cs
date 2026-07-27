using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace Riftbound
{
    public enum CoopDamageKind { Melee, Projectile, Hazard }

    [Serializable]
    public sealed class CoopProjectileSnapshot
    {
        public int networkId;
        public float x;
        public float y;
        public float z;
        public float damage;
        public float radius;
    }

    [Serializable]
    public sealed class CoopDefenseState
    {
        public long sequence;
        public bool invulnerable;
    }

    [Serializable]
    public sealed class CoopDamageEvent
    {
        public long sequence;
        public float amount;
        public CoopDamageKind kind;
    }

    public readonly struct CoopCombatTarget
    {
        public readonly bool valid;
        public readonly bool remote;
        public readonly Vector3 position;

        public CoopCombatTarget(bool valid, bool remote, Vector3 position)
        {
            this.valid = valid;
            this.remote = remote;
            this.position = position;
        }
    }

    public static class CoopTargeting
    {
        public static CoopCombatTarget SelectNearest(
            Vector3 origin,
            bool localAlive,
            Vector3 localPosition,
            bool remoteAlive,
            Vector3 remotePosition,
            int discriminator)
        {
            if (!localAlive && !remoteAlive)
                return new CoopCombatTarget(false, false, origin);
            if (!remoteAlive)
                return new CoopCombatTarget(true, false, localPosition);
            if (!localAlive)
                return new CoopCombatTarget(true, true, remotePosition);

            var localDistance = FlatDistanceSquared(origin, localPosition);
            var remoteDistance = FlatDistanceSquared(origin, remotePosition);
            if (Mathf.Abs(localDistance - remoteDistance) <= .20f)
            {
                var chooseRemote = (discriminator & 1) != 0;
                return new CoopCombatTarget(
                    true,
                    chooseRemote,
                    chooseRemote ? remotePosition : localPosition);
            }

            var remoteIsCloser = remoteDistance < localDistance;
            return new CoopCombatTarget(
                true,
                remoteIsCloser,
                remoteIsCloser ? remotePosition : localPosition);
        }

        private static float FlatDistanceSquared(Vector3 first, Vector3 second)
        {
            var delta = first - second;
            delta.y = 0f;
            return delta.sqrMagnitude;
        }
    }

    public static class CoopAuthorityProtocol
    {
        public const string Prefix = "RB5H";
        public const int Version = 1;

        public static string EncodeProjectiles(
            string sessionCode,
            string token,
            long sequence,
            int roomIndex,
            IReadOnlyList<CoopProjectileSnapshot> snapshots)
        {
            var count = snapshots?.Count ?? 0;
            var entries = new StringBuilder(Math.Max(32, count * 48));
            for (var i = 0; i < count; i++)
            {
                if (i > 0) entries.Append(';');
                var value = snapshots[i];
                entries.Append(value.networkId).Append(',')
                    .Append(Float(value.x)).Append(',')
                    .Append(Float(value.y)).Append(',')
                    .Append(Float(value.z)).Append(',')
                    .Append(Float(value.damage)).Append(',')
                    .Append(Float(value.radius));
            }

            return Join(
                Prefix,
                "PROJECTILES",
                Version,
                Clean(sessionCode),
                Clean(token),
                sequence,
                Math.Max(0, roomIndex),
                count,
                entries.ToString());
        }

        public static bool TryDecodeProjectiles(
            string payload,
            out string sessionCode,
            out string token,
            out long sequence,
            out int roomIndex,
            out List<CoopProjectileSnapshot> snapshots)
        {
            sessionCode = token = null;
            sequence = roomIndex = 0;
            snapshots = null;
            var parts = Split(payload, "PROJECTILES", 9);
            if (!HasVersion(parts) ||
                !TryLong(parts[5], out sequence) || sequence < 0 ||
                !TryInt(parts[6], out roomIndex) || roomIndex < 0 ||
                !TryInt(parts[7], out var count) || count < 0 || count > 128)
                return false;

            sessionCode = parts[3];
            token = parts[4];
            if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                return false;

            snapshots = new List<CoopProjectileSnapshot>(count);
            if (count == 0) return string.IsNullOrEmpty(parts[8]);
            var entries = parts[8].Split(';');
            if (entries.Length != count) return false;
            var ids = new HashSet<int>();
            for (var i = 0; i < entries.Length; i++)
            {
                var fields = entries[i].Split(',');
                if (fields.Length != 6 ||
                    !TryInt(fields[0], out var id) || id <= 0 || !ids.Add(id) ||
                    !TryFloat(fields[1], out var x) ||
                    !TryFloat(fields[2], out var y) ||
                    !TryFloat(fields[3], out var z) ||
                    !TryFloat(fields[4], out var damage) || damage <= 0f || damage > 500f ||
                    !TryFloat(fields[5], out var radius) || radius <= 0f || radius > 3f)
                    return false;

                snapshots.Add(new CoopProjectileSnapshot
                {
                    networkId = id,
                    x = x,
                    y = y,
                    z = z,
                    damage = damage,
                    radius = radius
                });
            }
            return true;
        }

        public static string EncodeDefense(
            string sessionCode,
            string token,
            CoopDefenseState state)
        {
            if (state == null) throw new ArgumentNullException(nameof(state));
            return Join(
                Prefix,
                "DEFENSE",
                Version,
                Clean(sessionCode),
                Clean(token),
                state.sequence,
                state.invulnerable ? 1 : 0);
        }

        public static bool TryDecodeDefense(
            string payload,
            out string sessionCode,
            out string token,
            out CoopDefenseState state)
        {
            sessionCode = token = null;
            state = null;
            var parts = Split(payload, "DEFENSE", 7);
            if (!HasVersion(parts) ||
                !TryLong(parts[5], out var sequence) || sequence <= 0 ||
                !TryInt(parts[6], out var invulnerable) || (invulnerable != 0 && invulnerable != 1))
                return false;

            sessionCode = parts[3];
            token = parts[4];
            if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                return false;
            state = new CoopDefenseState
            {
                sequence = sequence,
                invulnerable = invulnerable != 0
            };
            return true;
        }

        public static string EncodeDamage(
            string sessionCode,
            string token,
            CoopDamageEvent damageEvent)
        {
            if (damageEvent == null) throw new ArgumentNullException(nameof(damageEvent));
            return Join(
                Prefix,
                "DAMAGE",
                Version,
                Clean(sessionCode),
                Clean(token),
                damageEvent.sequence,
                Float(damageEvent.amount),
                (int)damageEvent.kind);
        }

        public static bool TryDecodeDamage(
            string payload,
            out string sessionCode,
            out string token,
            out CoopDamageEvent damageEvent)
        {
            sessionCode = token = null;
            damageEvent = null;
            var parts = Split(payload, "DAMAGE", 8);
            if (!HasVersion(parts) ||
                !TryLong(parts[5], out var sequence) || sequence <= 0 ||
                !TryFloat(parts[6], out var amount) ||
                !TryInt(parts[7], out var kindValue) ||
                kindValue < 0 || kindValue > (int)CoopDamageKind.Hazard ||
                !CoopAuthorityValidation.IsValidDamage(amount))
                return false;

            sessionCode = parts[3];
            token = parts[4];
            if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                return false;
            damageEvent = new CoopDamageEvent
            {
                sequence = sequence,
                amount = amount,
                kind = (CoopDamageKind)kindValue
            };
            return true;
        }

        private static bool HasVersion(string[] parts)
        {
            return parts != null &&
                   TryInt(parts[2], out var version) &&
                   version == Version;
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
            var builder = new StringBuilder(256);
            for (var i = 0; i < values.Length; i++)
            {
                if (i > 0) builder.Append('|');
                builder.Append(Convert.ToString(values[i], CultureInfo.InvariantCulture));
            }
            return builder.ToString();
        }

        private static string Clean(string value)
        {
            return (value ?? string.Empty)
                .Replace("|", string.Empty)
                .Replace(";", string.Empty)
                .Replace(",", string.Empty)
                .Trim();
        }

        private static string Float(float value) =>
            value.ToString("0.###", CultureInfo.InvariantCulture);

        private static bool TryInt(string value, out int result) =>
            int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out result);

        private static bool TryLong(string value, out long result) =>
            long.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out result);

        private static bool TryFloat(string value, out float result)
        {
            return float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result) &&
                   !float.IsNaN(result) &&
                   !float.IsInfinity(result);
        }
    }

    public static class CoopAuthorityValidation
    {
        public static bool IsValidDamage(float amount)
        {
            return amount > 0f && amount <= 500f &&
                   !float.IsNaN(amount) && !float.IsInfinity(amount);
        }
    }
}
