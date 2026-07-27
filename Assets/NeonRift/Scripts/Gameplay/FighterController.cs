using System;
using System.Collections.Generic;
using UnityEngine;
using UnityEngine.InputSystem;

namespace NeonRift
{
    [RequireComponent(typeof(CharacterController))]
    public sealed class FighterController : MonoBehaviour
    {
        public event Action<FighterController> Defeated;
        public event Action<FighterController, float> Damaged;

        public FighterSpec Spec { get; private set; }
        public FighterRole Role { get; private set; }
        public int TeamId { get; private set; }
        public int PlayerIndex { get; private set; }
        public float Health { get; private set; }
        public float Energy { get; private set; }
        public bool IsAlive => Health > 0f;
        public bool IsPlayerControlled => Role == FighterRole.Player;
        public bool IsGuarding { get; private set; }

        private CharacterController _controller;
        private Transform _visualRoot;
        private Vector3 _velocity;
        private Vector3 _knockback;
        private float _attackCooldown;
        private float _invulnerability;
        private float _dashCooldown;
        private float _flashTimer;
        private float _baseVisualY;
        private bool _configured;
        private Color _accent;

        public void Configure(FighterSpec spec, FighterRole role, int teamId, int playerIndex, string modelFile = null)
        {
            Spec = spec ?? throw new ArgumentNullException(nameof(spec));
            Role = role;
            TeamId = teamId;
            PlayerIndex = playerIndex;
            Health = spec.MaxHealth;
            Energy = role == FighterRole.TrainingDummy ? 100f : 45f;
            _accent = spec.Accent;

            name = $"{role} - {spec.Name}";
            _controller = GetComponent<CharacterController>();
            _controller.height = 2.05f;
            _controller.radius = 0.42f;
            _controller.center = new Vector3(0f, 1.02f, 0f);
            _controller.stepOffset = 0.28f;
            _controller.slopeLimit = 55f;

            _visualRoot = new GameObject("Character Visual").transform;
            _visualRoot.SetParent(transform, false);
            _visualRoot.localRotation = Quaternion.Euler(0f, teamId == 0 ? 90f : -90f, 0f);
            _baseVisualY = 0f;
            var model = _visualRoot.gameObject.AddComponent<CommunityModel>();
            string file = string.IsNullOrWhiteSpace(modelFile) ? spec.ModelFile : modelFile;
            model.Configure($"Community/KayKit/{file.Replace(".glb", string.Empty)}", spec.Primary, spec.Accent, role == FighterRole.Boss ? 1.32f : 1f);

            CreateGroundGlow();
            _configured = true;
        }

        private void CreateGroundGlow()
        {
            var glow = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            glow.name = "Team glow";
            glow.transform.SetParent(transform, false);
            glow.transform.localPosition = new Vector3(0f, 0.025f, 0f);
            glow.transform.localScale = new Vector3(0.72f, 0.012f, 0.72f);
            Destroy(glow.GetComponent<Collider>());
            Color color = Role == FighterRole.Enemy || Role == FighterRole.Boss
                ? new Color(1f, 0.12f, 0.22f)
                : Spec.Accent;
            glow.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit("Team glow", color, 0f, 1f, color * 3.4f);
        }

        private void Update()
        {
            if (!_configured || !IsAlive || NeonRiftGame.Instance == null || NeonRiftGame.Instance.Screen != GameScreen.Playing)
            {
                return;
            }

            float delta = Time.deltaTime;
            _attackCooldown = Mathf.Max(0f, _attackCooldown - delta);
            _invulnerability = Mathf.Max(0f, _invulnerability - delta);
            _dashCooldown = Mathf.Max(0f, _dashCooldown - delta);
            _flashTimer = Mathf.Max(0f, _flashTimer - delta);
            Energy = Mathf.Min(100f, Energy + delta * 5.5f);

            Vector2 move = Vector2.zero;
            bool light = false;
            bool heavy = false;
            bool special = false;
            bool jump = false;
            bool dash = false;
            bool guard = false;

            if (Role == FighterRole.Player)
            {
                ReadPlayerInput(ref move, ref light, ref heavy, ref special, ref jump, ref dash, ref guard);
            }
            else if (Role == FighterRole.TrainingDummy)
            {
                guard = false;
            }
            else
            {
                ReadAIInput(ref move, ref light, ref heavy, ref special, ref guard);
            }

            IsGuarding = guard && _attackCooldown <= 0f && _controller.isGrounded;
            if (IsGuarding) move *= 0.28f;

            if (dash && _dashCooldown <= 0f && move.sqrMagnitude > 0.05f)
            {
                _knockback += new Vector3(move.x, 0f, move.y).normalized * 8.5f;
                _dashCooldown = 0.8f;
                _invulnerability = 0.14f;
                CombatEffects.Instance?.Burst(transform.position + Vector3.up * 0.25f, Spec.Accent, 9, 0.65f);
            }

            if (_controller.isGrounded && _velocity.y < 0f)
            {
                _velocity.y = -1.5f;
            }

            if (jump && _controller.isGrounded && !IsGuarding)
            {
                _velocity.y = 7.2f;
                CombatEffects.Instance?.Burst(transform.position + Vector3.up * 0.1f, Spec.Accent, 7, 0.45f);
            }

            _velocity.y += Physics.gravity.y * delta * 1.65f;
            Vector3 planar = new Vector3(move.x, 0f, move.y);
            if (planar.sqrMagnitude > 1f) planar.Normalize();
            float speed = Spec.Speed * (Role == FighterRole.Boss ? 0.86f : 1f);
            Vector3 motion = planar * speed + _knockback;
            motion.y = _velocity.y;
            _controller.Move(motion * delta);
            _knockback = Vector3.Lerp(_knockback, Vector3.zero, delta * 5.8f);

            ClampToArena();
            AnimateVisual(planar, delta);

            if (planar.x > 0.05f) _visualRoot.localRotation = Quaternion.Euler(0f, 90f, 0f);
            if (planar.x < -0.05f) _visualRoot.localRotation = Quaternion.Euler(0f, -90f, 0f);

            if (_attackCooldown <= 0f)
            {
                if (special && Energy >= 35f) PerformAttack(false, true);
                else if (heavy) PerformAttack(true, false);
                else if (light) PerformAttack(false, false);
            }
        }

