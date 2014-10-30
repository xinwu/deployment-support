# Copyright 2014 Big Switch Networks, Inc.
# All Rights Reserved.
#
# This script requires sshpass python-yaml, python-pip,
# python-dev and concurrent.futures on the patch node.
# It also requires ssh on all nodes, i.e.,
# sudo apt-get install -y sshpass python-yaml python-pip python-dev (on patch node)
# sudo pip install futures subprocess32 (on patch node)
# sudo apt-get install -y ssh (on all nodes)

'''
# Following is an example data structure 
# after parsing yaml configuration

example_config = dict(
    nodes = [
        dict(
            hostname = '172.16.54.130',
            role = ROLE_MGMT,
        ),
        dict(
            hostname = '172.16.54.132',
        ),
        dict(
            hostname = '172.16.54.134',
            node_username: username,
            node_password: password,
            pxe_interface: 'eth9',
            bond_interface = dict(
                interfaces = ['eth3','eth4'],
                name = 'bond1',
            ),
        ),
    ],

    mysql_root_pwd = 'bsn',
    cloud_db_pwd = 'bsn',
    management_vlan = 6,
    storage_vlan = 7,
    public_vlan = 5,
    guest_vlan = None,
    default_pxe_interface: 'eth0',
    default_node_username: 'bsn',
    default_node_password: 'bsn',
    default_role = ROLE_COMPUTE,
    default_bond_interface = dict(
        interfaces = ['eth1','eth2'],
        name = 'bond0',
    ),
)
'''

import os
import sys
import yaml
import time
import string
import Queue
import logging
import argparse
import threading
import collections
import subprocess32 as subprocess
from sets import Set
from threading import Lock

LOG_FILENAME = '/tmp/cloudstack_deploy.log'
logging.basicConfig(filename=LOG_FILENAME,level=logging.DEBUG)


RELEASE_NAME = 'IronHorse+'

# A cloudstack node can be either management or compute,
# There is by default only one management node.
ROLE_MGMT    = 'management'
ROLE_COMPUTE = 'compute'

# Maximum number of workers to deploy to nodes concurrently
MAX_WORKERS = 10

# undef string for puppet
UNDEF = ''

# cloud stack packages
CS_VERSION = '4.5.0'
CS_URL    = ('http://jenkins.bigswitch.com/job/cloudstack_ihplus_4.5/lastSuccessfulBuild/artifact')
CS_COMMON = ('cloudstack-common_%(cs_version)s-snapshot_all.deb' % {'cs_version' : CS_VERSION})
CS_MGMT   = ('cloudstack-management_%(cs_version)s-snapshot_all.deb' % {'cs_version' : CS_VERSION})
CS_AGENT  = ('cloudstack-agent_%(cs_version)s-snapshot_all.deb' % {'cs_version' : CS_VERSION})

STORAGE_SCRIPT = '/usr/share/cloudstack-common/scripts/storage/secondary/cloud-install-sys-tmplt'
STORAGE_VM_URL = ('http://jenkins.buildacloud.org/view/master/job/'
                  'build-systemvm-master/lastSuccessfulBuild/artifact/'
                  'tools/appliance/dist')
STORAGE_VM_TEMPLATE = 'systemvmtemplate-master-kvm.qcow2.bz2'

