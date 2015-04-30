#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root"
   exit 1
fi

# source openrc file first

# install packages for centos
python -mplatform | grep centos
if [[ $? == 0 ]]; then
    yum groupinstall -y 'Development Tools'
    yum install -y python-devel python-yaml sshpass python-pip wget
    pip install --upgrade subprocess32 futures
    exit 0
fi

echo "Unsupported operating system."
