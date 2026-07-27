using System;
using System.Collections.Generic;
using System.Globalization;
using System.Text;
using UnityEngine;

namespace Riftbound
{
    public enum CoopAttackKind { Melee, Ability }

    [Serializable]
    public sealed class CoopEnemySnapshot
    {
        public int networkId;
        public EnemyKind kind;
        public float x;
        public float y;
        public float z;
        public float yaw;
        public float health;
        public float maxHealth;
        public int bossPhase;
    }

    [Serializable]
    public sealed class CoopAttackIntent
    {
        public long sequence;
        public CoopAttackKind kind;
        public Vector3 origin;
        public Vector3 direction;
        public float damage;
        public float range;
    }

    public static class CoopCombatProtocol
    {
        public const string Prefix = "RB5C";
        public const int Version = 1;

        public static string EncodeHello(string sessionCode, string token)
        {
            return Join(Prefix, "HELLO", Version, Clean(sessionCode), Clean(token));
        }

        public static bool TryDecodeHello(string payload, out string sessionCode, out string token)
        {
            sessionCode = token = null;
            var parts = Split(payload, "HELLO", 5);
            if (!HasVersion(parts)) return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        public static string EncodeWelcome(string sessionCode, string token)
        {
            return Join(Prefix, "WELCOME", Version, Clean(sessionCode), Clean(token));
        }

        public static bool TryDecodeWelcome(string payload, out string sessionCode, out string token)
        {
            sessionCode = token = null;
            var parts = Split(payload, "WELCOME", 5);
            if (!HasVersion(parts)) return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        public static string EncodeEnemies(
            string sessionCode,
            string token,
            long sequence,
            int roomIndex,
            IReadOnlyList<CoopEnemySnapshot> snapshots)
        {
            var count = snapshots?.Count ?? 0;
            var entries = new StringBuilder(Math.Max(32, count * 64));
            for (var i = 0; i < count; i++)
            {
                if (i > 0) entries.Append(';');
                var value = snapshots[i];
                entries.Append(value.networkId).Append(',')
                    .Append((int)value.kind).Append(',')
                    .Append(Float(value.x)).Append(',')
                    .Append(Float(value.y)).Append(',')
                    .Append(Float(value.z)).Append(',')
                    .Append(Float(value.yaw)).Append(',')
                    .Append(Float(value.health)).Append(',')
                    .Append(Float(value.maxHealth)).Append(',')
                    .Append(Math.Max(1, value.bossPhase));
            }

            return Join(
                Prefix,
                "ENEMIES",
                Version,
                Clean(sessionCode),
                Clean(token),
                sequence,
                Math.Max(0, roomIndex),
                count,
                entries.ToString());
        }

        public static bool TryDecodeEnemies(
            string payload,
            out string sessionCode,
            out string token,
            out long sequence,
            out int roomIndex,
            out List<CoopEnemySnapshot> snapshots)
        {
            sessionCode = token = null;
            sequence = roomIndex = 0;
            snapshots = null;
            var parts = Split(payload, "ENEMIES", 9);
            if (!HasVersion(parts) ||
                !TryLong(parts[5], out sequence) || sequence < 0 ||
                !TryInt(parts[6], out roomIndex) || roomIndex < 0 ||
                !TryInt(parts[7], out var count) || count < 0 || count > 64)
                return false;

            sessionCode = parts[3];
            token = parts[4];
            if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                return false;

            snapshots = new List<CoopEnemySnapshot>(count);
            if (count == 0) return string.IsNullOrEmpty(parts[8]);
            var entries = parts[8].Split(';');
            if (entries.Length != count) return false;
            for (var i = 0; i < entries.Length; i++)
            {
                var fields = entries[i].Split(',');
                if (fields.Length != 9 ||
                    !TryInt(fields[0], out var id) || id <= 0 ||
                    !TryInt(fields[1], out var kindValue) ||
                    kindValue < 0 || kindValue > (int)EnemyKind.Boss ||
                    !TryFloat(fields[2], out var x) ||
                    !TryFloat(fields[3], out var y) ||
                    !TryFloat(fields[4], out var z) ||
                    !TryFloat(fields[5], out var yaw) ||
                    !TryFloat(fields[6], out var health) || health < 0f ||
                    !TryFloat(fields[7], out var maxHealth) || maxHealth <= 0f ||
                    !TryInt(fields[8], out var phase) || phase < 1 || phase > 3)
                    return false;

                snapshots.Add(new CoopEnemySnapshot
                {
                    networkId = id,
                    kind = (EnemyKind)kindValue,
                    x = x,
                    y = y,
                    z = z,
                    yaw = yaw,
                    health = Mathf.Min(health, maxHealth),
                    maxHealth = maxHealth,
                    bossPhase = phase
                });
            }
            return true;
        }

        public static string EncodeAttack(
            string sessionCode,
            string token,
            CoopAttackIntent intent)
        {
            if (intent == null) throw new ArgumentNullException(nameof(intent));
            return Join(
                Prefix,
                "ATTACK",
                Version,
                Clean(sessionCode),
                Clean(token),
                intent.sequence,
                (int)intent.kind,
                Float(intent.origin.x),
                Float(intent.origin.y),
                Float(intent.origin.z),
                Float(intent.direction.x),
                Float(intent.direction.y),
                Float(intent.direction.z),
                Float(intent.damage),
                Float(intent.range));
        }

        public static bool TryDecodeAttack(
            string payload,
            out string sessionCode,
            out string token,
            out CoopAttackIntent intent)
        {
            sessionCode = token = null;
            intent = null;
            var parts = Split(payload, "ATTACK", 15);
            if (!HasVersion(parts) ||
                !TryLong(parts[5], out var sequence) || sequence <= 0 ||
                !TryInt(parts[6], out var kindValue) ||
                kindValue < 0 || kindValue > (int)CoopAttackKind.Ability ||
                !TryFloat(parts[7], out var x) ||
                !TryFloat(parts[8], out var y) ||
                !TryFloat(parts[9], out var z) ||
                !TryFloat(parts[10], out var dx) ||
                !TryFloat(parts[11], out var dy) ||
                !TryFloat(parts[12], out var dz) ||
                !TryFloat(parts[13], out var damage) ||
                !TryFloat(parts[14], out var range))
                return false;

            sessionCode = parts[3];
            token = parts[4];
            if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                return false;

            intent = new CoopAttackIntent
            {
                sequence = sequence,
                kind = (CoopAttackKind)kindValue,
                origin = new Vector3(x, y, z),
                direction = new Vector3(dx, dy, dz),
                damage = damage,
                range = range
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

    public static class CoopCombatValidation
    {
        public static bool IsFresh(long sequence, ref long lastSequence)
        {
            if (sequence <= lastSequence) return false;
            lastSequence = sequence;
            return true;
        }

        public static bool IsValidAttack(
            CoopAttackIntent intent,
            Vector3 confirmedPlayerPosition,
            float now,
            ref float nextMelee,
            ref float nextAbility)
        {
            if (intent == null ||
                intent.damage < 1f || intent.damage > 500f ||
                intent.range < .5f || intent.range > 4f ||
                intent.direction.sqrMagnitude < .25f ||
                Vector3.Distance(intent.origin, confirmedPlayerPosition) > 2.5f)
                return false;

            if (intent.kind == CoopAttackKind.Melee)
            {
                if (now < nextMelee) return false;
                nextMelee = now + .11f;
            }
            else
            {
                if (now < nextAbility) return false;
                nextAbility = now + .45f;
            }
            return true;
        }
    }
}
