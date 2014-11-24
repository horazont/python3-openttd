# File name: admin.py
# This file is part of: python3-openttd
#
# LICENSE
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 2 of the License.
#
# This program is distributed in the hope that it will be useful, but
# WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.
#
# FEEDBACK & QUESTIONS
#
# For feedback and questions about python3-openttd please e-mail one of
# the authors named in the AUTHORS file.
########################################################################

"""
``openttd.admin`` -- Administration interface client
####################################################

Client implementation
=====================

.. autoclass:: Client(*, loop=None, timeout=10)
   :members: connect, connect_tcp, authenticate, disconnect, disconnect_event,
             poll_client_info, poll_client_infos, poll_company_info,
             poll_company_infos, poll_company_economies, poll_company_stats,
             poll_date, rcon_command, server_info, subscribe_queue_to_push,
             subscribe_callback_to_push, unsubscribe_queue_from_push,
             unsubscribe_callback_from_push

Enumerations specific to the administration client
==================================================

.. autoclass:: UpdateType
   :members:

.. autoclass:: UpdateFrequency
   :members:

"""
import asyncio
import binascii
import logging

from enum import Enum, IntEnum
from datetime import timedelta, datetime

from . import limits, packet, info
from .protocol import PacketProtocol

logger = logging.getLogger(__name__)

class ClientState(Enum):
    """
    Internal state for the state machine of :class:`Client`.
    """
    CONNECTED = 0
    AUTHENTICATED = 1
    DISCONNECTED = 2

class UpdateType(Enum):
    """
    Types of updates to which the admin client can query or subscribe for (src:
    ``openttd:src/network/core/tcp_admin.h``).
    """

    #: Updates about the date of the game.
    DATE = 0
    #: Updates about the information of clients.
    CLIENT_INFO = 1
    #: Updates about the generic information of companies.
    COMPANY_INFO = 2
    #: Updates about the economy of companies.
    COMPANY_ECONOMY = 3
    #: Updates about the statistics of companies.
    COMPANY_STATS = 4
    #: The admin would like to have chat messages.
    CHAT = 5
    #: The admin would like to have console messages.
    CONSOLE = 6
    #: The admin would like a list of all DoCommand names.
    CMD_NAMES = 7
    #: The admin would like to have DoCommand information.
    CMD_LOGGING = 8
    #: The admin would like to have gamescript messages.
    GAMESCRIPT = 9

packet_to_update_type = {
    packet.AdminPacketType.SERVER_DATE: UpdateType.DATE,
    packet.AdminPacketType.SERVER_CLIENT_INFO: UpdateType.CLIENT_INFO,
    packet.AdminPacketType.SERVER_CLIENT_JOIN: UpdateType.CLIENT_INFO,
    packet.AdminPacketType.SERVER_CLIENT_UPDATE: UpdateType.CLIENT_INFO,
    packet.AdminPacketType.SERVER_CLIENT_QUIT: UpdateType.CLIENT_INFO,
    packet.AdminPacketType.SERVER_CLIENT_ERROR: UpdateType.CLIENT_INFO,
    packet.AdminPacketType.SERVER_COMPANY_INFO: UpdateType.COMPANY_INFO,
    packet.AdminPacketType.SERVER_COMPANY_UPDATE: UpdateType.COMPANY_INFO,
    packet.AdminPacketType.SERVER_COMPANY_ECONOMY: UpdateType.COMPANY_ECONOMY,
    packet.AdminPacketType.SERVER_COMPANY_STATS: UpdateType.COMPANY_STATS,
    packet.AdminPacketType.SERVER_CHAT: UpdateType.CHAT,
    packet.AdminPacketType.SERVER_CONSOLE: UpdateType.CONSOLE,
    packet.AdminPacketType.SERVER_CMD_NAMES: UpdateType.CMD_NAMES,
    packet.AdminPacketType.SERVER_CMD_LOGGING: UpdateType.CMD_LOGGING,
    packet.AdminPacketType.SERVER_GAMESCRIPT: UpdateType.GAMESCRIPT,
}

