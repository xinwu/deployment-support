import argparse
import json
import netaddr
import os
import tempfile
import subprocess
import yaml


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
                                'Format should be ip:port' %s)
        self.bigswitch_servers = servers

    def set_bigswitch_auth(self, auth):
        if ':' not in auth:
            raise Exception('Invalid credentials "%s".\n'
                            'Format should be user:pass' % auth)
        self.bigswitch_auth = auth


class ConfigEnvironment(Environment):

    def __init__(self, yaml_string):
        try:
            self.settings = yaml.load(yaml_string)
        except Exception as e:
            raise Exception("Error loading from yaml file:\n%s" % e)
        if not isinstance(self.settings.get('nodes'), list):
            raise Exception("Missing nodes in yaml data.\n%s" % self.settings)
        if not self.settings.get('network_vlan_ranges'):
            raise Exception('Missing network_vlan_ranges in config.\n%s' % self.settings)
        try:
            self.nodes = [n['hostname'] for n in self.settings['nodes']]
        except KeyError:
            raise Exception('missing hostname in nodes %s' % self.settings['nodes'])

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
        output, errors = subprocess.Popen(
            ["fuel", "--json", "--env", str(environment_id), "settings", "-d"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("Error Loading cluster %s:\n%s" % (environment_id, errors))
        try:
            path = output.split('downloaded to ')[1].rstrip()
        except IndexError:
            raise Exception("Could not download fuel settings: %s" %output)
        try:
            self.settings=json.loads(open(path, 'r').read())
        except Exception as e:
            raise Exception("Error parsing fuel json settings.\n%s" % e)

        # grab deployment files
        output, errors = subprocess.Popen(
            ["fuel", "--json", "--env", str(environment_id), "deployment", "default"],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("Error Loading node definitions %s:\n%s"
                            % (environment_id, errors))
        try:
            path = output.split('downloaded to ')[1].rstrip()
        except IndexError:
            raise Exception("Could not download fuel settings: %s" %output)
        try:
            files = os.listdir(path)
            for f in files:
                if f.endswith(".json"):
                     node_name = self.get_node_IP(f.split('.json')[0])
                     self.nodes.append(node_name)
                     self.node_settings[node_name] = json.loads(
                         open(os.path.join(path, f), 'r').read())
        except Exception as e:
            raise Exception("Could not get individual node settings:\n%s" % e)

    def get_node_IP(self, node):
        id = node.split("_")[1]
        resp, errors = subprocess.Popen(["fuel", "node", "--node-id", id],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE).communicate()
        try:
            # should be last line 5th column
            IP = str(netaddr.IPAddress(resp.splitlines()[-1].split('|')[4].strip()))
        except:
            raise Exception("Could not retrieve node IP address for node %s" % node)
        return IP

    @property
    def network_vlan_ranges(self):
        net_vlan = ''
        # comes from compute settings file
        node = self.node_settings.keys()[0]
        physnets = self.node_settings[node]['quantum_settings']['L2']['phys_nets']
        for physnet in physnets:
             net_vlan += '%s:%s,' % (
                 physnet, physnets[physnet]['vlan_range'])
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
    def __init__(self, environment):
        self.env = environment
        if any([not self.env.bigswitch_auth,
                not self.env.bigswitch_servers,
                not self.env.nodes]):
            raise Exception('Environment must have at least 1 node '
                            'and controller options')

    def deploy_to_all(self):
        for node in self.env.nodes:
            self.deploy_to_node(node)

    def deploy_to_node(self, node):
        puppet_settings = {
            'bond_int0': self.env.get_node_bond_interfaces(node)[0],
            'bond_int1': self.env.get_node_bond_interfaces(node)[1],
            'bond_interfaces': ','.join(self.env.get_node_bond_interfaces(node)),
            'bigswitch_servers': self.env.bigswitch_servers,
            'bigswitch_serverauth': self.env.bigswitch_auth,
            'network_vlan_ranges': self.env.network_vlan_ranges
        }
        pbody = PuppetTemplate(puppet_settings).get_string()
        f = tempfile.NamedTemporaryFile(delete=True)
        f.write(pbody)
        f.flush()
        remotefile = '~/generated_manifest.pp'
        resp, errors = subprocess.Popen(["scp",'-o LogLevel=quiet', f.name, "%s:%s" % (node, remotefile)],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("error pushing puppet manifest to %s:\n%s" %(node, errors))
        resp, errors = subprocess.Popen(["ssh", '-o LogLevel=quiet', node, "puppet apply %s" % remotefile],
                                         stdout=subprocess.PIPE,
                                         stderr=subprocess.PIPE).communicate()
        if errors:
            raise Exception("error applying puppet configuration to %s:\n%s" %(node, errors))
        print resp



class PuppetTemplate(object):

    def __init__(self, settings):
        for key in settings:
            self.settings[key] = settings[key]

    def get_string(self):
        return self.body % self.settings

    settings = {'bond_int0': '', 'bond_int1': '', 'bond_interfaces': '',
                'bigswitch_servers': '', 'bigswitch_serverauth': '',
                'network_vlan_ranges': ''}
    body = """
$bigswitch_serverauth = '%(bigswitch_serverauth)s'
$bigswitch_servers = '%(bigswitch_servers)s'
$bond_interfaces = '%(bond_interfaces)s'
$network_vlan_ranges = '%(network_vlan_ranges)s'
$bond_int0 = '%(bond_int0)s'
$bond_int1 = '%(bond_int1)s'
$bond_name = 'ovs-bond0'

$neutron_conf_path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
$neutron_l3_conf_path = '/etc/neutron/l3_agent.ini'
$neutron_main_conf_path = "/etc/neutron/neutron.conf"
$bigswitch_ssl_cert_directory = '/etc/neutron/plugins/ml2/ssl'


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
  command => "/usr/bin/ovs-aptctl bond/list | grep -v slaves | head -n1 | awk -F '\t' '{ print $1 }' | xargs -I {} ovs-vsctl del-port br-ovs-bond0 {}",
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
   command => 'ovs-vsctl add-port br-ovs-bond0 bond0 --may-exist',
   path    => "/usr/local/bin/:/bin/:/usr/bin",
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
    path    => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin",
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

exec {"cleanup_neutron":
  onlyif => "echo 'show tables' | mysql -u root neutron",
  path => "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin",
  command => "echo 'delete from networks where id NOT IN (select network_id from ml2_network_segments);' | mysql -u root neutron;
              echo 'delete from ports where network_id NOT IN (select id from networks);' | mysql -u root neutron;
              echo 'delete from routers where gw_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from floatingips where floating_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from floatingips where fixed_port_id NOT IN (select id from ports);' | mysql -u root neutron;
              echo 'delete from subnets where network_id NOT IN (select id from networks);' | mysql -u root neutron;
             "
}

"""

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    group = parser.add_mutually_exclusive_group()
    group.add_argument("-f", "--fuel-environment",
                       help="Fuel environment ID to load node settings from.")
    group.add_argument("-c", "--config-file", type=argparse.FileType('r'),
                       help="Path to YAML config file for non-fuel deployments.")
    parser.add_argument("-s", "--controllers", required=True,
                        help="Comma-separated list of <controller:port> pairs.")
    parser.add_argument("-a", "--controller-auth", required=True,
                        help="Username and password <user:pass> to connect to controller.")
    args = parser.parse_args()
    if args.fuel_environment:
        environment = FuelEnvironment(args.fuel_environment)
    elif args.config_file:
        environment = ConfigEnvironment(args.config_file.read())
    else:
        parser.error('You must specify either the Fuel environment or the config file.')
    environment.set_bigswitch_servers(args.controllers)
    environment.set_bigswitch_auth(args.controller_auth)
    deployer = ConfigDeployer(environment)
    deployer.deploy_to_all()