# management node puppet template
MGMT_PUPPET = r'''
$user           = "%(user)s"
$mysql_root_pwd = "%(mysql_root_pwd)s"
$cloud_db_pwd   = "%(cloud_db_pwd)s"
$distro         = 'precise'
$cs_url         = "%(cs_url)s"
$cs_common      = "%(cs_common)s"
$cs_mgmt        = "%(cs_mgmt)s"
$storage_script = "%(storage_script)s"
$storage_vm_url = "%(storage_vm_url)s"
$storage_vm_template = "%(storage_vm_template)s"

class { 'apt':
    always_apt_update => true,
}

file_line {'mvn3_deb':
    path    => '/etc/apt/sources.list',
    line    => "deb http://ppa.launchpad.net/natecarlson/maven3/ubuntu ${distro} main",
    match   => "^deb http://ppa.launchpad.net/natecarlson/maven3/ubuntu.*$",
    require => File['/etc/apt/sources.list'],
}

file_line {'mvn3_src_deb':
    path    => '/etc/apt/sources.list',
    line    => "deb-src http://ppa.launchpad.net/natecarlson/maven3/ubuntu ${distro} main",
    match   => "^deb-src http://ppa.launchpad.net/natecarlson/maven3/ubuntu.*$",
    require => File['/etc/apt/sources.list'],
}

exec {"update":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "apt-get update",
    require => [File_Line['mvn3_deb'],
                File_line['mvn3_src_deb']],
}


package {[
    'ethtool',
    'dbus',
    'qemu-kvm',
    'ubuntu-vm-builder',
    'nfs-kernel-server',
    'mysql-server',
    'mysql-client',
    'openjdk-7-jdk',
    'python-software-properties',
    'debhelper',
    'tomcat6',
    'genisoimage',
    'python-mysqldb',
    'augeas-lenses',
    'libaugeas0',
    'libcommons-daemon-java',
    'jsvc',
    'libmysql-java',
    'python-paramiko',
    'augeas-tools',
    ]:
    ensure  => installed,
    require => Exec['update'],
}

exec {'update jdk':
    subscribe   => Package["openjdk-7-jdk"],
    refreshonly => true,
    path        => "/bin:/usr/bin:/usr/sbin",
    command     => "update-java-alternatives -s java-1.7.0-openjdk-amd64",
}

exec {"set mysql password":
    subscribe   => Package["mysql-server"],
    refreshonly => true,
    path        => "/bin:/usr/bin",
    command     => "mysqladmin -uroot password $mysql_root_pwd",
}

exec {"config ufw":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow mysql",
}

exec {"accept iptables input":
    path    => "/sbin:/usr/share",
    command => "iptables --policy INPUT ACCEPT",
}

exec {"accept iptables output":
    path    => "/sbin:/usr/share",
    command => "iptables --policy OUTPUT ACCEPT",
}

exec {"accept iptables forward":
    path    => "/sbin:/usr/share",
    command => "iptables --policy FORWARD ACCEPT",
}


file {"/etc/mysql/conf.d/cloudstack.cnf":
    ensure  => present,
    owner   => root,
    group   => root,
    mode    => 0644,
    content => "
[mysqld]
innodb_rollback_on_timeout=1
innodb_lock_wait_timeout=600
max_connections=350
log-bin=mysql-bin
binlog-format = 'ROW'
",
    notify  => Service['mysql'],
}

file {"/export":
    ensure => "directory",
    owner  => root,
    group  => root,
    mode   => 0666,
}

file {"/export/primary":
    ensure  => "directory",
    owner   => root,
    group   => root,
    mode    => 0666,
    require => File['/export'],
}

file {"/export/secondary":
    ensure  => "directory",
    owner   => root,
    group   => root,
    mode    => 0666,
    require => File['/export'],
}


file {'/etc/exports':
    ensure  => present,
}

file_line {'config primary':
    path    => '/etc/exports',  
    line    => '/export/primary *(rw,async,no_root_squash,no_subtree_check)',
    match   => "^/export/primary.*$",
    require => File['/etc/exports'],
}

file_line {'config secondary':
    path    => '/etc/exports',
    line    => '/export/secondary *(rw,async,no_root_squash,no_subtree_check)',
    match   => "^/export/secondary.*$",
    require => File['/etc/exports'],
}


service {'mysql':
    ensure  => running,
    require => Package["mysql-server"],
}

exec {'export nfs':
    require     => Package['nfs-kernel-server'],
    subscribe   => [File_Line["config primary"],
                    File_Line["config secondary"]],
    refreshonly => true,
    path        => "/bin:/usr/bin:/usr/sbin:/sbin",
    command     => "exportfs -a",
}

exec {"install maven3":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "apt-get install -fy --force-yes maven3",
    require => Exec['update jdk'],
    returns => [0, 100],
}

exec {"wget cloudstack common":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "wget $cs_url/$cs_common -O /home/$user/bcf/$cs_common",
    creates => "/home/$user/bcf/$cs_common",
    timeout => 1200,
}

exec {"wget cloudstack management":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "wget $cs_url/$cs_mgmt -O /home/$user/bcf/$cs_mgmt",
    creates => "/home/$user/bcf/$cs_mgmt",
    timeout => 1200,
}

exec {"dpkg common":
    require => [Exec['wget cloudstack common'],
                Exec["install maven3"],
                Exec['export nfs'],
                Package['tomcat6'],
                Package['jsvc'],
                Package['qemu-kvm'],
                Package['ubuntu-vm-builder'],
                Package['mysql-server'],
                Package['ethtool'],
                Package['mysql-client'],
                Package['openjdk-7-jdk'],
                Package['python-software-properties'],
                Package['debhelper'],
                Package['genisoimage'],
                Package['python-mysqldb'],
                Package['augeas-lenses'],
                Package['libaugeas0'],
                Package['libcommons-daemon-java'],
                Package['libmysql-java'],
                Package['python-paramiko'],
                Package['augeas-tools']],
    user    => root,
    path    => "/bin:/usr/bin:/usr/sbin:/sbin",
    command => "dpkg -i /home/$user/bcf/$cs_common",
    returns => [0],
}

exec {"dpkg management":
    require => [Exec['wget cloudstack common'],
                Exec['wget cloudstack management'],
                Exec['dpkg common']],
    user    => root,
    path    => "/bin:/usr/bin:/usr/sbin:/sbin",
    command => "dpkg -i /home/$user/bcf/$cs_mgmt",
    returns => [0],
}

exec {"install cloudstack":
    require => Exec['dpkg management'],
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "apt-get -fy install",
}

service {"dbus":
    require => Package['dbus'],
    ensure  => running,
    enable  => true,
}

exec {"setup-databases":
    require => [Exec['install cloudstack'],
                Package['mysql-server']],
    notify  => [Service['mysql'], Exec['run cloudstack']],
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "bash /home/%(user)s/bcf/db.sh >>/home/%(user)s/bcf/management.log 2>&1",
}

exec {"run cloudstack":
    notify  => Service['cloudstack-management'],
    require => [Exec['setup-databases'],
                Service['dbus']],
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "cloudstack-setup-management",
    returns => [0],
}

service {"tomcat6":
    require => Package['tomcat6'],
    ensure  => running,
    enable  => true,
}

service {"cloudstack-management":
    require => Exec['install cloudstack'],
    ensure  => running,
    enable  => true,
}

exec {"wget storage_vm_template":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "wget $storage_vm_url/$storage_vm_template -O /home/$user/bcf/$storage_vm_template",
    creates => "/home/$user/bcf/$storage_vm_template",
    timeout => 1800,
}

exec {"install storage_vm_template":
    require => [Exec['wget storage_vm_template'],
                Exec['run cloudstack'],
                Service["cloudstack-management"]],
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "bash /usr/share/cloudstack-common/scripts/storage/secondary/cloud-install-sys-tmplt -m /export/secondary -f /home/$user/bcf/$storage_vm_template -h kvm -F",
}
'''

