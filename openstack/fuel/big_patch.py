# Copyright 2014 Big Switch Networks, Inc.
# All Rights Reserved.
#
# @author: Kevin Benton
import argparse
import json
import netaddr
import os
import tempfile
import subprocess
import threading
import urllib2

# each entry is a 3-tuple naming the python package,
# the relative path inside the package, and the source URL
PYTHON_FILES_TO_PATCH = [
    ('neutron', 'plugins/bigswitch/plugin.py',
     'https://raw.githubusercontent.com/bigswitch/neutron/'
     'stable/icehouse/neutron/plugins/bigswitch/plugin.py'),
    ('neutron', 'plugins/bigswitch/servermanager.py',
     'https://raw.githubusercontent.com/bigswitch/neutron/'
     'stable/icehouse/neutron/plugins/bigswitch/servermanager.py'),
]

# path to neutron tar.gz for CentOS nodes
NEUTRON_TGZ_URL = ('https://github.com/bigswitch/neutron/archive/'
                   'stable/icehouse.tar.gz')


class TimedCommand(object):
    def __init__(self, cmd):
        self.cmd = cmd
        self.process = None
        self.retries = 0
        self.resp = None
        self.errors = None

    def run(self, timeout=60, retries=0):
        def target():
            self.process = subprocess.Popen(
                self.cmd, stdout=subprocess.PIPE,
                stderr=subprocess.PIPE)
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
            self.errors = "Timed out waiting for command to finish."

        return self.resp, self.errors


class Environment(object):

    nodes = []
    bigswitch_auth = None
    bigswitch_servers = None

    def run_command_on_node(self, node, command, timeout=60, retries=0):
        raise NotImplementedError()

    def copy_file_to_node(self, node, local_path, remote_path):
        raise NotImplementedError()

    @property
    def network_vlan_ranges(self):
        raise NotImplementedError()

    def get_node_bond_interfaces(self, node):
        raise NotImplementedError()

    # where the physical interfaces should be added
    def get_node_phy_bridge(self, node):
        raise NotImplementedError()

    # associations of physnets to bridges
    def get_node_bridge_mappings(self, node):
        raise NotImplementedError()

    def set_bigswitch_servers(self, servers):
        for s in servers.split(','):
            try:
                int(s.split(':')[1])
            except:
                raise Exception('Invalid server "%s".\n'
                                'Format should be ip:port' % s)
        self.bigswitch_servers = servers

    def set_bigswitch_auth(self, auth):
        if ':' not in auth:
            raise Exception('Invalid credentials "%s".\n'
                            'Format should be user:pass' % auth)
        self.bigswitch_auth = auth

    def get_node_python_package_path(self, node, package):
        com = ('python -c "import %s;import os;print '
               'os.path.dirname(%s.__file__)"'
               % (package, package))
        resp, errors = self.run_command_on_node(node, com)
        if errors or not resp.strip() or len(resp.strip().splitlines()) > 1:
            if 'ImportError' in errors:
                return False
            raise Exception("Error retrieving path to pyhon package '%s' on "
                            "node '%s'.\n%s\n%s" % (package, node,
                                                    errors, resp))
        return resp.strip()


