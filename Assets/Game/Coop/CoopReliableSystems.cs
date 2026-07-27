using System;
using System.Collections.Generic;
using System.Globalization;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

namespace Riftbound
{
    public enum CoopCriticalKind
    {
        Damage,
        Revive,
        Advance,
        Decision,
        Economy
    }

    [Serializable]
    public sealed class CoopCriticalEnvelope
    {
        public long id;
        public CoopCriticalKind kind;
        public string payload;
    }

    public static class CoopReliableProtocol
    {
        public const string Prefix = "RB5R";
        public const int Version = 1;

        public static string EncodeHello(string sessionCode, string token) =>
            Join(Prefix, "HELLO", Version, Clean(sessionCode), Clean(token));

        public static bool TryDecodeHello(string payload, out string sessionCode, out string token) =>
            TryDecodeControl(payload, "HELLO", out sessionCode, out token);

        public static string EncodeWelcome(string sessionCode, string token) =>
            Join(Prefix, "WELCOME", Version, Clean(sessionCode), Clean(token));

        public static bool TryDecodeWelcome(string payload, out string sessionCode, out string token) =>
            TryDecodeControl(payload, "WELCOME", out sessionCode, out token);

        public static string EncodePing(string sessionCode, string token) =>
            Join(Prefix, "PING", Version, Clean(sessionCode), Clean(token));

        public static bool TryDecodePing(string payload, out string sessionCode, out string token) =>
            TryDecodeControl(payload, "PING", out sessionCode, out token);

        public static string EncodePong(string sessionCode, string token) =>
            Join(Prefix, "PONG", Version, Clean(sessionCode), Clean(token));

        public static bool TryDecodePong(string payload, out string sessionCode, out string token) =>
            TryDecodeControl(payload, "PONG", out sessionCode, out token);

        public static string EncodeMessage(
            string sessionCode,
            string token,
            CoopCriticalEnvelope envelope)
        {
            if (envelope == null) throw new ArgumentNullException(nameof(envelope));
            var bytes = Encoding.UTF8.GetBytes(envelope.payload ?? string.Empty);
            return Join(
                Prefix,
                "MSG",
                Version,
                Clean(sessionCode),
                Clean(token),
                envelope.id,
                (int)envelope.kind,
                Convert.ToBase64String(bytes));
        }

        public static bool TryDecodeMessage(
            string payload,
            out string sessionCode,
            out string token,
            out CoopCriticalEnvelope envelope)
        {
            sessionCode = token = null;
            envelope = null;
            var parts = Split(payload, "MSG", 8);
            if (!HasVersion(parts) ||
                !long.TryParse(parts[5], NumberStyles.Integer, CultureInfo.InvariantCulture, out var id) ||
                id <= 0 ||
                !int.TryParse(parts[6], NumberStyles.Integer, CultureInfo.InvariantCulture, out var kind) ||
                kind < 0 || kind > (int)CoopCriticalKind.Economy)
                return false;

            try
            {
                var decoded = Encoding.UTF8.GetString(Convert.FromBase64String(parts[7]));
                if (decoded.Length > 2048) return false;
                sessionCode = parts[3];
                token = parts[4];
                if (string.IsNullOrWhiteSpace(sessionCode) || string.IsNullOrWhiteSpace(token))
                    return false;
                envelope = new CoopCriticalEnvelope
                {
                    id = id,
                    kind = (CoopCriticalKind)kind,
                    payload = decoded
                };
                return true;
            }
            catch
            {
                return false;
            }
        }

        public static string EncodeAck(string sessionCode, string token, long id) =>
            Join(Prefix, "ACK", Version, Clean(sessionCode), Clean(token), id);