# compute node puppet template
COMPUTE_PUPPET = r'''

$user       = "%(user)s"
$distro     = 'precise'
$cs_url     = "%(cs_url)s"
$cs_common  = "%(cs_common)s"
$cs_agent   = "%(cs_agent)s"


class {'apt':
    always_apt_update => true,
}

file_line {'backports_deb':
    path    => '/etc/apt/sources.list',
    line    => "deb http://ppa.launchpad.net/pfak/backports/ubuntu ${distro} main",
    match   => "^deb http://ppa.launchpad.net/pfak/backports/ubuntu.*$",
    require => File['/etc/apt/sources.list'],
}

file_line {'backports_src_deb':
    path    => '/etc/apt/sources.list',
    line    => "deb-src http://ppa.launchpad.net/pfak/backports/ubuntu ${distro} main",
    match   => "^deb-src http://ppa.launchpad.net/pfak/backports/ubuntu.*$",
    require => File['/etc/apt/sources.list'],
}

exec {"update":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "apt-get update",
    require => [File_Line['backports_deb'],
                File_line['backports_src_deb']],
}

package {[
    'ethtool',
    'dbus',
    'qemu-kvm',
    'ubuntu-vm-builder',
    'openjdk-7-jre',
    'libcommons-daemon-java',
    'jsvc',
    'ipset',
    'python-software-properties',
    'nfs-common',
    'aptitude',
    'genisoimage',
    ]:
    ensure  => 'installed',
    require => Exec['update'],
    notify  => Service['libvirt-bin']
}->

file {'/etc/libvirt/qemu.conf':
    ensure  => present,
}

file_line {'config user':
    path    => '/etc/libvirt/qemu.conf',  
    line    => "user=\"root\"",
    match   => "^user=.*$",
    require => File['/etc/libvirt/qemu.conf'],
}

file_line {'config group':
    path    => '/etc/libvirt/qemu.conf',
    line    => "group=\"root\"",
    match   => "^group=.*$",
    require => File['/etc/libvirt/qemu.conf'],
}

exec {"allow tcp 22":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow proto tcp from any to any port 22",
}

exec {"allow tcp 1798":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow proto tcp from any to any port 1798",
}

exec {"allow tcp 16509":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow proto tcp from any to any port 16509",
}

exec {"allow tcp 5900:6100":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow proto tcp from any to any port 5900:6100",
}

exec {"allow tcp 49152:49216":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "ufw allow proto tcp from any to any port 49152:49216",
}

exec {"accept iptables input":
    path    => "/sbin:/usr/share",
    command => "iptables --policy INPUT ACCEPT",
}

exec {"accept iptables output":
    path    => "/sbin:/usr/share",
    command => "iptables --policy OUTPUT ACCEPT",
}

exec {"accept iptables forward":
    path    => "/sbin:/usr/share",
    command => "iptables --policy FORWARD ACCEPT",
}

service {"libvirt-bin":
    ensure  => running,
    require => [File_Line['config user'],
                File_Line['config group']],
}

exec {"wget cloudstack common":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "wget $cs_url/$cs_common -O /home/$user/bcf/$cs_common",
    creates => "/home/$user/bcf/$cs_common",
    timeout => 1200,
}

exec {"wget cloudstack agent":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "wget $cs_url/$cs_agent -O /home/$user/bcf/$cs_agent",
    creates => "/home/$user/bcf/$cs_agent",
    timeout => 1200,
}

exec {"dpkg common":
    require => [Exec['wget cloudstack common'],
                Package['ethtool'],
                Package['qemu-kvm'],
                Package['ubuntu-vm-builder'],
                Package['openjdk-7-jre'],
                Package['libcommons-daemon-java'],
                Package['jsvc'],
                Package['ipset'],
                Package['python-software-properties'],
                Package['nfs-common'],
                Package['aptitude'],
                Package['genisoimage'],
                Service["libvirt-bin"]],
    user    => root,
    path    => "/bin:/usr/bin:/usr/sbin:/sbin",
    command => "dpkg -i /home/$user/bcf/$cs_common",
    returns => [0],
}

exec {"dpkg agent":
    require => [Exec['wget cloudstack common'],
                Exec['wget cloudstack agent'],
                Exec['dpkg common']],
    user    => root,
    path    => "/bin:/usr/bin:/usr/sbin:/sbin",
    command => "dpkg -i /home/$user/bcf/$cs_agent",
    returns => [0],
}

exec {"install cloudstack":
    require => Exec['dpkg agent'],
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "apt-get -fy install",
}

service {"dbus":
    require => Package['dbus'],
    ensure  => running,
    enable  => true,
}

service {"cloudstack-agent":
    require => [Exec['install cloudstack'],
                Service['dbus']],
    enable  => true,
}
'''

