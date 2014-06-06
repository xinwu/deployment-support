# TODO populate from external
$bigswitch_serverauth = 'admin:adminadmin'
$bigswitch_servers = '10.210.48.13:8000,10.210.48.14:8000'
$bond_name = 'ovs-bond0'
$bond_interfaces = 'eth0,eth1'

#$bigswitch_servers = $::fuel_settings['bsn']['servers']
#$bigswitch_auth = $::fuel_settings['bsn']['server_auth']

# TODO populate from existing options
#$::fuel_settings['quantum_settings']['L2']['phys_nets']
$network_vlan_ranges = 'physnet1:100:3100'
$ovs_bridge_mappings = "physnet1:br-int"

# this gets the bond interface name
#"/usr/bin/ovs-aptctl bond/list | grep -v slaves | head -n1 | awk -F '\t' '{ print $1 }'"

# this gets the members
#"/usr/bin/ovs-aptctl bond/list | grep -v slaves | head -n1 | awk -F '\t' '{ print $3 }' | sed 's/[[:space:]]//g'"



$neutron_conf_path = "/etc/neutron/plugins/ml2/ml2_conf.ini"
$neutron_l3_conf_path = '/etc/neutron/l3_agent.ini'
$neutron_main_conf_path = "/etc/neutron/neutron.conf"
$neutron_ovs_conf_path = "/etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini"
$bigswitch_ssl_cert_directory = '/etc/neutron/plugins/ml2/ssl'


# make sure bond is right
exec {"setbondmode":
  command => "ovs-vsctl set port ${bond_name} bond_mode=balance-slb",
  path    => "/usr/local/bin/:/bin/:/usr/bin",
  onlyif  => "/sbin/ifconfig ${bond_name}"
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
    command => "/etc/init.d/neutron-server restart ||:;
               /etc/init.d/neutron-l3-agent restart ||:;
               /etc/init.d/neutron-plugin-openvswitch-agent restart ||:;",
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

# configure ovs agent

ini_setting {"ovs_vlan_ranges":
  path    => $neutron_ovs_conf_path,
  section => 'ovs',
  setting => 'network_vlan_ranges',
  value   => $network_vlan_ranges,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

ini_setting {"ovs_bridge_mappings":
  path    => $neutron_ovs_conf_path,
  section => 'ovs',
  setting => 'bridge_mappings',
  value   => $ovs_bridge_mappings,
  ensure  => present,
  notify => Exec['restartneutronservices'],
}

#configure l3 agent
ini_setting {"ext_net_bridge":
  path    => $neutron_l3_conf_path,
  section => 'DEFAULT',
  setting => 'external_network_bridge',
  value   => 'br-ex',
  ensure  => present,
  notify => Exec['restartneutronservices'],
}
