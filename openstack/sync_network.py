#! /usr/bin/env python
#
# vim: tabstop=4 shiftwidth=4 softtabstop=4
#
# Copyright 2011, Big Switch Networks, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mandeep Dhami, Big Switch Networks, Inc.
#

# USAGE:
# Set up quantum configuration for network controller. Use as:
#   ./sync_network.py
#

import platform
import re
import sys
import warnings
warnings.filterwarnings("ignore")

from oslo.config import cfg

from quantum.openstack.common import log as logging
from quantum.plugins.bigswitch.plugin import QuantumRestProxyV2


RED_HAT = 'red hat'
UBUNTU  = 'ubuntu'
DISTRO = None

def get_config_files():
    """Get config file for restproxy"""
    if DISTRO in [RED_HAT]:
        return [
            "/usr/share/quantum/quantum-dist.conf",
            "/etc/quantum/quantum.conf",
            "/etc/quantum/dhcp_agent.ini",
            "/etc/quantum/plugin.ini",
        ]
    elif DISTRO in [UBUNTU]:
        return [
            "/etc/quantum/quantum.conf",
            "/etc/quantum/dhcp_agent.ini",
            "/etc/quantum/plugins/bigswitch/restproxy.ini",
        ]


def init_config():
    """Initialize configuration for this script"""
    logging.setup("sync_network")
    cfgfile = get_config_files()
    cfg.CONF(
        args = [j for i in zip(["--config-file"]*len(cfgfile), cfgfile)
                  for j in i],
        project = "quantum",
    )
    cfg.CONF.set_override('control_exchange', '')
    cfg.CONF.set_override('rpc_backend', 'quantum.openstack.common.rpc.impl_fake')
    cfg.CONF.set_override('verbose', True)
    cfg.CONF.set_override('debug', True)


def send_all_data():
    """Send all data to the configured network controller
       returns: None on success, else the reason for error (string)
    """
    try:
        rproxy = QuantumRestProxyV2()
        print "INFO: Using servers: ", cfg.CONF.RESTPROXY.servers
        rproxy._send_all_data()
    except Exception as e:
        return e.message
    return None


if __name__ == "__main__":
    linux_distro = platform.linux_distribution()[0]
    print "INFO: Detected linux distro: ", linux_distro
    if re.search(RED_HAT, linux_distro, re.IGNORECASE):
        DISTRO = RED_HAT
    elif re.search(UBUNTU, linux_distro, re.IGNORECASE):
        DISTRO = UBUNTU
    else:
        print "ERROR: Linux distro not supported"
        sys.exit(1)
    init_config()
    ret = send_all_data()
    if ret is not None:
        print "ERROR: In sending data to network controller"
        print "       " + str(ret)
        sys.exit(1)
    print "INFO: Sync Done. All data (re)sent to the network controller"
    sys.exit(0)