LLDP_PUPPET = r'''
$bond_interfaces = '%(bond_interfaces)s'

file {"/etc/default/lldpd" :
    require => Exec['rm /var/run/lldpd.socket'],
    ensure  => present,
    owner   => root,
    group   => root,
    mode    => 0644,
    content => "DAEMON_ARGS='-S 5c:16:c7:00:00:00 -I ${bond_interfaces}'\n",
    notify  => Service['lldpd'],
}

file {'/etc/modules':
    ensure  => present,
}

file_line {'config bonding':
    path    => '/etc/modules',
    line    => "bonding",
    match   => "^bonding$",
    require => File['/etc/modules'],
}

file_line {'config vlan':
    path    => '/etc/modules',
    line    => "8021q",
    match   => "^8021q$",
    require => File['/etc/modules'],
}

file_line {'config loop':
    path    => '/etc/modules',
    line    => "loop",
    match   => "^loop$",
    require => File['/etc/modules'],
}

package {["lldpd", "vlan", "ifenslave"]:
    ensure => installed,
}

exec {'rm /var/run/lldpd.socket':
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "rm -rf /var/run/lldpd.socket",
    require => Package[lldpd],
}

exec {"start lldpd":
    path    => "/bin:/usr/bin:/usr/sbin",
    command => "/etc/init.d/lldpd start",
    require => [Package['lldpd'],
                File['/etc/default/lldpd']],
}

service {"lldpd":
    ensure  => running,
    enable  => true,
    require => Exec['start lldpd'],
}

apt::source {"puppetlabs_precise":
    location        => "http://apt.puppetlabs.com/",
    release         => "precise",
    repos           => "main",
    include_src     => false
}

apt::source {"ubuntu_archiv_precise":
    location        => "http://us.archive.ubuntu.com/ubuntu",
    release         => "precise",
    repos           => "main restricted universe multiverse",
    include_src     => true
}

apt::source {"ubuntu_archiv_precise-update":
    location        => "http://us.archive.ubuntu.com/ubuntu",
    release         => "precise-updates",
    repos           => "main restricted universe multiverse",
    include_src     => true
}

apt::source {"ubuntu_archiv_precise-backports":
    location        => "http://us.archive.ubuntu.com/ubuntu",
    release         => "precise-backports",
    repos           => "main restricted universe multiverse",
    include_src     => true
}

apt::source {"ubuntu_archiv_precise-security":
    location        => "http://us.archive.ubuntu.com/ubuntu",
    release         => "precise-security",
    repos           => "main restricted universe multiverse",
    include_src     => true
}
'''

