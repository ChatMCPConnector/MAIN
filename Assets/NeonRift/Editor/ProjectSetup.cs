using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEditor.Build;
using UnityEngine;
using UnityEngine.Rendering;
using UnityEngine.Rendering.Universal;
using UnityEngine.SceneManagement;

namespace NeonRift.Editor
{
    [InitializeOnLoad]
    public static class ProjectSetup
    {
        public const string MainScenePath = "Assets/NeonRift/Scenes/Main.unity";
        private const string PipelineDirectory = "Assets/NeonRift/Rendering";
        private const string RendererPath = PipelineDirectory + "/NeonRiftRenderer.asset";
        private const string PipelinePath = PipelineDirectory + "/NeonRiftURP.asset";

        static ProjectSetup()
        {
            EditorApplication.delayCall += EnsureProjectSafe;
        }

        [MenuItem("Neon Rift/Prepare Unity project")]
        public static void EnsureProject()
        {
            Directory.CreateDirectory("Assets/NeonRift/Scenes");
            Directory.CreateDirectory(PipelineDirectory);
            AssetDatabase.Refresh();
            EnsureRenderPipeline();
            EnsureMainScene();
            ConfigurePlayerSettings();
            EditorSettings.serializationMode = SerializationMode.ForceText;
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh();
            Debug.Log("Neon Rift Unity project prepared successfully.");
        }

        private static void EnsureProjectSafe()
        {
            try
            {
                EnsureProject();
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Automatic Neon Rift project setup could not finish: {exception}");
            }
        }

        private static void EnsureMainScene()
        {
            if (!File.Exists(MainScenePath))
            {
                Scene scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                scene.name = "NeonRift";
                var marker = new GameObject("Neon Rift scene - runtime bootstrap creates the game");
                marker.transform.position = Vector3.zero;
                EditorSceneManager.SaveScene(scene, MainScenePath);
            }

            EditorBuildSettings.scenes = new[] { new EditorBuildSettingsScene(MainScenePath, true) };
        }

        private static void EnsureRenderPipeline()
        {
            UniversalRenderPipelineAsset pipeline = AssetDatabase.LoadAssetAtPath<UniversalRenderPipelineAsset>(PipelinePath);
            if (pipeline == null)
            {
                pipeline = ScriptableObject.CreateInstance<UniversalRenderPipelineAsset>();
                pipeline.name = "Neon Rift URP";
                AssetDatabase.CreateAsset(pipeline, PipelinePath);
            }

            UniversalRendererData renderer = AssetDatabase.LoadAssetAtPath<UniversalRendererData>(RendererPath);
            if (renderer == null)
            {
                renderer = pipeline.LoadBuiltinRendererData(RendererType.UniversalRenderer) as UniversalRendererData;
                if (renderer == null)
                {
                    throw new InvalidOperationException("Unity did not provide the built-in Universal Renderer data.");
                }

                renderer.name = "Neon Rift Universal Renderer";
                AssetDatabase.CreateAsset(renderer, RendererPath);
            }

            var serialized = new SerializedObject(pipeline);
            SerializedProperty rendererList = serialized.FindProperty("m_RendererDataList");
            if (rendererList != null)
            {
                rendererList.arraySize = 1;
                rendererList.GetArrayElementAtIndex(0).objectReferenceValue = renderer;
            }

            SerializedProperty defaultRenderer = serialized.FindProperty("m_DefaultRendererIndex");
            if (defaultRenderer != null) defaultRenderer.intValue = 0;
            SerializedProperty hdr = serialized.FindProperty("m_SupportsHDR");
            if (hdr != null) hdr.boolValue = true;
            SerializedProperty renderScale = serialized.FindProperty("m_RenderScale");
            if (renderScale != null) renderScale.floatValue = 1f;
            SerializedProperty shadowDistance = serialized.FindProperty("m_ShadowDistance");
            if (shadowDistance != null) shadowDistance.floatValue = 55f;
            serialized.ApplyModifiedPropertiesWithoutUndo();
            pipeline.renderScale = 1f;
            pipeline.shadowDistance = 55f;
            pipeline.useSRPBatcher = true;

            GraphicsSettings.defaultRenderPipeline = pipeline;
            QualitySettings.renderPipeline = pipeline;
            EditorUtility.SetDirty(renderer);
            EditorUtility.SetDirty(pipeline);
        }

        private static void ConfigurePlayerSettings()
        {
            PlayerSettings.companyName = "ChatMCPConnector";
            PlayerSettings.productName = "Neon Rift Arena Breakers";
            PlayerSettings.bundleVersion = "2.0.0-unity";
            PlayerSettings.runInBackground = true;
            PlayerSettings.resizableWindow = true;
            PlayerSettings.fullScreenMode = FullScreenMode.Windowed;
            PlayerSettings.defaultScreenWidth = 1280;
            PlayerSettings.defaultScreenHeight = 720;
            PlayerSettings.colorSpace = ColorSpace.Linear;
            PlayerSettings.SetScriptingBackend(NamedBuildTarget.Standalone, ScriptingImplementation.Mono2x);

            UnityEngine.Object[] settingsAssets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (settingsAssets.Length > 0)
            {
                var serialized = new SerializedObject(settingsAssets[0]);
                SerializedProperty activeInput = serialized.FindProperty("m_ActiveInputHandler");
                if (activeInput != null)
                {
                    activeInput.intValue = 1; // Input System package
                    serialized.ApplyModifiedPropertiesWithoutUndo();
                }
            }
        }
    }
}
