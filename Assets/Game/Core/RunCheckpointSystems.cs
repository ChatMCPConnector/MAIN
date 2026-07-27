using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Riftbound
{
    [Serializable]
    public sealed class RunCheckpointData
    {
        public int version = 2;
        public int seed;
        public int roomIndex;
        public int runGold;
        public float health;
        public long savedUtcTicks;
        public string equippedWeaponId;
        public string equippedArmorId;
        public int minimumRarity;
        public bool combatActive;
        public List<ItemInstance> items = new List<ItemInstance>();
        public List<int> cardIndexes = new List<int>();
        public List<CoopEnemySnapshot> enemies = new List<CoopEnemySnapshot>();
    }

    public static class RunCheckpointService
    {
        public const int CurrentVersion = 2;
        public static readonly TimeSpan MaximumAge = TimeSpan.FromHours(24);

        private static string PathName =>
            Path.Combine(Application.persistentDataPath, "riftbound-run-checkpoint.json");
        private static string BackupName => PathName + ".bak";
        private static string TemporaryName => PathName + ".tmp";

        public static bool IsUsable(RunCheckpointData data, DateTime utcNow)
        {
            if (data == null || data.version != CurrentVersion ||
                data.roomIndex < 0 || data.roomIndex >= RunPlanner.RoomCount ||
                data.runGold < 0 || data.health <= 0f ||
                data.items == null || data.cardIndexes == null || data.enemies == null ||
                data.savedUtcTicks <= 0 || data.savedUtcTicks > DateTime.MaxValue.Ticks)
                return false;

            try
            {
                var saved = new DateTime(data.savedUtcTicks, DateTimeKind.Utc);
                var age = utcNow - saved;
                return age >= TimeSpan.Zero && age <= MaximumAge;
            }
            catch
            {
                return false;
            }
        }

        public static RunCheckpointData Load()
        {
            var primary = Read(PathName);
            if (IsUsable(primary, DateTime.UtcNow)) return primary;
            var backup = Read(BackupName);
            return IsUsable(backup, DateTime.UtcNow) ? backup : null;
        }

        public static void Save(RunCheckpointData data)
        {
            if (data == null) return;
            data.version = CurrentVersion;
            data.savedUtcTicks = DateTime.UtcNow.Ticks;
            data.items ??= new List<ItemInstance>();
            data.cardIndexes ??= new List<int>();
            data.enemies ??= new List<CoopEnemySnapshot>();

            try
            {
                File.WriteAllText(TemporaryName, JsonUtility.ToJson(data, true));
                if (File.Exists(PathName)) File.Copy(PathName, BackupName, true);
                File.Copy(TemporaryName, PathName, true);
                File.Delete(TemporaryName);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Run checkpoint save failed: {exception.Message}");
            }
        }

        public static void Clear()
        {
            TryDelete(PathName);
            TryDelete(BackupName);
            TryDelete(TemporaryName);
        }

        private static RunCheckpointData Read(string path)
        {
            try
            {
                return File.Exists(path)
                    ? JsonUtility.FromJson<RunCheckpointData>(File.ReadAllText(path))
                    : null;
            }
            catch
            {
                return null;
            }
        }

        private static void TryDelete(string path)
        {
            try
            {
                if (File.Exists(path)) File.Delete(path);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Run checkpoint cleanup failed: {exception.Message}");
            }
        }
    }

    public sealed class RunCheckpointRuntime : MonoBehaviour
    {
        private const float SaveInterval = 1.5f;
        private GameBootstrap game;
        private float nextSave;
        private bool encounterRestoreChecked;
        private bool restoredEncounterActive;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<RunCheckpointRuntime>() != null) return;
            var root = new GameObject("Run Checkpoint Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<RunCheckpointRuntime>();
        }

        private void Update()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            if (!encounterRestoreChecked && game != null)
            {
                encounterRestoreChecked = true;
                RestoreEncounterIfNeeded();
                nextSave = Time.unscaledTime + SaveInterval;
                return;
            }

            if (restoredEncounterActive && game != null && game.Player != null && game.Player.CombatEnabled)
            {
                var enemies = FindObjectsByType<EnemyController>(FindObjectsSortMode.None);
                var alive = 0;
                for (var i = 0; i < enemies.Length; i++)
                    if (enemies[i] != null && !enemies[i].IsDead)
                        alive++;
                if (alive == 0)
                {
                    restoredEncounterActive = false;
                    game.SendMessage("CompleteCombatRoom", SendMessageOptions.DontRequireReceiver);
                }
            }

            if (Time.unscaledTime < nextSave) return;
            nextSave = Time.unscaledTime + SaveInterval;
            SaveNow();
        }

        public void SaveNow()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            if (game == null || game.Player == null) return;
            var currentRoom = GameCatalog.GetRoom(RunPlanner.Generate(game.Seed)[game.RoomIndex]);
            var combatRoom = currentRoom.kind == RoomKind.Combat ||
                             currentRoom.kind == RoomKind.Elite ||
                             currentRoom.kind == RoomKind.Boss;
            if (combatRoom && !game.Player.CombatEnabled)
                return;
            if (!combatRoom)
            {
                var resumableChoice = currentRoom.kind == RoomKind.Treasure ||
                                      currentRoom.kind == RoomKind.Merchant;
                if (!resumableChoice || FindFirstObjectByType<InventoryView>() != null)
                    return;
            }

            var checkpoint = game.CaptureCheckpoint();
            if (checkpoint == null) return;
            checkpoint.enemies.Clear();
            var enemies = FindObjectsByType<EnemyController>(FindObjectsSortMode.None);
            for (var i = 0; i < enemies.Length; i++)
            {
                var enemy = enemies[i];
                if (enemy == null || enemy.IsDead || enemy.NetworkId <= 0) continue;
                checkpoint.enemies.Add(enemy.CreateSnapshot());
            }
            checkpoint.enemies.Sort((first, second) => first.networkId.CompareTo(second.networkId));
            RunCheckpointService.Save(checkpoint);
        }

        private void RestoreEncounterIfNeeded()
        {
            var checkpoint = RunCheckpointService.Load();
            if (checkpoint == null || game == null || game.Seed != checkpoint.seed ||
                game.RoomIndex != checkpoint.roomIndex || !game.Player.CombatEnabled)
                return;

            var room = GameCatalog.GetRoom(RunPlanner.Generate(game.Seed)[game.RoomIndex]);
            if (room.kind != RoomKind.Combat && room.kind != RoomKind.Elite && room.kind != RoomKind.Boss)
                return;

            if (!checkpoint.combatActive && checkpoint.enemies.Count == 0)
            {
                game.SendMessage("CompleteCombatRoom", SendMessageOptions.DontRequireReceiver);
                return;
            }

            var local = FindObjectsByType<EnemyController>(FindObjectsSortMode.None);
            var byId = new Dictionary<int, EnemyController>();
            for (var i = 0; i < local.Length; i++)
                if (local[i] != null && local[i].NetworkId > 0 && !byId.ContainsKey(local[i].NetworkId))
                    byId.Add(local[i].NetworkId, local[i]);

            var alive = new HashSet<int>();
            for (var i = 0; i < checkpoint.enemies.Count; i++)
            {
                var snapshot = checkpoint.enemies[i];
                if (snapshot == null || snapshot.networkId <= 0 || !alive.Add(snapshot.networkId)) continue;
                if (!byId.TryGetValue(snapshot.networkId, out var enemy)) continue;
                enemy.transform.position = new Vector3(snapshot.x, snapshot.y, snapshot.z);
                enemy.transform.rotation = Quaternion.Euler(0f, snapshot.yaw, 0f);
                var ratio = snapshot.maxHealth <= 0f
                    ? 1f
                    : Mathf.Clamp01(snapshot.health / snapshot.maxHealth);
                var restoredHealth = Mathf.Max(.1f, enemy.MaxHealth * ratio);
                var damage = Mathf.Max(0f, enemy.MaxHealth - restoredHealth);
                if (damage > 0f) enemy.TakeDamage(damage);
            }

            foreach (var pair in byId)
            {
                if (alive.Contains(pair.Key) || pair.Value == null) continue;
                Destroy(pair.Value.gameObject);
            }
            restoredEncounterActive = true;
        }

        private void OnApplicationPause(bool paused)
        {
            if (paused) SaveNow();
        }

        private void OnApplicationFocus(bool focused)
        {
            if (!focused) SaveNow();
        }

        private void OnApplicationQuit()
        {
            SaveNow();
        }
    }
}