class ConfigEnvironment(Environment):

    network_vlan_ranges = None

    def __init__(self, yaml_string, skip_nodes=[], specific_nodes=[]):
        import yaml
        try:
            self.settings = yaml.load(yaml_string)
        except Exception as e:
            raise Exception("Error loading from yaml file:\n%s" % e)
        if not isinstance(self.settings.get('nodes'), list):
            raise Exception("Missing nodes in yaml data.\n%s" % self.settings)
        if not self.settings.get('network_vlan_ranges'):
            raise Exception('Missing network_vlan_ranges in config.\n%s'
                            % self.settings)
        self.network_vlan_ranges = self.settings.get('network_vlan_ranges')
        try:
            self.nodes = [n['hostname'] for n in self.settings['nodes']
                          if n['hostname'] not in skip_nodes and
                          (not specific_nodes or
                           n['hostname'] in specific_nodes)]
        except KeyError:
            raise Exception('missing hostname in nodes %s'
                            % self.settings['nodes'])

    def get_node_bond_interfaces(self, node):
        for n in self.settings['nodes']:
            if n['hostname'] == node:
                return [i for i in n.get('bond_interfaces', '').split(',')
                        if i]
        print 'Node %s has no bond interfaces.' % node
        return []

    def get_node_bridge_mappings(self, node):
        br_mappings = None
        for n in self.settings['nodes']:
            if n['hostname'] == node:
                br_mappings = n.get('bridge_mappings')
        if not br_mappings:
            raise Exception('Node %s is missing bridge_mappings '
                            'which is required for the OVS agent.'
                            % node)
        cleaned = []
        for m in br_mappings.rstrip(',').split(','):
            if len(m.split(':')) != 2:
                raise Exception('Invalid bridge_mappings setting for node %s. '
                                'bridge_mappings should be a comma-separated '
                                'list of physnetName:bridgeName pairs.\n'
                                'Input -> %s ' % (br_mappings))
            cleaned.append(m.strip())
        return ','.join(cleaned)

    def get_node_phy_bridge(self, node):
        phy_br = None
        for n in self.settings['nodes']:
            if n['hostname'] == node:
                phy_br = n.get('physical_interface_bridge')
        if not phy_br:
            raise Exception('Node %s is missing physical_interface_bridge '
                            'which is required for bonding configuration.'
                            % node)
        return phy_br

    def copy_file_to_node(self, node, local_path, remote_path):
        resp, errors = TimedCommand(["scp", '-o LogLevel=quiet', local_path,
                                     "root@%s:%s" % (node, remote_path)]).run()
        return resp, errors

    def run_command_on_node(self, node, command, timeout=60, retries=0):
        resp, errors = TimedCommand(
            ["ssh", '-o LogLevel=quiet', "root@%s" % node, command]
        ).run(timeout, retries)
        return resp, errors


class FuelEnvironment(Environment):

    def __init__(self, environment_id, skip_nodes=[], specific_nodes=[]):
        self.node_settings = {}
        self.nodes = []
        self.settings = {}
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

    def copy_file_to_node(self, node, local_path, remote_path):
        resp, errors = TimedCommand(["scp", '-o LogLevel=quiet', local_path,
                                     "root@%s:%s" % (node, remote_path)]).run()
        return resp, errors

    def run_command_on_node(self, node, command, timeout=60, retries=0):
        resp, errors = TimedCommand(
            ["ssh", '-o LogLevel=quiet', "root@%s" % node, command]
        ).run(timeout, retries)
        return resp, errors

    def get_node_config(self, node):
        print "Retrieving Fuel configuration for node %s..." % node
        resp, errors = TimedCommand(["ssh", '-o LogLevel=quiet',
                                     "root@%s" % node,
                                     "cat", "/etc/astute.yaml"]).run()
        if errors:
            raise Exception("Error retrieving config for node %s:\n%s"
                            % (node, errors))
        try:
            conf = yaml.load(resp)
        except Exception as e:
            raise Exception("Error parsing node yaml file:\n%s\n%s"
                            % (e, resp))
        return conf

    @property
    def network_vlan_ranges(self):
        net_vlans = []
        # comes from compute settings file
        node = self.node_settings.keys()[0]
        physnets = self.node_settings[node][
            'quantum_settings']['L2']['phys_nets']
        for physnet in physnets:
            range = physnets[physnet]['vlan_range']
            if not range:
                continue
            net_vlans.append('%s:%s' % (physnet, range))
        return ','.join(net_vlans)

    def get_node_bond_interfaces(self, node):
        if node not in self.nodes:
            raise Exception('No node in fuel environment %s' % node)
        trans = self.node_settings[node]['network_scheme']['transformations']
        for t in trans:
            if t.get('action') == 'add-bond':
                return t.get('interfaces', [])
        print 'Node %s has no bond interfaces.' % node
        return []

    def get_node_phy_bridge(self, node):
        bridge = None
        if node not in self.nodes:
            raise Exception('No node in fuel environment %s' % node)
        trans = self.node_settings[node]['network_scheme']['transformations']
        for t in trans:
            if t.get('action') == 'add-bond':
                bridge = t.get('bridge')
        if not bridge:
            raise Exception('Node %s has no bridge for the bond.' % node)
        return bridge

    def get_node_bridge_mappings(self, node):
        if node not in self.nodes:
            raise Exception('No node in fuel environment %s' % node)
        # NOTE: only one used network vlan range supported for now
        physnet = self.network_vlan_ranges.split(',')[0].split(':')[0]
        bridge = self.node_settings[node]['network_scheme']['roles']['private']
        return '%s:%s' % (physnet, bridge)


