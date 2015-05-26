
$binpath = "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin"

# comment out heat domain related configurations
$heat_config = file('/etc/heat/heat.conf','/dev/null')
if($heat_config != '') {
    ini_setting { "heat stack_domain_admin_password":
        ensure            => absent,
        path              => '/etc/heat/heat.conf',
        section           => 'DEFAULT',
        key_val_separator => '=',
        setting           => 'stack_domain_admin_password',
        notify            => Service['openstack-heat-engine'],
    }
    ini_setting { "heat stack_domain_admin":
        ensure            => absent,
        path              => '/etc/heat/heat.conf',
        section           => 'DEFAULT',
        key_val_separator => '=',
        setting           => 'stack_domain_admin',
        notify            => Service['openstack-heat-engine'],
    }
    ini_setting { "heat stack_user_domain":
        ensure            => absent,
        path              => '/etc/heat/heat.conf',
        section           => 'DEFAULT',
        key_val_separator => '=',
        setting           => 'stack_user_domain',
        notify            => Service['openstack-heat-engine'],
    }
    ini_setting {"heat_deferred_auth_method":
        path              => '/etc/heat/heat.conf',
        section           => 'DEFAULT',
        setting           => 'deferred_auth_method',
        value             => 'password',
        ensure            => present,
        notify            => Service['openstack-heat-engine'],
    }
    service { 'openstack-heat-engine':
        ensure            => running,
        enable            => true,
        path              => $binpath,
    }
}

# assign ip to ivs internal port
define ivs_internal_port_ip {
    $port_ip = split($name, ',')
    file_line { "ifconfig ${port_ip[0]} ${port_ip[1]}":
        path  => '/etc/rc.d/rc.local',
        line  => "ifconfig ${port_ip[0]} ${port_ip[1]}",
        match => "^ifconfig ${port_ip[0]} ${port_ip[1]}$",
    }
}
# example ['storage,192.168.1.1/24', 'ex,192.168.2.1/24', 'management,192.168.3.1/24']
class ivs_internal_port_ips {
    $port_ips = [%(port_ips)s]
    file { "/etc/rc.d/rc.local":
        ensure  => file,
        mode    => 0777,
    }
    file_line { "restart ivs":
        require => File['/etc/rc.d/rc.local'],
        path    => '/etc/rc.d/rc.local',
        line    => "systemctl restart ivs",
        match   => "^systemctl restart ivs$",
    }
    ivs_internal_port_ip { $port_ips:
        require => File_line['restart ivs'],
    }
}
include ivs_internal_port_ips

# install and enable ntp
package { "ntp":
    ensure  => installed,
}
service { "ntpd":
    ensure  => running,
    enable  => true,
    path    => $binpath,
    require => Package['ntp'],
}

# make sure known_hosts is cleaned up
file { "/root/.ssh/known_hosts":
    ensure => absent,
}

# keystone paste config
ini_setting { "keystone paste config":
    ensure            => present,
    path              => '/etc/keystone/keystone.conf',
    section           => 'paste_deploy',
    key_val_separator => '=',
    setting           => 'config_file',
    value             => '/usr/share/keystone/keystone-dist-paste.ini',
}

# reserve keystone ephemeral port
exec { "reserve keystone port":
    command => "sysctl -w 'net.ipv4.ip_local_reserved_ports=49000,35357,41055,58882'",
    path    => $binpath,
}
file_line { "reserve keystone port":
    path  => '/etc/sysctl.conf',
    line  => 'net.ipv4.ip_local_reserved_ports=49000,35357,41055,58882',
    match => '^net.ipv4.ip_local_reserved_ports.*$',
}

# load 8021q module on boot
file {'/etc/sysconfig/modules/8021q.modules':
    ensure  => file,
    mode    => 0777,
    content => "modprobe 8021q",
}
exec { "load 8021q":
    command => "modprobe 8021q",
    path    => $binpath,
}

