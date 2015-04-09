#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root" 
   exit 1
fi

install_bsnstacklib_flag=%(install_bsnstacklib_flag)s
install_ivs_flag=%(install_ivs_flag)s
full_install_flag=%(full_installation_flag)s

# prepare dependencies
rpm -iUvh http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm
rpm -ivh https://yum.puppetlabs.com/el/7/products/x86_64/puppetlabs-release-7-10.noarch.rpm
yum groupinstall -y 'Development Tools'
yum install -y python-devel puppet python-pip wget libffi-devel openssl-devel

# install bsnstacklib
if [ $install_bsnstacklib_flag = true ]; then
    pip install bsnstacklib==%(bsnstacklib_version)s
fi

# install ivs
if [ $install_ivs_flag = true ]; then
    rpm -ivh --force %(dst_dir)s/%(ivs_pkg)s
    if [ -f %(dst_dir)s/%(ivs_debug_pkg)s ]; then
        rpm -ivh --force %(dst_dir)s/%(ivs_debug_pkg)s
    fi
fi

# full installation of bcf
if [ $full_install_flag = true ]; then
    puppet module install --force puppetlabs-inifile
    puppet module install --force puppetlabs-stdlib
    puppet module install jfryman-selinux
    mkdir -p /etc/puppet/modules/selinux/files
    cp %(dst_dir)s/%(hostname)s.te /etc/puppet/modules/selinux/files/centos.te
    cp /usr/lib/systemd/system/neutron-openvswitch-agent.service /usr/lib/systemd/system/neutron-bsn-agent.service

    # remove ovs, example ("br-storage" "br-prv" "br-ex")
    declare -a ovs_br=(%(ovs_br)s)
    len=${#ovs_br[@]}
    for (( i=0; i<$len; i++ )); do
        ovs-vsctl del-br ${ovs_br[$i]}
    done
    # delete ovs br-int
    ovs-vsctl del-br %(br-int)s

    # deploy bcf
    puppet apply --modulepath /etc/puppet/modules %(dst_dir)s/%(hostname)s.pp

    # assign ip to ivs internal ports
    bash /etc/rc.d/rc.local
fi

# restart libvirtd and nova compute on compute node
systemctl status openstack-nova-compute
if [ $?==0 ]; then
    systemctl restart libvirtd
    systemctl restart openstack-nova-compute
fi

# restart neutron-server on controller node
systemctl status neutron-server
if [ $?==0 ]; then
    systemctl restart neutron-server
fi
