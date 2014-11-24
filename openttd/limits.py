"""
``openttd.limits`` -- Limits as provided by OpenTTD
###################################################

These limits are taken from ``src/network/core/config.h`` from within the
OpenTTD source tree. All numeric values in this module **exclude** the
terminating NUL byte (which is not the case for the values in the OpenTTD
source).

.. autodata:: NETWORK_PASSWORD_LENGTH
.. autodata:: NETWORK_CLIENT_NAME_LENGTH
.. autodata:: NETWORK_REVISION_LENGTH
.. autodata:: NETWORK_RCONCOMMAND_LENGTH
.. autodata:: NETWORK_CHAT_LENGTH
"""

#: maximum length of a network password, in bytes
NETWORK_PASSWORD_LENGTH = 32

#: maximum length of a client name, in bytes
NETWORK_CLIENT_NAME_LENGTH = 24

#: maximum length of a client revision, in bytes
NETWORK_REVISION_LENGTH = 14

#: maximum length of a remote command line, in bytes
NETWORK_RCONCOMMAND_LENGTH = 499

#: maximum length of a chat message, in bytes
NETWORK_CHAT_LENGTH = 899
