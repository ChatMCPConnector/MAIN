using System;
using System.Collections.Generic;
using System.Net;
using System.Net.Sockets;
using System.Text;
using UnityEngine;

namespace Riftbound
{
    public sealed class CoopLanController : MonoBehaviour
    {
        private const int DiscoveryPort = 47777;
        private const int FirstGamePort = 47778;
        private const int LastGamePort = 47787;
        private const float DiscoveryInterval = .8f;
        private const float StateInterval = .1f;
        private const float HelloInterval = 1f;
        private const float ConnectionTimeout = 4f;
        private const float AdvertisementLifetime = 3f;
        private const float PeerUiInterval = .45f;
        private const string TokenKey = "riftbound-coop-device-token";

        private readonly List<CoopSessionAdvertisement> sessions = new List<CoopSessionAdvertisement>();
        private readonly CoopReadyGate readyGate = new CoopReadyGate();
        private readonly CoopReviveState reviveState = new CoopReviveState();

        private UdpClient discoverySocket;
        private UdpClient gameSocket;
        private IPEndPoint remoteEndpoint;
        private CoopPeerState remoteState;
        private GameBootstrap game;
        private CoopView view;
        private GameObject remoteAvatar;
        private Renderer remoteRenderer;
        private Action pendingRoomAdvance;
        private Action localRevived;
        private Action partyDefeated;
        private string localToken;
        private string remoteToken;
        private string sessionCode;
        private int gamePort;
        private long localSequence;
        private float nextDiscovery;
        private float nextState;
        private float nextHello;
        private float nextPeerUi;
        private float lastPacketAt;
        private float disconnectedAt = -1000f;
        private bool partyDefeatRaised;

        public static CoopLanController Instance { get; private set; }
        public CoopRole Role { get; private set; } = CoopRole.Offline;
        public CoopConnectionState State { get; private set; } = CoopConnectionState.Offline;
        public IReadOnlyList<CoopSessionAdvertisement> Sessions => sessions;
        public CoopPeerState RemoteState => remoteState;
        public string SessionCode => sessionCode ?? "----";
        public bool Connected => State == CoopConnectionState.Connected;
        public bool LocalReady => readyGate.LocalReady;
        public bool RemoteReady => readyGate.RemoteReady;
        public bool RemoteDowned => reviveState.RemoteDowned;
        public bool CanReviveRemote => reviveState.CanReviveRemote && Connected;
        public bool GameSafe => game != null && game.IsSafeRoom;
        public string LocalAddress => ResolveLocalAddress();

        [RuntimeInitializeOnLoadMethod(RuntimeInitializeLoadType.BeforeSceneLoad)]
        private static void EnsureRuntime()
        {
            if (FindFirstObjectByType<CoopLanController>() != null) return;
            var root = new GameObject("Coop LAN Runtime");
            DontDestroyOnLoad(root);
            root.AddComponent<CoopLanController>();
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
            localToken = LoadOrCreateToken();
            OpenDiscoverySocket();
        }

        private void Start()
        {
            game = FindFirstObjectByType<GameBootstrap>();
            view = CoopView.Create(this);
            NotifyChanged();
        }

        private void Update()
        {
            if (game == null) game = FindFirstObjectByType<GameBootstrap>();
            PollDiscovery();
            PollGameSocket();
            RemoveExpiredSessions();
            TickRole();
            UpdateRemoteAvatar();
        }

        public bool StartHost()
        {
            if (game == null || !game.IsSafeRoom)
            {
                ShowMessage("HOST NUR IN SICHEREM RAUM");
                return false;
            }

            StopSession(false);
            if (!OpenHostSocket())
            {
                State = CoopConnectionState.Rejected;
                ShowMessage("KEIN FREIER LAN-PORT");
                NotifyChanged();
                return false;
            }

            Role = CoopRole.Host;
            State = CoopConnectionState.Hosting;
            sessionCode = CoopSessionCode.FromToken($"{localToken}:{DateTime.UtcNow.Ticks}");
            remoteToken = null;
            remoteEndpoint = null;
            remoteState = null;
            readyGate.Reset();
            reviveState.Reset();
            CoopRuntimeState.Set(Role, false);
            nextDiscovery = 0f;
            NotifyChanged();
            return true;
        }