DB_BASH = r'''
#!/bin/bash
mysql -uroot -p%(mysql_root_pwd)s -e "DROP DATABASE cloud; DROP DATABASE cloud_usage; DROP USER cloud@localhost;"
cloudstack-setup-databases cloud:%(cloud_db_pwd)s@localhost --deploy-as=root:%(mysql_root_pwd)s -i %(hostname)s
'''

NODE_REMOTE_BASH = r'''
#!/bin/bash
cp /home/%(user)s/bcf/%(role)s.intf /etc/network/interfaces
apt-get install -fy puppet aptitude --force-yes
wget http://apt.puppetlabs.com/puppetlabs-release-precise.deb -O /home/%(user)s/bcf/puppetlabs-release-precise.deb
dpkg -i /home/%(user)s/bcf/puppetlabs-release-precise.deb
apt-get update
puppet resource package puppet ensure=latest
apt-get install -fy qemu-kvm libvirt-bin ubuntu-vm-builder bridge-utils
adduser `id -un` libvirtd
version="$(virsh --version)"
if [[ "$version" < "1.0.2" ]]; then
    apt-get install -fy python-software-properties
    add-apt-repository ppa:pfak/backports -y
    apt-get update -fy
    aptitude update -fy
    aptitude -fy safe-upgrade
    service libvirt-bin restart
fi
apt-get -fy install --fix-missing
puppet module install puppetlabs-apt --force
puppet module install puppetlabs-stdlib --force
puppet apply -d -v -l /home/%(user)s/bcf/%(role)s.log /home/%(user)s/bcf/%(role)s.pp
role="%(role)s"
if [[ "$role" == "management" ]]; then
    service cloudstack-management stop
    mysql -uroot -p%(mysql_root_pwd)s -e "DROP DATABASE cloud; DROP DATABASE cloud_usage; DROP USER cloud@localhost;"
    cloudstack-setup-databases cloud:%(cloud_db_pwd)s@localhost --deploy-as=root:%(mysql_root_pwd)s -i %(hostname)s
    service mysql stop
    service mysql start
    cloudstack-setup-management   
    service cloudstack-management start
fi
DEBIAN_FRONTEND=noninteractive aptitude install -y -q iptables-persistent
apt-get -fy install --fix-missing
reboot
'''

