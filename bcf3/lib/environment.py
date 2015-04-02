import os
import re
import socket
import constants as const
from helper import Helper

class Environment(object):
    def __init__(self, config, fuel_cluster_id):
        # fuel cluster id
        self.fuel_cluster_id = fuel_cluster_id

        # setup node ip and directory
        self.setup_node_ip  = Helper.get_setup_node_ip()
        self.setup_node_dir = os.getcwd()

        # if ivs pkg is necessary
        self.deploy_ivs = False
        if 'default_deploy_ivs' in config and config['default_deploy_ivs']:
            self.deploy_ivs = config['default_deploy_ivs']
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

        # information will be passed on to nodes
        self.skip = False
        if 'default_skip' in config:
            self.skip = config['default_skip']

        self.deploy_ivs = None
        if 'default_deploy_ivs' in config:
            self.deploy_ivs = config['default_deploy_ivs']

        self.os = None
        if 'default_os' in config:
            self.os = config['default_os']
        
        self.os_version = None
        if 'default_os_version' in config:
            self.os_version = config['default_os_version']
        
        self.bsnstacklib_version = None
        if 'default_bsnstacklib_version' in config:
            self.bsnstacklib_version = config['default_bsnstacklib_version']
        
        self.role = None
        if 'default_role' in config:
            self.role = config['default_role']

        self.user = None
        if 'default_user' in config:
            self.user = config['default_user']

        self.passwd = None
        if 'default_passwd' in config:
            self.passwd = config['default_passwd']

        self.uplink_interfaces = None
        if 'default_uplink_interfaces' in config:
            self.uplink_interfaces = config['default_uplink_interfaces']

        # fields introduced by fuel
        self.physnet_bridge = None
        self.br_management  = None
        self.br_storage     = None
        self.br_ex          = None
        self.br_private     = None
        self.br_bond        = None


    def set_physnet(self, physnet):
        self.physnet = physnet


    def set_physnet_bridge(self, physnet_bridge):
        self.physnet_bridge = physnet_bridge


    def set_lower_vlan(self, lower_vlan):
        self.lower_vlan = lower_vlan


    def set_upper_vlan(self, upper_vlan):
        self.upper_vlan = upper_vlan


    def set_br_management(self, br_mgmt):
        self.br_management = br_mgmt


    def set_br_storage(self, br_storage):
        self.br_storage = br_storage


    def set_br_ex(self, br_ex):
        self.br_ex = br_ex


    def set_br_private(self, br_private):
        self.br_private = br_private


    def set_br_bond(self, br_bond):
        self.br_bond = br_bond


