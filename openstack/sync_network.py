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
# Set up neutron configuration for network controller. Use as:
#   ./sync_network.py
#

import argparse
import eventlet
import os
import platform
import re
import sys
import warnings
warnings.filterwarnings("ignore")

from oslo.config import cfg

from neutron.openstack.common.db.sqlalchemy import session
from neutron.openstack.common import log as logging
from neutron.plugins.bigswitch.plugin import NeutronRestProxyV2
from neutron.plugins.bigswitch import servermanager
from neutron.plugins.bigswitch import config

RED_HAT = 'red hat'
UBUNTU = 'ubuntu'
CENTOS = 'CentOS'
DISTRO = None

eventlet.monkey_patch()


def get_config_files():
    """Get config file for restproxy"""
    if DISTRO in [RED_HAT, CENTOS]:
        files = [
            "/usr/share/neutron/neutron-dist.conf",
            "/etc/neutron/neutron.conf",
            "/etc/neutron/dhcp_agent.ini",
            "/etc/neutron/plugin.ini",
        ]
    elif DISTRO in [UBUNTU]:
        files = [
            "/etc/neutron/neutron.conf",
            "/etc/neutron/dhcp_agent.ini",
            "/etc/neutron/plugins/bigswitch/restproxy.ini",
            "/etc/neutron/plugins/ml2/ml2_conf.ini",
        ]
    return [f for f in files if os.path.exists(f)]


def init_config():
    """Initialize configuration for this script"""
    logging.setup("sync_network")
    cfgfile = get_config_files()
    cfg.CONF(
        args=[j for i in zip(["--config-file"]*len(cfgfile), cfgfile)
              for j in i],
        project="neutron",
    )
    cfg.CONF.set_override('control_exchange', '')
    cfg.CONF.set_override('rpc_backend', 'neutron.openstack.common.rpc.impl_fake')
    cfg.CONF.set_override('verbose', True)
    cfg.CONF.set_override('debug', True)
    config.register_config()
    cfg.CONF.set_override('consistency_interval', 0, 'RESTPROXY')
    cfg.CONF.set_override('sync_data', False, 'RESTPROXY')
    # override to suppress annoying mysql mode warning
    session.LOG.warning = lambda *args, **kwargs: True
    # replace watchdog so it doesn't try to start
    servermanager.ServerPool._consistency_watchdog = lambda x, y: True


def send_all_data(send_ports=True, send_floating_ips=True, send_routers=True):
    """Send all data to the configured network controller
       returns: None on success, else the reason for error (string)
    """
    try:
        rproxy = NeutronRestProxyV2()
        print "INFO: Using servers: ", cfg.CONF.RESTPROXY.servers
        rproxy._send_all_data(send_ports, send_floating_ips, send_routers)
    except Exception as e:
        return e.message
    return None


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description='Push OpenStack Data to Controller')
    parser.add_argument('--include-routers', action='store_true',
                        help="Include routers in data sent to controller. "
                             "(Do not use with ML2)")
    parser.add_argument('--no-floatingips', action='store_true',
                        help="Don't include floating IPs in data sent to controller")
    parser.add_argument('--no-ports', action='store_true',
                        help="Don't include ports in data sent to controller")

    args = parser.parse_args()

    # hillbilly speak to convert negative boolean to positive boolean
    send_ports = not args.no_ports
    send_floating_ips = not args.no_floatingips
    send_routers = args.include_routers

    linux_distro = platform.linux_distribution()[0]
    print "INFO: Detected linux distro: ", linux_distro
    if re.search(RED_HAT, linux_distro, re.IGNORECASE):
        DISTRO = RED_HAT
    elif re.search(UBUNTU, linux_distro, re.IGNORECASE):
        DISTRO = UBUNTU
    elif re.search(CENTOS, linux_distro, re.IGNORECASE):
        DISTRO = CENTOS
    else:
        print "ERROR: Linux distro not supported"
        sys.exit(1)
    init_config()
    ret = send_all_data(send_ports=send_ports,
                        send_floating_ips=send_floating_ips,
                        send_routers=send_routers)
    if ret is not None:
        print "ERROR: In sending data to network controller"
        print "       " + str(ret)
        sys.exit(1)
    print "INFO: Sync Done. All data (re)sent to the network controller"
    sys.exit(0)
