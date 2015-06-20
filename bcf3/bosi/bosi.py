import yaml
import Queue
import argparse
import threading
import lib.constants as const
import subprocess32 as subprocess
from lib.node import Node
from lib.helper import Helper
from lib.environment import Environment


# queue to store all nodes
node_q = Queue.Queue()

# data structure to setup dhcp agent and metadata agent
dhcp_node_q = Queue.Queue()


def worker_setup_node():
    while True:
        node = node_q.get()
        # copy ivs pkg to node
        Helper.copy_pkg_scripts_to_remote(node)

        # deploy node
        Helper.safe_print("Start to deploy %(hostname)s\n" %
                         {'hostname' : node.hostname})
        if node.cleanup and node.role == const.ROLE_NEUTRON_SERVER:
            Helper.run_command_on_remote(node,
                (r'''/bin/bash %(dst_dir)s/%(hostname)s_ospurge.sh >> %(log)s 2>&1''' %
                {'dst_dir'  : node.dst_dir,
                 'hostname' : node.hostname,
                 'log'      : node.log}))
        Helper.run_command_on_remote(node,
            (r'''/bin/bash %(dst_dir)s/%(hostname)s.sh >> %(log)s 2>&1''' %
            {'dst_dir'  : node.dst_dir,
             'hostname' : node.hostname,
             'log'      : node.log}))
        Helper.safe_print("Finish deploying %(hostname)s\n" %
                         {'hostname' : node.hostname})
        node_q.task_done()


def worker_setup_dhcp_agent():
    while True:
        node = dhcp_node_q.get()
        Helper.safe_print("Copy dhcp_agent.ini to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote(node, r'''%(dir)s/dhcp_agent.ini''' % {'dir' : node.setup_node_dir},
                                   '/etc/neutron', 'dhcp_agent.ini')
        Helper.safe_print("Copy metadata_agent.ini to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote(node, r'''%(dir)s/metadata_agent.ini''' % {'dir': node.setup_node_dir},
                                   '/etc/neutron', 'metadata_agent.ini')
        Helper.safe_print("Restart neutron-metadata-agent and neutron-dhcp-agent on %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.run_command_on_remote(node, 'service neutron-metadata-agent restart')
        Helper.run_command_on_remote(node, 'service neutron-dhcp-agent restart')
        Helper.safe_print("Finish deploying dhcp agent and metadata agent on %(hostname)s\n" %
                         {'hostname' : node.hostname})
        dhcp_node_q.task_done()


def deploy_bcf(config, fuel_cluster_id, tag, cleanup):
    # Deploy setup node
    Helper.safe_print("Start to prepare setup node\n")
    env = Environment(config, fuel_cluster_id, tag, cleanup)
    Helper.common_setup_node_preparation(env)
    controller_node = None

    # Generate detailed node information
    Helper.safe_print("Start to setup Big Cloud Fabric\n")
    nodes_config = None
    if 'nodes' in config:
        nodes_yaml_config = config['nodes']
    node_dic = Helper.load_nodes(nodes_yaml_config, env)

    # Generate scripts for each node
    for hostname, node in node_dic.iteritems():
        if node.os == const.CENTOS:
            Helper.generate_scripts_for_centos(node)
        elif node.os == const.UBUNTU:
            Helper.generate_scripts_for_ubuntu(node)
        with open(const.LOG_FILE, "a") as log_file:
            log_file.write(str(node))
        if node.skip:
            Helper.safe_print("skip node %(hostname)s due to %(error)s\n" %
                             {'hostname' : hostname,
                              'error'    : node.error})
            continue
        if node.tag != node.env_tag:
            Helper.safe_print("skip node %(hostname)s due to mismatched tag\n" %
                             {'hostname' : hostname})
            continue
        node_q.put(node)

        if node.role == const.ROLE_NEUTRON_SERVER:
            controller_node = node
        elif node.deploy_dhcp_agent:
            dhcp_node_q.put(node)

    # Use multiple threads to setup nodes
    for i in range(const.MAX_WORKERS):
        t = threading.Thread(target=worker_setup_node)
        t.daemon = True
        t.start()
    node_q.join()

    # Use multiple threads to setup up dhcp agent and metadata agent
    if controller_node:
        Helper.safe_print("Copy dhcp_agent.ini from openstack controller %(controller_node)s\n" %
                         {'controller_node' : controller_node.hostname})
        Helper.copy_file_from_remote(controller_node, '/etc/neutron', 'dhcp_agent.ini',
                                     controller_node.setup_node_dir)
        Helper.safe_print("Copy metadata_agent.ini from openstack controller %(controller_node)s\n" %
                         {'controller_node' : controller_node.hostname})
        Helper.copy_file_from_remote(controller_node, '/etc/neutron', 'metadata_agent.ini',
                                     controller_node.setup_node_dir)
    for i in range(const.MAX_WORKERS):
        t = threading.Thread(target=worker_setup_dhcp_agent)
        t.daemon = True
        t.start()
    dhcp_node_q.join()

    Helper.safe_print("Big Cloud Fabric deployment finished! Check %(log)s on each node for details.\n" %
                     {'log' : const.LOG_FILE})


if __name__=='__main__':

    # Check if network is working properly
    code = subprocess.call("ping www.bigswitch.com -c1", shell=True)
    if code != 0:
        Helper.safe_print("Network is not working properly, quit deployment\n")
        exit(1)

    # Parse configuration
    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True,
                        help="BCF YAML configuration file")
    parser.add_argument('-f', "--fuel-cluster-id", required=False,
                        help="Fuel cluster ID. Fuel settings may override YAML configuration. Please refer to config.yaml")
    parser.add_argument('-t', "--tag", required=False,
                        help="Deploy to tagged nodes only.")
    parser.add_argument('--cleanup', action='store_true', default=False,
                        help="Clean up existing routers, networks and projects.")
    args = parser.parse_args()
    with open(args.config_file, 'r') as config_file:
        config = yaml.load(config_file)
    deploy_bcf(config, args.fuel_cluster_id, args.tag, args.cleanup)



