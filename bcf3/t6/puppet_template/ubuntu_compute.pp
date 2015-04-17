
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
    ivs_internal_port_ip { $port_ips:
    }->
    file_line { "add exit 0":
        path    => '/etc/rc.local',
        line    => "exit 0",
    }
}
include ivs_internal_port_ips

# ivs configruation and service
file_line { 'ivs daemon args':
    path    => '/etc/init/ivs.conf',
    line    => "%(ivs_daemon_args)s",
    match   => "^.*DAEMON_ARGS=.*$",
    notify  => Service['ivs'],
} 
service { 'ivs':
    ensure  => running,
    enable  => true,
    path    => $binpath,
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

# config neutron-bsn-agent service
file_line { "neutron-plugin-bsn-agent.conf remove start on neutron-ovs-cleanup":
    notify  => File['/etc/init.d/neutron-plugin-bsn-agent'],
    path    => '/etc/init/neutron-plugin-bsn-agent.conf',
    line    => 'start on neutron-ovs-cleanup or runlevel [2345]',
    ensure  => absent,
}
file_line { "neutron-plugin-bsn-agent.conf remove stop on runlevel":
    notify  => File['/etc/init.d/neutron-plugin-bsn-agent'],
    path    => '/etc/init/neutron-plugin-bsn-agent.conf',
    line    => 'stop on runlevel [!2345]',
    ensure  => absent,
}
file_line { "neutron-plugin-bsn-agent.conf exec":
    notify  => File['/etc/init.d/neutron-plugin-bsn-agent'],
    path    => '/etc/init/neutron-plugin-bsn-agent.conf',
    line    => 'exec start-stop-daemon --start --chuid neutron --exec /usr/bin/neutron-plugin-bsn-agent --config-file=/etc/neutron/neutron.conf --config-file=/etc/neutron/plugin.ini --log-file=/var/log/neutron/bsn-agent.log',
    match   => '^exec start-stop-daemon --start.*$',
}
file { '/etc/init.d/neutron-plugin-bsn-agent':
    ensure => link,
    target => '/lib/init/upstart-job',
    notify => Service['neutron-plugin-bsn-agent'],
}
service {'neutron-plugin-bsn-agent':
    ensure  => running,
    enable  => true,
    path    => $binpath,
}

# stop and disable neutron-plugin-openvswitch-agent
service { 'neutron-plugin-openvswitch-agent':
  ensure  => stopped,
  enable  => false,
  path    => $binpath,
}
