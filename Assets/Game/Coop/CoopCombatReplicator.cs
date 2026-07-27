using System;
using System.Globalization;
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
        private const float DefenseInterval = .1f;
        private const float ChannelTimeout = 4f;
        private const string TokenKey = "riftbound-coop-device-token";

        private UdpClient socket;
        private IPEndPoint remoteEndpoint;
        private GameBootstrap game;
        private CoopReliableRuntime reliable;
        private CoopRole role = CoopRole.Offline;
        private string sessionCode;
        private string localToken;
        private string remoteToken;
        private float nextHello;
        private float nextSnapshot;
        private float nextDefense;
        private float lastPacketAt;
        private float nextRemoteMelee;
        private float nextRemoteAbility;
        private float nextRemoteDamage;
        private long outgoingSequence;
        private long lastEnemySequence;
        private long lastProjectileSequence;
        private long lastAttackSequence;
        private long lastDefenseSequence;
        private long lastDamageSequence;
        private bool channelConnected;
        private bool remoteInvulnerable;

        public static CoopCombatReplicator Instance { get; private set; }
        public bool CombatConnected => channelConnected && CoopRuntimeState.Connected;
        public bool IsClientReplica => CombatConnected && role == CoopRole.Client;
        public bool RemoteInvulnerable => remoteInvulnerable;

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
            HookReliable();
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
                lastProjectileSequence = 0;
                lastDamageSequence = 0;
                nextHello = 0f;
                Projectile.ReleaseReplicaProjectiles();
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

        public bool TryDamageRemote(float amount, CoopDamageKind kind)
        {
            if (!CombatConnected || role != CoopRole.Host ||
                remoteInvulnerable || !CoopAuthorityValidation.IsValidDamage(amount) ||
                Time.unscaledTime < nextRemoteDamage)
                return false;

            var peer = CoopLanController.Instance?.RemoteState;
            if (peer == null || peer.health <= 0f || peer.downed) return false;
            reliable ??= CoopReliableRuntime.Instance;
            if (reliable == null) return false;

            nextRemoteDamage = Time.unscaledTime + .04f;
            var payload = Mathf.Clamp(amount, .1f, 500f).ToString("0.###", CultureInfo.InvariantCulture) +
                          "," + ((int)kind).ToString(CultureInfo.InvariantCulture);
            return reliable.SendCritical(CoopCriticalKind.Damage, payload) > 0;
        }

        private void HookReliable()
        {
            if (reliable == CoopReliableRuntime.Instance) return;
            if (reliable != null) reliable.Received -= HandleReliable;
            reliable = CoopReliableRuntime.Instance;
            if (reliable != null) reliable.Received += HandleReliable;
        }

        private void HandleReliable(CoopCriticalEnvelope envelope)
        {
            if (envelope == null || envelope.kind != CoopCriticalKind.Damage ||
                CoopRuntimeState.Role != CoopRole.Client)
                return;
            var parts = (envelope.payload ?? string.Empty).Split(',');
            if (parts.Length != 2 ||
                !float.TryParse(parts[0], NumberStyles.Float, CultureInfo.InvariantCulture, out var amount) ||
                !int.TryParse(parts[1], NumberStyles.Integer, CultureInfo.InvariantCulture, out var kind) ||
                kind < 0 || kind > (int)CoopDamageKind.Hazard ||
                !CoopAuthorityValidation.IsValidDamage(amount))
                return;
            game?.Player?.TakeNetworkDamage(amount);
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
                nextHello = nextSnapshot = nextDefense = 0f;
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
            if (remoteEndpoint == null) return;

            if (!channelConnected)
            {
                if (Time.unscaledTime < nextHello) return;
                nextHello = Time.unscaledTime + HelloInterval;
                Send(remoteEndpoint, CoopCombatProtocol.EncodeHello(sessionCode, localToken));
                return;
            }

            if (Time.unscaledTime < nextDefense || game?.Player == null) return;
            nextDefense = Time.unscaledTime + DefenseInterval;
            var defense = new CoopDefenseState
            {
                sequence = ++outgoingSequence,
                invulnerable = game.Player.IsNetworkInvulnerable
            };
            Send(
                remoteEndpoint,
                CoopAuthorityProtocol.EncodeDefense(sessionCode, localToken, defense));
        }

        private void TickHost()
        {
            if (!channelConnected || remoteEndpoint == null || game == null || Time.unscaledTime < nextSnapshot)
                return;
            nextSnapshot = Time.unscaledTime + SnapshotInterval;

            var enemies = CoopCombatWorld.CaptureEnemySnapshots(game.RoomIndex);
            Send(
                remoteEndpoint,
                CoopCombatProtocol.EncodeEnemies(
                    sessionCode,
                    localToken,
                    ++outgoingSequence,
                    game.RoomIndex,
                    enemies));

            var projectiles = Projectile.CaptureEnemySnapshots();
            Send(
                remoteEndpoint,
                CoopAuthorityProtocol.EncodeProjectiles(
                    sessionCode,
                    localToken,
                    ++outgoingSequence,
                    game.RoomIndex,
                    projectiles));
        }

        private void PollSocket(CoopLanController session)
        {
            if (socket == null) return;
            for (var i = 0; i < 64 && socket.Available > 0; i++)
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
                remoteInvulnerable = false;
                lastPacketAt = Time.unscaledTime;
                lastAttackSequence = 0;
                lastDefenseSequence = 0;
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
                lastProjectileSequence = 0;
                lastDamageSequence = 0;
                CoopCombatWorld.SetReplication(true);
                Projectile.ReleaseReplicaProjectiles();
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

            if (role == CoopRole.Client &&
                CoopAuthorityProtocol.TryDecodeProjectiles(
                    payload,
                    out var projectileCode,
                    out var projectileToken,
                    out var projectileSequence,
                    out var projectileRoom,
                    out var projectileSnapshots))
            {
                if (!AcceptPinned(projectileCode, projectileToken, sender) ||
                    !CoopCombatValidation.IsFresh(projectileSequence, ref lastProjectileSequence) ||
                    game == null || projectileRoom != game.RoomIndex)
                    return;
                lastPacketAt = Time.unscaledTime;
                Projectile.ApplyEnemySnapshots(projectileSnapshots);
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
                return;
            }

            if (role == CoopRole.Host &&
                CoopAuthorityProtocol.TryDecodeDefense(
                    payload,
                    out var defenseCode,
                    out var defenseToken,
                    out var defense))
            {
                if (!AcceptPinned(defenseCode, defenseToken, sender) ||
                    !CoopCombatValidation.IsFresh(defense.sequence, ref lastDefenseSequence))
                    return;
                lastPacketAt = Time.unscaledTime;
                remoteInvulnerable = defense.invulnerable;
                return;
            }

            // Compatibility fallback for older phase-5C clients.
            if (role == CoopRole.Client &&
                CoopAuthorityProtocol.TryDecodeDamage(
                    payload,
                    out var damageCode,
                    out var damageToken,
                    out var damageEvent))
            {
                if (!AcceptPinned(damageCode, damageToken, sender) ||
                    !CoopCombatValidation.IsFresh(damageEvent.sequence, ref lastDamageSequence))
                    return;
                lastPacketAt = Time.unscaledTime;
                game?.Player?.TakeNetworkDamage(damageEvent.amount);
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
            remoteInvulnerable = false;
            outgoingSequence = 0;
            lastEnemySequence = 0;
            lastProjectileSequence = 0;
            lastAttackSequence = 0;
            lastDefenseSequence = 0;
            lastDamageSequence = 0;
            nextRemoteMelee = nextRemoteAbility = nextRemoteDamage = 0f;
            if (wasClient)
            {
                CoopCombatWorld.SetReplication(false);
                Projectile.ReleaseReplicaProjectiles();
            }
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
            if (reliable != null) reliable.Received -= HandleReliable;
            if (Instance == this) Instance = null;
            StopChannel();
        }
    }
}
