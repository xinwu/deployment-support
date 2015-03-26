#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root"
   exit 1
fi

# source openrc file first

# install packages for centos 7
python -mplatform | grep centos-7
if [[ $? == 0 ]]; then
    rpm -iUvh http://dl.fedoraproject.org/pub/epel/7/x86_64/e/epel-release-7-5.noarch.rpm
    yum update -y
    yum groupinstall -y 'Development Tools'
    yum install -y python-devel.x86_64 python-yaml sshpass puppet python-pip wget
    pip install --upgrade subprocess32 futures
    pip install --upgrade python-keystoneclient python-novaclient python-neutronclient
    #pip install --upgrade ospurge
    exit 0
else
    echo "Unsupported operating system."
fi
