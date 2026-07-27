using System;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;

namespace Riftbound
{
    public sealed class TouchHud : MonoBehaviour
    {
        private GameBootstrap game;
        private RectTransform safeRoot;
        private Text healthText;
        private Text roomText;
        private Text goldText;
        private Text equipmentText;
        private Text messageText;
        private Image healthFill;
        private GameObject overlay;
        private float messageUntil;
        private Font font;

        public static TouchHud Create(GameBootstrap bootstrap)
        {
            var root = new GameObject("Touch HUD");
            DontDestroyOnLoad(root);
            var hud = root.AddComponent<TouchHud>();
            hud.game = bootstrap;
            hud.Build();
            return hud;
        }

        private void Build()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            gameObject.AddComponent<GraphicRaycaster>();

            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;

            safeRoot = CreateRect("SafeArea", transform, Vector2.zero, Vector2.one);
            safeRoot.gameObject.AddComponent<SafeAreaFitter>();

            var top = CreatePanel(
                "Top",
                safeRoot,
                new Color(0f, 0f, 0f, .38f),
                new Vector2(.03f, .85f),
                new Vector2(.97f, .985f));

            healthText = CreateText(
                "HP 100 / 100",
                top,
                31,
                TextAnchor.MiddleLeft,
                new Vector2(.04f, .58f),
                new Vector2(.58f, .96f));

            roomText = CreateText(
                "Raum",
                top,
                25,
                TextAnchor.MiddleRight,
                new Vector2(.43f, .58f),
                new Vector2(.96f, .96f));

            goldText = CreateText(
                "Gold 0",
                top,
                24,
                TextAnchor.MiddleLeft,
                new Vector2(.04f, .36f),
                new Vector2(.34f, .58f));

            equipmentText = CreateText(
                "Eisenklinge · Keine Rüstung",
                top,
                22,
                TextAnchor.MiddleRight,
                new Vector2(.30f, .36f),
                new Vector2(.96f, .58f));

            var healthBack = CreatePanel(
                "HealthBack",
                top,
                new Color(.08f, .08f, .1f, .9f),
                new Vector2(.04f, .10f),
                new Vector2(.96f, .31f));

            healthFill = CreateImage(
                "HealthFill",
                healthBack,
                new Color(.1f, .85f, .55f, 1f),
                Vector2.zero,
                Vector2.one);
            healthFill.type = Image.Type.Filled;
            healthFill.fillMethod = Image.FillMethod.Horizontal;

            messageText = CreateText(
                "",
                safeRoot,
                42,
                TextAnchor.MiddleCenter,
                new Vector2(.08f, .68f),
                new Vector2(.92f, .81f));

            var stickBase = CreatePanel(
                "MoveBase",
                safeRoot,
                new Color(.1f, .2f, .3f, .45f),
                new Vector2(.04f, .04f),
                new Vector2(.36f, .23f));

            var stick = stickBase.gameObject.AddComponent<VirtualStick>();
            stick.target = game.Player;
            var knob = CreatePanel(
                "Knob",
                stickBase,
                new Color(.2f, .85f, 1f, .72f),
                new Vector2(.31f, .31f),
                new Vector2(.69f, .69f));
            stick.knob = knob;

            CreateActionButton(
                "ANGRIFF",
                new Vector2(.66f, .04f),
                new Vector2(.96f, .16f),
                game.Player.Attack);

            CreateActionButton(
                "DASH",
                new Vector2(.52f, .17f),
                new Vector2(.73f, .27f),
                game.Player.Dash);

            CreateActionButton(
                "FÄHIGKEIT",
                new Vector2(.75f, .18f),
                new Vector2(.96f, .30f),
                game.Player.Ability);
        }

        private void Update()
        {
            if (messageText != null && Time.unscaledTime >= messageUntil)
                messageText.text = "";
        }

        public void SetHealth(float current, float max)
        {
            if (healthText == null) return;
            healthText.text = $"HP {Mathf.CeilToInt(current)} / {Mathf.CeilToInt(max)}";
            healthFill.fillAmount = max <= 0f ? 0f : current / max;
        }

        public void SetRoom(int current, int total, string roomName, int seed)
        {
            if (roomText == null) return;
            roomText.text = $"{current}/{total}  {roomName}\nSeed {seed}";
        }

        public void SetGold(int gold)
        {
            if (goldText != null) goldText.text = $"Gold {gold}";
        }

        public void SetEquipment(string weapon, string armor)
        {
            if (equipmentText != null)
                equipmentText.text = $"{weapon} · {armor}";
        }

        public void ShowMessage(string text, float seconds)
        {
            messageText.text = text;
            messageUntil = Time.unscaledTime + seconds;
        }

        public void ShowRewards(CardDefinition[] cards, Action<CardDefinition> selected)
        {
            ShowOverlay(
                "WÄHLE EINE KARTE",
                cards.Length,
                i =>
                {
                    selected(cards[i]);
                    CloseOverlay();
                },
                i => $"{cards[i].title}\n\n" +
                     $"<color=#6CFFB4>{cards[i].benefit}</color>\n" +
                     $"<color=#FF718C>{cards[i].drawback}</color>");
        }

        public void ShowTreasure(ShopOffer[] offers, Action<ShopOffer> selected)
        {
            ShowOverlay(
                "SCHATZKAMMER\nWähle einen Gegenstand",
                offers.Length,
                i =>
                {
                    selected(offers[i]);
                    CloseOverlay();
                },
                i => $"{offers[i].title}\n\n{offers[i].description}");
        }

