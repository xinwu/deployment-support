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
import urllib2
import yaml

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


class Environment(object):

    nodes = []
    bigswitch_auth = None
    bigswitch_servers = None

    @property
    def network_vlan_ranges(self):
        raise NotImplementedError()

    def get_node_bond_interfaces(self, node):
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
        com = ["ssh", '-o LogLevel=quiet',
               "root@%s" % node,
               'python -c "import %s;import os;print '
               'os.path.dirname(%s.__file__)"'
               % (package, package)]
        resp, errors = subprocess.Popen(com, stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE).communicate()
        if errors or not resp.strip() or len(resp.strip().splitlines()) > 1:
            if 'ImportError' in errors:
                return False
            raise Exception("Error retrieving path to pyhon package '%s' on "
                            "node '%s'.\n%s\n%s" % (package, node,
                                                    errors, resp))
        return resp.strip()


class ConfigEnvironment(Environment):

    def __init__(self, yaml_string):
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
            self.nodes = [n['hostname'] for n in self.settings['nodes']]
        except KeyError:
            raise Exception('missing hostname in nodes %s'
                            % self.settings['nodes'])

    def get_node_bond_interfaces(self, node):
        for n in self.settings['nodes']:
            if n['hostname'] == node:
                return n.get('bond_interfaces', '').split(',')
        return []