        private void ReadPlayerInput(
            ref Vector2 move,
            ref bool light,
            ref bool heavy,
            ref bool special,
            ref bool jump,
            ref bool dash,
            ref bool guard)
        {
            Keyboard keyboard = Keyboard.current;
            if (keyboard != null)
            {
                int player = Mathf.Clamp(PlayerIndex, 0, 1);
                move.x += ReadAxis(InputBindings.Held(keyboard, player, PlayerAction.MoveLeft), InputBindings.Held(keyboard, player, PlayerAction.MoveRight));
                move.y += ReadAxis(InputBindings.Held(keyboard, player, PlayerAction.MoveDown), InputBindings.Held(keyboard, player, PlayerAction.MoveUp));
                light |= InputBindings.Pressed(keyboard, player, PlayerAction.Light);
                heavy |= InputBindings.Pressed(keyboard, player, PlayerAction.Heavy);
                special |= InputBindings.Pressed(keyboard, player, PlayerAction.Special);
                jump |= InputBindings.Pressed(keyboard, player, PlayerAction.Jump);
                dash |= InputBindings.Pressed(keyboard, player, PlayerAction.DashGuard);
                guard |= InputBindings.Held(keyboard, player, PlayerAction.DashGuard);
            }

            var pads = Gamepad.all;
            if (PlayerIndex >= 0 && PlayerIndex < pads.Count)
            {
                Gamepad pad = pads[PlayerIndex];
                move += pad.leftStick.ReadValue();
                light |= pad.buttonSouth.wasPressedThisFrame;
                heavy |= pad.buttonWest.wasPressedThisFrame;
                special |= pad.buttonNorth.wasPressedThisFrame;
                jump |= pad.buttonEast.wasPressedThisFrame;
                dash |= pad.leftShoulder.wasPressedThisFrame;
                guard |= pad.leftShoulder.isPressed;
            }
        }

        private void ReadAIInput(
            ref Vector2 move,
            ref bool light,
            ref bool heavy,
            ref bool special,
            ref bool guard)
        {
            FighterController target = NeonRiftGame.Instance.FindNearestOpponent(this);
            if (target == null) return;

            Vector3 delta = target.transform.position - transform.position;
            float distance = new Vector2(delta.x, delta.z).magnitude;
            float desiredRange = Role == FighterRole.Boss ? 2.1f : 1.35f;
            if (distance > desiredRange)
            {
                Vector3 direction = delta.normalized;
                move = new Vector2(direction.x, direction.z);
            }
            else if (distance < 0.72f && UnityEngine.Random.value < 0.015f)
            {
                move = new Vector2(-Mathf.Sign(delta.x), -Mathf.Sign(delta.z));
            }

            if (distance < 2.25f && _attackCooldown <= 0f)
            {
                float roll = UnityEngine.Random.value;
                special = Energy >= 35f && roll > 0.88f;
                heavy = !special && roll > 0.58f;
                light = !special && !heavy;
            }

            guard = target._attackCooldown > 0.25f && distance < 2.3f && UnityEngine.Random.value < 0.08f;
        }

