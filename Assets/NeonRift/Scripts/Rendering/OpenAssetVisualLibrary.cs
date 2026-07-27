using System;
using System.Linq;
using UnityEngine;

namespace NeonRift
{
    /// <summary>
    /// Builds runtime URP materials from the reproducibly downloaded Poly Haven
    /// and ambientCG textures. Every method returns null when an asset is missing,
    /// allowing ArenaVisualFactory to keep its procedural fallback materials.
    /// </summary>
    public static class OpenAssetVisualLibrary
    {
        private const string PolyMetal = "Community/OpenAssets/polyhaven/materials/metal_plate";
        private const string PolyFoundryHdri = "Community/OpenAssets/polyhaven/lighting/industrial_workshop_foundry";
        private const string AmbientSciFiMetal = "Community/OpenAssets/ambientcg/materials/MetalPlates015A";
        private const string AmbientConcrete = "Community/OpenAssets/ambientcg/materials/Concrete023";
        private const string AmbientFacade = "Community/OpenAssets/ambientcg/materials/Facade019C";

        public static Material CreateFloorMaterial(ArenaSpec spec, int arenaIndex)
        {
            return arenaIndex switch
            {
                0 => CreateSurface(
                    PolyMetal,
                    "Poly Haven worn steel floor",
                    Color.Lerp(Color.white, spec.Ground * 1.8f, 0.22f),
                    new Vector2(5.5f, 2.6f),
                    0.78f,
                    0.42f),
                1 => CreateSurface(
                    AmbientConcrete,
                    "ambientCG weathered concrete floor",
                    Color.Lerp(Color.white, spec.Ground * 2.1f, 0.24f),
                    new Vector2(5.2f, 2.4f),
                    0.04f,
                    0.3f),
                _ => CreateSurface(
                    AmbientSciFiMetal,
                    "ambientCG sci-fi panel floor",
                    Color.Lerp(Color.white, spec.Ground * 2.2f, 0.2f),
                    new Vector2(4.8f, 2.2f),
                    0.72f,
                    0.5f)
            };
        }

        public static Material CreateWallMaterial(ArenaSpec spec, int arenaIndex)
        {
            return arenaIndex switch
            {
                0 => CreateSurface(
                    AmbientSciFiMetal,
                    "ambientCG industrial panel walls",
                    Color.Lerp(Color.white, spec.Ground * 1.65f, 0.18f),
                    new Vector2(1.4f, 1.4f),
                    0.74f,
                    0.48f),
                1 => CreateSurface(
                    AmbientConcrete,
                    "ambientCG concrete arena walls",
                    Color.Lerp(Color.white, spec.Ground * 2f, 0.2f),
                    new Vector2(1.8f, 1.2f),
                    0.02f,
                    0.25f),
                _ => CreateSurface(
                    PolyMetal,
                    "Poly Haven worn metal walls",
                    Color.Lerp(Color.white, spec.Ground * 2f, 0.22f),
                    new Vector2(2f, 1.2f),
                    0.68f,
                    0.38f)
            };
        }

        public static Material CreateFacadeMaterial(ArenaSpec spec, int arenaIndex)
        {
            Color tint = arenaIndex switch
            {
                0 => Color.Lerp(Color.white, spec.Sky * 2.5f, 0.2f),
                1 => Color.Lerp(Color.white, spec.Fog * 2f, 0.22f),
                _ => Color.Lerp(Color.white, spec.Neon * 0.8f, 0.16f)
            };

            return CreateSurface(
                AmbientFacade,
                "ambientCG distant tower facade",
                tint,
                new Vector2(1.15f, 2.7f),
                0.12f,
                0.5f);
        }

        public static Material CreateSkyboxMaterial(ArenaSpec spec, int arenaIndex)
        {
            Texture2D[] textures = Resources.LoadAll<Texture2D>(PolyFoundryHdri);
            Texture2D panorama = FindTexture(textures, "hdr", "environment", "industrial_workshop_foundry")
                                 ?? textures.FirstOrDefault();
            if (panorama == null) return null;

            Shader shader = Shader.Find("Skybox/Panoramic");
            if (shader == null) return null;

            var material = new Material(shader)
            {
                name = "Poly Haven industrial workshop skybox"
            };
            if (material.HasProperty("_Tex")) material.SetTexture("_Tex", panorama);
            if (material.HasProperty("_Exposure"))
            {
                material.SetFloat("_Exposure", arenaIndex switch
                {
                    0 => 0.82f,
                    1 => 0.58f,
                    _ => 0.68f
                });
            }
            if (material.HasProperty("_Rotation")) material.SetFloat("_Rotation", 22f + arenaIndex * 73f);
            if (material.HasProperty("_Tint"))
            {
                Color tint = Color.Lerp(Color.white, spec.Sky * 3.2f, arenaIndex == 1 ? 0.48f : 0.34f);
                material.SetColor("_Tint", tint);
            }
            return material;
        }

        private static Material CreateSurface(
            string resourcePath,
            string name,
            Color tint,
            Vector2 tiling,
            float metallic,
            float smoothness)
        {
            Texture2D[] textures = Resources.LoadAll<Texture2D>(resourcePath);
            if (textures.Length == 0) return null;

            Texture2D albedo = FindTexture(
                textures,
                "basecolor",
                "base_color",
                "albedo",
                "diffuse",
                "_diff",
                "color");
            if (albedo == null) return null;

            Texture2D normal = FindTexture(
                textures,
                "normalgl",
                "normal_gl",
                "nor_gl",
                "normal");
            Texture2D occlusion = FindTexture(
                textures,
                "ambientocclusion",
                "ambient_occlusion",
                "_ao",
                "-ao");

            return MaterialFactory.CreateTexturedLit(
                name,
                tint,
                albedo,
                normal,
                occlusion,
                tiling,
                metallic,
                smoothness);
        }

        private static Texture2D FindTexture(Texture2D[] textures, params string[] tokens)
        {
            foreach (string token in tokens)
            {
                Texture2D match = textures.FirstOrDefault(texture =>
                    texture != null &&
                    texture.name.Contains(token, StringComparison.OrdinalIgnoreCase));
                if (match != null) return match;
            }
            return null;
        }
    }
}
