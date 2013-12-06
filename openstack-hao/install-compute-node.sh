#!/bin/bash

# This script must be able to be re-executed again and again. That is, you
# can't assume it is run on a freshly installed OS. That makes it easier
# to test changes made to this script.
#
# Basic assumptions:
# 1. All controller functions, database are all hosted by a single host named
#    $HOSTNAME_CONTROLLER. This hostname is either in DNS, or in /etc/hosts,
#    on all hosts within this OpenStack cluster.

set -e -x

if [ $(id -u) != 0 ]; then
   echo "ERROR: Must run as root"
   exit 1
fi

# Definitions that can be customized per installation

# This hostname should resolve to the IP of the interface on management
# network, often em1.
HOSTNAME_CONTROLLER=controller

# We must use IP (not DNS hostname) of BSN controller in "ovs-vsctl set-controller ..." command.
BSN_CONTROLLER=10.203.0.21

# The interface on openstack management network.
MGMT_IF=em1
MGMT_IP=$(ifconfig $MGMT_IF | sed -n 's/^.*inet addr:\([0-9\.]\+\).*$/\1/p')

DATA_IF=em2
# FIXME: Don't hard code 10.203 here.
DATA_IP=$(echo $MGMT_IP | sed 's/10\.203\.0\./10.203.1./')
DATA_MASK=255.255.255.0

# Do NOT use any non-alphanumerical characters that require quoting in
# passwords below. They would break this script.
NOVA_DB_PASSWORD=NOVA_DBPASS
NOVA_ADMIN_PASSWORD=NOVA_PASS
NEUTRON_DB_PASSWORD=NEUTRON_DBPASS
NEUTRON_ADMIN_PASSWORD=NEUTRON_PASS


keep_stock_conf() {
    CONF=$1
    if [ ! -f $CONF.stock ]; then
        mv $CONF $CONF.stock
    fi
}

install_extra_packages() {
    apt-get -y install vim-nox debconf-utils python-mysqldb curl
}

configure_network() {
    cat >> /etc/network/interfaces <<EOF

auto $DATA_IF
iface $DATA_IF inet manual
EOF

    ifconfig $DATA_IF up

    # FIXME: Test that $HOSTNAME_CONTROLLER is reachable.

    apt-get -y install bridge-utils openvswitch-switch

    cat > /etc/sysctl.conf <<EOF
net.ipv4.ip_forward=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF

    service procps restart; sleep 1
}

install_kvm() {
    apt-get -y install kvm libvirt-bin pm-utils
    keep_stock_conf /etc/libvirt/qemu.conf
    cat > /etc/libvirt/qemu.conf <<EOF
    cgroup_device_acl = [
        "/dev/null", "/dev/full", "/dev/zero",
        "/dev/random", "/dev/urandom",
        "/dev/ptmx", "/dev/kvm", "/dev/kqemu",
        "/dev/rtc","/dev/hpet", "/dev/vfio/vfio", "/dev/net/tun"
    ]
EOF

    virsh net-destroy default || :
    virsh net-undefine default || :

    sed -i -e 's/^.*listen_tls = .*$/listen_tls = 0/' \
           -e 's/^.*listen_tcp = .*$/listen_tcp = 1/' \
           -e 's/^.*auth_tcp = .*$/auth_tcp = "none"/' \
        /etc/libvirt/libvirtd.conf

    sed -i -e 's/^env libvirtd_opts=.*$/env libvirtd_opts="-d -l"/' /etc/init/libvirt-bin.conf
    sed -i -e 's/^libvirtd_opts=.*$/libvirtd_opts="-d -l"/' /etc/default/libvirt-bin
    service libvirt-bin restart
}

install_nova_compute() {
    apt-get -y install nova-compute-kvm

    sed -i \
        -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
        -e "s|%SERVICE_TENANT_NAME%|service|" \
        -e "s|%SERVICE_USER%|nova|" \
        -e "s|%SERVICE_PASSWORD%|$NOVA_ADMIN_PASSWORD|" \
        /etc/nova/api-paste.ini

    if ! grep -qs 'libvirt_ovs_bridge=br-int' /etc/nova/nova-compute.conf; then
        cat >> /etc/nova/nova-compute.conf <<EOF
libvirt_ovs_bridge=br-int
libvirt_vif_type=ethernet
libvirt_vif_driver=nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver
libvirt_use_virtio_for_bridges=True
EOF
    fi

    # Tell Nova about Neutron
    if ! egrep -qs "^firewall_driver=" /etc/nova/nova.conf; then
        sed -i "/\[DEFAULT\]/a network_api_class=nova.network.neutronv2.api.API\nneutron_url=http://$HOSTNAME_CONTROLLER:9696\nneutron_auth_strategy=keystone\nneutron_admin_tenant_name=service\nneutron_admin_username=neutron\nneutron_admin_password=$NEUTRON_ADMIN_PASSWORD\nneutron_admin_auth_url=http://$HOSTNAME_CONTROLLER:35357/v2.0\nlibvirt_vif_driver=nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver\nlinuxnet_interface_driver=nova.network.linux_net.LinuxOVSInterfaceDriver\nfirewall_driver=nova.virt.libvirt.firewall.IptablesFirewallDriver" /etc/nova/nova.conf
    fi

    if ! egrep -qs '^\[database\]' /etc/nova/nova.conf; then
        sed -i "/^\[DEFAULT\]/i [database]\nconnection = mysql://nova:$NOVA_DB_PASSWORD@$HOSTNAME_CONTROLLER/nova" /etc/nova/nova.conf
        cat >> /etc/nova/nova.conf <<EOF
my_ip=$MGMT_IP
vncserver_listen=0.0.0.0
vncserver_proxyclient_address=$MGMT_IP
rpc_backend=nova.rpc.impl_kombu
rabbit_host=$HOSTNAME_CONTROLLER
glance_host=$HOSTNAME_CONTROLLER
EOF
    fi

    rm -f /var/lib/nova/nova.sqlite

    service nova-compute restart; sleep 1

    if ! ovs-vsctl br-exists br-int; then
        ovs-vsctl add-br br-int
        ovs-vsctl add-port br-int $DATA_IF

        ovs-vsctl set-controller br-int tcp:$BSN_CONTROLLER:6633
    fi

}

# Execution starts here

install_extra_packages
configure_network
install_kvm
install_nova_compute

echo "OpenStack compute node installation completed."