        public static bool TryDecodeAck(
            string payload,
            out string sessionCode,
            out string token,
            out long id)
        {
            sessionCode = token = null;
            id = 0;
            var parts = Split(payload, "ACK", 6);
            if (!HasVersion(parts) ||
                !long.TryParse(parts[5], NumberStyles.Integer, CultureInfo.InvariantCulture, out id) ||
                id <= 0)
                return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        private static bool TryDecodeControl(
            string payload,
            string type,
            out string sessionCode,
            out string token)
        {
            sessionCode = token = null;
            var parts = Split(payload, type, 5);
            if (!HasVersion(parts)) return false;
            sessionCode = parts[3];
            token = parts[4];
            return !string.IsNullOrWhiteSpace(sessionCode) && !string.IsNullOrWhiteSpace(token);
        }

        private static bool HasVersion(string[] parts) =>
            parts != null &&
            int.TryParse(parts[2], NumberStyles.Integer, CultureInfo.InvariantCulture, out var version) &&
            version == Version;

        private static string[] Split(string payload, string type, int expected)
        {
            if (string.IsNullOrWhiteSpace(payload)) return null;
            var parts = payload.Split('|');
            return parts.Length == expected && parts[0] == Prefix && parts[1] == type
                ? parts
                : null;
        }

        private static string Join(params object[] values)
        {
            var builder = new StringBuilder(256);
            for (var i = 0; i < values.Length; i++)
            {
                if (i > 0) builder.Append('|');
                builder.Append(Convert.ToString(values[i], CultureInfo.InvariantCulture));
            }
            return builder.ToString();
        }

        private static string Clean(string value) =>
            (value ?? string.Empty).Replace("|", string.Empty).Trim();
    }

    public sealed class CoopReliableLedger
    {
        private sealed class Pending
        {
            public CoopCriticalEnvelope envelope;
            public double lastSent;
            public int attempts;
        }

        private readonly Dictionary<long, Pending> pending = new Dictionary<long, Pending>();
        private readonly HashSet<long> received = new HashSet<long>();
        private readonly Queue<long> receivedOrder = new Queue<long>();
        private long nextId;

        public int PendingCount => pending.Count;

        public CoopCriticalEnvelope Create(CoopCriticalKind kind, string payload)
        {
            nextId++;
            if (nextId <= 0) nextId = 1;
            var envelope = new CoopCriticalEnvelope
            {
                id = nextId,
                kind = kind,
                payload = payload ?? string.Empty
            };
            pending[envelope.id] = new Pending { envelope = envelope, lastSent = double.NegativeInfinity };
            return envelope;
        }

        public List<CoopCriticalEnvelope> CollectDue(double now, double interval, int maxAttempts)
        {
            var result = new List<CoopCriticalEnvelope>();
            foreach (var pair in pending)
            {
                var entry = pair.Value;
                if (entry.attempts >= maxAttempts || now - entry.lastSent < interval) continue;
                entry.lastSent = now;
                entry.attempts++;
                result.Add(entry.envelope);
            }
            return result;
        }

        public bool Acknowledge(long id) => pending.Remove(id);

        public bool AcceptIncoming(long id)
        {
            if (id <= 0 || !received.Add(id)) return false;
            receivedOrder.Enqueue(id);
            while (receivedOrder.Count > 512)
                received.Remove(receivedOrder.Dequeue());
            return true;
        }

        public void Clear()
        {
            pending.Clear();
            received.Clear();
            receivedOrder.Clear();
            nextId = 0;
        }
    }

    public sealed class CoopReliableRuntime : MonoBehaviour
    {
        private const int ReliablePort = 47830;
        private const float HelloInterval = .5f;
        private const float HeartbeatInterval = 1f;
        private const float Timeout = 4f;
        private const double ResendInterval = .22d;
        private const int MaxAttempts = 180;
        private const string TokenKey = "riftbound-coop-device-token";

        private readonly CoopReliableLedger ledger = new CoopReliableLedger();
        private readonly Dictionary<long, Action> acknowledgements = new Dictionary<long, Action>();
        private UdpClient socket;
        private IPEndPoint remoteEndpoint;
        private CoopRole role;
        private string sessionCode;
        private string localToken;
        private string remoteToken;
        private float nextHello;
        private float nextHeartbeat;
        private float lastPacketAt;
        private bool channelConnected;

        public static CoopReliableRuntime Instance { get; private set; }
        public bool Connected => channelConnected && CoopRuntimeState.Connected;
        public event Action<CoopCriticalEnvelope> Received;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopReliableRuntime>() != null) return;
            var root = new GameObject("Coop Reliable Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopReliableRuntime>();
        }

        private void Awake()
        {
            if (Instance != null && Instance != this)
            {
                Destroy(gameObject);
                return;
            }
            Instance = this;
            DontDestroyOnLoad(gameObject);
            localToken = PlayerPrefs.GetString(TokenKey, string.Empty);
        }

