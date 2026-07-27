using System;
using UnityEngine;
using UnityEngine.UI;

namespace Riftbound
{
    public sealed class CoopView : MonoBehaviour
    {
        private CoopLanController controller;
        private RectTransform safeRoot;
        private RectTransform statusButton;
        private Text statusText;
        private GameObject overlay;
        private Font font;
        private float nextRefresh;

        public static CoopView Create(CoopLanController controller)
        {
            var root = new GameObject("Coop HUD");
            DontDestroyOnLoad(root);
            var view = root.AddComponent<CoopView>();
            view.controller = controller;
            view.Build();
            return view;
        }

        private void Build()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 80;
            gameObject.AddComponent<GraphicRaycaster>();

            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;

            safeRoot = CreateRect("SafeArea", transform, Vector2.zero, Vector2.one);
            safeRoot.gameObject.AddComponent<SafeAreaFitter>();

            statusButton = CreatePanel(
                "CoopButton",
                safeRoot,
                new Color(.08f, .14f, .23f, .92f),
                new Vector2(.03f, .775f),
                new Vector2(.25f, .835f));
            var button = statusButton.gameObject.AddComponent<Button>();
            button.targetGraphic = statusButton.GetComponent<Image>();
            button.onClick.AddListener(OpenOverlay);
            statusText = CreateText(
                "KOOP\nOFFLINE",
                statusButton,
                22,
                TextAnchor.MiddleCenter,
                new Vector2(.03f, .04f),
                new Vector2(.97f, .96f));
            RefreshSoon();
        }

        private void Update()
        {
            if (Time.unscaledTime < nextRefresh) return;
            nextRefresh = Time.unscaledTime + .45f;
            RefreshStatus();
            if (overlay != null) RefreshOverlay();
        }

        public void RefreshSoon()
        {
            nextRefresh = 0f;
        }

        private void RefreshStatus()
        {
            if (statusText == null || controller == null) return;
            statusText.text = controller.State switch
            {
                CoopConnectionState.Hosting => $"KOOP\nCODE {controller.SessionCode}",
                CoopConnectionState.Connecting => "KOOP\nVERBINDE",
                CoopConnectionState.Connected => "KOOP\n2 SPIELER",
                CoopConnectionState.Reconnecting => "KOOP\nNEUVERB.",
                CoopConnectionState.Rejected => "KOOP\nFEHLER",
                _ => controller.Sessions.Count > 0
                    ? $"KOOP\n{controller.Sessions.Count} GEFUNDEN"
                    : "KOOP\nOFFLINE"
            };

            statusButton.GetComponent<Image>().color = controller.Connected
                ? new Color(.08f, .40f, .32f, .94f)
                : controller.Role == CoopRole.Host
                    ? new Color(.34f, .20f, .06f, .94f)
                    : new Color(.08f, .14f, .23f, .92f);
        }

