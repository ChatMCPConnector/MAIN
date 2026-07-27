using System.Collections;
using System.Collections.Generic;
using UnityEngine;

namespace Riftbound
{
    public sealed class EnemyController : MonoBehaviour
    {
        private GameBootstrap game;
        private EnemyKind kind;
        private float health;
        private float damage;
        private float moveSpeed;
        private float nextAttack;
        private float nextSpecial;
        private bool dead;

        public void Initialize(GameBootstrap bootstrap, EnemyKind enemyKind, float scale)
        {
            game = bootstrap;
            kind = enemyKind;
            health = BaseHealth(kind) * scale;
            damage = BaseDamage(kind) * scale;
            moveSpeed = kind switch
            {
                EnemyKind.Boss => 1.35f,
                EnemyKind.Elite => 2.25f,
                EnemyKind.Ranged => 1.65f,
                _ => 1.85f
            };

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

            if (kind == EnemyKind.Boss && Time.time >= nextSpecial)
            {
                nextSpecial = Time.time + 4f;
                StartCoroutine(BossBurst());
            }
        }

        public void TakeDamage(float amount)
        {
            if (dead || amount <= 0f) return;
            health -= amount;
            transform.localScale *= .985f;
            if (health > 0f) return;

            dead = true;
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
            nextAttack = Time.time + (kind == EnemyKind.Boss ? 1.25f : 1f);
            player.TakeDamage(damage);
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
            nextAttack = Time.time + 1.55f;
            Projectile.Spawn(
                transform.position + Vector3.up * .65f,
                delta.normalized,
                damage * .8f,
                false);
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

        private IEnumerator BossBurst()
        {
            PlayerController.Pulse(
                new Color(1f, .12f, .12f),
                transform.position + Vector3.up * .15f,
                .85f,
                2.4f);

            yield return new WaitForSeconds(.8f);
            if (dead) yield break;

            for (var i = 0; i < 10; i++)
            {
                var angle = i * Mathf.PI * 2f / 10f;
                Projectile.Spawn(
                    transform.position + Vector3.up * .5f,
                    new Vector3(Mathf.Sin(angle), 0f, Mathf.Cos(angle)),
                    damage * .65f,
                    false);
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
    }

    public sealed class Projectile : MonoBehaviour
    {
        private static readonly Stack<Projectile> Pool = new Stack<Projectile>();
        private static readonly HashSet<Projectile> Active = new HashSet<Projectile>();

        private Vector3 direction;
        private float damage;
        private bool fromPlayer;
        private float deathAt;
        private bool consumed;

        public static void Spawn(Vector3 position, Vector3 direction, float damage, bool fromPlayer)
        {
            var projectile = Pool.Count > 0 ? Pool.Pop() : Create();
            projectile.gameObject.SetActive(true);
            projectile.transform.position = position;
            projectile.transform.localScale = Vector3.one * (fromPlayer ? .35f : .28f);
            projectile.GetComponent<Renderer>().sharedMaterial = WorldFactory.GetUnlitMaterial(
                fromPlayer ? new Color(.1f, .9f, 1f) : new Color(1f, .15f, .15f));
            projectile.direction = direction.normalized;
            projectile.damage = damage;
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
            transform.position += direction * (fromPlayer ? 9f : 5f) * Time.deltaTime;
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
