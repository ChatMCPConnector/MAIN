using System;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

namespace Riftbound
{
    public sealed class CoopCombatReplicator : MonoBehaviour
    {
        private const int CombatPort = 47820;
        private const float HelloInterval = .5f;
        private const float SnapshotInterval = .1f;
        private const float ChannelTimeout = 4f;
        private const string TokenKey = "riftbound-coop-device-token";

        private UdpClient socket;
        private IPEndPoint remoteEndpoint;
        private GameBootstrap game;
        private CoopRole role = CoopRole.Offline;
        private string sessionCode;
        private string localToken;
        private string remoteToken;
        private float nextHello;
        private float nextSnapshot;
        private float lastPacketAt;
        private float nextRemoteMelee;
        private float nextRemoteAbility;
        private long outgoingSequence;
        private long lastEnemySequence;
        private long lastAttackSequence;
        private bool channelConnected;

        public static CoopCombatReplicator Instance { get; private set; }
        public bool CombatConnected => channelConnected && CoopRuntimeState.Connected;
        public bool IsClientReplica => CombatConnected && role == CoopRole.Client;

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopCombatReplicator>() != null) return;
            var root = new GameObject("Coop Combat Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopCombatReplicator>();
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
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            var session = CoopLanController.Instance;
            if (session == null || !session.Connected)
            {
                StopChannel();
                return;
            }

            if (socket == null || role != session.Role || sessionCode != session.SessionCode)
                StartChannel(session);

            PollSocket(session);
            if (role == CoopRole.Client)
                TickClient(session);
            else if (role == CoopRole.Host)
                TickHost();

            if (channelConnected &&
                role == CoopRole.Client &&
                Time.unscaledTime - lastPacketAt > ChannelTimeout)
            {
                channelConnected = false;
                remoteToken = null;
                lastEnemySequence = 0;
                nextHello = 0f;
            }
        }

        public bool SendAttackIntent(
            CoopAttackKind kind,
            Vector3 origin,
            Vector3 direction,
            float damage,
            float range)
        {
            if (!CombatConnected || role != CoopRole.Client || remoteEndpoint == null)
                return false;

            var intent = new CoopAttackIntent
            {
                sequence = ++outgoingSequence,
                kind = kind,
                origin = origin,
                direction = direction.sqrMagnitude > .001f ? direction.normalized : Vector3.forward,
                damage = Mathf.Clamp(damage, 1f, 500f),
                range = Mathf.Clamp(range, .5f, 4f)
            };
            Send(remoteEndpoint, CoopCombatProtocol.EncodeAttack(sessionCode, localToken, intent));
            return true;
        }

        private void StartChannel(CoopLanController session)
        {
            StopChannel();
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
                    socket.Client.Bind(new IPEndPoint(IPAddress.Any, CombatPort));
                }
                else if (role == CoopRole.Client)
                {
                    socket = new UdpClient(new IPEndPoint(IPAddress.Any, 0));
                    ResolveHostEndpoint(session);
                }
                else
                {
                    return;
                }