class StandaloneEnvironment(Environment):
    network_vlan_ranges = None
    nodes = ['localhost']

    def __init__(self, network_vlan_ranges, bridge_mappings, bond_interfaces,
                 physical_bridge):
        self.network_vlan_ranges = network_vlan_ranges
        # optional
        bond_interfaces = bond_interfaces or ''
        self.bridge_mappings = bridge_mappings
        self.bond_interfaces = [i for i in bond_interfaces.split(',') if i]
        self.phy_bridge = physical_bridge

    def get_node_bond_interfaces(self, node):
        return self.bond_interfaces

    def get_node_phy_bridge(self, node):
        return self.phy_bridge

    def get_node_bridge_mappings(self, node):
        if not self.bridge_mappings:
            raise Exception("Missing bridge_mappings setting")
        cleaned = []
        for m in self.bridge_mappings.rstrip(',').split(','):
            if len(m.split(':')) != 2:
                raise Exception('Invalid bridge_mappings setting for node %s. '
                                'bridge_mappings should be a comma-separated '
                                'list of physnetName:bridgeName pairs.\n'
                                'Input -> %s ' % (self.bridge_mappings))
            cleaned.append(m.strip())
        return ','.join(cleaned)

    def copy_file_to_node(self, node, local_path, remote_path):
        resp, errors = TimedCommand(
            ['bash', '-lc', "cp %s %s" % (local_path, remote_path)]).run()
        return resp, errors

    def run_command_on_node(self, node, command, timeout=60, retries=0):
        resp, errors = TimedCommand(['bash', '-lc', command]).run(timeout,
                                                                  retries)
        return resp, errors


class ConfigDeployer(object):
    def __init__(self, environment, patch_python_files=True):
        self.env = environment
        self.patch_python_files = patch_python_files
        self.patch_file_cache = {}
        if any([not self.env.bigswitch_auth,
                not self.env.bigswitch_servers,
                not self.env.nodes]):
            raise Exception('Environment must have at least 1 node '
                            'and controller options')
        if self.patch_python_files:
            print 'Downloading patch files...'
            for patch in PYTHON_FILES_TO_PATCH + [('', '', NEUTRON_TGZ_URL)]:
                url = patch[2]
                try:
                    body = urllib2.urlopen(url).read()
                except Exception as e:
                    raise Exception("Error encountered while trying to "
                                    "download patch file at %s.\n%s"
                                    % (url, e))
                self.patch_file_cache[url] = body

    def deploy_to_all(self):
        for node in self.env.nodes:
            self.deploy_to_node(node)
        print "Deployment Complete!"

    def deploy_to_node(self, node):
        print "Applying configuration to %s..." % node
        bond_interfaces = self.env.get_node_bond_interfaces(node)
        puppet_settings = {
            'bond_interfaces': ','.join(bond_interfaces),
            'bigswitch_servers': self.env.bigswitch_servers,
            'bigswitch_serverauth': self.env.bigswitch_auth,
            'network_vlan_ranges': self.env.network_vlan_ranges
        }
        if bond_interfaces:
            puppet_settings['physical_bridge'] = self.env.get_node_phy_bridge(
                node)
            physnets = self.env.network_vlan_ranges.split(',')
            if len(physnets) > 1:
                print ('Warning, multiple physnets configured "%s". A '
                       'bridge_mapping will only be configured for %s'
                       % (physnets, physnets[0]))
            puppet_settings['bridge_mappings'] = (
                self.env.get_node_bridge_mappings(node))
            for key, val in enumerate(bond_interfaces):
                puppet_settings['bond_int%s' % key] = val
            # If only one bond interface was provided, set the second bond
            # interface to the same as the first to prevent empty config errors
            if len(bond_interfaces) < 2:
                puppet_settings['bond_int1'] = bond_interfaces[0]
        ptemplate = PuppetTemplate(puppet_settings)
        if self.patch_python_files:
            for package, rel_path, url in PYTHON_FILES_TO_PATCH:
                node_path = self.env.get_node_python_package_path(node,
                                                                  package)
                # package is not installed on this node
                # FIXME: Skipping 2.6 to workaround issues with CentOS
                if not node_path or '2.6' in node_path:
                    continue
                full_path = os.path.join(node_path, rel_path)
                contents = self.patch_file_cache[url]
                ptemplate.add_replacement_file(full_path, contents)
        pbody = ptemplate.get_string()
        f = tempfile.NamedTemporaryFile(delete=True)
        f.write(pbody)
        f.flush()
        remotefile = '~/generated_manifest.pp'
        resp, errors = self.env.copy_file_to_node(node, f.name, remotefile)
        if errors:
            raise Exception("error pushing puppet manifest to %s:\n%s"
                            % (node, errors))

        # Find where python libs are installed
        netaddr_path = self.env.get_node_python_package_path(node, 'netaddr')
        # we need to replace all of neutron plugins dir in CentOS
        if netaddr_path:
            python_lib_dir = "/".join(netaddr_path.split("/")[:-1]) + "/"
            target_neutron_path = python_lib_dir + 'neutron'
            f = tempfile.NamedTemporaryFile(delete=True)
            f.write(self.patch_file_cache[NEUTRON_TGZ_URL])
            f.flush()
            nfile = '~/neutron.tar.gz'
            resp, errors = self.env.copy_file_to_node(node, f.name, nfile)
            if errors:
                raise Exception("error pushing neutron to %s:\n%s"
                                % (node, errors))
            # remove existing plugins and agent directory
            extract = "rm -rf '%s/plugins';" % target_neutron_path
            extract += "rm -rf '%s/agent';" % target_neutron_path
            # temp dir to extract to
            extract += "export TGT=$(mktemp -d);"
            # extract with strip-components to remove the branch dir
            extract += 'tar --strip-components=1 -xf '
            extract += '~/neutron.tar.gz -C "$TGT";'
            # move the extraced plugins to the neutron dir
            extract += 'mv "$TGT/neutron/plugins" "%s/";' % target_neutron_path
            # move the extraced agent dir to the neutron dir
            extract += 'mv "$TGT/neutron/agent" "%s/"' % target_neutron_path
            resp, errors = self.env.run_command_on_node(
                node, "bash -c '%s'" % extract)
            if errors:
                raise Exception("error installing neutron to %s:\n%s"
                                % (node, errors))

        resp, errors = self.env.run_command_on_node(
            node, "puppet apply %s" % remotefile, 30, 2)
        if errors:
            raise Exception("error applying puppet configuration to %s:\n%s"
                            % (node, errors))


