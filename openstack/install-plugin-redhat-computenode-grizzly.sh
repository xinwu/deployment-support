#!/usr/bin/env bash
#
# This script patches a RedHat openstack grizzly compute node install with BigSwitch changes
#
# Big Switch Plugin: https://github.com/bigswitch/neutron/tree/grizzly/stable
#
# @author: Kevin Benton, Big Switch Networks, Inc.
# @date: July 20, 2013
#
# See usage below:
USAGE="$0 bsn-conotroller-ip:port[,bsn-controller-ip:port]*"

DATE=$(date +"%Y%m%d%H%M")
exec >  >(tee -a patchlog-$DATE.log | grep -v '^+')
exec 2> >(tee -a patchlog-$DATE.log | grep -v '^+' >&2)
trap "sleep 1" exit
set -x
set -e

umask 022

RESTPROXY_CONTROLLER=$1

# Gracefully cp only if source file/dir exists
# cp_it source destination
function cp_it {
    if [ -e $1 ] || [ -d $1 ]; then
        cp -pRL $1 $2
    fi
}

# Get an option from an INI file
# iniget config-file section option
function iniget() {
    local file=$1
    local section=$2
    local option=$3
    local line
    line=$(sed -ne "/^\[$section\]/,/^\[.*\]/ { /^$option[ \t]*=/ p; }" $file)
    echo ${line#*=}
}


# Set an option in an INI file
# iniset config-file section option value
function iniset() {
    local file=$1
    local section=$2
    local option=$3
    local value=$4
    if ! grep -q "^\[$section\]" $file; then
        # Add section at the end
        echo -e "\n[$section]" >>$file
    fi
    if [[ -z "$(iniget $file $section $option)" ]]; then
        # Add it
        sed -i -e "/^\[$section\]/ a\\
$option = $value
" $file
    else
        # Replace it
        sed -i -e "/^\[$section\]/,/^\[.*\]/ s|^\($option[ \t]*=[ \t]*\).*$|\1$value|" $file
    fi
}


function PatchNova() {
    local nova_conf=`rpm -ql openstack-nova-common | grep "/nova.conf"`
    iniset $nova_conf DEFAULT security_group_api nova
    iniset $nova_conf DEFAULT firewall_driver nova.virt.libvirt.firewall.IptablesFirewallDriver
    iniset $nova_conf DEFAULT service_quantum_metadata_proxy False
 
    iptables -D FORWARD -j REJECT --reject-with icmp-host-prohibited ||:
    sed -i 's/-A FORWARD -j REJECT --reject-with icmp-host-prohibited/# Commented out by BigSwitch script\n#-A FORWARD -j REJECT --reject-with icmp-host-prohibited/g' /etc/sysconfig/iptables
    chkconfig quantum-openvswitch-agent off
    /etc/init.d/quantum-openvswitch-agent stop ||:
}



function SetOVSController() {
    OVSCONTROLLERSTRING=""
    splitstring=`echo $RESTPROXY_CONTROLLER | sed -n 1'p' | tr ',' '\n'`
    for word in $splitstring; do
        CONTROLLERIP=`echo "$word" | awk -F':' '{ print $1 }'`
        OVSCONTROLLERSTRING="$OVSCONTROLLERSTRING tcp:$CONTROLLERIP:6633"
    done
    ovs-vsctl set-controller br-int $OVSCONTROLLERSTRING
}
# Prints "message" and exits
# die "message"
function die() {
    local exitcode=$?
    echo $@
    exit $exitcode
}

if [ "${RESTPROXY_CONTROLLER}"x = ""x ] ; then
    echo "ERROR: RESTPROXY_CONTROLLER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
PatchNova
SetOVSController
echo "Done patching services. Restarting services..."
/etc/init.d/openstack-nova-api restart ||:
/etc/init.d/openstack-nova-compute restart ||:
