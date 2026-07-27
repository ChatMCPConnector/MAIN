using System;
using System.Globalization;
using UnityEngine;
using UnityEngine.UI;

namespace Riftbound
{
    public sealed class CoopReliableButtonMarker : MonoBehaviour { }

    public sealed class CoopProgressReliabilityRuntime : MonoBehaviour
    {
        private GameBootstrap game;
        private CoopReliableRuntime reliable;
        private int lastSeed = int.MinValue;
        private int lastRoom = -1;
        private float nextButtonScan;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopProgressReliabilityRuntime>() != null) return;
            var root = new GameObject("Coop Progress Reliability");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopProgressReliabilityRuntime>();
        }

        private void Update()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            HookReliable();
            if (game != null && CoopRuntimeState.Connected && CoopRuntimeState.Role == CoopRole.Host &&
                (game.Seed != lastSeed || game.RoomIndex != lastRoom))
            {
                lastSeed = game.Seed;
                lastRoom = game.RoomIndex;
                reliable?.SendCritical(
                    CoopCriticalKind.Advance,
                    string.Join(
                        ",",
                        lastSeed.ToString(CultureInfo.InvariantCulture),
                        lastRoom.ToString(CultureInfo.InvariantCulture)));
            }

            if (Time.unscaledTime >= nextButtonScan)
            {
                nextButtonScan = Time.unscaledTime + .5f;
                AttachReliableReviveButtons();
            }
        }

        private void HookReliable()
        {
            if (reliable == CoopReliableRuntime.Instance) return;
            if (reliable != null) reliable.Received -= HandleReliable;
            reliable = CoopReliableRuntime.Instance;
            if (reliable != null) reliable.Received += HandleReliable;
        }

        private void AttachReliableReviveButtons()
        {
            var buttons = FindObjectsByType<Button>(FindObjectsSortMode.None);
            for (var i = 0; i < buttons.Length; i++)
            {
                var button = buttons[i];
                if (button == null || button.GetComponent<CoopReliableButtonMarker>() != null) continue;
                var text = button.GetComponentInChildren<Text>();
                if (text == null || text.text != "PARTNER WIEDERBELEBEN") continue;
                button.gameObject.AddComponent<CoopReliableButtonMarker>();
                button.onClick.AddListener(() =>
                    CoopReliableRuntime.Instance?.SendCritical(CoopCriticalKind.Revive, "REVIVE"));
            }
        }

        private void HandleReliable(CoopCriticalEnvelope envelope)
        {
            if (envelope == null) return;
            if (envelope.kind == CoopCriticalKind.Revive && envelope.payload == "REVIVE")
            {
                CoopLanController.Instance?.SendMessage(
                    "HandleCommand",
                    "REVIVE",
                    SendMessageOptions.DontRequireReceiver);
                return;
            }

            if (envelope.kind != CoopCriticalKind.Advance ||
                CoopRuntimeState.Role != CoopRole.Client || game == null)
                return;
            var parts = (envelope.payload ?? string.Empty).Split(',');
            if (parts.Length != 2 ||
                !int.TryParse(parts[0], NumberStyles.Integer, CultureInfo.InvariantCulture, out var seed) ||
                !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out var room) ||
                room < 0 || room >= RunPlanner.RoomCount)
                return;

            if (game.Seed == seed && game.RoomIndex == room) return;
            if (game.Seed == seed && game.RoomIndex + 1 == room)
            {
                CoopLanController.Instance?.SendMessage(
                    "HandleCommand",
                    "ADVANCE",
                    SendMessageOptions.DontRequireReceiver);
                return;
            }
            game.SynchronizeToHost(seed, room);
        }

        private void OnDestroy()
        {
            if (reliable != null) reliable.Received -= HandleReliable;
        }
    }
}
