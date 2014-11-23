class ServerInformation:
    def __init__(self):
        self.name = None
        self.openttd_revision = None
        self.dedicated = None
        self.map_name = None
        self.map_seed = None
        self.map_landscape = None
        self.starting_year = None
        self.map_size = None

    def read_from_welcome(self, pkt, encoding=None):
        success = True
        try:
            self.name = pkt.unpack_bytes().decode(encoding)
        except UnicodeDecodeError as err:
            success = False
        try:
            self.openttd_revision = pkt.unpack_bytes().decode(encoding)
        except UnicodeDecodeError as err:
            success = False
        self.dedicated = pkt.unpack_bool()
        try:
            self.map_name = pkt.unpack_bytes().decode(encoding)
        except UnicodeDecodeError as err:
            success = False
        self.map_seed = pkt.unpack_uint32()
        self.map_landscape = pkt.unpack_uint8()
        self.starting_year = pkt.unpack_uint32()
        self.map_size = pkt.unpack_uint16(), pkt.unpack_uint16()

        return success
