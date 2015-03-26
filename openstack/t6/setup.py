import os
import re
import yaml
import Queue
import argparse
import threading
import lib.constants as const
from lib.helper import Helper
import subprocess32 as subprocess
from lib.clean_helper import CleanHelper
from lib.configuration import Node, Environment

# queue to store all nodes
node_q = Queue.Queue()


def worker_setup_node():
    while True:
        node = node_q.get()
        if node.user != None and node.passwd != None:
            # copy ivs pkg to node
            Helper.safe_print("Copy %(ivs_pkg)s to %(hostname)s\n" %
                              {'ivs_pkg'  : node.ivs_pkg,
                               'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
                (r'''%(src_dir)s/%(ivs_pkg)s''' %
                {'src_dir' : node.setup_node_dir,
                 'ivs_pkg' : node.ivs_pkg}),
                node.dst_dir,
                node.ivs_pkg)
            if node.ivs_debug_pkg != None:
                Helper.safe_print("Copy %(ivs_debug_pkg)s to %(hostname)s\n" %
                                 {'ivs_debug_pkg'  : node.ivs_debug_pkg,
                                  'hostname'       : node.hostname})
                Helper.copy_file_to_remote_with_passwd(node,
                    (r'''%(src_dir)s/%(ivs_debug_pkg)s''' %
                    {'src_dir'       : node.setup_node_dir,
                     'ivs_debug_pkg' : node.ivs_debug_pkg}),
                    node.dst_dir,
                    node.ivs_debug_pkg)
            # copy bash script to node
            Helper.safe_print("Copy bash script to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
               node.bash_script_path,
               node.dst_dir,
               "%(hostname)s.sh" % {'hostname' : node.hostname})
            # copy puppet script to node
            Helper.safe_print("Copy puppet script to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
               node.puppet_script_path,
               node.dst_dir,
               "%(hostname)s.pp" % {'hostname' : node.hostname})
            # copy selinux script to node
            Helper.safe_print("Copy bsn selinux policy to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
               node.selinux_script_path,
               node.dst_dir,
               "%(hostname)s.te" % {'hostname' : node.hostname})
            # deploy node
            Helper.safe_print("Start to deploy %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.run_command_on_remote_with_passwd(node,
                (r'''/bin/bash %(dst_dir)s/%(hostname)s.sh >> %(log)s 2>&1''' %
                {'dst_dir'  : node.dst_dir,
                 'hostname' : node.hostname,
                 'log'      : node.log}))
            Helper.safe_print("Finish deploying %(hostname)s\n" %
                             {'hostname' : node.hostname})
        node_q.task_done()


def load_bcf_config(config, env):
    """
    Parse yaml file and return a dictionary
    """
    node_dic = {}
    for node_config in config['nodes']:
        if 'os' not in node_config:
            node_config['os'] = config['default_os']
        if 'os_version' not in node_config:
            node_config['os_version'] = config['default_os_version']
        if 'bsnstacklib_version' not in node_config:
            node_config['bsnstacklib_version'] = config['default_bsnstacklib_version']
        if 'user' not in node_config:
            node_config['user'] = config['default_user']
        if 'passwd' not in node_config:
            node_config['passwd'] = config['default_passwd']
        if 'role' not in node_config:
            node_config['role'] = config['default_role']
        if 'uplink_interfaces' not in node_config:
            node_config['uplink_interfaces'] = config['default_uplink_interfaces']
        node = Node(node_config, env)
        node_dic[node.hostname] = node
    return node_dic


def generate_scripts_for_centos(node):
    # generate bash script
    with open((r'''%(setup_node_dir)s/%(bash_template_dir)s/%(bash_template)s_%(os_version)s.sh''' %
              {'setup_node_dir'    : node.setup_node_dir,
               'bash_template_dir' : const.BASH_TEMPLATE_DIR,
               'bash_template'     : const.CENTOS,
               'os_version'        : node.os_version}), "r") as bash_template_file:
        bash_template = bash_template_file.read()
        bash = (bash_template %
               {'bsnstacklib_version' : node.bsnstacklib_version,
                'dst_dir'             : node.dst_dir,
                'hostname'            : node.hostname, 
                'ivs_pkg'             : node.ivs_pkg,
                'ivs_debug_pkg'       : node.ivs_debug_pkg})
    bash_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.sh''' %
                       {'setup_node_dir'       : node.setup_node_dir,
                        'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                        'hostname'             : node.hostname})
    with open(bash_script_path, "w") as bash_file:
        bash_file.write(bash)
    node.set_bash_script_path(bash_script_path)

    # generate puppet script
    ivs_daemon_args = (const.IVS_DAEMON_ARGS %
                      {'inband_vlan' : const.INBAND_VLAN,
                       'uplink_interfaces' : node.uplink_interfaces})
    with open((r'''%(setup_node_dir)s/%(puppet_template_dir)s/%(puppet_template)s_%(role)s.pp''' %
              {'setup_node_dir'      : node.setup_node_dir,
               'puppet_template_dir' : const.PUPPET_TEMPLATE_DIR,
               'puppet_template'     : const.CENTOS,
               'role'                : node.role}), "r") as puppet_template_file:
        puppet_template = puppet_template_file.read()
        puppet = (puppet_template %
                 {'ivs_daemon_args'       : ivs_daemon_args,
                  'network_vlan_ranges'   : node.network_vlan_ranges,
                  'bcf_controllers'       : node.bcf_controllers,
                  'bcf_controller_user'   : node.bcf_controller_user,
                  'bcf_controller_passwd' : node.bcf_controller_passwd,
                  'selinux_mode'          : node.selinux_mode})
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
    subprocess.call(r'''cp %(setup_node_dir)s/%(selinux_template_dir)s/%(selinux_template)s.te %(selinux_script_path)s''' %
                    {'setup_node_dir'       : node.setup_node_dir,
                     'selinux_template_dir' : const.SELINUX_TEMPLATE_DIR,
                     'selinux_template'     : const.CENTOS,
                     'selinux_script_path'    : selinux_script_path}, shell=True)
    node.set_selinux_script_path(selinux_script_path)


def deploy_by_bcf_config(config):
    # Deploy setup node
    Helper.safe_print("Start to prepare setup node\n")
    setup_node_dir = os.getcwd()
    subprocess.call("rm -rf ~/.ssh/known_hosts", shell=True)
    subprocess.call("rm -rf %(log)s" %
                    {'log' : const.LOG_FILE}, shell=True)
    subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.rpm" %
                    {'setup_node_dir' : setup_node_dir}, shell=True)
    subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.deb" %
                    {'setup_node_dir' : setup_node_dir}, shell=True)
    subprocess.call("mkdir -p %(setup_node_dir)s/%(generated_script)s" %
                    {'setup_node_dir'   : setup_node_dir,
                     'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)
    subprocess.call("rm -rf %(setup_node_dir)s/%(generated_script)s/*" %
                    {'setup_node_dir'   : setup_node_dir,
                     'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)
    code_web = 1
    code_local = 1
    for package in config['ivs_packages']:
        url = package['package']
        if 'http://' in url or 'https://' in url:
            code_web = subprocess.call("wget --no-check-certificate %(url)s -P %(setup_node_dir)s" %
                                      {'url' : url, 'setup_node_dir' : setup_node_dir},
                                       shell=True)
    for package in config['ivs_packages']:
        url = package['package']
        if os.path.isfile(url):
            code_local = subprocess.call("cp %(url)s %(setup_node_dir)s" %
                                        {'url' : url, 'setup_node_dir' : setup_node_dir},
                                         shell=True)
    if code_web != 0 and code_local != 0:
        Helper.safe_print("Required packages are not correctly downloaded.\n")
        exit(1)

    # Generate detailed node information
    Helper.safe_print("Start to setup Big Cloud Fabric\n")
    setup_node_ip = Helper.get_setup_node_ip()
    selinux_mode_match = re.compile(const.SELINUX_MODE_EXPRESSION, re.IGNORECASE)
    selinux_mode = None
    with open(const.SELINUX_CONFIG_PATH, "r") as selinux_config_file:
        lines = selinux_config_file.readlines()
        for line in lines:
            match = selinux_mode_match.match(line)
            if match:
                selinux_mode = match.group(1)
    env = Environment(config, setup_node_ip, setup_node_dir, selinux_mode)
    existing_vlan_range_pattern = re.compile(const.EXISTING_VLAN_RANGE_EXPRESSION, re.IGNORECASE)
    with open(const.VLAN_RANGE_CONFIG_PATH, "r") as vlan_range_file:
        lines = vlan_range_file.readlines()
        for line in lines:
            match = existing_vlan_range_pattern.match(line)
            if match:
                existing_phynet = match.group(1)
                existing_lower_vlan = match.group(2)
                existing_upper_vlan = match.group(3)
                if env.physnet != existing_phynet:
                    Helper.safe_print("physnet does not match with exiting ml2_conf.ini.\n")
                    exit(1)
                if env.lower_vlan > existing_lower_vlan:
                    Helper.safe_print("lower vlan range is larger than exiting lower vlan range in ml2_conf.ini.\n")
                    exit(1)
                if env.upper_vlan < existing_upper_vlan:
                    Helper.safe_print("upper vlan range is smaller than exiting upper vlan range in ml2_conf.ini.\n")
                    exit(1)
                break
    node_dic = load_bcf_config(config, env)
    
    # Check if setup node is one of the neutron nodes
    setup_node = node_dic[setup_node_ip]
    if setup_node.role != const.ROLE_NEUTRON_SERVER:
        Helper.safe_print("Setup node %(setup_node)s needs to be a neutron server.\n" %
                         {'setup_node' : setup_node_ip})
        exit(1)

    # clean up network resources created by openstack installation
    #cleaner = CleanHelper()
    #cleaner.delete_ovs_agents()
    #cleaner.delete_non_bcf_projects_neutron_resources()

    # Generate scripts for each node
    for hostname, node in node_dic.iteritems():
        if node.os == const.CENTOS:
            generate_scripts_for_centos(node)
        with open(const.LOG_FILE, "a") as log_file:
            log_file.write(str(node))
        node_q.put(node)

    # Use multiple threads to setup nodes
    for i in range(const.MAX_WORKERS):
        t = threading.Thread(target=worker_setup_node)
        t.daemon = True
        t.start()
    node_q.join()
    Helper.safe_print("Big Cloud Fabric deployment finished!\n")


def deploy_by_fuel_config(config):
    pass


if __name__=='__main__':

    # Check if network is working properly
    code = subprocess.call("ping www.bigswitch.com -c1", shell=True)
    if code != 0:
        Helper.safe_print("Network is not working properly, quit deployment\n")
        exit(1)

    # Parse configuration
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True,
                        help="OpenStack YAML configuration file")
    parser.add_argument('-f', "--fuel-format", action='store_true',
                        default=False, help="YAML file is generated by Fuel")
    args = parser.parse_args()
    with open(args.config_file, 'r') as config_file:
        config = yaml.load(config_file)

    if not args.fuel_format:
        deploy_by_bcf_config(config)
    else:
        deploy_by_fuel_config(config)

