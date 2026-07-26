using System.Collections;
using UnityEngine;

namespace NeonRift
{
    public sealed class CombatEffects : MonoBehaviour
    {
        public static CombatEffects Instance { get; private set; }

        private Material _sparkMaterial;

        private void Awake()
        {
            Instance = this;
            _sparkMaterial = MaterialFactory.CreateLit(
                "Neon spark",
                Color.white,
                0f,
                0.8f,
                new Color(1f, 0.35f, 0.1f) * 3f);
        }

        public void Burst(Vector3 position, Color color, int count = 18, float scale = 1f)
        {
            var root = new GameObject("Impact burst");
            root.transform.position = position;
            var particle = root.AddComponent<ParticleSystem>();
            var main = particle.main;
            main.duration = 0.35f;
            main.startLifetime = new ParticleSystem.MinMaxCurve(0.18f, 0.5f);
            main.startSpeed = new ParticleSystem.MinMaxCurve(3.5f * scale, 8f * scale);
            main.startSize = new ParticleSystem.MinMaxCurve(0.05f * scale, 0.16f * scale);
            main.startColor = new ParticleSystem.MinMaxGradient(color, Color.white);
            main.gravityModifier = 0.25f;
            main.simulationSpace = ParticleSystemSimulationSpace.World;

            var emission = particle.emission;
            emission.rateOverTime = 0f;
            emission.SetBursts(new[] { new ParticleSystem.Burst(0f, (short)count) });

            var shape = particle.shape;
            shape.shapeType = ParticleSystemShapeType.Sphere;
            shape.radius = 0.18f * scale;

            var trails = particle.trails;
            trails.enabled = true;
            trails.lifetime = 0.12f;

            var renderer = particle.GetComponent<ParticleSystemRenderer>();
            renderer.renderMode = ParticleSystemRenderMode.Stretch;
            renderer.lengthScale = 0.5f;
            renderer.velocityScale = 0.3f;
            renderer.sharedMaterial = _sparkMaterial;

            particle.Play();
            Destroy(root, 1.3f);
        }

        public void Shockwave(Vector3 position, Color color, float radius)
        {
            StartCoroutine(ShockwaveRoutine(position, color, radius));
        }

        private IEnumerator ShockwaveRoutine(Vector3 position, Color color, float radius)
        {
            var ring = GameObject.CreatePrimitive(PrimitiveType.Cylinder);
            ring.name = "Shockwave";
            ring.transform.position = position + Vector3.up * 0.08f;
            ring.transform.localScale = new Vector3(0.1f, 0.015f, 0.1f);
            Destroy(ring.GetComponent<Collider>());
            ring.GetComponent<Renderer>().sharedMaterial = MaterialFactory.CreateLit("Shockwave", color, 0f, 1f, color * 3f);

            float time = 0f;
            while (time < 0.34f)
            {
                time += Time.deltaTime;
                float t = Mathf.Clamp01(time / 0.34f);
                float size = Mathf.Lerp(0.1f, radius, t);
                ring.transform.localScale = new Vector3(size, Mathf.Lerp(0.02f, 0.002f, t), size);
                yield return null;
            }

            Destroy(ring);
        }
    }
}