        private void OpenOverlay()
        {
            if (overlay != null) return;
            overlay = new GameObject("Coop Overlay", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(safeRoot, false);
            var rect = overlay.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            overlay.GetComponent<Image>().color = new Color(.02f, .025f, .055f, .97f);
            RefreshOverlay();
        }

        private void RefreshOverlay()
        {
            if (overlay == null || controller == null) return;
            var rect = overlay.GetComponent<RectTransform>();
            ClearChildren(rect);

            CreateText(
                HeaderText(),
                rect,
                40,
                TextAnchor.MiddleCenter,
                new Vector2(.06f, .75f),
                new Vector2(.94f, .94f));

            var body = CreateText(
                DetailText(),
                rect,
                25,
                TextAnchor.UpperCenter,
                new Vector2(.08f, .58f),
                new Vector2(.92f, .75f));
            body.verticalOverflow = VerticalWrapMode.Overflow;

            var labels = new string[7];
            var actions = new Action[7];
            var count = BuildActions(labels, actions);
            for (var i = 0; i < count; i++)
            {
                var top = .56f - i * .092f;
                var bottom = top - .074f;
                CreateButton(
                    labels[i],
                    rect,
                    new Vector2(.09f, bottom),
                    new Vector2(.91f, top),
                    actions[i]);
            }
        }

        private int BuildActions(string[] labels, Action[] actions)
        {
            var count = 0;
            if (controller.Role == CoopRole.Offline)
            {
                labels[count] = controller.GameSafe ? "HOST STARTEN" : "HOST NUR IM SICHEREN RAUM";
                actions[count++] = controller.StartHost;

                var shown = 0;
                for (var i = 0; i < controller.Sessions.Count && shown < 3; i++)
                {
                    var session = controller.Sessions[i];
                    if (!session.joinable) continue;
                    labels[count] = $"BEITRETEN · CODE {session.sessionCode}\n" +
                                    $"Raum {session.roomIndex + 1} · {session.address}";
                    actions[count++] = () => controller.Join(session);
                    shown++;
                }
            }
            else if (controller.Connected)
            {
                labels[count] = controller.LocalReady ? "BEREITSCHAFT ZURÜCKNEHMEN" : "BEREIT FÜR RAUMWECHSEL";
                actions[count++] = controller.SetLocalReadyFromMenu;

                if (controller.CanReviveRemote)
                {
                    labels[count] = "PARTNER WIEDERBELEBEN";
                    actions[count++] = controller.RevivePartner;
                }

                labels[count] = "VERBINDUNG TRENNEN";
                actions[count++] = controller.Disconnect;
            }
            else
            {
                labels[count] = controller.Role == CoopRole.Host
                    ? "HOST BEENDEN"
                    : "VERBINDUNG ABBRECHEN";
                actions[count++] = controller.Disconnect;
            }

            labels[count] = "SCHLIESSEN";
            actions[count++] = CloseOverlay;
            return count;
        }

        private string HeaderText()
        {
            return controller.State switch
            {
                CoopConnectionState.Hosting => $"LOKALER HOST · CODE {controller.SessionCode}",
                CoopConnectionState.Connecting => "LOKALE SITZUNG WIRD VERBUNDEN",
                CoopConnectionState.Connected => controller.Role == CoopRole.Host
                    ? $"KOOP VERBUNDEN · HOST {controller.SessionCode}"
                    : $"KOOP VERBUNDEN · CLIENT {controller.SessionCode}",
                CoopConnectionState.Reconnecting => "WIEDERVERBINDUNG LÄUFT",
                CoopConnectionState.Rejected => "VERBINDUNG ABGELEHNT",
                _ => "LOKALER ZWEI-SPIELER-KOOP"
            };
        }

        private string DetailText()
        {
            if (controller.Connected)
            {
                var peer = controller.RemoteState;
                var health = peer == null || peer.maxHealth <= 0f
                    ? "Partnerstatus wird geladen"
                    : $"Partner: {Mathf.CeilToInt(peer.health)} / {Mathf.CeilToInt(peer.maxHealth)} HP";
                var ready = $"Bereit: Du {(controller.LocalReady ? "JA" : "NEIN")} · " +
                            $"Partner {(controller.RemoteReady ? "JA" : "NEIN")}";
                var downed = controller.RemoteDowned ? "\nPartner ist gefallen." : string.Empty;
                return $"{health}\n{ready}{downed}\nLAN/Hotspot · kein externer Server";
            }

            if (controller.Role == CoopRole.Host)
                return $"Adresse: {controller.LocalAddress}\n" +
                       $"Code: {controller.SessionCode}\n" +
                       "Beitritt ist nur in sicheren Räumen möglich.";

            if (controller.State == CoopConnectionState.Reconnecting)
                return "Die letzte lokale Sitzung wird automatisch erneut kontaktiert.";

            var found = controller.Sessions.Count;
            return found == 0
                ? "Keine Sitzung entdeckt. Beide Geräte müssen im selben WLAN oder Hotspot sein."
                : $"{found} lokale Sitzung{(found == 1 ? string.Empty : "en")} entdeckt.";
        }

        private void CloseOverlay()
        {
            if (overlay == null) return;
            Destroy(overlay);
            overlay = null;
        }

        private void CreateButton(
            string label,
            Transform parent,
            Vector2 min,
            Vector2 max,
            Action action)
        {
            var panel = CreatePanel(
                "CoopAction",
                parent,
                new Color(.12f, .19f, .30f, 1f),
                min,
                max);
            var button = panel.gameObject.AddComponent<Button>();
            button.targetGraphic = panel.GetComponent<Image>();
            button.interactable = action != null;
            if (action != null) button.onClick.AddListener(() => action());
            CreateText(
                label,
                panel,
                27,
                TextAnchor.MiddleCenter,
                new Vector2(.03f, .06f),
                new Vector2(.97f, .94f));
        }

        private static void ClearChildren(Transform parent)
        {
            while (parent.childCount > 0)
            {
                var child = parent.GetChild(0);
                child.SetParent(null, false);
                Destroy(child.gameObject);
            }
        }

        private RectTransform CreatePanel(
            string name,
            Transform parent,
            Color color,
            Vector2 min,
            Vector2 max)
        {
            var rect = CreateRect(name, parent, min, max);
            rect.gameObject.AddComponent<Image>().color = color;
            return rect;
        }

        private Text CreateText(
            string value,
            Transform parent,
            int size,
            TextAnchor alignment,
            Vector2 min,
            Vector2 max)
        {
            var rect = CreateRect("Text", parent, min, max);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = alignment;
            text.color = Color.white;
            text.text = value;
            text.supportRichText = true;
            text.resizeTextForBestFit = true;
            text.resizeTextMinSize = 16;
            text.resizeTextMaxSize = size;
            return text;
        }

        private static RectTransform CreateRect(
            string name,
            Transform parent,
            Vector2 min,
            Vector2 max)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            return rect;
        }
    }
}