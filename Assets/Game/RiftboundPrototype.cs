using System;
using System.Collections.Generic;
using System.IO;
using UnityEngine;
using UnityEngine.EventSystems;
using UnityEngine.UI;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
using UnityEngine.InputSystem.UI;
#endif

namespace Riftbound
{
    public enum EnemyKind { Grunt, Elite, Boss }
    public enum RewardKind { Card, Weapon, Armor }

    [Serializable]
    public sealed class CardDefinition
    {
        public string id;
        public string title;
        public string benefit;
        public string drawback;
        public float damageMultiplier = 1f;
        public float maxHealthMultiplier = 1f;
        public float moveSpeedMultiplier = 1f;
        public float cooldownMultiplier = 1f;
        public float incomingDamageMultiplier = 1f;
    }

    [Serializable]
    public sealed class WeaponDefinition
    {
        public string id;
        public string title;
        public float damage;
        public float attackRate;
        public float range;
    }

    [Serializable]
    public sealed class ArmorDefinition
    {
        public string id;
        public string title;
        public float maxHealth;
        public float damageReduction;
    }

    [Serializable]
    public struct PlayerBuild
    {
        public float maxHealth;
        public float damage;
        public float moveSpeed;
        public float attackRate;
        public float abilityCooldown;
        public float incomingDamageMultiplier;
        public float damageReduction;

        public static PlayerBuild Default => new PlayerBuild
        {
            maxHealth = 100f,
            damage = 18f,
            moveSpeed = 5.4f,
            attackRate = 0.42f,
            abilityCooldown = 4f,
            incomingDamageMultiplier = 1f,
            damageReduction = 0f
        };
    }

    public static class GameCatalog
    {
        public static readonly string[] RoomTemplates =
        {
            "Zerbrochener Vorhof", "Schmale Galerie", "Kristallgrube", "Aschenbrücke",
            "Fluchkapelle", "Versunkene Halle", "Wächterkammer", "Blutaltar",
            "Elite-Arena", "Thronsaal"
        };

        public static readonly WeaponDefinition[] Weapons =
        {
            new WeaponDefinition { id = "iron_blade", title = "Eisenklinge", damage = 18f, attackRate = .42f, range = 1.65f },
            new WeaponDefinition { id = "ash_spear", title = "Aschenspeer", damage = 15f, attackRate = .36f, range = 2.2f },
            new WeaponDefinition { id = "storm_knuckles", title = "Sturmhandschuhe", damage = 11f, attackRate = .22f, range = 1.25f },
            new WeaponDefinition { id = "grave_hammer", title = "Grabhammer", damage = 27f, attackRate = .68f, range = 1.75f },
            new WeaponDefinition { id = "void_focus", title = "Leerenfokus", damage = 21f, attackRate = .5f, range = 2.6f }
        };

        public static readonly ArmorDefinition[] Armors =
        {
            new ArmorDefinition { id = "warden_helm", title = "Wächterhelm", maxHealth = 8f, damageReduction = .02f },
            new ArmorDefinition { id = "ash_plate", title = "Aschenpanzer", maxHealth = 16f, damageReduction = .05f },
            new ArmorDefinition { id = "swift_gloves", title = "Schnelle Handschuhe", maxHealth = 4f, damageReduction = .01f },
            new ArmorDefinition { id = "rift_boots", title = "Rissstiefel", maxHealth = 6f, damageReduction = .02f },
            new ArmorDefinition { id = "blood_charm", title = "Blutamulett", maxHealth = 12f, damageReduction = .03f }
        };

        public static readonly CardDefinition[] Cards =
        {
            Card("blood_pact", "Blutpakt", "+30 % Schaden", "-20 % maximale Leben", 1.30f, .80f, 1f, 1f, 1f),
            Card("overcharge", "Überladung", "+45 % Fähigkeitsschaden", "+30 % Abklingzeit", 1.18f, 1f, 1f, 1.30f, 1f),
            Card("glass_cannon", "Glaskanone", "+40 % Schaden", "+25 % erlittener Schaden", 1.40f, 1f, 1f, 1f, 1.25f),
            Card("swift_step", "Flüchtiger Schritt", "+25 % Bewegung", "-10 % maximale Leben", 1f, .90f, 1.25f, 1f, 1f),
            Card("iron_heart", "Eisenherz", "+35 % maximale Leben", "-12 % Schaden", .88f, 1.35f, 1f, 1f, 1f),
            Card("frenzy", "Raserei", "+25 % Angriffstempo", "+10 % erlittener Schaden", 1f, 1f, 1.08f, .82f, 1.10f),
            Card("ritual_blade", "Ritualklinge", "+20 % Schaden", "-15 % Bewegung", 1.20f, 1f, .85f, 1f, 1f),
            Card("guardian_oath", "Wächterschwur", "-20 % erlittener Schaden", "-15 % Schaden", .85f, 1f, .92f, 1f, .80f),
            Card("volatile_core", "Instabiler Kern", "-25 % Fähigkeitsabklingzeit", "-15 % maximale Leben", 1f, .85f, 1f, .75f, 1f),
            Card("cursed_rebirth", "Verfluchte Wiedergeburt", "+50 % maximale Leben", "+20 % erlittener Schaden", 1f, 1.50f, .9f, 1f, 1.20f)
        };

