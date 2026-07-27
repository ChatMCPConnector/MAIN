using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.SceneManagement;

namespace NeonRift
{
    public sealed class PauseReturnController : MonoBehaviour
    {
        private static PauseReturnController _instance;
        private bool _returning;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            if (_instance != null) return;

            var controllerObject = new GameObject("Pause Return Controller");
            DontDestroyOnLoad(controllerObject);
            _instance = controllerObject.AddComponent<PauseReturnController>();
        }

        private void Update()
        {
            if (_returning || NeonRiftGame.Instance == null || NeonRiftGame.Instance.Screen != GameScreen.Paused)
            {
                return;
            }

            Keyboard keyboard = Keyboard.current;
            if (keyboard != null && keyboard.backspaceKey.wasPressedThisFrame)
            {
                StartCoroutine(ReturnToMainMenu());
            }
        }

        private void OnGUI()
        {
            if (_returning || NeonRiftGame.Instance == null || NeonRiftGame.Instance.Screen != GameScreen.Paused)
            {
                return;
            }

            GUI.depth = -100;
            float width = Mathf.Min(360f, Screen.width - 48f);
            Rect buttonRect = new Rect(
                (Screen.width - width) * 0.5f,
                Screen.height * 0.5f + 145f,
                width,
                48f);

            if (GUI.Button(buttonRect, "RETURN TO MAIN MENU  [BACKSPACE]"))
            {
                StartCoroutine(ReturnToMainMenu());
            }
        }

        private IEnumerator ReturnToMainMenu()
        {
            if (_returning) yield break;
            _returning = true;
            Time.timeScale = 1f;

            NeonRiftGame game = NeonRiftGame.Instance;
            if (game != null)
            {
                Destroy(game.gameObject);
            }

            yield return null;

            Scene activeScene = SceneManager.GetActiveScene();
            if (activeScene.buildIndex >= 0)
            {
                SceneManager.LoadScene(activeScene.buildIndex);
            }
            else if (!string.IsNullOrWhiteSpace(activeScene.name))
            {
                SceneManager.LoadScene(activeScene.name);
            }

            yield return null;
            _returning = false;
        }
    }
}
