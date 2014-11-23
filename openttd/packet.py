import io
import logging
import struct

try:
    from enum import Enum, IntEnum
except ImportError as err:
    logging.getLogger("init").warn("Cannot use Enum: %s", err)
    Enum = object
    IntEnum = object

SEND_MTU = 1460

class AdminPacketType(Enum):
    # The admin announces and authenticates itself to the server.
    ADMIN_JOIN = 0
    # The admin tells the server that it is quitting.
    ADMIN_QUIT = 1
    # The admin tells the server the update frequency of a particular piece of information.
    ADMIN_UPDATE_FREQUENCY = 2
    # The admin explicitly polls for a piece of information.
    ADMIN_POLL = 3
    # The admin sends a chat message to be distributed.
    ADMIN_CHAT = 4
    # The admin sends a remote console command.
    ADMIN_RCON = 5
    # The admin sends a JSON string for the GameScript.
    ADMIN_GAMESCRIPT = 6
    # The admin sends a ping to the server, expecting a ping-reply (PONG) packet.
    ADMIN_PING = 7
    # The server tells the admin it cannot accept the admin.
    SERVER_FULL = 100
    # The server tells the admin it is banned.
    SERVER_BANNED = 101
    # The server tells the admin an error has occurred.
    SERVER_ERROR = 102
    # The server tells the admin its protocol version.
    SERVER_PROTOCOL = 103
    # The server welcomes the admin to a game.
    SERVER_WELCOME = 104
    # The server tells the admin its going to start a new game.
    SERVER_NEWGAME = 105
    # The server tells the admin its shutting down.
    SERVER_SHUTDOWN = 106
    # The server tells the admin what the current game date is.
    SERVER_DATE = 107
    # The server tells the admin that a client has joined.
    SERVER_CLIENT_JOIN = 108
    # The server gives the admin information about a client.
    SERVER_CLIENT_INFO = 109
    # The server gives the admin an information update on a client.
    SERVER_CLIENT_UPDATE = 110
    # The server tells the admin that a client quit.
    SERVER_CLIENT_QUIT = 111
    # The server tells the admin that a client caused an error.
    SERVER_CLIENT_ERROR = 112
    # The server tells the admin that a new company has started.
    SERVER_COMPANY_NEW = 113
    # The server gives the admin information about a company.
    SERVER_COMPANY_INFO = 114
    # The server gives the admin an information update on a company.
    SERVER_COMPANY_UPDATE = 115
    # The server tells the admin that a company was removed.
    SERVER_COMPANY_REMOVE = 116
    # The server gives the admin some economy related company information.
    SERVER_COMPANY_ECONOMY = 117
    # The server gives the admin some statistics about a company.
    SERVER_COMPANY_STATS = 118
    # The server received a chat message and relays it.
    SERVER_CHAT = 119
    # The server's reply to a remove console command.
    SERVER_RCON = 120
    # The server gives the admin the data that got printed to its console.
    SERVER_CONSOLE = 121
    # The server sends out the names of the DoCommands to the admins.
    SERVER_CMD_NAMES = 122
    # The server gives the admin copies of incoming command packets.
    SERVER_CMD_LOGGING = 123
    # The server gives the admin information from the GameScript in JSON.
    SERVER_GAMESCRIPT = 124
    # The server indicates that the remote console command has completed.
    SERVER_RCON_END = 125
    # The server replies to a ping request from the admin.
    SERVER_PONG = 126
    # An invalid marker for admin packets.
    INVALID_ADMIN_PACKET = 255