        private static CardDefinition Card(string id, string title, string benefit, string drawback,
            float damage, float health, float move, float cooldown, float incoming)
        {
            return new CardDefinition
            {
                id = id, title = title, benefit = benefit, drawback = drawback,
                damageMultiplier = damage, maxHealthMultiplier = health,
                moveSpeedMultiplier = move, cooldownMultiplier = cooldown,
                incomingDamageMultiplier = incoming
            };
        }
    }

    public static class RunPlanner
    {
        public const int RoomCount = 6;

        public static int[] Generate(int seed)
        {
            var result = new int[RoomCount];
            var rng = new System.Random(seed);
            var used = new HashSet<int>();
            for (var i = 0; i < RoomCount - 2; i++)
            {
                int next;
                do next = rng.Next(0, 8); while (!used.Add(next));
                result[i] = next;
            }

            result[RoomCount - 2] = 8;
            result[RoomCount - 1] = 9;
            return result;
        }

        public static bool Validate(int[] rooms)
        {
            if (rooms == null || rooms.Length != RoomCount) return false;
            if (rooms[RoomCount - 2] != 8 || rooms[RoomCount - 1] != 9) return false;
            for (var i = 0; i < rooms.Length; i++)
                if (rooms[i] < 0 || rooms[i] >= GameCatalog.RoomTemplates.Length) return false;
            return true;
        }

        public static PlayerBuild ApplyCard(PlayerBuild build, CardDefinition card)
        {
            build.damage *= card.damageMultiplier;
            build.maxHealth *= card.maxHealthMultiplier;
            build.moveSpeed *= card.moveSpeedMultiplier;
            build.abilityCooldown *= card.cooldownMultiplier;
            build.incomingDamageMultiplier *= card.incomingDamageMultiplier;
            return build;
        }
    }

    [Serializable]
    public sealed class SaveData
    {
        public int version = 1;
        public int bestRoom;
        public int completedRuns;
        public int lastSeed;
    }

    public static class SaveService
    {
        private static string PathName => Path.Combine(Application.persistentDataPath, "riftbound-save.json");
        private static string BackupName => PathName + ".bak";

        public static SaveData Load()
        {
            try
            {
                if (!File.Exists(PathName)) return new SaveData();
                return JsonUtility.FromJson<SaveData>(File.ReadAllText(PathName)) ?? new SaveData();
            }
            catch
            {
                try
                {
                    return File.Exists(BackupName)
                        ? JsonUtility.FromJson<SaveData>(File.ReadAllText(BackupName)) ?? new SaveData()
                        : new SaveData();
                }
                catch { return new SaveData(); }
            }
        }

        public static void Save(SaveData data)
        {
            try
            {
                if (File.Exists(PathName)) File.Copy(PathName, BackupName, true);
                File.WriteAllText(PathName, JsonUtility.ToJson(data, true));
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Save failed: {exception.Message}");
            }
        }
    }

    public sealed class GameBootstrap : MonoBehaviour
    {
        private readonly List<EnemyController> enemies = new List<EnemyController>();
        private readonly List<GameObject> roomObjects = new List<GameObject>();
        private System.Random rng;
        private int[] roomPlan;
        private int roomIndex;
        private int seed;
        private PlayerController player;
        private TouchHud hud;
        private SaveData saveData;
        private bool transitioning;

        public PlayerController Player => player;
        public int RoomIndex => roomIndex;
        public int Seed => seed;

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

        private void CreateEventSystem()
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
            light.intensity = 1.25f;
            light.color = new Color(.78f, .85f, 1f);
            light.transform.rotation = Quaternion.Euler(48f, -32f, 0f);

            var fillObject = new GameObject("Fill Light");
            var fill = fillObject.AddComponent<Light>();
            fill.type = LightType.Point;
            fill.intensity = 4f;
            fill.range = 18f;
            fill.color = new Color(.25f, .12f, .55f);
            fillObject.transform.position = new Vector3(0f, 5f, 1f);

            var playerObject = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            playerObject.name = "Player";
            playerObject.transform.position = new Vector3(0f, 1f, -2f);
            playerObject.GetComponent<Renderer>().material = CreateMaterial(new Color(.12f, .82f, 1f));
            Destroy(playerObject.GetComponent<CapsuleCollider>());
            player = playerObject.AddComponent<PlayerController>();
            player.Initialize(this);

