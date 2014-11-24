import asyncio
import io
import logging
import struct

from . import packet, packet_hooks

logger = logging.getLogger(__name__)

class OpenTTDPacketProtocol(asyncio.Protocol):
    STRUCT_PACKETSIZE = packet.Packer.STRUCT_UINT16

    def __init__(self, encoding=None, loop=None):
        super().__init__()
        self._loop = loop or asyncio.get_event_loop()
        self.packet_hooks = packet_hooks.PacketHooks()
        self.on_disconnect = None
        self._encoding = encoding
        self._closed = asyncio.Event(loop=loop)
        self._closed.set()
        self._reset()

    def _close_transport(self):
        logger.debug("closing underlying transport")
        self._transport.close()

    def _finalize_incomplete_buffer(self):
        self._incomplete_buffer.seek(0)
        final_packet = packet.ReceivedPacket(self._incomplete_buffer,
                                             encoding=self._encoding)
        self._incomplete_buffer = None
        self._incomplete_size = None

        logger.debug("rx packet: %r", final_packet)
        self._packet_received(final_packet)

    def _packet_received(self, packet):
        try:
            self.packet_hooks.unicast(packet.type_, packet)
        except KeyError as err:
            if self._buffer_unknown:
                logger.info("buffering unhandled packet: %r", packet)
                self._unknown_buffer.append(packet)
            else:
                logger.warn("unhandled packet: %r", packet)

    def _protocol_violation(self, msg):
        self._connection_error("Protocol violation: {}".format(msg))

    @asyncio.coroutine
    def _collector_task(self, eot_futures, data_futures,
                        initial_timeout,
                        subsequent_timeout,
                        response_required):
        timeout = initial_timeout
        data_future_set = set(data_futures)
        eot_future_set = set(eot_futures)
        has_response = False

        try:
            while True:
                future_list = list(eot_futures) + list(data_futures)
                logger.debug("collector_task: timeout=%f", timeout)
                done, pending = yield from asyncio.wait(
                    future_list,
                    timeout=timeout,
                    return_when=asyncio.FIRST_COMPLETED,
                    loop=self._loop)

                if done & data_future_set:
                    timeout = subsequent_timeout
                    has_response = True
                    for future in done:
                        future.result()
                    data_future_set -= done
                    eot_future_set -= done
                    continue

                if done & eot_future_set:
                    for future in done:
                        future.result()
                    eot_future_set -= done
                    break

                if response_required and not has_response:
                    raise TimeoutError("Timeout")
                break
        finally:
            for future in (data_future_set | eot_future_set):
                future.cancel()
                type_ = eot_futures.get(future, data_futures[future])
                logger.debug("collector_task: removing future for %r",
                             type_)
                try:
                    self.packet_hooks.remove_future(type_, future)
                except KeyError:
                    pass

    def _connection_error(self, msg):
        logger.error("protocol error: %s", msg)
        exc = ConnectionError(msg)
        try:
            self._terminate(exc)
        finally:
            raise exc

    def _recv_into_incomplete(self, data):
        if not self._incomplete_buffer:
            logger.debug("nothing to receive into")
            return data

        to_write = self._incomplete_size - self._incomplete_buffer.seek(
            0,
            io.SEEK_CUR)
        logger.debug("to_write=%d, len(data)=%d",
                     to_write,
                     len(data))

        assert to_write >= 0

        self._incomplete_buffer.write(data[:to_write])
        if len(self._incomplete_buffer.getbuffer()) == self._incomplete_size:
            self._finalize_incomplete_buffer()

        return data[to_write:]

    def _reinspect_buffered_packets(self):
        if self._unknown_buffer:
            saved_buffer_unknown = self._buffer_unknown
            try:
                self._buffer_unknown = True
                # re-inspect all buffered packets
                buffered_packets = self._unknown_buffer
                self._unknown_buffer = []
                for buffered_packet in buffered_packets:
                    self._packet_received(buffered_packet)
            finally:
                self._buffer_unknown = saved_buffer_unknown

    def _reset(self):
        self._header_buffer = b""
        self._incomplete_buffer = None
        self._incomplete_size = None
        self._transport = None
        self._buffer_unknown = False
        self._unknown_buffer = []

    def _terminate(self, exc):
        logger.debug("terminating with error: %r", exc)
        self.packet_hooks.close_all(exc)
        self._close_transport()

    @asyncio.coroutine
    def _waiter_task(self, futures, timeout, critical_timeout):
        logger = logging.getLogger(__name__ + ".send_andor_wait_for")
        logger.debug("waiting for response...")

        if futures:
            done, pending = yield from asyncio.wait(
                [f for _, f in futures],
                timeout=timeout,
                return_when=asyncio.FIRST_COMPLETED)
        else:
            done = set()
            pending = set()
            yield from asyncio.sleep(timeout)

        logger.debug("received response")
        logger.debug("done=%r", done)
        logger.debug("pending=%r", pending)

        for type_, future in futures:
            # skip futures which are done
            if future not in pending:
                continue

            future.cancel()
            try:
                self.packet_hooks.remove_future(type_, future)
            except KeyError:
                # defensive guard against a maybe race condition
                # (I guess that in some cases, asyncio.wait may catch only
                # one future, but more than one has been fulfilled)
                pass

        if not done:
            logger.debug("timed out")
            if critical_timeout:
                self._connection_error("Critical timeout")
                raise ConnectionError("Disconnected")
            raise TimeoutError("Timeout")

        try:
            return done.pop().result()
        finally:
            for other_done in done:
                try:
                    other_done.result()
                except:
                    pass

    # shared implementation

    def connection_made(self, transport):
        self._transport = transport
        self._closed.clear()
        super().connection_made(transport)

    def connection_lost(self, exc):
        logger.debug("connection lost: %r", exc)
        if exc is not None:
            self._terminate(exc)
        else:
            self._terminate(ConnectionError("Disconnected"))
        super().connection_lost(exc)
        self._close_transport()
        self._closed.set()
        self._reset()
        if self.on_disconnect is not None:
            logger.debug("forwarding disconnect event")
            self._loop.call_soon(self.on_disconnect, exc)

    def pause_writing(self):
        pass

    def resume_writing(self):
        pass

    # asyncio.Protocol implementation

    def data_received(self, data):
        logger.debug("received %d bytes", len(data))
        while data:
            data = self._recv_into_incomplete(data)
            if not data:
                break
            logger.debug("%d bytes remaining after consumption into buffer",
                         len(data))

            to_write = 3 - len(self._header_buffer)
            assert to_write > 0
            logger.debug("to_write = %d", to_write)

            self._header_buffer += data[:to_write]
            data = data[to_write:]

            if len(self._header_buffer) < 3:
                logger.debug("header for next packet still incomplete (%d)",
                             len(self._header_buffer))
                assert not data
                break

            self._incomplete_size = self.STRUCT_PACKETSIZE.unpack(
                self._header_buffer[0:2])[0]

            logger.debug("header received: size=%d, type=%d",
                         self._incomplete_size,
                         self._header_buffer[2])

            if self._incomplete_size > packet.SEND_MTU:
                # this raises
                self._protocol_violation(
                    "packet size ({}) exceeds SEND_MTU".format(
                        self._incomplete_size))

            self._incomplete_buffer = io.BytesIO(
                bytearray(self._incomplete_size))
            self._incomplete_buffer.write(self._header_buffer)
            self._header_buffer = b""


    def eof_received(self):
        pass

    # asyncio.DatagramProtocol implementation

    # def datagram_received(self, data, addr):
    #     pass

    # def error_received(self, exc):
    #     pass

    # public interface

    @property
    def buffer_unknown(self):
        return self._buffer_unknown

    @buffer_unknown.setter
    def buffer_unknown(self, new_value):
        if new_value == self._buffer_unknown:
            return
        self._buffer_unknown = new_value
        if not new_value:
            self._reinspect_buffered_packets()

    @asyncio.coroutine
    def close(self, exc=None):
        if self._transport is None:
            return
        logger.debug("disconnecting...")
        if exc is not None:
            self._terminate(exc)
        else:
            self._close_transport()
        yield from self._closed.wait()

    def new_packet(self, type_):
        return packet.PacketToTransmit(type_,
                                       encoding=self._encoding)

    @asyncio.coroutine
    def send_andor_wait_for(
            self,
            packets_to_send,
            types_to_wait_for,
            queues_to_register={},
            timeout=None,
            buffer_unknown=None,
            critical_timeout=True):
        logger = logging.getLogger(__name__ + ".send_andor_wait_for")

        if buffer_unknown is not None:
            self._buffer_unknown = buffer_unknown

        futures = []
        for type_ in types_to_wait_for:
            logger.debug("registering for type %r", type_)
            f = asyncio.Future(loop=self._loop)
            futures.append((type_, f))
            self.packet_hooks.add_future(type_, f)

        for type_, queue in queues_to_register.items():
            logger.debug("registering queue for type %r", type_)
            self.packet_hooks.add_queue(type_, queue)

        try:
            for packet in packets_to_send:
                self.send_packet(packet)

            self._reinspect_buffered_packets()


            return (yield from self._waiter_task(
                futures,
                timeout,
                critical_timeout))
        finally:
            for type_, queue in queues_to_register.items():
                self.packet_hooks.remove_queue(type_, queue)

    @asyncio.coroutine
    def send_and_collect_replies(self,
                                 packets_to_send,
                                 type_queues,
                                 end_of_transmission_marker,
                                 initial_timeout,
                                 subsequent_timeout,
                                 response_required=True):
        eot_futures = {}
        for type_ in end_of_transmission_marker:
            logger.debug("send_and_collect_replies: registering eot marker %r",
                         type_)
            f = asyncio.Future(loop=self._loop)
            eot_futures[f] = type_
            self.packet_hooks.add_future(type_, f)

        data_futures = {}
        for type_, queue in type_queues.items():
            logger.debug("send_and_collect_replies: registering response queue "
                         "for %r", queue)
            f = asyncio.Future(loop=self._loop)
            data_futures[f] = type_
            self.packet_hooks.add_future(type_, f)
            self.packet_hooks.add_queue(type_, queue)

        try:
            for packet in packets_to_send:
                self.send_packet(packet)

            self._reinspect_buffered_packets()

            return (yield from self._collector_task(
                eot_futures,
                data_futures,
                initial_timeout,
                subsequent_timeout,
                response_required))
        finally:
            for type_, queue in type_queues.items():
                # queues might have been killed due to disconnect
                try:
                    self.packet_hooks.remove_queue(type_, queue)
                except KeyError:
                    pass

    def send_packet(self, pkt):
        if self._transport is None:
            raise ConnectionError("Disconnected")
        logger.debug("sending packet: %r", pkt)
        self._transport.write(pkt.finalize_packet())
