
$binpath = "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin"

# assign ip to ivs internal port
define ivs_internal_port_ip {
    $port_ip = split($name, ',')
    file_line { "ifconfig ${port_ip[0]} ${port_ip[1]}":
        path  => '/etc/rc.local',
        line  => "ifconfig ${port_ip[0]} ${port_ip[1]}",
        match => "^ifconfig ${port_ip[0]} ${port_ip[1]}$",
    }
}
# example ['storage,192.168.1.1/24', 'ex,192.168.2.1/24', 'management,192.168.3.1/24']
class ivs_internal_port_ips {
    $port_ips = [%(port_ips)s]
    $setup_node_ip = "%(setup_node_ip)s"
    file { "/etc/rc.local":
        ensure  => file,
        mode    => 0777,
    }->
    file_line { "remove exit 0":
        path    => '/etc/rc.local',
        ensure  => absent,
        line    => "exit 0",
    }->
    file_line { "restart ivs":
        path    => '/etc/rc.local',
        line    => "service ivs restart",
        match   => "^service ivs restart$",
    }->
    file_line { "sleep 2":
        path    => '/etc/rc.local',
        line    => "sleep 2",
        match   => "^sleep 2$",
    }->
    ivs_internal_port_ip { $port_ips:
    }->
    file_line { "clear default gw":
        path    => '/etc/rc.local',
        line    => "ip route del default",
        match   => "^ip route del default$",
    }->
    file_line { "add default gw":
        path    => '/etc/rc.local',
        line    => "ip route add default via ${setup_node_ip}",
        match   => "^ip route add default via ${setup_node_ip}$",
    }->
    file_line { "add exit 0":
        path    => '/etc/rc.local',
        line    => "exit 0",
    }
}
include ivs_internal_port_ips

# install and enable ntp
package { "ntp":
    ensure  => installed,
}
service { "ntp":
    ensure  => running,
    enable  => true,
    require => Package['ntp'],
}

# ivs configruation and service
file { '/etc/default/ivs':
    ensure  => file,
    mode    => 0644,
    content => "%(ivs_daemon_args)s",
    notify  => Service['ivs'],
}
service { 'ivs':
    ensure     => 'running',
    provider   => 'upstart',
    hasrestart => 'true',
    hasstatus  => 'true',
    subscribe  => File['/etc/default/ivs'],
}

# load 8021q module on boot
package { 'vlan':
    ensure  => latest,
}
file_line {'load 8021q on boot':
    path    => '/etc/modules',
    line    => '8021q',
    match   => '^8021q$',
    require => Package['vlan'],
}
exec { "load 8021q":
    command => "modprobe 8021q",
    path    => $binpath,
    require => Package['vlan'],
}

# config neutron-bsn-agent conf
file { '/etc/init/neutron-bsn-agent.conf':
    ensure => present,
    content => "
description \"Neutron BSN Agent\"
start on runlevel [2345]
stop on runlevel [!2345]
respawn
script
    exec /usr/local/bin/neutron-bsn-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/plugins/ml2/ml2_conf.ini --log-file=/var/log/neutron/neutron-bsn-agent.log
end script
",
}
file { '/etc/init.d/neutron-bsn-agent':
    ensure => link,
    target => '/lib/init/upstart-job',
    notify => Service['neutron-bsn-agent'],
}
service {'neutron-bsn-agent':
    ensure     => 'running',
    provider   => 'upstart',
    hasrestart => 'true',
    hasstatus  => 'true',
    subscribe  => [File['/etc/init/neutron-bsn-agent.conf'], File['/etc/init.d/neutron-bsn-agent']],
}

# stop and disable neutron-plugin-openvswitch-agent
service { 'neutron-plugin-openvswitch-agent':
  ensure   => 'stopped',
  enable   => false,
  provider => 'upstart',
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

