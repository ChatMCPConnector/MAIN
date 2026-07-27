using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.EventSystems;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem.UI;
#endif

namespace Riftbound
{
    public sealed class GameBootstrap : MonoBehaviour
    {
        private readonly List<EnemyController> enemies = new List<EnemyController>();
        private readonly List<GameObject> roomObjects = new List<GameObject>();
        private System.Random rng;
        private int[] roomPlan;
        private int roomIndex;
        private int seed;
        private int runGold;
        private PlayerController player;
        private TouchHud hud;
        private SaveData saveData;
        private bool transitioning;

        public PlayerController Player => player;
        public int RoomIndex => roomIndex;
        public int Seed => seed;
        public int RunGold => runGold;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureBootstrap()
        {
            if (FindFirstObjectByType<GameBootstrap>() != null) return;
            var root = new GameObject("Riftbound");
            DontDestroyOnLoad(root);
            root.AddComponent<GameBootstrap>();
        }

        private void Awake()
        {
            Application.targetFrameRate = 60;
            Screen.orientation = ScreenOrientation.Portrait;
            QualitySettings.vSyncCount = 0;
            saveData = SaveService.Load();
        }

        private void Start()
        {
            CreateEventSystem();
            CreateWorld();
            hud = TouchHud.Create(this);
            NewRun();
        }

        private static void CreateEventSystem()
        {
            if (FindFirstObjectByType<EventSystem>() != null) return;
            var go = new GameObject("EventSystem", typeof(EventSystem));
#if ENABLE_INPUT_SYSTEM
            go.AddComponent<InputSystemUIInputModule>();
#else
            go.AddComponent<StandaloneInputModule>();
#endif
            DontDestroyOnLoad(go);
        }

        private void CreateWorld()
        {
            var cameraObject = new GameObject("Main Camera");
            var camera = cameraObject.AddComponent<Camera>();
            camera.tag = "MainCamera";
            camera.fieldOfView = 47f;
            camera.clearFlags = CameraClearFlags.SolidColor;
            camera.backgroundColor = new Color(.035f, .045f, .075f);
            camera.transform.position = new Vector3(0f, 8.6f, -11.4f);
            camera.transform.rotation = Quaternion.Euler(25f, 0f, 0f);
            cameraObject.AddComponent<AudioListener>();

            var lightObject = new GameObject("Key Light");
            var light = lightObject.AddComponent<Light>();
            light.type = LightType.Directional;
            light.intensity = 1.2f;
            light.color = new Color(.78f, .85f, 1f);
            light.transform.rotation = Quaternion.Euler(48f, -32f, 0f);

            var fillObject = new GameObject("Fill Light");
            var fill = fillObject.AddComponent<Light>();
            fill.type = LightType.Point;
            fill.intensity = 3.5f;
            fill.range = 18f;
            fill.color = new Color(.25f, .12f, .55f);
            fillObject.transform.position = new Vector3(0f, 5f, 1f);

            var playerObject = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            playerObject.name = "Player";
            playerObject.transform.position = new Vector3(0f, 1f, -2f);
            playerObject.GetComponent<Renderer>().material = WorldFactory.CreateMaterial(new Color(.12f, .82f, 1f));
            Destroy(playerObject.GetComponent<CapsuleCollider>());
            player = playerObject.AddComponent<PlayerController>();
            player.Initialize(this);

            var cameraFollow = cameraObject.AddComponent<CameraFollow>();
            cameraFollow.target = playerObject.transform;
        }

        public void NewRun()
        {
            seed = unchecked((int)DateTime.UtcNow.Ticks);
            roomPlan = GenerateValidRun(ref seed);
            rng = new System.Random(seed);
            roomIndex = 0;
            runGold = 25;
            player.ResetForNewRun();
            saveData.lastSeed = seed;
            SaveService.Save(saveData);
            ReportGold();
            ReportEquipment(player.CurrentWeapon, player.CurrentArmor);
            LoadCurrentRoom();
        }

