using System;
using System.Collections.Generic;
using System.Globalization;
using UnityEngine;

namespace Riftbound
{
    public enum CoopHazardKind { Laser, Pulse }
    public enum CoopHazardPhase { Spawn, Warning, Active, Inactive, Clear }

    public readonly struct CoopHazardEvent
    {
        public readonly int seed;
        public readonly int roomIndex;
        public readonly int hazardId;
        public readonly CoopHazardKind kind;
        public readonly CoopHazardPhase phase;
        public readonly Vector3 position;
        public readonly float yaw;
        public readonly float radius;
        public readonly float damage;

        public CoopHazardEvent(
            int seed,
            int roomIndex,
            int hazardId,
            CoopHazardKind kind,
            CoopHazardPhase phase,
            Vector3 position,
            float yaw,
            float radius,
            float damage)
        {
            this.seed = seed;
            this.roomIndex = roomIndex;
            this.hazardId = hazardId;
            this.kind = kind;
            this.phase = phase;
            this.position = position;
            this.yaw = yaw;
            this.radius = radius;
            this.damage = damage;
        }
    }

    public static class CoopHazardCodec
    {
        private const string Marker = "HZ";

        public static string Encode(CoopHazardEvent value) => string.Join(
            ",",
            Marker,
            value.seed.ToString(CultureInfo.InvariantCulture),
            value.roomIndex.ToString(CultureInfo.InvariantCulture),
            value.hazardId.ToString(CultureInfo.InvariantCulture),
            ((int)value.kind).ToString(CultureInfo.InvariantCulture),
            ((int)value.phase).ToString(CultureInfo.InvariantCulture),
            Float(value.position.x),
            Float(value.position.y),
            Float(value.position.z),
            Float(value.yaw),
            Float(value.radius),
            Float(value.damage));

        public static bool TryDecode(string payload, out CoopHazardEvent value)
        {
            value = default;
            var parts = (payload ?? string.Empty).Split(',');
            if (parts.Length != 12 || parts[0] != Marker ||
                !TryInt(parts[1], out var seed) ||
                !TryInt(parts[2], out var room) || room < 0 || room >= RunPlanner.RoomCount ||
                !TryInt(parts[3], out var id) || id <= 0 ||
                !TryInt(parts[4], out var kind) || kind < 0 || kind > (int)CoopHazardKind.Pulse ||
                !TryInt(parts[5], out var phase) || phase < 0 || phase > (int)CoopHazardPhase.Clear ||
                !TryFloat(parts[6], out var x) ||
                !TryFloat(parts[7], out var y) ||
                !TryFloat(parts[8], out var z) ||
                !TryFloat(parts[9], out var yaw) ||
                !TryFloat(parts[10], out var radius) || radius <= 0f || radius > 8f ||
                !TryFloat(parts[11], out var damage) || damage <= 0f || damage > 500f)
                return false;
            value = new CoopHazardEvent(
                seed,
                room,
                id,
                (CoopHazardKind)kind,
                (CoopHazardPhase)phase,
                new Vector3(x, y, z),
                yaw,
                radius,
                damage);
            return true;
        }

        private static string Float(float value) =>
            value.ToString("0.###", CultureInfo.InvariantCulture);
        private static bool TryInt(string value, out int result) =>
            int.TryParse(value, NumberStyles.Integer, CultureInfo.InvariantCulture, out result);
        private static bool TryFloat(string value, out float result) =>
            float.TryParse(value, NumberStyles.Float, CultureInfo.InvariantCulture, out result) &&
            !float.IsNaN(result) && !float.IsInfinity(result);
    }

    public static class CoopHazardMath
    {
        public static float DistanceToSegmentXZ(Vector3 point, Vector3 start, Vector3 end)
        {
            point.y = start.y = end.y = 0f;
            var segment = end - start;
            var lengthSquared = segment.sqrMagnitude;
            if (lengthSquared <= .0001f) return Vector3.Distance(point, start);
            var t = Mathf.Clamp01(Vector3.Dot(point - start, segment) / lengthSquared);
            return Vector3.Distance(point, start + segment * t);
        }

        public static bool Hits(
            CoopHazardKind kind,
            Vector3 hazardPosition,
            float yaw,
            float radius,
            Vector3 playerPosition)
        {
            if (kind == CoopHazardKind.Pulse)
            {
                var delta = playerPosition - hazardPosition;
                delta.y = 0f;
                return delta.sqrMagnitude <= radius * radius;
            }

            var direction = Quaternion.Euler(0f, yaw, 0f) * Vector3.forward;
            var half = Mathf.Max(1f, radius);
            return DistanceToSegmentXZ(
                       playerPosition,
                       hazardPosition - direction * half,
                       hazardPosition + direction * half) <= .42f;
        }
    }

