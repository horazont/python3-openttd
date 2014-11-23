import asyncio
import binascii
import logging
import sys

def handle_client_info(info):
    print(info)

def handle_company_info(info):
    print(info)

@asyncio.coroutine
def main(loop, hostname, port, password):
    client = openttd.admin.Client(loop=loop)
    client.on_error = logger.error
    try:
        yield from client.connect_tcp(hostname, port)
    except OSError as err:
        print("failed to connect:", err, file=sys.stderr)
        return

    try:
        yield from client.authenticate(
            password,
            "python3-openttd test",
            "devel")
    except:
        logger.exception("during authentication: ")
        return

    logger.info("Connected to server: %s", client.server_info.name)

    yield from client.rcon_command("unpause")

    client.subscribe_callback_to_push(
        openttd.admin.UpdateType.CLIENT_INFO,
        handle_client_info)

    client.subscribe_callback_to_push(
        openttd.admin.UpdateType.COMPANY_INFO,
        handle_company_info)

    client.subscribe_callback_to_push(
        openttd.admin.UpdateType.COMPANY_STATS,
        handle_company_info,
        frequency=openttd.admin.UpdateFrequency.WEEKLY
    )

    client.subscribe_callback_to_push(
        openttd.admin.UpdateType.COMPANY_ECONOMY,
        handle_company_info,
        frequency=openttd.admin.UpdateFrequency.WEEKLY
    )

    try:
        yield from asyncio.wait(
            [
                client.disconnected_event.wait()
            ])
    except:
        yield from client.disconnect()

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument(
        "-v",
        dest="verbosity",
        action="count",
        default=0,
        help="Increase verbosity (anything above -vvv does not make sense)"
    )
    parser.add_argument(
        "hostname",
        help="Host name to connect to"
    )
    parser.add_argument(
        "port",
        nargs="?",
        type=int,
        default=3977,
        help="Port to connect to"
    )
    parser.add_argument(
        "password",
        help="Password for the administration interface."
    )

    args = parser.parse_args()

    logging.basicConfig(
        level={
            0: logging.ERROR,
            1: logging.WARN,
            2: logging.INFO
        }.get(args.verbosity, logging.DEBUG))

    logging.getLogger("asyncio").setLevel(level=logging.WARN)

    logger = logging.getLogger("test")


    loop = asyncio.get_event_loop()
    loop.set_debug(True)

    import openttd.admin
    import openttd.packet

    loop.run_until_complete(main(
        loop,
        args.hostname,
        args.port,
        args.password))
