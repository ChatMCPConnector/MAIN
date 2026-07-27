using UnityEngine;

namespace NeonRift
{
    public static class MaterialFactory
    {
        public static Material CreateLit(
            string name,
            Color color,
            float metallic = 0f,
            float smoothness = 0.35f,
            Color? emission = null)
        {
            Material material = CreateBaseLit(name, color, metallic, smoothness);
            ApplyEmission(material, emission);
            return material;
        }

        public static Material CreateTexturedLit(
            string name,
            Color tint,
            Texture2D baseMap,
            Texture2D normalMap,
            Texture2D occlusionMap,
            Vector2 tiling,
            float metallic = 0f,
            float smoothness = 0.35f,
            Color? emission = null)
        {
            Material material = CreateBaseLit(name, tint, metallic, smoothness);

            if (baseMap != null)
            {
                SetTexture(material, "_BaseMap", baseMap);
                SetTexture(material, "_MainTex", baseMap);
                SetTextureScale(material, "_BaseMap", tiling);
                SetTextureScale(material, "_MainTex", tiling);
            }

            if (normalMap != null)
            {
                SetTexture(material, "_BumpMap", normalMap);
                if (material.HasProperty("_BumpScale"))
                {
                    material.SetFloat("_BumpScale", 0.9f);
                }
                material.EnableKeyword("_NORMALMAP");
            }

            if (occlusionMap != null)
            {
                SetTexture(material, "_OcclusionMap", occlusionMap);
                if (material.HasProperty("_OcclusionStrength"))
                {
                    material.SetFloat("_OcclusionStrength", 0.82f);
                }
                material.EnableKeyword("_OCCLUSIONMAP");
            }

            ApplyEmission(material, emission);
            return material;
        }

        private static Material CreateBaseLit(string name, Color color, float metallic, float smoothness)
        {
            Shader shader = Shader.Find("Universal Render Pipeline/Lit");
            if (shader == null)
            {
                shader = Shader.Find("Standard");
            }

            var material = new Material(shader) { name = name };
            SetColor(material, color);

            if (material.HasProperty("_Metallic"))
            {
                material.SetFloat("_Metallic", metallic);
            }

            if (material.HasProperty("_Smoothness"))
            {
                material.SetFloat("_Smoothness", smoothness);
            }

            return material;
        }

        private static void ApplyEmission(Material material, Color? emission)
        {
            if (!emission.HasValue) return;

            material.EnableKeyword("_EMISSION");
            if (material.HasProperty("_EmissionColor"))
            {
                material.SetColor("_EmissionColor", emission.Value);
            }
        }

        private static void SetTexture(Material material, string property, Texture texture)
        {
            if (material.HasProperty(property))
            {
                material.SetTexture(property, texture);
            }
        }

        private static void SetTextureScale(Material material, string property, Vector2 scale)
        {
            if (material.HasProperty(property))
            {
                material.SetTextureScale(property, scale);
            }
        }

        public static void SetColor(Material material, Color color)
        {
            if (material == null) return;
            if (material.HasProperty("_BaseColor")) material.SetColor("_BaseColor", color);
            if (material.HasProperty("_Color")) material.SetColor("_Color", color);
        }
    }
}