                ConfigureNonBlocking(socket);
                nextHello = nextSnapshot = 0f;
                lastPacketAt = Time.unscaledTime;
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Coop combat channel unavailable: {exception.Message}");
                StopChannel();
            }
        }

        private void TickClient(CoopLanController session)
        {
            if (remoteEndpoint == null) ResolveHostEndpoint(session);
            if (remoteEndpoint == null || channelConnected || Time.unscaledTime < nextHello) return;
            nextHello = Time.unscaledTime + HelloInterval;
            Send(remoteEndpoint, CoopCombatProtocol.EncodeHello(sessionCode, localToken));
        }

        private void TickHost()
        {
            if (!channelConnected || remoteEndpoint == null || game == null || Time.unscaledTime < nextSnapshot)
                return;
            nextSnapshot = Time.unscaledTime + SnapshotInterval;
            var snapshots = CoopCombatWorld.CaptureEnemySnapshots(game.RoomIndex);
            var payload = CoopCombatProtocol.EncodeEnemies(
                sessionCode,
                localToken,
                ++outgoingSequence,
                game.RoomIndex,
                snapshots);
            Send(remoteEndpoint, payload);
        }

        private void PollSocket(CoopLanController session)
        {
            if (socket == null) return;
            for (var i = 0; i < 48 && socket.Available > 0; i++)
            {
                try
                {
                    var sender = new IPEndPoint(IPAddress.Any, 0);
                    var bytes = socket.Receive(ref sender);
                    HandlePacket(Encoding.UTF8.GetString(bytes), sender, session);
                }
                catch (SocketException exception) when (IsWouldBlock(exception))
                {
                    break;
                }
                catch (Exception exception)
                {
                    Debug.LogWarning($"Coop combat packet failed: {exception.Message}");
                    break;
                }
            }
        }

        private void HandlePacket(string payload, IPEndPoint sender, CoopLanController session)
        {
            if (role == CoopRole.Host &&
                CoopCombatProtocol.TryDecodeHello(payload, out var helloCode, out var helloToken))
            {
                if (helloCode != sessionCode || !MatchesMainPeerToken(session, helloToken)) return;
                remoteEndpoint = sender;
                remoteToken = helloToken;
                channelConnected = true;
                lastPacketAt = Time.unscaledTime;
                lastAttackSequence = 0;
                Send(sender, CoopCombatProtocol.EncodeWelcome(sessionCode, localToken));
                return;
            }

            if (role == CoopRole.Client &&
                CoopCombatProtocol.TryDecodeWelcome(payload, out var welcomeCode, out var welcomeToken))
            {
                if (welcomeCode != sessionCode || !EndpointsEqual(sender, remoteEndpoint) ||
                    !MatchesMainPeerToken(session, welcomeToken))
                    return;
                remoteToken = welcomeToken;
                channelConnected = true;
                lastPacketAt = Time.unscaledTime;
                lastEnemySequence = 0;
                CoopCombatWorld.SetReplication(true);
                return;
            }

            if (role == CoopRole.Client &&
                CoopCombatProtocol.TryDecodeEnemies(
                    payload,
                    out var enemyCode,
                    out var enemyToken,
                    out var enemySequence,
                    out var roomIndex,
                    out var snapshots))
            {
                if (!AcceptPinned(enemyCode, enemyToken, sender) ||
                    !CoopCombatValidation.IsFresh(enemySequence, ref lastEnemySequence))
                    return;
                lastPacketAt = Time.unscaledTime;
                CoopCombatWorld.ApplyEnemySnapshots(game, roomIndex, snapshots);
                return;
            }

            if (role == CoopRole.Host &&
                CoopCombatProtocol.TryDecodeAttack(
                    payload,
                    out var attackCode,
                    out var attackToken,
                    out var intent))
            {
                if (!AcceptPinned(attackCode, attackToken, sender) ||
                    !CoopCombatValidation.IsFresh(intent.sequence, ref lastAttackSequence))
                    return;

                var peer = session.RemoteState;
                if (peer == null) return;
                var confirmed = new Vector3(peer.x, peer.y, peer.z);
                if (!CoopCombatValidation.IsValidAttack(
                        intent,
                        confirmed,
                        Time.unscaledTime,
                        ref nextRemoteMelee,
                        ref nextRemoteAbility))
                    return;

                lastPacketAt = Time.unscaledTime;
                CoopCombatWorld.ApplyRemoteAttack(game, intent);
            }
        }

        private bool AcceptPinned(string code, string token, IPEndPoint sender)
        {
            return channelConnected &&
                   code == sessionCode &&
                   !string.IsNullOrWhiteSpace(remoteToken) &&
                   token == remoteToken &&
                   EndpointsEqual(sender, remoteEndpoint);
        }

        private static bool MatchesMainPeerToken(CoopLanController session, string token)
        {
            var expected = session?.RemoteState?.token;
            return string.IsNullOrWhiteSpace(expected) || expected == token;
        }

        private void ResolveHostEndpoint(CoopLanController session)
        {
            if (session == null || role != CoopRole.Client) return;
            for (var i = 0; i < session.Sessions.Count; i++)
            {
                var advertisement = session.Sessions[i];
                if (advertisement == null || advertisement.sessionCode != sessionCode) continue;
                if (!IPAddress.TryParse(advertisement.address, out var address)) continue;
                remoteEndpoint = new IPEndPoint(address, CombatPort);
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
                Debug.LogWarning($"Coop combat send failed: {exception.Message}");
            }
        }

        private void StopChannel()
        {
            var wasClient = role == CoopRole.Client;
            socket?.Close();
            socket = null;
            remoteEndpoint = null;
            remoteToken = null;
            sessionCode = null;
            role = CoopRole.Offline;
            channelConnected = false;
            outgoingSequence = 0;
            lastEnemySequence = 0;
            lastAttackSequence = 0;
            nextRemoteMelee = nextRemoteAbility = 0f;
            if (wasClient) CoopCombatWorld.SetReplication(false);
        }

        private static void ConfigureNonBlocking(UdpClient client)
        {
            client.Client.Blocking = false;
            client.Client.ReceiveBufferSize = 64 * 1024;
            client.Client.SendBufferSize = 64 * 1024;
        }

        private static bool EndpointsEqual(IPEndPoint first, IPEndPoint second)
        {
            return first != null && second != null &&
                   first.Port == second.Port &&
                   Equals(first.Address, second.Address);
        }

        private static bool IsWouldBlock(SocketException exception)
        {
            return exception.SocketErrorCode == SocketError.WouldBlock ||
                   exception.SocketErrorCode == SocketError.IOPending ||
                   exception.SocketErrorCode == SocketError.NoBufferSpaceAvailable;
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
            StopChannel();
        }
    }
}
