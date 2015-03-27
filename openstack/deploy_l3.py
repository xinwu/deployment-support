# Copyright 2014 Big Switch Networks, Inc.
# All Rights Reserved.
#
# @author: Kanzhe Jiang
import argparse
import collections
import json
import netaddr
import os
import subprocess
import threading
import urllib2
try:
    import yaml
except:
    pass

# Arbitrary identifier printed in output to make tracking easy
BRANCH_ID = 'master'
SCRIPT_VERSION = '1.0'

# Maximum number of threads to deploy to nodes concurrently
MAX_THREADS = 20

CONF_DIR = "neutron-conf"


class TimedCommand(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None
        self.retries = 0
        self.resp = None
        self.errors = None

    def run(self, timeout=60, retries=0, shell=False):
        # if shell is True, the incoming command is expected to be a string
        # that has been properly escaped.
        def target():
            try:
                self.process = subprocess.Popen(
                    self.cmd, stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE, shell=shell)
            except Exception as e:
                self.errors = 'Error opening process "%s": %s' % (self.cmd, e)
                return
            self.resp, self.errors = self.process.communicate()

        thread = threading.Thread(target=target)
        thread.start()

        thread.join(timeout)
        if thread.is_alive():
            self.process.terminate()
            thread.join()
            if self.retries < retries:
                self.retries += 1
                return self.run(timeout, retries)
            self.errors = (
                "Timed out waiting for command '%s' to finish." % self.cmd)

        return self.resp, self.errors


class Environment(object):

    nodes = []
    bigswitch_auth = None
    bigswitch_servers = None
    neutron_id = 'neutron'
    extra_template_params = {}
    offline_mode = False
    check_interface_errors = True
    debug = False
    bond_mode = 2

    def run_command_on_node(self, node, command, timeout=60, retries=0, shell=False):
        raise NotImplementedError()

    def copy_file_to_node(self, node, local_path, remote_path):
        raise NotImplementedError()


class SSHEnvironment(Environment):
    # shared SSH stuff for config based deployments and fuel deployments

    def __init__(self, *args, **kwargs):
        self.ssh_user = 'root'
        self.ssh_password = None
        self.sshpass_detected = False
        super(SSHEnvironment, self).__init__(*args, **kwargs)

    def copy_file_to_node(self, node, local_path, remote_path):
        sshcomm = ["scp", '-o LogLevel=quiet', local_path,
                   "%s@%s:%s" % (self.ssh_user, node, remote_path)]
        if self.ssh_password:
            sshcomm = ['sshpass', '-p', self.ssh_password] + sshcomm
        resp, errors = TimedCommand(sshcomm).run(timeout=180)
        return resp, errors

    def run_command_on_node(self, node, command, timeout=60, retries=0,
                            shell=False):
        if self.debug:
            print "[Node %s] Running command: %s" % (node, command)
        sshcomm = [
            "ssh", '-oStrictHostKeyChecking=no',
            '-o LogLevel=quiet', "%s@%s" % (self.ssh_user, node),
            command
        ]
        if self.ssh_password:
            sshcomm = ['sshpass', '-p', self.ssh_password] + sshcomm
            if not self.sshpass_detected:
                # we need to see if sshpass is installed
                resp, errors = TimedCommand(['sshpass', '-h']).run()
                if errors:
                    raise Exception(
                        "Error running 'sshpass'. 'sshpass' must be installed "
                        "to use password based authentication.\n%s" % errors)
                self.sshpass_detected = True
        if shell:
            sshcomm = ' '.join(sshcomm)
        self.ensure_connectivity(node)
        resp, errors = TimedCommand(sshcomm).run(timeout, retries, shell=shell)
        return resp, errors

    def ensure_connectivity(self, node):
        # This might be worth caching if many SSH calls are made to each node.
        sshcomm = [
            "ssh", '-oStrictHostKeyChecking=no',
            "%s@%s" % (self.ssh_user, node),
            "echo hello"
        ]
        if self.ssh_password:
            sshcomm = ['sshpass', '-p', self.ssh_password] + sshcomm
        resp, errors = TimedCommand(sshcomm).run(60, 4)
        if "Permission denied, please try again." in errors:
            raise Exception(
                "Error: Received permission error on node %s. Verify that "
                "the SSH password is correct or that the ssh key being used is "
                "authorized on that host.")
        if not resp.strip() and errors:
            print ("Warning: Errors when checking SSH connectivity for node "
                   "%s:\n%s" % (node, errors))


class ConfigEnvironment(SSHEnvironment):

    network_vlan_ranges = None

    def __init__(self, yaml_string, skip_nodes=[], specific_nodes=[]):
        super(ConfigEnvironment, self).__init__()
        try:
            self.settings = yaml.load(yaml_string)
        except Exception as e:
            raise Exception("Error loading from yaml file:\n%s" % e)
        if not isinstance(self.settings.get('nodes'), list):
            raise Exception("Missing nodes in yaml data.\n%s" % self.settings)

        try:
            self.nodes = [n['hostname'] for n in self.settings['nodes']
                          if n['hostname'] not in skip_nodes and
                          (not specific_nodes or
                           n['hostname'] in specific_nodes)]
        except KeyError:
            raise Exception('missing hostname in nodes %s'
                            % self.settings['nodes'])


class FuelEnvironment(SSHEnvironment):

    def __init__(self, environment_id, skip_nodes=[], specific_nodes=[]):
        self.node_settings = {}
        self.nodes = []
        self.settings = {}
        super(FuelEnvironment, self).__init__()
        try:
            print "Retrieving general Fuel settings..."
            output, errors = TimedCommand(
                ["fuel", "--json", "--env", str(environment_id),
                 "settings", "-d"]).run()
        except Exception as e:
            raise Exception("Error encountered trying to execute the Fuel "
                            "CLI:\n%s" % e)
        if errors:
            raise Exception("Error Loading cluster %s:\n%s"
                            % (environment_id, errors))
        try:
            path = output.split('downloaded to ')[1].rstrip()
        except (IndexError, AttributeError):
            raise Exception("Could not download fuel settings: %s"
                            % output)
        try:
            self.settings = json.loads(open(path, 'r').read())
        except Exception as e:
            raise Exception("Error parsing fuel json settings.\n%s" % e)

        # grab list of hosts
        print "Retrieving list of Fuel nodes..."
        output, errors = TimedCommand(
            ["fuel", "nodes", "--env", str(environment_id)]).run()
        if errors:
            raise Exception("Error Loading node list %s:\n%s"
                            % (environment_id, errors))
        try:
            lines = [l for l in output.splitlines()
                     if '----' not in l and 'pending_roles' not in l]
            nodes = [str(netaddr.IPAddress(l.split('|')[4].strip()))
                     for l in lines]
            self.nodes = [n for n in nodes if n not in skip_nodes and
                          (not specific_nodes or n in specific_nodes)]
            print "Nodes to configure: %s" % self.nodes
        except IndexError:
            raise Exception("Could not parse node list:\n%s" % output)
        for node in self.nodes:
            self.node_settings[node] = self.get_node_config(node)

    def get_node_config(self, node):
        print "Retrieving Fuel configuration for node %s..." % node
        resp, errors = self.run_command_on_node(node, 'cat /etc/astute.yaml')
        if errors or not resp:
            raise Exception("Error retrieving config for node %s:\n%s\n"
                            "Is the node online?"
                            % (node, errors))
        try:
            conf = yaml.load(resp)
        except Exception as e:
            raise Exception("Error parsing node yaml file:\n%s\n%s"
                            % (e, resp))
        return conf


class StandaloneEnvironment(Environment):

    def __init__(self):
        self.nodes = ['localhost']

    def copy_file_to_node(self, node, local_path, remote_path):
        resp, errors = TimedCommand(
            ['bash', '-lc', "cp %s %s" % (local_path, remote_path)]).run()
        return resp, errors

    def run_command_on_node(self, node, command, timeout=60, retries=0,
                            shell=False):
        resp, errors = TimedCommand(['bash', '-lc', command]).run(timeout,
                                                                  retries)
        return resp, errors


class ConfigDeployer(object):
    def __init__(self, environment):
        self.env = environment

    def deploy_to_all(self):
        thread_list = collections.deque()
        errors = []
        nodes_information = []
        for node in self.env.nodes:
            t = threading.Thread(target=self.deploy_to_node_catch_errors,
                                 args=(node, errors, nodes_information))
            thread_list.append(t)
            t.start()
            if len(thread_list) >= MAX_THREADS:
                top = thread_list.popleft()
                top.join()
        for thread in thread_list:
            thread.join()
        # sanity checks across collected info
        # make sure neutron servers are all pointing to the same DB
        conn_strings = [info['neutron_connection']
                        for (node, info) in nodes_information
                        if info.get('neutron_connection')]
        if len(set(conn_strings)) > 1:
            strings_with_nodes = ["%s: %s" % (node, info['neutron_connection'])
                                  for (node, info) in nodes_information
                                  if info.get('neutron_connection')]
            print ("Warning: different neutron connection strings detected on "
                   "neutron server nodes. They should all reference the same "
                   "database.\nConnections:\n%s" % "\n".join(strings_with_nodes))

        if errors:
            print "Encountered errors while deploying patch to nodes."
            for node, error in errors:
                print "Error on node %s:\n%s" % (node, error)
        else:
            print "Deployment Complete!"

    def deploy_to_node_catch_errors(self, node, error_log, nodes_information):
        try:
            self.deploy_to_node(node, nodes_information)
        except Exception as e:
            error_log.append((node, str(e)))


    def deploy_to_node(self, node, nodes_information):
        print "Applying configuration to %s..." % node

        self.push_conf_to_node(node)

        # run a few last sanity checks
        self.check_rabbit_cluster_partition_free(node)

        # aggregate node information to compare across other nodes
        node_info = {}
        # collect connection string for comparison with other neutron servers
        connection_string = self.get_neutron_connection_string(node)
        if connection_string:
            node_info['neutron_connection'] = connection_string
        nodes_information.append((node, node_info))
        print "Configuration applied to %s." % node

    def push_conf_to_node(self, node):
        # pushes a neutron conf file to nodes
        self.env.run_command_on_node(node, "apt-get install -y neutron-l3-agent")
        for f in ('neutron.conf', 'l3_agent.ini'):
            remotefile = '/etc/neutron/%s' % f
            localfile = '/'.join((CONF_DIR, f))
            resp, errors = self.env.copy_file_to_node(node, localfile, remotefile)
            if errors:
                raise Exception("error pushing puppet manifest to %s:\n%s"
                                % (node, errors))
        self.env.run_command_on_node(node, "service neutron-l3-agent restart")

    def check_rabbit_cluster_partition_free(self, node):
        self.env.run_command_on_node(node, "service rabbitmq-server start")
        resp, errors = self.env.run_command_on_node(
            node, ("rabbitmqctl cluster_status | grep partitions | " +
                   r"""grep -v '\[\]'"""))
        if 'partitions' in resp:
            self.env.run_command_on_node(node, "rabbitmqctl stop_app")
            self.env.run_command_on_node(node, "rabbitmqctl start_app")
            resp, errors = self.env.run_command_on_node(
                node, ("rabbitmqctl cluster_status | grep partitions | " +
                       r"""grep -v '\[\]'"""))
            if 'partitions' in resp:
                print ("Warning: RabbitMQ partition detected on node %s: %s "
                       "Restart rabbitmq-server on each node in the parition."
                       % (node, resp))

    def get_neutron_connection_string(self, node):
        neutron_running = self.env.run_command_on_node(
            node, 'ps -ef | grep neutron-server | grep -v grep')[0].strip()
        if neutron_running:
            resp = self.env.run_command_on_node(
                node, ("grep -R -e '^connection' /etc/neutron/neutron.conf")
            )[0].strip()
            if resp:
                return resp.replace(' ', '')


if __name__ == '__main__':
    print "Deploy_L3 Version %s:%s" % (BRANCH_ID, SCRIPT_VERSION)
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-i", "--stand-alone", action='store_true',
                       help="Configure the server running this script "
                            "(root privileges required).")
    group.add_argument("-f", "--fuel-environment",
                       help="Fuel environment ID to load node settings from.")
    group.add_argument("-c", "--config-file", type=argparse.FileType('r'),
                       help="Path to YAML config file for "
                            "non-Fuel deployments.")
    parser.add_argument('--debug', action='store_true',
                        help="Show commands being executed on nodes.")
    remote = parser.add_argument_group('remote-deployment')
    remote.add_argument('--skip-nodes',
                        help="Comma-separate list of nodes to skip deploying "
                             "configurations to.")
    remote.add_argument('--specific-nodes',
                        help="Comma-separate list of nodes to deploy to. All "
                             "others will be skipped.")
    remote.add_argument('--ssh-user', default='root',
                        help="User to use when connecting to remote nodes "
                             "via SSH. Default is 'root'.")
    remote.add_argument('--ssh-password', default=None,
                        help="Password to use when connecting to remote nodes "
                             "via SSH. By default no password is used under "
                             "the assumption that SSH keys are setup.")
    args = parser.parse_args()
    if args.specific_nodes:
        specific_nodes = args.specific_nodes.split(',')
    else:
        specific_nodes = []
    if args.skip_nodes:
        skip_nodes = args.skip_nodes.split(',')
    else:
        skip_nodes = []

    for f in ('neutron.conf', 'l3_agent.ini'):
        if not os.path.isfile("/".join((CONF_DIR, f))):
            print ("ERROR: configuration file %s is missing" %
                   "/".join((CONF_DIR, f)))
            exit()

    if args.fuel_environment:
        environment = FuelEnvironment(args.fuel_environment,
                                      skip_nodes=skip_nodes,
                                      specific_nodes=specific_nodes)
    elif args.config_file:
        environment = ConfigEnvironment(args.config_file.read(),
                                        skip_nodes=skip_nodes,
                                        specific_nodes=specific_nodes)
    else:
        parser.error('You must specify the Fuel environment or the config '
                     'file.')
    if not args.stand_alone:
        environment.ssh_user = args.ssh_user
        environment.ssh_password = args.ssh_password
    environment.debug = args.debug
    deployer = ConfigDeployer(environment)
    deployer.deploy_to_all()