class PuppetTemplate(object):

    def __init__(self, settings):
        self.settings = {
            'bond_int0': '', 'bond_int1': '', 'bond_interfaces': '',
            'bigswitch_servers': '', 'bigswitch_serverauth': '',
            'network_vlan_ranges': '', 'physical_bridge': 'br-ovs-bond0',
            'bridge_mappings': ''}
        self.files_to_replace = []
        for key in settings:
            self.settings[key] = settings[key]

    def get_string(self):
        # inject settings into template
        manifest = self.main_body % self.settings
        # only setup bond stuff if interfaces are defined
        if self.settings['bond_interfaces']:
            manifest += self.bond_and_lldpd_configuration

        # inject all replacement files
        for path, contents in self.files_to_replace:
            escaped = contents.replace("\\", "\\\\").replace("'", "\\'")
            manifest += ("\nfile {'%(path)s':\nensure => file,"
                         "\npath => '%(path)s',\nmode => 0755,"
                         "\nnotify => Exec['restartneutronservices'],"
                         "\nrequire => Exec['neutronfilespresent'],"
                         "\ncontent => '%(escaped_content)s'\n}" %
                         {'path': path, 'escaped_content': escaped})
        return manifest

    def add_replacement_file(self, path, contents):
        """Adds a file that needs to be replaced.

        Path specifies the location on the server and contents will be the
        contents loaded into the file.
        """
        self.files_to_replace.append((path, contents))
        return self

    main_body = """
$bigswitch_serverauth = '%(bigswitch_serverauth)s'
$bigswitch_servers = '%(bigswitch_servers)s'
$bond_interfaces = '%(bond_interfaces)s'
$network_vlan_ranges = '%(network_vlan_ranges)s'
$bond_int0 = '%(bond_int0)s'
$bond_int1 = '%(bond_int1)s'
$bond_name = 'ovs-bond0'
$phy_bridge = '%(physical_bridge)s'
$ovs_bridge_mappings = '%(bridge_mappings)s'

if $operatingsystem == 'Ubuntu'{
    $neutron_conf_path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
}
if $operatingsystem == 'CentOS' or $operatingsystem == 'RedHat'{
    $neutron_conf_path = "/etc/neutron/plugin.ini"
}

$neutron_ovs_conf_path = "/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini"
$neutron_l3_conf_path = '/etc/neutron/l3_agent.ini'
$neutron_main_conf_path = "/etc/neutron/neutron.conf"
$bigswitch_ssl_cert_directory = '/etc/neutron/plugins/ml2/ssl'


exec{'neutronfilespresent':
    onlyif => "python -c 'import neutron, os; print os.path.dirname(neutron.__file__)' && python -c 'import neutron, os; print os.path.dirname(neutron.__file__)' | xargs -I {} ls {}/plugins/bigswitch",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    command => "echo",
}
if $operatingsystem == 'Ubuntu' {
  exec{"restartneutronservices":
      refreshonly => true,
      command => "/etc/init.d/neutron-plugin-openvswitch-agent restart ||:;",
      notify => [Exec['neutronl3restart'], Exec['neutronserverrestart']]
  }
}
if $operatingsystem == 'CentOS' or $operatingsystem == 'RedHat' {
  exec{"restartneutronservices":
      refreshonly => true,
      command => "/etc/init.d/neutron-openvswitch-agent restart ||:;",
      notify => [Exec['neutronl3restart'], Exec['neutronserverrestart']]
  }
}
exec{"neutronserverrestart":
    refreshonly => true,
    command => "/etc/init.d/neutron-server restart ||:;",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    onlyif => "ls /etc/init.d/neutron-server"
}
exec{"neutronl3restart":
    refreshonly => true,
    command => "/etc/init.d/neutron-l3-agent restart ||:;",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    onlyif => "ls /etc/init.d/neutron-l3-agent"
}

# basic conf directories
$conf_dirs = ["/etc/neutron/plugins/ml2"]
file {$conf_dirs:
    ensure => "directory",
    owner => "neutron",
    group => "neutron",
    mode => 755,
}

# make sure ml2 is core plugin
ini_setting {"ml2core":
  path    => $neutron_main_conf_path,
  section => 'DEFAULT',
  setting => 'core_plugin',
  value   => 'ml2',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}
# enable l3
ini_setting {"serviceplugins":
  path    => $neutron_main_conf_path,
  section => 'DEFAULT',
  setting => 'service_plugins',
  value   => 'router',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

# reference ml2 ini from init script
file{'neutron_init_config':
  ensure => file,
  mode   => 0644,
  path   => '/etc/default/neutron-server',
  content =>"NEUTRON_PLUGIN_CONFIG='${neutron_conf_path}'\n",
  notify => Exec['restartneutronservices'],
}


# setup ml2 ini
ini_setting { "roothelper":
  path    => $neutron_conf_path,
  section => 'agent',
  setting => 'root_helper',
  value   => 'sudo neutron-rootwrap /etc/neutron/rootwrap.conf',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting { "secgroup":
  path    => $neutron_conf_path,
  section => 'securitygroup',
  setting => 'firewall_driver',
  value   => 'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"type_drivers":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'type_drivers',
  value   => 'vlan',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"tenant_network_types":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'tenant_network_types',
  value   => 'vlan',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"mechanism_drivers":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'mechanism_drivers',
  value   => 'openvswitch,bigswitch',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"vlan_ranges":
  path    => $neutron_conf_path,
  section => 'ml2_type_vlan',
  setting => 'network_vlan_ranges',
  value   => $network_vlan_ranges,
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"ovs_vlan_ranges":
  path    => $neutron_ovs_conf_path,
  section => 'ovs',
  setting => 'network_vlan_ranges',
  value   => $network_vlan_ranges,
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting {"bigswitch_servers":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'servers',
  value   => $bigswitch_servers,
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting { "bigswitch_auth":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'server_auth',
  value   => $bigswitch_serverauth,
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

ini_setting { "bigswitch_ssl":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'ssl_cert_directory',
  value   => $bigswitch_ssl_cert_directory,
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}

# temporarily disable sync until beta-2
ini_setting { "bigswitch_auto_sync":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'auto_sync_on_failure',
  value   => 'False',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}
ini_setting { "bigswitch_consistency_interval":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'consistency_interval',
  value   => '0',
  ensure  => present,
  notify => Exec['restartneutronservices'],
  require => File[$conf_dirs],
}



file { 'ssl_dir':
  ensure => "directory",
  path   => $bigswitch_ssl_cert_directory,
  owner  => "neutron",
  group  => "neutron",
  purge => true,
  recurse => true,
  mode   => 0750,
  notify => Exec['restartneutronservices'],
}

if $operatingsystem == 'Ubuntu'{
    file {'keystone':
      path   => '/usr/lib/python2.7/dist-packages/keystone-signing',
      ensure => 'directory',
      owner  => 'root',
      group  => 'root',
      mode   => 0777,
      notify => Exec['restartneutronservices'],
    }
}
if $operatingsystem == 'CentOS'{
    file {'keystone26':
      path   => '/usr/lib/python2.6/site-packages/keystone-signing',
      ensure => 'directory',
      owner  => 'root',
      group  => 'root',
      mode   => 0777,
      notify => Exec['restartneutronservices'],
    }
}

#configure l3 agent
ini_setting {"ext_net_bridge":
  path    => $neutron_l3_conf_path,
  section => 'DEFAULT',
  setting => 'external_network_bridge',
  value   => '',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"handle_internal_only":
  path    => $neutron_l3_conf_path,
  section => 'DEFAULT',
  setting => 'handle_internal_only_routers',
  value   => 'True',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

exec {"cleanup_neutron":
  onlyif => ["which mysql", "echo 'show tables' | mysql -u root neutron"],
  path => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
  command => "echo 'delete ports, floatingips from ports INNER JOIN floatingips on floatingips.floating_port_id = ports.id where ports.network_id NOT IN (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete ports, routers from ports INNER JOIN routers on routers.gw_port_id = ports.id where ports.network_id NOT IN (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete from ports where network_id NOT in (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete from subnets where network_id NOT IN (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete from networks where id NOT IN (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete from ports where network_id NOT IN (select network_id from networks);' | mysql -u root neutron;
              echo 'delete from routers where gw_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from floatingips where floating_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from floatingips where fixed_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from subnets where network_id NOT IN (select id from networks);' | mysql -u root neutron;
             "
}

"""  # noqa

    bond_and_lldpd_configuration = r'''
exec {"loadbond":
   command => 'modprobe bonding',
   path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
   unless => "modinfo bonding",
   notify => Exec['deleteovsbond'],
}
exec {"deleteovsbond":
  command => "/usr/bin/ovs-appctl bond/list | grep -v slaves | head -n1 | awk -F '\\t' '{ print \$1 }' | xargs -I {} ovs-vsctl del-port ${phy_bridge} {}",
  path    => "/usr/local/bin/:/bin/:/usr/bin",
  require => Exec['lldpdinstall'],
  onlyif  => "/sbin/ifconfig ${phy_bridge} && ovs-vsctl show | grep '\"${bond_name}\"'",
  notify => Exec['networkingrestart']
}
exec {"clearint0":
  command => "ovs-vsctl --if-exists del-port $bond_int0",
  path    => "/usr/local/bin/:/bin/:/usr/bin",
  require => Exec['lldpdinstall'],
  onlyif => "ovs-vsctl show | grep 'Port \"${bond_int0}\"'",
}
exec {"clearint1":
  command => "ovs-vsctl --if-exists del-port $bond_int1",
  path    => "/usr/local/bin/:/bin/:/usr/bin",
  require => Exec['lldpdinstall'],
  onlyif => "ovs-vsctl show | grep 'Port \"${bond_int1}\"'",
}

# make sure bond module is loaded
if $operatingsystem == 'Ubuntu' {
    file_line { 'bond':
       path => '/etc/modules',
       line => 'bonding',
       notify => Exec['loadbond'],
    }
    file {'bondmembers':
        ensure => file,
        path => '/etc/network/interfaces.d/bond',
        mode => 0644,
        content => "
auto ${bond_int0}
iface ${bond_int0} inet manual
bond-master bond0

auto ${bond_int1}
iface ${bond_int1} inet manual
bond-master bond0

auto bond0
    iface bond0 inet manual
    bond-mode 0
    bond-slaves none
    ",
    }
    exec {"networkingrestart":
       refreshonly => true,
       require => [Exec['loadbond'], File['bondmembers'], Exec['deleteovsbond'], Exec['lldpdinstall']],
       command => '/etc/init.d/networking restart',
       notify => Exec['addbondtobridge'],
    }
    file {'sources':
          ensure  => file,
          path    => '/etc/apt/sources.list.d/universe.list',
          mode    => 0644,
          notify => Exec['lldpdinstall'],
          content => "
deb http://us.archive.ubuntu.com/ubuntu/ precise universe
deb-src http://us.archive.ubuntu.com/ubuntu/ precise universe
deb http://us.archive.ubuntu.com/ubuntu/ precise-updates universe
deb-src http://us.archive.ubuntu.com/ubuntu/ precise-updates universe
deb http://us.archive.ubuntu.com/ubuntu/ precise-backports main restricted universe multiverse
deb-src http://us.archive.ubuntu.com/ubuntu/ precise-backports main restricted universe multiverse
deb http://security.ubuntu.com/ubuntu precise-security universe
deb-src http://security.ubuntu.com/ubuntu precise-security universe",
        }

    exec{"lldpdinstall":
        onlyif => "bash -c '! ls /etc/init.d/lldpd'",
        command => "apt-get update; apt-get -o Dpkg::Options::=--force-confdef install --allow-unauthenticated -y lldpd",
        path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
        notify => [Exec['networkingrestart'], File['ubuntulldpdconfig']],
    }
    exec{"triggerinstall":
        onlyif => 'bash -c "! ls /etc/init.d/lldpd"',
        command => 'echo',
        notify => Exec['lldpdinstall'],
        path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    }
    file{'ubuntulldpdconfig':
        ensure => file,
        mode   => 0644,
        path   => '/etc/default/lldpd',
        content => "DAEMON_ARGS='-S 5c:16:c7:00:00:00 -I ${bond_interfaces}'\n",
        notify => Exec['lldpdrestart'],
    }
    exec {"openvswitchrestart":
       refreshonly => true,
       command => '/etc/init.d/openvswitch-switch restart',
       path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    }
}
if $operatingsystem == 'RedHat' {
    exec {"networkingrestart":
       refreshonly => true,
       command => '/etc/init.d/network restart',
       require => [Exec['loadbond'], File['bondmembers'], Exec['deleteovsbond']],
       notify => Exec['addbondtobridge'],
    }
    file{'bondmembers':
        require => [Exec['loadbond']],
        ensure => file,
        mode => 0644,
        path => '/etc/sysconfig/network-scripts/ifcfg-bond0',
        content => '
DEVICE=bond0
USERCTL=no
BOOTPROTO=none
ONBOOT=yes
BONDING_OPTS="mode=0 miimon=50"
',
    }
    file{'bond_int0config':
        require => File['bondmembers'],
        notify => Exec['networkingrestart'],
        ensure => file,
        mode => 0644,
        path => "/etc/sysconfig/network-scripts/ifcfg-$bond_int0",
        content => "DEVICE=$bond_int0\nMASTER=bond0\nSLAVE=yes\nONBOOT=yes\nUSERCTL=no\n",
    }
    if $bond_int0 != $bond_int1 {
        file{'bond_int1config':
            require => File['bondmembers'],
            notify => Exec['networkingrestart'],
            ensure => file,
            mode => 0644,
            path => "/etc/sysconfig/network-scripts/ifcfg-$bond_int1",
            content => "DEVICE=$bond_int1\nMASTER=bond0\nSLAVE=yes\nONBOOT=yes\nUSERCTL=no\n",
        }
    }

    exec {"openvswitchrestart":
       refreshonly => true,
       command => '/etc/init.d/openvswitch restart',
       path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    }

}
if $operatingsystem == 'CentOS' {
    exec {'lldpdinstall':
       onlyif => "yum --version && (! ls /etc/init.d/lldpd)",
       command => "bash -c 'cd /etc/yum.repos.d/; wget http://download.opensuse.org/repositories/home:vbernat/CentOS_CentOS-6/home:vbernat.repo; yum -y install lldpd'",
       path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
       notify => File['centoslldpdconfig'],
    }
    file{'centoslldpdconfig':
        ensure => file,
        mode   => 0644,
        path   => '/etc/sysconfig/lldpd',
        content => "LLDPD_OPTIONS='-S 5c:16:c7:00:00:00 -I ${bond_interfaces}'\n",
        notify => Exec['lldpdrestart'],
    }
    exec {"networkingrestart":
       refreshonly => true,
       command => '/etc/init.d/network restart',
       require => [Exec['loadbond'], File['bondmembers'], Exec['deleteovsbond'], Exec['lldpdinstall']],
       notify => Exec['addbondtobridge'],
    }
    file{'bondmembers':
        require => [Exec['lldpdinstall'],Exec['loadbond'],File['centoslldpdconfig']],
        ensure => file,
        mode => 0644,
        path => '/etc/sysconfig/network-scripts/ifcfg-bond0',
        content => '
DEVICE=bond0
USERCTL=no
BOOTPROTO=none
ONBOOT=yes
BONDING_OPTS="mode=0 miimon=50"
',
    }
    file{'bond_int0config':
        require => File['bondmembers'],
        notify => Exec['networkingrestart'],
        ensure => file,
        mode => 0644,
        path => "/etc/sysconfig/network-scripts/ifcfg-$bond_int0",
        content => "DEVICE=$bond_int0\nMASTER=bond0\nSLAVE=yes\nONBOOT=yes\nUSERCTL=no\n",
    }
    if $bond_int0 != $bond_int1 {
        file{'bond_int1config':
            require => File['bondmembers'],
            notify => Exec['networkingrestart'],
            ensure => file,
            mode => 0644,
            path => "/etc/sysconfig/network-scripts/ifcfg-$bond_int1",
            content => "DEVICE=$bond_int1\nMASTER=bond0\nSLAVE=yes\nONBOOT=yes\nUSERCTL=no\n",
        }
    }
    exec {"openvswitchrestart":
       refreshonly => true,
       command => '/etc/init.d/openvswitch restart',
       path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    }
}
exec {"addbondtobridge":
   command => "ovs-vsctl --may-exist add-port ${phy_bridge} bond0",
   onlyif => "/sbin/ifconfig bond0 && ! ovs-ofctl show ${phy_bridge} | grep '(bond0)'",
   path    => "/usr/local/bin/:/bin/:/usr/bin",
   notify => Exec['openvswitchrestart'],
}
exec{'lldpdrestart':
    refreshonly => true,
    require => Exec['lldpdinstall'],
    command => "rm /var/run/lldpd.socket ||:;/etc/init.d/lldpd restart",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
}

ini_setting {"ovs_bridge_mappings":
  path    => $neutron_ovs_conf_path,
  section => 'ovs',
  setting => 'bridge_mappings',
  value   => $ovs_bridge_mappings,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

'''  # noqa