        public void ShowMerchant(
            ShopOffer[] offers,
            int gold,
            Func<ShopOffer, bool> purchase,
            Action leave)
        {
            ShowOverlay(
                $"RISSHÄNDLER\nGold: {gold}",
                offers.Length + 1,
                i =>
                {
                    if (i == offers.Length)
                    {
                        leave();
                        CloseOverlay();
                        return;
                    }

                    if (purchase(offers[i]))
                    {
                        CloseOverlay();
                    }
                    else
                    {
                        ShowMessage("ZU WENIG GOLD", 1.2f);
                    }
                },
                i => i == offers.Length
                    ? "WEITER OHNE KAUF"
                    : $"{offers[i].title} · {offers[i].price} Gold\n{offers[i].description}");
        }

        public void ShowContinue(string title, string body, Action continueAction)
        {
            ShowOverlay(
                title,
                1,
                _ =>
                {
                    continueAction();
                    CloseOverlay();
                },
                _ => $"{body}\n\nWEITER");
        }

        public void ShowRunComplete(int completedRuns, int gold, Action restart)
        {
            ShowOverlay(
                $"RUN ABGESCHLOSSEN\nSiege: {completedRuns}\nGold: {gold}",
                1,
                _ =>
                {
                    restart();
                    CloseOverlay();
                },
                _ => "NEUER RUN");
        }

        public void ShowGameOver(int room, int seed, int gold, Action restart)
        {
            ShowOverlay(
                $"RUN BEENDET\nRaum {room} · Seed {seed}\nGold: {gold}",
                1,
                _ =>
                {
                    restart();
                    CloseOverlay();
                },
                _ => "ERNEUT VERSUCHEN");
        }

        private void ShowOverlay(
            string title,
            int buttonCount,
            Action<int> clicked,
            Func<int, string> label)
        {
            CloseOverlay();

            overlay = new GameObject("Overlay", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(safeRoot, false);
            var rect = overlay.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            overlay.GetComponent<Image>().color = new Color(.025f, .03f, .07f, .95f);

            CreateText(
                title,
                rect,
                43,
                TextAnchor.MiddleCenter,
                new Vector2(.06f, .73f),
                new Vector2(.94f, .93f));

            for (var i = 0; i < buttonCount; i++)
            {
                var index = i;
                var height = buttonCount >= 4 ? .125f : buttonCount == 1 ? .18f : .16f;
                var gap = .025f;
                var top = .68f - i * (height + gap);
                var bottom = top - height;

                var button = CreatePanel(
                    $"OverlayButton{i}",
                    rect,
                    new Color(.12f, .18f, .28f, 1f),
                    new Vector2(.08f, bottom),
                    new Vector2(.92f, top));

                var uiButton = button.gameObject.AddComponent<Button>();
                uiButton.targetGraphic = button.GetComponent<Image>();
                uiButton.onClick.AddListener(() => clicked(index));

                CreateText(
                    label(i),
                    button,
                    buttonCount == 1 ? 34 : 28,
                    TextAnchor.MiddleCenter,
                    new Vector2(.04f, .06f),
                    new Vector2(.96f, .94f));
            }
        }

        private void CloseOverlay()
        {
            if (overlay == null) return;
            Destroy(overlay);
            overlay = null;
        }

        private void CreateActionButton(
            string text,
            Vector2 min,
            Vector2 max,
            UnityEngine.Events.UnityAction action)
        {
            var panel = CreatePanel(
                text,
                safeRoot,
                new Color(.13f, .2f, .34f, .82f),
                min,
                max);

            var button = panel.gameObject.AddComponent<Button>();
            button.targetGraphic = panel.GetComponent<Image>();
            button.onClick.AddListener(action);
            CreateText(text, panel, 28, TextAnchor.MiddleCenter, Vector2.zero, Vector2.one);
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

        private Image CreateImage(
            string name,
            Transform parent,
            Color color,
            Vector2 min,
            Vector2 max)
        {
            var rect = CreateRect(name, parent, min, max);
            var image = rect.gameObject.AddComponent<Image>();
            image.color = color;
            return image;
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
            text.resizeTextMinSize = 17;
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

    public sealed class VirtualStick : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IDragHandler
    {
        public RectTransform knob;
        public PlayerController target;
        private RectTransform rect;

        private void Awake()
        {
            rect = GetComponent<RectTransform>();
        }

        public void OnPointerDown(PointerEventData eventData)
        {
            OnDrag(eventData);
        }

        public void OnDrag(PointerEventData eventData)
        {
            if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(
                    rect,
                    eventData.position,
                    eventData.pressEventCamera,
                    out var local))
                return;

            var radius = Mathf.Min(rect.rect.width, rect.rect.height) * .35f;
            var value = Vector2.ClampMagnitude(local / radius, 1f);
            knob.anchoredPosition = value * radius * .48f;
            target.SetTouchMove(value);
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            knob.anchoredPosition = Vector2.zero;
            target.SetTouchMove(Vector2.zero);
        }
    }

    public sealed class SafeAreaFitter : MonoBehaviour
    {
        private Rect lastSafeArea;
        private Vector2Int lastSize;
        private RectTransform rect;

        private void Awake()
        {
            rect = GetComponent<RectTransform>();
            Apply();
        }

        private void Update()
        {
            if (lastSafeArea != Screen.safeArea ||
                lastSize.x != Screen.width ||
                lastSize.y != Screen.height)
                Apply();
        }

        private void Apply()
        {
            var safe = Screen.safeArea;
            lastSafeArea = safe;
            lastSize = new Vector2Int(Screen.width, Screen.height);

            var min = safe.position;
            var max = safe.position + safe.size;
            min.x /= Screen.width;
            min.y /= Screen.height;
            max.x /= Screen.width;
            max.y /= Screen.height;

            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
        }
    }
}