    public static class CoopHazardPlanner
    {
        public static CoopHazardEvent[] Create(int seed, int roomIndex)
        {
            var rng = new System.Random(unchecked(seed * 397 ^ roomIndex * 7919));
            var count = roomIndex >= 6 ? 2 : 1;
            var result = new CoopHazardEvent[count];
            for (var i = 0; i < count; i++)
            {
                var kind = (i + roomIndex) % 2 == 0 ? CoopHazardKind.Laser : CoopHazardKind.Pulse;
                var x = (float)(rng.NextDouble() * 5.6d - 2.8d);
                var z = (float)(rng.NextDouble() * 4.8d - .8d);
                var yaw = rng.Next(0, 8) * 22.5f;
                var radius = kind == CoopHazardKind.Laser ? 4.5f : 1.35f + roomIndex * .06f;
                var damage = 8f + roomIndex * 1.4f;
                result[i] = new CoopHazardEvent(
                    seed,
                    roomIndex,
                    roomIndex * 10 + i + 1,
                    kind,
                    CoopHazardPhase.Spawn,
                    new Vector3(x, kind == CoopHazardKind.Laser ? .12f : .05f, z),
                    yaw,
                    radius,
                    damage);
            }
            return result;
        }
    }

    public sealed class CoopHazardRuntime : MonoBehaviour
    {
        private sealed class HazardState
        {
            public CoopHazardEvent definition;
            public CoopHazardPhase phase;
            public float nextTransition;
            public int activation;
            public GameObject visual;
            public bool localHit;
            public bool remoteHit;
        }

        private readonly Dictionary<int, HazardState> hazards = new Dictionary<int, HazardState>();
        private GameBootstrap game;
        private CoopReliableRuntime reliable;
        private int activeSeed = int.MinValue;
        private int activeRoom = -1;
        private float nextResend;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopHazardRuntime>() != null) return;
            var root = new GameObject("Coop Hazard Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopHazardRuntime>();
        }

        private void Update()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            HookReliable();
            if (game == null) return;

            var authoritative = !CoopRuntimeState.Connected || CoopRuntimeState.Role == CoopRole.Host;
            if (!game.Player.CombatEnabled)
            {
                if (hazards.Count > 0) ClearHazards(authoritative);
                return;
            }

            if (authoritative && (game.Seed != activeSeed || game.RoomIndex != activeRoom))
                BeginRoom();

