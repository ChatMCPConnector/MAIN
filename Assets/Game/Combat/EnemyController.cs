using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Riftbound
{
    public sealed class EnemyController : MonoBehaviour
    {
        private GameBootstrap game;
        private EnemyKind kind;
        private EncounterTuning tuning;
        private float health;
        private float maxHealth;
        private float damage;
        private float moveSpeed;
        private float baseMoveSpeed;
        private float nextAttack;
        private float nextSpecial;
        private int bossPhase = 1;
        private bool specialActive;
        private bool dead;

        public void Initialize(GameBootstrap bootstrap, EnemyKind enemyKind, float scale)
        {
            game = bootstrap;
            kind = enemyKind;
            tuning = EncounterDirector.Create(bootstrap.Seed, bootstrap.RoomIndex);
            maxHealth = BaseHealth(kind) * scale * tuning.EnemyHealthMultiplier;
            health = maxHealth;
            damage = BaseDamage(kind) * scale * tuning.EnemyDamageMultiplier;
            baseMoveSpeed = BaseMoveSpeed(kind) * tuning.EnemySpeedMultiplier;
            moveSpeed = baseMoveSpeed;

            var hitCollider = gameObject.AddComponent<CapsuleCollider>();
            hitCollider.isTrigger = false;
            hitCollider.radius = kind == EnemyKind.Boss ? .9f : .5f;
            hitCollider.height = kind == EnemyKind.Boss ? 2.5f : 1.8f;
        }

        private void Update()
        {
            if (dead) return;
            var player = game.Player;
            if (player == null || player.Health <= 0f) return;

            var delta = player.transform.position - transform.position;
            delta.y = 0f;
            var distance = delta.magnitude;

            if (kind == EnemyKind.Ranged)
                UpdateRanged(player, delta, distance);
            else
                UpdateMelee(player, delta, distance);

            if (kind == EnemyKind.Boss &&
                !specialActive &&
                Time.time >= nextSpecial)
            {
                nextSpecial = Time.time + BossSpecialCooldown();
                StartCoroutine(BossPattern());
            }
        }

        public void TakeDamage(float amount)
        {
            if (dead || amount <= 0f) return;
            health -= amount;
            transform.localScale *= .992f;

            if (kind == EnemyKind.Boss && health > 0f)
                UpdateBossPhase();

            if (health > 0f) return;
            dead = true;
            StopAllCoroutines();
            game.NotifyEnemyDefeated(this, kind);
            Destroy(gameObject);
        }

        private void UpdateMelee(PlayerController player, Vector3 delta, float distance)
        {
            if (distance > 1.35f)
            {
                Move(delta.normalized);
                return;
            }

            if (Time.time < nextAttack) return;
            var bossAttackRate = bossPhase == 3 ? .82f : bossPhase == 2 ? 1.02f : 1.25f;
            nextAttack = Time.time + (kind == EnemyKind.Boss ? bossAttackRate : 1f);
            player.TakeDamage(damage * (kind == EnemyKind.Boss && bossPhase == 3 ? 1.12f : 1f));
        }

        private void UpdateRanged(PlayerController player, Vector3 delta, float distance)
        {
            if (distance > 5f)
                Move(delta.normalized);
            else if (distance < 2.8f)
                Move(-delta.normalized);
            else
                transform.rotation = Quaternion.Slerp(
                    transform.rotation,
                    Quaternion.LookRotation(delta),
                    10f * Time.deltaTime);

            if (Time.time < nextAttack || distance > 6f) return;
            nextAttack = Time.time + 1.55f * tuning.SpecialCooldownMultiplier;
            Projectile.Spawn(
                transform.position + Vector3.up * .65f,
                delta.normalized,
                damage * .8f,
                false,
                tuning.ProjectileSpeedMultiplier);
        }

        private void Move(Vector3 direction)
        {
            if (direction.sqrMagnitude <= .001f) return;
            transform.position += direction * moveSpeed * Time.deltaTime;
            transform.rotation = Quaternion.Slerp(
                transform.rotation,
                Quaternion.LookRotation(direction),
                10f * Time.deltaTime);
        }

        private void UpdateBossPhase()
        {
            var ratio = maxHealth <= 0f ? 0f : health / maxHealth;
            var nextPhase = ratio <= .33f ? 3 : ratio <= .66f ? 2 : 1;
            if (nextPhase <= bossPhase) return;

            bossPhase = nextPhase;
            moveSpeed = baseMoveSpeed * (bossPhase == 3 ? 1.28f : 1.14f);
            var color = bossPhase == 3
                ? new Color(1f, .16f, .1f)
                : new Color(1f, .42f, .08f);
            var renderer = GetComponent<Renderer>();
            if (renderer != null)
                renderer.sharedMaterial = WorldFactory.GetLitMaterial(color);

            FindFirstObjectByType<TouchHud>()?.ShowMessage(
                $"BOSS-PHASE {bossPhase}\nANGRIFFSMUSTER VERÄNDERT",
                1.6f);
            PlayerController.Pulse(color, transform.position, .7f, 2.8f);
            nextSpecial = Mathf.Min(nextSpecial, Time.time + .55f);
        }

        private float BossSpecialCooldown()
        {
            var phaseMultiplier = bossPhase == 3 ? .62f : bossPhase == 2 ? .80f : 1f;
            return 4f * tuning.SpecialCooldownMultiplier * phaseMultiplier;
        }

        private IEnumerator BossPattern()
        {
            specialActive = true;
            var warningColor = bossPhase == 3
                ? new Color(1f, .05f, .05f)
                : bossPhase == 2
                    ? new Color(1f, .35f, .08f)
                    : new Color(1f, .12f, .12f);

            PlayerController.Pulse(
                warningColor,
                transform.position + Vector3.up * .15f,
                bossPhase == 3 ? .55f : .75f,
                bossPhase == 3 ? 3.2f : 2.4f);

            yield return new WaitForSeconds(bossPhase == 3 ? .5f : .72f);
            if (dead)
            {
                specialActive = false;
                yield break;
            }

            if (bossPhase == 1)
            {
                FireRadial(10, 0f, .65f);
            }
            else if (bossPhase == 2)
            {
                FireRadial(14, 0f, .68f);
                yield return new WaitForSeconds(.18f);
                FireAimedFan(5, 16f, .72f);
            }
            else
            {
                FireRadial(18, 0f, .72f);
                yield return new WaitForSeconds(.24f);
                FireRadial(18, 10f, .62f);
                FireAimedFan(7, 13f, .78f);
            }

            specialActive = false;
        }

        private void FireRadial(int count, float offsetDegrees, float damageScale)
        {
            for (var i = 0; i < count; i++)
            {
                var angle = (offsetDegrees + i * 360f / count) * Mathf.Deg2Rad;
                Projectile.Spawn(
                    transform.position + Vector3.up * .5f,
                    new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle)),
                    damage * damageScale,
                    false,
                    tuning.ProjectileSpeedMultiplier);
            }
        }

        private void FireAimedFan(int count, float stepDegrees, float damageScale)
        {
            var player = game.Player;
            if (player == null) return;

            var direction = player.transform.position - transform.position;
            direction.y = 0f;
            if (direction.sqrMagnitude <= .001f) direction = transform.forward;
            direction.Normalize();

            var center = (count - 1) * .5f;
            for (var i = 0; i < count; i++)
            {
                var rotated = Quaternion.AngleAxis((i - center) * stepDegrees, Vector3.up) * direction;
                Projectile.Spawn(
                    transform.position + Vector3.up * .55f,
                    rotated,
                    damage * damageScale,
                    false,
                    tuning.ProjectileSpeedMultiplier * 1.08f);
            }
        }

        private static float BaseHealth(EnemyKind value)
        {
            return value switch
            {
                EnemyKind.Boss => 360f,
                EnemyKind.Elite => 105f,
                EnemyKind.Ranged => 42f,
                _ => 52f
            };
        }

        private static float BaseDamage(EnemyKind value)
        {
            return value switch
            {
                EnemyKind.Boss => 20f,
                EnemyKind.Elite => 14f,
                EnemyKind.Ranged => 10f,
                _ => 9f
            };
        }

        private static float BaseMoveSpeed(EnemyKind value)
        {
            return value switch
            {
                EnemyKind.Boss => 1.35f,
                EnemyKind.Elite => 2.25f,
                EnemyKind.Ranged => 1.65f,
                _ => 1.85f
            };
        }
    }

    public sealed class Projectile : MonoBehaviour
    {
        private static readonly Stack<Projectile> Pool = new Stack<Projectile>();
        private static readonly HashSet<Projectile> Active = new HashSet<Projectile>();

        private Vector3 direction;
        private float damage;
        private float speed;
        private bool fromPlayer;
        private float deathAt;
        private bool consumed;

        public static void Spawn(
            Vector3 position,
            Vector3 direction,
            float damage,
            bool fromPlayer,
            float speedMultiplier = 1f)
        {
            var projectile = Pool.Count > 0 ? Pool.Pop() : Create();
            projectile.gameObject.SetActive(true);
            projectile.transform.position = position;
            projectile.transform.localScale = Vector3.one * (fromPlayer ? .35f : .28f);
            projectile.GetComponent<Renderer>().sharedMaterial = WorldFactory.GetUnlitMaterial(
                fromPlayer ? new Color(.1f, .9f, 1f) : new Color(1f, .15f, .15f));
            projectile.direction = direction.normalized;
            projectile.damage = damage;
            projectile.speed = (fromPlayer ? 9f : 5f) * Mathf.Max(.25f, speedMultiplier);
            projectile.fromPlayer = fromPlayer;
            projectile.deathAt = Time.time + 3f;
            projectile.consumed = false;
            Active.Add(projectile);
        }

        public static void ReleaseAllActive()
        {
            if (Active.Count == 0) return;
            var snapshot = new List<Projectile>(Active);
            foreach (var projectile in snapshot)
                if (projectile != null) projectile.Release();
            Active.Clear();
        }

        private static Projectile Create()
        {
            var go = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            go.name = "PooledProjectile";
            var collider = go.GetComponent<SphereCollider>();
            collider.isTrigger = true;

            var body = go.AddComponent<Rigidbody>();
            body.isKinematic = true;
            body.useGravity = false;
            body.collisionDetectionMode = CollisionDetectionMode.ContinuousSpeculative;

            return go.AddComponent<Projectile>();
        }

        private void Update()
        {
            transform.position += direction * speed * Time.deltaTime;
            if (Time.time >= deathAt) Release();
        }

        private void OnTriggerEnter(Collider other)
        {
            if (consumed) return;

            if (fromPlayer)
            {
                var enemy = other.GetComponent<EnemyController>();
                if (enemy == null) return;
                consumed = true;
                enemy.TakeDamage(damage);
                Release();
                return;
            }

            var player = other.GetComponent<PlayerController>();
            if (player == null) return;
            consumed = true;
            player.TakeDamage(damage);
            Release();
        }

        private void Release()
        {
            if (!gameObject.activeSelf) return;
            Active.Remove(this);
            gameObject.SetActive(false);
            Pool.Push(this);
        }
    }
}
