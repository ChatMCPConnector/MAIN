using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Riftbound
{
    public enum CoopDecisionType
    {
        Card,
        Treasure,
        MerchantBuy,
        MerchantLeave
    }

    public readonly struct CoopDecision
    {
        public readonly int seed;
        public readonly int roomIndex;
        public readonly CoopDecisionType type;
        public readonly int optionIndex;
        public readonly int hostGold;

        public CoopDecision(int seed, int roomIndex, CoopDecisionType type, int optionIndex, int hostGold)
        {
            this.seed = seed;
            this.roomIndex = roomIndex;
            this.type = type;
            this.optionIndex = optionIndex;
            this.hostGold = hostGold;
        }

        public string Key => $"{seed}:{roomIndex}:{(int)type}";
    }

    public sealed class CoopTransactionLedger
    {
        private readonly HashSet<string> applied = new HashSet<string>(StringComparer.Ordinal);

        public bool TryApply(string transactionKey)
        {
            return !string.IsNullOrWhiteSpace(transactionKey) && applied.Add(transactionKey);
        }

        public bool Contains(string transactionKey) =>
            !string.IsNullOrWhiteSpace(transactionKey) && applied.Contains(transactionKey);

        public void Reset() => applied.Clear();
    }

    public static class CoopDecisionCodec
    {
        public static string Encode(CoopDecision value) => string.Join(
            ",",
            value.seed.ToString(CultureInfo.InvariantCulture),
            value.roomIndex.ToString(CultureInfo.InvariantCulture),
            ((int)value.type).ToString(CultureInfo.InvariantCulture),
            value.optionIndex.ToString(CultureInfo.InvariantCulture),
            value.hostGold.ToString(CultureInfo.InvariantCulture));

        public static bool TryDecode(string payload, out CoopDecision value)
        {
            value = default;
            var parts = (payload ?? string.Empty).Split(',');
            if (parts.Length != 5 ||
                !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var seed) ||
                !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out var room) ||
                room < 0 || room >= RunPlanner.RoomCount ||
                !int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out var type) ||
                type < 0 || type > (int)CoopDecisionType.MerchantLeave ||
                !int.TryParse(parts[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out var option) ||
                option < -1 || option > 16 ||
                !int.TryParse(parts[4], NumberStyles.Integer, CultureInfo.InvariantCulture, out var gold) ||
                gold < 0)
                return false;
            value = new CoopDecision(seed, room, (CoopDecisionType)type, option, gold);
            return true;
        }

        public static string EncodeEconomy(int seed, int roomIndex, int gold, long revision) =>
            string.Join(
                ",",
                seed.ToString(CultureInfo.InvariantCulture),
                roomIndex.ToString(CultureInfo.InvariantCulture),
                Math.Max(0, gold).ToString(CultureInfo.InvariantCulture),
                Math.Max(1L, revision).ToString(CultureInfo.InvariantCulture));

        public static bool TryDecodeEconomy(
            string payload,
            out int seed,
            out int roomIndex,
            out int gold,
            out long revision)
        {
            seed = roomIndex = gold = 0;
            revision = 0;
            var parts = (payload ?? string.Empty).Split(',');
            return parts.Length == 4 &&
                   int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out seed) &&
                   int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out roomIndex) &&
                   roomIndex >= 0 && roomIndex < RunPlanner.RoomCount &&
                   int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out gold) && gold >= 0 &&
                   long.TryParse(parts[3], NumberStyles.Integer, CultureInfo.InvariantCulture, out revision) &&
                   revision > 0;
        }
    }

    public sealed class CoopDecisionRuntime : MonoBehaviour
    {
        private readonly Dictionary<string, Action<CoopDecision>> waiters =
            new Dictionary<string, Action<CoopDecision>>(StringComparer.Ordinal);
        private readonly Dictionary<string, CoopDecision> buffered =
            new Dictionary<string, CoopDecision>(StringComparer.Ordinal);
        private readonly CoopTransactionLedger ledger = new CoopTransactionLedger();
        private CoopReliableRuntime reliable;
        private long economyRevision;
        private long lastEconomyRevision;

        public static CoopDecisionRuntime Instance { get; private set; }
        public event Action<int, int, int> HostEconomyReceived;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopDecisionRuntime>() != null) return;
            var root = new GameObject("Coop Decision Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopDecisionRuntime>();
        }

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
        }

        private void Update()
        {
            if (reliable == CoopReliableRuntime.Instance) return;
            if (reliable != null) reliable.Received -= HandleReliable;
            reliable = CoopReliableRuntime.Instance;
            if (reliable != null) reliable.Received += HandleReliable;
        }

        public void ResetRun()
        {
            waiters.Clear();
            buffered.Clear();
            ledger.Reset();
            economyRevision = 0;
            lastEconomyRevision = 0;
        }

        public bool Publish(CoopDecision decision)
        {
            if (!CoopRuntimeState.Connected || CoopRuntimeState.Role != CoopRole.Host || reliable == null)
                return false;
            var key = decision.Key;
            if (!ledger.TryApply(key)) return false;
            reliable.SendCritical(CoopCriticalKind.Decision, CoopDecisionCodec.Encode(decision));
            return true;
        }

        public void WaitFor(
            int seed,
            int roomIndex,
            CoopDecisionType type,
            Action<CoopDecision> callback)
        {
            var key = $"{seed}:{roomIndex}:{(int)type}";
            if (buffered.TryGetValue(key, out var decision))
            {
                buffered.Remove(key);
                if (ledger.TryApply(key)) callback?.Invoke(decision);
                return;
            }
            waiters[key] = callback;
        }

        public void PublishEconomy(int seed, int roomIndex, int gold)
        {
            if (!CoopRuntimeState.Connected || CoopRuntimeState.Role != CoopRole.Host || reliable == null)
                return;
            economyRevision++;
            reliable.SendCritical(
                CoopCriticalKind.Economy,
                CoopDecisionCodec.EncodeEconomy(seed, roomIndex, gold, economyRevision));
        }

        private void HandleReliable(CoopCriticalEnvelope envelope)
        {
            if (envelope == null) return;
            if (envelope.kind == CoopCriticalKind.Decision &&
                CoopDecisionCodec.TryDecode(envelope.payload, out var decision))
            {
                var key = decision.Key;
                if (ledger.Contains(key)) return;
                if (waiters.TryGetValue(key, out var callback))
                {
                    waiters.Remove(key);
                    if (ledger.TryApply(key)) callback?.Invoke(decision);
                }
                else
                {
                    buffered[key] = decision;
                }
                return;
            }

            if (envelope.kind == CoopCriticalKind.Economy &&
                CoopDecisionCodec.TryDecodeEconomy(
                    envelope.payload,
                    out var seed,
                    out var room,
                    out var gold,
                    out var revision) &&
                revision > lastEconomyRevision)
            {
                lastEconomyRevision = revision;
                HostEconomyReceived?.Invoke(seed, room, gold);
            }
        }

        private void OnDestroy()
        {
            if (reliable != null) reliable.Received -= HandleReliable;
            if (Instance == this) Instance = null;
        }
    }
}
