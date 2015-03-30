import os
import re
import socket
import constants as const
from helper import Helper

class Environment(object):
    def __init__(self, config):
        self.deploy_ivs = False
        if 'default_deploy_ivs' in config and config['default_deploy_ivs']:
            self.deploy_ivs = config['default_deploy_ivs']
        # setup node ip, user and pwd
        self.setup_node_ip  = Helper.get_setup_node_ip()
        self.setup_node_dir = os.getcwd()
        for node_config in config['nodes']:
            if not self.deploy_ivs and 'deploy_ivs' in node_config and node_config['deploy_ivs']:
                self.deploy_ivs = node_config['deploy_ivs']

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
                        break

        # neutron vlan ranges
        self.network_vlan_ranges = config['network_vlan_ranges']
        network_vlan_range_pattern = re.compile(const.NETWORK_VLAN_RANGE_EXPRESSION, re.IGNORECASE)
        match = network_vlan_range_pattern.match(self.network_vlan_ranges)
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
        self.ivs_url_map = {}
        for ivs_package in config['ivs_packages']:
            ivs_url = ivs_package['package']
            ivs_pkg = os.path.basename(ivs_url)
            if '.rpm' in ivs_pkg and '-debuginfo-' not in ivs_pkg:
                self.ivs_url_map['rpm'] = ivs_url
                self.ivs_pkg_map['rpm'] = ivs_pkg
            elif '.rpm' in ivs_pkg and '-debuginfo-' in ivs_pkg:
                self.ivs_url_map['debug_rpm'] = ivs_url
                self.ivs_pkg_map['debug_rpm'] = ivs_pkg
            elif '.deb' in ivs_pkg and '-debuginfo-' not in ivs_pkg:
                self.ivs_url_map['deb'] = ivs_url
                self.ivs_pkg_map['deb'] = ivs_pkg
            elif '.deb' in ivs_pkg and '-debuginfo-' in ivs_pkg:
                self.ivs_url_map['debug_deb'] = ivs_url
                self.ivs_pkg_map['debug_deb'] = ivs_pkg


