#!/bin/bash
#
# Copyright 2014 Big Switch Networks, Inc.
# All Rights Reserved.
#
# This script is used to set up cloud stack management node
# and compute nodes with Big Cloud Fabric. The requirements are:
# BCF: 2.0.1 or higher
# installation node: ubuntu 12.04, centos 6.5 or centos 6.6
# management node: ubuntu 12.04, centos 6.5 or centos 6.6
# compute node: ubuntu 12.04 or xenserver 6.2
# 
# To prepare installation, on installation node, please download
# cloudstack-common_4.5.0-snapshot_all.deb,
# cloudstack-management_4.5.0-snapshot_all.deb,
# cloudstack-agent_4.5.0-snapshot_all.deb
# and put them under the same directory as this script.
#
# please also download example.yaml and make necessary modifications
# according to your physical setup.
#
# Usage: bash big_patch.sh example.yaml

# check configuration file
if [[ -z "$*" ]]; then
    echo -e "No configuration file is specified.\nUsage: bash big_patch.sh example.yaml"
    exit 1
fi
config=$1
if [[ ! -f ${config} ]]; then
    echo "Configuration file does not exist"
    exit 1
fi
echo "Configuration file is ${config}"
mkdir -p /home/root/bcf
cp ${config} /home/root/bcf/

# if os is ubuntu
python -mplatform | grep Ubuntu
if [[ $? == 0 ]]; then
    sudo apt-get update -y
    sudo apt-get install -y sshpass python-yaml python-pip python-dev
    sudo pip install futures subprocess32
    rm /home/root/bcf/big_patch.py
    wget --no-check-certificate https://raw.githubusercontent.com/bigswitch/deployment-support/master/cloudstack/big_patch.py -P /home/root/bcf
    python /home/root/bcf/big_patch.py -c /home/root/bcf/${config}
    exit 0
fi

# if os is centos
python -mplatform | grep centos
if [[ $? == 0 ]]; then
    # install sshpass
    rm /home/root/bcf/sshpass-1.05-1.el6.rf.x86_64.rpm
    wget http://pkgs.repoforge.org/sshpass/sshpass-1.05-1.el6.rf.x86_64.rpm -P /home/root/bcf/
    yum install -y /home/root/bcf/sshpass-1.05-1.el6.rf.x86_64.rpm

    # install epel repo
    rm /home/root/bcf/epel-release-5-4.noarch.rpm
    wget http://dl.fedoraproject.org/pub/epel/5/x86_64/epel-release-5-4.noarch.rpm -P /home/root/bcf/
    yum install -y /home/root/bcf/epel-release-5-4.noarch.rpm

    # install python-pip and python-dev
    rm /home/root/bcf/python-pip-0.8-1.1.noarch.rpm
    wget ftp://ftp.pbone.net/mirror/ftp5.gwdg.de/pub/opensuse/repositories/home:/dalgaaf:/ceph:/extra/CentOS_CentOS-6/noarch/python-pip-0.8-1.1.noarch.rpm -P /home/root/bcf/
    yum install -y /home/root/bcf/python-pip-0.8-1.1.noarch.rpm
    yum install -y python-devel

    # install subprocess32
    pip-python install "subprocess32>=3.2.6"

    rm /home/root/bcf/big_patch.py
    wget --no-check-certificate https://raw.githubusercontent.com/bigswitch/deployment-support/master/cloudstack/big_patch.py -P /home/root/bcf/
    python /home/root/bcf/big_patch.py -c /home/root/bcf/${config}
    exit 0
fi

# we don't support other os
echo "Please use centos 6.5, 6.6 or ubuntu 12.04 as cloudstack management node"