        private void Update()
        {
            var session = CoopLanController.Instance;
            if (session == null || !session.Connected)
            {
                StopChannel(true);
                return;
            }

            if (socket == null || role != session.Role || sessionCode != session.SessionCode)
                StartChannel(session);

            Poll(session);
            if (role == CoopRole.Client && !channelConnected && Time.unscaledTime >= nextHello)
            {
                nextHello = Time.unscaledTime + HelloInterval;
                ResolveHost(session);
                Send(remoteEndpoint, CoopReliableProtocol.EncodeHello(sessionCode, localToken));
            }

            if (role == CoopRole.Client && channelConnected && Time.unscaledTime >= nextHeartbeat)
            {
                nextHeartbeat = Time.unscaledTime + HeartbeatInterval;
                Send(remoteEndpoint, CoopReliableProtocol.EncodePing(sessionCode, localToken));
            }

            if (channelConnected)
            {
                var due = ledger.CollectDue(Time.unscaledTimeAsDouble, ResendInterval, MaxAttempts);
                for (var i = 0; i < due.Count; i++)
                    Send(remoteEndpoint, CoopReliableProtocol.EncodeMessage(sessionCode, localToken, due[i]));
            }

            if (role == CoopRole.Client && channelConnected && Time.unscaledTime - lastPacketAt > Timeout)
            {
                channelConnected = false;
                remoteToken = null;
                nextHello = 0f;
            }
        }

        public long SendCritical(CoopCriticalKind kind, string payload, Action acknowledged = null)
        {
            if (!CoopRuntimeState.Connected) return 0;
            var envelope = ledger.Create(kind, payload);
            if (acknowledged != null) acknowledgements[envelope.id] = acknowledged;
            return envelope.id;
        }

        private void StartChannel(CoopLanController session)
        {
            StopSocketOnly();
            role = session.Role;
            sessionCode = session.SessionCode;
            localToken = PlayerPrefs.GetString(TokenKey, localToken ?? string.Empty);
            if (string.IsNullOrWhiteSpace(localToken)) return;

            try
            {
                if (role == CoopRole.Host)
                {
                    socket = new UdpClient();
                    try { socket.Client.ExclusiveAddressUse = false; } catch { }
                    socket.Client.SetSocketOption(SocketOptionLevel.Socket, SocketOptionName.ReuseAddress, true);
                    socket.Client.Bind(new IPEndPoint(IPAddress.Any, ReliablePort));
                }
                else if (role == CoopRole.Client)
                {
                    socket = new UdpClient(new IPEndPoint(IPAddress.Any, 0));
                    ResolveHost(session);
                }
                else return;

                socket.Client.Blocking = false;
                socket.Client.ReceiveBufferSize = 64 * 1024;
                socket.Client.SendBufferSize = 64 * 1024;
                nextHello = nextHeartbeat = 0f;
                lastPacketAt = Time.unscaledTime;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Reliable coop channel unavailable: {exception.Message}");
                StopSocketOnly();
            }
        }

        private void Poll(CoopLanController session)
        {
            if (socket == null) return;
            for (var i = 0; i < 64 && socket.Available > 0; i++)
            {
                try
                {
                    var sender = new IPEndPoint(IPAddress.Any, 0);
                    var bytes = socket.Receive(ref sender);
                    Handle(Encoding.UTF8.GetString(bytes), sender, session);
                }
                catch (SocketException exception) when (IsWouldBlock(exception))
                {
                    break;
                }
                catch (Exception exception)
                {
                    Debug.LogWarning($"Reliable coop packet failed: {exception.Message}");
                    break;
                }
            }
        }