class Packer:
    STRUCT_UINT8 = struct.Struct("<B")
    STRUCT_UINT16 = struct.Struct("<H")
    STRUCT_UINT32 = struct.Struct("<L")
    STRUCT_UINT64 = struct.Struct("<Q")
    STRUCT_INT8 = struct.Struct("<b")
    STRUCT_INT16 = struct.Struct("<h")
    STRUCT_INT32 = struct.Struct("<l")
    STRUCT_INT64 = struct.Struct("<q")

    def __init__(self, dest=None, *, encoding=None):
        self.dest = dest or io.BytesIO()
        self._encoding = encoding

    def _pack_struct(self, struct, *data):
        buf = struct.pack(*data)
        offs = self.dest.seek(0, io.SEEK_CUR)
        self.dest.write(buf)
        return offs, len(buf)

    def pack_bool(self, value):
        return self.pack_uint8(1 if value else 0)

    def pack_uint8(self, value):
        return self._pack_struct(self.STRUCT_UINT8, value)

    def pack_uint16(self, value):
        return self._pack_struct(self.STRUCT_UINT16, value)

    def pack_uint32(self, value):
        return self._pack_struct(self.STRUCT_UINT32, value)

    def pack_uint64(self, value):
        return self._pack_struct(self.STRUCT_UINT64, value)

    def pack_int8(self, value):
        return self._pack_struct(self.STRUCT_INT8, value)

    def pack_int16(self, value):
        return self._pack_struct(self.STRUCT_INT16, value)

    def pack_int32(self, value):
        return self._pack_struct(self.STRUCT_INT32, value)

    def pack_int64(self, value):
        return self._pack_struct(self.STRUCT_INT64, value)

    def pack_bytes(self, value):
        offs = self.dest.seek(0, io.SEEK_CUR)
        if b"\0" in value:
            raise ValueError("Cannot pack bytes containing a NUL byte")
        self.dest.write(value)
        self.dest.write(b"\0")
        return offs, len(value)+1

    def pack_string(self, value, maxlen, *, encoding=None):
        encoding = encoding or self._encoding
        if encoding is None:
            raise ValueError("No encoding specified")
        value_encoded = value.encode(encoding)
        if len(value_encoded) > maxlen:
            raise ValueError(
                "String value too long ({} out of {} bytes)".format(
                    len(value_encoded),
                    maxlen))
        return self.pack_bytes(value_encoded)

    @property
    def encoding(self):
        return self._encoding


class Unpacker:
    def __init__(self, src, *, encoding=None):
        self._src = src
        self._encoding = encoding

    @property
    def encoding(self):
        return self._encoding

    def _unpack_struct(self, struct):
        buf = self._src.read(struct.size)
        if len(buf) < struct.size:
            # read beyond EOF, return 0 as per protocol
            return 0
        return struct.unpack(buf)[0]

    def unpack_bool(self):
        return self._unpack_struct(Packer.STRUCT_UINT8) != 0

    def unpack_uint8(self):
        return self._unpack_struct(Packer.STRUCT_UINT8)

    def unpack_uint16(self):
        return self._unpack_struct(Packer.STRUCT_UINT16)

    def unpack_uint32(self):
        return self._unpack_struct(Packer.STRUCT_UINT32)

    def unpack_uint64(self):
        return self._unpack_struct(Packer.STRUCT_UINT64)

    def unpack_int8(self):
        return self._unpack_struct(Packer.STRUCT_INT8)

    def unpack_int16(self):
        return self._unpack_struct(Packer.STRUCT_INT16)

    def unpack_int32(self):
        return self._unpack_struct(Packer.STRUCT_INT32)

    def unpack_int64(self):
        return self._unpack_struct(Packer.STRUCT_INT64)

    def unpack_bytes(self):
        byte_list = []
        while True:
            b = self._src.read(1)
            if not b:
                return b""
            if b != b"\0":
                byte_list.append(b)
            else:
                break

        return b"".join(byte_list)

    def unpack_string(self, encoding=None):
        encoding = encoding or self._encoding
        if encoding is None:
            raise ValueError("No encoding specified")
        return self.unpack_bytes().decode(encoding)

class ReceivedPacket(Unpacker):
    def __init__(self, src, **kwargs):
        super().__init__(src, **kwargs)
        self.size = self.unpack_uint16()
        try:
            self.type_ = AdminPacketType(self.unpack_uint8())
        except ValueError:
            self.type_ = AdminPacketType.INVALID_ADMIN_PACKET

    @property
    def remaining_length(self):
        return self.size - self._src.seek(0, io.SEEK_CUR)

    def __repr__(self):
        return "<ReceivedPacket type={} size={:d}>".format(
            self.type_,
            self.size)


class PacketToTransmit(Packer):
    def __init__(self, type_, **kwargs):
        self._finalized = False
        super().__init__(**kwargs)
        self.pack_uint16(0)  # placeholder for size
        self.pack_uint8(type_.value)

    def _require_not_finalized(self):
        if self._finalized:
            raise ValueError("Packet is already finalized")

    def _pack_struct(self, struct, value):
        self._require_not_finalized()
        return super()._pack_struct(struct, value)

    def pack_bytes(self, value):
        self._require_not_finalized()
        return super().pack_bytes(value)

    def finalize_packet(self):
        self._finalized = True
        byte_count = len(self.dest.getbuffer())
        if byte_count > SEND_MTU:
            raise ValueError("Packet too large ({} out of {} bytes)".format(
                self._written,
                SEND_MTU))

        self.dest.getbuffer()[0:2] = Packer.STRUCT_UINT16.pack(
            len(self.dest.getbuffer()))
        return self.dest.getvalue()

    def __repr__(self):
        return "<PacketToTransmit type={} current_size={:d}>".format(
            AdminPacketType(
                Packer.STRUCT_UINT8.unpack(self.dest.getbuffer()[2:3])[0]),
            len(self.dest.getbuffer()))