        public bool Join(CoopSessionAdvertisement advertisement)
        {
            if (advertisement == null || !advertisement.joinable)
            {
                ShowMessage("SITZUNG NICHT BEITRETBAR");
                return false;
            }

            StopSession(false);
            try
            {
                gameSocket = new UdpClient(new IPEndPoint(IPAddress.Any, 0));
                ConfigureNonBlocking(gameSocket);
                remoteEndpoint = new IPEndPoint(IPAddress.Parse(advertisement.address), advertisement.port);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Coop join socket failed: {exception.Message}");
                StopSession(false);
                State = CoopConnectionState.Rejected;
                NotifyChanged();
                return false;
            }

            Role = CoopRole.Client;
            State = CoopConnectionState.Connecting;
            sessionCode = advertisement.sessionCode;
            remoteToken = null;
            remoteState = null;
            readyGate.Reset();
            reviveState.Reset();
            CoopRuntimeState.Set(Role, false);
            nextHello = 0f;
            lastPacketAt = Time.unscaledTime;
            NotifyChanged();
            return true;
        }

        public void Disconnect()
        {
            if (Connected) SendCommand("BYE");
            ContinueSoloAndStop("KOOP BEENDET");
        }

        public void RequestRoomAdvance(Action authorized)
        {
            if (!Connected)
            {
                authorized?.Invoke();
                return;
            }

            pendingRoomAdvance = authorized;
            readyGate.SetLocal(true);
            SendStateNow();
            ShowMessage(readyGate.RemoteReady ? "BEIDE BEREIT" : "WARTE AUF PARTNER");
            TryCompleteReadyGate();
            NotifyChanged();
        }

        public void MarkLocalDowned(Action revived, Action defeated)
        {
            if (!Connected)
            {
                defeated?.Invoke();
                return;
            }

            localRevived = revived;
            partyDefeated = defeated;
            reviveState.SetLocalDowned(true);
            SendStateNow();
            ShowMessage("GEFALLEN · PARTNER KANN DICH WIEDERBELEBEN");
            EvaluatePartyDefeat();
            NotifyChanged();
        }

        public void RevivePartner()
        {
            if (!CanReviveRemote) return;
            SendCommand("REVIVE");
            ShowMessage("WIEDERBELEBUNG GESENDET");
        }

        public void SetLocalReadyFromMenu()
        {
            if (!Connected || !GameSafe) return;
            readyGate.SetLocal(!readyGate.LocalReady);
            SendStateNow();
            TryCompleteReadyGate();
            NotifyChanged();
        }

        private void TickRole()
        {
            var now = Time.unscaledTime;
            if (Role == CoopRole.Host)
            {
                if (now >= nextDiscovery)
                {
                    nextDiscovery = now + DiscoveryInterval;
                    BroadcastAdvertisement();
                }
            }
            else if (Role == CoopRole.Client &&
                     (State == CoopConnectionState.Connecting || State == CoopConnectionState.Reconnecting) &&
                     now >= nextHello)
            {
                nextHello = now + HelloInterval;
                SendHello();
            }

            if (State == CoopConnectionState.Reconnecting &&
                now - lastPacketAt > CoopReconnectPolicy.GraceSeconds)
            {
                ContinueSoloAndStop("WIEDERVERBINDUNG ABGEBROCHEN · SOLO WEITER");
                return;
            }

            if (Connected && now >= nextState)
            {
                nextState = now + StateInterval;
                SendStateNow();
            }

            if (Connected && now - lastPacketAt > ConnectionTimeout)
                HandleConnectionTimeout();
        }

        private void PollDiscovery()
        {
            if (discoverySocket == null) return;
            for (var i = 0; i < 16 && discoverySocket.Available > 0; i++)
            {
                try
                {
                    var sender = new IPEndPoint(IPAddress.Any, 0);
                    var bytes = discoverySocket.Receive(ref sender);
                    var payload = Encoding.UTF8.GetString(bytes);
                    if (!CoopProtocol.TryDecodeDiscovery(payload, sender.Address.ToString(), out var advertisement))
                        continue;
                    if (Role == CoopRole.Host && advertisement.sessionCode == sessionCode)
                        continue;

                    advertisement.lastSeenSeconds = Time.unscaledTimeAsDouble;
                    var existing = sessions.FindIndex(item => item.Key == advertisement.Key);
                    if (existing >= 0) sessions[existing] = advertisement;
                    else sessions.Add(advertisement);
                    NotifyChanged();
                }
                catch (SocketException exception) when (IsWouldBlock(exception))
                {
                    break;
                }
                catch (Exception exception)
                {
                    Debug.LogWarning($"Coop discovery receive failed: {exception.Message}");
                    break;
                }
            }
        }