# install selinux policies
Package { allow_virtual => true }
class { selinux:
    mode => '%(selinux_mode)s'
}
selinux::module { 'selinux-bcf':
    ensure => 'present',
    source => 'puppet:///modules/selinux/centos.te',
}

# ivs configruation and service
file { '/etc/sysconfig/ivs':
    ensure  => file,
    mode    => 0644,
    content => "%(ivs_daemon_args)s",
    notify  => Service['ivs'],
}
service{ 'ivs':
    ensure  => running,
    enable  => true,
    path    => $binpath,
    require => Selinux::Module['selinux-bcf'],
}

# fix centos symbolic link problem for ivs debug logging
file { '/usr/lib64/debug':
   ensure => link,
   target => '/lib/debug',
}

# config neutron-bsn-agent service
ini_setting { "neutron-bsn-agent.service Description":
  ensure            => present,
  path              => '/usr/lib/systemd/system/neutron-bsn-agent.service',
  section           => 'Unit',
  key_val_separator => '=',
  setting           => 'Description',
  value             => 'OpenStack Neutron BSN Agent',
}
ini_setting { "neutron-bsn-agent.service ExecStart":
  notify            => File['/etc/systemd/system/multi-user.target.wants/neutron-bsn-agent.service'],
  ensure            => present,
  path              => '/usr/lib/systemd/system/neutron-bsn-agent.service',
  section           => 'Service',
  key_val_separator => '=',
  setting           => 'ExecStart',
  value             => '/usr/bin/neutron-bsn-agent --config-file /usr/share/neutron/neutron-dist.conf --config-file /etc/neutron/neutron.conf --config-file /etc/neutron/plugins/openvswitch/ovs_neutron_plugin.ini --log-file /var/log/neutron/neutron-bsn-agent.log',
}
file { '/etc/systemd/system/multi-user.target.wants/neutron-bsn-agent.service':
   ensure => link,
   target => '/usr/lib/systemd/system/neutron-bsn-agent.service',
   notify => Service['neutron-bsn-agent'],
}
service {'neutron-bsn-agent':
    ensure  => running,
    enable  => true,
    path    => $binpath,
    require => Selinux::Module['selinux-bcf'],
}

# purge bcf controller public key
exec { 'purge bcf key':
    command => "rm -rf /etc/neutron/plugins/ml2/host_certs/*",
    path    => $binpath,
    notify  => Service['neutron-server'],
}

# config /etc/neutron/neutron.conf
ini_setting { "neutron.conf service_plugins":
  ensure            => present,
  path              => '/etc/neutron/neutron.conf',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'service_plugins',
  value             => 'bsn_l3',
  notify            => Service['neutron-server'],
}
ini_setting { "neutron.conf dhcp_agents_per_network":
  ensure            => present,
  path              => '/etc/neutron/neutron.conf',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'dhcp_agents_per_network',
  value             => '2',
  notify            => Service['neutron-server'],
}

# config /etc/neutron/plugin.ini
ini_setting { "neutron plugin.ini firewall_driver":
  ensure            => present,
  path              => '/etc/neutron/plugin.ini',
  section           => 'securitygroup',
  key_val_separator => '=',
  setting           => 'firewall_driver',
  value             => 'neutron.agent.linux.iptables_firewall.OVSHybridIptablesFirewallDriver',
  notify            => Service['neutron-server'],
}
ini_setting { "neutron plugin.ini enable_security_group":
  ensure            => present,
  path              => '/etc/neutron/plugin.ini',
  section           => 'securitygroup',
  key_val_separator => '=',
  setting           => 'enable_security_group',
  value             => 'True',
  notify            => Service['neutron-server'],
}

