using System;
using System.Collections.Generic;
using System.IO;
using System.IO.Compression;
using System.Net;
using UnityEditor;
using UnityEngine;

namespace NeonRift.Editor
{
    public static class CommunityAssetInstaller
    {
        private const string AdventurerCommit = "672074b73ba276876a19e8816ecdc5241817ab47";
        private const string SkeletonCommit = "15b62b9bad122f72926c10fb14d622c73819fa54";
        private const string AdventurerRoot = "https://cdn.jsdelivr.net/gh/KayKit-Game-Assets/KayKit-Character-Pack-Adventures-1.0@" + AdventurerCommit + "/addons/kaykit_character_pack_adventures/Characters/gltf/";
        private const string SkeletonRoot = "https://cdn.jsdelivr.net/gh/KayKit-Game-Assets/KayKit-Character-Pack-Skeletons-1.0@" + SkeletonCommit + "/addons/kaykit_character_pack_skeletons/Characters/gltf/";

        private static readonly IReadOnlyDictionary<string, string> CharacterDownloads = new Dictionary<string, string>
        {
            ["Knight.glb"] = AdventurerRoot + "Knight.glb",
            ["Barbarian.glb"] = AdventurerRoot + "Barbarian.glb",
            ["Mage.glb"] = AdventurerRoot + "Mage.glb",
            ["Rogue.glb"] = AdventurerRoot + "Rogue.glb",
            ["Skeleton_Warrior.glb"] = SkeletonRoot + "Skeleton_Warrior.glb",
            ["Skeleton_Rogue.glb"] = SkeletonRoot + "Skeleton_Rogue.glb",
            ["Skeleton_Mage.glb"] = SkeletonRoot + "Skeleton_Mage.glb",
            ["Skeleton_Minion.glb"] = SkeletonRoot + "Skeleton_Minion.glb"
        };

        private static readonly IReadOnlyDictionary<string, string> EnvironmentDownloads = new Dictionary<string, string>
        {
            ["MiniArena"] = "https://kenney.nl/media/pages/assets/mini-arena/88f977a0cb-1709220730/kenney_mini-arena.zip",
            ["CityIndustrial"] = "https://kenney.nl/media/pages/assets/city-kit-industrial/5fcb837741-1750838303/kenney_city-kit-industrial_1.0.zip"
        };

        [MenuItem("Neon Rift/Download or repair CC0 assets")]
        public static void DownloadFromMenu()
        {
            bool success = EnsureAssets(true);
            EditorUtility.DisplayDialog(
                "Neon Rift community assets",
                success
                    ? "All selected KayKit and Kenney CC0 assets are available."
                    : "One or more downloads failed. The game remains playable with procedural fallback art. Check the Console for details.",
                "OK");
        }

        public static bool EnsureAssets(bool showProgress)
        {
            string projectRoot = Directory.GetParent(Application.dataPath)?.FullName ?? Environment.CurrentDirectory;
            string characterDirectory = Path.Combine(Application.dataPath, "Resources", "Community", "KayKit");
            string environmentDirectory = Path.Combine(Application.dataPath, "Resources", "Community", "Kenney");
            string cacheDirectory = Path.Combine(projectRoot, "CommunityAssetCache");
            Directory.CreateDirectory(characterDirectory);
            Directory.CreateDirectory(environmentDirectory);
            Directory.CreateDirectory(cacheDirectory);

            bool success = true;
            int index = 0;
            int total = CharacterDownloads.Count + EnvironmentDownloads.Count;
            try
            {
                foreach (KeyValuePair<string, string> item in CharacterDownloads)
                {
                    index++;
                    if (showProgress) EditorUtility.DisplayProgressBar("Neon Rift CC0 assets", item.Key, index / (float)total);
                    string destination = Path.Combine(characterDirectory, item.Key);
                    if (File.Exists(destination) && new FileInfo(destination).Length > 100_000) continue;
                    success &= DownloadFile(item.Value, destination);
                }

                foreach (KeyValuePair<string, string> item in EnvironmentDownloads)
                {
                    index++;
                    if (showProgress) EditorUtility.DisplayProgressBar("Neon Rift CC0 assets", item.Key, index / (float)total);
                    string marker = Path.Combine(environmentDirectory, item.Key, ".installed");
                    if (File.Exists(marker)) continue;

                    string zipPath = Path.Combine(cacheDirectory, item.Key + ".zip");
                    string target = Path.Combine(environmentDirectory, item.Key);
                    if (!DownloadFile(item.Value, zipPath))
                    {
                        success = false;
                        continue;
                    }

                    try
                    {
                        if (Directory.Exists(target)) Directory.Delete(target, true);
                        Directory.CreateDirectory(target);
                        ExtractZipSafely(zipPath, target);
                        File.WriteAllText(marker, "CC0 asset archive installed by CommunityAssetInstaller.\n");
                    }
                    catch (Exception exception)
                    {
                        success = false;
                        Debug.LogWarning($"Could not extract {item.Key}: {exception.Message}");
                    }
                }
            }
            finally
            {
                if (showProgress) EditorUtility.ClearProgressBar();
            }

            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
            return success;
        }

        private static bool DownloadFile(string url, string destination)
        {
            try
            {
                Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? Application.dataPath);
                string temporary = destination + ".download";
                if (File.Exists(temporary)) File.Delete(temporary);
                using var client = new WebClient();
                client.Headers[HttpRequestHeader.UserAgent] = "NeonRift-Unity-Asset-Installer/1.0";
                client.DownloadFile(url, temporary);
                if (File.Exists(destination)) File.Delete(destination);
                File.Move(temporary, destination);
                Debug.Log($"Downloaded CC0 asset: {Path.GetFileName(destination)}");
                return true;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"CC0 asset download failed ({url}): {exception.Message}");
                return false;
            }
        }

        private static void ExtractZipSafely(string archivePath, string targetDirectory)
        {
            string fullTarget = Path.GetFullPath(targetDirectory) + Path.DirectorySeparatorChar;
            using ZipArchive archive = ZipFile.OpenRead(archivePath);
            foreach (ZipArchiveEntry entry in archive.Entries)
            {
                string destination = Path.GetFullPath(Path.Combine(targetDirectory, entry.FullName));
                if (!destination.StartsWith(fullTarget, StringComparison.Ordinal))
                {
                    throw new InvalidDataException("Archive entry attempted to leave the target directory.");
                }

                if (string.IsNullOrEmpty(entry.Name))
                {
                    Directory.CreateDirectory(destination);
                    continue;
                }

                Directory.CreateDirectory(Path.GetDirectoryName(destination) ?? targetDirectory);
                entry.ExtractToFile(destination, true);
            }
        }
    }
}