        private void PollGameSocket()
        {
            if (gameSocket == null) return;
            for (var i = 0; i < 32 && gameSocket.Available > 0; i++)
            {
                try
                {
                    var sender = new IPEndPoint(IPAddress.Any, 0);
                    var bytes = gameSocket.Receive(ref sender);
                    HandlePacket(Encoding.UTF8.GetString(bytes), sender);
                }
                catch (SocketException exception) when (IsWouldBlock(exception))
                {
                    break;
                }
                catch (Exception exception)
                {
                    Debug.LogWarning($"Coop packet receive failed: {exception.Message}");
                    break;
                }
            }
        }

        private void HandlePacket(string payload, IPEndPoint sender)
        {
            if (Role == CoopRole.Host && CoopProtocol.TryDecodeHello(payload, out var code, out var token))
            {
                HandleHello(code, token, sender);
                return;
            }

            if (Role == CoopRole.Client &&
                CoopProtocol.TryDecodeWelcome(payload, out var welcomeCode, out var hostToken, out var hostSeed, out var hostRoom))
            {
                if (welcomeCode != sessionCode || !EndpointsEqual(sender, remoteEndpoint)) return;
                remoteToken = hostToken;
                remoteState = null;
                lastPacketAt = Time.unscaledTime;
                State = CoopConnectionState.Connected;
                CoopRuntimeState.Set(Role, true);
                game?.SynchronizeToHost(hostSeed, hostRoom);
                EnsureRemoteAvatar();
                NotifyChanged();
                return;
            }

            if (CoopProtocol.TryDecodeState(payload, out var state))
            {
                if (!AcceptState(state, sender)) return;
                var readyChanged = remoteState == null || remoteState.ready != state.ready;
                var downedChanged = remoteState == null || remoteState.downed != state.downed;
                remoteState = state;
                lastPacketAt = Time.unscaledTime;
                readyGate.SetRemote(state.ready);
                reviveState.SetRemoteDowned(state.downed);
                if (Role == CoopRole.Client && game != null &&
                    (game.Seed != state.seed || game.RoomIndex != state.roomIndex))
                    game.SynchronizeToHost(state.seed, state.roomIndex);
                TryCompleteReadyGate();
                EvaluatePartyDefeat();
                if (readyChanged || downedChanged || Time.unscaledTime >= nextPeerUi)
                {
                    nextPeerUi = Time.unscaledTime + PeerUiInterval;
                    NotifyChanged();
                }
                return;
            }

            if (CoopProtocol.TryDecodeCommand(payload, out var command, out var tokenValue))
            {
                if (!AcceptTokenAndEndpoint(tokenValue, sender)) return;
                lastPacketAt = Time.unscaledTime;
                HandleCommand(command);
                return;
            }

            if (Role == CoopRole.Client && CoopProtocol.TryDecodeReject(payload, out var reason))
            {
                State = CoopConnectionState.Rejected;
                ShowMessage($"KOOP ABGELEHNT: {reason}");
                NotifyChanged();
            }
        }

