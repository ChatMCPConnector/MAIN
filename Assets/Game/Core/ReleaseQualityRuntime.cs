using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.Rendering.Universal;
using UnityEngine.UI;

namespace Riftbound
{
    public enum FeedbackCue { Attack, Ability, Dash, Hit, Damage, Reward, Revive }

    public static class ReleasePreferences
    {
        private const string ReducedMotionKey = "riftbound-reduced-motion";
        private const string HighContrastKey = "riftbound-high-contrast";
        private const string LargeTextKey = "riftbound-large-text";
        private const string VibrationKey = "riftbound-vibration";

        public static bool ReducedMotion
        {
            get => PlayerPrefs.GetInt(ReducedMotionKey, 0) != 0;
            set => Set(ReducedMotionKey, value);
        }

        public static bool HighContrast
        {
            get => PlayerPrefs.GetInt(HighContrastKey, 0) != 0;
            set => Set(HighContrastKey, value);
        }

        public static bool LargeText
        {
            get => PlayerPrefs.GetInt(LargeTextKey, 0) != 0;
            set => Set(LargeTextKey, value);
        }

        public static bool Vibration
        {
            get => PlayerPrefs.GetInt(VibrationKey, 1) != 0;
            set => Set(VibrationKey, value);
        }

        private static void Set(string key, bool value)
        {
            PlayerPrefs.SetInt(key, value ? 1 : 0);
            PlayerPrefs.Save();
        }
    }

    public sealed class ReleaseQualityRuntime : MonoBehaviour
    {
        private const float SampleWindow = 2f;
        private UniversalRenderPipelineAsset pipeline;
        private float sampleTime;
        private int sampleFrames;
        private float nextUiRefresh;
        private AudioSource audioSource;
        private readonly Dictionary<FeedbackCue, AudioClip> clips = new Dictionary<FeedbackCue, AudioClip>();
        private float nextVibration;

        public static ReleaseQualityRuntime Instance { get; private set; }

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<ReleaseQualityRuntime>() != null) return;
            var root = new GameObject("Release Quality Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<ReleaseQualityRuntime>();
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
            Application.targetFrameRate = 60;
            QualitySettings.vSyncCount = 0;
            ConfigureInitialQuality();
            audioSource = gameObject.AddComponent<AudioSource>();
            audioSource.playOnAwake = false;
            audioSource.spatialBlend = 0f;
            BuildClips();
        }

        private void Start()
        {
            AccessibilityView.Create(this);
            ApplyAccessibility();
        }

        private void Update()
        {
            sampleTime += Time.unscaledDeltaTime;
            sampleFrames++;
            if (sampleTime >= SampleWindow)
            {
                var fps = sampleFrames / Mathf.Max(.01f, sampleTime);
                AdjustRenderScale(fps);
                sampleTime = 0f;
                sampleFrames = 0;
            }

            if (Time.unscaledTime >= nextUiRefresh)
            {
                nextUiRefresh = Time.unscaledTime + 1f;
                ApplyAccessibility();
            }
        }

        public static void Play(FeedbackCue cue, bool vibrate = false)
        {
            Instance?.PlayInternal(cue, vibrate);
        }

        public void ApplyAccessibility()
        {
            var texts = FindObjectsByType<Text>(FindObjectsSortMode.None);
            for (var i = 0; i < texts.Length; i++)
            {
                var text = texts[i];
                if (text == null) continue;
                var baseSize = Mathf.Clamp(text.fontSize, 18, 46);
                text.fontSize = ReleasePreferences.LargeText
                    ? Mathf.Clamp(Mathf.RoundToInt(baseSize * 1.12f), 20, 52)
                    : Mathf.Clamp(baseSize, 18, 46);
                if (ReleasePreferences.HighContrast)
                    text.color = Color.white;
            }

            var camera = Camera.main;
            if (camera != null && ReleasePreferences.HighContrast)
                camera.backgroundColor = new Color(.008f, .01f, .018f);
        }

        private void ConfigureInitialQuality()
        {
            var memory = SystemInfo.systemMemorySize;
            var cores = SystemInfo.processorCount;
            QualitySettings.shadows = memory >= 4000 && cores >= 6
                ? ShadowQuality.HardOnly
                : ShadowQuality.Disable;
            QualitySettings.shadowDistance = memory >= 4000 ? 18f : 0f;
            QualitySettings.antiAliasing = memory >= 6000 ? 4 : memory >= 3500 ? 2 : 0;
            pipeline = QualitySettings.renderPipeline as UniversalRenderPipelineAsset;
            if (pipeline != null)
                pipeline.renderScale = memory < 3000 ? .78f : memory < 5000 ? .9f : 1f;
        }

        private void AdjustRenderScale(float fps)
        {
            pipeline ??= QualitySettings.renderPipeline as UniversalRenderPipelineAsset;
            if (pipeline == null) return;
            var scale = pipeline.renderScale;
            if (fps < 43f) scale -= .08f;
            else if (fps > 57f) scale += .04f;
            pipeline.renderScale = Mathf.Clamp(scale, .72f, 1f);
        }