        private static int[] GenerateValidRun(ref int runSeed)
        {
            for (var attempt = 0; attempt < 100; attempt++)
            {
                var candidate = RunPlanner.Generate(runSeed);
                if (RunPlanner.Validate(candidate)) return candidate;
                runSeed++;
            }

            throw new InvalidOperationException("Could not generate a valid run after 100 attempts.");
        }

        private void LoadCurrentRoom()
        {
            transitioning = false;
            ClearRoom();
            player.transform.position = new Vector3(0f, 1f, -2.4f);

            var room = GameCatalog.GetRoom(roomPlan[roomIndex]);
            BuildRoom(room);
            hud.SetRoom(roomIndex + 1, roomPlan.Length, room.title, seed);

            switch (room.kind)
            {
                case RoomKind.Combat:
                case RoomKind.Elite:
                case RoomKind.Boss:
                    player.SetCombatEnabled(true);
                    SpawnWave(room);
                    hud.ShowMessage(room.kind == RoomKind.Boss ? "BOSSRAUM" :
                        room.kind == RoomKind.Elite ? "ELITE-RAUM" : "RAUM VERSIEGELT", 1.5f);
                    break;
                case RoomKind.Treasure:
                    player.SetCombatEnabled(false);
                    hud.ShowTreasure(ShopGenerator.GenerateTreasure(seed, roomIndex), ChooseTreasure);
                    break;
                case RoomKind.Merchant:
                    player.SetCombatEnabled(false);
                    hud.ShowMerchant(
                        ShopGenerator.Generate(seed, roomIndex),
                        runGold,
                        TryBuyOffer,
                        AdvanceRoom);
                    break;
                case RoomKind.Healing:
                    player.SetCombatEnabled(false);
                    var healed = player.Heal(player.MaxHealth * .35f);
                    hud.ShowContinue(
                        "HEILBRUNNEN",
                        $"Du regenerierst {Mathf.CeilToInt(healed)} Leben.",
                        AdvanceRoom);
                    break;
                default:
                    throw new ArgumentOutOfRangeException();
            }
        }

        private void BuildRoom(RoomDefinition room)
        {
            var roomColor = room.kind switch
            {
                RoomKind.Treasure => new Color(.20f, .16f, .08f),
                RoomKind.Merchant => new Color(.08f, .17f, .18f),
                RoomKind.Healing => new Color(.08f, .20f, .14f),
                RoomKind.Elite => new Color(.22f, .10f, .08f),
                RoomKind.Boss => new Color(.24f, .06f, .10f),
                _ => new Color(.11f + room.index * .008f, .12f, .17f + room.index * .01f)
            };

            roomObjects.Add(WorldFactory.CreateCube(
                "Floor",
                new Vector3(0f, -.25f, 1f),
                new Vector3(9f, .5f, 8f),
                roomColor));

            CreateWall(new Vector3(-4.65f, 1.2f, 1f), new Vector3(.3f, 3f, 8f));
            CreateWall(new Vector3(4.65f, 1.2f, 1f), new Vector3(.3f, 3f, 8f));
            CreateWall(new Vector3(0f, 1.2f, 5.15f), new Vector3(9f, 3f, .3f));
            CreateWall(new Vector3(0f, 1.2f, -3.15f), new Vector3(9f, 3f, .3f));

            for (var i = 0; i < room.obstacleCount; i++)
            {
                var x = i == 0 ? -2f : 2f;
                roomObjects.Add(WorldFactory.CreateCube(
                    "Obstacle",
                    new Vector3(x, .65f, 1f),
                    new Vector3(1.1f, 1.3f, 1.1f),
                    new Color(.24f, .25f, .31f)));
            }

            if (room.kind == RoomKind.Treasure)
                roomObjects.Add(WorldFactory.CreateCube(
                    "Chest",
                    new Vector3(0f, .55f, 2.1f),
                    new Vector3(1.6f, 1.1f, 1.1f),
                    new Color(.75f, .48f, .08f)));

            if (room.kind == RoomKind.Merchant)
                roomObjects.Add(WorldFactory.CreatePrimitive(
                    "Merchant",
                    PrimitiveType.Capsule,
                    new Vector3(0f, 1f, 2f),
                    Vector3.one * 1.2f,
                    new Color(.15f, .9f, .72f)));

            if (room.kind == RoomKind.Healing)
                roomObjects.Add(WorldFactory.CreatePrimitive(
                    "HealingWell",
                    PrimitiveType.Cylinder,
                    new Vector3(0f, .5f, 2f),
                    new Vector3(1.8f, .5f, 1.8f),
                    new Color(.12f, .9f, .5f)));
        }

