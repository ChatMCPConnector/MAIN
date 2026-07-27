using System;
using System.Collections;
using UnityEngine;
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.Controls;

namespace NeonRift
{
    public sealed class KeyboardRemapOverlay : MonoBehaviour
    {
        private static readonly PlayerAction[] Actions =
        {
            PlayerAction.MoveUp,
            PlayerAction.MoveDown,
            PlayerAction.MoveLeft,
            PlayerAction.MoveRight,
            PlayerAction.Light,
            PlayerAction.Heavy,
            PlayerAction.Special,
            PlayerAction.Jump,
            PlayerAction.DashGuard
        };

        private static readonly string[] ActionLabels =
        {
            "Move Up",
            "Move Down",
            "Move Left",
            "Move Right",
            "Light",
            "Heavy",
            "Special",
            "Jump",
            "Dash / Guard"
        };

        private NeonRiftGame _game;
        private int _rebindPlayer = -1;
        private PlayerAction _rebindAction;
        private string _message = "Click a key, then press its replacement.";
        private bool _stylesReady;
        private GUIStyle _titleStyle;
        private GUIStyle _headerStyle;
        private GUIStyle _labelStyle;
        private GUIStyle _buttonStyle;
        private GUIStyle _activeButtonStyle;
        private GUIStyle _smallStyle;
        private Texture2D _panelTexture;
        private Texture2D _buttonTexture;
        private Texture2D _activeTexture;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.AfterSceneLoad)]
        private static void Install()
        {
            if (FindFirstObjectByType<KeyboardRemapOverlay>() != null)
            {
                return;
            }

            var host = new GameObject("Keyboard Remapping UI");
            DontDestroyOnLoad(host);
            host.AddComponent<KeyboardRemapOverlay>();
        }

        private IEnumerator Start()
        {
            while (_game == null)
            {
                _game = NeonRiftGame.Instance ?? FindFirstObjectByType<NeonRiftGame>();
                yield return null;
            }
        }

        private void Update()
        {
            if (_rebindPlayer < 0)
            {
                return;
            }

            Keyboard keyboard = Keyboard.current;
            if (keyboard == null)
            {
                _message = "No keyboard detected. Connect a keyboard or press Escape after reconnecting.";
                return;
            }

            if (keyboard.escapeKey.wasPressedThisFrame)
            {
                _message = "Remapping cancelled.";
                FinishRebind();
                return;
            }

            foreach (KeyControl keyControl in keyboard.allKeys)
            {
                if (!keyControl.wasPressedThisFrame)
                {
                    continue;
                }

                if (!InputBindings.IsBindable(keyControl.keyCode))
                {
                    _message = $"{FormatKey(keyControl.keyCode)} is reserved. Press another key or Escape.";
                    return;
                }

                InputBindings.Set(_rebindPlayer, _rebindAction, keyControl.keyCode);
                _message = $"Saved Player {_rebindPlayer + 1} {ActionName(_rebindAction)}: {InputBindings.Label(_rebindPlayer, _rebindAction)}";
                FinishRebind();
                return;
            }
        }

        private void OnGUI()
        {
            if (_game == null || _game.Screen != GameScreen.Controls)
            {
                return;
            }

            GUI.depth = -1000;
            EnsureStyles();

            float scale = Mathf.Clamp(Mathf.Min(UnityEngine.Screen.width / 1100f, UnityEngine.Screen.height / 760f), 0.72f, 1.15f);
            float panelWidth = Mathf.Min(UnityEngine.Screen.width - 24f, 1050f * scale);
            float panelHeight = Mathf.Min(UnityEngine.Screen.height - 24f, 660f * scale);
            Rect panel = new Rect(
                (UnityEngine.Screen.width - panelWidth) * 0.5f,
                (UnityEngine.Screen.height - panelHeight) * 0.5f,
                panelWidth,
                panelHeight);

            Color previousColor = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, 0.78f);
            GUI.DrawTexture(new Rect(0f, 0f, UnityEngine.Screen.width, UnityEngine.Screen.height), Texture2D.whiteTexture);
            GUI.color = previousColor;
            GUI.DrawTexture(panel, _panelTexture, ScaleMode.StretchToFill);

            float padding = 24f * scale;
            GUI.Label(new Rect(panel.x + padding, panel.y + 16f * scale, panel.width - padding * 2f, 45f * scale),
                "KEYBOARD CONTROLS — CLICK TO REMAP", _titleStyle);

            float gap = 24f * scale;
            float columnWidth = (panel.width - padding * 2f - gap) * 0.5f;
            for (int player = 0; player < 2; player++)
            {
                DrawPlayerColumn(player, panel.x + padding + player * (columnWidth + gap), panel.y + 72f * scale, columnWidth, scale);
            }

            string footer = _rebindPlayer >= 0
                ? _message
                : $"{_message}  •  Escape returns to the main menu  •  F11 remains reserved";
            GUI.Label(new Rect(panel.x + padding, panel.yMax - 46f * scale, panel.width - padding * 2f, 30f * scale), footer, _smallStyle);
        }

        private void DrawPlayerColumn(int player, float x, float y, float width, float scale)
        {
            GUI.Label(new Rect(x, y, width, 32f * scale), $"PLAYER {player + 1}", _headerStyle);
            float rowHeight = 43f * scale;
            float labelWidth = width * 0.52f;
            for (int index = 0; index < Actions.Length; index++)
            {
                float rowY = y + 42f * scale + index * rowHeight;
                GUI.Label(new Rect(x, rowY + 5f * scale, labelWidth, 30f * scale), ActionLabels[index], _labelStyle);

                bool waiting = _rebindPlayer == player && _rebindAction == Actions[index];
                string keyText = waiting ? "PRESS A KEY…" : InputBindings.Label(player, Actions[index]);
                if (GUI.Button(
                    new Rect(x + labelWidth, rowY, width - labelWidth, 34f * scale),
                    keyText,
                    waiting ? _activeButtonStyle : _buttonStyle))
                {
                    BeginRebind(player, Actions[index]);
                }
            }

            if (GUI.Button(
                new Rect(x, y + 438f * scale, width, 38f * scale),
                "RESET PLAYER DEFAULTS",
                _buttonStyle))
            {
                InputBindings.ResetPlayer(player);
                _message = $"Player {player + 1} controls restored to defaults.";
            }
        }

        private void BeginRebind(int player, PlayerAction action)
        {
            _rebindPlayer = player;
            _rebindAction = action;
            _message = $"Player {player + 1}: press a key for {ActionName(action)}. Escape cancels.";

            // Pause NeonRiftGame's menu keyboard handling so Enter, Space and arrows
            // can be assigned without also leaving or navigating the controls screen.
            if (_game != null)
            {
                _game.enabled = false;
            }
        }

        private void FinishRebind()
        {
            _rebindPlayer = -1;
            StartCoroutine(ResumeGameOnNextFrame());
        }

        private IEnumerator ResumeGameOnNextFrame()
        {
            yield return null;
            if (_game != null)
            {
                _game.enabled = true;
            }
        }

        private static string ActionName(PlayerAction action)
        {
            int index = Array.IndexOf(Actions, action);
            return index >= 0 ? ActionLabels[index] : action.ToString();
        }

        private static string FormatKey(Key key)
        {
            return key.ToString().ToUpperInvariant();
        }

        private void EnsureStyles()
        {
            if (_stylesReady)
            {
                return;
            }

            _stylesReady = true;
            _panelTexture = MakeTexture(new Color(0.018f, 0.026f, 0.065f, 0.985f));
            _buttonTexture = MakeTexture(new Color(0.012f, 0.02f, 0.045f, 1f));
            _activeTexture = MakeTexture(new Color(0.08f, 0.24f, 0.34f, 1f));

            _titleStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 28,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter,
                normal = { textColor = new Color(0.72f, 0.96f, 1f) }
            };
            _headerStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 21,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleLeft,
                normal = { textColor = Color.white }
            };
            _labelStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 17,
                alignment = TextAnchor.MiddleLeft,
                normal = { textColor = new Color(0.84f, 0.89f, 0.98f) }
            };
            _buttonStyle = new GUIStyle(GUI.skin.button)
            {
                fontSize = 16,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleCenter,
                normal = { background = _buttonTexture, textColor = new Color(0.8f, 0.87f, 0.96f) },
                hover = { background = _activeTexture, textColor = Color.white },
                active = { background = _activeTexture, textColor = Color.white }
            };
            _activeButtonStyle = new GUIStyle(_buttonStyle)
            {
                normal = { background = _activeTexture, textColor = Color.white }
            };
            _smallStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 14,
                alignment = TextAnchor.MiddleCenter,
                wordWrap = true,
                normal = { textColor = new Color(0.72f, 0.79f, 0.9f) }
            };
        }

        private static Texture2D MakeTexture(Color color)
        {
            var texture = new Texture2D(1, 1, TextureFormat.RGBA32, false)
            {
                hideFlags = HideFlags.HideAndDontSave
            };
            texture.SetPixel(0, 0, color);
            texture.Apply();
            return texture;
        }

        private void OnDestroy()
        {
            if (_game != null)
            {
                _game.enabled = true;
            }
            if (_panelTexture != null) Destroy(_panelTexture);
            if (_buttonTexture != null) Destroy(_buttonTexture);
            if (_activeTexture != null) Destroy(_activeTexture);
        }
    }
}