        private void PlayInternal(FeedbackCue cue, bool vibrate)
        {
            if (audioSource != null && clips.TryGetValue(cue, out var clip) && clip != null)
                audioSource.PlayOneShot(clip, cue == FeedbackCue.Damage ? .65f : .45f);

            if (!vibrate || !ReleasePreferences.Vibration || Time.unscaledTime < nextVibration) return;
            nextVibration = Time.unscaledTime + .25f;
#if UNITY_ANDROID && !UNITY_EDITOR
            Handheld.Vibrate();
#endif
        }

        private void BuildClips()
        {
            clips[FeedbackCue.Attack] = CreateTone("Attack", 420f, .055f);
            clips[FeedbackCue.Ability] = CreateTone("Ability", 720f, .12f);
            clips[FeedbackCue.Dash] = CreateTone("Dash", 260f, .07f);
            clips[FeedbackCue.Hit] = CreateTone("Hit", 160f, .045f);
            clips[FeedbackCue.Damage] = CreateTone("Damage", 95f, .11f);
            clips[FeedbackCue.Reward] = CreateTone("Reward", 880f, .16f);
            clips[FeedbackCue.Revive] = CreateTone("Revive", 540f, .20f);
        }

        private static AudioClip CreateTone(string name, float frequency, float duration)
        {
            const int sampleRate = 22050;
            var count = Mathf.Max(32, Mathf.RoundToInt(sampleRate * duration));
            var samples = new float[count];
            for (var i = 0; i < count; i++)
            {
                var envelope = 1f - i / (float)count;
                samples[i] = Mathf.Sin(2f * Mathf.PI * frequency * i / sampleRate) * envelope * .22f;
            }
            var clip = AudioClip.Create(name, count, 1, sampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
        }
    }

    public sealed class AccessibilityView : MonoBehaviour
    {
        private ReleaseQualityRuntime runtime;
        private RectTransform safeRoot;
        private GameObject overlay;
        private Font font;

        public static AccessibilityView Create(ReleaseQualityRuntime runtime)
        {
            var existing = FindFirstObjectByType<AccessibilityView>();
            if (existing != null) return existing;
            var root = new GameObject("Accessibility HUD");
            DontDestroyOnLoad(root);
            var view = root.AddComponent<AccessibilityView>();
            view.runtime = runtime;
            view.Build();
            return view;
        }

        private void Build()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            canvas.sortingOrder = 90;
            gameObject.AddComponent<GraphicRaycaster>();
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;
            safeRoot = CreateRect("SafeArea", transform, Vector2.zero, Vector2.one);
            safeRoot.gameObject.AddComponent<SafeAreaFitter>();
            CreateButton("⚙", safeRoot, new Vector2(.88f, .775f), new Vector2(.97f, .835f), Open);
        }

        private void Open()
        {
            if (overlay != null) return;
            overlay = new GameObject("Accessibility Overlay", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(safeRoot, false);
            var rect = overlay.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            overlay.GetComponent<Image>().color = new Color(.01f, .015f, .035f, .98f);
            Refresh();
        }

        private void Refresh()
        {
            if (overlay == null) return;
            var rect = overlay.GetComponent<RectTransform>();
            for (var i = rect.childCount - 1; i >= 0; i--) Destroy(rect.GetChild(i).gameObject);
            CreateText("BARRIEREFREIHEIT & QUALITÄT", rect, 40, new Vector2(.06f, .80f), new Vector2(.94f, .94f));
            AddToggle(rect, 0, "GROSSE SCHRIFT", ReleasePreferences.LargeText, value => ReleasePreferences.LargeText = value);
            AddToggle(rect, 1, "HOHER KONTRAST", ReleasePreferences.HighContrast, value => ReleasePreferences.HighContrast = value);
            AddToggle(rect, 2, "BEWEGUNG REDUZIEREN", ReleasePreferences.ReducedMotion, value => ReleasePreferences.ReducedMotion = value);
            AddToggle(rect, 3, "VIBRATION", ReleasePreferences.Vibration, value => ReleasePreferences.Vibration = value);
            CreateButton("SCHLIESSEN", rect, new Vector2(.10f, .20f), new Vector2(.90f, .28f), Close);
        }

        private void AddToggle(RectTransform parent, int index, string label, bool value, Action<bool> set)
        {
            var top = .73f - index * .12f;
            CreateButton(
                $"{label}: {(value ? "AN" : "AUS")}",
                parent,
                new Vector2(.10f, top - .085f),
                new Vector2(.90f, top),
                () =>
                {
                    set(!value);
                    runtime?.ApplyAccessibility();
                    Refresh();
                });
        }

        private void Close()
        {
            if (overlay != null) Destroy(overlay);
            overlay = null;
        }

        private void CreateButton(string label, Transform parent, Vector2 min, Vector2 max, Action action)
        {
            var rect = CreateRect(label, parent, min, max);
            var image = rect.gameObject.AddComponent<Image>();
            image.color = new Color(.12f, .20f, .32f, .96f);
            var button = rect.gameObject.AddComponent<Button>();
            button.targetGraphic = image;
            button.onClick.AddListener(() => action?.Invoke());
            CreateText(label, rect, 28, Vector2.zero, Vector2.one);
        }

        private void CreateText(string value, Transform parent, int size, Vector2 min, Vector2 max)
        {
            var rect = CreateRect("Text", parent, min, max);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = TextAnchor.MiddleCenter;
            text.color = Color.white;
            text.text = value;
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
