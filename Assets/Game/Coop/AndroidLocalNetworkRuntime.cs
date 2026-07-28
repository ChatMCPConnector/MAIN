using UnityEngine;

namespace Riftbound
{
    public sealed class AndroidLocalNetworkRuntime : MonoBehaviour
    {
        private AndroidJavaObject multicastLock;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<AndroidLocalNetworkRuntime>() != null) return;
            var root = new GameObject("Android Local Network Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<AndroidLocalNetworkRuntime>();
        }

        private void Awake()
        {
            Application.runInBackground = true;
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                using var unityPlayer = new AndroidJavaClass("com.unity3d.player.UnityPlayer");
                using var activity = unityPlayer.GetStatic<AndroidJavaObject>("currentActivity");
                using var context = new AndroidJavaClass("android.content.Context");
                var serviceName = context.GetStatic<string>("WIFI_SERVICE");
                using var wifiManager = activity.Call<AndroidJavaObject>("getSystemService", serviceName);
                multicastLock = wifiManager.Call<AndroidJavaObject>(
                    "createMulticastLock",
                    "riftbound-local-coop");
                multicastLock.Call("setReferenceCounted", false);
                multicastLock.Call("acquire");
            }
            catch (System.Exception exception)
            {
                Debug.LogWarning($"Android multicast lock unavailable: {exception.Message}");
                multicastLock = null;
            }
#endif
        }

        private void OnDestroy()
        {
#if UNITY_ANDROID && !UNITY_EDITOR
            try
            {
                if (multicastLock != null && multicastLock.Call<bool>("isHeld"))
                    multicastLock.Call("release");
            }
            catch (System.Exception exception)
            {
                Debug.LogWarning($"Android multicast lock release failed: {exception.Message}");
            }
            finally
            {
                multicastLock?.Dispose();
                multicastLock = null;
            }
#endif
        }
    }
}