        private void HandleHello(string code, string token, IPEndPoint sender)
        {
            if (code != sessionCode)
            {
                Send(sender, CoopProtocol.EncodeReject("CODE"));
                return;
            }

            var reservationExpired = !string.IsNullOrWhiteSpace(remoteToken) &&
                                     disconnectedAt > -999f &&
                                     Time.unscaledTime - disconnectedAt > CoopReconnectPolicy.GraceSeconds;
            if (reservationExpired)
            {
                remoteToken = null;
                remoteEndpoint = null;
                remoteState = null;
            }

            var reconnect = !string.IsNullOrWhiteSpace(remoteToken) &&
                            CoopReconnectPolicy.CanReconnect(
                                remoteToken,
                                token,
                                Time.unscaledTime - disconnectedAt);
            var newJoin = string.IsNullOrWhiteSpace(remoteToken) && game != null && game.IsSafeRoom;
            if (!newJoin && !reconnect)
            {
                Send(sender, CoopProtocol.EncodeReject(game != null && game.IsSafeRoom ? "BESETZT" : "KAMPF"));
                return;
            }

            remoteToken = token;
            remoteEndpoint = sender;
            remoteState = null;
            disconnectedAt = -1000f;
            lastPacketAt = Time.unscaledTime;
            State = CoopConnectionState.Connected;
            CoopRuntimeState.Set(Role, true);
            EnsureRemoteAvatar();
            Send(sender, CoopProtocol.EncodeWelcome(sessionCode, localToken, game.Seed, game.RoomIndex));
            SendStateNow();
            ShowMessage(reconnect ? "PARTNER WIEDERVERBUNDEN" : "PARTNER VERBUNDEN");
            NotifyChanged();
        }

        private bool AcceptState(CoopPeerState state, IPEndPoint sender)
        {
            if (!Connected || state == null || !AcceptTokenAndEndpoint(state.token, sender)) return false;
            return remoteState == null || state.sequence > remoteState.sequence;
        }

        private bool AcceptTokenAndEndpoint(string token, IPEndPoint sender)
        {
            return Connected &&
                   !string.IsNullOrWhiteSpace(remoteToken) &&
                   string.Equals(token, remoteToken, StringComparison.Ordinal) &&
                   EndpointsEqual(sender, remoteEndpoint);
        }

        private void HandleCommand(string command)
        {
            switch (command)
            {
                case "REVIVE":
                    if (!reviveState.LocalDowned) return;
                    reviveState.SetLocalDowned(false);
                    partyDefeatRaised = false;
                    var reviveCallback = localRevived;
                    localRevived = null;
                    reviveCallback?.Invoke();
                    SendStateNow();
                    ShowMessage("WIEDERBELEBT");
                    NotifyChanged();
                    break;
                case "ADVANCE":
                    if (Role != CoopRole.Client) return;
                    readyGate.Reset();
                    var roomCallback = pendingRoomAdvance;
                    pendingRoomAdvance = null;
                    SendStateNow();
                    roomCallback?.Invoke();
                    break;
                case "BYE":
                    ContinueSoloAndStop("PARTNER HAT DIE SITZUNG VERLASSEN");
                    break;
            }
        }

        private void TryCompleteReadyGate()
        {
            if (Role != CoopRole.Host || pendingRoomAdvance == null) return;
            if (!readyGate.TryConsume()) return;
            SendCommand("ADVANCE");
            var callback = pendingRoomAdvance;
            pendingRoomAdvance = null;
            SendStateNow();
            callback?.Invoke();
        }

        private void EvaluatePartyDefeat()
        {
            if (!reviveState.PartyDefeated || partyDefeatRaised) return;
            partyDefeatRaised = true;
            var callback = partyDefeated;
            partyDefeated = null;
            callback?.Invoke();
        }

        private void HandleConnectionTimeout()
        {
            if (Role == CoopRole.Host)
            {
                disconnectedAt = Time.unscaledTime;
                State = CoopConnectionState.Hosting;
                CoopRuntimeState.Set(Role, false);
                HideRemoteAvatar();
                remoteState = null;
                reviveState.SetRemoteDowned(false);
                readyGate.Reset();
                ContinueLocalPlayerIfNeeded();
                ContinuePendingRoomIfNeeded();
                ShowMessage("PARTNER GETRENNT · SOLO WEITER · WIEDERVERBINDUNG MÖGLICH");
            }
            else if (Role == CoopRole.Client)
            {
                State = CoopConnectionState.Reconnecting;
                CoopRuntimeState.Set(Role, false);
                HideRemoteAvatar();
                remoteState = null;
                reviveState.SetRemoteDowned(false);
                var waitingForRoom = pendingRoomAdvance != null;
                readyGate.Reset();
                if (waitingForRoom) readyGate.SetLocal(true);
                nextHello = 0f;
                ShowMessage("VERBINDUNG VERLOREN · NEUER VERSUCH");
            }

            NotifyChanged();
        }

