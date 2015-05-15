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
deploy_horizon_patch=%(deploy_horizon_patch)s

# prepare dependencies
set +e
cat /etc/apt/sources.list | grep "http://archive.ubuntu.com/ubuntu"
if [[ $? != 0 ]]; then
    release=$(lsb_release -sc)
    echo -e "\ndeb http://archive.ubuntu.com/ubuntu $release main\n" >> /etc/apt/sources.list
fi
apt-get update -y
apt-get install -y linux-headers-$(uname -r) build-essential
apt-get install -y python-dev python-setuptools
apt-get install -y libssl-dev libffi6 libffi-dev puppet dpkg libnl-genl-3-200
apt-get -f install -y
easy_install pip

# install bsnstacklib
if [[ $install_bsnstacklib == true ]]; then
    pip install --upgrade "bsnstacklib<%(bsnstacklib_version)s"
fi

# install ivs
if [[ $install_ivs == true ]]; then
    # check ivs version compatability
    pass=true
    ivs --version
    if [[ $? == 0 ]]; then
        old_version=$(ivs --version | awk '{print $2}')
        old_version_numbers=(${old_version//./ })
        new_version_numbers=(${ivs_version//./ })
        if [[ $old_version > $ivs_version ]]; then
            pass=false
        elif [[ $((${new_version_numbers[0]}-1)) -gt ${old_version_numbers[0]} ]]; then
            pass=false
        fi
    fi

    if [[ $pass == true ]]; then
        dpkg --force-all -i %(dst_dir)s/%(ivs_pkg)s
        if [[ -f %(dst_dir)s/%(ivs_debug_pkg)s ]]; then
            dpkg --force-all -i %(dst_dir)s/%(ivs_debug_pkg)s
        fi
    else
        echo "ivs upgrade fails version validation"
    fi
fi

# full installation of bcf
if [[ $install_all == true ]]; then
    puppet module install --force puppetlabs-inifile
    puppet module install --force puppetlabs-stdlib
    cp /etc/init/neutron-plugin-openvswitch-agent.conf /etc/init/neutron-plugin-bsn-agent.conf

    # remove ovs, example ("br-storage" "br-prv" "br-ex")
    declare -a ovs_br=(%(ovs_br)s)
    len=${#ovs_br[@]}
    for (( i=0; i<$len; i++ )); do
        ovs-vsctl del-br ${ovs_br[$i]}
    done

    # delete ovs br-int
    while true; do
        ovs-vsctl del-br %(br-int)s
        ovs-vsctl show | grep %(br-int)s
        if [[ $? != 0 ]]; then
            break
        fi
        sleep 1
    done

    # deploy bcf
    puppet apply --modulepath /etc/puppet/modules %(dst_dir)s/%(hostname)s.pp

    # assign ip to ivs internal ports
    bash /etc/rc.local

    # deploy bcf horizon patch to controller node
    if [[ $is_controller == true && $deploy_horizon_patch == true ]]; then
        if [[ -f %(dst_dir)s/%(horizon_patch)s ]]; then
            chmod -R 777 '/etc/neutron/'
            tar -xzf %(dst_dir)s/%(horizon_patch)s -C %(dst_dir)s
            fs=('openstack_dashboard/dashboards/admin/dashboard.py' 'openstack_dashboard/dashboards/project/dashboard.py' 'openstack_dashboard/dashboards/admin/connections' 'openstack_dashboard/dashboards/project/connections')
            for f in "${fs[@]}"
            do
                yes | cp -rfp %(dst_dir)s/%(horizon_patch_dir)s/$f %(horizon_base_dir)s/$f
            done
            find "%(horizon_base_dir)s" -name "*.pyc" -exec rm -rf {} \;
            service apache2 restart
        fi
    fi
fi

# restart libvirtd and nova compute on compute node
if [[ $is_controller == false ]]; then
    echo 'Restart libvirtd and openstack-nova-compute'
    service libvirt-bin restart 
    service nova-compute restart
fi

# restart neutron-server on controller node
if [[ $is_controller == true ]]; then
    echo 'Restart neutron-server'
    rm -rf /etc/neutron/plugins/ml2/host_certs/*
    service neutron-server restart
fi

set -e

