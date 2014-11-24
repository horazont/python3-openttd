"""
.. _packet:

``openttd.packet`` -- Work with OpenTTD packets
###############################################

Support for working with OpenTTD packets is provided in this module. The OpenTTD
protocol uses binary packets of the following format::

                         1                   2
     0 1 2 3 4 5 6 7 8 9 0 1 2 3 4 5 6 7 8 9 0 1 2 3
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    | size                          | type          |
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+
    | payload ...
    +-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+-+

The *size* of each packet must not exceed :data:`SEND_MTU`. Valid values for
*type* depend on the packet stream type. For admin interface packets, the valid
values are enumerated in :class:`AdminPacketType`.

All multi-byte integer values are encoded in little-endian. Arrays of bytes are
encoded with NUL termination and without length indicator.

Classes to work with packets
============================

To unpack and pack data into packets, the following two classes are
provided. Both take an :class:`io.BytesIO` instance into which or from which
(respectively) they write/read the data.

.. autoclass:: Packer
   :members:

.. autoclass:: Unpacker
   :members:

These classes are extended by the following classes, which manage the size and
type of the packet, too:

.. autoclass:: ReceivedPacket(src, *, encoding=None)
   :members:

.. autoclass:: PacketToTransmit(type_, *, encoding=None)
   :members:

Values relevant for packets
===========================

.. autodata:: SEND_MTU

.. autoclass:: AdminPacketType
   :members:

"""
import io
import logging
import struct

from enum import Enum, IntEnum

#: Maximum packet size (from ``openttd:src/network/core/config.h``)
SEND_MTU = 1460

class AdminPacketType(Enum):
    """
    Valid types for packets in an admin protocol stream. Values are taken and
    auto-converted from the OpenTTD source (``src/network/core/tcp_admin.h``).
    """

    #: The admin announces and authenticates itself to the server.
    ADMIN_JOIN = 0
    #: The admin tells the server that it is quitting.
    ADMIN_QUIT = 1
    #: The admin tells the server the update frequency of a particular piece of information.
    ADMIN_UPDATE_FREQUENCY = 2
    #: The admin explicitly polls for a piece of information.
    ADMIN_POLL = 3
    #: The admin sends a chat message to be distributed.
    ADMIN_CHAT = 4
    #: The admin sends a remote console command.
    ADMIN_RCON = 5
    #: The admin sends a JSON string for the GameScript.
    ADMIN_GAMESCRIPT = 6
    #: The admin sends a ping to the server, expecting a ping-reply (PONG) packet.
    ADMIN_PING = 7
    #: The server tells the admin it cannot accept the admin.
    SERVER_FULL = 100
    #: The server tells the admin it is banned.
    SERVER_BANNED = 101
    #: The server tells the admin an error has occurred.
    SERVER_ERROR = 102
    #: The server tells the admin its protocol version.
    SERVER_PROTOCOL = 103
    #: The server welcomes the admin to a game.
    SERVER_WELCOME = 104
    #: The server tells the admin its going to start a new game.
    SERVER_NEWGAME = 105
    #: The server tells the admin its shutting down.
    SERVER_SHUTDOWN = 106
    #: The server tells the admin what the current game date is.
    SERVER_DATE = 107
    #: The server tells the admin that a client has joined.
    SERVER_CLIENT_JOIN = 108
    #: The server gives the admin information about a client.
    SERVER_CLIENT_INFO = 109
    #: The server gives the admin an information update on a client.
    SERVER_CLIENT_UPDATE = 110
    #: The server tells the admin that a client quit.
    SERVER_CLIENT_QUIT = 111
    #: The server tells the admin that a client caused an error.
    SERVER_CLIENT_ERROR = 112
    #: The server tells the admin that a new company has started.
    SERVER_COMPANY_NEW = 113
    #: The server gives the admin information about a company.
    SERVER_COMPANY_INFO = 114
    #: The server gives the admin an information update on a company.
    SERVER_COMPANY_UPDATE = 115
    #: The server tells the admin that a company was removed.
    SERVER_COMPANY_REMOVE = 116
    #: The server gives the admin some economy related company information.
    SERVER_COMPANY_ECONOMY = 117
    #: The server gives the admin some statistics about a company.
    SERVER_COMPANY_STATS = 118
    #: The server received a chat message and relays it.
    SERVER_CHAT = 119
    #: The server's reply to a remove console command.
    SERVER_RCON = 120
    #: The server gives the admin the data that got printed to its console.
    SERVER_CONSOLE = 121
    #: The server sends out the names of the DoCommands to the admins.
    SERVER_CMD_NAMES = 122
    #: The server gives the admin copies of incoming command packets.
    SERVER_CMD_LOGGING = 123
    #: The server gives the admin information from the GameScript in JSON.
    SERVER_GAMESCRIPT = 124
    #: The server indicates that the remote console command has completed.
    SERVER_RCON_END = 125
    #: The server replies to a ping request from the admin.
    SERVER_PONG = 126
    #: An invalid marker for admin packets.
    INVALID_ADMIN_PACKET = 255