            var cameraFollow = cameraObject.AddComponent<CameraFollow>();
            cameraFollow.target = playerObject.transform;
        }

        public void NewRun()
        {
            seed = unchecked((int)DateTime.UtcNow.Ticks);
            rng = new System.Random(seed);
            roomPlan = RunPlanner.Generate(seed);
            if (!RunPlanner.Validate(roomPlan))
            {
                seed++;
                roomPlan = RunPlanner.Generate(seed);
            }

            roomIndex = 0;
            player.ResetForNewRun();
            saveData.lastSeed = seed;
            SaveService.Save(saveData);
            LoadCurrentRoom();
        }

        private void LoadCurrentRoom()
        {
            transitioning = false;
            ClearRoom();
            player.transform.position = new Vector3(0f, 1f, -2.4f);
            player.SetCombatEnabled(true);

            var templateIndex = roomPlan[roomIndex];
            BuildRoom(templateIndex);
            SpawnWave(templateIndex);
            hud.SetRoom(roomIndex + 1, roomPlan.Length, GameCatalog.RoomTemplates[templateIndex], seed);
            hud.ShowMessage(roomIndex == roomPlan.Length - 1 ? "BOSSRAUM" : "RAUM VERSIEGELT", 1.5f);
        }

        private void BuildRoom(int templateIndex)
        {
            var floor = CreateCube("Floor", new Vector3(0f, -.25f, 1f), new Vector3(9f, .5f, 8f),
                new Color(.11f + templateIndex * .008f, .12f, .17f + templateIndex * .01f));
            roomObjects.Add(floor);
            CreateWall(new Vector3(-4.65f, 1.2f, 1f), new Vector3(.3f, 3f, 8f));
            CreateWall(new Vector3(4.65f, 1.2f, 1f), new Vector3(.3f, 3f, 8f));
            CreateWall(new Vector3(0f, 1.2f, 5.15f), new Vector3(9f, 3f, .3f));
            CreateWall(new Vector3(0f, 1.2f, -3.15f), new Vector3(9f, 3f, .3f));

            var obstacleCount = templateIndex % 3;
            for (var i = 0; i < obstacleCount; i++)
            {
                var x = i == 0 ? -2f : 2f;
                var obstacle = CreateCube("Obstacle", new Vector3(x, .65f, 1f), new Vector3(1.1f, 1.3f, 1.1f),
                    new Color(.24f, .25f, .31f));
                roomObjects.Add(obstacle);
            }
        }

        private void CreateWall(Vector3 position, Vector3 scale)
        {
            roomObjects.Add(CreateCube("Wall", position, scale, new Color(.18f, .19f, .25f)));
        }

