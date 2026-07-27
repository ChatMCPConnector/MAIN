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
        private int networkId;
        private int bossPhase = 1;
        private bool specialActive;
        private bool replica;
        private bool dead;
        private Vector3 replicaTarget;
        private float replicaYaw;

        public int NetworkId => networkId;
        public EnemyKind Kind => kind;
        public float Health => health;
        public float MaxHealth => maxHealth;
        public int BossPhase => bossPhase;
        public bool IsReplica => replica;
        public bool IsDead => dead;

        public void Initialize(
            GameBootstrap bootstrap,
            EnemyKind enemyKind,
            float scale,
            int id,
            bool forceReplica = false)
        {
            game = bootstrap;
            kind = enemyKind;
            networkId = id;
            tuning = EncounterDirector.Create(bootstrap.Seed, bootstrap.RoomIndex);
            var players = CoopRuntimeState.ActivePlayerCount;
            maxHealth = BaseHealth(kind) *
                        scale *
                        tuning.EnemyHealthMultiplier *
                        CoopBalance.EnemyHealthMultiplier(players, kind);
            health = maxHealth;
            damage = BaseDamage(kind) *
                     scale *
                     tuning.EnemyDamageMultiplier *
                     CoopBalance.EnemyDamageMultiplier(players);
            baseMoveSpeed = BaseMoveSpeed(kind) * tuning.EnemySpeedMultiplier;
            moveSpeed = baseMoveSpeed;
            replica = forceReplica ||
                      (CoopRuntimeState.Connected && CoopRuntimeState.Role == CoopRole.Client);
            replicaTarget = transform.position;
            replicaYaw = transform.eulerAngles.y;

            var hitCollider = gameObject.AddComponent<CapsuleCollider>();
            hitCollider.isTrigger = false;
            hitCollider.radius = kind == EnemyKind.Boss ? .9f : .5f;
            hitCollider.height = kind == EnemyKind.Boss ? 2.5f : 1.8f;
        }

        private void Update()
        {
            if (dead) return;
            if (replica)
            {
                UpdateReplica();
                return;
            }

            var target = ResolveTarget();
            if (!target.valid) return;

            var delta = target.position - transform.position;
            delta.y = 0f;
            var distance = delta.magnitude;

            if (kind == EnemyKind.Ranged)
                UpdateRanged(delta, distance);
            else
                UpdateMelee(delta, distance, target.remote);

            if (kind == EnemyKind.Boss &&
                !specialActive &&
                Time.time >= nextSpecial)
            {
                nextSpecial = Time.time + BossSpecialCooldown();
                StartCoroutine(BossPattern());
            }
        }

        public CoopEnemySnapshot CreateSnapshot()
        {
            return new CoopEnemySnapshot
            {
                networkId = networkId,
                kind = kind,
                x = transform.position.x,
                y = transform.position.y,
                z = transform.position.z,
                yaw = transform.eulerAngles.y,
                health = Mathf.Max(0f, health),
                maxHealth = Mathf.Max(1f, maxHealth),
                bossPhase = Mathf.Clamp(bossPhase, 1, 3)
            };
        }

        public void ApplyReplicaSnapshot(CoopEnemySnapshot snapshot)
        {
            if (snapshot == null || snapshot.networkId != networkId || !replica) return;
            replicaTarget = new Vector3(snapshot.x, snapshot.y, snapshot.z);
            replicaYaw = snapshot.yaw;
            maxHealth = Mathf.Max(1f, snapshot.maxHealth);
            health = Mathf.Clamp(snapshot.health, 0f, maxHealth);
            SetBossPhase(Mathf.Clamp(snapshot.bossPhase, 1, 3), true);
        }

        public void SetReplicaMode(bool value)
        {
            if (replica == value) return;
            replica = value;
            replicaTarget = transform.position;
            replicaYaw = transform.eulerAngles.y;
            specialActive = false;
            StopAllCoroutines();
            if (!replica && kind == EnemyKind.Boss)
                nextSpecial = Time.time + 1f;
        }

        public void TakeDamage(float amount)
        {
            if (replica || dead || amount <= 0f) return;
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

        private CoopCombatTarget ResolveTarget()
        {
            var local = game != null ? game.Player : null;
            var localAlive = local != null && local.Health > 0f && local.CombatEnabled;
            var localPosition = local != null ? local.transform.position : transform.position;

            var session = CoopLanController.Instance;
            var combat = CoopCombatReplicator.Instance;
            var peer = session?.RemoteState;
            var remoteAlive = CoopRuntimeState.Connected &&
                              CoopRuntimeState.Role == CoopRole.Host &&
                              combat != null && combat.CombatConnected &&
                              peer != null && peer.health > 0f && !peer.downed;
            var remotePosition = remoteAlive
                ? new Vector3(peer.x, peer.y, peer.z)
                : transform.position;

            return CoopTargeting.SelectNearest(
                transform.position,
                localAlive,
                localPosition,
                remoteAlive,
                remotePosition,
                networkId);
        }

        private void UpdateReplica()
        {
            transform.position = Vector3.Lerp(
                transform.position,
                replicaTarget,
                16f * Time.unscaledDeltaTime);
            var targetRotation = Quaternion.Euler(0f, replicaYaw, 0f);
            transform.rotation = Quaternion.Slerp(
                transform.rotation,
                targetRotation,
                16f * Time.unscaledDeltaTime);
        }

        private void UpdateMelee(Vector3 delta, float distance, bool targetRemote)
        {
            if (distance > 1.35f)
            {
                Move(delta.normalized);
                return;
            }

            if (Time.time < nextAttack) return;
            var bossAttackRate = bossPhase == 3 ? .82f : bossPhase == 2 ? 1.02f : 1.25f;
            nextAttack = Time.time + (kind == EnemyKind.Boss ? bossAttackRate : 1f);
            var amount = damage * (kind == EnemyKind.Boss && bossPhase == 3 ? 1.12f : 1f);
            if (targetRemote)
                CoopCombatReplicator.Instance?.TryDamageRemote(amount, CoopDamageKind.Melee);
            else
                game.Player?.TakeDamage(amount);
        }

        private void UpdateRanged(Vector3 delta, float distance)
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
            SetBossPhase(nextPhase, true);
        }

        private void SetBossPhase(int value, bool announce)
        {
            if (kind != EnemyKind.Boss || value <= bossPhase) return;
            bossPhase = value;
            moveSpeed = baseMoveSpeed * (bossPhase == 3 ? 1.28f : 1.14f);
            var color = bossPhase == 3
                ? new Color(1f, .16f, .1f)
                : new Color(1f, .42f, .08f);
            var renderer = GetComponent<Renderer>();
            if (renderer != null)
                renderer.sharedMaterial = WorldFactory.GetLitMaterial(color);

            if (announce)
            {
                FindFirstObjectByType<TouchHud>()?.ShowMessage(
                    $"BOSS-PHASE {bossPhase}\nANGRIFFSMUSTER VERÄNDERT",
                    1.6f);
                PlayerController.Pulse(color, transform.position, .7f, 2.8f);
            }
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
            var coop = CoopRuntimeState.ActivePlayerCount > 1;
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
                FireRadial(coop ? 12 : 10, 0f, .65f);
            }
            else if (bossPhase == 2)
            {
                FireRadial(coop ? 17 : 14, 0f, .68f);
                yield return new WaitForSeconds(.18f);
                FireAimedFan(coop ? 7 : 5, coop ? 13f : 16f, .72f);
            }
            else
            {
                FireRadial(coop ? 22 : 18, 0f, .72f);
                yield return new WaitForSeconds(.24f);
                FireRadial(coop ? 22 : 18, coop ? 8f : 10f, .62f);
                FireAimedFan(coop ? 9 : 7, coop ? 11f : 13f, .78f);
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
            var target = ResolveTarget();
            if (!target.valid) return;

            var direction = target.position - transform.position;
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
        private static int nextNetworkId = 1000;

        private Vector3 direction;
        private Vector3 replicaTarget;
        private float damage;
        private float speed;
        private bool fromPlayer;
        private bool replica;
        private float deathAt;
        private bool consumed;
        private int networkId;

        public int NetworkId => networkId;
        public bool IsEnemyProjectile => !fromPlayer;
        public bool IsReplica => replica;

        public static Projectile Spawn(
            Vector3 position,
            Vector3 direction,
            float damage,
            bool fromPlayer,
            float speedMultiplier = 1f,
            int networkId = 0,
            bool replica = false)
        {
            var projectile = Pool.Count > 0 ? Pool.Pop() : Create();
            projectile.gameObject.SetActive(true);
            projectile.transform.position = position;
            projectile.transform.localScale = Vector3.one * (fromPlayer ? .35f : .28f);
            projectile.GetComponent<Renderer>().sharedMaterial = WorldFactory.GetUnlitMaterial(
                fromPlayer ? new Color(.1f, .9f, 1f) : new Color(1f, .15f, .15f));
            projectile.direction = direction.sqrMagnitude > .001f ? direction.normalized : Vector3.forward;
            projectile.replicaTarget = position;
            projectile.damage = Mathf.Max(0f, damage);
            projectile.speed = (fromPlayer ? 9f : 5f) * Mathf.Max(.25f, speedMultiplier);
            projectile.fromPlayer = fromPlayer;
            projectile.replica = replica;
            projectile.networkId = networkId > 0 ? networkId : NextNetworkId();
            projectile.deathAt = Time.time + 3f;
            projectile.consumed = false;
            var collider = projectile.GetComponent<SphereCollider>();
            if (collider != null) collider.enabled = !replica;
            Active.Add(projectile);
            return projectile;
        }

        public static CoopProjectileSnapshot[] CaptureEnemySnapshots()
        {
            var snapshots = new List<CoopProjectileSnapshot>();
            foreach (var projectile in Active)
            {
                if (projectile == null || !projectile.gameObject.activeSelf ||
                    projectile.fromPlayer || projectile.replica)
                    continue;
                snapshots.Add(projectile.CreateSnapshot());
            }
            snapshots.Sort((first, second) => first.networkId.CompareTo(second.networkId));
            return snapshots.ToArray();
        }

        public static void ApplyEnemySnapshots(IReadOnlyList<CoopProjectileSnapshot> snapshots)
        {
            if (snapshots == null) return;
            var existing = new Dictionary<int, Projectile>();
            foreach (var projectile in Active)
            {
                if (projectile == null || !projectile.replica || projectile.fromPlayer) continue;
                if (!existing.ContainsKey(projectile.networkId))
                    existing.Add(projectile.networkId, projectile);
            }

            var alive = new HashSet<int>();
            for (var i = 0; i < snapshots.Count; i++)
            {
                var snapshot = snapshots[i];
                if (snapshot == null || !alive.Add(snapshot.networkId)) continue;
                if (!existing.TryGetValue(snapshot.networkId, out var projectile))
                {
                    projectile = Spawn(
                        new Vector3(snapshot.x, snapshot.y, snapshot.z),
                        Vector3.forward,
                        snapshot.damage,
                        false,
                        1f,
                        snapshot.networkId,
                        true);
                }
                projectile.ApplyReplicaSnapshot(snapshot);
            }

            foreach (var pair in existing)
                if (!alive.Contains(pair.Key) && pair.Value != null)
                    pair.Value.Release();
        }

        public static void ReleaseReplicaProjectiles()
        {
            var snapshot = new List<Projectile>(Active);
            foreach (var projectile in snapshot)
                if (projectile != null && projectile.replica)
                    projectile.Release();
        }

        public static void ReleaseAllActive()
        {
            if (Active.Count == 0) return;
            var snapshot = new List<Projectile>(Active);
            foreach (var projectile in snapshot)
                if (projectile != null) projectile.Release();
            Active.Clear();
        }

        private CoopProjectileSnapshot CreateSnapshot()
        {
            return new CoopProjectileSnapshot
            {
                networkId = networkId,
                x = transform.position.x,
                y = transform.position.y,
                z = transform.position.z,
                damage = Mathf.Clamp(damage, .1f, 500f),
                radius = Mathf.Clamp(transform.localScale.x * .5f, .05f, 1.5f)
            };
        }

        private void ApplyReplicaSnapshot(CoopProjectileSnapshot snapshot)
        {
            replicaTarget = new Vector3(snapshot.x, snapshot.y, snapshot.z);
            damage = snapshot.damage;
            var diameter = Mathf.Clamp(snapshot.radius * 2f, .1f, 3f);
            transform.localScale = Vector3.one * diameter;
            deathAt = Time.time + .5f;
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
            if (replica)
            {
                transform.position = Vector3.Lerp(
                    transform.position,
                    replicaTarget,
                    20f * Time.unscaledDeltaTime);
                if (Time.time >= deathAt) Release();
                return;
            }

            transform.position += direction * speed * Time.deltaTime;
            if (!fromPlayer) TryHitRemotePlayer();
            if (Time.time >= deathAt) Release();
        }

        private void TryHitRemotePlayer()
        {
            if (consumed || !CoopRuntimeState.Connected || CoopRuntimeState.Role != CoopRole.Host)
                return;
            var session = CoopLanController.Instance;
            var peer = session?.RemoteState;
            if (peer == null || peer.health <= 0f || peer.downed) return;

            var remotePosition = new Vector3(peer.x, peer.y, peer.z);
            var delta = remotePosition - transform.position;
            delta.y = 0f;
            var hitRadius = transform.localScale.x * .5f + .45f;
            if (delta.sqrMagnitude > hitRadius * hitRadius) return;
            if (CoopCombatReplicator.Instance == null ||
                !CoopCombatReplicator.Instance.TryDamageRemote(damage, CoopDamageKind.Projectile))
                return;
            consumed = true;
            Release();
        }

        private void OnTriggerEnter(Collider other)
        {
            if (consumed || replica) return;

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

        private static int NextNetworkId()
        {
            unchecked
            {
                nextNetworkId++;
                if (nextNetworkId <= 0) nextNetworkId = 1000;
                return nextNetworkId;
            }
        }
    }
}
