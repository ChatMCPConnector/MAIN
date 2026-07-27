using System.Collections.Generic;
using UnityEngine;

namespace NeonRift
{
    /// <summary>
    /// Resolves a CC0 KayKit model imported by glTFast from Resources. If the
    /// download/import is unavailable, the fighter still receives a complete
    /// procedural model so gameplay never depends on a network request.
    /// </summary>
    public sealed class CommunityModel : MonoBehaviour
    {
        private GameObject _visual;
        private readonly List<Material> _ownedMaterials = new();

        public void Configure(string resourcePath, Color primary, Color accent, float scale = 1f)
        {
            transform.localScale = Vector3.one * scale;
            GameObject prefab = Resources.Load<GameObject>(resourcePath);
            _visual = prefab != null
                ? Instantiate(prefab, transform, false)
                : CreateFallback(primary, accent);

            if (_visual.transform.parent != transform)
            {
                _visual.transform.SetParent(transform, false);
            }

            NormalizeVisual(prefab != null);
            TryPlayImportedAnimation();
        }

        private void NormalizeVisual(bool imported)
        {
            _visual.name = imported ? "CC0 KayKit visual" : "Procedural fallback visual";
            _visual.transform.localPosition = Vector3.zero;
            _visual.transform.localRotation = imported
                ? Quaternion.Euler(0f, 180f, 0f)
                : Quaternion.identity;

            foreach (Collider collider in _visual.GetComponentsInChildren<Collider>(true))
            {
                Destroy(collider);
            }
        }

        private void TryPlayImportedAnimation()
        {
            Animation legacyAnimation = _visual.GetComponentInChildren<Animation>(true);
            if (legacyAnimation != null && legacyAnimation.clip != null)
            {
                legacyAnimation.Play();
            }
        }

        private GameObject CreateFallback(Color primary, Color accent)
        {
            var root = new GameObject("Stylized fallback fighter");
            var body = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            body.name = "Body";
            body.transform.SetParent(root.transform, false);
            body.transform.localPosition = new Vector3(0f, 0.95f, 0f);
            body.transform.localScale = new Vector3(0.72f, 0.9f, 0.72f);
            body.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit("Fallback Body", primary, 0.15f, 0.5f));
            Object.Destroy(body.GetComponent<Collider>());

            var head = GameObject.CreatePrimitive(PrimitiveType.Sphere);
            head.name = "Head";
            head.transform.SetParent(root.transform, false);
            head.transform.localPosition = new Vector3(0f, 1.95f, 0f);
            head.transform.localScale = Vector3.one * 0.58f;
            head.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit("Fallback Head", accent, 0.05f, 0.55f));
            Object.Destroy(head.GetComponent<Collider>());

            var weapon = GameObject.CreatePrimitive(PrimitiveType.Cube);
            weapon.name = "Energy weapon";
            weapon.transform.SetParent(root.transform, false);
            weapon.transform.localPosition = new Vector3(0.58f, 1.05f, 0f);
            weapon.transform.localScale = new Vector3(0.09f, 1.25f, 0.09f);
            weapon.GetComponent<Renderer>().sharedMaterial = Own(MaterialFactory.CreateLit("Fallback Weapon", accent, 0.35f, 0.9f, accent * 2.6f));
            Object.Destroy(weapon.GetComponent<Collider>());
            return root;
        }

        private Material Own(Material material)
        {
            _ownedMaterials.Add(material);
            return material;
        }

        private void OnDestroy()
        {
            foreach (Material material in _ownedMaterials)
            {
                if (material != null) Destroy(material);
            }
            _ownedMaterials.Clear();
        }
    }
}
