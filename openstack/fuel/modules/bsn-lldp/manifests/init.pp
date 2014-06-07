include apt


class bsn-lldp {
        $bond_interfaces = 'eth0,eth1'

	file { "/etc/default/lldpd" :
		ensure => present,
		owner => root, group => root, mode => 0644,
		content => "DAEMON_ARGS='-S 5c:16:c7:00:00:00 -I ${bond_interfaces}'\n",
                notify => Service['lldpd'],
	}

        package { "lldpd":
		ensure => installed,
	}

	service { "lldpd":
    		ensure  => "running",
    		enable  => "true",
    		require => Package["lldpd"],
	}

	apt::source { "puppetlabs_precise":
		location        => "http://apt.puppetlabs.com/",
		release         => "precise",
		repos           => "main",
		include_src     => false
	}

	apt::source { "ubuntu_archiv_precise":
		location        => "http://us.archive.ubuntu.com/ubuntu",
		release         => "precise",
		repos           => "main restricted universe multiverse",
		include_src     => true
	}

	apt::source { "ubuntu_archiv_precise-update":
		location        => "http://us.archive.ubuntu.com/ubuntu",
		release         => "precise-updates",
		repos           => "main restricted universe multiverse",
		include_src     => true
	}

	apt::source { "ubuntu_archiv_precise-backports":
		location        => "http://us.archive.ubuntu.com/ubuntu",
		release         => "precise-backports",
		repos           => "main restricted universe multiverse",
		include_src     => true
	}

	apt::source { "ubuntu_archiv_precise-security":
		location        => "http://us.archive.ubuntu.com/ubuntu",
		release         => "precise-security",
		repos           => "main restricted universe multiverse",
		include_src     => true
	}
}

