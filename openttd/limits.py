# File name: limits.py
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
