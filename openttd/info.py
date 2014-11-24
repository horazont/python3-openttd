"""
``openttd.info`` -- Data tuples for game metadata
#################################################

This module merely contains several enums, classes and
:class:`~collections.namedtuple`\ s which contain data received in queries to the
server.

Enumerations
============

.. autoclass:: NetworkVehicleType
   :members:
   :undoc-members:

.. autoclass:: DestType
   :members:
   :undoc-members:

.. autoclass:: NetworkAction
   :members:
   :undoc-members:

Classes
=======

.. autoclass:: ServerInformation
   :members:
   :undoc-members:

.. autoclass:: ClientInformation
   :members:
   :undoc-members:

.. autoclass:: CompanyInformation
   :members:
   :undoc-members:

"""

import collections
import logging

from enum import Enum

logger = logging.getLogger()

class NetworkVehicleType(Enum):
    """
    Enum for OpenTTD vehicle types (src:
    ``openttd:src/network/core/network_type.h``)
    """

    TRAIN = 0
    LORRY = 1
    BUS = 2
    PLANE = 3
    SHIP = 4

class DestType(Enum):
    """
    Enum for the destination of a chat message (src:
    ``openttd:src/network/core/network_type.h``)
    """

    BROADCAST = 0
    TEAM = 1
    CLIENT = 2

class NetworkAction(Enum):
    """
    Enum for the action of a chat message (src:
    ``openttd:src/network/core/network_type.h``)
    """

    JOIN = 0
    LEAVE = 1
    SERVER_MESSAGE = 2
    CHAT = 3
    CHAT_COMPANY = 4
    CHAT_CLIENT = 5
    GIVE_MONEY = 6
    NAME_CHANGE = 7
    COMPANY_SPECTATOR = 8
    COMPANY_JOIN = 9
    COMPANY_NEW = 10


class ServerInformation:
    """
    Server information
    """

    #: server name (as displayed in the GUI)
    name = None

    #: openttd revision running on the server
    openttd_revision = None

    #: is a dedicated server
    dedicated = None

    #: name of the map, if any (empty string otherwise)
    map_name = None

    #: seed used to generate the map
    map_seed = None

    #: landscape of the map
    map_landscape = None

    #: year in which the game started
    starting_year = None

    #: size of the map
    map_size = None

    def read_from_packet(self, pkt):
        """
        Read the information from a :class:`~openttd.packet.ReceivedPacket`
        *pkt*.

        Return :data:`True` if all data has been read successfully,
        :data:`False` otherwise. This can occur e.g. if the encoding of the
        string data is incorrect or unset.
        """
        success = True
        try:
            self.name = pkt.unpack_string()
        except UnicodeDecodeError as err:
            success = False
        try:
            self.openttd_revision = pkt.unpack_string()
        except UnicodeDecodeError as err:
            success = False
        self.dedicated = pkt.unpack_bool()
        try:
            self.map_name = pkt.unpack_string()
        except UnicodeDecodeError as err:
            success = False
        self.map_seed = pkt.unpack_uint32()
        self.map_landscape = pkt.unpack_uint8()
        self.starting_year = pkt.unpack_uint32()
        self.map_size = pkt.unpack_uint16(), pkt.unpack_uint16()

        return success

class ClientInformation:
    """
    Client information
    """

    #: client id
    id = None

    hostname = None

    #: client name (as shown in the GUI)
    name = None
    lang = None
    join_date = None

    #: company ID controlled by the client (255 -> none)
    play_as = None

    def read_from_packet(self, pkt):
        """
        Read the information from a :class:`~openttd.packet.ReceivedPacket`
        *pkt*.
        """
        self.id = pkt.unpack_uint32()
        self.hostname = pkt.unpack_string()
        self.name = pkt.unpack_string()
        self.lang = pkt.unpack_uint8()
        self.join_date = pkt.unpack_uint32()
        self.play_as = pkt.unpack_uint8()

    def __str__(self):
        return ("client #{}: hostname={!r} name={!r} lang={} join_date={} "
                "play_as={}".format(
                    self.id,
                    self.hostname,
                    self.name,
                    self.lang,
                    self.join_date,
                    self.play_as))

