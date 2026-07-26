using System.Collections.Generic;
using UnityEngine;

namespace NeonRift
{
    public sealed class ArenaCameraRig : MonoBehaviour
    {
        private readonly List<Transform> _targets = new();
        private Vector3 _velocity;
        private float _shake;

        public void SetTargets(IEnumerable<FighterController> fighters)
        {
            _targets.Clear();
            foreach (FighterController fighter in fighters)
            {
                if (fighter != null) _targets.Add(fighter.transform);
            }
        }

        public void AddShake(float amount)
        {
            _shake = Mathf.Max(_shake, amount);
        }

        private void LateUpdate()
        {
            _targets.RemoveAll(target => target == null);
            Vector3 focus = new Vector3(0f, 1.25f, 0f);
            float horizontalSpread = 6f;

            if (_targets.Count > 0)
            {
                float minX = float.MaxValue;
                float maxX = float.MinValue;
                Vector3 sum = Vector3.zero;
                foreach (Transform target in _targets)
                {
                    sum += target.position;
                    minX = Mathf.Min(minX, target.position.x);
                    maxX = Mathf.Max(maxX, target.position.x);
                }

                focus = sum / _targets.Count + Vector3.up * 1.15f;
                horizontalSpread = Mathf.Max(5f, maxX - minX);
            }

            float distance = Mathf.Lerp(13.5f, 20f, Mathf.InverseLerp(5f, 18f, horizontalSpread));
            Vector3 desired = focus + new Vector3(0f, 7.4f, -distance);
            transform.position = Vector3.SmoothDamp(transform.position, desired, ref _velocity, 0.22f);
            transform.rotation = Quaternion.Slerp(transform.rotation, Quaternion.LookRotation(focus - transform.position), Time.deltaTime * 7f);

            if (_shake > 0.001f)
            {
                transform.position += Random.insideUnitSphere * _shake;
                _shake = Mathf.MoveTowards(_shake, 0f, Time.deltaTime * 2.8f);
            }
        }
    }
}
