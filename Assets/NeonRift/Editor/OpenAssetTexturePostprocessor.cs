using System;
using UnityEditor;
using UnityEngine;

namespace NeonRift.Editor
{
    /// <summary>
    /// Applies deterministic, game-ready import settings to generated open assets.
    /// The source files remain outside Git, while every build imports them the same way.
    /// </summary>
    public sealed class OpenAssetTexturePostprocessor : AssetPostprocessor
    {
        private const string OpenAssetRoot = "Assets/Resources/Community/OpenAssets/";

        private void OnPreprocessTexture()
        {
            string normalizedPath = assetPath.Replace('\\', '/');
            if (!normalizedPath.StartsWith(OpenAssetRoot, StringComparison.OrdinalIgnoreCase))
            {
                return;
            }

            var importer = (TextureImporter)assetImporter;
            string fileName = System.IO.Path.GetFileNameWithoutExtension(normalizedPath).ToLowerInvariant();
            string extension = System.IO.Path.GetExtension(normalizedPath).ToLowerInvariant();

            importer.maxTextureSize = 2048;
            importer.mipmapEnabled = true;
            importer.streamingMipmaps = true;
            importer.filterMode = FilterMode.Trilinear;
            importer.anisoLevel = 8;
            importer.wrapMode = TextureWrapMode.Repeat;
            importer.alphaSource = TextureImporterAlphaSource.None;
            importer.crunchedCompression = false;

            bool isHdr = extension is ".hdr" or ".exr";
            bool isNormal = ContainsAny(fileName, "normalgl", "normal_gl", "nor_gl", "_normal", "-normal");
            bool isLinearMask = ContainsAny(
                fileName,
                "ambientocclusion",
                "ambient_occlusion",
                "_ao",
                "-ao",
                "roughness",
                "_rough",
                "-rough",
                "metallic",
                "_metal",
                "-metal",
                "displacement",
                "_disp",
                "-disp",
                "height");

            if (isHdr)
            {
                importer.textureType = TextureImporterType.Default;
                importer.sRGBTexture = false;
                importer.textureCompression = TextureImporterCompression.Uncompressed;
                importer.wrapMode = TextureWrapMode.Clamp;
                return;
            }

            if (isNormal)
            {
                importer.textureType = TextureImporterType.NormalMap;
                importer.sRGBTexture = false;
                importer.textureCompression = TextureImporterCompression.CompressedHQ;
                return;
            }

            importer.textureType = TextureImporterType.Default;
            importer.sRGBTexture = !isLinearMask;
            importer.textureCompression = TextureImporterCompression.CompressedHQ;
        }

        private static bool ContainsAny(string value, params string[] tokens)
        {
            foreach (string token in tokens)
            {
                if (value.Contains(token, StringComparison.OrdinalIgnoreCase))
                {
                    return true;
                }
            }
            return false;
        }
    }
}
