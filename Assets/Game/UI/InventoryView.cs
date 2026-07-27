using System;
using UnityEngine;
using UnityEngine.UI;

namespace Riftbound
{
    public sealed class InventoryView : MonoBehaviour
    {
        private RunInventory inventory;
        private PlayerController player;
        private Func<ItemInstance, int> salvage;
        private Action cycleFilter;
        private Action closeAction;
        private RectTransform safeRoot;
        private Font font;
        private int index;

        public static InventoryView Show(
            RunInventory inventory,
            PlayerController player,
            Func<ItemInstance, int> salvage,
            Action cycleFilter,
            Action closeAction)
        {
            var root = new GameObject("Inventory View");
            DontDestroyOnLoad(root);
            var view = root.AddComponent<InventoryView>();
            view.inventory = inventory;
            view.player = player;
            view.salvage = salvage;
            view.cycleFilter = cycleFilter;
            view.closeAction = closeAction;
            view.BuildCanvas();
            view.Refresh();
            return view;
        }

        private void BuildCanvas()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");

            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 100;
            gameObject.AddComponent<GraphicRaycaster>();

            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;

            safeRoot = CreateRect("SafeArea", transform, Vector2.zero, Vector2.one);
            safeRoot.gameObject.AddComponent<SafeAreaFitter>();
        }

        private void Refresh()
        {
            ClearSafeRoot();

            var background = CreatePanel(
                "Background",
                safeRoot,
                new Color(.025f, .03f, .07f, .98f),
                Vector2.zero,
                Vector2.one);

            var count = inventory.Items.Count;
            if (count == 0)
            {
                CreateText(
                    "INVENTAR\n\nLeer",
                    background,
                    44,
                    TextAnchor.MiddleCenter,
                    new Vector2(.08f, .48f),
                    new Vector2(.92f, .88f));
                CreateButton("WEITER", background, new Vector2(.12f, .08f), new Vector2(.88f, .20f), Close);
                return;
            }

            index = Mathf.Clamp(index, 0, count - 1);
            var item = inventory.Items[index];
            var equipped = player.IsEquipped(item.instanceId) ? "\n<color=#6CFFB4>AUSGERÜSTET</color>" : "";
            var locked = item.locked ? "\n<color=#FFD36C>STARTAUSRÜSTUNG</color>" : "";

            CreateText(
                $"INVENTAR {index + 1}/{count} · Plätze {count}/{inventory.Capacity}\n\n" +
                $"{ItemText.Title(item)}\n{ItemText.Description(item)}" +
                $"{equipped}{locked}\n\n" +
                $"Aufhebefilter: {RarityUtility.DisplayName(inventory.MinimumRarity)}",
                background,
                38,
                TextAnchor.MiddleCenter,
                new Vector2(.07f, .57f),
                new Vector2(.93f, .94f));

            CreateButton("◀ VORHERIGER", background, new Vector2(.08f, .45f), new Vector2(.48f, .55f), Previous);
            CreateButton("NÄCHSTER ▶", background, new Vector2(.52f, .45f), new Vector2(.92f, .55f), Next);
            CreateButton("AUSRÜSTEN", background, new Vector2(.08f, .32f), new Vector2(.92f, .42f), Equip);
            CreateButton(
                item.locked ? "NICHT ZERLEGBAR" : $"ZERLEGEN · +{item.salvageValue} GOLD",
                background,
                new Vector2(.08f, .20f),
                new Vector2(.92f, .30f),
                Salvage);
            CreateButton(
                $"FILTER WECHSELN · {RarityUtility.DisplayName(inventory.MinimumRarity)}",
                background,
                new Vector2(.08f, .08f),
                new Vector2(.63f, .18f),
                CycleFilter);
            CreateButton("WEITER", background, new Vector2(.67f, .08f), new Vector2(.92f, .18f), Close);
        }

        private void ClearSafeRoot()
        {
            for (var i = safeRoot.childCount - 1; i >= 0; i--)
            {
                var child = safeRoot.GetChild(i);
                child.SetParent(null, false);
                Destroy(child.gameObject);
            }
        }

        private void Previous()
        {
            var count = inventory.Items.Count;
            if (count == 0) return;
            index = (index - 1 + count) % count;
            Refresh();
        }

        private void Next()
        {
            var count = inventory.Items.Count;
            if (count == 0) return;
            index = (index + 1) % count;
            Refresh();
        }

        private void Equip()
        {
            if (inventory.Items.Count == 0) return;
            player.EquipItem(inventory.Items[index]);
            Refresh();
        }

        private void Salvage()
        {
            if (inventory.Items.Count == 0) return;
            var item = inventory.Items[index];
            if (item.locked || player.IsEquipped(item.instanceId)) return;

            salvage?.Invoke(item);
            index = Mathf.Max(0, index - 1);
            Refresh();
        }

        private void CycleFilter()
        {
            cycleFilter?.Invoke();
            Refresh();
        }

        private void Close()
        {
            closeAction?.Invoke();
            Destroy(gameObject);
        }

        private void CreateButton(
            string label,
            Transform parent,
            Vector2 min,
            Vector2 max,
            UnityEngine.Events.UnityAction action)
        {
            var panel = CreatePanel(
                label,
                parent,
                new Color(.13f, .2f, .34f, .92f),
                min,
                max);
            var button = panel.gameObject.AddComponent<Button>();
            button.targetGraphic = panel.GetComponent<Image>();
            button.onClick.AddListener(action);
            CreateText(label, panel, 28, TextAnchor.MiddleCenter, Vector2.zero, Vector2.one);
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
}