# config /etc/neutron/dhcp_agent.ini
ini_setting { "dhcp agent interface driver":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'interface_driver',
  value             => 'neutron.agent.linux.interface.IVSInterfaceDriver',
  notify            => Service['neutron-dhcp-agent'],
}
ini_setting { "dhcp agent dhcp driver":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'dhcp_driver',
  value             => 'bsnstacklib.plugins.bigswitch.dhcp_driver.DnsmasqWithMetaData',
  notify            => Service['neutron-dhcp-agent'],
}
ini_setting { "dhcp agent enable isolated metadata":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_isolated_metadata',
  value             => 'True',
  notify            => Service['neutron-dhcp-agent'],
}
ini_setting { "dhcp agent disable metadata network":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_metadata_network',
  value             => 'False',
  notify            => Service['neutron-dhcp-agent'],
}
ini_setting { "dhcp agent disable dhcp_delete_namespaces":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'dhcp_delete_namespaces',
  value             => 'False',
  notify            => Service['neutron-dhcp-agent'],
}
file { '/etc/neutron/dnsmasq-neutron.conf':
  ensure            => file,
  content           => 'dhcp-option-force=26,1400',
  notify            => Service['neutron-dhcp-agent'],
}

# disable l3 agent
service { 'neutron-l3-agent':
  ensure  => stopped,
  enable  => false,
  path    => $binpath,
}
ini_setting { "l3 agent disable metadata proxy":
  ensure            => present,
  path              => '/etc/neutron/l3_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_metadata_proxy',
  value             => 'False',
}

# make sure metadata agent is running
service { 'neutron-metadata-agent':
  ensure  => running,
  enable  => true,
  path    => $binpath,
}

# config /etc/neutron/plugins/ml2/ml2_conf.ini 
ini_setting { "ml2 type dirvers":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'ml2',
  key_val_separator => '=',
  setting           => 'type_drivers',
  value             => 'vlan',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 tenant network types":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'ml2',
  key_val_separator => '=',
  setting           => 'tenant_network_types',
  value             => 'vlan',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 tenant network vlan ranges":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'ml2_type_vlan',
  key_val_separator => '=',
  setting           => 'network_vlan_ranges',
  value             => '%(network_vlan_ranges)s',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 mechanism drivers":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'ml2',
  key_val_separator => '=',
  setting           => 'mechanism_drivers',
  value             => 'bsn_ml2',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy ssl cert directory":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'ssl_cert_directory',
  value             => '/etc/neutron/plugins/ml2',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy servers":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'servers',
  value             => '%(bcf_controllers)s',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy server auth":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'server_auth',
  value             => '%(bcf_controller_user)s:%(bcf_controller_passwd)s',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy server ssl":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'server_ssl',
  value             => 'True',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy auto sync on failure":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'auto_sync_on_failure',
  value             => 'True',
  notify            => Service['neutron-server'],
}
ini_setting { "ml2 restproxy consistency interval":
  ensure            => present,
  path              => '/etc/neutron/plugins/ml2/ml2_conf.ini',
  section           => 'restproxy',
  key_val_separator => '=',
  setting           => 'consistency_interval',
  value             => 60,
  notify            => Service['neutron-server'],
}

# change ml2 ownership
file { '/etc/neutron/plugins/ml2':
  owner   => neutron,
  group   => neutron,
  recurse => true,
  notify  => Service['neutron-server'],
}

# stop and disable neutron-openvswitch-agent
service { 'neutron-openvswitch-agent':
  ensure  => stopped,
  enable  => false,
  path    => $binpath,
  require => Selinux::Module['selinux-bcf'],
}

# neutron-server and neutron-dhcp-agent
service { 'neutron-server':
  ensure  => running,
  enable  => true,
  path    => $binpath,
  require => [Selinux::Module['selinux-bcf'], Exec['purge bcf key']]
}
service { 'neutron-dhcp-agent':
  ensure  => running,
  enable  => true,
  path    => $binpath,
  require => Selinux::Module['selinux-bcf'],
}

# patch for packstack nova
package { "device-mapper-libs":
  ensure => latest,
}
