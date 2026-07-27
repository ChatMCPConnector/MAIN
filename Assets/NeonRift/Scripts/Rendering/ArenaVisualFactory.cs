using System;
using System.Collections.Generic;
using System.Linq;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace NeonRift
{
    public sealed class ArenaVisualFactory : MonoBehaviour
    {
        public Transform ArenaRoot { get; private set; }
        public Camera GameCamera { get; private set; }

        private readonly List<Material> _materials = new();
        private Material _floorSurface;
        private Material _wallSurface;
        private Material _facadeSurface;
        private Material _skyboxMaterial;
        private VolumeProfile _volumeProfile;

        public void Build(ArenaSpec spec, int arenaIndex)
        {
            ClearArena();
            PrepareOpenAssetVisuals(spec, arenaIndex);
            ConfigureWorld(spec);
            CreateCamera(spec);
            CreateLights(spec);
            CreatePostProcessing(spec);
            CreateGround(spec);
            CreateBackdrop(spec, arenaIndex);
            CreateCommunityProps(spec, arenaIndex);
            CreateAtmosphere(spec, arenaIndex);
        }

        private void ClearArena()
        {
            if (RenderSettings.skybox == _skyboxMaterial)
            {
                RenderSettings.skybox = null;
            }

            if (ArenaRoot != null)
            {
                ArenaRoot.gameObject.SetActive(false);
                Destroy(ArenaRoot.gameObject);
            }

            ReleaseRuntimeResources();
            _floorSurface = null;
            _wallSurface = null;
            _facadeSurface = null;
            _skyboxMaterial = null;
            GameCamera = null;

            ArenaRoot = new GameObject("Arena Visuals").transform;
            ArenaRoot.SetParent(transform, false);
        }

        private void PrepareOpenAssetVisuals(ArenaSpec spec, int arenaIndex)
        {
            _floorSurface = RememberIfPresent(OpenAssetVisualLibrary.CreateFloorMaterial(spec, arenaIndex));
            _wallSurface = RememberIfPresent(OpenAssetVisualLibrary.CreateWallMaterial(spec, arenaIndex));
            _facadeSurface = RememberIfPresent(OpenAssetVisualLibrary.CreateFacadeMaterial(spec, arenaIndex));
            _skyboxMaterial = RememberIfPresent(OpenAssetVisualLibrary.CreateSkyboxMaterial(spec, arenaIndex));

            if (_skyboxMaterial != null)
            {
                RenderSettings.skybox = _skyboxMaterial;
                DynamicGI.UpdateEnvironment();
            }
        }

        private static void ConfigureWorld(ArenaSpec spec)
        {
            RenderSettings.fog = true;
            RenderSettings.fogMode = FogMode.ExponentialSquared;
            RenderSettings.fogColor = spec.Fog;
            RenderSettings.fogDensity = 0.0105f;
            RenderSettings.ambientMode = AmbientMode.Trilight;
            RenderSettings.ambientSkyColor = spec.Sky * 1.55f;
            RenderSettings.ambientEquatorColor = spec.Fog * 1.15f;
            RenderSettings.ambientGroundColor = spec.Ground * 0.72f;
            RenderSettings.defaultReflectionMode = DefaultReflectionMode.Skybox;
            RenderSettings.reflectionIntensity = 0.82f;
        }

        private void CreateCamera(ArenaSpec spec)
        {
            var cameraObject = new GameObject("Arena Camera");
            cameraObject.transform.SetParent(ArenaRoot, false);
            GameCamera = cameraObject.AddComponent<Camera>();
            GameCamera.tag = "MainCamera";
            GameCamera.fieldOfView = 43f;
            GameCamera.nearClipPlane = 0.15f;
            GameCamera.farClipPlane = 190f;
            GameCamera.backgroundColor = spec.Sky;
            GameCamera.clearFlags = _skyboxMaterial != null
                ? CameraClearFlags.Skybox
                : CameraClearFlags.SolidColor;
            GameCamera.allowHDR = true;
            GameCamera.allowMSAA = true;

            var additional = cameraObject.AddComponent<UniversalAdditionalCameraData>();
            additional.renderPostProcessing = true;
            additional.antialiasing = AntialiasingMode.FastApproximateAntialiasing;

            cameraObject.AddComponent<ArenaCameraRig>();
        }

        private void CreateLights(ArenaSpec spec)
        {
            var sunObject = new GameObject("Key Light");
            sunObject.transform.SetParent(ArenaRoot, false);
            sunObject.transform.rotation = Quaternion.Euler(48f, -34f, 0f);
            var sun = sunObject.AddComponent<Light>();
            sun.type = LightType.Directional;
            sun.color = Color.Lerp(Color.white, spec.Neon, 0.14f);
            sun.intensity = _skyboxMaterial != null ? 1.18f : 1.45f;
            sun.shadows = LightShadows.Soft;
            sun.shadowStrength = 0.8f;
            sun.shadowBias = 0.045f;
            sun.shadowNormalBias = 0.35f;

            CreatePointLight(new Vector3(-7f, 4.5f, 2.5f), spec.Neon, 14f, 4.3f);
            CreatePointLight(new Vector3(7f, 3.8f, -1.5f), Color.Lerp(spec.Neon, Color.magenta, 0.38f), 12f, 3.5f);
            CreatePointLight(new Vector3(0f, 5.5f, 7f), Color.Lerp(spec.Neon, Color.white, 0.45f), 16f, 2.8f);
        }

        private void CreatePointLight(Vector3 position, Color color, float range, float intensity)
        {
            var lightObject = new GameObject("Arena Accent Light");
            lightObject.transform.SetParent(ArenaRoot, false);
            lightObject.transform.position = position;
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Point;
            light.color = color;
            light.range = range;
            light.intensity = intensity;
            light.shadows = LightShadows.None;
        }

        private void CreatePostProcessing(ArenaSpec spec)
        {
            var volumeObject = new GameObject("Global Visual Grade");
            volumeObject.transform.SetParent(ArenaRoot, false);
            var volume = volumeObject.AddComponent<Volume>();
            volume.isGlobal = true;
            volume.priority = 20f;
            _volumeProfile = ScriptableObject.CreateInstance<VolumeProfile>();
            _volumeProfile.name = "Neon Rift Runtime Grade";
            volume.profile = _volumeProfile;

            var bloom = _volumeProfile.Add<Bloom>(true);
            bloom.intensity.Override(0.58f);
            bloom.threshold.Override(0.92f);
            bloom.scatter.Override(0.68f);

            var colorAdjustments = _volumeProfile.Add<ColorAdjustments>(true);
            colorAdjustments.contrast.Override(7f);
            colorAdjustments.saturation.Override(9f);
            colorAdjustments.colorFilter.Override(Color.Lerp(Color.white, spec.Neon, 0.065f));

            var vignette = _volumeProfile.Add<Vignette>(true);
            vignette.intensity.Override(0.22f);
            vignette.smoothness.Override(0.72f);

            var tonemapping = _volumeProfile.Add<Tonemapping>(true);
            tonemapping.mode.Override(TonemappingMode.ACES);
        }

        private void CreateGround(ArenaSpec spec)
        {
            Material floor = _floorSurface
                             ?? Remember(MaterialFactory.CreateLit("Arena floor", spec.Ground, 0.48f, 0.62f));
            Material walls = _wallSurface ?? floor;
            Material grid = Remember(MaterialFactory.CreateLit(
                "Neon grid",
                spec.Neon * 0.55f,
                0.15f,
                0.9f,
                spec.Neon * 3.2f));

            CreateBox("Main platform", new Vector3(0f, -0.42f, 0f), new Vector3(24f, 0.8f, 11f), floor, true);
            CreateBox("Front lip", new Vector3(0f, -0.05f, -5.35f), new Vector3(24.5f, 0.12f, 0.15f), grid, false);
            CreateBox("Back lip", new Vector3(0f, -0.05f, 5.35f), new Vector3(24.5f, 0.12f, 0.15f), grid, false);

            for (int x = -10; x <= 10; x += 2)
            {
                CreateBox("Floor line", new Vector3(x, 0.015f, 0f), new Vector3(0.028f, 0.018f, 10.4f), grid, false);
            }

            for (int z = -4; z <= 4; z += 2)
            {
                CreateBox("Floor line", new Vector3(0f, 0.016f, z), new Vector3(23.5f, 0.018f, 0.028f), grid, false);
            }

            CreateBox("Left boundary", new Vector3(-12f, 1f, 0f), new Vector3(0.3f, 2f, 11f), walls, true);
            CreateBox("Right boundary", new Vector3(12f, 1f, 0f), new Vector3(0.3f, 2f, 11f), walls, true);

            for (int side = -1; side <= 1; side += 2)
            {
                CreateBox(
                    "Textured side deck",
                    new Vector3(side * 11.2f, -0.06f, 0f),
                    new Vector3(1.25f, 0.12f, 10.4f),
                    walls,
                    false);
            }
        }

        private void CreateBackdrop(ArenaSpec spec, int arenaIndex)
        {
            Material dark = _facadeSurface
                            ?? _wallSurface
                            ?? Remember(MaterialFactory.CreateLit("Backdrop", spec.Ground * 0.55f, 0.7f, 0.5f));
            Material neon = Remember(MaterialFactory.CreateLit(
                "Backdrop neon",
                spec.Neon,
                0.15f,
                0.95f,
                spec.Neon * 4f));

            for (int i = -5; i <= 5; i++)
            {
                float height = 3.5f + Mathf.Abs(Mathf.Sin(i * 1.71f + arenaIndex)) * 7f;
                float depth = 1.4f + Mathf.Abs(Mathf.Cos(i * 0.63f)) * 2.2f;
                CreateBox(
                    "Textured skyline block",
                    new Vector3(i * 3.2f, height * 0.5f - 0.2f, 9f + depth * 0.35f),
                    new Vector3(2.2f, height, depth),
                    dark,
                    false);
                CreateBox(
                    "Skyline strip",
                    new Vector3(i * 3.2f, height * 0.7f, 8.9f),
                    new Vector3(1.6f, 0.08f, 0.04f),
                    neon,
                    false);
            }

            for (int side = -1; side <= 1; side += 2)
            {
                for (int i = 0; i < 4; i++)
                {
                    float x = side * (7.8f + i * 1.1f);
                    CreateCylinder(
                        "Energy pylon",
                        new Vector3(x, 1.4f + i * 0.18f, 5.4f),
                        new Vector3(0.34f, 1.4f + i * 0.18f, 0.34f),
                        _wallSurface ?? dark,
                        false);
                    CreateCylinder(
                        "Pylon core",
                        new Vector3(x, 1.6f + i * 0.18f, 5.4f),
                        new Vector3(0.13f, 1.1f, 0.13f),
                        neon,
                        false);
                }
            }
        }

        private void CreateCommunityProps(ArenaSpec spec, int arenaIndex)
        {
            GameObject[] allProps = Resources.LoadAll<GameObject>("Community/Kenney");
            if (allProps.Length == 0)
            {
                CreateProceduralProps(spec, arenaIndex);
                return;
            }

            GameObject[] candidates = allProps
                .Where(prop => spec.PropKeywords.Any(keyword =>
                    prop.name.Contains(keyword, StringComparison.OrdinalIgnoreCase)))
                .Take(18)
                .ToArray();

            if (candidates.Length == 0)
            {
                candidates = allProps.Take(12).ToArray();
            }

            var random = new System.Random(713 + arenaIndex * 97);
            for (int i = 0; i < Mathf.Min(14, candidates.Length * 2); i++)
            {
                GameObject source = candidates[random.Next(candidates.Length)];
                var instance = Instantiate(source, ArenaRoot);
                instance.name = $"CC0 prop - {source.name}";
                float side = i % 2 == 0 ? -1f : 1f;
                float x = side * (7.4f + (float)random.NextDouble() * 3.2f);
                float z = -3.8f + (float)random.NextDouble() * 8.2f;
                instance.transform.position = new Vector3(x, 0f, z);
                instance.transform.rotation = Quaternion.Euler(0f, random.Next(0, 4) * 90f, 0f);
                instance.transform.localScale = Vector3.one * Mathf.Lerp(0.75f, 1.35f, (float)random.NextDouble());
            }
        }

        private void CreateProceduralProps(ArenaSpec spec, int arenaIndex)
        {
            Material metal = _wallSurface
                             ?? Remember(MaterialFactory.CreateLit(
                                 "Prop metal",
                                 Color.Lerp(spec.Ground, Color.gray, 0.35f),
                                 0.75f,
                                 0.58f));
            Material glow = Remember(MaterialFactory.CreateLit(
                "Prop glow",
                spec.Neon,
                0.25f,
                0.9f,
                spec.Neon * 3.2f));
            var random = new System.Random(42 + arenaIndex * 83);

            for (int i = 0; i < 16; i++)
            {
                float side = i % 2 == 0 ? -1f : 1f;
                float x = side * (7.2f + (float)random.NextDouble() * 3.7f);
                float z = -4.2f + (float)random.NextDouble() * 8.4f;
                float scale = Mathf.Lerp(0.7f, 1.45f, (float)random.NextDouble());
                CreateBox(
                    "Textured industrial crate",
                    new Vector3(x, 0.45f * scale, z),
                    Vector3.one * 0.9f * scale,
                    metal,
                    true);
                CreateBox(
                    "Crate light",
                    new Vector3(x, 0.47f * scale, z - 0.46f * scale),
                    new Vector3(0.55f * scale, 0.08f, 0.025f),
                    glow,
                    false);
            }
        }

        private void CreateAtmosphere(ArenaSpec spec, int arenaIndex)
        {
            var root = new GameObject("Atmosphere");
            root.transform.SetParent(ArenaRoot, false);
            var particles = root.AddComponent<ParticleSystem>();
            var main = particles.main;
            main.loop = true;
            main.duration = 8f;
            main.startLifetime = new ParticleSystem.MinMaxCurve(2f, 6f);
            main.startSpeed = arenaIndex == 0 ? 7f : 0.35f;
            main.startSize = arenaIndex == 0
                ? new ParticleSystem.MinMaxCurve(0.018f, 0.04f)
                : new ParticleSystem.MinMaxCurve(0.025f, 0.09f);
            main.startColor = new ParticleSystem.MinMaxGradient(
                Color.Lerp(spec.Neon, Color.white, 0.45f) * 0.75f);
            main.maxParticles = 650;
            main.simulationSpace = ParticleSystemSimulationSpace.World;
            main.gravityModifier = arenaIndex == 0 ? 0.55f : -0.005f;

            var emission = particles.emission;
            emission.rateOverTime = arenaIndex == 0 ? 120f : 22f;
            var shape = particles.shape;
            shape.shapeType = ParticleSystemShapeType.Box;
            shape.scale = new Vector3(28f, 1f, 15f);
            root.transform.position = new Vector3(0f, 8f, 0f);

            var renderer = particles.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = arenaIndex == 0
                ? ParticleSystemRenderMode.Stretch
                : ParticleSystemRenderMode.Billboard;
            renderer.lengthScale = arenaIndex == 0 ? 1.1f : 0.1f;
            renderer.velocityScale = 0.6f;
            renderer.sharedMaterial = Remember(MaterialFactory.CreateLit(
                "Atmosphere particle",
                spec.Neon,
                0f,
                0.8f,
                spec.Neon * 1.8f));
        }

        private GameObject CreateBox(
            string name,
            Vector3 position,
            Vector3 scale,
            Material material,
            bool collider)
        {
            GameObject item = GameObject.CreatePrimitive(PrimitiveType.Cube);
            item.name = name;
            item.transform.SetParent(ArenaRoot, false);
            item.transform.position = position;
            item.transform.localScale = scale;
            item.GetComponent<Renderer>().sharedMaterial = material;
            if (!collider) Destroy(item.GetComponent<Collider>());
            return item;
        }

        private GameObject CreateCylinder(
            string name,
            Vector3 position,
            Vector3 scale,
            Material material,
            bool collider)
        {
            GameObject item = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            item.name = name;
            item.transform.SetParent(ArenaRoot, false);
            item.transform.position = position;
            item.transform.localScale = scale;
            item.GetComponent<Renderer>().sharedMaterial = material;
            if (!collider) Destroy(item.GetComponent<Collider>());
            return item;
        }

        private Material Remember(Material material)
        {
            _materials.Add(material);
            return material;
        }

        private Material RememberIfPresent(Material material)
        {
            if (material != null)
            {
                _materials.Add(material);
            }
            return material;
        }

        private void ReleaseRuntimeResources()
        {
            if (_volumeProfile != null)
            {
                Destroy(_volumeProfile);
                _volumeProfile = null;
            }

            foreach (Material material in _materials)
            {
                if (material != null) Destroy(material);
            }
            _materials.Clear();
        }

        private void OnDestroy()
        {
            if (RenderSettings.skybox == _skyboxMaterial)
            {
                RenderSettings.skybox = null;
            }
            ReleaseRuntimeResources();
        }
    }
}
