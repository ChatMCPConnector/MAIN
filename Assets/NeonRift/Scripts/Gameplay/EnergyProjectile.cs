using UnityEngine;

namespace NeonRift
{
    public sealed class EnergyProjectile : MonoBehaviour
    {
        private FighterController _owner;
        private float _damage;
        private float _speed;
        private Vector3 _direction;
        private float _life = 2.3f;
        private bool _spent;

        public static void Spawn(FighterController owner, float damage, Color color, Vector3 direction, float speed)
        {
            var projectile = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            projectile.name = $"{owner.Spec.Name} special projectile";
            projectile.transform.position = owner.transform.position + Vector3.up * 1.2f + direction.normalized * 0.85f;
            projectile.transform.localScale = Vector3.one * 0.42f;
            Collider collider = projectile.GetComponent<Collider>();
            collider.isTrigger = true;
            var rigidbody = projectile.AddComponent<Rigidbody>();
            rigidbody.isKinematic = true;
            rigidbody.useGravity = false;
            projectile.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit("Special projectile", color, 0f, 1f, color * 4.5f);
            var script = projectile.AddComponent<EnergyProjectile>();
            script._owner = owner;
            script._damage = damage;
            script._speed = speed;
            script._direction = direction.sqrMagnitude > 0.01f ? direction.normalized : Vector3.right;

            CombatEffects.Instance?.Burst(projectile.transform.position, color, 12, 0.55f);
        }

        private void Update()
        {
            if (_spent) return;
            transform.position += _direction * (_speed * Time.deltaTime);
            transform.Rotate(Vector3.up, 360f * Time.deltaTime, Space.World);
            _life -= Time.deltaTime;
            if (_life <= 0f || Mathf.Abs(transform.position.x) > 13f || Mathf.Abs(transform.position.z) > 7f)
            {
                Destroy(gameObject);
            }
        }

        private void OnTriggerEnter(Collider other)
        {
            if (_spent || _owner == null) return;
            FighterController target = other.GetComponentInParent<FighterController>();
            if (target == null || target == _owner || target.TeamId == _owner.TeamId || !target.IsAlive) return;

            _spent = true;
            Vector3 direction = (target.transform.position - transform.position).normalized;
            target.ReceiveDamage(_damage, direction, false, true);
            CombatEffects.Instance?.Shockwave(transform.position, _owner.Spec.Accent, 1.8f);
            CombatEffects.Instance?.Burst(transform.position, _owner.Spec.Accent, 26, 1.05f);
            Destroy(gameObject);
        }
    }
}
