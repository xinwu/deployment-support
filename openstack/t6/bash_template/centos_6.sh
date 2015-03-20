#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root" 
   exit 1
fi

setenforce 0
checkmodule -M -m -o %(dst_dir)s/%(hostname)s.mod %(dst_dir)s/%(hostname)s.te
semodule_package -o %(dst_dir)s/%(hostname)s_selinux.pp -m %(dst_dir)s/%(hostname)s.mod
semodule -i %(dst_dir)s/%(hostname)_selinux.pp
yum update -y
yum install -y python-devel.x86_64 puppet python-pip
pip install --upgrade ospurge
pip install bsnstacklib==%(bsnstacklib_version)s
rpm -ivh %(dst_dir)s/%(ivs_pkg)s
rpm -ivh https://yum.puppetlabs.com/el/6.5/products/x86_64/puppetlabs-release-6-10.noarch.rpm
puppet module install puppetlabs-inifile
cp /usr/lib/systemd/system/neutron-openvswitch-agent.service /usr/lib/systemd/system/neutron-bsn-agent.service
puppet apply %(dst_dir)s/%(hostname)s.pp