class Packer:
    """
    Stepwise construction of a binary packet. The data is written into *dest*,
    which must be either an :class:`io.BytesIO`-compatible instance or
    :data:`None`. In the latter case, a new :class:`io.BytesIO` object is
    created.

    If *encoding* is set, :meth:`pack_string` can be used as a shorthand for
    ``packer.pack_bytes(value.encode(encoding))``.

    +--------------------+---------------+---------------------------------+-----------+
    |Method              |Value type     |Range                            |Notes      |
    +====================+===============+=================================+===========+
    |:meth:`pack_bool`   |any            |---                              |           |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_uint8`  |:class:`int`   |0 to 255                         |           |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_uint16` |:class:`int`   |0 to 65535                       |           |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_uint32` |:class:`int`   |0 to 2\ :sup:`32`--1             |           |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_uint64` |:class:`int`   |0 to 2\ :sup:`64`--1             |           |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_int8`   |:class:`int`   |-128 to 127                      |\(1)       |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_int16`  |:class:`int`   |-32768 to 32767                  |\(1)       |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_int32`  |:class:`int`   |-2\ :sup:`31` to 2\ :sup:`31`--1 |\(1)       |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_int64`  |:class:`int`   |-2\ :sup:`64` to 2\ :sup:`64`--1 |\(1)       |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_bytes`  |:class:`bytes` |---                              |\(2)       |
    +--------------------+---------------+---------------------------------+-----------+
    |:meth:`pack_string` |:class:`str`   |depends on *encoding*            |\(2), \(3) |
    +--------------------+---------------+---------------------------------+-----------+

    Notes:

    1. These functions are not provided in OpenTTD itself. OpenTTD uses raw
       casts to unsigned integers when transmitting signed integers.

    2. The length of any field expecting a string (an array of bytes, rather) is
       restricted. The individual length depends on the field, and is mainly
       documented inside the OpenTTD source.

       The byte sequence must not contain any ``\0`` byte.

    3. :meth:`pack_string` is only available if *encoding* is set. The
       restrictions of :meth:`pack_bytes` apply.

    See :class:`PacketToTransmit` for an example on the usage of
    :class:`Packer`.

    """

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
        """
        Pack a boolean value. The value is encoded as a uint8 (see
        :meth:`pack_uint8`). If the value is logically :data:`True` (see
        :func:`bool`), the value of the uint8 is 1, otherwise it is 0.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self.pack_uint8(1 if value else 0)

    def pack_uint8(self, value):
        """
        Pack an unsigned 8 bit integer *value*. If the value exceeds the range
        of an uint8, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_UINT8, value)

    def pack_uint16(self, value):
        """
        Pack an unsigned 16 bit integer *value*. If the value exceeds the range
        of an uint16, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_UINT16, value)

    def pack_uint32(self, value):
        """
        Pack an unsigned 32 bit integer *value*. If the value exceeds the range
        of an uint32, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_UINT32, value)

    def pack_uint64(self, value):
        """
        Pack an unsigned 64 bit integer *value*. If the value exceeds the range
        of an uint64, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_UINT64, value)

    def pack_int8(self, value):
        """
        Pack a signed 8 bit integer *value*. If the value exceeds the range
        of a int8, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_INT8, value)

    def pack_int16(self, value):
        """
        Pack a signed 16 bit integer *value*. If the value exceeds the range
        of a int16, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_INT16, value)

    def pack_int32(self, value):
        """
        Pack a signed 32 bit integer *value*. If the value exceeds the range
        of a int32, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_INT32, value)

    def pack_int64(self, value):
        """
        Pack a signed 64 bit integer *value*. If the value exceeds the range
        of a int64, a :class:`ValueError` is raised.

        Return the offset and the length of the encoded value in the resulting
        buffer.
        """
        return self._pack_struct(self.STRUCT_INT64, value)

    def pack_bytes(self, value):
        """
        Pack a sequence of bytes from *value*. *value* must not contain a NUL
        byte (``b"\0"``), otherwise :class:`ValueError` is raised.

        Return the offset and the length of the encoded value, including the
        terminating NUL byte.
        """
        offs = self.dest.seek(0, io.SEEK_CUR)
        if b"\0" in value:
            raise ValueError("Cannot pack bytes containing a NUL byte")
        self.dest.write(value)
        self.dest.write(b"\0")
        return offs, len(value)+1

    def pack_string(self, value, maxlen, *, encoding=None):
        """
        Encode and pack a string from *value*. As all strings in the OpenTTD
        protocol are restricted in length, *maxlen* must be specified against
        which the length of the *encoded* string is checked.

        If the encoded string exceeds *maxlen* or contains a NUL byte,
        :class:`ValueError` is raised.

        If *encoding* is not set (either by argument to this function or via the
        :attr:`encoding`), :class:`ValueError` is raised.

        Return the offset and the length of the encoded value, including the
        terminating NUL byte.
        """

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
        """
        The encoding as specified at construction time. This is used by
        :meth:`pack_string`.
        """
        return self._encoding


