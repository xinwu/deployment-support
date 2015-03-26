import os
import re
import socket
import constants as const
from lib.helper import Helper

class Environment(object):
    def __init__(self, config):
        # setup node ip, user and pwd
        self.setup_node_ip  = Helper.get_setup_node_ip()
        self.setup_node_dir = os.getcwd()
        for node_config in config['nodes']:
            node_ip = socket.gethostbyname(node_config['hostname'])
            if node_ip == self.setup_node_ip:
                self.setup_node_user =config['default_user']
                if 'user' in node_config:
                    self.setup_node_user = node_config['user']
                self.setup_node_passwd = config['default_passwd']
                if 'passwd' in node_config:
                    self.setup_node_passwd = node_config['passwd']
                break

        # selinux configuration
        self.selinux_mode = None
        if os.path.isfile(const.SELINUX_CONFIG_PATH):
            with open(const.SELINUX_CONFIG_PATH, "r") as selinux_config_file:
                selinux_mode_match = re.compile(const.SELINUX_MODE_EXPRESSION, re.IGNORECASE)
                lines = selinux_config_file.readlines()
                for line in lines:
                    match = selinux_mode_match.match(line)
                    if match:
                        self.selinux_mode = match.group(1)

        # neutron vlan ranges
        self.network_vlan_ranges = config['network_vlan_ranges']
        new_vlan_range_pattern = re.compile(const.NEW_VLAN_RANGE_EXPRESSION, re.IGNORECASE)
        match = new_vlan_range_pattern.match(self.network_vlan_ranges)
        if not match:
            Helper.safe_print("network_vlan_ranges' format is not correct.\n")
            exit(1)
        self.physnet    = match.group(1)
        self.lower_vlan = match.group(2)
        self.upper_vlan = match.group(3)

        # bcf controller information
        self.bcf_controllers = config['bcf_controllers']
        self.bcf_controller_user = config['bcf_controller_user']
        self.bcf_controller_passwd = config['bcf_controller_passwd']

        # ivs pkg and debug pkg
        self.ivs_pkg_map = {}
        for ivs_package in config['ivs_packages']:
            ivs_pkg = os.path.basename(ivs_package['package'])
            if '.rpm' in ivs_pkg and '-debuginfo-' not in ivs_pkg:
                self.ivs_pkg_map['rpm'] = ivs_pkg
            elif '.rpm' in ivs_pkg and '-debuginfo-' in ivs_pkg:
                self.ivs_pkg_map['debug_rpm'] = ivs_pkg
            elif '.deb' in ivs_pkg and '-debuginfo-' not in ivs_pkg:
                self.ivs_pkg_map['deb'] = ivs_pkg
            elif '.deb' in ivs_pkg and '-debuginfo-' in ivs_pkg:
                self.ivs_pkg_map['debug_deb'] = ivs_pkg


