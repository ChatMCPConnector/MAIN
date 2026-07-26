using System.Collections;
using UnityEngine;

namespace NeonRift
{
    /// <summary>
    /// Lightweight original audio generated at runtime. No external sound files
    /// are required, so the portable build remains self-contained.
    /// </summary>
    public sealed class SynthAudio : MonoBehaviour
    {
        public static SynthAudio Instance { get; private set; }

        private AudioSource _effects;
        private AudioSource _music;

        private void Awake()
        {
            Instance = this;
            _effects = gameObject.AddComponent<AudioSource>();
            _effects.playOnAwake = false;
            _effects.spatialBlend = 0f;

            _music = gameObject.AddComponent<AudioSource>();
            _music.playOnAwake = false;
            _music.loop = true;
            _music.volume = 0.12f;
            _music.spatialBlend = 0f;
            _music.clip = CreateAmbientLoop();
            _music.Play();
        }

        public void Confirm() => PlayTone(440f, 760f, 0.08f, 0.12f, 0.18f);
        public void Attack(bool heavy) => PlayTone(heavy ? 155f : 240f, heavy ? 82f : 175f, heavy ? 0.14f : 0.09f, 0.18f, 0.22f);
        public void Special() => PlayTone(330f, 980f, 0.22f, 0.28f, 0.28f);
        public void Hit(bool guarded) => PlayTone(guarded ? 520f : 120f, guarded ? 260f : 55f, 0.09f, 0.13f, guarded ? 0.12f : 0.28f);

        private void PlayTone(float startFrequency, float endFrequency, float duration, float volume, float noise)
        {
            if (_effects == null) return;
            AudioClip clip = CreateTone(startFrequency, endFrequency, duration, volume, noise);
            _effects.PlayOneShot(clip, 1f);
            StartCoroutine(DestroyClipAfter(clip, duration + 0.2f));
        }

        private static AudioClip CreateTone(float startFrequency, float endFrequency, float duration, float volume, float noise)
        {
            const int sampleRate = 44100;
            int sampleCount = Mathf.Max(1, Mathf.CeilToInt(duration * sampleRate));
            var samples = new float[sampleCount];
            float phase = 0f;
            uint randomState = 0x9E3779B9u;
            for (int i = 0; i < sampleCount; i++)
            {
                float t = i / (float)sampleCount;
                float frequency = Mathf.Lerp(startFrequency, endFrequency, t * t);
                phase += Mathf.PI * 2f * frequency / sampleRate;
                randomState = randomState * 1664525u + 1013904223u;
                float random = ((randomState >> 8) / 16777215f) * 2f - 1f;
                float envelope = Mathf.Sin(Mathf.PI * Mathf.Clamp01(t)) * (1f - t * 0.65f);
                samples[i] = (Mathf.Sin(phase) * (1f - noise) + random * noise) * envelope * volume;
            }

            AudioClip clip = AudioClip.Create("Neon Rift generated effect", sampleCount, 1, sampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }

        private static AudioClip CreateAmbientLoop()
        {
            const int sampleRate = 44100;
            const float duration = 4f;
            int sampleCount = Mathf.CeilToInt(duration * sampleRate);
            var samples = new float[sampleCount];
            for (int i = 0; i < sampleCount; i++)
            {
                float time = i / (float)sampleRate;
                float pulse = 0.56f + 0.44f * Mathf.Sin(time * Mathf.PI * 2f * 0.5f);
                float bass = Mathf.Sin(time * Mathf.PI * 2f * 55f) * 0.55f;
                float pad = Mathf.Sin(time * Mathf.PI * 2f * 110f) * 0.28f + Mathf.Sin(time * Mathf.PI * 2f * 164.81f) * 0.17f;
                samples[i] = (bass + pad) * pulse * 0.32f;
            }

            AudioClip clip = AudioClip.Create("Neon Rift generated ambience", sampleCount, 1, sampleRate, false);
            clip.SetData(samples, 0);
            return clip;
        }

        private static IEnumerator DestroyClipAfter(AudioClip clip, float delay)
        {
            yield return new WaitForSecondsRealtime(delay);
            if (clip != null) Destroy(clip);
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
            if (_music != null && _music.clip != null) Destroy(_music.clip);
        }
    }
}