        private void BroadcastAdvertisement()
        {
            if (gameSocket == null || Role != CoopRole.Host) return;
            var reservationActive = !string.IsNullOrWhiteSpace(remoteToken) &&
                                    disconnectedAt > -999f &&
                                    Time.unscaledTime - disconnectedAt <= CoopReconnectPolicy.GraceSeconds;
            var advertisement = new CoopSessionAdvertisement
            {
                port = gamePort,
                sessionCode = sessionCode,
                seed = game != null ? game.Seed : 0,
                roomIndex = game != null ? game.RoomIndex : 0,
                playerCount = Connected ? 2 : 1,
                joinable = !Connected && !reservationActive && game != null && game.IsSafeRoom
            };
            Send(new IPEndPoint(IPAddress.Broadcast, DiscoveryPort), CoopProtocol.EncodeDiscovery(advertisement));
        }

        private void SendHello()
        {
            if (remoteEndpoint == null) return;
            Send(remoteEndpoint, CoopProtocol.EncodeHello(sessionCode, localToken));
        }

        private void SendStateNow()
        {
            if (!Connected || gameSocket == null || remoteEndpoint == null || game?.Player == null) return;
            var position = game.Player.transform.position;
            var state = new CoopPeerState
            {
                sequence = ++localSequence,
                token = localToken,
                seed = game.Seed,
                roomIndex = game.RoomIndex,
                x = position.x,
                y = position.y,
                z = position.z,
                health = game.Player.Health,
                maxHealth = game.Player.MaxHealth,
                downed = reviveState.LocalDowned,
                ready = readyGate.LocalReady
            };
            Send(remoteEndpoint, CoopProtocol.EncodeState(state));
        }

        private void SendCommand(string command)
        {
            if (!Connected || remoteEndpoint == null) return;
            Send(remoteEndpoint, CoopProtocol.EncodeCommand(command, localToken));
        }

        private void Send(IPEndPoint endpoint, string payload)
        {
            if (gameSocket == null || endpoint == null || string.IsNullOrEmpty(payload)) return;
            try
            {
                var bytes = Encoding.UTF8.GetBytes(payload);
                gameSocket.Send(bytes, bytes.Length, endpoint);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Coop send failed: {exception.Message}");
            }
        }

        private bool OpenHostSocket()
        {
            for (var port = FirstGamePort; port <= LastGamePort; port++)
            {
                try
                {
                    gameSocket = new UdpClient(new IPEndPoint(IPAddress.Any, port));
                    ConfigureNonBlocking(gameSocket);
                    gameSocket.EnableBroadcast = true;
                    gamePort = port;
                    return true;
                }
                catch
                {
                    gameSocket?.Close();
                    gameSocket = null;
                }
            }
            return false;
        }

        private void OpenDiscoverySocket()
        {
            try
            {
                discoverySocket = new UdpClient();
                try
                {
                    discoverySocket.Client.ExclusiveAddressUse = false;
                }
                catch
                {
                    // Some Android socket backends do not expose this option.
                }
                discoverySocket.Client.SetSocketOption(
                    SocketOptionLevel.Socket,
                    SocketOptionName.ReuseAddress,
                    true);
                discoverySocket.Client.Bind(new IPEndPoint(IPAddress.Any, DiscoveryPort));
                ConfigureNonBlocking(discoverySocket);
            }
            catch (Exception exception)
            {
                Debug.LogWarning($"Coop discovery unavailable: {exception.Message}");
                discoverySocket?.Close();
                discoverySocket = null;
            }
        }

        private static void ConfigureNonBlocking(UdpClient socket)
        {
            socket.Client.Blocking = false;
            socket.Client.ReceiveBufferSize = 64 * 1024;
            socket.Client.SendBufferSize = 64 * 1024;
        }

        private void RemoveExpiredSessions()
        {
            var removed = sessions.RemoveAll(
                item => Time.unscaledTimeAsDouble - item.lastSeenSeconds > AdvertisementLifetime);
            if (removed > 0) NotifyChanged();
        }

