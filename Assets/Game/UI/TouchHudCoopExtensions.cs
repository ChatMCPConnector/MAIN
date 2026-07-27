using System.Collections.Generic;
using UnityEngine;
using UnityEngine.UI;

namespace Riftbound
{
    public static class TouchHudCoopExtensions
    {
        private static readonly Dictionary<int, GameObject> Waiting = new Dictionary<int, GameObject>();

        public static void ShowWaiting(this TouchHud hud, string title, string body)
        {
            if (hud == null) return;
            hud.CloseOverlayNow();
            var root = new GameObject("Coop Waiting Overlay");
            Object.DontDestroyOnLoad(root);
            var canvas = root.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 75;
            root.AddComponent<GraphicRaycaster>();
            var scaler = root.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;

            var safe = CreateRect("SafeArea", root.transform, Vector2.zero, Vector2.one);
            safe.gameObject.AddComponent<SafeAreaFitter>();
            var background = safe.gameObject.AddComponent<Image>();
            background.color = new Color(.018f, .025f, .055f, .97f);
            var font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            CreateText(title, safe, font, 44, new Vector2(.08f, .60f), new Vector2(.92f, .78f));
            CreateText(body + "\n\nDie Auswahl wird zuverlässig synchronisiert.", safe, font, 29,
                new Vector2(.10f, .36f), new Vector2(.90f, .60f));
            CreateText("VERBUNDEN · BITTE WARTEN", safe, font, 25,
                new Vector2(.16f, .25f), new Vector2(.84f, .33f));
            Waiting[hud.GetInstanceID()] = root;
        }

        public static void CloseOverlayNow(this TouchHud hud)
        {
            if (hud == null) return;
            var key = hud.GetInstanceID();
            if (!Waiting.TryGetValue(key, out var root)) return;
            Waiting.Remove(key);
            if (root != null) Object.Destroy(root);
        }

        private static void CreateText(
            string value,
            Transform parent,
            Font font,
            int size,
            Vector2 min,
            Vector2 max)
        {
            var rect = CreateRect("Text", parent, min, max);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.text = value;
            text.resizeTextForBestFit = true;
            text.resizeTextMinSize = 18;
            text.resizeTextMaxSize = size;
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