            if (authoritative)
            {
                TickAuthoritative();
                if (CoopRuntimeState.Connected && Time.unscaledTime >= nextResend)
                {
                    nextResend = Time.unscaledTime + 2f;
                    foreach (var state in hazards.Values) Publish(state);
                }
            }
        }

        private void HookReliable()
        {
            if (reliable == CoopReliableRuntime.Instance) return;
            if (reliable != null) reliable.Received -= HandleReliable;
            reliable = CoopReliableRuntime.Instance;
            if (reliable != null) reliable.Received += HandleReliable;
        }

        private void BeginRoom()
        {
            ClearHazards(false);
            activeSeed = game.Seed;
            activeRoom = game.RoomIndex;
            var definitions = CoopHazardPlanner.Create(activeSeed, activeRoom);
            for (var i = 0; i < definitions.Length; i++)
            {
                var state = new HazardState
                {
                    definition = definitions[i],
                    phase = CoopHazardPhase.Spawn,
                    nextTransition = Time.unscaledTime + 1.2f + i * .4f
                };
                state.visual = CreateVisual(state.definition);
                hazards[state.definition.hazardId] = state;
                UpdateVisual(state);
                Publish(state);
            }
        }

        private void TickAuthoritative()
        {
            foreach (var state in hazards.Values)
            {
                if (Time.unscaledTime >= state.nextTransition)
                {
                    switch (state.phase)
                    {
                        case CoopHazardPhase.Spawn:
                        case CoopHazardPhase.Inactive:
                            state.phase = CoopHazardPhase.Warning;
                            state.nextTransition = Time.unscaledTime + .85f;
                            break;
                        case CoopHazardPhase.Warning:
                            state.phase = CoopHazardPhase.Active;
                            state.nextTransition = Time.unscaledTime + .55f;
                            state.activation++;
                            state.localHit = state.remoteHit = false;
                            break;
                        default:
                            state.phase = CoopHazardPhase.Inactive;
                            state.nextTransition = Time.unscaledTime + 2.1f;
                            break;
                    }
                    UpdateVisual(state);
                    Publish(state);
                }

                if (state.phase == CoopHazardPhase.Active) ApplyDamage(state);
            }
        }

        private void ApplyDamage(HazardState state)
        {
            var local = game.Player;
            if (!state.localHit && local != null && local.Health > 0f &&
                CoopHazardMath.Hits(
                    state.definition.kind,
                    state.definition.position,
                    state.definition.yaw,
                    state.definition.radius,
                    local.transform.position))
            {
                state.localHit = true;
                local.TakeDamage(state.definition.damage);
            }

            if (state.remoteHit || !CoopRuntimeState.Connected || CoopRuntimeState.Role != CoopRole.Host)
                return;
            var peer = CoopLanController.Instance?.RemoteState;
            if (peer == null || peer.health <= 0f || peer.downed) return;
            var remote = new Vector3(peer.x, peer.y, peer.z);
            if (!CoopHazardMath.Hits(
                    state.definition.kind,
                    state.definition.position,
                    state.definition.yaw,
                    state.definition.radius,
                    remote))
                return;
            state.remoteHit = CoopCombatReplicator.Instance != null &&
                              CoopCombatReplicator.Instance.TryDamageRemote(
                                  state.definition.damage,
                                  CoopDamageKind.Hazard);
        }

        private void Publish(HazardState state)
        {
            if (!CoopRuntimeState.Connected || CoopRuntimeState.Role != CoopRole.Host || reliable == null)
                return;
            var value = new CoopHazardEvent(
                state.definition.seed,
                state.definition.roomIndex,
                state.definition.hazardId,
                state.definition.kind,
                state.phase,
                state.definition.position,
                state.definition.yaw,
                state.definition.radius,
                state.definition.damage);
            reliable.SendCritical(CoopCriticalKind.Decision, CoopHazardCodec.Encode(value));
        }

        private void HandleReliable(CoopCriticalEnvelope envelope)
        {
            if (envelope == null || envelope.kind != CoopCriticalKind.Decision ||
                CoopRuntimeState.Role != CoopRole.Client ||
                !CoopHazardCodec.TryDecode(envelope.payload, out var value) ||
                game == null || value.seed != game.Seed || value.roomIndex != game.RoomIndex)
                return;

            if (value.phase == CoopHazardPhase.Clear)
            {
                ClearHazards(false);
                return;
            }

            if (!hazards.TryGetValue(value.hazardId, out var state))
            {
                state = new HazardState { definition = value };
                state.visual = CreateVisual(value);
                hazards[value.hazardId] = state;
            }
            state.definition = value;
            state.phase = value.phase;
            activeSeed = value.seed;
            activeRoom = value.roomIndex;
            UpdateVisual(state);
        }

        private static GameObject CreateVisual(CoopHazardEvent value)
        {
            var primitive = value.kind == CoopHazardKind.Laser
                ? PrimitiveType.Cube
                : PrimitiveType.Cylinder;
            var go = GameObject.CreatePrimitive(primitive);
            go.name = $"CoopHazard-{value.hazardId}";
            var collider = go.GetComponent<Collider>();
            if (collider != null) collider.enabled = false;
            return go;
        }

        private static void UpdateVisual(HazardState state)
        {
            if (state.visual == null) return;
            state.visual.transform.position = state.definition.position;
            state.visual.transform.rotation = Quaternion.Euler(0f, state.definition.yaw, 0f);
            state.visual.transform.localScale = state.definition.kind == CoopHazardKind.Laser
                ? new Vector3(.22f, .10f, state.definition.radius * 2f)
                : new Vector3(state.definition.radius * 2f, .05f, state.definition.radius * 2f);
            var color = state.phase switch
            {
                CoopHazardPhase.Warning => new Color(1f, .65f, .05f, .8f),
                CoopHazardPhase.Active => new Color(1f, .05f, .08f, .95f),
                _ => new Color(.3f, .12f, .12f, .35f)
            };
            var renderer = state.visual.GetComponent<Renderer>();
            if (renderer != null) renderer.sharedMaterial = WorldFactory.GetUnlitMaterial(color);
            state.visual.SetActive(state.phase != CoopHazardPhase.Clear);
        }

        private void ClearHazards(bool publish)
        {
            if (publish && CoopRuntimeState.Connected && CoopRuntimeState.Role == CoopRole.Host && reliable != null &&
                activeSeed != int.MinValue && activeRoom >= 0)
            {
                reliable.SendCritical(
                    CoopCriticalKind.Decision,
                    CoopHazardCodec.Encode(new CoopHazardEvent(
                        activeSeed,
                        activeRoom,
                        1,
                        CoopHazardKind.Laser,
                        CoopHazardPhase.Clear,
                        Vector3.zero,
                        0f,
                        1f,
                        1f)));
            }
            foreach (var state in hazards.Values)
                if (state.visual != null) Destroy(state.visual);
            hazards.Clear();
            activeSeed = int.MinValue;
            activeRoom = -1;
        }

        private void OnDestroy()
        {
            if (reliable != null) reliable.Received -= HandleReliable;
            ClearHazards(false);
        }
    }
}