        private GameObject CreateCube(string objectName, Vector3 position, Vector3 scale, Color color)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Cube);
            go.name = objectName;
            go.transform.SetPositionAndRotation(position, Quaternion.identity);
            go.transform.localScale = scale;
            go.GetComponent<Renderer>().material = CreateMaterial(color);
            return go;
        }

        private static Material CreateMaterial(Color color)
        {
            var shader = Shader.Find("Universal Render Pipeline/Lit") ?? Shader.Find("Standard");
            var material = new Material(shader);
            material.color = color;
            return material;
        }

        private void SpawnWave(int templateIndex)
        {
            enemies.Clear();
            var isBoss = roomIndex == roomPlan.Length - 1;
            var isElite = roomIndex == roomPlan.Length - 2;
            if (isBoss)
            {
                SpawnEnemy(EnemyKind.Boss, new Vector3(0f, 1.35f, 2.5f));
                return;
            }

            var count = 2 + roomIndex;
            for (var i = 0; i < count; i++)
            {
                var angle = (float)(i * Math.PI * 2 / count);
                var pos = new Vector3(Mathf.Sin(angle) * 2.8f, 1f, 1.5f + Mathf.Cos(angle) * 1.8f);
                SpawnEnemy(isElite && i == 0 ? EnemyKind.Elite : EnemyKind.Grunt, pos);
            }
        }

        private void SpawnEnemy(EnemyKind kind, Vector3 position)
        {
            var primitive = kind == EnemyKind.Boss ? PrimitiveType.Cylinder : PrimitiveType.Capsule;
            var go = GameObject.CreatePrimitive(primitive);
            go.name = kind.ToString();
            go.transform.position = position;
            go.transform.localScale = kind == EnemyKind.Boss ? new Vector3(1.5f, 1.4f, 1.5f) :
                kind == EnemyKind.Elite ? Vector3.one * 1.25f : Vector3.one;
            go.GetComponent<Renderer>().material = CreateMaterial(
                kind == EnemyKind.Boss ? new Color(.9f, .1f, .32f) :
                kind == EnemyKind.Elite ? new Color(1f, .48f, .08f) : new Color(.72f, .18f, .72f));
            Destroy(go.GetComponent<Collider>());
            var enemy = go.AddComponent<EnemyController>();
            enemy.Initialize(this, kind, 1f + roomIndex * .15f);
            enemies.Add(enemy);
        }

        public void NotifyEnemyDefeated(EnemyController enemy)
        {
            enemies.Remove(enemy);
            if (enemies.Count == 0 && !transitioning) CompleteRoom();
        }

        private void CompleteRoom()
        {
            transitioning = true;
            player.SetCombatEnabled(false);
            saveData.bestRoom = Mathf.Max(saveData.bestRoom, roomIndex + 1);
            SaveService.Save(saveData);

            if (roomIndex == roomPlan.Length - 1)
            {
                saveData.completedRuns++;
                SaveService.Save(saveData);
                hud.ShowRunComplete(saveData.completedRuns, NewRun);
                return;
            }

            var rewards = new CardDefinition[3];
            var selected = new HashSet<int>();
            for (var i = 0; i < rewards.Length; i++)
            {
                int cardIndex;
                do cardIndex = rng.Next(GameCatalog.Cards.Length); while (!selected.Add(cardIndex));
                rewards[i] = GameCatalog.Cards[cardIndex];
            }

            hud.ShowRewards(rewards, ChooseCard);
        }

        private void ChooseCard(CardDefinition card)
        {
            player.ApplyCard(card);
            if (roomIndex % 2 == 1)
            {
                var weapon = GameCatalog.Weapons[rng.Next(GameCatalog.Weapons.Length)];
                player.EquipWeapon(weapon);
                hud.ShowMessage($"WAFFE: {weapon.title}", 1.4f);
            }
            else
            {
                var armor = GameCatalog.Armors[rng.Next(GameCatalog.Armors.Length)];
                player.EquipArmor(armor);
                hud.ShowMessage($"RÜSTUNG: {armor.title}", 1.4f);
            }

            roomIndex++;
            Invoke(nameof(LoadCurrentRoom), .35f);
        }

        public void PlayerDied()
        {
            player.SetCombatEnabled(false);
            hud.ShowGameOver(roomIndex + 1, seed, NewRun);
        }

        public void ReportHealth(float current, float max) => hud?.SetHealth(current, max);

        private void ClearRoom()
        {
            foreach (var enemy in enemies)
                if (enemy != null) Destroy(enemy.gameObject);
            enemies.Clear();

            foreach (var item in roomObjects)
                if (item != null) Destroy(item);
            roomObjects.Clear();
        }
    }

    public sealed class PlayerController : MonoBehaviour
    {
        private GameBootstrap game;
        private CharacterController controller;
        private PlayerBuild build;
        private Vector2 touchMove;
        private float health;
        private float nextAttack;
        private float nextAbility;
        private float dashUntil;
        private float nextDash;
        private Vector3 dashDirection;
        private bool combatEnabled;
        private bool invulnerable;
        private float weaponRange = 1.65f;

        public float Health => health;
        public float MaxHealth => build.maxHealth;

        public void Initialize(GameBootstrap bootstrap)
        {
            game = bootstrap;
            controller = gameObject.AddComponent<CharacterController>();
            controller.radius = .45f;
            controller.height = 1.8f;
            controller.center = new Vector3(0f, .9f, 0f);
            build = PlayerBuild.Default;
            health = build.maxHealth;
        }

        public void ResetForNewRun()
        {
            build = PlayerBuild.Default;
            weaponRange = GameCatalog.Weapons[0].range;
            health = build.maxHealth;
            game.ReportHealth(health, build.maxHealth);
            combatEnabled = true;
        }

        public void SetCombatEnabled(bool value) => combatEnabled = value;
        public void SetTouchMove(Vector2 value) => touchMove = Vector2.ClampMagnitude(value, 1f);

        private void Update()
        {
            if (!combatEnabled) return;
            var input = touchMove;
#if ENABLE_INPUT_SYSTEM
            if (Keyboard.current != null)
            {
                var keyboard = Vector2.zero;
                if (Keyboard.current.aKey.isPressed || Keyboard.current.leftArrowKey.isPressed) keyboard.x -= 1f;
                if (Keyboard.current.dKey.isPressed || Keyboard.current.rightArrowKey.isPressed) keyboard.x += 1f;
                if (Keyboard.current.sKey.isPressed || Keyboard.current.downArrowKey.isPressed) keyboard.y -= 1f;
                if (Keyboard.current.wKey.isPressed || Keyboard.current.upArrowKey.isPressed) keyboard.y += 1f;
                if (keyboard.sqrMagnitude > 0f) input = keyboard.normalized;
                if (Keyboard.current.spaceKey.wasPressedThisFrame) Attack();
                if (Keyboard.current.leftShiftKey.wasPressedThisFrame) Dash();
                if (Keyboard.current.eKey.wasPressedThisFrame) Ability();
            }
#endif
            if (Time.time < dashUntil)
            {
                controller.Move(dashDirection * 11f * Time.deltaTime);
                return;
            }

            invulnerable = false;
            var movement = new Vector3(input.x, 0f, input.y) * build.moveSpeed;
            controller.Move(movement * Time.deltaTime);
            var position = transform.position;
            position.x = Mathf.Clamp(position.x, -4f, 4f);
            position.z = Mathf.Clamp(position.z, -2.6f, 4.6f);
            transform.position = position;

            if (movement.sqrMagnitude > .01f)
                transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(movement), 16f * Time.deltaTime);
        }

        public void Attack()
        {
            if (!combatEnabled || Time.time < nextAttack) return;
            nextAttack = Time.time + build.attackRate;
            var center = transform.position + transform.forward * (weaponRange * .65f);
            var hits = Physics.OverlapSphere(center, weaponRange, ~0, QueryTriggerInteraction.Collide);
            foreach (var hit in hits)
            {
                var enemy = hit.GetComponent<EnemyController>();
                if (enemy != null) enemy.TakeDamage(build.damage);
            }
            Pulse(new Color(.2f, .95f, 1f), center, .35f);
        }

        public void Ability()
        {
            if (!combatEnabled || Time.time < nextAbility) return;
            nextAbility = Time.time + build.abilityCooldown;
            Projectile.Spawn(transform.position + Vector3.up * .7f + transform.forward * .7f,
                transform.forward, build.damage * 1.8f, true);
        }

        public void Dash()
        {
            if (!combatEnabled || Time.time < nextDash) return;
            nextDash = Time.time + 1.2f;
            dashUntil = Time.time + .22f;
            dashDirection = transform.forward;
            if (touchMove.sqrMagnitude > .1f) dashDirection = new Vector3(touchMove.x, 0f, touchMove.y).normalized;
            invulnerable = true;
        }

        public void ApplyCard(CardDefinition card)
        {
            var oldMax = build.maxHealth;
            build = RunPlanner.ApplyCard(build, card);
            health = Mathf.Clamp(health + (build.maxHealth - oldMax), 1f, build.maxHealth);
            game.ReportHealth(health, build.maxHealth);
        }

        public void EquipWeapon(WeaponDefinition weapon)
        {
            build.damage = Mathf.Max(build.damage, weapon.damage);
            build.attackRate = Mathf.Min(build.attackRate, weapon.attackRate);
            weaponRange = weapon.range;
        }

        public void EquipArmor(ArmorDefinition armor)
        {
            build.maxHealth += armor.maxHealth;
            build.damageReduction = Mathf.Clamp01(build.damageReduction + armor.damageReduction);
            health = Mathf.Min(build.maxHealth, health + armor.maxHealth);
            game.ReportHealth(health, build.maxHealth);
        }

        public void TakeDamage(float amount)
        {
            if (!combatEnabled || invulnerable) return;
            var final = amount * build.incomingDamageMultiplier * (1f - build.damageReduction);
            health = Mathf.Max(0f, health - final);
            game.ReportHealth(health, build.maxHealth);
            if (health <= 0f) game.PlayerDied();
        }

        private static void Pulse(Color color, Vector3 position, float lifetime)
        {
            var pulse = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            pulse.name = "HitPulse";
            pulse.transform.position = position;
            pulse.transform.localScale = Vector3.one * .4f;
            pulse.GetComponent<Collider>().enabled = false;
            var shader = Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color");
            var material = new Material(shader);
            material.color = color;
            pulse.GetComponent<Renderer>().material = material;
            Destroy(pulse, lifetime);
        }
    }

    public sealed class EnemyController : MonoBehaviour
    {
        private GameBootstrap game;
        private EnemyKind kind;
        private float health;
        private float damage;
        private float moveSpeed;
        private float nextAttack;
        private float nextSpecial;
        private Collider hitCollider;

        public void Initialize(GameBootstrap bootstrap, EnemyKind enemyKind, float scale)
        {
            game = bootstrap;
            kind = enemyKind;
            health = (kind == EnemyKind.Boss ? 330f : kind == EnemyKind.Elite ? 95f : 48f) * scale;
            damage = (kind == EnemyKind.Boss ? 20f : kind == EnemyKind.Elite ? 14f : 9f) * scale;
            moveSpeed = kind == EnemyKind.Boss ? 1.4f : kind == EnemyKind.Elite ? 2.3f : 1.8f;
            hitCollider = gameObject.AddComponent<CapsuleCollider>();
            hitCollider.isTrigger = false;
            hitCollider.radius = kind == EnemyKind.Boss ? .9f : .5f;
            hitCollider.height = kind == EnemyKind.Boss ? 2.5f : 1.8f;
        }

        private void Update()
        {
            var player = game.Player;
            if (player == null || player.Health <= 0f) return;
            var delta = player.transform.position - transform.position;
            delta.y = 0f;
            var distance = delta.magnitude;
            if (distance > 1.35f)
            {
                transform.position += delta.normalized * moveSpeed * Time.deltaTime;
                transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(delta), 10f * Time.deltaTime);
            }
            else if (Time.time >= nextAttack)
            {
                nextAttack = Time.time + (kind == EnemyKind.Boss ? 1.2f : 1f);
                player.TakeDamage(damage);
            }

            if (kind == EnemyKind.Boss && Time.time >= nextSpecial)
            {
                nextSpecial = Time.time + 3f;
                for (var i = 0; i < 8; i++)
                {
                    var angle = i * Mathf.PI * 2f / 8f;
                    Projectile.Spawn(transform.position + Vector3.up * .5f,
                        new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle)), damage * .65f, false);
                }
            }
        }

        public void TakeDamage(float amount)
        {
            health -= amount;
            transform.localScale *= .97f;
            if (health > 0f) return;
            game.NotifyEnemyDefeated(this);
            Destroy(gameObject);
        }
    }

    public sealed class Projectile : MonoBehaviour
    {
        private Vector3 direction;
        private float damage;
        private bool fromPlayer;
        private float deathAt;

        public static void Spawn(Vector3 position, Vector3 direction, float damage, bool fromPlayer)
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = fromPlayer ? "PlayerProjectile" : "EnemyProjectile";
            go.transform.position = position;
            go.transform.localScale = Vector3.one * (fromPlayer ? .35f : .28f);
            var collider = go.GetComponent<SphereCollider>();
            collider.isTrigger = true;
            var body = go.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;
            body.collisionDetectionMode = CollisionDetectionMode.ContinuousSpeculative;
            var renderer = go.GetComponent<Renderer>();
            var shader = Shader.Find("Universal Render Pipeline/Unlit") ?? Shader.Find("Unlit/Color");
            var material = new Material(shader);
            material.color = fromPlayer ? new Color(.1f, .9f, 1f) : new Color(1f, .15f, .15f);
            renderer.material = material;
            var projectile = go.AddComponent<Projectile>();
            projectile.direction = direction.normalized;
            projectile.damage = damage;
            projectile.fromPlayer = fromPlayer;
            projectile.deathAt = Time.time + 3f;
        }

        private void Update()
        {
            transform.position += direction * (fromPlayer ? 9f : 5f) * Time.deltaTime;
            if (Time.time >= deathAt) Destroy(gameObject);
        }

        private void OnTriggerEnter(Collider other)
        {
            if (fromPlayer)
            {
                var enemy = other.GetComponent<EnemyController>();
                if (enemy == null) return;
                enemy.TakeDamage(damage);
                Destroy(gameObject);
            }
            else
            {
                var player = other.GetComponent<PlayerController>();
                if (player == null) return;
                player.TakeDamage(damage);
                Destroy(gameObject);
            }
        }
    }

    public sealed class CameraFollow : MonoBehaviour
    {
        public Transform target;
        private Vector3 velocity;

        private void LateUpdate()
        {
            if (target == null) return;
            var desired = new Vector3(Mathf.Clamp(target.position.x * .22f, -1f, 1f), 8.6f, -11.4f);
            transform.position = Vector3.SmoothDamp(transform.position, desired, ref velocity, .18f);
        }
    }

    public sealed class TouchHud : MonoBehaviour
    {
        private GameBootstrap game;
        private RectTransform safeRoot;
        private Text healthText;
        private Text roomText;
        private Text messageText;
        private Image healthFill;
        private GameObject overlay;
        private float messageUntil;
        private Font font;

        public static TouchHud Create(GameBootstrap bootstrap)
        {
            var root = new GameObject("Touch HUD");
            DontDestroyOnLoad(root);
            var hud = root.AddComponent<TouchHud>();
            hud.game = bootstrap;
            hud.Build();
            return hud;
        }

        private void Build()
        {
            font = Resources.GetBuiltinResource<Font>("LegacyRuntime.ttf");
            var canvas = gameObject.AddComponent<Canvas>();
            canvas.renderMode = RenderMode.ScreenSpaceOverlay;
            gameObject.AddComponent<GraphicRaycaster>();
            var scaler = gameObject.AddComponent<CanvasScaler>();
            scaler.uiScaleMode = CanvasScaler.ScaleMode.ScaleWithScreenSize;
            scaler.referenceResolution = new Vector2(1080f, 1920f);
            scaler.matchWidthOrHeight = .55f;

            safeRoot = CreateRect("SafeArea", transform, Vector2.zero, Vector2.one);
            safeRoot.gameObject.AddComponent<SafeAreaFitter>();

            var top = CreatePanel("Top", safeRoot, new Color(0f, 0f, 0f, .35f),
                new Vector2(.03f, .88f), new Vector2(.97f, .985f));
            healthText = CreateText("HP 100 / 100", top, 32, TextAnchor.MiddleLeft,
                new Vector2(.04f, .52f), new Vector2(.6f, .94f));
            roomText = CreateText("Raum", top, 28, TextAnchor.MiddleRight,
                new Vector2(.42f, .52f), new Vector2(.96f, .94f));
            var healthBack = CreatePanel("HealthBack", top, new Color(.08f, .08f, .1f, .9f),
                new Vector2(.04f, .13f), new Vector2(.96f, .43f));
            healthFill = CreateImage("HealthFill", healthBack, new Color(.1f, .85f, .55f, 1f),
                Vector2.zero, Vector2.one);
            healthFill.type = Image.Type.Filled;
            healthFill.fillMethod = Image.FillMethod.Horizontal;

            messageText = CreateText("", safeRoot, 42, TextAnchor.MiddleCenter,
                new Vector2(.08f, .70f), new Vector2(.92f, .82f));

            var stickBase = CreatePanel("MoveBase", safeRoot, new Color(.1f, .2f, .3f, .45f),
                new Vector2(.04f, .04f), new Vector2(.36f, .23f));
            var stick = stickBase.gameObject.AddComponent<VirtualStick>();
            stick.target = game.Player;
            var knob = CreatePanel("Knob", stickBase, new Color(.2f, .85f, 1f, .72f),
                new Vector2(.31f, .31f), new Vector2(.69f, .69f));
            stick.knob = knob;

            CreateActionButton("ANGRIFF", new Vector2(.66f, .04f), new Vector2(.96f, .16f), game.Player.Attack);
            CreateActionButton("DASH", new Vector2(.52f, .17f), new Vector2(.73f, .27f), game.Player.Dash);
            CreateActionButton("FÄHIGKEIT", new Vector2(.75f, .18f), new Vector2(.96f, .30f), game.Player.Ability);
        }

        private void Update()
        {
            if (messageText != null && Time.unscaledTime >= messageUntil) messageText.text = "";
        }

        public void SetHealth(float current, float max)
        {
            if (healthText == null) return;
            healthText.text = $"HP {Mathf.CeilToInt(current)} / {Mathf.CeilToInt(max)}";
            healthFill.fillAmount = max <= 0f ? 0f : current / max;
        }

        public void SetRoom(int current, int total, string roomName, int seed)
        {
            roomText.text = $"{current}/{total}  {roomName}\nSeed {seed}";
        }

        public void ShowMessage(string text, float seconds)
        {
            messageText.text = text;
            messageUntil = Time.unscaledTime + seconds;
        }

        public void ShowRewards(CardDefinition[] cards, Action<CardDefinition> selected)
        {
            ShowOverlay("WÄHLE EINE KARTE", cards.Length, i =>
            {
                selected(cards[i]);
                Destroy(overlay);
            }, i => $"{cards[i].title}\n\n<color=#6CFFB4>{cards[i].benefit}</color>\n<color=#FF718C>{cards[i].drawback}</color>");
        }

        public void ShowRunComplete(int completedRuns, Action restart)
        {
            ShowOverlay($"RUN ABGESCHLOSSEN\nSiege: {completedRuns}", 1, _ =>
            {
                restart();
                Destroy(overlay);
            }, _ => "NEUER RUN");
        }

        public void ShowGameOver(int room, int seed, Action restart)
        {
            ShowOverlay($"RUN BEENDET\nRaum {room} · Seed {seed}", 1, _ =>
            {
                restart();
                Destroy(overlay);
            }, _ => "ERNEUT VERSUCHEN");
        }

        private void ShowOverlay(string title, int buttonCount, Action<int> clicked, Func<int, string> label)
        {
            if (overlay != null) Destroy(overlay);
            overlay = new GameObject("Overlay", typeof(RectTransform), typeof(Image));
            overlay.transform.SetParent(safeRoot, false);
            var rect = overlay.GetComponent<RectTransform>();
            rect.anchorMin = Vector2.zero;
            rect.anchorMax = Vector2.one;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            overlay.GetComponent<Image>().color = new Color(.025f, .03f, .07f, .94f);
            CreateText(title, rect, 44, TextAnchor.MiddleCenter,
                new Vector2(.06f, .72f), new Vector2(.94f, .92f));

            for (var i = 0; i < buttonCount; i++)
            {
                var index = i;
                var height = buttonCount == 1 ? .18f : .16f;
                var top = .66f - i * (height + .035f);
                var bottom = top - height;
                var button = CreatePanel($"Reward {i}", rect, new Color(.12f, .18f, .28f, 1f),
                    new Vector2(.08f, bottom), new Vector2(.92f, top));
                var uiButton = button.gameObject.AddComponent<Button>();
                uiButton.targetGraphic = button.GetComponent<Image>();
                uiButton.onClick.AddListener(() => clicked(index));
                CreateText(label(i), button, buttonCount == 1 ? 34 : 30, TextAnchor.MiddleCenter,
                    new Vector2(.04f, .08f), new Vector2(.96f, .92f));
            }
        }

        private void CreateActionButton(string text, Vector2 min, Vector2 max, UnityEngine.Events.UnityAction action)
        {
            var panel = CreatePanel(text, safeRoot, new Color(.13f, .2f, .34f, .82f), min, max);
            var button = panel.gameObject.AddComponent<Button>();
            button.targetGraphic = panel.GetComponent<Image>();
            button.onClick.AddListener(action);
            CreateText(text, panel, 28, TextAnchor.MiddleCenter, Vector2.zero, Vector2.one);
        }

        private RectTransform CreatePanel(string name, Transform parent, Color color, Vector2 min, Vector2 max)
        {
            var rect = CreateRect(name, parent, min, max);
            rect.gameObject.AddComponent<Image>().color = color;
            return rect;
        }

        private Image CreateImage(string name, Transform parent, Color color, Vector2 min, Vector2 max)
        {
            var rect = CreateRect(name, parent, min, max);
            var image = rect.gameObject.AddComponent<Image>();
            image.color = color;
            return image;
        }

        private Text CreateText(string value, Transform parent, int size, TextAnchor alignment, Vector2 min, Vector2 max)
        {
            var rect = CreateRect("Text", parent, min, max);
            var text = rect.gameObject.AddComponent<Text>();
            text.font = font;
            text.fontSize = size;
            text.alignment = alignment;
            text.color = Color.white;
            text.text = value;
            text.supportRichText = true;
            text.resizeTextForBestFit = true;
            text.resizeTextMinSize = 18;
            text.resizeTextMaxSize = size;
            return text;
        }

        private static RectTransform CreateRect(string name, Transform parent, Vector2 min, Vector2 max)
        {
            var go = new GameObject(name, typeof(RectTransform));
            go.transform.SetParent(parent, false);
            var rect = go.GetComponent<RectTransform>();
            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
            return rect;
        }
    }

    public sealed class VirtualStick : MonoBehaviour, IPointerDownHandler, IPointerUpHandler, IDragHandler
    {
        public RectTransform knob;
        public PlayerController target;
        private RectTransform rect;

        private void Awake() => rect = GetComponent<RectTransform>();

        public void OnPointerDown(PointerEventData eventData) => OnDrag(eventData);

        public void OnDrag(PointerEventData eventData)
        {
            if (!RectTransformUtility.ScreenPointToLocalPointInRectangle(rect, eventData.position, eventData.pressEventCamera, out var local))
                return;
            var radius = Mathf.Min(rect.rect.width, rect.rect.height) * .35f;
            var value = Vector2.ClampMagnitude(local / radius, 1f);
            knob.anchoredPosition = value * radius * .48f;
            target.SetTouchMove(value);
        }

        public void OnPointerUp(PointerEventData eventData)
        {
            knob.anchoredPosition = Vector2.zero;
            target.SetTouchMove(Vector2.zero);
        }
    }

    public sealed class SafeAreaFitter : MonoBehaviour
    {
        private Rect lastSafeArea;
        private Vector2Int lastSize;
        private RectTransform rect;

        private void Awake()
        {
            rect = GetComponent<RectTransform>();
            Apply();
        }

        private void Update()
        {
            if (lastSafeArea != Screen.safeArea || lastSize.x != Screen.width || lastSize.y != Screen.height) Apply();
        }

        private void Apply()
        {
            var safe = Screen.safeArea;
            lastSafeArea = safe;
            lastSize = new Vector2Int(Screen.width, Screen.height);
            var min = safe.position;
            var max = safe.position + safe.size;
            min.x /= Screen.width;
            min.y /= Screen.height;
            max.x /= Screen.width;
            max.y /= Screen.height;
            rect.anchorMin = min;
            rect.anchorMax = max;
            rect.offsetMin = rect.offsetMax = Vector2.zero;
        }
    }
}
