#!/bin/bash

# Make sure only root can run this script
if [ "$(id -u)" != "0" ]; then
   echo -e "Please run as root"
   exit 1
fi

# install packages for centos 7
python -mplatform | grep centos-7
if [[ $? == 0 ]]; then
    yum update -y
    yum install -y python-devel.x86_64 python-yaml sshpass puppet python-pip
    pip install --upgrade subprocess32 futures
    exit 0
fi
