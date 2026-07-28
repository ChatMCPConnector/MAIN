using System;
using System.IO;
using UnityEditor;
using UnityEditor.Build.Reporting;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;

namespace Riftbound.Editor
{
    public static class BuildAutomation
    {
        private const string PipelinePath = "Assets/Game/Settings/RiftboundURP.asset";
        private const string RendererPath = "Assets/Game/Settings/RiftboundRenderer.asset";

        [MenuItem("Riftbound/Build Android APK")]
        public static void BuildAndroid()
        {
            ProjectSetup.EnsureProject();
            ConfigureProject();
            EnsurePipeline();
            ProjectSetup.ValidateReadyForBuild();

#if !ENABLE_INPUT_SYSTEM
            throw new InvalidOperationException(
                "The Android build was compiled without ENABLE_INPUT_SYSTEM. " +
                "Allow Unity to finish recompiling after project setup, then run the build again.");
#endif

            var outputPath = GetArgument("-customBuildPath");
            if (string.IsNullOrWhiteSpace(outputPath))
                outputPath = "Builds/Android/Riftbound.apk";
            if (!outputPath.EndsWith(".apk", StringComparison.OrdinalIgnoreCase))
                outputPath = Path.Combine(outputPath, "Riftbound.apk");

            var directory = Path.GetDirectoryName(outputPath);
            if (!string.IsNullOrWhiteSpace(directory))
                Directory.CreateDirectory(directory);

            var options = new BuildPlayerOptions
            {
                scenes = new[] { ProjectSetup.MainScenePath },
                locationPathName = outputPath,
                target = BuildTarget.Android,
                targetGroup = BuildTargetGroup.Android,
                options = BuildOptions.None
            };

            var report = BuildPipeline.BuildPlayer(options);
            if (report.summary.result != BuildResult.Succeeded)
                throw new InvalidOperationException(
                    $"Android build failed: {report.summary.result}, errors: {report.summary.totalErrors}");

            Debug.Log($"Android APK created: {outputPath} ({report.summary.totalSize} bytes)");
        }

        private static void ConfigureProject()
        {
            PlayerSettings.companyName = "Riftbound Studio";
            PlayerSettings.productName = "Riftbound";
            PlayerSettings.SetApplicationIdentifier(
                BuildTargetGroup.Android,
                "com.chatmcpconnector.riftbound");
            PlayerSettings.bundleVersion = "1.0.2";
            PlayerSettings.Android.bundleVersionCode = 102;
            PlayerSettings.Android.minSdkVersion = AndroidSdkVersions.AndroidApiLevel26;
            PlayerSettings.Android.targetSdkVersion = AndroidSdkVersions.AndroidApiLevelAuto;
            PlayerSettings.Android.targetArchitectures = AndroidArchitecture.ARM64;
            PlayerSettings.Android.forceInternetPermission = true;
            PlayerSettings.SetScriptingBackend(
                BuildTargetGroup.Android,
                ScriptingImplementation.IL2CPP);
            PlayerSettings.defaultInterfaceOrientation = UIOrientation.Portrait;
            PlayerSettings.allowedAutorotateToLandscapeLeft = false;
            PlayerSettings.allowedAutorotateToLandscapeRight = false;
            PlayerSettings.allowedAutorotateToPortrait = true;
            PlayerSettings.allowedAutorotateToPortraitUpsideDown = false;
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.SetGraphicsAPIs(
                BuildTarget.Android,
                new[] { GraphicsDeviceType.OpenGLES3 });
            EditorUserBuildSettings.buildAppBundle = false;
        }

        private static void EnsurePipeline()
        {
            Directory.CreateDirectory("Assets/Game/Settings");

            var renderer = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(RendererPath);
            if (renderer == null)
            {
                renderer = ScriptableObject.CreateInstance<UniversalRendererData>();
                AssetDatabase.CreateAsset(renderer, RendererPath);
            }

            var pipeline = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PipelinePath);
            if (pipeline == null)
            {
                pipeline = ScriptableObject.CreateInstance<UniversalRenderPipelineAsset>();
                AssetDatabase.CreateAsset(pipeline, PipelinePath);
            }

            var serialized = new SerializedObject(pipeline);
            var list = serialized.FindProperty("m_RendererDataList");
            if (list != null)
            {
                list.arraySize = 1;
                list.GetArrayElementAtIndex(0).objectReferenceValue = renderer;
            }

            var defaultRenderer = serialized.FindProperty("m_DefaultRendererIndex");
            if (defaultRenderer != null)
                defaultRenderer.intValue = 0;
            serialized.ApplyModifiedPropertiesWithoutUndo();

            GraphicsSettings.defaultRenderPipeline = pipeline;
            QualitySettings.renderPipeline = pipeline;
            EditorUtility.SetDirty(pipeline);
            EditorUtility.SetDirty(renderer);
            AssetDatabase.SaveAssets();
        }

        private static string GetArgument(string name)
        {
            var args = Environment.GetCommandLineArgs();
            for (var i = 0; i < args.Length - 1; i++)
                if (string.Equals(
                        args[i],
                        name,
                        StringComparison.OrdinalIgnoreCase))
                    return args[i + 1];
            return null;
        }
    }
}
