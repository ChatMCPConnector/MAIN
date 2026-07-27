using System;
using System.IO;
using System.Linq;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;

namespace NeonRift.Editor
{
    public static class BuildAutomation
    {
        private const string BuildDirectory = "build/StandaloneWindows64/NeonRift";
        private const string ExecutablePath = BuildDirectory + "/NeonRift.exe";

        [MenuItem("Neon Rift/Build portable Windows game")]
        public static void BuildWindows()
        {
            CommunityAssetInstaller.EnsureAssets(false);
            OpenAssetInstaller.EnsureAssets(false);
            ProjectSetup.EnsureProject();
            Directory.CreateDirectory(BuildDirectory);

            string[] scenes = EditorBuildSettings.scenes
                .Where(scene => scene.enabled)
                .Select(scene => scene.path)
                .ToArray();
            if (scenes.Length == 0)
            {
                throw new InvalidOperationException("No enabled Unity scene is available for the build.");
            }

            var options = new BuildPlayerOptions
            {
                scenes = scenes,
                locationPathName = ExecutablePath,
                target = BuildTarget.StandaloneWindows64,
                targetGroup = BuildTargetGroup.Standalone,
                options = BuildOptions.CleanBuildCache
            };

            BuildReport report = BuildPipeline.BuildPlayer(options);
            if (report.summary.result != BuildResult.Succeeded)
            {
                throw new InvalidOperationException($"Unity build failed: {report.summary.result} ({report.summary.totalErrors} errors)");
            }

            CopyDistributionFile("README.md", "README.txt");
            CopyDistributionFile("CONTROLS.md", "CONTROLS.txt");
            CopyDistributionFile("ASSET_SOURCES.md", "ASSET_SOURCES.txt");
            CopyDistributionFile("LICENSE", "LICENSE.txt");
            CopyDistributionFile("ThirdPartyNotices/CC0-1.0.txt", "CC0-1.0.txt");
            CopyDistributionFile("ThirdPartyNotices/glTFast-Apache-2.0.txt", "glTFast-Apache-2.0.txt");
            File.WriteAllText(Path.Combine(BuildDirectory, "VERSION.txt"),
                $"Neon Rift Arena Breakers Unity Edition\nVersion {PlayerSettings.bundleVersion}\nUnity {Application.unityVersion}\nWindows x86_64 portable build\n");
            File.WriteAllText(Path.Combine(BuildDirectory, "build-manifest.txt"),
                $"Result: {report.summary.result}\nSize: {report.summary.totalSize}\nDuration: {report.summary.totalTime}\nUnity: {Application.unityVersion}\n");

            Debug.Log($"Portable Windows build completed: {Path.GetFullPath(BuildDirectory)}");
        }

        private static void CopyDistributionFile(string source, string destinationName)
        {
            if (!File.Exists(source)) return;
            File.Copy(source, Path.Combine(BuildDirectory, destinationName), true);
        }
    }
}