class CompanyInformation:
    """
    Company information
    """

    id = None
    name = None
    manager_name = None
    colour = None
    is_passworded = None
    inaugurated_year = None
    is_ai = None
    quarters_of_bankruptcy = None
    share_owners = None

    def __init__(self):
        self.share_owners = []

    def read_from_packet(self, pkt):
        """
        Read the information from a :class:`~openttd.packet.ReceivedPacket`
        *pkt*.
        """
        self.id = pkt.unpack_uint8()
        self.name = pkt.unpack_string()
        self.manager_name = pkt.unpack_string()
        self.colour = pkt.unpack_uint8()
        self.is_passworded = pkt.unpack_bool()
        self.inaugurated_year = pkt.unpack_uint32()
        self.is_ai = pkt.unpack_bool()
        self.quarters_of_bankruptcy = pkt.unpack_uint8()

        self.share_owners = [
            value for value in (
                pkt.unpack_uint8()
                for i in range(4)
            )
            if value != 255]

    def __str__(self):
        return ("company #{}: name={!r} manager={!r} colour={} passworded={}"
                " ai={} inaugurated_year={} quarters_of_bankruptcy={}"
                " share_owners={}".format(
                    self.id,
                    self.name,
                    self.manager_name,
                    self.colour,
                    self.is_passworded,
                    self.is_ai,
                    self.inaugurated_year,
                    self.quarters_of_bankruptcy,
                    self.share_owners))

CompanyPerformance = collections.namedtuple(
    "CompanyPerformance",
    [
        "value",
        "performance",
        "delivered_cargo"
    ])

class CompanyEconomy:
    id = None
    money = None
    current_loan = None
    income = None
    delivered_cargo = None
    performance_history = None

    def read_from_packet(self, pkt):
        self.id = pkt.unpack_uint8()
        self.money = pkt.unpack_int64()
        self.current_loan = pkt.unpack_uint64()
        self.income = pkt.unpack_int64()
        self.delivered_cargo = pkt.unpack_uint16()

        self.performance_history = [
            CompanyPerformance(
                value=pkt.unpack_uint64(),
                performance=pkt.unpack_uint16(),
                delivered_cargo=pkt.unpack_uint16()
            )
            for i in range(2)
        ]

    def __str__(self):
        return ("company #{} (economy): money={} loan={} income={} "
                "delivered_cargo={} performance_history={}".format(
                    self.id,
                    self.money,
                    self.current_loan,
                    self.income,
                    self.delivered_cargo,
                    self.performance_history))

class CompanyStats:
    id = None
    vehicle_counts = None
    station_counts = None

    def __init__(self):
        # override attributes with new values
        self.vehicle_counts = collections.Counter()
        self.station_counts = collections.Counter()

    def read_from_packet(self, pkt):
        self.id = pkt.unpack_uint8()
        # guess number of types by length of packet
        types = pkt.remaining_length // 4
        for type_id in range(types):
            try:
                type_ = NetworkVehicleType(type_id)
            except ValueError:
                logger.debug("unknown vehicle type: %d", type_id)
                type_ = type_id
            self.vehicle_counts[type_] = pkt.unpack_uint16()

        for type_id in range(types):
            try:
                type_ = NetworkVehicleType(type_id)
            except ValueError:
                type_ = type_id
            self.station_counts[type_] = pkt.unpack_uint16()

    def __str__(self):
        return ("company #{} (stats): vehicle_counts={} "
                "station_counts={}".format(
                    self.id,
                    self.vehicle_counts,
                    self.station_counts))

_ChatMessage = collections.namedtuple(
    "_ChatMessage",
    ["action", "desttype", "dest", "msg"])

class ChatMessage(_ChatMessage):
    @classmethod
    def read_from_packet(cls, pkt):
        return cls(NetworkAction(pkt.unpack_uint8()),
                   DestType(pkt.unpack_uint8()),
                   pkt.unpack_uint32(),
                   pkt.unpack_string())

    def __str__(self):
        return "{} {} {} {}".format(
            self.action, self.desttype, self.dest,
            self.msg)

    def __repr__(self):
        return "<ChatMessage action={} desttype={} dest={} msg={!r}>".format(
            self.action,
            self.desttype,
            self.dest,
            self.msg)

ClientError = collections.namedtuple(
    "ClientError",
    ["id", "error"])

ClientQuit = collections.namedtuple(
    "ClientQuit",
    ["id"])

ClientUpdate = collections.namedtuple(
    "ClientUpdate",
    ["id", "new_name", "new_company_id"])

ClientJoin = collections.namedtuple(
    "ClientJoin",
    ["id"])

CompanyUpdate = collections.namedtuple(
    "CompanyUpdate",
    ["id", "new_name", "new_manager_name",
     "new_colour", "new_is_passworded",
     "new_quarters_of_bankruptcy", "new_share_owners"])
