using System.Collections.Generic;
using UnityEngine;
#if ENABLE_INPUT_SYSTEM
using UnityEngine.InputSystem;
#endif

namespace Riftbound
{
    public sealed class PlayerController : MonoBehaviour
    {
        private GameBootstrap game;
        private CharacterController controller;
        private PlayerBuild cardBuild;
        private PlayerBuild build;
        private ItemInstance equippedWeapon;
        private ItemInstance equippedArmor;
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
        public bool CombatEnabled => combatEnabled;
        public string CurrentWeapon => ItemText.PlainTitle(equippedWeapon);
        public string CurrentArmor => equippedArmor == null
            ? "Keine Rüstung"
            : ItemText.PlainTitle(equippedArmor);
        public string EquippedWeaponId => equippedWeapon?.instanceId;
        public string EquippedArmorId => equippedArmor?.instanceId;

        public void Initialize(GameBootstrap bootstrap)
        {
            game = bootstrap;
            controller = gameObject.AddComponent<CharacterController>();
            controller.radius = .45f;
            controller.height = 1.8f;
            controller.center = new Vector3(0f, .9f, 0f);
            cardBuild = PlayerBuild.Default;
            build = cardBuild;
            health = build.maxHealth;
        }

        public void ResetForNewRun(ItemInstance starterWeapon)
        {
            cardBuild = PlayerBuild.Default;
            equippedWeapon = starterWeapon?.Clone() ?? LootGenerator.CreateStarterWeapon();
            equippedArmor = null;
            nextAttack = nextAbility = nextDash = dashUntil = 0f;
            invulnerable = false;
            combatEnabled = true;
            RebuildDerivedStats(false);
            health = build.maxHealth;
            game.ReportHealth(health, build.maxHealth);
            game.ReportEquipment(CurrentWeapon, CurrentArmor);
        }

        public void SetCombatEnabled(bool value)
        {
            combatEnabled = value;
            if (!value) SetTouchMove(Vector2.zero);
        }

        public void SetTouchMove(Vector2 value)
        {
            touchMove = Vector2.ClampMagnitude(value, 1f);
        }

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
                if (Keyboard.current.iKey.wasPressedThisFrame) game.OpenInventoryFromHud();
            }
#endif

            if (Time.time < dashUntil)
            {
                controller.Move(dashDirection * 11f * Time.deltaTime);
                ClampToArena();
                return;
            }

            invulnerable = false;
            var movement = new Vector3(input.x, 0f, input.y) * build.moveSpeed;
            controller.Move(movement * Time.deltaTime);
            ClampToArena();

