using UnityEngine;

namespace Riftbound
{
    public sealed class CameraFollow : MonoBehaviour
    {
        public Transform target;
        private Vector3 velocity;

        private void LateUpdate()
        {
            if (target == null) return;
            var desired = new Vector3(
                Mathf.Clamp(target.position.x * .22f, -1f, 1f),
                8.6f,
                -11.4f);
            transform.position = Vector3.SmoothDamp(
                transform.position,
                desired,
                ref velocity,
                .18f);
        }
    }
}
