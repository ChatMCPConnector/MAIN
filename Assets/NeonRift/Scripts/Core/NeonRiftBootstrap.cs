using UnityEngine;

namespace NeonRift
{
    public static class NeonRiftBootstrap
    {
        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Boot()
        {
            if (Object.FindFirstObjectByType<NeonRiftGame>() != null)
            {
                return;
            }

            var root = new GameObject("Neon Rift Runtime");
            Object.DontDestroyOnLoad(root);
            root.AddComponent<NeonRiftGame>();
        }
    }
}