NODE_LOCAL_BASH = r'''
#!/bin/bash
echo -e "Start to deploy %(role)s node %(hostname)s...\n"
sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s >> %(log)s 2>&1 "echo %(pwd)s | sudo -S mkdir -m 0777 -p /home/%(user)s/bcf"
echo -e "Copy /etc/network/interfaces to node %(hostname)s\n"
sshpass -p %(pwd)s scp /tmp/%(hostname)s.intf %(user)s@%(hostname)s:/home/%(user)s/bcf/%(role)s.intf >> %(log)s 2>&1
echo -e "Copy %(role)s.pp to node %(hostname)s\n"
sshpass -p %(pwd)s scp /tmp/%(hostname)s.pp %(user)s@%(hostname)s:/home/%(user)s/bcf/%(role)s.pp >> %(log)s 2>&1
if [ -f /tmp/%(hostname)s.db.sh ]; then
    echo -e "Copy db.sh to node %(hostname)s\n"
    sshpass -p %(pwd)s scp /tmp/%(hostname)s.db.sh %(user)s@%(hostname)s:/home/%(user)s/bcf/db.sh >> %(log)s 2>&1
fi
echo -e "Copy %(role)s.sh to node %(hostname)s\n"
sshpass -p %(pwd)s scp /tmp/%(hostname)s.remote.sh %(user)s@%(hostname)s:/home/%(user)s/bcf/%(role)s.sh >> %(log)s 2>&1
echo -e "Run %(role)s.sh on node %(hostname)s\n"
sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s >> %(log)s 2>&1 "echo %(pwd)s | sudo -S bash /home/%(user)s/bcf/%(role)s.sh"
echo -e "Finish deploying %(role)s on %(hostname)s\n"
'''

class Node(object):
    def __init__(self, node_config):
        self.hostname = node_config['hostname']
        if type(self.hostname) in (tuple, list):
            self.hostname = self.hostname[0]
        self.pxe_interface = node_config['pxe_interface']
        if type(self.pxe_interface) in (tuple, list):
            self.pxe_interface = self.pxe_interface[0]
        self.pxe_gw = node_config['pxe_gw']
        if type(self.pxe_gw) in (tuple, list):
            self.pxe_gw = self.pxe_gw[0]
        self.node_username = node_config['node_username']
        if type(self.node_username) in (tuple, list):
            self.node_username = self.node_username[0]
        self.node_password = node_config['node_password']
        if type(self.node_password) in (tuple, list):
            self.node_password = self.node_password[0]
        self.role = node_config['role']
        if type(self.role) in (tuple, list):
            self.role = self.role[0]
        self.bond_interfaces = node_config['bond_interface']['interfaces']
        self.bond_name = node_config['bond_interface']['name']
        if type(self.bond_name) in (tuple, list):
            self.bond_name = self.bond_name[0]
        self.mysql_root_pwd = node_config['mysql_root_pwd']
        if type(self.mysql_root_pwd) in (tuple, list):
            self.mysql_root_pwd = self.mysql_root_pwd[0]
        self.cloud_db_pwd = node_config['cloud_db_pwd']
        if type(self.cloud_db_pwd) in (tuple, list):
            self.cloud_db_pwd = self.cloud_db_pwd[0]
        self.bridges = node_config['bridges']


