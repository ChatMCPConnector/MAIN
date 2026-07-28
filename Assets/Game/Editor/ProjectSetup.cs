using System;
using System.IO;
using UnityEditor;
using UnityEditor.SceneManagement;
using UnityEngine;
using UnityEngine.SceneManagement;

namespace Riftbound.Editor
{
    [InitializeOnLoad]
    public static class ProjectSetup
    {
        public const string MainScenePath = "Assets/Game/Scenes/Main.unity";
        private const int InputSystemOnly = 1;

        static ProjectSetup()
        {
            EditorApplication.delayCall += EnsureProjectSafe;
        }

        [MenuItem("Riftbound/Prepare Android project")]
        public static void EnsureProject()
        {
            ConfigureInputSystem();
            EnsureMainScene();
            EditorSettings.serializationMode = SerializationMode.ForceText;
            AssetDatabase.SaveAssets();
            AssetDatabase.Refresh(ImportAssetOptions.ForceSynchronousImport);
        }

        public static void ValidateReadyForBuild()
        {
            var inputHandler = FindInputHandlerProperty();
            if (inputHandler.intValue != InputSystemOnly)
                throw new InvalidOperationException(
                    "Riftbound requires the Unity Input System backend before compilation and build.");

            if (!File.Exists(MainScenePath))
                throw new FileNotFoundException("The Riftbound main scene is missing.", MainScenePath);

            var enabled = false;
            foreach (var scene in EditorBuildSettings.scenes)
            {
                if (scene.enabled && string.Equals(scene.path, MainScenePath, StringComparison.Ordinal))
                {
                    enabled = true;
                    break;
                }
            }

            if (!enabled)
                throw new InvalidOperationException("The Riftbound main scene is not enabled for builds.");
        }

        private static void EnsureProjectSafe()
        {
            try
            {
                EnsureProject();
            }
            catch (Exception exception)
            {
                Debug.LogError($"Riftbound project setup failed: {exception}");
            }
        }

        private static void ConfigureInputSystem()
        {
            var property = FindInputHandlerProperty();
            if (property.intValue == InputSystemOnly) return;

            property.intValue = InputSystemOnly;
            property.serializedObject.ApplyModifiedPropertiesWithoutUndo();
            EditorUtility.SetDirty(property.serializedObject.targetObject);
            AssetDatabase.SaveAssets();
            Debug.Log("Riftbound configured the Unity Input System as the sole input backend.");
        }

        private static SerializedProperty FindInputHandlerProperty()
        {
            var settingsAssets = AssetDatabase.LoadAllAssetsAtPath("ProjectSettings/ProjectSettings.asset");
            if (settingsAssets == null || settingsAssets.Length == 0)
                throw new InvalidOperationException("ProjectSettings.asset is unavailable.");

            var serialized = new SerializedObject(settingsAssets[0]);
            var property = serialized.FindProperty("m_ActiveInputHandler")
                           ?? serialized.FindProperty("activeInputHandler");
            if (property == null)
                throw new InvalidOperationException("Unity's active input handler setting was not found.");
            return property;
        }

        private static void EnsureMainScene()
        {
            Directory.CreateDirectory("Assets/Game/Scenes");
            if (!File.Exists(MainScenePath))
            {
                var scene = EditorSceneManager.NewScene(NewSceneSetup.EmptyScene, NewSceneMode.Single);
                scene.name = "Riftbound";
                var marker = new GameObject("Riftbound runtime bootstrap scene");
                marker.transform.position = Vector3.zero;
                EditorSceneManager.SaveScene(scene, MainScenePath);
            }

            EditorBuildSettings.scenes =
                new[] { new EditorBuildSettingsScene(MainScenePath, true) };
        }
    }
}
