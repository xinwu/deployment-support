
$binpath = "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin"

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

# install selinux policies
Package { allow_virtual => true }
class { selinux:
  mode => '%(selinux_mode)s'
}
selinux::module { 'selinux-bcf':
  ensure => 'present',
  source => 'puppet:///modules/selinux/centos.te',
}

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

# ivs configruation and service
file{'/etc/sysconfig/ivs':
    ensure  => file,
    mode    => 0644,
    content => "%(ivs_daemon_args)s",
    notify  => Service['ivs'],
} 
service{'ivs':
    ensure  => running,
    enable  => true,
    path    => $binpath,
    require => Selinux::Module['selinux-bcf'],
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
service{'neutron-bsn-agent':
    ensure  => running,
    enable  => true,
    path    => $binpath,
    require => Selinux::Module['selinux-bcf'],
}

# stop and disable neutron-openvswitch-agent
service { 'neutron-openvswitch-agent':
  ensure  => stopped,
  enable  => false,
  path    => $binpath,
  require => Selinux::Module['selinux-bcf'],
}

# patch for packstack nova
package { "device-mapper-libs":
  ensure => latest,
  notify => Service['libvirtd'],
}
service { "libvirtd":
  ensure  => running,
  enable  => true,
  path    => $binpath,
  notify  => Service['openstack-nova-compute'],
}
service { "openstack-nova-compute":
  ensure  => running,
  enable  => true,
  path    => $binpath,
}

# disable l3 agent
ini_setting { "l3 agent disable metadata proxy":
  ensure            => present,
  path              => '/etc/neutron/l3_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_metadata_proxy',
  value             => 'False',
}
ini_setting { "dhcp agent disable dhcp_delete_namespaces":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'dhcp_delete_namespaces',
  value             => 'False',
}
file { '/etc/neutron/dnsmasq-neutron.conf':
  ensure            => file,
  content           => 'dhcp-option-force=26,1400',
}