update_to_packet_types = {}
for packet_type, update_type in packet_to_update_type.items():
    update_to_packet_types.setdefault(update_type, set()).add(packet_type)

update_to_packet_type = {
    UpdateType.DATE: packet.AdminPacketType.SERVER_DATE,
    UpdateType.CLIENT_INFO: packet.AdminPacketType.SERVER_CLIENT_INFO,
    UpdateType.COMPANY_INFO: packet.AdminPacketType.SERVER_COMPANY_INFO,
    UpdateType.COMPANY_ECONOMY: packet.AdminPacketType.SERVER_COMPANY_ECONOMY,
    UpdateType.COMPANY_STATS: packet.AdminPacketType.SERVER_COMPANY_STATS,
    UpdateType.CHAT: packet.AdminPacketType.SERVER_CHAT,
    UpdateType.CONSOLE: packet.AdminPacketType.SERVER_CONSOLE,
    UpdateType.CMD_NAMES: packet.AdminPacketType.SERVER_CMD_NAMES,
    UpdateType.CMD_LOGGING: packet.AdminPacketType.SERVER_CMD_LOGGING,
    UpdateType.GAMESCRIPT: packet.AdminPacketType.SERVER_GAMESCRIPT,
}

class UpdateFrequency(IntEnum):
    """
    Frequency of updates (src: ``openttd:src/network/core/tcp_admin.h``). This
    is relevant for subscribing to updates. Unsubscription is only possible if
    :attr:`POLL` is supported (which is not the case for all update types).
    """

    #: The admin can poll this.
    POLL = 1
    #: The admin gets information about this on a daily basis.
    DAILY = 2
    #: The admin gets information about this on a weekly basis.
    WEEKLY = 4
    #: The admin gets information about this on a monthly basis.
    MONTHLY = 8
    #: The admin gets information about this on a quarterly basis.
    QUARTERLY = 16
    #: The admin gets information about this on a yearly basis.
    ANUALLY = 32
    #: The admin gets information about this when it changes.
    AUTOMATIC = 64