        private void CreateWall(Vector3 position, Vector3 scale)
        {
            roomObjects.Add(WorldFactory.CreateCube("Wall", position, scale, new Color(.18f, .19f, .25f)));
        }

        private void SpawnWave(RoomDefinition room)
        {
            enemies.Clear();

            if (room.kind == RoomKind.Boss)
            {
                SpawnEnemy(EnemyKind.Boss, new Vector3(0f, 1.35f, 2.5f));
                return;
            }

            var count = room.kind == RoomKind.Elite ? 4 : 2 + roomIndex + room.difficulty / 2;
            for (var i = 0; i < count; i++)
            {
                var angle = i * Mathf.PI * 2f / count;
                var position = new Vector3(Mathf.Sin(angle) * 2.8f, 1f, 1.5f + Mathf.Cos(angle) * 1.8f);
                var kind = room.kind == RoomKind.Elite && i == 0
                    ? EnemyKind.Elite
                    : i % 3 == 2 ? EnemyKind.Ranged : EnemyKind.Grunt;
                SpawnEnemy(kind, position);
            }
        }

        private void SpawnEnemy(EnemyKind kind, Vector3 position)
        {
            var primitive = kind == EnemyKind.Boss ? PrimitiveType.Cylinder : PrimitiveType.Capsule;
            var color = kind switch
            {
                EnemyKind.Boss => new Color(.9f, .1f, .32f),
                EnemyKind.Elite => new Color(1f, .48f, .08f),
                EnemyKind.Ranged => new Color(.3f, .55f, 1f),
                _ => new Color(.72f, .18f, .72f)
            };

            var scale = kind == EnemyKind.Boss
                ? new Vector3(1.5f, 1.4f, 1.5f)
                : kind == EnemyKind.Elite ? Vector3.one * 1.25f : Vector3.one;

            var go = WorldFactory.CreatePrimitive(kind.ToString(), primitive, position, scale, color);
            Destroy(go.GetComponent<Collider>());
            var enemy = go.AddComponent<EnemyController>();
            enemy.Initialize(this, kind, 1f + roomIndex * .12f);
            enemies.Add(enemy);
        }

        public void NotifyEnemyDefeated(EnemyController enemy, EnemyKind kind)
        {
            enemies.Remove(enemy);
            var reward = kind switch
            {
                EnemyKind.Boss => 80,
                EnemyKind.Elite => 30,
                EnemyKind.Ranged => 9,
                _ => 7
            };

            runGold += reward;
            saveData.lifetimeGold += reward;
            ReportGold();

            if (enemies.Count == 0 && !transitioning) CompleteCombatRoom();
        }

        private void CompleteCombatRoom()
        {
            transitioning = true;
            player.SetCombatEnabled(false);
            saveData.bestRoom = Mathf.Max(saveData.bestRoom, roomIndex + 1);
            SaveService.Save(saveData);

            var room = GameCatalog.GetRoom(roomPlan[roomIndex]);
            if (room.kind == RoomKind.Boss)
            {
                saveData.completedRuns++;
                SaveService.Save(saveData);
                hud.ShowRunComplete(saveData.completedRuns, runGold, NewRun);
                return;
            }

            var rewards = DrawCards(3);
            hud.ShowRewards(rewards, card =>
            {
                player.ApplyCard(card);
                AdvanceRoom();
            });
        }

