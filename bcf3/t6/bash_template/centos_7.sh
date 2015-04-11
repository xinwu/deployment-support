#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root" 
   exit 1
fi

install_bsnstacklib=%(install_bsnstacklib)s
install_ivs=%(install_ivs)s
install_all=%(install_all)s
ivs_version=%(ivs_version)s
is_controller=%(is_controller)s

# prepare dependencies
rpm -iUvh http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm
rpm -ivh https://yum.puppetlabs.com/el/7/products/x86_64/puppetlabs-release-7-10.noarch.rpm
yum groupinstall -y 'Development Tools'
yum install -y python-devel puppet python-pip wget libffi-devel openssl-devel

# install bsnstacklib
if [[ $install_bsnstacklib = true ]]; then
    pip install --upgrade "bsnstacklib<%(bsnstacklib_version)s"
fi

# install ivs
if [ $install_ivs = true ]; then
    # check ivs version compatability
    pass=true
    ivs --version
    if [[ $? == 0 ]]; then
        old_version=$(ivs --version | awk '{print $2}')
        old_version_numbers=(${old_version//./ })
        new_version_numbers=(${ivs_version//./ })
        if [[ $old_version > $ivs_version ]]; then
            pass=false
        elif [[ $((${new_version_numbers[0]}-1)) > ${old_version_numbers[0]} ]]; then
            pass=false
        fi
    fi

    if [[ $pass == true ]]; then
        rpm -ivh --force %(dst_dir)s/%(ivs_pkg)s
        if [ -f %(dst_dir)s/%(ivs_debug_pkg)s ]; then
            rpm -ivh --force %(dst_dir)s/%(ivs_debug_pkg)s
        fi
    else
        echo "ivs upgrade fails version validation"
    fi
fi

# full installation of bcf
if [[ $install_all == true ]]; then
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
if [[ $is_controller == false ]]; then
    echo 'Restart libvirtd and openstack-nova-compute'
    systemctl restart libvirtd
    systemctl restart openstack-nova-compute
fi

# restart neutron-server on controller node
if [[ $is_controller == true ]]; then
    echo 'Restart neutron-server'
    systemctl restart neutron-server
fi

