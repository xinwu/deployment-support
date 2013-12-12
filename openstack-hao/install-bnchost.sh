#!/bin/bash

# Install kvm on Ubuntu host, and create a VM for BNC master.

set -e
set -x

cat >> /etc/network/interfaces <<EOF

# Bridge for KVM guests
auto br0
iface br0 inet dhcp
bridge_ports em1
EOF

ifup br0

apt‐get -y install qemu‐kvm libvirt‐bin virt‐manager

IMAGEDIR=/var/lib/libvirt/images

cd $IMAGEDIR
# Guinness GA
wget http://bigtop/~bsn/abat/builds/guinness/GA/bigswitchcontroller.vmdk
for i in bnc-master bnc-slave; do
    qemu-img convert -O qcow2 -o preallocation=metadata bigswitchcontroller.vmdk $i.qcow2

    virt-install \
        --connect qemu:///system \
        --name=$i \
        --ram=4096 \
        --vcpu=2 \
        --cpu host \
        --os-type=linux \
        --os-variant=ubuntuprecise \
        --import \
        --disk path=$i.qcow2,format=qcow2,bus=virtio,cache=writeback \
        --network bridge=br0,model=virtio \
        --noautoconsole \
        --autostart
done

# FIXME: Run "virsh console ..." to connect to the VM, and configure them with expect.
