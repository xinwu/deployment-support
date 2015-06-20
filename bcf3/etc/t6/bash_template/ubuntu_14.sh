#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root" 
   exit 1
fi

install_bsnstacklib=%(install_bsnstacklib)s
install_ivs=%(install_ivs)s
install_all=%(install_all)s
deploy_dhcp_agent=%(deploy_dhcp_agent)s
ivs_version=%(ivs_version)s
is_controller=%(is_controller)s
deploy_horizon_patch=%(deploy_horizon_patch)s
fuel_cluster_id=%(fuel_cluster_id)s

# prepare dependencies
set +e
cat /etc/apt/sources.list | grep "http://archive.ubuntu.com/ubuntu"
if [[ $? != 0 ]]; then
    release=$(lsb_release -sc)
    echo -e "\ndeb http://archive.ubuntu.com/ubuntu $release main\n" >> /etc/apt/sources.list
fi

apt-get install ubuntu-cloud-keyring
echo "deb http://ubuntu-cloud.archive.canonical.com/ubuntu" \
"trusty-updates/juno main" > /etc/apt/sources.list.d/cloudarchive-juno.list
apt-get update -y
apt-get install -y linux-headers-$(uname -r) build-essential
apt-get install -y python-dev python-setuptools
apt-get install -y libssl-dev libffi6 libffi-dev puppet dpkg libnl-genl-3-200 vlan ethtool
apt-get -f install -y
apt-get install -o Dpkg::Options::="--force-confold" --force-yes -y neutron-common
if [[ $deploy_dhcp_agent == true ]]; then
    apt-get install -o Dpkg::Options::="--force-confold" -y neutron-metadata-agent
    apt-get install -o Dpkg::Options::="--force-confold" -y neutron-dhcp-agent
