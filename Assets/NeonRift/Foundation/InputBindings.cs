using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NeonRift
{
    public enum PlayerAction
    {
        MoveUp,
        MoveDown,
        MoveLeft,
        MoveRight,
        Light,
        Heavy,
        Special,
        Jump,
        DashGuard
    }

    public static class InputBindings
    {
        private const string PreferencePrefix = "NeonRift.Input";
        private const int PlayerCount = 2;

        private static readonly Key[,] Defaults =
        {
            {
                Key.UpArrow, Key.DownArrow, Key.LeftArrow, Key.RightArrow,
                Key.Z, Key.X, Key.C, Key.V, Key.B
            },
            {
                Key.W, Key.S, Key.A, Key.D,
                Key.F, Key.G, Key.H, Key.R, Key.T
            }
        };

        private static readonly IReadOnlyDictionary<Key, string> KeyLabels = new Dictionary<Key, string>
        {
            [Key.UpArrow] = "↑",
            [Key.DownArrow] = "↓",
            [Key.LeftArrow] = "←",
            [Key.RightArrow] = "→",
            [Key.Space] = "SPACE",
            [Key.Enter] = "ENTER",
            [Key.NumpadEnter] = "NUM ENTER",
            [Key.LeftShift] = "L SHIFT",
            [Key.RightShift] = "R SHIFT",
            [Key.LeftCtrl] = "L CTRL",
            [Key.RightCtrl] = "R CTRL",
            [Key.LeftAlt] = "L ALT",
            [Key.RightAlt] = "R ALT"
        };

        public static Key Get(int player, PlayerAction action)
        {
            ValidatePlayer(player);
            ValidateAction(action);

            Key fallback = Defaults[player, (int)action];
            int stored = PlayerPrefs.GetInt(PreferenceKey(player, action), (int)fallback);
            Key key = (Key)stored;
            return IsValidKey(key) ? key : fallback;
        }

        public static void Set(int player, PlayerAction action, Key key)
        {
            ValidatePlayer(player);
            ValidateAction(action);
            if (!IsBindable(key))
            {
                throw new ArgumentException($"Key '{key}' cannot be assigned.", nameof(key));
            }

            Key previous = Get(player, action);
            PlayerAction? conflictingAction = FindAction(player, key, action);
            PlayerPrefs.SetInt(PreferenceKey(player, action), (int)key);

            if (conflictingAction.HasValue)
            {
                PlayerPrefs.SetInt(PreferenceKey(player, conflictingAction.Value), (int)previous);
            }

            PlayerPrefs.Save();
        }

        public static bool Held(Keyboard keyboard, int player, PlayerAction action)
        {
            if (keyboard == null) return false;
            return keyboard[Get(player, action)].isPressed;
        }

        public static bool Pressed(Keyboard keyboard, int player, PlayerAction action)
        {
            if (keyboard == null) return false;
            return keyboard[Get(player, action)].wasPressedThisFrame;
        }

        public static string Label(int player, PlayerAction action)
        {
            return FormatKey(Get(player, action));
        }

        public static void ResetPlayer(int player)
        {
            ValidatePlayer(player);
            foreach (PlayerAction action in Enum.GetValues(typeof(PlayerAction)))
            {
                PlayerPrefs.DeleteKey(PreferenceKey(player, action));
            }
            PlayerPrefs.Save();
        }

        public static void ResetAll()
        {
            for (int player = 0; player < PlayerCount; player++)
            {
                ResetPlayer(player);
            }
        }

        public static bool IsBindable(Key key)
        {
            return IsValidKey(key) && key != Key.Escape && key != Key.F11;
        }

        private static PlayerAction? FindAction(int player, Key key, PlayerAction except)
        {
            foreach (PlayerAction action in Enum.GetValues(typeof(PlayerAction)))
            {
                if (action != except && Get(player, action) == key)
                {
                    return action;
                }
            }
            return null;
        }

        private static bool IsValidKey(Key key)
        {
            return key != Key.None && Enum.IsDefined(typeof(Key), key);
        }

        private static string PreferenceKey(int player, PlayerAction action)
        {
            return $"{PreferencePrefix}.P{player + 1}.{action}";
        }

        private static void ValidatePlayer(int player)
        {
            if (player < 0 || player >= PlayerCount)
            {
                throw new ArgumentOutOfRangeException(nameof(player), player, "Only players 0 and 1 are supported.");
            }
        }

        private static void ValidateAction(PlayerAction action)
        {
            if (!Enum.IsDefined(typeof(PlayerAction), action))
            {
                throw new ArgumentOutOfRangeException(nameof(action), action, "Unknown player action.");
            }
        }

        private static string FormatKey(Key key)
        {
            return KeyLabels.TryGetValue(key, out string label)
                ? label
                : key.ToString().ToUpperInvariant();
        }
    }
}