        private void PerformAttack(bool heavy, bool special)
        {
            float baseDamage = special ? 20f : heavy ? 15f : 9f;
            float damage = GameBalance.CalculateDamage(baseDamage, Spec.Power, heavy, special);
            float range = special ? 4.4f : heavy ? 2.2f : 1.65f;
            float cooldown = special ? 1.05f : heavy ? 0.72f : 0.34f;
            _attackCooldown = cooldown;
            if (special) SynthAudio.Instance?.Special();
            else SynthAudio.Instance?.Attack(heavy);

            if (special)
            {
                Energy -= 35f;
                if (Spec.Name.Contains("Mira", StringComparison.OrdinalIgnoreCase))
                {
                    Health = Mathf.Min(Spec.MaxHealth, Health + 16f);
                    CombatEffects.Instance?.Shockwave(transform.position, Spec.Accent, 3.8f);
                }
                else
                {
                    EnergyProjectile.Spawn(this, damage, Spec.Accent, _visualRoot.forward, 10.5f);
                    CombatEffects.Instance?.Shockwave(transform.position, Spec.Accent, 2.6f);
                }
            }

            Vector3 center = transform.position + Vector3.up * 1.0f + _visualRoot.forward * (range * 0.36f);
            Collider[] hits = Physics.OverlapSphere(center, range * 0.62f, ~0, QueryTriggerInteraction.Collide);
            var processed = new HashSet<FighterController>();
            foreach (Collider hit in hits)
            {
                FighterController target = hit.GetComponentInParent<FighterController>();
                if (target == null || target == this || target.TeamId == TeamId || !target.IsAlive || !processed.Add(target))
                {
                    continue;
                }

                Vector3 direction = (target.transform.position - transform.position).normalized;
                target.ReceiveDamage(damage, direction, heavy, special);
            }

            CombatEffects.Instance?.Burst(center, Spec.Accent, special ? 28 : heavy ? 18 : 10, special ? 1.2f : 0.8f);
            NeonRiftGame.Instance.CameraRig?.AddShake(special ? 0.18f : heavy ? 0.1f : 0.045f);
        }

        public void ReceiveDamage(float amount, Vector3 direction, bool heavy, bool special)
        {
            if (!IsAlive || _invulnerability > 0f) return;
            float finalDamage = IsGuarding ? amount * 0.28f : amount;
            Health = Mathf.Max(0f, Health - finalDamage);
            Energy = Mathf.Min(100f, Energy + finalDamage * 0.42f);
            _flashTimer = 0.13f;
            float force = GameBalance.KnockbackFor(finalDamage, heavy, special) * (IsGuarding ? 0.35f : 1f);
            _knockback += new Vector3(direction.x, special ? 2.4f : heavy ? 1.2f : 0.35f, direction.z).normalized * force;
            _invulnerability = IsGuarding ? 0.08f : 0.16f;
            SynthAudio.Instance?.Hit(IsGuarding);

            CombatEffects.Instance?.Burst(transform.position + Vector3.up * 1.1f, IsGuarding ? Color.cyan : _accent, special ? 30 : 16, special ? 1.2f : 0.78f);
            Damaged?.Invoke(this, finalDamage);

            if (Health <= 0f)
            {
                _controller.enabled = false;
                transform.rotation = Quaternion.Euler(0f, transform.eulerAngles.y, 82f);
                Defeated?.Invoke(this);
            }
        }

        public void RestoreFull()
        {
            Health = Spec.MaxHealth;
            Energy = 100f;
            transform.rotation = Quaternion.identity;
            if (_controller != null) _controller.enabled = true;
        }

        private void ClampToArena()
        {
            Vector3 position = transform.position;
            position.x = Mathf.Clamp(position.x, -10.9f, 10.9f);
            position.z = Mathf.Clamp(position.z, -4.7f, 4.7f);
            if (position.y < -2f) position.y = 0.05f;
            transform.position = position;
        }

        private void AnimateVisual(Vector3 planar, float delta)
        {
            if (_visualRoot == null) return;
            float speed = planar.magnitude;
            float bob = speed > 0.05f ? Mathf.Sin(Time.time * 11f) * 0.045f : Mathf.Sin(Time.time * 2.2f) * 0.012f;
            float attackSquash = _attackCooldown > 0f ? Mathf.Sin(_attackCooldown * 18f) * 0.06f : 0f;
            _visualRoot.localPosition = Vector3.Lerp(
                _visualRoot.localPosition,
                new Vector3(0f, _baseVisualY + bob, attackSquash),
                delta * 12f);
            Vector3 targetScale = _flashTimer > 0f ? new Vector3(1.08f, 0.92f, 1.08f) : Vector3.one;
            _visualRoot.localScale = Vector3.Lerp(_visualRoot.localScale, targetScale, delta * 18f);
        }

        private static float ReadAxis(bool negative, bool positive)
        {
            return (positive ? 1f : 0f) - (negative ? 1f : 0f);
        }
    }
}