fi
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
        if [[ ${old_version_numbers[0]} == 0 ]]; then
            pass=true
        elif [[ "$old_version" != "${old_version%%$ivs_version*}" ]]; then
            pass=true
        elif [[ $old_version > $ivs_version ]]; then
            pass=false
        elif [[ $((${new_version_numbers[0]}-1)) -gt ${old_version_numbers[0]} ]]; then
            pass=false
        fi
    fi

    if [[ $pass == true ]]; then
        dpkg --force-all -i %(dst_dir)s/%(ivs_pkg)s
        if [[ -f %(dst_dir)s/%(ivs_debug_pkg)s ]]; then
            apt-get install -y libnl-genl-3-200
            apt-get -f install -y
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
    if [[ -f /etc/init/neutron-plugin-openvswitch-agent.override ]]; then
        cp /etc/init/neutron-plugin-openvswitch-agent.override /etc/init/neutron-bsn-agent.override
    fi
    service neutron-plugin-openvswitch-agent stop
    service neutron-bsn-agent stop
    rm -f /etc/init/neutron-bsn-agent.conf
    pkill neutron-openvswitch-agent
    rm -f /usr/bin/neutron-openvswitch-agent

    # stop ovs agent, otherwise, ovs bridges cannot be removed
    service neutron-plugin-openvswitch-agent stop
    update-rc.d neutron-plugin-openvswitch-agent disable

    # remove ovs, example ("br-storage" "br-prv" "br-ex")
    declare -a ovs_br=(%(ovs_br)s)
    len=${#ovs_br[@]}
    for (( i=0; i<$len; i++ )); do
        ovs-vsctl del-br ${ovs_br[$i]}
    done
    for (( i=0; i<$len; i++ )); do
        ifconfig ${ovs_br[$i]} down
        brctl delbr ${ovs_br[$i]}
    done

    # delete ovs br-int
    while true; do
        ovs-vsctl del-br %(br-int)s
        sleep 1
        ovs-vsctl show | grep %(br-int)s
        if [[ $? != 0 ]]; then
            break
        fi
        service neutron-plugin-openvswitch-agent stop
        update-rc.d neutron-plugin-openvswitch-agent disable
    done

    #bring down tagged bonds
    apt-get install -y ethtool
    apt-get -f install -y
    declare -a bonds=(%(bonds)s)
    len=${#bonds[@]}
    for (( i=0; i<$len; i++ )); do
        ifconfig ${bonds[$i]} down
        ip link set ${bonds[$i]} down
        ifdown ${bonds[$i]} --force
    done

    # deploy bcf
    puppet apply --modulepath /etc/puppet/modules %(dst_dir)s/%(hostname)s.pp

    # /etc/network/interfaces
    if [[ ${fuel_cluster_id} != 'None' ]]; then
        echo '' > /etc/network/interfaces
        declare -a interfaces=(%(interfaces)s)
        len=${#interfaces[@]}
        for (( i=0; i<$len; i++ )); do
            echo -e 'auto' ${interfaces[$i]} >>/etc/network/interfaces 
            echo -e 'iface' ${interfaces[$i]} 'inet manual' >>/etc/network/interfaces
            echo ${interfaces[$i]} | grep '\.'
            if [[ $? == 0 ]]; then
                intf=$(echo ${interfaces[$i]} | cut -d \. -f 1)
                echo -e 'vlan-raw-device ' $intf >> /etc/network/interfaces
            fi
            echo -e '\n' >> /etc/network/interfaces
        done
        echo -e 'auto' %(br_fw_admin)s >>/etc/network/interfaces
        echo -e 'iface' %(br_fw_admin)s 'inet static' >>/etc/network/interfaces
        echo -e 'bridge_ports' %(pxe_interface)s >>/etc/network/interfaces
        echo -e 'address' %(br_fw_admin_address)s >>/etc/network/interfaces
        echo -e 'up ip route add default via' %(br_fw_admin_gw)s >>/etc/network/interfaces
    fi

    #reset uplinks to move them out of bond
    declare -a uplinks=(%(uplinks)s)
    len=${#uplinks[@]}
    for (( i=0; i<$len; i++ )); do
        ifconfig ${uplinks[$i]} down
        ip link set ${uplinks[$i]} down
        ifdown ${uplinks[$i]} --force
        sleep 2
        ifconfig ${uplinks[$i]} down
        ip link set ${uplinks[$i]} down
        ifdown ${uplinks[$i]} --force
        sleep 2
        ifconfig ${uplinks[$i]} down
        ip link set ${uplinks[$i]} down
        ifdown ${uplinks[$i]} --force
    done
    for (( i=0; i<$len; i++ )); do
        ifconfig ${uplinks[$i]} up
        ifup ${uplinks[$i]} --force
        ip link set ${uplinks[$i]} up
    done

    # assign ip to ivs internal ports
    bash /etc/rc.local

    # chmod neutron config since bigswitch horizon patch reads neutron config as well
    chmod -R a+r /usr/share/neutron
    chmod -R a+x /usr/share/neutron
    chmod -R a+r /etc/neutron
    chmod -R a+x /etc/neutron

    # deploy bcf horizon patch to controller node
    if [[ $is_controller == true && $deploy_horizon_patch == true ]]; then
        if [[ -f %(dst_dir)s/%(horizon_patch)s ]]; then
            chmod -R 777 '/etc/neutron/'
            tar -xzf %(dst_dir)s/%(horizon_patch)s -C %(dst_dir)s
            fs=('openstack_dashboard/dashboards/admin/dashboard.py' 'openstack_dashboard/dashboards/project/dashboard.py' 'openstack_dashboard/dashboards/admin/connections' 'openstack_dashboard/dashboards/project/connections')
            for f in "${fs[@]}"
            do
                if [[ -f %(dst_dir)s/%(horizon_patch_dir)s/$f ]]; then
                    yes | cp -rfp %(dst_dir)s/%(horizon_patch_dir)s/$f %(horizon_base_dir)s/$f
                else
                    mkdir -p %(horizon_base_dir)s/$f
                    yes | cp -rfp %(dst_dir)s/%(horizon_patch_dir)s/$f/* %(horizon_base_dir)s/$f
                fi
            done
            find "%(horizon_base_dir)s" -name "*.pyc" | xargs rm
            find "%(horizon_base_dir)s" -name "*.pyo" | xargs rm

            # patch neutron api.py to work around oslo bug
            # https://bugs.launchpad.net/oslo-incubator/+bug/1328247
            # https://review.openstack.org/#/c/130892/1/openstack/common/fileutils.py
            neutron_api_py=$(find /usr -name api.py | grep neutron | grep db | grep -v plugins)
            neutron_api_dir=$(dirname "${neutron_api_py}")
            sed -i 's/from neutron.openstack.common import log as logging/import logging/g' $neutron_api_py
            find $neutron_api_dir -name "*.pyc" | xargs rm
            find $neutron_api_dir -name "*.pyo" | xargs rm
            service apache2 restart
        fi
    fi

    # patch linux/dhcp.py to make sure static host route is pushed to instances
    dhcp_py=$(find /usr -name dhcp.py | grep linux)
    dhcp_dir=$(dirname "${dhcp_py}")
    sed -i 's/if (isolated_subnets\[subnet.id\] and/if (True and/g' $dhcp_py
    find $dhcp_dir -name "*.pyc" | xargs rm
    find $dhcp_dir -name "*.pyo" | xargs rm
    if [[ $deploy_dhcp_agent == true ]]; then
        echo 'Restart neutron-metadata-agent and neutron-dhcp-agent'
        service neutron-metadata-agent restart
        update-rc.d neutron-metadata-agent defaults
        service neutron-dhcp-agent restart
        update-rc.d neutron-dhcp-agent defaults
    else
        echo 'Stop and disable neutron-metadata-agent and neutron-dhcp-agent'
        service neutron-metadata-agent stop
        update-rc.d neutron-metadata-agent disable
        service neutron-dhcp-agent stop
        update-rc.d neutron-dhcp-agent disable
    fi
fi

# restart libvirtd and nova compute on compute node
if [[ $is_controller == false ]]; then
    echo 'Restart libvirtd and openstack-nova-compute'
    service libvirt-bin restart 
    update-rc.d libvirt-bin defaults
    service nova-compute restart
    update-rc.d nova-compute defaults
fi

# restart neutron-server on controller node
if [[ $is_controller == true ]]; then
    echo 'Restart neutron-server'
    rm -rf /etc/neutron/plugins/ml2/host_certs/*
    service neutron-server restart
fi

# restart bsn-agent
service neutron-bsn-agent restart

# patch nova rootwrap for fuel
if [[ ${fuel_cluster_id} != 'None' ]]; then
    mkdir -p /usr/share/nova
    rm -rf /usr/share/nova/rootwrap
    cp -r /tmp/rootwrap /usr/share/nova/
    chmod -R 777 /usr/share/nova/rootwrap
fi

set -e