def generate_interface_config(node):
    config =  ('auto lo\n'
               '  iface lo inet loopback\n\n')
    config += ('auto %(pxe_intf)s\n'
               '  iface %(pxe_intf)s inet dhcp\n'
               '  up route add default gw %(pxe_gw)s\n\n' %
              {'pxe_intf' : node.pxe_interface,
               'pxe_gw'   : node.pxe_gw})
    for intf in node.bond_interfaces:
        config += ('auto %(intf)s\n'
                   '  iface %(intf)s inet manual\n'
                   '  bond-master %(bond)s\n\n' %
                   {'intf' : intf, 'bond' : node.bond_name})
    config += ('auto %(bond)s\n'
               '  iface %(bond)s inet manual\n'
               '  bond-mode 0\n'
               '  bond-slaves none\n'
               '  bond-miimon 50\n\n' %
               {'bond' : node.bond_name})

    for bridge in node.bridges:
        name = bridge['name']
        if type(name) in (tuple, list):
            name = name[0]
        vlan = bridge['vlan']
        if type(vlan) in (tuple, list):
            vlan = vlan[0]
        inet = bridge['inet']
        if type(inet) in (tuple, list):
            inet = inet[0]

        port_name = node.bond_name
        if vlan:
            port_name = ('%(bond)s.%(vlan)s' % 
                        {'vlan' : vlan,
                         'bond' : node.bond_name})
            if node.role == ROLE_MGMT:
                config += ('auto %(port_name)s\n'
                           '  iface %(port_name)s inet %(inet)s\n'
                           '  vlan-raw-device %(bond)s\n\n' %
                          {'port_name' : port_name,
                           'bond'      : node.bond_name,
                           'inet'      : inet})
            else:
                config += ('auto %(port_name)s\n'
                           '  iface %(port_name)s inet manual\n'
                           '  vlan-raw-device %(bond)s\n\n' %
                          {'port_name' : port_name,
                           'bond'      : node.bond_name})
 
        if node.role == ROLE_COMPUTE:
            config += ('auto %(name)s\n'
                       '  iface %(name)s inet %(inet)s\n'
                       '  bridge_ports %(port_name)s\n'
                       '  bridge_stp off\n'
                       '  up /sbin/ifconfig $IFACE up || /bin/true\n\n' %
                       {'name'      : name,
                        'port_name' : port_name,
                        'inet'      : inet})

    with open('/tmp/%s.intf' % node.hostname, "w") as config_file:
        config_file.write(config)
        config_file.close()


# print in python is not thread safe
print_lock = Lock()
def safe_print(message):
    with print_lock:
        message = ''.join(filter(lambda x: x in string.printable, message))
        sys.stdout.write(message)
        sys.stdout.flush()

def read_output(pipe, func):
    for lines in iter(pipe.readline, ''):
        for line in lines.splitlines(True):
            func(line.lstrip())
    pipe.close()

# queue to store all stdout and stderr
msg_q = Queue.Queue()
def write_output():
    while True:
        line = msg_q.get()
        safe_print(line)
        msg_q.task_done()

# function to kill expired bash script
def kill_on_timeout(command, event, timeout, proc):
    if not event.wait(timeout):
        safe_print('Timeout when running %s' % command)
        proc.kill()

# queue to store all bash cmd
cmd_q = Queue.Queue()
def run_command_on_local(command, timeout=1800):
    event = threading.Event()
    p = subprocess.Popen(
        command, shell=True, stdout=subprocess.PIPE,
        stderr=subprocess.PIPE, close_fds=True, bufsize=1)

    tout = threading.Thread(
        target=read_output, args=(p.stdout, msg_q.put))
    terr = threading.Thread(
        target=read_output, args=(p.stderr, msg_q.put))
    for t in (tout, terr):
        t.daemon = True
        t.start()

    watcher = threading.Thread(
        target=kill_on_timeout, args=(command, event, timeout, p))
    watcher.daemon = True
    watcher.start()

    p.wait()
    event.set()
    for t in (tout, terr):
        t.join()


