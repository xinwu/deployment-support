
$binpath = "/usr/local/bin/:/bin/:/usr/bin:/usr/sbin:/usr/local/sbin:/sbin"

# ivs configruation and service
file{'/etc/sysconfig/ivs':
    ensure  => file,
    mode    => 0644,
    content => "%(ivs_daemon_args)s",
    notify  => Service['ivs'],
} 
service{'ivs':
    ensure => running,
    enable => true,
    path   => $binpath,
}

# set selinux to permissive mode
ini_setting { "selinux permissive":
  ensure            => present,
  path              => '/etc/selinux/config',
  section           => '',
  key_val_separator => '=',
  setting           => 'SELINUX',
  value             => 'permissive',
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
   ensure => 'link',
   target => '/usr/lib/systemd/system/neutron-bsn-agent.service',
   notify => Service['neutron-bsn-agent'],
}
service{'neutron-bsn-agent':
    ensure => running,
    enable => true,
    path   => $binpath,
}

# stop and disable neutron-openvswitch-agent
service { 'neutron-openvswitch-agent':
  ensure => stopped,
  enable => false,
  path   => $binpath,
}

