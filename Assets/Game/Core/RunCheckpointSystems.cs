using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;

namespace Riftbound
{
    [Serializable]
    public sealed class RunCheckpointData
    {
        public int version = 1;
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
    }

    public static class RunCheckpointService
    {
        public const int CurrentVersion = 1;
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
                data.items == null || data.cardIndexes == null ||
                data.savedUtcTicks <= 0)
                return false;

            var saved = new DateTime(data.savedUtcTicks, DateTimeKind.Utc);
            var age = utcNow - saved;
            return age >= TimeSpan.Zero && age <= MaximumAge;
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
            if (Time.unscaledTime < nextSave) return;
            nextSave = Time.unscaledTime + SaveInterval;
            SaveNow();
        }

        public void SaveNow()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            var checkpoint = game?.CaptureCheckpoint();
            if (checkpoint != null) RunCheckpointService.Save(checkpoint);
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
