
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
}
file_line { "neutron-bsn-agent.conf exec":
    notify  => File['/etc/init.d/neutron-bsn-agent'],
    path    => '/etc/init/neutron-bsn-agent.conf',
    line    => 'exec start-stop-daemon --start --chuid neutron --exec /usr/local/bin/neutron-bsn-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/plugin.ini --log-file=/var/log/neutron/neutron-bsn-agent.log',
    match   => '^exec start-stop-daemon --start.*$',
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

# make sure dhcp and metadata agent
# are not running on compute node
ini_setting { "dhcp agent disable metadata network":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_metadata_network',
  value             => 'False',
}
ini_setting { "dhcp agent enable isolated metadata":
  ensure            => present,
  path              => '/etc/neutron/dhcp_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_isolated_metadata',
  value             => 'True',
}
ini_setting { "l3 agent disable metadata proxy":
  ensure            => present,
  path              => '/etc/neutron/l3_agent.ini',
  section           => 'DEFAULT',
  key_val_separator => '=',
  setting           => 'enable_metadata_proxy',
  value             => 'False',
}