            if (movement.sqrMagnitude > .01f)
                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    Quaternion.LookRotation(movement),
                    16f * Time.deltaTime);
        }

        public void Attack()
        {
            if (!combatEnabled || Time.time < nextAttack) return;
            nextAttack = Time.time + Mathf.Max(.12f, build.attackRate);

            var center = transform.position + transform.forward * (weaponRange * .65f);
            var hits = Physics.OverlapSphere(center, weaponRange, ~0, QueryTriggerInteraction.Collide);
            var damaged = new HashSet<EnemyController>();
            foreach (var hit in hits)
            {
                var enemy = hit.GetComponent<EnemyController>();
                if (enemy != null && damaged.Add(enemy)) enemy.TakeDamage(build.damage);
            }

            Pulse(new Color(.2f, .95f, 1f), center, .35f, .4f);
        }

        public void Ability()
        {
            if (!combatEnabled || Time.time < nextAbility) return;
            nextAbility = Time.time + Mathf.Max(.5f, build.abilityCooldown);
            Projectile.Spawn(
                transform.position + Vector3.up * .7f + transform.forward * .7f,
                transform.forward,
                build.damage * 1.8f,
                true);
        }

        public void Dash()
        {
            if (!combatEnabled || Time.time < nextDash) return;
            nextDash = Time.time + 1.2f;
            dashUntil = Time.time + .22f;
            dashDirection = transform.forward;
            if (touchMove.sqrMagnitude > .1f)
                dashDirection = new Vector3(touchMove.x, 0f, touchMove.y).normalized;
            invulnerable = true;
        }

        public void ApplyCard(CardDefinition card)
        {
            if (card == null) return;
            cardBuild = RunPlanner.ApplyCard(cardBuild, card);
            RebuildDerivedStats(true);
        }

        public bool EquipItem(ItemInstance item)
        {
            if (item == null) return false;

            if (item.kind == ItemKind.Weapon)
                equippedWeapon = item.Clone();
            else
                equippedArmor = item.Clone();

            RebuildDerivedStats(true);
            game.ReportEquipment(CurrentWeapon, CurrentArmor);
            return true;
        }

        public bool IsEquipped(string instanceId)
        {
            if (string.IsNullOrEmpty(instanceId)) return false;
            return equippedWeapon?.instanceId == instanceId ||
                   equippedArmor?.instanceId == instanceId;
        }

        public float Heal(float amount)
        {
            if (amount <= 0f) return 0f;
            var before = health;
            health = Mathf.Min(build.maxHealth, health + amount);
            game.ReportHealth(health, build.maxHealth);
            return health - before;
        }

        public void TakeDamage(float amount)
        {
            if (!combatEnabled || invulnerable || health <= 0f) return;
            var final = amount * build.incomingDamageMultiplier * (1f - build.damageReduction);
            health = Mathf.Max(0f, health - final);
            game.ReportHealth(health, build.maxHealth);
            if (health <= 0f) game.PlayerDied();
        }

        private void RebuildDerivedStats(bool preserveMissingHealth)
        {
            var previousMax = build.maxHealth <= 0f ? cardBuild.maxHealth : build.maxHealth;
            var missingHealth = Mathf.Max(0f, previousMax - health);
            build = cardBuild;

            if (equippedWeapon != null)
            {
                var weapon = GameCatalog.Weapons[equippedWeapon.catalogIndex];
                var cardDamageMultiplier = cardBuild.damage / PlayerBuild.Default.damage;
                var cardAttackRateMultiplier = cardBuild.attackRate / PlayerBuild.Default.attackRate;
                build.damage = weapon.damage * equippedWeapon.powerMultiplier * cardDamageMultiplier;
                build.attackRate = Mathf.Max(.12f, weapon.attackRate * cardAttackRateMultiplier);
                weaponRange = weapon.range * (1f + (equippedWeapon.powerMultiplier - 1f) * .15f);
                if (equippedWeapon.rarity == ItemRarity.Cursed)
                    build.incomingDamageMultiplier *= 1.12f;
            }

            if (equippedArmor != null)
            {
                var armor = GameCatalog.Armors[equippedArmor.catalogIndex];
                build.maxHealth += armor.maxHealth * equippedArmor.powerMultiplier;
                build.damageReduction = Mathf.Clamp01(
                    build.damageReduction + armor.damageReduction * equippedArmor.powerMultiplier);
                if (equippedArmor.rarity == ItemRarity.Cursed)
                    build.incomingDamageMultiplier *= 1.12f;
            }

            if (preserveMissingHealth)
                health = Mathf.Clamp(build.maxHealth - missingHealth, 1f, build.maxHealth);

            game?.ReportHealth(health, build.maxHealth);
        }

        private void ClampToArena()
        {
            var position = transform.position;
            position.x = Mathf.Clamp(position.x, -4f, 4f);
            position.z = Mathf.Clamp(position.z, -2.6f, 4.6f);
            position.y = 1f;
            transform.position = position;
        }

        public static void Pulse(Color color, Vector3 position, float lifetime, float scale)
        {
            var pulse = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            pulse.name = "CombatPulse";
            pulse.transform.position = position;
            pulse.transform.localScale = Vector3.one * scale;
            pulse.GetComponent<Collider>().enabled = false;
            pulse.GetComponent<Renderer>().sharedMaterial =
                WorldFactory.GetUnlitMaterial(color);
            Destroy(pulse, lifetime);
        }
    }
}
