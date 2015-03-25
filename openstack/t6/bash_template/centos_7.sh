#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root" 
   exit 1
fi

# prepare dependencies
rpm -iUvh http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm
yum update -y
yum groupinstall -y 'Development Tools'
yum install -y python-devel.x86_64 puppet python-pip wget libffi-devel openssl-devel
pip install --upgrade ospurge
pip install bsnstacklib==%(bsnstacklib_version)s
rpm -ivh %(dst_dir)s/%(ivs_pkg)s
if [ -f %(dst_dir)s/%(ivs_debug_pkg)s ]; then
    rpm -ivh %(dst_dir)s/%(ivs_debug_pkg)s
fi
rpm -ivh https://yum.puppetlabs.com/el/7/products/x86_64/puppetlabs-release-7-10.noarch.rpm
puppet module install puppetlabs-inifile
puppet module install jfryman-selinux
mkdir -p /etc/puppet/modules/selinux/files
cp %(dst_dir)s/%(hostname)s.te /etc/puppet/modules/selinux/files/centos.te
cp /usr/lib/systemd/system/neutron-openvswitch-agent.service /usr/lib/systemd/system/neutron-bsn-agent.service

# deploy bcf
puppet apply --modulepath /etc/puppet/modules %(dst_dir)s/%(hostname)s.pp
