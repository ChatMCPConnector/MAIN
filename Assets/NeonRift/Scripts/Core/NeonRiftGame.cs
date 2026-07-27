using System;
using System.Collections;
using System.Collections.Generic;
using System.IO;
using System.Linq;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NeonRift
{
    public sealed class NeonRiftGame : MonoBehaviour
    {
        public static NeonRiftGame Instance { get; private set; }

        public GameScreen Screen { get; private set; } = GameScreen.MainMenu;
        public GameMode SelectedMode { get; private set; } = GameMode.StageRun;
        public ArenaCameraRig CameraRig { get; private set; }
        public IReadOnlyList<FighterController> Fighters => _fighters;

        private readonly List<FighterController> _fighters = new();
        private ArenaVisualFactory _arenaFactory;
        private Transform _matchRoot;
        private int _menuIndex;
        private int _selectedCharacter;
        private int _secondCharacter = 1;
        private int _selectedArena;
        private int _wave = 1;
        private int _score;
        private float _roundTime;
        private float _resultTimer;
        private string _resultText = string.Empty;
        private bool _stylesReady;
        private GUIStyle _titleStyle;
        private GUIStyle _subtitleStyle;
        private GUIStyle _buttonStyle;
        private GUIStyle _activeButtonStyle;
        private GUIStyle _bodyStyle;
        private GUIStyle _hudStyle;
        private GUIStyle _smallStyle;
        private Texture2D _panelTexture;
        private Texture2D _activeTexture;
        private Texture2D _darkTexture;
        private bool _smokeMode;
        private string _captureDirectory;

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }

            Instance = this;
            DontDestroyOnLoad(gameObject);
            Application.targetFrameRate = 120;
            QualitySettings.vSyncCount = 1;

            _arenaFactory = gameObject.AddComponent<ArenaVisualFactory>();
            gameObject.AddComponent<CombatEffects>();
            gameObject.AddComponent<SynthAudio>();
            _arenaFactory.Build(NeonRiftCatalog.Arenas[0], 0);
            CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();

            string[] args = Environment.GetCommandLineArgs();
            _smokeMode = args.Any(arg => string.Equals(arg, "--smoke-test", StringComparison.OrdinalIgnoreCase));
            string captureArgument = args.FirstOrDefault(arg => arg.StartsWith("--capture-dir=", StringComparison.OrdinalIgnoreCase));
            _captureDirectory = captureArgument?.Substring("--capture-dir=".Length);
            if (_smokeMode)
            {
                StartCoroutine(RunSmokeTest());
            }
            else if (args.Any(arg => string.Equals(arg, "--capture-ci", StringComparison.OrdinalIgnoreCase)))
            {
                StartCoroutine(CaptureGallery());
            }
        }

        private void Update()
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard != null && keyboard.f11Key.wasPressedThisFrame)
            {
                UnityEngine.Screen.fullScreen = !UnityEngine.Screen.fullScreen;
            }

            if (Screen == GameScreen.Playing)
            {
                _roundTime += Time.deltaTime;
                EvaluateMatch();
                if (keyboard != null && keyboard.escapeKey.wasPressedThisFrame)
                {
                    UnityEngine.Time.timeScale = 0f;
                    Screen = GameScreen.Paused;
                }
                return;
            }

            if (Screen == GameScreen.Paused)
            {
                if (keyboard != null && (keyboard.escapeKey.wasPressedThisFrame || keyboard.enterKey.wasPressedThisFrame))
                {
                    UnityEngine.Time.timeScale = 1f;
                    Screen = GameScreen.Playing;
                }
                return;
            }

            if (Screen == GameScreen.Result)
            {
                _resultTimer += Time.unscaledDeltaTime;
                if (keyboard != null && (keyboard.enterKey.wasPressedThisFrame || keyboard.spaceKey.wasPressedThisFrame))
                {
                    ReturnToMenu();
                }
                return;
            }

            if (keyboard == null) return;
            if (keyboard.upArrowKey.wasPressedThisFrame) MoveSelection(-1);
            if (keyboard.downArrowKey.wasPressedThisFrame) MoveSelection(1);
            if (keyboard.leftArrowKey.wasPressedThisFrame) MoveSelection(-1);
            if (keyboard.rightArrowKey.wasPressedThisFrame) MoveSelection(1);
            if (keyboard.enterKey.wasPressedThisFrame || keyboard.spaceKey.wasPressedThisFrame) ConfirmSelection();
            if (keyboard.escapeKey.wasPressedThisFrame) Back();
        }

        private int OptionCountForCurrentScreen()
        {
            return Screen switch
            {
                GameScreen.MainMenu => 3,
                GameScreen.ModeSelect => NeonRiftCatalog.Modes.Count,
                GameScreen.CharacterSelect => NeonRiftCatalog.Fighters.Count,
                GameScreen.ArenaSelect => NeonRiftCatalog.Arenas.Count,
                GameScreen.Controls => 1,
                _ => 1
            };
        }

        private void MoveSelection(int direction)
        {
            _menuIndex = Wrap(_menuIndex + direction, OptionCountForCurrentScreen());
            SynchronizeSelectionPreview();
        }

        private void SynchronizeSelectionPreview()
        {
            if (Screen == GameScreen.CharacterSelect)
            {
                _selectedCharacter = _menuIndex;
            }
            else if (Screen == GameScreen.ArenaSelect)
            {
                _selectedArena = _menuIndex;
                RebuildArenaPreview();
            }
        }

        private void RebuildArenaPreview()
        {
            _arenaFactory.Build(NeonRiftCatalog.Arenas[_selectedArena], _selectedArena);
            CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();
        }

        private void ConfirmSelection()
        {
            SynthAudio.Instance?.Confirm();
            switch (Screen)
            {
                case GameScreen.MainMenu:
                    if (_menuIndex == 0)
                    {
                        Screen = GameScreen.ModeSelect;
                        _menuIndex = 0;
                    }
                    else if (_menuIndex == 1)
                    {
                        Screen = GameScreen.Controls;
                        _menuIndex = 0;
                    }
                    else
                    {
                        Application.Quit();
                    }
                    break;
                case GameScreen.ModeSelect:
                    SelectedMode = (GameMode)_menuIndex;
                    Screen = GameScreen.CharacterSelect;
                    _menuIndex = _selectedCharacter;
                    break;
                case GameScreen.CharacterSelect:
                    _selectedCharacter = _menuIndex;
                    _secondCharacter = (_selectedCharacter + 1) % NeonRiftCatalog.Fighters.Count;
                    Screen = GameScreen.ArenaSelect;
                    _menuIndex = _selectedArena;
                    RebuildArenaPreview();
                    break;
                case GameScreen.ArenaSelect:
                    _selectedArena = _menuIndex;
                    StartMatch();
                    break;
                case GameScreen.Controls:
                    Screen = GameScreen.MainMenu;
                    _menuIndex = 0;
                    break;
            }
        }

        private void Back()
        {
            switch (Screen)
            {
                case GameScreen.ModeSelect:
                case GameScreen.Controls:
                    Screen = GameScreen.MainMenu;
                    _menuIndex = 0;
                    break;
                case GameScreen.CharacterSelect:
                    Screen = GameScreen.ModeSelect;
                    _menuIndex = (int)SelectedMode;
                    break;
                case GameScreen.ArenaSelect:
                    Screen = GameScreen.CharacterSelect;
                    _menuIndex = _selectedCharacter;
                    break;
            }
        }

        public void StartMatch()
        {
            ClearMatch();
            UnityEngine.Time.timeScale = 1f;
            Screen = GameScreen.Playing;
            _roundTime = 0f;
            _wave = 1;
            _score = 0;
            _resultText = string.Empty;

            _arenaFactory.Build(NeonRiftCatalog.Arenas[_selectedArena], _selectedArena);
            CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();
            _matchRoot = new GameObject("Active Match").transform;

            switch (SelectedMode)
            {
                case GameMode.LocalVersus:
                    SpawnFighter(NeonRiftCatalog.Fighters[_selectedCharacter], FighterRole.Player, 0, 0, new Vector3(-3.2f, 0.1f, -0.6f));
                    SpawnFighter(NeonRiftCatalog.Fighters[_secondCharacter], FighterRole.Player, 1, 1, new Vector3(3.2f, 0.1f, 0.6f));
                    break;
                case GameMode.TeamBattle:
                    SpawnFighter(NeonRiftCatalog.Fighters[_selectedCharacter], FighterRole.Player, 0, 0, new Vector3(-5.2f, 0.1f, -1.2f));
                    SpawnFighter(NeonRiftCatalog.Fighters[_secondCharacter], FighterRole.Player, 0, 1, new Vector3(-3.2f, 0.1f, 1.2f));
                    SpawnEnemy("Skeleton_Warrior.glb", new Vector3(4.6f, 0.1f, -1.4f), 1, false);
                    SpawnEnemy("Skeleton_Rogue.glb", new Vector3(5.8f, 0.1f, 1.4f), 1, false);
                    SpawnEnemy("Skeleton_Mage.glb", new Vector3(3.2f, 0.1f, 0f), 1, false);
                    break;
                case GameMode.Training:
                    SpawnFighter(NeonRiftCatalog.Fighters[_selectedCharacter], FighterRole.Player, 0, 0, new Vector3(-2.2f, 0.1f, 0f));
                    SpawnFighter(CreateDummySpec(), FighterRole.TrainingDummy, 1, -1, new Vector3(2.2f, 0.1f, 0f), "Skeleton_Minion.glb");
                    break;
                case GameMode.Survival:
                    SpawnFighter(NeonRiftCatalog.Fighters[_selectedCharacter], FighterRole.Player, 0, 0, new Vector3(-4f, 0.1f, 0f));
                    SpawnSurvivalWave();
                    break;
                default:
                    SpawnFighter(NeonRiftCatalog.Fighters[_selectedCharacter], FighterRole.Player, 0, 0, new Vector3(-4.5f, 0.1f, 0f));
                    SpawnStageWave();
                    break;
            }

            CameraRig?.SetTargets(_fighters);
        }

        private FighterController SpawnFighter(
            FighterSpec spec,
            FighterRole role,
            int team,
            int playerIndex,
            Vector3 position,
            string modelFile = null)
        {
            var fighterObject = new GameObject(spec.Name);
            fighterObject.transform.SetParent(_matchRoot, false);
            fighterObject.transform.position = position;
            fighterObject.AddComponent<CharacterController>();
            var fighter = fighterObject.AddComponent<FighterController>();
            fighter.Configure(spec, role, team, playerIndex, modelFile);
            fighter.Defeated += OnFighterDefeated;
            _fighters.Add(fighter);
            return fighter;
        }

        private void SpawnEnemy(string model, Vector3 position, int team, bool boss)
        {
            FighterSpec spec = boss
                ? new FighterSpec("Rift Warden", "Boss", model, new Color(0.48f, 0.08f, 0.1f), new Color(1f, 0.18f, 0.12f), 260f + _wave * 20f, 5.4f, 1.35f, 1.6f)
                : new FighterSpec("Rift Raider", "Enemy", model, new Color(0.35f, 0.08f, 0.1f), new Color(1f, 0.2f, 0.18f), 68f + _wave * 8f, 5.4f + _wave * 0.12f, 0.82f + _wave * 0.035f, 1.05f);
            SpawnFighter(spec, boss ? FighterRole.Boss : FighterRole.Enemy, team, -1, position, model);
        }

        private void SpawnStageWave()
        {
            int count = Mathf.Clamp(2 + _wave, 3, 7);
            string[] models = { "Skeleton_Warrior.glb", "Skeleton_Rogue.glb", "Skeleton_Mage.glb", "Skeleton_Minion.glb" };
            for (int i = 0; i < count; i++)
            {
                float z = Mathf.Lerp(-3.2f, 3.2f, count == 1 ? 0.5f : i / (float)(count - 1));
                bool boss = _wave % 3 == 0 && i == count - 1;
                SpawnEnemy(models[i % models.Length], new Vector3(4.2f + (i % 2) * 1.8f, 0.1f, z), 1, boss);
            }
        }

        private void SpawnSurvivalWave()
        {
            int count = Mathf.Clamp(1 + _wave, 2, 8);
            string[] models = { "Skeleton_Minion.glb", "Skeleton_Rogue.glb", "Skeleton_Warrior.glb", "Skeleton_Mage.glb" };
            for (int i = 0; i < count; i++)
            {
                float angle = i / (float)count * Mathf.PI * 2f;
                Vector3 position = new Vector3(Mathf.Cos(angle) * 6f, 0.1f, Mathf.Sin(angle) * 3.2f);
                SpawnEnemy(models[(i + _wave) % models.Length], position, 1, _wave % 5 == 0 && i == 0);
            }
        }

        private static FighterSpec CreateDummySpec()
        {
            return new FighterSpec("Training Unit", "Damage laboratory", "Skeleton_Minion.glb", new Color(0.25f, 0.3f, 0.38f), Color.cyan, 9999f, 0f, 0f, 0f);
        }

        private void OnFighterDefeated(FighterController fighter)
        {
            if (fighter.TeamId != 0) _score += fighter.Role == FighterRole.Boss ? 1000 : 120;
        }

        private void EvaluateMatch()
        {
            if (SelectedMode == GameMode.Training) return;
            int livingTeamZero = _fighters.Count(fighter => fighter != null && fighter.IsAlive && fighter.TeamId == 0);
            int livingOpponents = _fighters.Count(fighter => fighter != null && fighter.IsAlive && fighter.TeamId != 0);

            if (livingTeamZero == 0)
            {
                FinishMatch("RIFT COLLAPSE");
                return;
            }

            if (livingOpponents > 0) return;

            if (SelectedMode == GameMode.StageRun && _wave < 5)
            {
                _wave++;
                RemoveDefeatedEnemies();
                SpawnStageWave();
                CameraRig?.SetTargets(_fighters);
                return;
            }

            if (SelectedMode == GameMode.Survival)
            {
                _wave++;
                RemoveDefeatedEnemies();
                SpawnSurvivalWave();
                CameraRig?.SetTargets(_fighters);
                return;
            }

            FinishMatch(SelectedMode == GameMode.LocalVersus
                ? $"PLAYER {Mathf.Max(1, _fighters.FirstOrDefault(fighter => fighter.IsAlive)?.PlayerIndex + 1 ?? 1)} WINS"
                : "ARENA CLEARED");
        }

        private void FinishMatch(string message)
        {
            if (Screen == GameScreen.Result) return;
            EnergyProjectile.DestroyAll();
            _resultText = message;
            _resultTimer = 0f;
            Screen = GameScreen.Result;
        }

        private void RemoveDefeatedEnemies()
        {
            for (int i = _fighters.Count - 1; i >= 0; i--)
            {
                FighterController fighter = _fighters[i];
                if (fighter == null || (!fighter.IsAlive && fighter.TeamId != 0))
                {
                    if (fighter != null) Destroy(fighter.gameObject);
                    _fighters.RemoveAt(i);
                }
            }
        }

        public FighterController FindNearestOpponent(FighterController seeker)
        {
            FighterController result = null;
            float best = float.MaxValue;
            foreach (FighterController fighter in _fighters)
            {
                if (fighter == null || fighter == seeker || !fighter.IsAlive || fighter.TeamId == seeker.TeamId) continue;
                float distance = (fighter.transform.position - seeker.transform.position).sqrMagnitude;
                if (distance < best)
                {
                    best = distance;
                    result = fighter;
                }
            }
            return result;
        }

        private void ReturnToMenu()
        {
            ClearMatch();
            Screen = GameScreen.MainMenu;
            _menuIndex = 0;
            _arenaFactory.Build(NeonRiftCatalog.Arenas[0], 0);
            CameraRig = _arenaFactory.GameCamera.GetComponent<ArenaCameraRig>();
        }

        private void ClearMatch()
        {
            EnergyProjectile.DestroyAll();
            foreach (FighterController fighter in _fighters)
            {
                if (fighter != null) Destroy(fighter.gameObject);
            }
            _fighters.Clear();
            if (_matchRoot != null) Destroy(_matchRoot.gameObject);
            _matchRoot = null;
        }

        private void OnGUI()
        {
            EnsureStyles();
            DrawTopBrand();
            switch (Screen)
            {
                case GameScreen.MainMenu: DrawMainMenu(); break;
                case GameScreen.ModeSelect: DrawModeSelect(); break;
                case GameScreen.CharacterSelect: DrawCharacterSelect(); break;
                case GameScreen.ArenaSelect: DrawArenaSelect(); break;
                case GameScreen.Playing: DrawHud(); break;
                case GameScreen.Paused: DrawHud(); DrawPause(); break;
                case GameScreen.Result: DrawResult(); break;
                case GameScreen.Controls: DrawControls(); break;
            }
        }

        private void DrawTopBrand()
        {
            GUI.Label(new Rect(28f, 18f, 620f, 54f), "NEON RIFT", _titleStyle);
            GUI.Label(new Rect(31f, 67f, 520f, 28f), "ARENA BREAKERS — UNITY EDITION", _subtitleStyle);
        }

        private void DrawMainMenu()
        {
            DrawPanel(new Rect(44f, 132f, 400f, 390f));
            GUI.Label(new Rect(76f, 157f, 340f, 55f), "ENTER THE RIFT", _titleStyle);
            string[] options = { "PLAY", "CONTROLS", "QUIT" };
            for (int i = 0; i < options.Length; i++)
            {
                if (DrawMenuButton(new Rect(78f, 245f + i * 78f, 330f, 58f), options[i], i == _menuIndex))
                {
                    _menuIndex = i;
                    ConfirmSelection();
                }
            }
            GUI.Label(new Rect(78f, 485f, 330f, 28f), "Arrow keys • Enter • F11", _smallStyle);
        }

        private void DrawModeSelect()
        {
            DrawPanel(new Rect(42f, 118f, 480f, 520f));
            GUI.Label(new Rect(75f, 144f, 420f, 48f), "SELECT MODE", _titleStyle);
            for (int i = 0; i < NeonRiftCatalog.Modes.Count; i++)
            {
                if (DrawMenuButton(new Rect(75f, 215f + i * 72f, 414f, 52f), NeonRiftCatalog.Modes[i], i == _menuIndex))
                {
                    _menuIndex = i;
                    ConfirmSelection();
                }
            }
        }

        private void DrawCharacterSelect()
        {
            float width = Mathf.Min(UnityEngine.Screen.width - 56f, 1180f);
            float cardWidth = (width - 60f) / 4f;
            float startX = (UnityEngine.Screen.width - width) * 0.5f;
            GUI.Label(new Rect(startX, 112f, width, 52f), "CHOOSE YOUR BREAKER", _titleStyle);
            for (int i = 0; i < NeonRiftCatalog.Fighters.Count; i++)
            {
                FighterSpec spec = NeonRiftCatalog.Fighters[i];
                Rect rect = new Rect(startX + i * (cardWidth + 20f), 185f, cardWidth, 385f);
                GUI.DrawTexture(rect, i == _selectedCharacter ? _activeTexture : _panelTexture, ScaleMode.StretchToFill);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 22f, rect.width - 36f, 34f), spec.Name, _hudStyle);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 62f, rect.width - 36f, 48f), spec.Tagline, _bodyStyle);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 142f, rect.width - 36f, 28f), $"HP  {spec.MaxHealth:0}", _bodyStyle);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 184f, rect.width - 36f, 28f), $"SPEED  {spec.Speed:0.0}", _bodyStyle);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 226f, rect.width - 36f, 28f), $"POWER  {spec.Power:0.00}", _bodyStyle);
                GUI.Label(new Rect(rect.x + 18f, rect.y + 290f, rect.width - 36f, 40f), i == _selectedCharacter ? "▶ PLAYER 1" : "SELECT", _subtitleStyle);
                if (GUI.Button(rect, GUIContent.none, GUIStyle.none))
                {
                    _selectedCharacter = i;
                    _menuIndex = i;
                }
            }
            GUI.Label(new Rect(startX, 600f, width, 28f), "Arrow keys choose • Enter continue • Player 2 uses the next fighter", _smallStyle);
        }

        private void DrawArenaSelect()
        {
            DrawPanel(new Rect(42f, 122f, 480f, 420f));
            ArenaSpec arena = NeonRiftCatalog.Arenas[_selectedArena];
            GUI.Label(new Rect(76f, 150f, 410f, 45f), "SELECT ARENA", _titleStyle);
            GUI.Label(new Rect(76f, 235f, 410f, 46f), arena.Name, _hudStyle);
            GUI.Label(new Rect(76f, 289f, 410f, 72f), arena.Subtitle, _bodyStyle);
            if (DrawMenuButton(new Rect(76f, 409f, 410f, 58f), "START MATCH", true))
            {
                StartMatch();
            }
            GUI.Label(new Rect(76f, 486f, 410f, 28f), "Arrow keys change arena", _smallStyle);
        }

        private void DrawHud()
        {
            float cardWidth = Mathf.Min(360f, UnityEngine.Screen.width * 0.31f);
            float x = 24f;
            foreach (FighterController fighter in _fighters.Where(fighter => fighter != null && fighter.IsAlive).Take(6))
            {
                DrawFighterHud(fighter, new Rect(x, 108f, cardWidth, 68f));
                x += cardWidth + 12f;
                if (x + cardWidth > UnityEngine.Screen.width)
                {
                    x = 24f;
                }
            }

            GUI.Label(new Rect(25f, UnityEngine.Screen.height - 58f, 580f, 28f), $"{NeonRiftCatalog.Modes[(int)SelectedMode]}  •  Wave {_wave}  •  Score {_score}  •  {_roundTime:0.0}s", _smallStyle);
        }

        private void DrawFighterHud(FighterController fighter, Rect rect)
        {
            GUI.DrawTexture(rect, _panelTexture, ScaleMode.StretchToFill);
            GUI.Label(new Rect(rect.x + 12f, rect.y + 7f, rect.width - 24f, 23f), fighter.Spec.Name, _smallStyle);
            float healthRatio = Mathf.Clamp01(fighter.Health / fighter.Spec.MaxHealth);
            float energyRatio = Mathf.Clamp01(fighter.Energy / 100f);
            DrawBar(new Rect(rect.x + 12f, rect.y + 32f, rect.width - 24f, 12f), healthRatio, new Color(1f, 0.18f, 0.28f));
            DrawBar(new Rect(rect.x + 12f, rect.y + 50f, rect.width - 24f, 8f), energyRatio, new Color(0.1f, 0.8f, 1f));
        }

        private void DrawPause()
        {
            DrawFullscreenShade();
            Rect panel = CenterRect(460f, 260f);
            DrawPanel(panel);
            GUI.Label(new Rect(panel.x + 45f, panel.y + 42f, panel.width - 90f, 52f), "PAUSED", _titleStyle);
            GUI.Label(new Rect(panel.x + 45f, panel.y + 115f, panel.width - 90f, 58f), "Press Escape or Enter to continue", _bodyStyle);
            if (DrawMenuButton(new Rect(panel.x + 45f, panel.y + 180f, panel.width - 90f, 52f), "RESUME", true))
            {
                UnityEngine.Time.timeScale = 1f;
                Screen = GameScreen.Playing;
            }
        }

        private void DrawResult()
        {
            DrawFullscreenShade();
            Rect panel = CenterRect(610f, 330f);
            DrawPanel(panel);
            GUI.Label(new Rect(panel.x + 40f, panel.y + 45f, panel.width - 80f, 70f), _resultText, _titleStyle);
            GUI.Label(new Rect(panel.x + 40f, panel.y + 135f, panel.width - 80f, 35f), $"Score {_score}   Time {_roundTime:0.0}s", _hudStyle);
            GUI.Label(new Rect(panel.x + 40f, panel.y + 192f, panel.width - 80f, 35f), "Enter to return to the main menu", _bodyStyle);
        }

        private void DrawControls()
        {
            DrawPanel(new Rect(44f, 120f, 760f, 500f));
            GUI.Label(new Rect(78f, 147f, 690f, 48f), "CONTROLS", _titleStyle);
            GUI.Label(new Rect(78f, 220f, 320f, 300f),
                "PLAYER 1\n\nMove       Arrow keys\nLight      Z\nHeavy      X\nSpecial    C\nJump       V\nDash/Guard B",
                _bodyStyle);
            GUI.Label(new Rect(420f, 220f, 320f, 300f),
                "PLAYER 2\n\nMove       W A S D\nLight      F\nHeavy      G\nSpecial    H\nJump       R\nDash/Guard T",
                _bodyStyle);
            GUI.Label(new Rect(78f, 530f, 680f, 54f), "Gamepads: left stick, South/West/North/East buttons and left shoulder", _smallStyle);
        }

        private void DrawBar(Rect rect, float ratio, Color color)
        {
            GUI.DrawTexture(rect, _darkTexture, ScaleMode.StretchToFill);
            Rect fill = rect;
            fill.width *= ratio;
            Color previous = GUI.color;
            GUI.color = color;
            GUI.DrawTexture(fill, Texture2D.whiteTexture, ScaleMode.StretchToFill);
            GUI.color = previous;
        }

        private bool DrawMenuButton(Rect rect, string text, bool active)
        {
            return GUI.Button(rect, text, active ? _activeButtonStyle : _buttonStyle);
        }

        private void DrawPanel(Rect rect)
        {
            GUI.DrawTexture(rect, _panelTexture, ScaleMode.StretchToFill);
        }

        private void DrawFullscreenShade()
        {
            Color previous = GUI.color;
            GUI.color = new Color(0f, 0f, 0f, 0.68f);
            GUI.DrawTexture(new Rect(0f, 0f, UnityEngine.Screen.width, UnityEngine.Screen.height), Texture2D.whiteTexture);
            GUI.color = previous;
        }

        private void EnsureStyles()
        {
            if (_stylesReady) return;
            _stylesReady = true;
            _panelTexture = MakeTexture(new Color(0.018f, 0.026f, 0.065f, 0.93f));
            _activeTexture = MakeTexture(new Color(0.08f, 0.24f, 0.34f, 0.96f));
            _darkTexture = MakeTexture(new Color(0.005f, 0.009f, 0.02f, 0.9f));

            _titleStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 36,
                fontStyle = FontStyle.Bold,
                normal = { textColor = new Color(0.72f, 0.96f, 1f) }
            };
            _subtitleStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 16,
                fontStyle = FontStyle.Bold,
                normal = { textColor = new Color(1f, 0.33f, 0.78f) }
            };
            _buttonStyle = new GUIStyle(GUI.skin.button)
            {
                fontSize = 22,
                fontStyle = FontStyle.Bold,
                alignment = TextAnchor.MiddleLeft,
                padding = new RectOffset(24, 18, 8, 8),
                normal = { background = _darkTexture, textColor = new Color(0.76f, 0.82f, 0.92f) },
                hover = { background = _activeTexture, textColor = Color.white }
            };
            _activeButtonStyle = new GUIStyle(_buttonStyle)
            {
                normal = { background = _activeTexture, textColor = Color.white }
            };
            _bodyStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 19,
                wordWrap = true,
                normal = { textColor = new Color(0.82f, 0.88f, 0.98f) }
            };
            _hudStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 22,
                fontStyle = FontStyle.Bold,
                normal = { textColor = Color.white }
            };
            _smallStyle = new GUIStyle(GUI.skin.label)
            {
                fontSize = 14,
                normal = { textColor = new Color(0.68f, 0.75f, 0.88f) }
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

        private static Rect CenterRect(float width, float height)
        {
            return new Rect((UnityEngine.Screen.width - width) * 0.5f, (UnityEngine.Screen.height - height) * 0.5f, width, height);
        }

        private static int Wrap(int value, int count)
        {
            if (count <= 0) return 0;
            while (value < 0) value += count;
            return value % count;
        }

        private IEnumerator RunSmokeTest()
        {
            yield return null;
            SelectedMode = GameMode.Training;
            _selectedCharacter = 0;
            _selectedArena = 0;
            StartMatch();
            yield return new WaitForSecondsRealtime(1.4f);

            bool pass = _fighters.Count >= 2 && _fighters[0] != null && _fighters[1] != null;
            if (pass)
            {
                float before = _fighters[1].Health;
                _fighters[1].ReceiveDamage(12f, Vector3.right, false, false);
                pass = _fighters[1].Health < before && _fighters[0].IsAlive;
            }

            string directory = Directory.GetParent(Application.dataPath)?.FullName ?? Application.persistentDataPath;
            string path = Path.Combine(directory, "smoke-test.log");
            File.WriteAllText(path,
                $"Neon Rift Unity smoke test: {(pass ? "PASS" : "FAIL")}\n" +
                $"fighters={_fighters.Count} unity={Application.unityVersion} renderer={SystemInfo.graphicsDeviceType}\n");
            yield return null;
            Application.Quit(pass ? 0 : 1);
        }

        private IEnumerator CaptureGallery()
        {
            string directory = string.IsNullOrWhiteSpace(_captureDirectory)
                ? Path.Combine(Application.persistentDataPath, "NeonRiftScreenshots")
                : Path.GetFullPath(_captureDirectory);
            Directory.CreateDirectory(directory);

            yield return CaptureFrame(directory, "01-main-menu.png");
            Screen = GameScreen.ModeSelect;
            yield return CaptureFrame(directory, "02-mode-select.png");
            Screen = GameScreen.CharacterSelect;
            yield return CaptureFrame(directory, "03-character-select.png");
            Screen = GameScreen.ArenaSelect;
            yield return CaptureFrame(directory, "04-arena-select.png");

            SelectedMode = GameMode.StageRun;
            StartMatch();
            yield return CaptureFrame(directory, "05-combat.png", 1.2f);

            for (int i = _fighters.Count - 1; i >= 0; i--)
            {
                FighterController fighter = _fighters[i];
                if (fighter != null && fighter.TeamId != 0)
                {
                    Destroy(fighter.gameObject);
                    _fighters.RemoveAt(i);
                }
            }
            _wave = 3;
            SpawnEnemy("Skeleton_Warrior.glb", new Vector3(3.4f, 0.1f, 0f), 1, true);
            CameraRig?.SetTargets(_fighters);
            yield return CaptureFrame(directory, "06-boss.png", 0.8f);

            UnityEngine.Time.timeScale = 0f;
            Screen = GameScreen.Paused;
            yield return CaptureFrame(directory, "07-pause.png");
            UnityEngine.Time.timeScale = 1f;
            FinishMatch("ARENA CLEARED");
            yield return CaptureFrame(directory, "08-result.png");

            int count = Directory.GetFiles(directory, "*.png", SearchOption.TopDirectoryOnly).Length;
            File.WriteAllText(Path.Combine(directory, "capture.log"), $"screenshots={count} unity={Application.unityVersion}\n");
            Application.Quit(count >= 8 ? 0 : 1);
        }

        private static IEnumerator CaptureFrame(string directory, string fileName, float settleSeconds = 0.3f)
        {
            yield return new WaitForSecondsRealtime(settleSeconds);
            yield return new WaitForEndOfFrame();
            ScreenCapture.CaptureScreenshot(Path.Combine(directory, fileName));
            yield return new WaitForSecondsRealtime(0.45f);
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
            UnityEngine.Time.timeScale = 1f;
            EnergyProjectile.DestroyAll();
            if (_panelTexture != null) Destroy(_panelTexture);
            if (_activeTexture != null) Destroy(_activeTexture);
            if (_darkTexture != null) Destroy(_darkTexture);
        }
    }
}