def generate_command_for_node(node):
    # generate interface config
    generate_interface_config(node)

    # generate puppet script
    intfs = ','.join(node.bond_interfaces)
    lldp_config = LLDP_PUPPET % {'bond_interfaces' : intfs}
    node_config = None
    if node.role == ROLE_MGMT:
        node_config = (MGMT_PUPPET %
                       {'user'                : node.node_username,
                        'mysql_root_pwd'      : node.mysql_root_pwd,
                        'cs_url'              : CS_URL,
                        'cs_common'           : CS_COMMON,
                        'cs_mgmt'             : CS_MGMT,
                        'cloud_db_pwd'        : node.cloud_db_pwd,
                        'storage_script'      : STORAGE_SCRIPT,
                        'storage_vm_url'      : STORAGE_VM_URL,
                        'storage_vm_template' : STORAGE_VM_TEMPLATE})
    elif node.role == ROLE_COMPUTE:
        node_config = (COMPUTE_PUPPET %
                       {'user'      : node.node_username,
                        'cs_url'    : CS_URL,
                        'cs_common' : CS_COMMON,
                        'cs_agent'  : CS_AGENT})
    with open('/tmp/%s.pp' % node.hostname, "w") as node_puppet:
        node_puppet.write("%(node_config)s\n\n%(lldp_config)s" %
                          {'node_config' : node_config,
                           'lldp_config' : lldp_config})
        node_puppet.close()

    # generate db shell script
    if node.role == ROLE_MGMT:
        with open('/tmp/%s.db.sh' % node.hostname, "w") as node_db_bash:
            node_db_bash.write(DB_BASH %
                               {'user'           : node.node_username,
                                'role'           : node.role,
                                'cloud_db_pwd'   : node.cloud_db_pwd,
                                'mysql_root_pwd' : node.mysql_root_pwd,
                                'hostname'       : node.hostname})
            node_db_bash.close()

    # generate shell script
    with open('/tmp/%s.remote.sh' % node.hostname, "w") as node_remote_bash:
        node_remote_bash.write(NODE_REMOTE_BASH %
                               {'user'           : node.node_username,
                                'role'           : node.role,
                                'cloud_db_pwd'   : node.cloud_db_pwd,
                                'mysql_root_pwd' : node.mysql_root_pwd,
                                'hostname'       : node.hostname})
        node_remote_bash.close()

    # generate script for node
    with open('/tmp/%s.local.sh' % node.hostname, "w") as node_local_bash:
        node_local_bash.write(NODE_LOCAL_BASH %
                               {'pwd'      : node.node_password,
                                'hostname' : node.hostname,
                                'user'     : node.node_username,
                                'role'     : node.role,
                                'log'      : LOG_FILENAME})
        node_local_bash.close()

    cmd_q.put('bash /tmp/%s.local.sh' % node.hostname)
    


def worker():
    while True:
        cmd = cmd_q.get()
        run_command_on_local(cmd)
        cmd_q.task_done()

def deploy_to_all(config):
    # install sshpass
    safe_print("Installing sshpass to local node...\n")
    run_command_on_local(
        'sudo rm -rf ~/.ssh/known_hosts;'
        ' sudo apt-get update;'
        ' sudo apt-get -fy install --fix-missing;'
        ' sudo apt-get install -fy sshpass;'
        ' sudo rm %(log)s' % {'log' : LOG_FILENAME})

    for node_config in config['nodes']:
        if 'pxe_interface' not in node_config:
            node_config['pxe_interface'] = config['default_pxe_interface']
        if 'node_username' not in node_config:
            node_config['node_username'] = config['default_node_username']
        if 'node_password' not in node_config:
            node_config['node_password'] = config['default_node_password']
        if 'role' not in node_config:
            node_config['role'] = config['default_role']
        if 'bond_interface' not in node_config:
            node_config['bond_interface'] = config['default_bond_interface']
        if 'bridges' not in node_config:
             node_config['bridges'] = config['default_bridges']
        node_config['pxe_gw'] = config['pxe_gw']
        node_config['mysql_root_pwd'] = config['mysql_root_pwd']
        if not node_config['mysql_root_pwd']:
            node_config['mysql_root_pwd'] = UNDEF
        node_config['cloud_db_pwd'] = config['cloud_db_pwd']
        if not node_config['cloud_db_pwd']:
            node_config['cloud_db_pwd'] = UNDEF

        node = Node(node_config)
        generate_command_for_node(node)

    for i in range(MAX_WORKERS):
        t = threading.Thread(target=worker)
        t.daemon = True
        t.start()

    twrite = threading.Thread(target=write_output)
    twrite.daemon = True
    twrite.start()

    cmd_q.join()
    msg_q.join()
    safe_print("CloudStack deployment finished\n")


if __name__ == '__main__':
    safe_print("Start to setup CloudStack for "
               "Big Cloud Fabric %s\n" % (RELEASE_NAME))

    parser = argparse.ArgumentParser()
    parser.add_argument("-c", "--config-file", required=True,
                        help="CloudStack YAML config path")
    args = parser.parse_args()
    if not args.config_file:
        parser.error('--config-file is not specified.')
    else:
        config_file_path = args.config_file
        with open(config_file_path, 'r') as config_file:
            config = yaml.load(config_file)

    deploy_to_all(config)

