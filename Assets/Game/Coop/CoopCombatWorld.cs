using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;

namespace Riftbound
{
    public static class CoopCombatWorld
    {
        public static int CreateNetworkId(int roomIndex, EnemyKind kind, Vector3 position)
        {
            unchecked
            {
                var hash = 17;
                hash = hash * 31 + roomIndex;
                hash = hash * 31 + (int)kind;
                hash = hash * 31 + Mathf.RoundToInt(position.x * 100f);
                hash = hash * 31 + Mathf.RoundToInt(position.z * 100f);
                if (hash == int.MinValue) hash = int.MaxValue;
                hash = Math.Abs(hash);
                return hash == 0 ? 1 : hash;
            }
        }

        public static CoopEnemySnapshot[] CaptureEnemySnapshots(int roomIndex)
        {
            return FindObjectsByType<EnemyController>(FindObjectsSortMode.None)
                .Where(enemy => enemy != null && !enemy.IsDead && !enemy.IsReplica)
                .Select(enemy => enemy.CreateSnapshot())
                .OrderBy(snapshot => snapshot.networkId)
                .ToArray();
        }

        public static void ApplyEnemySnapshots(
            GameBootstrap game,
            int roomIndex,
            IReadOnlyList<CoopEnemySnapshot> snapshots)
        {
            if (game == null || snapshots == null || game.RoomIndex != roomIndex) return;
            var existing = FindObjectsByType<EnemyController>(FindObjectsSortMode.None)
                .Where(enemy => enemy != null)
                .ToDictionary(enemy => enemy.NetworkId, enemy => enemy);
            var alive = new HashSet<int>();

            for (var i = 0; i < snapshots.Count; i++)
            {
                var snapshot = snapshots[i];
                alive.Add(snapshot.networkId);
                if (existing.TryGetValue(snapshot.networkId, out var enemy))
                {
                    enemy.SetReplicaMode(true);
                    enemy.ApplyReplicaSnapshot(snapshot);
                }
            }

            foreach (var pair in existing)
            {
                if (alive.Contains(pair.Key)) continue;
                if (pair.Value != null) UnityEngine.Object.Destroy(pair.Value.gameObject);
            }

            if (snapshots.Count == 0 && game.Player != null && game.Player.CombatEnabled)
                game.SendMessage("CompleteCombatRoom", SendMessageOptions.DontRequireReceiver);
        }

        public static void SetReplication(bool enabled)
        {
            var enemies = FindObjectsByType<EnemyController>(FindObjectsSortMode.None);
            foreach (var enemy in enemies)
                if (enemy != null) enemy.SetReplicaMode(enabled);
        }

        public static void ApplyRemoteAttack(GameBootstrap game, CoopAttackIntent intent)
        {
            if (game == null || intent == null || CoopRuntimeState.Role != CoopRole.Host) return;
            var direction = intent.direction.sqrMagnitude > .001f
                ? intent.direction.normalized
                : Vector3.forward;

            if (intent.kind == CoopAttackKind.Ability)
            {
                Projectile.Spawn(
                    intent.origin + Vector3.up * .7f + direction * .7f,
                    direction,
                    intent.damage,
                    true);
                return;
            }

            var center = intent.origin + direction * (intent.range * .65f);
            var enemies = FindObjectsByType<EnemyController>(FindObjectsSortMode.None);
            foreach (var enemy in enemies)
            {
                if (enemy == null || enemy.IsReplica || enemy.IsDead) continue;
                var delta = enemy.transform.position - center;
                delta.y = 0f;
                if (delta.sqrMagnitude <= intent.range * intent.range)
                    enemy.TakeDamage(intent.damage);
            }
            PlayerController.Pulse(new Color(.95f, .58f, .12f), center, .35f, .4f);
        }
    }
}
