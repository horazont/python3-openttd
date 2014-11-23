import asyncio
import logging

from . import limits, packet, server_info
from .protocol import OpenTTDPacketProtocol

try:
    from enum import Enum, IntEnum
except ImportError:
    Enum = object
    IntEnum = object

logger = logging.getLogger(__name__)

class ClientState(Enum):
    CONNECTED = 0
    AUTHENTICATED = 1
    DISCONNECTED = 2

class UpdateType(Enum):
    # Updates about the date of the game.
    DATE = 0
    # Updates about the information of clients.
    CLIENT_INFO = 1
    # Updates about the generic information of companies.
    COMPANY_INFO = 2
    # Updates about the economy of companies.
    COMPANY_ECONOMY = 3
    # Updates about the statistics of companies.
    COMPANY_STATS = 4
    # The admin would like to have chat messages.
    CHAT = 5
    # The admin would like to have console messages.
    CONSOLE = 6
    # The admin would like a list of all DoCommand names.
    CMD_NAMES = 7
    # The admin would like to have DoCommand information.
    CMD_LOGGING = 8
    # The admin would like to have gamescript messages.
    GAMESCRIPT = 9

class UpdateFrequency(IntEnum):
    # The admin can poll this.
    ADMIN_FREQUENCY_POLL = 1
    # The admin gets information about this on a daily basis.
    ADMIN_FREQUENCY_DAILY = 2
    # The admin gets information about this on a weekly basis.
    ADMIN_FREQUENCY_WEEKLY = 4
    # The admin gets information about this on a monthly basis.
    ADMIN_FREQUENCY_MONTHLY = 8
    # The admin gets information about this on a quarterly basis.
    ADMIN_FREQUENCY_QUARTERLY = 16
    # The admin gets information about this on a yearly basis.
    ADMIN_FREQUENCY_ANUALLY = 32
    # The admin gets information about this when it changes.
    ADMIN_FREQUENCY_AUTOMATIC = 64

class Client:
    def __init__(self, *, loop=None, **kwargs):
        super().__init__(**kwargs)
        self._loop = loop
        self._reset()

    def _reset(self):
        self._protocol = None
        self._encoding = "utf8"
        self._state = ClientState.DISCONNECTED
        self._update_map = {}
        self._server_info = server_info.ServerInformation()

    def _require_disconnected(self):
        if self._state != ClientState.DISCONNECTED:
            raise ConnectionError("Already connected")

    def _require_connected_and_unauthed(self):
        if self._state != ClientState.CONNECTED:
            raise ConnectionError("Incorrect state")

    def _require_connected_or_authed(self):
        if self._state == ClientState.DISCONNECTED:
            raise ConnectionError("Not connected")

    def _require_authed(self):
        if self._state == ClientState.AUTHENTICATED:
            raise ConnectionError("Not authenticated or not connected")

    @asyncio.coroutine
    def _fatal_error(self, exc):
        yield from self.disconnect()
        raise exc

    @asyncio.coroutine
    def connect_tcp(self, host, port=3977, **kwargs):
        self._require_disconnected()
        _, protocol = yield from self._loop.create_connection(
            lambda: OpenTTDPacketProtocol(loop=self._loop),
            host=host,
            port=port)

        yield from self.connect(protocol, **kwargs)

    @asyncio.coroutine
    def connect(self, protocol, *, encoding=None):
        self._require_disconnected()
        self._protocol = protocol
        self._encoding = encoding or "utf8"
        self._state = ClientState.CONNECTED

    @asyncio.coroutine
    def authenticate(self, password, client_name, client_version):
        self._require_connected_and_unauthed()
        password = password.encode(self._encoding)
        client_name = client_name.encode(self._encoding)
        client_version = client_version.encode(self._encoding)

        if len(password) > limits.NETWORK_PASSWORD_LENGTH:
            raise ValueError("Password too long")
        if len(client_name) > limits.NETWORK_CLIENT_NAME_LENGTH:
            raise ValueError("Client name too long")
        if len(client_version) > limits.NETWORK_REVISION_LENGTH:
            raise ValueError("Client revision too long")

        join_pkt = packet.PacketToTransmit(packet.AdminPacketType.ADMIN_JOIN)
        join_pkt.pack_bytes(password)
        join_pkt.pack_bytes(client_name)
        join_pkt.pack_bytes(client_version)

        response = yield from self._protocol.send_andor_wait_for(
            [
                join_pkt.finalize_packet()
            ],
            [
                packet.AdminPacketType.SERVER_PROTOCOL,
                packet.AdminPacketType.SERVER_FULL,
                packet.AdminPacketType.SERVER_BANNED,
                packet.AdminPacketType.SERVER_ERROR,
            ],
            buffer_unknown=True,
            timeout=10)

        if response.type_ != packet.AdminPacketType.SERVER_PROTOCOL:
            # FIXME: better error message
            yield from self._fatal_error(
                ConnectionError("Received negative response: {}".format(
                    response.type_)))

        version = response.unpack_uint8()
        if version != 1:
            self._fatal_error(ConnectionError(
                "Protocol version mismatch: server speaks {}".format(
                    version)))

        logger.debug("receiving update information...")
        has_more = response.unpack_bool()
        while has_more:
            try:
                type_ = UpdateType(response.unpack_uint16())
            except ValueError as err:
                logger.warn(err)
                # skip
                response.unpack_uint16()
            else:
                frequency = response.unpack_uint16()
                logger.debug("update: %s -- 0x%02x", type_, frequency)
                self._update_map[type_] = frequency
            has_more = response.unpack_bool()
        del response

        welcome = yield from self._protocol.send_andor_wait_for(
            [],
            [
                packet.AdminPacketType.SERVER_WELCOME
            ],
            timeout=1)

        if not self._server_info.read_from_welcome(welcome, self._encoding):
            logger.warn("some server information was not read successfully")
        logger.info("successfully authenticated")

    @asyncio.coroutine
    def disconnect(self):
        self._require_connected_or_authed()
        yield from self._protocol.close()
        self._reset()

    @property
    def server_info(self):
        return self._server_info