        private CardDefinition[] DrawCards(int count)
        {
            var rewards = new CardDefinition[count];
            var selected = new HashSet<int>();
            for (var i = 0; i < rewards.Length; i++)
            {
                int cardIndex;
                do cardIndex = rng.Next(GameCatalog.Cards.Length); while (!selected.Add(cardIndex));
                rewards[i] = GameCatalog.Cards[cardIndex];
            }

            return rewards;
        }

        private void ChooseTreasure(ShopOffer offer)
        {
            ApplyOffer(offer);
            AdvanceRoom();
        }

        private bool TryBuyOffer(ShopOffer offer)
        {
            if (offer == null || runGold < offer.price) return false;
            runGold -= offer.price;
            ApplyOffer(offer);
            ReportGold();
            return true;
        }

        private void ApplyOffer(ShopOffer offer)
        {
            if (offer.kind == ItemKind.Weapon)
                player.EquipWeapon(GameCatalog.Weapons[offer.catalogIndex]);
            else
                player.EquipArmor(GameCatalog.Armors[offer.catalogIndex]);

            ReportEquipment(player.CurrentWeapon, player.CurrentArmor);
            hud.ShowMessage($"AUSGERÜSTET: {offer.title}", 1.4f);
        }

        private void AdvanceRoom()
        {
            if (IsInvoking(nameof(LoadCurrentRoom))) return;
            transitioning = true;
            roomIndex++;
            Invoke(nameof(LoadCurrentRoom), .25f);
        }

        public void PlayerDied()
        {
            player.SetCombatEnabled(false);
            hud.ShowGameOver(roomIndex + 1, seed, runGold, NewRun);
        }

        public void ReportHealth(float current, float max) => hud?.SetHealth(current, max);
        public void ReportGold() => hud?.SetGold(runGold);
        public void ReportEquipment(string weapon, string armor) => hud?.SetEquipment(weapon, armor);

        private void ClearRoom()
        {
            foreach (var enemy in enemies)
                if (enemy != null) Destroy(enemy.gameObject);
            enemies.Clear();

            foreach (var item in roomObjects)
                if (item != null) Destroy(item);
            roomObjects.Clear();
            Projectile.ReleaseAllActive();
        }
    }

    public static class WorldFactory
    {
        private static readonly Dictionary<Color, Material> LitMaterials =
            new Dictionary<Color, Material>();
        private static readonly Dictionary<Color, Material> UnlitMaterials =
            new Dictionary<Color, Material>();

        public static GameObject CreateCube(string name, Vector3 position, Vector3 scale, Color color)
        {
            return CreatePrimitive(name, PrimitiveType.Cube, position, scale, color);
        }

        public static GameObject CreatePrimitive(
            string name,
            PrimitiveType primitive,
            Vector3 position,
            Vector3 scale,
            Color color)
        {
            var go = GameObject.CreatePrimitive(primitive);
            go.name = name;
            go.transform.SetPositionAndRotation(position, Quaternion.identity);
            go.transform.localScale = scale;
            go.GetComponent<Renderer>().sharedMaterial = GetLitMaterial(color);
            return go;
        }

        public static Material CreateMaterial(Color color)
        {
            return GetLitMaterial(color);
        }

        public static Material GetLitMaterial(Color color)
        {
            return GetMaterial(color, false);
        }

        public static Material GetUnlitMaterial(Color color)
        {
            return GetMaterial(color, true);
        }

        private static Material GetMaterial(Color color, bool unlit)
        {
            var cache = unlit ? UnlitMaterials : LitMaterials;
            if (cache.TryGetValue(color, out var existing) && existing != null)
                return existing;

            var shader = unlit
                ? Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color")
                : Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            var material = new Material(shader) { color = color };
            cache[color] = material;
            return material;
        }
    }
}