        private void Handle(string payload, IPEndPoint sender, CoopLanController session)
        {
            if (role == CoopRole.Host &&
                CoopReliableProtocol.TryDecodeHello(payload, out var helloCode, out var helloToken))
            {
                if (helloCode != sessionCode || !MatchesMainPeer(session, helloToken)) return;
                remoteEndpoint = sender;
                remoteToken = helloToken;
                channelConnected = true;
                lastPacketAt = Time.unscaledTime;
                Send(sender, CoopReliableProtocol.EncodeWelcome(sessionCode, localToken));
                return;
            }

            if (role == CoopRole.Client &&
                CoopReliableProtocol.TryDecodeWelcome(payload, out var welcomeCode, out var welcomeToken))
            {
                if (welcomeCode != sessionCode || !EndpointsEqual(sender, remoteEndpoint) ||
                    !MatchesMainPeer(session, welcomeToken))
                    return;
                remoteToken = welcomeToken;
                channelConnected = true;
                lastPacketAt = Time.unscaledTime;
                nextHeartbeat = 0f;
                return;
            }

            if (role == CoopRole.Host &&
                CoopReliableProtocol.TryDecodePing(payload, out var pingCode, out var pingToken))
            {
                if (!AcceptPinned(pingCode, pingToken, sender)) return;
                lastPacketAt = Time.unscaledTime;
                Send(sender, CoopReliableProtocol.EncodePong(sessionCode, localToken));
                return;
            }

            if (role == CoopRole.Client &&
                CoopReliableProtocol.TryDecodePong(payload, out var pongCode, out var pongToken))
            {
                if (!AcceptPinned(pongCode, pongToken, sender)) return;
                lastPacketAt = Time.unscaledTime;
                return;
            }

            if (CoopReliableProtocol.TryDecodeMessage(
                    payload,
                    out var messageCode,
                    out var messageToken,
                    out var envelope))
            {
                if (!AcceptPinned(messageCode, messageToken, sender)) return;
                lastPacketAt = Time.unscaledTime;
                var accepted = ledger.AcceptIncoming(envelope.id);
                Send(sender, CoopReliableProtocol.EncodeAck(sessionCode, localToken, envelope.id));
                if (accepted) Received?.Invoke(envelope);
                return;
            }

            if (CoopReliableProtocol.TryDecodeAck(
                    payload,
                    out var ackCode,
                    out var ackToken,
                    out var id))
            {
                if (!AcceptPinned(ackCode, ackToken, sender)) return;
                lastPacketAt = Time.unscaledTime;
                if (!ledger.Acknowledge(id)) return;
                if (!acknowledgements.TryGetValue(id, out var callback)) return;
                acknowledgements.Remove(id);
                callback?.Invoke();
            }
        }

        private bool AcceptPinned(string code, string token, IPEndPoint sender) =>
            channelConnected && code == sessionCode && token == remoteToken &&
            EndpointsEqual(sender, remoteEndpoint);

        private static bool MatchesMainPeer(CoopLanController session, string token)
        {
            var expected = session?.RemoteState?.token;
            return string.IsNullOrWhiteSpace(expected) || expected == token;
        }

        private void ResolveHost(CoopLanController session)
        {
            if (session == null || role != CoopRole.Client) return;
            for (var i = 0; i < session.Sessions.Count; i++)
            {
                var advertisement = session.Sessions[i];
                if (advertisement == null || advertisement.sessionCode != sessionCode) continue;
                if (!IPAddress.TryParse(advertisement.address, out var address)) continue;
                remoteEndpoint = new IPEndPoint(address, ReliablePort);
                return;
            }
        }

        private void Send(IPEndPoint endpoint, string payload)
        {
            if (socket == null || endpoint == null || string.IsNullOrWhiteSpace(payload)) return;
            try
            {
                var bytes = Encoding.UTF8.GetBytes(payload);
                socket.Send(bytes, bytes.Length, endpoint);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Reliable coop send failed: {exception.Message}");
            }
        }

        private void StopChannel(bool clearLedger)
        {
            StopSocketOnly();
            role = CoopRole.Offline;
            sessionCode = remoteToken = null;
            if (!clearLedger) return;
            ledger.Clear();
            acknowledgements.Clear();
        }

        private void StopSocketOnly()
        {
            socket?.Close();
            socket = null;
            remoteEndpoint = null;
            remoteToken = null;
            channelConnected = false;
        }

        private static bool EndpointsEqual(IPEndPoint first, IPEndPoint second) =>
            first != null && second != null && first.Port == second.Port &&
            Equals(first.Address, second.Address);

        private static bool IsWouldBlock(SocketException exception) =>
            exception.SocketErrorCode == SocketError.WouldBlock ||
            exception.SocketErrorCode == SocketError.IOPending ||
            exception.SocketErrorCode == SocketError.NoBufferSpaceAvailable;

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
            StopChannel(true);
        }
    }
}