class FuelEnvironment(Environment):

    def __init__(self, environment_id):
        self.node_settings = {}
        self.nodes = []
        self.settings = {}
        try:
            print "Retrieving general Fuel settings..."
            output, errors = subprocess.Popen(
                ["fuel", "--json", "--env", str(environment_id),
                 "settings", "-d"],
                stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        except Exception as e:
            raise Exception("Error encountered trying to execute the Fuel "
                            "CLI:\n%s" % e)
        if errors:
            raise Exception("Error Loading cluster %s:\n%s"
                            % (environment_id, errors))
        try:
            path = output.split('downloaded to ')[1].rstrip()
        except IndexError:
            raise Exception("Could not download fuel settings: %s"
                            % output)
        try:
            self.settings = json.loads(open(path, 'r').read())
        except Exception as e:
            raise Exception("Error parsing fuel json settings.\n%s" % e)

        # grab list of hosts
        print "Retrieving list of Fuel nodes..."
        output, errors = subprocess.Popen(
            ["fuel", "nodes", "--env", str(environment_id)],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("Error Loading node list %s:\n%s"
                            % (environment_id, errors))
        try:
            lines = [l for l in output.splitlines()
                     if '----' not in l and 'pending_roles' not in l]
            self.nodes = [str(netaddr.IPAddress(l.split('|')[4].strip()))
                          for l in lines]
            print "Found nodes: %s" % self.nodes
        except IndexError:
            raise Exception("Could not parse node list:\n%s" % output)
        for node in self.nodes:
            self.node_settings[node] = self.get_node_config(node)

    def get_node_config(self, node):
        print "Retrieving Fuel configuration for node %s..." % node
        resp, errors = subprocess.Popen(["ssh", '-o LogLevel=quiet',
                                         "root@%s" % node,
                                         "cat", "/etc/astute.yaml"],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE).communicate()
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
        net_vlan = ''
        # comes from compute settings file
        node = self.node_settings.keys()[0]
        physnets = self.node_settings[node][
            'quantum_settings']['L2']['phys_nets']
        for physnet in physnets:
            range = physnets[physnet]['vlan_range']
            if not range:
                continue
            net_vlan += '%s:%s,' % (physnet, range)
        return net_vlan

    def get_node_bond_interfaces(self, node):
        if node not in self.nodes:
            raise Exception('No node in fuel environment %s' % node)
        trans = self.node_settings[node]['network_scheme']['transformations']
        for t in trans:
            if t.get('action') == 'add-bond':
                return t.get('interfaces', [])
        return []


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
            for patchset in PYTHON_FILES_TO_PATCH:
                url = patchset[2]
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
        puppet_settings = {
            'bond_int0': self.env.get_node_bond_interfaces(node)[0],
            'bond_int1': self.env.get_node_bond_interfaces(node)[1],
            'bond_interfaces': ','.join(
                self.env.get_node_bond_interfaces(node)),
            'bigswitch_servers': self.env.bigswitch_servers,
            'bigswitch_serverauth': self.env.bigswitch_auth,
            'network_vlan_ranges': self.env.network_vlan_ranges
        }
        ptemplate = PuppetTemplate(puppet_settings)
        if self.patch_python_files:
            for package, rel_path, url in PYTHON_FILES_TO_PATCH:
                node_path = self.env.get_node_python_package_path(node,
                                                                  package)
                # package is not installed on this node
                if not node_path:
                    continue
                full_path = os.path.join(node_path, rel_path)
                contents = self.patch_file_cache[url]
                ptemplate.add_replacement_file(full_path, contents)
        pbody = ptemplate.get_string()
        f = tempfile.NamedTemporaryFile(delete=True)
        f.write(pbody)
        f.flush()
        remotefile = '~/generated_manifest.pp'
        resp, errors = subprocess.Popen(["scp", '-o LogLevel=quiet', f.name,
                                         "root@%s:%s" % (node, remotefile)],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("error pushing puppet manifest to %s:\n%s"
                            % (node, errors))
        resp, errors = subprocess.Popen(["ssh", '-o LogLevel=quiet',
                                         "root@%s" % node,
                                         "puppet apply %s" % remotefile],
                                        stdout=subprocess.PIPE,
                                        stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("error applying puppet configuration to %s:\n%s"
                            % (node, errors))


class PuppetTemplate(object):

    def __init__(self, settings):
        self.settings = {
            'bond_int0': '', 'bond_int1': '', 'bond_interfaces': '',
            'bigswitch_servers': '', 'bigswitch_serverauth': '',
            'network_vlan_ranges': ''}
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
            escaped_content = contents.replace("'", "\\'")
            manifest += ("\nfile {'%(path)s':\nensure => file,"
                         "\npath => '%(path)s',\nmode => 0755,"
                         "\nnotify => Exec['restartneutronservices'],"
                         "\ncontent => '%(escaped_content)s'\n}" %
                         {'path': path, 'escaped_content': escaped_content})
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

$neutron_conf_path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
$neutron_ovs_conf_path = "/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini"
$neutron_l3_conf_path = '/etc/neutron/l3_agent.ini'
$neutron_main_conf_path = "/etc/neutron/neutron.conf"
$bigswitch_ssl_cert_directory = '/etc/neutron/plugins/ml2/ssl'



exec{"restartneutronservices":
    refreshonly => true,
    command => "/etc/init.d/neutron-plugin-openvswitch-agent restart ||:;",
    notify => [Exec['neutronl3restart'], Exec['neutronserverrestart']]
}
exec{"neutronserverrestart":
    refreshonly => true,
    command => "/etc/init.d/neutron-server restart ||:;",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    onlyif => "file /etc/init.d/neutron-server"
}
exec{"neutronl3restart":
    refreshonly => true,
    command => "/etc/init.d/neutron-l3-agent restart ||:;",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    onlyif => "file /etc/init.d/neutron-l3-agent"
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
}

ini_setting { "secgroup":
  path    => $neutron_conf_path,
  section => 'securitygroup',
  setting => 'firewall_driver',
  value   => 'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"type_drivers":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'type_drivers',
  value   => 'vlan',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"tenant_network_types":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'tenant_network_types',
  value   => 'vlan',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"mechanism_drivers":
  path    => $neutron_conf_path,
  section => 'ml2',
  setting => 'mechanism_drivers',
  value   => 'openvswitch,bigswitch,logger',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"vlan_ranges":
  path    => $neutron_conf_path,
  section => 'ml2_type_vlan',
  setting => 'network_vlan_ranges',
  value   => $network_vlan_ranges,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"ovs_vlan_ranges":
  path    => $neutron_ovs_conf_path,
  section => 'ovs',
  setting => 'network_vlan_ranges',
  value   => $network_vlan_ranges,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"bigswitch_servers":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'servers',
  value   => $bigswitch_servers,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting { "bigswitch_auth":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'server_auth',
  value   => $bigswitch_serverauth,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting { "bigswitch_ssl":
  path    => $neutron_conf_path,
  section => 'restproxy',
  setting => 'ssl_cert_directory',
  value   => $bigswitch_ssl_cert_directory,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

file { 'ssl_dir':
  ensure => "directory",
  path   => $bigswitch_ssl_cert_directory,
  owner  => "neutron",
  group  => "neutron",
  mode   => 0750,
  notify => Exec['restartneutronservices'],
}

file {'keystone':
  path   => '/usr/lib/python2.7/dist-packages/keystone-signing',
  ensure => 'directory',
  owner  => 'root',
  group  => 'root',
  mode   => 0777,
  notify => Exec['restartneutronservices'],
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

    bond_and_lldpd_configuration = """
# make sure bond module is loaded
file_line { 'bond':
   path => '/etc/modules',
   line => 'bonding',
   notify => Exec['loadbond'],
}
exec {"loadbond":
   command => 'modprobe bonding',
   path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
   unless => "modinfo bonding",
   notify => Exec['deleteovsbond'],
}
exec {"deleteovsbond":
  command => "/usr/bin/ovs-appctl bond/list | grep -v slaves | head -n1 | awk -F '\t' '{ print $1 }' | xargs -I {} ovs-vsctl del-port br-ovs-bond0 {}",
  path    => "/usr/local/bin/:/bin/:/usr/bin",
  onlyif  => "/sbin/ifconfig ${bond_name} && /sbin/ifconfig br-ovs-bond0"
}
file {'bondmembers':
    ensure => file,
    path => '/etc/network/interfaces.d/bond',
    mode => 0644,
    content => "
auto ${bond_int0}
iface eth0 inet manual
bond-master bond0

auto ${bond_int1}
iface eth1 inet manual
bond-master bond0

auto bond0
    iface bond0 inet manual
    bond-mode 0
    bond-slaves none
",
   notify => Exec['networkingrestart'],
}
exec {"networkingrestart":
   refreshonly => true,
   require => Exec['loadbond'],
   command => '/etc/init.d/networking restart',
   notify => Exec['addbondtobridge'],
}
exec {"addbondtobridge":
   refreshonly => true,
   command => 'ovs-vsctl --may-exist add-port br-ovs-bond0 bond0',
   path    => "/usr/local/bin/:/bin/:/usr/bin",
   notify => Exec['openvswitchrestart'],
}
exec {"openvswitchrestart":
   refreshonly => true,
   command => '/etc/init.d/openvswitch-switch restart',
   path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
}


file {'sources':
      ensure  => file,
      path    => '/etc/apt/sources.list.d/universe.list',
      mode    => 0644,
      notify => Exec['aptupdate'],
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

exec{"aptupdate":
    refreshonly => true,
    command => "apt-get update; apt-get install --allow-unauthenticated -y lldpd",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
    notify => File['lldpdconfig'],
}

file{'lldpdconfig':
    ensure => file,
    mode   => 0644,
    path   => '/etc/default/lldpd',
    content => "DAEMON_ARGS='-S 5c:16:c7:00:00:00 -I ${bond_interfaces}'\n",
    notify => Exec['lldpdrestart'],
}

exec{'lldpdrestart':
    refreshonly => true,
    command => "rm /var/run/lldpd.socket ||:;/etc/init.d/lldpd restart",
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
}
"""  # noqa

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
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
    args = parser.parse_args()
    if args.fuel_environment:
        environment = FuelEnvironment(args.fuel_environment)
    elif args.config_file:
        environment = ConfigEnvironment(args.config_file.read())
    else:
        parser.error('You must specify either the Fuel '
                     'environment or the config file.')
    environment.set_bigswitch_servers(args.controllers)
    environment.set_bigswitch_auth(args.controller_auth)
    deployer = ConfigDeployer(environment,
                              patch_python_files=not args.skip_file_patching)
    deployer.deploy_to_all()