class Unpacker:
    """
    Similar to :class:`Packer`, :class:`Unpacker` provides services for dealing
    with binary OpenTTD packets. It provides step-by-step reading of the data
    in a binary buffer *src* (a :class:`io.BytesIO` instance).

    For unpacking of strings, *encoding* should be given.

    When reading beyond the EOF of the source, zeros and empty :class:`bytes`
    are returned, respectively.
    """

    def __init__(self, src, *, encoding=None):
        self._src = src
        self._encoding = encoding

    @property
    def encoding(self):
        """
        The encoding as specified at construction time. This is used by
        :meth:`unpack_string`.
        """
        return self._encoding

    def _unpack_struct(self, struct):
        buf = self._src.read(struct.size)
        if len(buf) < struct.size:
            # read beyond EOF, return 0 as per protocol
            return 0
        return struct.unpack(buf)[0]

    def unpack_bool(self):
        """
        Unpack a uint8 at the current offset (see :meth:`unpack_uint8`). If the
        value is nonzero, return :data:`True`. Otherwise, return :data:`False`.
        """
        return self._unpack_struct(Packer.STRUCT_UINT8) != 0

    def unpack_uint8(self):
        """
        Unpack a uint8 at the current offset. Advance the offset by one byte and
        return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_UINT8)

    def unpack_uint16(self):
        """
        Unpack a uint16 at the current offset. Advance the offset by two bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_UINT16)

    def unpack_uint32(self):
        """
        Unpack a uint32 at the current offset. Advance the offset by four bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_UINT32)

    def unpack_uint64(self):
        """
        Unpack a uint64 at the current offset. Advance the offset by eight bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_UINT64)

    def unpack_int8(self):
        """
        Unpack an int8 at the current offset. Advance the offset by one byte and
        return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_INT8)

    def unpack_int16(self):
        """
        Unpack an int16 at the current offset. Advance the offset by two bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_INT16)

    def unpack_int32(self):
        """
        Unpack an int32 at the current offset. Advance the offset by four bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_INT32)

    def unpack_int64(self):
        """
        Unpack an int64 at the current offset. Advance the offset by eight bytes
        and return the unpacked value.
        """
        return self._unpack_struct(Packer.STRUCT_INT64)

    def unpack_bytes(self):
        """
        Unpack bytes until a NUL byte is read or EOF is reached. Advance the
        offset accordingly and return the resulting :class:`bytes`.
        """
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
        """
        Call :meth:`unpack_bytes` and decode the :class:`bytes` using the given
        *encoding* (or :attr:`encoding`, if the argument is
        :data:`None`). Return the result.
        """
        encoding = encoding or self._encoding
        if encoding is None:
            raise ValueError("No encoding specified")
        return self.unpack_bytes().decode(encoding)

class ReceivedPacket(Unpacker):
    """
    Interpret the contents of the given :class:`io.BytesIO` *src* as OpenTTD
    packet. The *encoding* is forwarded to the inherited :class:`Unpacker`.

    .. attribute:: size

       Contents of the ``size`` field of the packet.

    .. attribute:: type_

       Contents of the ``type`` field of the packet, as
       :class:`AdminPacketType`.

    """

    def __init__(self, src, **kwargs):
        super().__init__(src, **kwargs)
        self.size = self.unpack_uint16()
        # FIXME: more flexibility with respect to packet type
        try:
            self.type_ = AdminPacketType(self.unpack_uint8())
        except ValueError:
            self.type_ = AdminPacketType.INVALID_ADMIN_PACKET

    @property
    def remaining_length(self):
        """
        The remaining length of the packet. This is the total size of the packet
        (see :attr:`size`) minus the current read offset.
        """
        return self.size - self._src.seek(0, io.SEEK_CUR)

    def __repr__(self):
        return "<ReceivedPacket type={} size={:d}>".format(
            self.type_,
            self.size)


class PacketToTransmit(Packer):
    """
    Construct a packet to send to OpenTTD. The *type_* must be an :class:`Enum`
    instance, which maps to a valid OpenTTD packet ``type``. The *encoding* is
    forwarded to the inherited :class:`Packer`.

    Upon construction, a new :class:`io.BytesIO` buffer is created, and space
    for the size and the type of the packet is reserved. It can be filled using
    the methods documented in :class:`Packer`.

    When the packet is to be sent, calling :meth:`finalize_packet` will return a
    :class:`bytes` instance, containing the whole packet including the correctly
    filled size and type fields.

    After calling :meth:`finalize_packet`, no data can be appended to the packet
    anymore.

    Example usage:

    .. code-block:: python3

       pkt = PacketToTransmit(AdminPacketType.ADMIN_JOIN)
       pkt.pack_string(client_password)
       pkt.pack_string(client_name)
       pkt.pack_string(client_version)

       pkt = PacketToTransmit(AdminPacketType.ADMIN_POLL)
       pkt.pack_uint8(openttd.admin.UpdateType.COMPANY_INFO)
       pkt.pack_uint32(company_id)

    """

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
        """
        Finalize the packet and return the :class:`bytes` object containing the
        whole packet.

        First, this method checks whether the packet is within the bounds set by
        :data:`SEND_MTU` (if not, a :class:`ValueError` is raised).

        Then, the size is written into the buffer and the whole buffer is
        returned as :class:`bytes`.

        .. warning::

           Attempting to append further data to a packet on which
           :meth:`finalize_packet` has been called will result in
           :class:`ValueError`.

        """
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
