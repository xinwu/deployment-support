import os
import re
import socket
import constants as const
from lib.helper import Helper

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
            node_ip = socket.gethostbyname(node_config['hostname'])
            if node_ip == self.setup_node_ip:
                role = config['default_role']
                if 'role' in node_config:
                    role = node_config['role']
                if role != const.ROLE_NEUTRON_SERVER:
                    Helper.safe_print("Setup node %(node_ip)s needs to be a neutron server.\n" %
                                     {'node_ip' : node_ip})
                    exit(1)
                self.setup_node_user = config['default_user']
                if 'user' in node_config:
                    self.setup_node_user = node_config['user']
                self.setup_node_passwd = config['default_passwd']
                if 'passwd' in node_config:
                    self.setup_node_passwd = node_config['passwd']

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
        new_vlan_range_pattern = re.compile(const.NEW_VLAN_RANGE_EXPRESSION, re.IGNORECASE)
        match = new_vlan_range_pattern.match(self.network_vlan_ranges)
        if not match:
            Helper.safe_print("network_vlan_ranges' format is not correct.\n")
            exit(1)
        self.physnet    = match.group(1)
        self.lower_vlan = match.group(2)
        self.upper_vlan = match.group(3)
        with open(const.VLAN_RANGE_CONFIG_PATH, "r") as vlan_range_file:
            lines = vlan_range_file.readlines()
            for line in lines:
                match = existing_vlan_range_pattern.match(line)
                if match:
                    existing_phynet = match.group(1)
                    existing_lower_vlan = match.group(2)
                    existing_upper_vlan = match.group(3)
                    if self.physnet != existing_phynet:
                        Helper.safe_print("physnet does not match with exiting ml2_conf.ini.\n")
                        exit(1)
                    if self.lower_vlan > existing_lower_vlan:
                        Helper.safe_print("lower vlan range is larger than exiting lower vlan range in ml2_conf.ini.\n")
                        exit(1)
                    if self.upper_vlan < existing_upper_vlan:
                        Helper.safe_print("upper vlan range is smaller than exiting upper vlan range in ml2_conf.ini.\n")
                        exit(1)
                    break

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