class Client:
    """
    Client implementation for interfacing with the administration network port.

    The implementation will use the :class:`asyncio.BaseEventLoop` *loop* if
    provided, otherwise the current event loop as returned by
    :func:`asyncio.get_event_loop`.

    The given *timeout* is used as the default timeout for any operation which
    does not specify another timeout internally.

    After construction, the client is in :attr:`~ClientState.DISCONNECTED`
    state. To connect, one must call :meth:`connect_tcp` or passing a fully
    initialized protocol to :meth:`connect`. The client is then in
    :attr:`~ClientState.CONNECTED` state.

    To be able to do anything meaningful (and not get disconnected within 10
    seconds), one has to :meth:`authenticate`. If authentication is successful,
    the client is now in the usable :attr:`~ClientState.AUTHENTICATED` state.

    If the client is in any other state than :attr:`~ClientState.AUTHENTICATED`,
    any operation besides authenticating or connecting, respectively, will fail
    by raising :class:`ConnectionError`. If not stated otherwise, all methods
    require the :attr:`~ClientState.AUTHENTICATED` state.

    Methods for requesting data from the remote server:

    +-------------------------------+------------------------------------------------------+------+
    |Method                         |Result type                                           |Notes |
    +===============================+======================================================+======+
    |:meth:`poll_client_info`       |:class:`~openttd.info.ClientInformation`              |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_client_infos`      |list of :class:`~openttd.info.ClientInformation`      |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_company_info`      |:class:`~openttd.info.CompanyInformation`             |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_company_infos`     |list of :class:`~openttd.info.CompanyInformation`     |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_company_economies` |list of :class:`~openttd.info.CompanyEconomy`         |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_company_stats`     |list of :class:`~openttd.info.CompanyStats`           |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`poll_date`              |:class:`int`                                          |\(1)  |
    +-------------------------------+------------------------------------------------------+------+
    |:meth:`rcon_command`           |list of tuples of :class:`bytes`, :class:`str`        |\(2)  |
    +-------------------------------+------------------------------------------------------+------+

    Notes:

    .. _poll-note:

    1. All ``poll_*``-commands share an issue. The client cannot distinguish
       between messages sent in response to poll request and periodically sent
       messages. To avoid similar issues with polls executed at the same time,
       only one poll for one message type can be carried out at one point in
       time. Locks are used to enforce this.

       It is thus recommended to not mix subscription and polling for one type
       of message.

    2. The second element of the tuples is the actual message content. The
       purpose of the first element is unknown to me.

    """

    def __init__(self, *, loop=None, timeout=10, **kwargs):
        super().__init__(**kwargs)
        self._push_receivers = {
            packet.AdminPacketType.SERVER_CHAT: self._recv_chat,
            packet.AdminPacketType.SERVER_DATE: self._recv_date,
            packet.AdminPacketType.SERVER_COMPANY_INFO: self._recv_company_info,
            packet.AdminPacketType.SERVER_COMPANY_UPDATE: self._recv_company_update,
            packet.AdminPacketType.SERVER_COMPANY_ECONOMY: self._recv_company_economy,
            packet.AdminPacketType.SERVER_COMPANY_STATS: self._recv_company_stats,
            packet.AdminPacketType.SERVER_CLIENT_INFO: self._recv_client_info,
            packet.AdminPacketType.SERVER_CLIENT_QUIT: self._recv_client_quit,
            packet.AdminPacketType.SERVER_CLIENT_UPDATE: self._recv_client_update,
            packet.AdminPacketType.SERVER_CLIENT_ERROR: self._recv_client_error,
            packet.AdminPacketType.SERVER_CLIENT_JOIN: self._recv_client_join,
        }

        self.on_error = None
        self._loop = loop or asyncio.get_event_loop()
        self._disconnected = asyncio.Event()
        self._default_timeout = timeout
        self._ping_task = None
        self._update_task = None
        self._update_task_interrupt = asyncio.Event()
        self._poll_locks = {}
        self._reset()

    @asyncio.coroutine
    def _fatal_error(self, exc):
        if not self._disconnected.is_set():
            raise exc
        logger.fatal("%s: %s", type(exc).__name__, exc)
        yield from self.disconnect(exc)
        if self.on_error:
            self._loop.call_soon(self.on_error, exc)
        raise exc

    def _fatal_error_as_async(self, exc):
        def handler(task):
            try:
                task.result()
            except:
                pass

        task = asyncio.async(self._fatal_error(exc))
        task.add_done_callback(handler)

    def _on_protocol_disconnect(self, exc):
        logger.debug("protocol disconnected: %r", exc)
        if not self._disconnected.is_set():
            logger.debug("forwarding disconnect")
            exc = exc or ConnectionError("Disconnected")
            self._fatal_error_as_async(exc)
        else:
            logger.debug("protocol disconnect ignored (already disconnected)")

    def _on_task_done(self, task):
        try:
            task.result()
        except asyncio.CancelledError:
            pass
        except Exception as err:
            logger.error("task %r unexpectedly exited: %s: %s",
                         task,
                         type(err).__name__,
                         err)
            self._fatal_error_as_async(err)

    def _packet_to_update_type(self, packet_type):
        try:
            return packet_to_update_type[packet_type]
        except KeyError:
            raise ValueError(
                "unsupported push packet type: {}".format(packet_type)
            ) from None

    def _expand_update_type_or_packet_type(self, packet_or_update_type):
        if isinstance(packet_or_update_type, UpdateType):
            packet_types = update_to_packet_types[packet_or_update_type]
            update_type = packet_or_update_type
        else:
            packet_types = [packet_or_update_type]
            update_type = packet_to_update_type[packet_or_update_type]
        return update_type, packet_types

    @asyncio.coroutine
    def _ping_task_impl(self, interval):
        ping_pkt = self._protocol.new_packet(packet.AdminPacketType.ADMIN_PING)
        offset, len_ = ping_pkt.pack_uint32(0) # placeholder
        end = offset+len_
        ctr = 0

        ping_buffer = ping_pkt.dest.getbuffer()

        logger.info("will ping in intervals of %s", interval)
        while True:
            yield from asyncio.sleep(interval.total_seconds())
            if self._state == ClientState.DISCONNECTED:
                return
            elif self._state == ClientState.CONNECTED:
                logger.warn("ping skipped, not authenticated")
                continue

            ctr = (ctr + 1) & 0xFFFFFFFF
            ping_buffer[offset:end] = ctr.to_bytes(len_, 'little')
            try:
                logger.debug("ping %d", ctr)
                response = yield from self._protocol.send_andor_wait_for(
                    [
                        ping_pkt
                    ],
                    [
                        packet.AdminPacketType.SERVER_PONG
                    ],
                    timeout=4,
                    critical_timeout=False)
                logger.debug("pong %d", response.unpack_uint32())
            except TimeoutError as err:
                logger.error("ping timeout!")
                yield from self._fatal_error(err)

    @asyncio.coroutine
    def _poll_update(self, update_type, d1=None, nresponses=1):
        poll_pkt = self._protocol.new_packet(packet.AdminPacketType.ADMIN_POLL)
        poll_pkt.pack_uint8(update_type.value)
        d1 = d1 or 0
        if d1 < 0:
            d1 = 0xFFFFFFFF
        poll_pkt.pack_uint32(d1)

        if nresponses not in {"*", "?", 1}:
            raise ValueError("Invalid value for nresponses: {!r}".format(
                nresponses))

        response_packet_type = update_to_packet_type[update_type]
        handler_func = self._push_receivers[response_packet_type]

        logger.debug("acquiring poll update lock for %r", response_packet_type)
        try:
            lock = self._poll_locks[response_packet_type]
        except KeyError:
            lock = self._poll_locks.setdefault(response_packet_type,
                                               asyncio.Lock())

        with (yield from lock):
            logger.debug("requesting poll update for %r", response_packet_type)
            if nresponses == 1:
                response = yield from self._send_andor_wait_for(
                    [
                        poll_pkt
                    ],
                    [
                        response_packet_type
                    ])

                return handler_func(response)

            values, _ = yield from self._send_and_collect_replies(
                [
                    poll_pkt
                ],
                [
                    response_packet_type
                ],
                initial_timeout=1)

        if nresponses == "?":
            values = list(values)
            if values:
                return handler_func(values[0])
            else:
                return None
        else:
            return map(handler_func, values)

    def _prepare_subscription(self, update_type, packet_types, frequency):
        dependencies, prev_frequency = self._update_dependencies.setdefault(
            update_type,
            (set(), frequency))
        if not dependencies:
            # subscribe
            self._set_update_frequency(update_type, frequency)
        elif prev_frequency != frequency:
            raise ValueError("New frequency conflicts with set frequency")
        dependencies.update(packet_types)

    def _recv_chat(self, pkt):
        chat_message = info.ChatMessage()
        chat_message.read_from_packet(pkt)
        return chat_message

    def _recv_client_error(self, pkt):
        return info.ClientError(pkt.unpack_uint32(), pkt.unpack_uint8())

    def _recv_client_info(self, pkt):
        client_info = info.ClientInformation()
        client_info.read_from_packet(pkt)
        return client_info

    def _recv_client_join(self, pkt):
        return info.ClientJoin(pkt.unpack_uint32())

    def _recv_client_quit(self, pkt):
        return info.ClientQuit(pkt.unpack_uint32())

    def _recv_client_update(self, pkt):
        return info.ClientUpdate(
            pkt.unpack_uint32(), pkt.unpack_string(), pkt.unpack_uint8()
        )

    def _recv_company_economy(self, pkt):
        company_economy = info.CompanyEconomy()
        company_economy.read_from_packet(pkt)
        return company_economy

    def _recv_company_info(self, pkt):
        company_info = info.CompanyInformation()
        company_info.read_from_packet(pkt)
        return company_info

    def _recv_company_update(self, pkt):
        new_share_owners = []
        update = info.CompanyUpdate(
            pkt.unpack_uint8(),
            pkt.unpack_string(),
            pkt.unpack_string(),
            pkt.unpack_uint8(),
            pkt.unpack_bool(),
            pkt.unpack_uint8(),
            new_share_owners,
        )
        for i in range(4):
            share_owner = pkt.unpack_uint8()
            if share_owner == 255:
                continue
            new_share_owners.append(share_owner)
        return update


    def _recv_company_stats(self, pkt):
        company_stats = info.CompanyStats()
        company_stats.read_from_packet(pkt)
        return company_stats

    def _recv_date(self, pkt):
        return pkt.unpack_uint32()

    def _require_disconnected(self):
        if self._state != ClientState.DISCONNECTED:
            logger.debug("invalid state: %r", self._state)
            raise ConnectionError("Already connected")

    def _require_connected_and_unauthed(self):
        if self._state != ClientState.CONNECTED:
            logger.debug("invalid state: %r", self._state)
            raise ConnectionError("Incorrect state")

    def _require_connected_or_authed(self):
        if self._state == ClientState.DISCONNECTED:
            logger.debug("invalid state: %r", self._state)
            raise ConnectionError("Not connected")

    def _require_authed(self):
        if self._state != ClientState.AUTHENTICATED:
            logger.debug("invalid state: %r", self._state)
            raise ConnectionError("Not authenticated or not connected")

    def _reset(self):
        logger.debug("resetting")
        self._protocol = None
        self._state = ClientState.DISCONNECTED
        self._update_map = {}
        self._server_info = info.ServerInformation()
        self._disconnected.set()
        self._task_teardown(self._ping_task)
        self._task_teardown(self._update_task)
        self._ping_task = None
        self._update_task = None
        self._push_callbacks = {}
        self._update_dependencies = {}
        self._update_task_interrupt.clear()
        self._rcon_lock = asyncio.Lock()

    @asyncio.coroutine
    def _send_and_collect_replies(self,
                                  packets_to_send,
                                  types_to_listen_for,
                                  end_of_transmission_marker=[],
                                  initial_timeout=None,
                                  subsequent_timeout=None):
        queue = asyncio.Queue()
        queues_to_register = {
            type_: queue
            for type_ in types_to_listen_for
        }

        response = yield from self._send_and_wait_for_replies(
            packets_to_send,
            queues_to_register,
            end_of_transmission_marker=end_of_transmission_marker,
            initial_timeout=initial_timeout,
            subsequent_timeout=subsequent_timeout)

        def result_generator():
            while not queue.empty():
                yield queue.get_nowait()

        return result_generator(), response

    @asyncio.coroutine
    def _send_and_wait_for_replies(self,
                                   packets_to_send,
                                   queues_to_register,
                                   end_of_transmission_marker=[],
                                   initial_timeout=None,
                                   subsequent_timeout=None):
        try:
            initial_timeout = initial_timeout or self._default_timeout
            subsequent_timeout = subsequent_timeout or 0.1
            return (yield from self._protocol.send_and_collect_replies(
                packets_to_send,
                queues_to_register,
                end_of_transmission_marker,
                initial_timeout=initial_timeout,
                subsequent_timeout=subsequent_timeout))
        except TimeoutError as err:
            return None

    @asyncio.coroutine
    def _send_andor_wait_for(self, *args, timeout=None, **kwargs):
        """
        Forwards the request to the protocol, but (a) overrides the timeout if
        unset and (b) handles the TimeoutError by triggering a call to
        :meth:`_fatal_error`.
        """
        try:
            timeout = timeout or self._default_timeout
            return (yield from self._protocol.send_andor_wait_for(
                *args,
                timeout=timeout,
                critical_timeout=False,
                **kwargs))
        except TimeoutError as err:
            yield from self._fatal_error(err)

    def _set_update_frequency(self, update_type, frequency):
        self._require_authed()
        try:
            allowed_frequencies = self._update_map[update_type]
        except KeyError:
            raise ValueError(
                "Update not supported by server: {}".format(update_type)
            ) from None

        if not (frequency & allowed_frequencies):
            raise ValueError("Frequency {} not allowed for update {}".format(
                frequency, update_frequency))

        set_pkt = self._protocol.new_packet(
            packet.AdminPacketType.ADMIN_UPDATE_FREQUENCY)
        set_pkt.pack_uint16(update_type.value)
        set_pkt.pack_uint16(frequency)

        self._protocol.send_packet(set_pkt)

    def _task_setup(self, task):
        task = asyncio.async(
            task,
            loop=self._loop)
        task.add_done_callback(self._on_task_done)
        return task

    @asyncio.coroutine
    def _task_teardown(self, task):
        try:
            if task.cancel():
                # wait for it to cancel
                yield from task
                task.result()
            task.result()
        except asyncio.CancelledError:
            pass

    @asyncio.coroutine
    def _update_task_impl(self):
        logger = logging.getLogger(__name__ + ".update_task_impl")
        logger.debug("listening for push messages")
        futures = {}
        interrupt_future = asyncio.async(
            self._update_task_interrupt.wait(),
            loop=self._loop)
        try:
            while True:
                for future in futures:
                    future.cancel()
                futures = {
                    asyncio.async(queue.get(), loop=self._loop): (
                        self._push_receivers[packet_type], cbs)
                    for packet_type, (queue, cbs) in self._push_callbacks.items()
                }

                logger.debug("futures=%r", futures)
                done, pending = yield from asyncio.wait(
                    list(futures) + [interrupt_future],
                    loop=self._loop,
                    return_when=asyncio.FIRST_COMPLETED)

                if interrupt_future in done:
                    done.remove(interrupt_future)
                    self._update_task_interrupt.clear()
                    interrupt_future = asyncio.async(
                        self._update_task_interrupt.wait(),
                        loop=self._loop)

                for future in done:
                    converter, cbs = futures[future]
                    value = converter(future.result())
                    for cb in cbs:
                        self._loop.call_soon(cb, value)
                    del futures[future]
        finally:
            interrupt_future.cancel()
            for future in futures:
                future.cancel()
                try:
                    future.result()
                except asyncio.CancelledError:
                    pass

    @asyncio.coroutine
    def authenticate(self, password, client_name, client_version):
        """
        Authenticate with the server by sending a
        :attr:`~openttd.packet.AdminPacketType.ADMIN_JOIN` message with the
        provided arguments. The arguments are subject to the limits set in
        :mod:`openttd.limits`. If any of the arguments fails to encode or
        exceeds the limits, :class:`ValueError` is raised.

        If the server rejects the connection, :class:`ConnectionError` is
        raised.

        Requires the client to be in :attr:`~ClientState.CONNECTED` state. If
        the coroutine completes successfully, the client then is in
        :attr:`~ClientState.AUTHENTICATED` state.
        """

        self._require_connected_and_unauthed()
        join_pkt = self._protocol.new_packet(packet.AdminPacketType.ADMIN_JOIN)
        join_pkt.pack_string(password, limits.NETWORK_PASSWORD_LENGTH)
        join_pkt.pack_string(client_name, limits.NETWORK_CLIENT_NAME_LENGTH)
        join_pkt.pack_string(client_version, limits.NETWORK_REVISION_LENGTH)

        try:
            response = yield from self._protocol.send_andor_wait_for(
                [
                    join_pkt
                ],
                [
                    packet.AdminPacketType.SERVER_PROTOCOL,
                    packet.AdminPacketType.SERVER_FULL,
                    packet.AdminPacketType.SERVER_BANNED,
                    packet.AdminPacketType.SERVER_ERROR,
                ],
                buffer_unknown=True,
                timeout=10)
        except ConnectionError:
            raise ConnectionError(
                "Disconnected (most likely authentication failure)"
            ) from None

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

        if not self._server_info.read_from_packet(welcome):
            logger.warn("some server information was not read successfully")
        self._state = ClientState.AUTHENTICATED
        logger.info("successfully authenticated")

        self._ping_task = self._task_setup(
            self._ping_task_impl(interval=timedelta(seconds=20))
        )
        self._update_task = self._task_setup(
            self._update_task_impl()
        )

    @asyncio.coroutine
    def connect(self, protocol):
        """
        Connect the client using the given
        :class:`openttd.protocol.PacketProtocol` instance.

        Requires the client to be in :class:`~ClientState.DISCONNECTED` state.
        """
        self._require_disconnected()
        self._protocol = protocol
        self._protocol.on_disconnect = self._on_protocol_disconnect
        logger.debug("connected")
        self._state = ClientState.CONNECTED
        self._disconnected.clear()

    @asyncio.coroutine
    def connect_tcp(self, host, port=3977, *, encoding="utf8"):
        """
        Automatically connect to the given *host* at the given *port* using
        TCP. The protocol is set to use the given *encoding*.

        Requires the client to be in :class:`~ClientState.DISCONNECTED` state.
        """
        self._require_disconnected()
        _, protocol = yield from self._loop.create_connection(
            lambda: PacketProtocol(loop=self._loop,
                                   encoding=encoding),
            host=host,
            port=port)

        yield from self.connect(protocol, **kwargs)

    @asyncio.coroutine
    def disconnect(self, exc=None):
        """
        Disconnect from the server, optionally with an exception *exc*.
        """
        self._require_connected_or_authed()
        self._disconnected.set()
        yield from self._protocol.close(exc)
        self._reset()

    @property
    def disconnected_event(self):
        """
        An :class:`asyncio.Event` instance which is set as long as the client is
        disconnected.
        """
        return self._disconnected

    @asyncio.coroutine
    def poll_client_info(self, client_id):
        """
        Request :class:`~openttd.info.ClientInformation` for a specific
        *client_id*. Return :data:`None` if the client does not exist.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        if client_id < 0 or client_id is None:
            raise ValueError("poll_client_info requires one specific id")
        return (yield from self._poll_update(
            UpdateType.CLIENT_INFO,
            d1=client_id,
            nresponses="?"))

    @asyncio.coroutine
    def poll_client_infos(self):
        """
        Request :class:`~openttd.info.ClientInformation` for all connected
        clients.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        return (yield from self._poll_update(
            UpdateType.CLIENT_INFO,
            d1=-1,
            nresponses="*"))

    @asyncio.coroutine
    def poll_company_info(self, company_id):
        """
        Request :class:`~openttd.info.CompanyInformation` for a specific
        *company_id*. Return :data:`None` if the company does not exist.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        if company_id < 0 or company_id is None:
            raise ValueError("poll_company_info requires one specific id")
        return (yield from self._poll_update(
            UpdateType.COMPANY_INFO,
            d1=company_id,
            nresponses="?"))

    @asyncio.coroutine
    def poll_company_infos(self):
        """
        Request :class:`~openttd.info.CompanyInformation` for all existing
        companies.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        return (yield from self._poll_update(
            UpdateType.COMPANY_INFO,
            d1=-1,
            nresponses="*"))

    @asyncio.coroutine
    def poll_company_economies(self):
        """
        Request :class:`~openttd.info.CompanyEconomy` for all existing
        companies.

        .. note::

           The protocol does not support querying economy information for a
           specific company.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        return (yield from self._poll_update(
            UpdateType.COMPANY_ECONOMY,
            d1=-1,
            nresponses="*"))

    @asyncio.coroutine
    def poll_company_stats(self):
        """
        Request :class:`~openttd.info.CompanyStats` for all existing
        companies.

        .. note::

           The protocol does not support querying statistics information for a
           specific company.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        return (yield from self._poll_update(
            UpdateType.COMPANY_STATS,
            d1=-1,
            nresponses="*"))

    @asyncio.coroutine
    def poll_date(self):
        """
        Request the current in-game date. Return an integer.

        .. note::

           See :ref:`the note on polling functions <poll-note>` for interference
           issues with subscription based information retrieval.

        """
        self._require_authed()
        return (yield from self._poll_update(
            UpdateType.DATE,
            nresponses=1))

    @asyncio.coroutine
    def rcon_command(self, command):
        """
        Execute the OpenTTD console *command* remotely. Return an iterable which
        yields tuples.

        Each tuple consists of a :class:`bytes` and a :class:`str`. The string
        is the actual console message. The iterable may be empty if the command
        did not produce any output.
        """

        self._require_authed()
        rcon_pkt = self._protocol.new_packet(packet.AdminPacketType.ADMIN_RCON)
        rcon_pkt.pack_string(command, limits.NETWORK_RCONCOMMAND_LENGTH)

        logger.debug("locking rcon lock")
        with (yield from self._rcon_lock):
            logger.debug("sending rcon: %r", command)
            results, _ = (yield from self._send_and_collect_replies(
                [
                    rcon_pkt
                ],
                [
                    packet.AdminPacketType.SERVER_RCON,
                ],
                [
                    packet.AdminPacketType.SERVER_RCON_END
                ]))

        def result_generator(results):
            for pkt in results:
                yield (pkt.unpack_bytes(), pkt.unpack_string())

        return result_generator(results)

    @property
    def server_info(self):
        """
        Return the :class:`~openttd.info.ServerInformation` provided by the
        server after authentication.
        """
        return self._server_info

    def subscribe_queue_to_push(self,
                                update_type,
                                message_queue,
                                frequency=UpdateFrequency.AUTOMATIC):
        """
        Subscribe a :class:`asyncio.Queue` message_queue to an *update_type*. If
        the update is not subscribed yet, it will be subscribed with the given
        *frequency*. If it is already subscribed and the subscription frequency
        differs from the given *frequency*, a :class:`ValueError` is raised.

        *update_type* can either be a :class:`UpdateType`, in which case all
        packet types associated with that packet type are subscribed. The
        alternative is to subscribe to a specific packet type
        :class:`~openttd.packet.AdminPacketType`. Only packet types which relate
        to an :class:`UpdateType` can be subscribed this way.

        If a matching packet is received, it is converted into the corresponding
        :mod:`openttd.info` object and pushed to the queue.
        """

        update_type, packet_types = self._expand_update_type_or_packet_type(
            update_type)

        self._prepare_subscription(update_type, packet_types,
                                   frequency=frequency)

        for packet_type in packet_types:
            logger.debug("adding callback subscription for %r/%r",
                         update_type, packet_type)
            self._protocol.packet_hooks.add_queue(
                packet_type,
                message_queue)

    def subscribe_callback_to_push(self,
                                   update_type,
                                   callback,
                                   frequency=UpdateFrequency.AUTOMATIC):
        """
        The arguments *update_type* and *frequency* have the same meaning as for
        :meth:`subscribe_callback_to_push`.

        If a matching packet is received, it is converted into the corresponding
        :mod:`openttd.info` object and the *callback* is called with the result
        as its only argument.
        """

        update_type, packet_types = self._expand_update_type_or_packet_type(
            update_type)

        self._prepare_subscription(update_type, packet_types,
                                   frequency=frequency)

        for packet_type in packet_types:
            logger.debug("adding callback subscription for %r/%r",
                         update_type, packet_type)
            try:
                # avoiding extra-construction of asyncio.Queue
                queue, cbs = self._push_callbacks[packet_type]
            except KeyError:
                queue, cbs = self._push_callbacks.setdefault(
                    packet_type,
                    (asyncio.Queue(), set()))
                self._protocol.packet_hooks.add_queue(packet_type, queue)
                self._update_task_interrupt.set()

            cbs.add(callback)

    def unsubscribe_queue_from_push(self, packet_type, queue):
        """
        Unsubscribe a *queue* from the given
        :class:`~openttd.packet.AdminPacketType` or :class:`UpdateType`.
        """

        update_type, packet_types = self._expand_update_type_or_packet_type(
            update_type)

        for packet_type in packet_types:
            try:
                self._protocol.packet_hooks.remove_queue(packet_type, queue)
            except KeyError:
                pass

    def unsubscribe_callback_from_push(self, packet_type, callback):
        """
        Unsubscribe a *callback* from the given
        :class:`~openttd.packet.AdminPacketType` or :class:`UpdateType`.
        """

        update_type, packet_types = self._expand_update_type_or_packet_type(
            update_type)

        for packet_type in packet_types:
            try:
                # avoiding extra-construction of asyncio.Queue
                queue, cbs = self._push_callbacks[packet_type]
            except KeyError:
                pass
            else:
                cbs.remove(callback)
                if not cbs:
                    self._protocol.packet_hooks.remove_queue(packet_type, queue)
                    del self._push_callbacks[packet_type]