if __name__ == '__main__':
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
    parser.add_argument("-s", "--controllers", required=True,
                        help="Comma-separated list of "
                             "<controller:port> pairs.")
    parser.add_argument("-a", "--controller-auth", required=True,
                        help="Username and password <user:pass> "
                             "to connect to controller.")
    parser.add_argument('--skip-file-patching', action='store_true',
                        help="Do not patch openstack packages with updated "
                             "versions.")
    remote = parser.add_argument_group('remote-deployment')
    remote.add_argument('--skip-nodes',
                        help="Comma-separate list of nodes to skip deploying "
                             "configurations to.")
    remote.add_argument('--specific-nodes',
                        help="Comma-separate list of nodes to deploy to. All "
                             "others will be skipped.")
    local = parser.add_argument_group(
        'standalone-deployment', 'Arguments for standalone deployments')
    local.add_argument('--network-vlan-ranges',
                       help="Comma-separated list of physical network vlan "
                            "ranges. (e.g. a single vlan range would be "
                            "physnet1:100:3000)")
    local.add_argument('--phy-int-bridge',
                       help="OVS bridge that will contain the bond "
                            "interface. (e.g. br-eth0)")
    local.add_argument('--bridge-mappings',
                       help="Mappings between physical networks and OVS "
                            "bridges. (e.g. physnet1:br-eth0)")
    local.add_argument('--bond-interfaces',
                       help="Comma-separated list of interfaces to configure. "
                            "(e.g. eth1,eth2)")
    args = parser.parse_args()
    if args.specific_nodes:
        specific_nodes = args.specific_nodes.split(',')
    else:
        specific_nodes = []
    if args.skip_nodes:
        skip_nodes = args.skip_nodes.split(',')
    else:
        skip_nodes = []
    if args.fuel_environment:
        environment = FuelEnvironment(args.fuel_environment,
                                      skip_nodes=skip_nodes,
                                      specific_nodes=specific_nodes)
    elif args.config_file:
        environment = ConfigEnvironment(args.config_file.read(),
                                        skip_nodes=skip_nodes,
                                        specific_nodes=specific_nodes)
    elif args.stand_alone:
        if not args.network_vlan_ranges:
            parser.error('--network-vlan-ranges is required when using '
                         'stand-alone mode.')
        if args.bond_interfaces:
            missing = []
            if not args.phy_int_bridge:
                missing.append('--phy-int-bridge')
            if not args.bridge_mappings:
                missing.append('--bridge-mappings')
            if missing:
                parser.error('Missing required params %s when specifying bond '
                             'interfaces.' % missing)
        environment = StandaloneEnvironment(
            args.network_vlan_ranges, args.bridge_mappings,
            args.bond_interfaces, args.phy_int_bridge)
    else:
        parser.error('You must specify the Fuel environment, the config '
                     'file, or standalone mode.')
    environment.set_bigswitch_servers(args.controllers)
    environment.set_bigswitch_auth(args.controller_auth)
    deployer = ConfigDeployer(environment,
                              patch_python_files=not args.skip_file_patching)
    deployer.deploy_to_all()