        private void EnsureRemoteAvatar()
        {
            if (remoteAvatar != null)
            {
                remoteAvatar.SetActive(true);
                return;
            }

            remoteAvatar = GameObject.CreatePrimitive(PrimitiveType.Capsule);
            remoteAvatar.name = "Coop Remote Player";
            remoteAvatar.transform.localScale = Vector3.one * .92f;
            var collider = remoteAvatar.GetComponent<Collider>();
            if (collider != null) collider.enabled = false;
            remoteRenderer = remoteAvatar.GetComponent<Renderer>();
            DontDestroyOnLoad(remoteAvatar);
        }

        private void UpdateRemoteAvatar()
        {
            if (!Connected || remoteState == null)
            {
                HideRemoteAvatar();
                return;
            }

            EnsureRemoteAvatar();
            var target = new Vector3(remoteState.x, remoteState.y, remoteState.z);
            remoteAvatar.transform.position = Vector3.Lerp(
                remoteAvatar.transform.position,
                target,
                14f * Time.unscaledDeltaTime);
            if (remoteRenderer != null)
            {
                var color = remoteState.downed
                    ? new Color(.35f, .08f, .08f)
                    : Role == CoopRole.Host
                        ? new Color(1f, .52f, .12f)
                        : new Color(.18f, .82f, 1f);
                remoteRenderer.sharedMaterial = WorldFactory.GetLitMaterial(color);
            }
        }

        private void HideRemoteAvatar()
        {
            if (remoteAvatar != null) remoteAvatar.SetActive(false);
        }

        private void ContinueSoloAndStop(string message)
        {
            var roomCallback = pendingRoomAdvance;
            var reviveCallback = reviveState.LocalDowned ? localRevived : null;
            StopSession(false);
            reviveCallback?.Invoke();
            roomCallback?.Invoke();
            ShowMessage(message);
        }

        private void ContinueLocalPlayerIfNeeded()
        {
            if (!reviveState.LocalDowned) return;
            reviveState.SetLocalDowned(false);
            var callback = localRevived;
            localRevived = null;
            callback?.Invoke();
        }

        private void ContinuePendingRoomIfNeeded()
        {
            var callback = pendingRoomAdvance;
            pendingRoomAdvance = null;
            callback?.Invoke();
        }

        private void StopSession(bool resetUi)
        {
            gameSocket?.Close();
            gameSocket = null;
            remoteEndpoint = null;
            remoteState = null;
            remoteToken = null;
            sessionCode = null;
            gamePort = 0;
            localSequence = 0;
            pendingRoomAdvance = null;
            localRevived = null;
            partyDefeated = null;
            partyDefeatRaised = false;
            readyGate.Reset();
            reviveState.Reset();
            HideRemoteAvatar();
            Role = CoopRole.Offline;
            State = CoopConnectionState.Offline;
            CoopRuntimeState.Reset();
            if (resetUi) ShowMessage("KOOP BEENDET");
            NotifyChanged();
        }

        private void NotifyChanged()
        {
            view?.RefreshSoon();
        }

        private void ShowMessage(string text)
        {
            FindFirstObjectByType<TouchHud>()?.ShowMessage(text, 1.8f);
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

        private static string LoadOrCreateToken()
        {
            var value = PlayerPrefs.GetString(TokenKey, string.Empty);
            if (!string.IsNullOrWhiteSpace(value)) return value;
            value = Guid.NewGuid().ToString("N");
            PlayerPrefs.SetString(TokenKey, value);
            PlayerPrefs.Save();
            return value;
        }

        private static string ResolveLocalAddress()
        {
            try
            {
                foreach (var address in Dns.GetHostEntry(Dns.GetHostName()).AddressList)
                    if (address.AddressFamily == AddressFamily.InterNetwork &&
                        !IPAddress.IsLoopback(address))
                        return address.ToString();
            }
            catch
            {
                // UDP broadcast discovery can still work when hostname lookup is unavailable.
            }
            return "Lokales Netzwerk";
        }

        private void OnDestroy()
        {
            if (Instance == this) Instance = null;
            gameSocket?.Close();
            discoverySocket?.Close();
            CoopRuntimeState.Reset();
        }

        private void OnApplicationQuit()
        {
            if (Connected) SendCommand("BYE");
            gameSocket?.Close();
            discoverySocket?.Close();
        }
    }
}