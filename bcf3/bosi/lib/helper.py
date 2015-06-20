import os
import sys
import time
import json
import yaml
import socket
import string
import netaddr
import threading
import constants as const
import subprocess32 as subprocess
from node import Node
from rest import RestLib
from bridge import Bridge
from threading import Lock
from membership_rule import MembershipRule


class Helper(object):

    # lock to serialize stdout of different threads
    __print_lock = Lock()

    @staticmethod
    def get_setup_node_ip():
        """
        Get the setup node's eth0 ip
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('bigswitch.com', 0))
        return s.getsockname()[0]


    @staticmethod
    def run_command_on_local_without_timeout(command):
        output, error = subprocess.Popen(command,
            stdout = subprocess.PIPE,
            stderr = subprocess.PIPE,
            shell=True).communicate()
        return output, error


    @staticmethod
    def run_command_on_remote_with_key_without_timeout(node_ip, command):
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(hostname)s "%(remote_cmd)s"''' %
                    {'hostname'   : node_ip,
                     'remote_cmd' : command,
                    })
        return Helper.run_command_on_local_without_timeout(local_cmd)


    @staticmethod
    def run_command_on_local(command, timeout=1800):
        """
        Use subprocess to run a shell command on local node.
        """
        def target():
            try:
                p = subprocess.Popen(
                    command, shell=True, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, close_fds=True, bufsize=1)
            except Exception as e:
                msg = "Error opening process %s: %s\n" % (command, e)
                Helper.safe_print(msg)
                return
            p.communicate()

        thread = threading.Thread(target=target)
        thread.start()
        thread.join(timeout)
        if thread.is_alive():
            p.terminate()
            thread.join()
            msg = "Timed out waiting for command %s to finish." % command
            Helper.safe_print(msg)


    @staticmethod
    def safe_print(message):
        """
        Grab the lock and print to stdout.
        The lock is to serialize messages from
        different thread. 'stty sane' is to
        clean up any hiden space.
        """
        with Helper.__print_lock:
            subprocess.call('stty sane', shell=True)
            sys.stdout.write(message)
            sys.stdout.flush()
            subprocess.call('stty sane', shell=True)


    @staticmethod
    def run_command_on_remote_with_passwd(node, command):
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s >> %(log)s 2>&1 "echo %(pwd)s | sudo -S %(remote_cmd)s"''' %
                   {'user'       : node.user,
                    'hostname'   : node.hostname,
                    'pwd'        : node.passwd,
                    'log'        : node.log,
                    'remote_cmd' : command,
                   })
        Helper.run_command_on_local(local_cmd)


    @staticmethod
    def run_command_on_remote_with_passwd_without_timeout(hostname, user, passwd, command):
        local_cmd = (r'''sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s "echo %(pwd)s | sudo -S %(remote_cmd)s"''' %
                   {'user'       : user,
                    'hostname'   : hostname,
                    'pwd'        : passwd,
                    'log'        : const.LOG_FILE,
                    'remote_cmd' : command,
                   })
        return Helper.run_command_on_local_without_timeout(local_cmd)


    @staticmethod
    def copy_file_to_remote_with_passwd(node, src_file, dst_dir, dst_file, mode=777):
        """
        Copy file from local node to remote node,
        create directory if remote directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_remote_with_passwd(node, mkdir_cmd)
        scp_cmd = (r'''sshpass -p %(pwd)s scp -oStrictHostKeyChecking=no -o LogLevel=quiet -r %(src_file)s  %(user)s@%(hostname)s:%(dst_dir)s/%(dst_file)s >> %(log)s 2>&1''' %
                  {'user'       : node.user,
                   'hostname'   : node.hostname,
                   'pwd'        : node.passwd,
                   'log'        : node.log,
                   'src_file'   : src_file,
                   'dst_dir'    : dst_dir,
                   'dst_file'   : dst_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(dst_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'dst_file' : dst_file
                    })
        Helper.run_command_on_remote_with_passwd(node, chmod_cmd)


    @staticmethod
    def copy_file_from_remote_with_passwd(node, src_dir, src_file, dst_dir, mode=777):
        """
        Copy file from remote node to local node,
        create directory if local directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_local(mkdir_cmd)
        scp_cmd = (r'''sshpass -p %(pwd)s scp -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s:%(src_dir)s/%(src_file)s %(dst_dir)s/%(src_file)s >> %(log)s 2>&1''' %
                  {'pwd'        : node.passwd,
                   'user'       : node.user,
                   'hostname'   : node.hostname,
                   'log'        : node.log,
                   'src_dir'    : src_dir,
                   'dst_dir'    : dst_dir,
                   'src_file'   : src_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(src_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'src_file' : src_file
                    })
        Helper.run_command_on_local(chmod_cmd)


    @staticmethod
    def run_command_on_remote_with_key(node, command):
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(hostname)s >> %(log)s 2>&1 "%(remote_cmd)s"''' %
                   {'hostname'   : node.hostname,
                    'log'        : node.log,
                    'remote_cmd' : command
                   })
        Helper.run_command_on_local(local_cmd)


    @staticmethod
    def copy_file_to_remote_with_key(node, src_file, dst_dir, dst_file, mode=777):
        """
        Copy file from local node to remote node,
        create directory if remote directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_remote_with_key(node, mkdir_cmd)
        scp_cmd = (r'''scp -oStrictHostKeyChecking=no -o LogLevel=quiet -r %(src_file)s %(hostname)s:%(dst_dir)s/%(dst_file)s >> %(log)s 2>&1''' %
                  {'hostname'   : node.hostname,
                   'log'        : node.log,
                   'src_file'   : src_file,
                   'dst_dir'    : dst_dir,
                   'dst_file'   : dst_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(dst_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'dst_file' : dst_file
                    })
        Helper.run_command_on_remote_with_key(node, chmod_cmd)


    @staticmethod
    def copy_file_from_remote_with_key(node, src_dir, src_file, dst_dir, mode=777):
        """
        Copy file from remote node to local node,
        create directory if local directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_local(mkdir_cmd)
        scp_cmd = (r'''scp -oStrictHostKeyChecking=no -o LogLevel=quiet %(hostname)s:%(src_dir)s/%(src_file)s %(dst_dir)s/%(src_file)s >> %(log)s 2>&1''' %
                  {'hostname'   : node.hostname,
                   'log'        : node.log,
                   'src_dir'    : src_dir,
                   'dst_dir'    : dst_dir,
                   'src_file'   : src_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(src_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'src_file' : src_file
                    })
        Helper.run_command_on_local(chmod_cmd)


    @staticmethod
    def generate_scripts_for_ubuntu(node):
        # generate bash script
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(bash_template_dir)s/%(bash_template)s_%(os_version)s.sh''' %
                  {'setup_node_dir'    : node.setup_node_dir,
                   'deploy_mode'       : node.deploy_mode,
                   'bash_template_dir' : const.BASH_TEMPLATE_DIR,
                   'bash_template'     : const.UBUNTU,
                   'os_version'        : node.os_version}), "r") as bash_template_file:
            bash_template = bash_template_file.read()
            is_controller = False
            if node.role == const.ROLE_NEUTRON_SERVER:
                is_controller = True
            bash = (bash_template %
                   {'install_ivs'         : str(node.install_ivs).lower(),
                    'install_bsnstacklib' : str(node.install_bsnstacklib).lower(),
                    'install_all'         : str(node.install_all).lower(),
                    'deploy_dhcp_agent'   : str(node.deploy_dhcp_agent).lower(),
                    'is_controller'       : str(is_controller).lower(),
                    'deploy_horizon_patch': str(node.deploy_horizon_patch).lower(),
                    'ivs_version'         : node.ivs_version,
                    'bsnstacklib_version' : node.bsnstacklib_version,
                    'dst_dir'             : node.dst_dir,
                    'hostname'            : node.hostname,
                    'ivs_pkg'             : node.ivs_pkg,
                    'horizon_patch'       : node.horizon_patch,
                    'horizon_patch_dir'   : node.horizon_patch_dir,
                    'horizon_base_dir'    : node.horizon_base_dir,
                    'ivs_debug_pkg'       : node.ivs_debug_pkg,
                    'ovs_br'              : node.get_all_ovs_brs(),
                    'bonds'               : node.get_all_bonds(),
                    'br-int'              : const.BR_NAME_INT,
                    'fuel_cluster_id'     : str(node.fuel_cluster_id),
                    'interfaces'          : node.get_all_interfaces(),
                    'br_fw_admin'         : node.br_fw_admin,
                    'pxe_interface'       : node.pxe_interface,
                    'br_fw_admin_address' : node.br_fw_admin_address,
                    'br_fw_admin_gw'      : node.setup_node_ip,
                    'uplinks'             : node.get_all_uplinks()})
        bash_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.sh''' %
                           {'setup_node_dir'       : node.setup_node_dir,
                            'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                            'hostname'             : node.hostname})
        with open(bash_script_path, "w") as bash_file:
            bash_file.write(bash)
        node.set_bash_script_path(bash_script_path)

        # generate puppet script
        ivs_daemon_args = (const.IVS_DAEMON_ARGS %
                          {'inband_vlan'       : const.INBAND_VLAN,
                           'internal_ports'    : node.get_ivs_internal_ports(),
                           'uplink_interfaces' : node.get_uplink_intfs_for_ivs()})
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(puppet_template_dir)s/%(puppet_template)s_%(role)s.pp''' %
                  {'setup_node_dir'      : node.setup_node_dir,
                   'deploy_mode'         : node.deploy_mode,
                   'puppet_template_dir' : const.PUPPET_TEMPLATE_DIR,
                   'puppet_template'     : const.UBUNTU,
                   'role'                : node.role}), "r") as puppet_template_file:
            puppet_template = puppet_template_file.read()
            puppet = (puppet_template %
                     {'ivs_daemon_args'       : ivs_daemon_args,
                      'network_vlan_ranges'   : node.get_network_vlan_ranges(),
                      'bcf_controllers'       : node.get_controllers_for_neutron(),
                      'bcf_controller_user'   : node.bcf_controller_user,
                      'bcf_controller_passwd' : node.bcf_controller_passwd,
                      'port_ips'              : node.get_ivs_internal_port_ips(),
                      'setup_node_ip'         : node.setup_node_ip})
        puppet_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.pp''' %
                             {'setup_node_dir'       : node.setup_node_dir,
                              'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                              'hostname'             : node.hostname})
        with open(puppet_script_path, "w") as puppet_file:
            puppet_file.write(puppet)
        node.set_puppet_script_path(puppet_script_path)

        # generate ospurge script
        if node.role != const.ROLE_NEUTRON_SERVER:
            return
        openrc = const.MANUAL_OPENRC
        if node.fuel_cluster_id:
            openrc = const.FUEL_OPENRC
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(ospurge_template_dir)s/%(ospurge_template)s.sh''' %
                  {'setup_node_dir'       : node.setup_node_dir,
                   'deploy_mode'          : node.deploy_mode,
                   'ospurge_template_dir' : const.OSPURGE_TEMPLATE_DIR,
                   'ospurge_template'     : "purge_all"}), "r") as ospurge_template_file:
            ospurge_template = ospurge_template_file.read()
            ospurge = (ospurge_template % {'openrc' : openrc})
        ospurge_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s_ospurge.sh''' %
                              {'setup_node_dir'       : node.setup_node_dir,
                               'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                               'hostname'             : node.hostname})
        with open(ospurge_script_path, "w") as ospurge_file:
            ospurge_file.write(ospurge)
        node.set_ospurge_script_path(ospurge_script_path)


    @staticmethod
    def generate_scripts_for_centos(node):

        # generate bash script
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(bash_template_dir)s/%(bash_template)s_%(os_version)s.sh''' %
                  {'setup_node_dir'    : node.setup_node_dir,
                   'deploy_mode'       : node.deploy_mode,
                   'bash_template_dir' : const.BASH_TEMPLATE_DIR,
                   'bash_template'     : const.CENTOS,
                   'os_version'        : node.os_version}), "r") as bash_template_file:
            bash_template = bash_template_file.read()
            is_controller = False
            if node.role == const.ROLE_NEUTRON_SERVER:
                is_controller = True
            bash = (bash_template %
                   {'install_ivs'         : str(node.install_ivs).lower(),
                    'install_bsnstacklib' : str(node.install_bsnstacklib).lower(),
                    'install_all'         : str(node.install_all).lower(),
                    'deploy_dhcp_agent'   : str(node.deploy_dhcp_agent).lower(),
                    'is_controller'       : str(is_controller).lower(),
                    'deploy_horizon_patch': str(node.deploy_horizon_patch).lower(),
                    'ivs_version'         : node.ivs_version,
                    'bsnstacklib_version' : node.bsnstacklib_version,
                    'dst_dir'             : node.dst_dir,
                    'hostname'            : node.hostname,
                    'ivs_pkg'             : node.ivs_pkg,
                    'horizon_patch'       : node.horizon_patch,
                    'horizon_patch_dir'   : node.horizon_patch_dir,
                    'horizon_base_dir'    : node.horizon_base_dir,
                    'ivs_debug_pkg'       : node.ivs_debug_pkg,
                    'ovs_br'              : node.get_all_ovs_brs(),
                    'bonds'               : node.get_all_bonds(),
                    'br-int'              : const.BR_NAME_INT})
        bash_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.sh''' %
                           {'setup_node_dir'       : node.setup_node_dir,
                            'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                            'hostname'             : node.hostname})
        with open(bash_script_path, "w") as bash_file:
            bash_file.write(bash)
        node.set_bash_script_path(bash_script_path)

        # generate puppet script
        ivs_daemon_args = (const.IVS_DAEMON_ARGS %
                          {'inband_vlan'       : const.INBAND_VLAN,
                           'internal_ports'    : node.get_ivs_internal_ports(),
                           'uplink_interfaces' : node.get_uplink_intfs_for_ivs()})
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(puppet_template_dir)s/%(puppet_template)s_%(role)s.pp''' %
                  {'setup_node_dir'      : node.setup_node_dir,
                   'deploy_mode'         : node.deploy_mode,
                   'puppet_template_dir' : const.PUPPET_TEMPLATE_DIR,
                   'puppet_template'     : const.CENTOS,
                   'role'                : node.role}), "r") as puppet_template_file:
            puppet_template = puppet_template_file.read()
            puppet = (puppet_template %
                     {'ivs_daemon_args'       : ivs_daemon_args,
                      'network_vlan_ranges'   : node.get_network_vlan_ranges(),
                      'bcf_controllers'       : node.get_controllers_for_neutron(),
                      'bcf_controller_user'   : node.bcf_controller_user,
                      'bcf_controller_passwd' : node.bcf_controller_passwd,
                      'selinux_mode'          : node.selinux_mode,
                      'port_ips'              : node.get_ivs_internal_port_ips()})
        puppet_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.pp''' %
                             {'setup_node_dir'       : node.setup_node_dir,
                              'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                              'hostname'             : node.hostname})
        with open(puppet_script_path, "w") as puppet_file:
            puppet_file.write(puppet)
        node.set_puppet_script_path(puppet_script_path)

        # generate selinux script
        selinux_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.te''' %
                              {'setup_node_dir'       : node.setup_node_dir,
                               'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                               'hostname'             : node.hostname})
        subprocess.call(r'''cp %(setup_node_dir)s/%(deploy_mode)s/%(selinux_template_dir)s/%(selinux_template)s.te %(selinux_script_path)s''' %
                       {'setup_node_dir'       : node.setup_node_dir,
                        'deploy_mode'          : node.deploy_mode,
                        'selinux_template_dir' : const.SELINUX_TEMPLATE_DIR,
                        'selinux_template'     : const.CENTOS,
                        'selinux_script_path'  : selinux_script_path}, shell=True)
        node.set_selinux_script_path(selinux_script_path)

        # generate ospurge script
        if node.role != const.ROLE_NEUTRON_SERVER:
            return
        openrc = const.PACKSTACK_OPENRC
        if node.fuel_cluster_id:
            openrc = const.FUEL_OPENRC
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(ospurge_template_dir)s/%(ospurge_template)s.sh''' %
                  {'setup_node_dir'       : node.setup_node_dir,
                   'deploy_mode'          : node.deploy_mode,
                   'ospurge_template_dir' : const.OSPURGE_TEMPLATE_DIR,
                   'ospurge_template'     : "purge_all"}), "r") as ospurge_template_file:
            ospurge_template = ospurge_template_file.read()
            ospurge = (ospurge_template % {'openrc' : openrc})
        ospurge_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s_ospurge.sh''' %
                              {'setup_node_dir'       : node.setup_node_dir,
                               'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                               'hostname'             : node.hostname})
        with open(ospurge_script_path, "w") as ospurge_file:
            ospurge_file.write(ospurge)
        node.set_ospurge_script_path(ospurge_script_path)
        


    @staticmethod
    def __load_node_yaml_config__(node_config, env):
        if 'role' not in node_config:
            node_config['role'] = env.role
        if 'skip' not in node_config:
            node_config['skip'] = env.skip
        if 'deploy_mode' not in node_config:
            node_config['deploy_mode'] = env.deploy_mode
        if 'os' not in node_config:
            node_config['os'] = env.os
        if 'os_version' not in node_config:
            node_config['os_version'] = env.os_version
        if 'user' not in node_config:
            node_config['user'] = env.user
        if 'passwd' not in node_config:
            node_config['passwd'] = env.passwd
        if 'uplink_interfaces' not in node_config:
            node_config['uplink_interfaces'] = env.uplink_interfaces
        if 'install_ivs' not in node_config:
            node_config['install_ivs'] = env.install_ivs
        if 'install_bsnstacklib' not in node_config:
            node_config['install_bsnstacklib'] = env.install_bsnstacklib
        if 'install_all' not in node_config:
            node_config['install_all'] = env.install_all
        if 'deploy_dhcp_agent' not in node_config:
            node_config['deploy_dhcp_agent'] = env.deploy_dhcp_agent
        return node_config


    @staticmethod
    def load_nodes_from_yaml(node_yaml_config_map, env):
        """
        Parse yaml file and return a dictionary
        """
        node_dic = {}
        if node_yaml_config_map == None:
            return node_dic
        for hostname, node_yaml_config in node_yaml_config_map.iteritems():
            node_yaml_config = Helper.__load_node_yaml_config__(node_yaml_config, env)

            # get existing ivs version
            node_yaml_config['old_ivs_version'] = None
            output,errors = Helper.run_command_on_remote_with_passwd_without_timeout(
                node_yaml_config['hostname'],
                node_yaml_config['user'],
                node_yaml_config['passwd'],
                'ivs --version')
            if errors or not output:
                node_yaml_config['skip'] = True
                node_yaml_config['error'] = ("Fail to retrieve ivs version from %(hostname)s" %
                                            {'hostname' : node_yaml_config['hostname']})
            if output and 'command not found' not in output:
                node_yaml_config['old_ivs_version'] = output.split()[1]

            node = Node(node_yaml_config, env)
            node_dic[node.hostname] = node
        return node_dic


    @staticmethod
    def __load_fuel_evn_setting__(fuel_cluster_id):
        try:
            Helper.safe_print("Retrieving general Fuel settings\n")
            cmd = (r'''fuel --json --env %(fuel_cluster_id)s settings -d''' %
                  {'fuel_cluster_id' : fuel_cluster_id})
            output, errors = Helper.run_command_on_local_without_timeout(cmd)
        except Exception as e:
            raise Exception("Error encountered trying to execute the Fuel CLI\n%(e)s\n"
                            % {'e' : e})
        if errors and 'DEPRECATION WARNING' not in errors:
            raise Exception("Error Loading cluster %(fuel_cluster_id)s\n%(errors)s\n"
                            % {'fuel_cluster_id' : str(fuel_cluster_id),
                               'errors'          : errors})
        try:
            path = output.split('downloaded to ')[1].rstrip()
        except (IndexError, AttributeError):
            raise Exception("Could not download fuel settings: %(output)s\n"
                            % {'output' : output})
        try:
            fuel_settings = json.loads(open(path, 'r').read())
        except Exception as e:
            raise Exception("Error parsing fuel json settings.\n%(e)s\n"
                            % {'e' : e})
        return fuel_settings


    @staticmethod
    def __load_fuel_node__(hostname, role, node_yaml_config, env):
        node_config = {}
        if node_yaml_config:
            node_config = Helper.__load_node_yaml_config__(node_yaml_config, env)
        else:
            node_config = Helper.__load_node_yaml_config__(node_config, env)
        node_config['hostname'] = hostname
        node_config['role'] = role

        # get node operating system information
        os_info, errors = Helper.run_command_on_remote_with_key_without_timeout(node_config['hostname'],
            'python -mplatform')
        if errors or (not os_info):
            Helper.safe_print("Error retrieving operating system info from node %(hostname)s:\n%(errors)s\n"
                              % {'hostname' : node_config['hostname'], 'errors' : errors})
            return None
        try:
            os_and_version = os_info.split('with-')[1].split('-')
            node_config['os'] = os_and_version[0]
            node_config['os_version'] = os_and_version[1]
        except Exception as e:
            Helper.safe_print("Error parsing node %(hostname)s operating system info:\n%(e)s\n"
                              % {'hostname' : node_config['hostname'], 'e' : e})
            return None

        # get node /etc/astute.yaml
        node_yaml, errors = Helper.run_command_on_remote_with_key_without_timeout(node_config['hostname'],
            'cat /etc/astute.yaml')
        if errors or not node_yaml:
            Helper.safe_print("Error retrieving config for node %(hostname)s:\n%(errors)s\n"
                              % {'hostname' : node_config['hostname'], 'errors' : errors})
            return None
        try:
            node_yaml_config = yaml.load(node_yaml)
        except Exception as e:
            Helper.safe_print("Error parsing node %(hostname)s yaml file:\n%(e)s\n"
                              % {'hostname' : node_config['hostname'], 'e' : e})
            return None

        # get existing ivs version
        node_config['old_ivs_version'] = None
        output, errors = Helper.run_command_on_remote_with_key_without_timeout(node_config['hostname'],
            'ivs --version')
        if errors or not output:
            Helper.safe_print("Error retrieving ivs version from node %(hostname)s:\n%(errors)s\n"
                              % {'hostname' : node_config['hostname'], 'errors' : errors})
            return None
        if 'command not found' not in output:
            node_config['old_ivs_version'] = output.split()[1]

        # physnet and vlan range
        physnets = node_yaml_config['quantum_settings']['L2']['phys_nets']
        for physnet, physnet_detail in physnets.iteritems():
            env.set_physnet(physnet)
            vlans = physnet_detail['vlan_range'].strip().split(':')
            env.set_lower_vlan(vlans[0])
            env.set_upper_vlan(vlans[1])
            # we deal with only the first physnet
            break

        # get bond bridge attached by br_prv
        roles = node_yaml_config['network_scheme']['roles']
        br_prv = roles[const.BR_KEY_PRIVATE]
        trans = node_yaml_config['network_scheme']['transformations']
        for tran in trans:
            if (tran['action'] != 'add-patch'):
                continue
            if (br_prv not in tran['bridges']):
                continue
            bridges = list(tran['bridges'])
            bridges.remove(br_prv)
            node_config['br_bond'] = bridges[0]
            break

        # get bond name
        for tran in trans:
            if (tran['action'] != 'add-bond'):
                continue
            if (node_config['br_bond'] != tran.get('bridge')):
                continue
            node_config['bond'] = tran['name']
            break

        # bond intfs
        for tran in trans:
            if (tran['action'] == 'add-bond'
                and tran['bridge'] == node_config['br_bond']):
                node_config['uplink_interfaces'] = tran['interfaces']
                break

        # get br-fw-admin information
        endpoints = node_yaml_config['network_scheme']['endpoints']
        node_config['br_fw_admin'] = roles[const.BR_KEY_FW_ADMIN]
        ip = endpoints[node_config['br_fw_admin']]['IP']
        if ip == const.NONE_IP:
            node_config['br_fw_admin_address'] = None
        else:
            node_config['br_fw_admin_address'] = ip[0]
        for tran in trans:
            if (tran['action'] != 'add-port'):
                continue
            if (tran.get('bridge') != node_config['br_fw_admin']):
                continue
            node_config['pxe_interface'] = tran['name']
            break

        # get bridge ip, vlan and construct bridge obj
        bridges = []
        bridge_names = []
        for br_key, br_name in roles.iteritems():
            if br_key in const.BR_KEY_EXCEPTION:
                continue

            vlan = None
            vendor_specific = endpoints[br_name].get('vendor_specific')
            if vendor_specific:
                vlan = vendor_specific.get('vlans')
            else:
                # we don't touch bridge without vendor_specific,
                # for example: br-floating
                continue

            phy_interfaces = vendor_specific.get('phy_interfaces')
            if not (set(node_config['uplink_interfaces']).issuperset(set(phy_interfaces)) and
                    set(phy_interfaces).issuperset(set(node_config['uplink_interfaces']))):
                # we don't touch the bridge which doesn't use bond
                continue

            ip = endpoints[br_name]['IP']
            if ip == const.NONE_IP:
                ip = None
            else:
                ip = ip[0]
            bridge = Bridge(br_key, br_name, ip, vlan)
            bridges.append(bridge)
            bridge_names.append(br_name)
        node_config['bridges'] = bridges

        # get non-bond, non-pxe interfaces,
        # will be most likely tagged
        tagged_intfs = []
        for tran in trans:
            if (tran['action'] != 'add-port'
                or tran['name'] == node_config['pxe_interface']
                or tran['bridge'] in bridge_names):
                    continue
            tagged_intfs.append(tran['name'])
        node_config['tagged_intfs'] = tagged_intfs

        node = Node(node_config, env)
        return node


    @staticmethod
    def load_nodes_from_fuel(node_yaml_config_map, env):
        fuel_settings = Helper.__load_fuel_evn_setting__(env.fuel_cluster_id)
        Helper.safe_print("Retrieving list of Fuel nodes\n")
        cmd = (r'''fuel nodes --env %(fuel_cluster_id)s''' %
              {'fuel_cluster_id' : str(env.fuel_cluster_id)})
        node_list, errors = Helper.run_command_on_local_without_timeout(cmd)
        if errors and 'DEPRECATION WARNING' not in errors:
            raise Exception("Error Loading node list %(fuel_cluster_id)s:\n%(errors)s\n"
                            % {'fuel_cluster_id' : env.fuel_cluster_id,
                               'errors'          : errors})

        node_dic = {}
        membership_rules = {}
        try:
            lines = [l for l in node_list.splitlines()
                     if '----' not in l and 'pending_roles' not in l]
            for line in lines:
                hostname = str(netaddr.IPAddress(line.split('|')[4].strip()))
                role = str(line.split('|')[6].strip())
                node_yaml_config = None
                node_yaml_config = node_yaml_config_map.get(hostname)
                node = Helper.__load_fuel_node__(hostname, role, node_yaml_config, env)
                if (not node) or (not node.hostname):
                    continue
                node_dic[node.hostname] = node
                
                # get node bridges
                for br in node.bridges:
                    if (not br.br_vlan) or (br.br_key == const.BR_KEY_PRIVATE):
                        continue
                    rule = MembershipRule(br.br_key, br.br_vlan,
                                          node.bcf_openstack_management_tenant)
                    membership_rules[rule.br_key] = rule

        except IndexError:
            raise Exception("Could not parse node list:\n%(node_list)s\n"
                            % {'node_list' : node_list})
        return node_dic, membership_rules


    @staticmethod
    def load_nodes(nodes_yaml_config, env):
        node_yaml_config_map = {}
        if nodes_yaml_config != None:
            for node_yaml_config in nodes_yaml_config:
                # we always use ip address as the hostname
                node_yaml_config['hostname'] = socket.gethostbyname(node_yaml_config['hostname'])
                node_yaml_config_map[node_yaml_config['hostname']] = node_yaml_config
        if env.fuel_cluster_id == None:
            return Helper.load_nodes_from_yaml(node_yaml_config_map, env)
        else:
            node_dic, membership_rules = Helper.load_nodes_from_fuel(node_yaml_config_map, env)
            # program membership rules to controller
            for br_key, rule in membership_rules.iteritems():
                RestLib.program_segment_and_membership_rule(env.bcf_master, env.bcf_cookie, rule,
                                                            env.bcf_openstack_management_tenant)
            return node_dic


    @staticmethod
    def common_setup_node_preparation(env):
        # clean up from previous installation
        setup_node_dir = os.getcwd()
        subprocess.call("rm -rf ~/.ssh/known_hosts", shell=True)
        subprocess.call("rm -rf %(log)s" %
                       {'log' : const.LOG_FILE}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.rpm" %
                       {'setup_node_dir' : setup_node_dir}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.deb" %
                       {'setup_node_dir' : setup_node_dir}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/*.tar.gz" %
                       {'setup_node_dir' : setup_node_dir}, shell=True)
        subprocess.call("mkdir -p %(setup_node_dir)s/%(generated_script)s" %
                       {'setup_node_dir'   : setup_node_dir,
                        'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/%(generated_script)s/*" %
                       {'setup_node_dir'   : setup_node_dir,
                        'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)

        # wget ivs packages
        code_web = 1
        code_local = 1
        for pkg_type, url in env.ivs_url_map.iteritems():
            if 'http://' in url or 'https://' in url:
                code_web = subprocess.call("wget --no-check-certificate %(url)s -P %(setup_node_dir)s" %
                                          {'url' : url, 'setup_node_dir' : setup_node_dir},
                                           shell=True)
        for pkg_type, url in env.ivs_url_map.iteritems():
            if os.path.isfile(url):
                code_local = subprocess.call("cp %(url)s %(setup_node_dir)s" %
                                            {'url' : url, 'setup_node_dir' : setup_node_dir},
                                             shell=True)
        if env.deploy_mode == const.T6 and code_web != 0 and code_local != 0:
            Helper.safe_print("Required ivs packages are not correctly downloaded.\n")
            exit(1)
        # TODO: deal with tarball

        # wget horizon patch
        code_web = 1
        code_local = 1
        url = env.horizon_patch_url
        if 'http://' in url or 'https://' in url:
            code_web = subprocess.call("wget --no-check-certificate %(url)s -P %(setup_node_dir)s" %
                                          {'url' : url, 'setup_node_dir' : setup_node_dir},
                                           shell=True)
        if os.path.isfile(url):
            code_local = subprocess.call("cp %(url)s %(setup_node_dir)s" %
                                        {'url' : url, 'setup_node_dir' : setup_node_dir},
                                         shell=True)
        if env.deploy_horizon_patch and code_web != 0 and code_local != 0:
            Helper.safe_print("Required horizon packages are not correctly downloaded.\n")
            exit(1)


    @staticmethod
    def run_command_on_remote(node, command):
        if node.fuel_cluster_id:
            Helper.run_command_on_remote_with_key(node, command)
        else:
            Helper.run_command_on_remote_with_passwd(node, command)


    @staticmethod
    def copy_file_from_remote(node, src_dir, src_file, dst_dir, mode=777):
        if node.fuel_cluster_id:
            Helper.copy_file_from_remote_with_key(node, src_dir, src_file, dst_dir, mode)
        else:
            Helper.copy_file_from_remote_with_passwd(node, src_dir, src_file, dst_dir, mode)


    @staticmethod
    def copy_file_to_remote(node, src_file, dst_dir, dst_file, mode=777):
        if node.fuel_cluster_id:
            Helper.copy_file_to_remote_with_key(node, src_file, dst_dir, dst_file, mode)
        else:
            Helper.copy_file_to_remote_with_passwd(node, src_file, dst_dir, dst_file, mode)


    @staticmethod
    def copy_pkg_scripts_to_remote(node):
        # copy ivs to node
        if node.deploy_mode == const.T6:
            Helper.safe_print("Copy %(ivs_pkg)s to %(hostname)s\n" %
                              {'ivs_pkg'  : node.ivs_pkg,
                               'hostname' : node.hostname})
            Helper.copy_file_to_remote(node,
                (r'''%(src_dir)s/%(ivs_pkg)s''' %
                {'src_dir' : node.setup_node_dir,
                 'ivs_pkg' : node.ivs_pkg}),
                node.dst_dir,
                node.ivs_pkg)
            if node.ivs_debug_pkg != None:
                Helper.safe_print("Copy %(ivs_debug_pkg)s to %(hostname)s\n" %
                                 {'ivs_debug_pkg'  : node.ivs_debug_pkg,
                                  'hostname'       : node.hostname})
                Helper.copy_file_to_remote(node,
                    (r'''%(src_dir)s/%(ivs_debug_pkg)s''' %
                    {'src_dir'       : node.setup_node_dir,
                     'ivs_debug_pkg' : node.ivs_debug_pkg}),
                    node.dst_dir,
                    node.ivs_debug_pkg)

        # copy bash script to node
        Helper.safe_print("Copy bash script to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote(node,
           node.bash_script_path,
           node.dst_dir,
           "%(hostname)s.sh" % {'hostname' : node.hostname})

        # copy puppet script to node
        Helper.safe_print("Copy puppet script to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote(node,
           node.puppet_script_path,
           node.dst_dir,
           "%(hostname)s.pp" % {'hostname' : node.hostname})

        # copy selinux script to node
        if node.os in const.RPM_OS_SET:
            Helper.safe_print("Copy bsn selinux policy to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote(node,
               node.selinux_script_path,
               node.dst_dir,
               "%(hostname)s.te" % {'hostname' : node.hostname})

        # copy ospurge script to node
        if node.role == const.ROLE_NEUTRON_SERVER:
            Helper.safe_print("Copy ospurge script to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote(node,
               node.ospurge_script_path,
               node.dst_dir,
               "%(hostname)s_ospurge.sh" % {'hostname' : node.hostname})

        # copy horizon patch to node
        if node.role == const.ROLE_NEUTRON_SERVER and node.deploy_horizon_patch:
            Helper.safe_print("Copy horizon patch to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote(node,
                (r'''%(src_dir)s/%(horizon_patch)s''' %
                {'src_dir' : node.setup_node_dir,
                 'horizon_patch' : node.horizon_patch}),
                node.dst_dir,
                node.horizon_patch)

        # copy rootwrap to remote
        if node.fuel_cluster_id:
            Helper.safe_print("Copy rootwrap to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote(node,
                (r'''%(src_dir)s/rootwrap''' %
                {'src_dir' : node.setup_node_dir}),
                node.dst_dir,
                "rootwrap")



