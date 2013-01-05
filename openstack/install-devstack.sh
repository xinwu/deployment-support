#!/bin/sh
#
# Install stable devstack and openstack with quantum and restproxy
# Note:
#   1. this script uses the same password for all openstack services
#
# See usage below:
USAGE="$0 <network-controller-for-restproxy> [[port] [<password>]]"

set -e

# set parameters
RESTPROXY_CONTROLLER=$1
RESTPROXY_CONTROLLER_PORT=${2:-'80'}
RESTPROXY_CONF_DIR='/etc/quantum/plugins/bigswitch'
STACK_PASSWORD=${3:-'nova'}
STACK_TOP='/opt/stack'
DEVSTACK_REPO='http://github.com/bigswitch/devstack.git'
DEVSTACK_BRANCH='bigswitch'
DEVSTACK_DIR='devstack'

#
# Validate env
#
if [ ! -f /etc/lsb-release ] ; then
    echo "ERROR: This script is only supported on ubuntu" 1>&2
    exit 1
fi
eval `cat /etc/lsb-release`
if [ "${DISTRIB_RELEASE}"x != "12.04"x ] ; then
    echo "ERROR: This script is only supported on ubuntu 12.04" 1>&2
    exit 1
fi

RESTPROXY_HOMEDIR=`dirname $0`/..
if [ ! -d "${RESTPROXY_HOMEDIR}" ] ; then
    echo "ERROR: Directory '${RESTPROXY_HOMEDIR}' not found." 1>&2
    exit 1
fi
RESTPROXY_HOMEDIR=`cd ${RESTPROXY_HOMEDIR}; pwd`

# Validate args
if [ "${RESTPROXY_CONTROLLER}"x = ""x ] ; then
    echo "ERROR: RESTPROXY_CONTROLLER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi

# install git
sudo apt-get -y update
sudo apt-get -y upgrade
sudo apt-get -y install gcc make python-all-dev python-pip git

# get devstack
cd ${HOME}
git clone -b ${DEVSTACK_BRANCH} ${DEVSTACK_REPO} ${DEVSTACK_DIR}

# create localrc
cd ${HOME}/${DEVSTACK_DIR}
cat >localrc <<EOF
disable_service n-net
enable_service q-svc
enable_service q-dhcp
enable_service quantum
enable_service bigswitch_floodlight
Q_PLUGIN=bigswitch_floodlight
Q_USE_NAMESPACE=False
NOVA_USE_QUANTUM_API=v2
SCHEDULER=nova.scheduler.simple.SimpleScheduler
MYSQL_PASSWORD=${STACK_PASSWORD}
RABBIT_PASSWORD=${STACK_PASSWORD}
ADMIN_PASSWORD=${STACK_PASSWORD}
SERVICE_PASSWORD=${STACK_PASSWORD}
SERVICE_TOKEN=${STACK_PASSWORD}
DEST=${STACK_TOP}
SCREEN_LOGDIR=$DEST/logs/screen
SYSLOG=True
#IP:Port for the BSN controller
#if more than one, separate with commas
BS_FL_CONTROLLERS_PORT=${RESTPROXY_CONTROLLER}:${RESTPROXY_CONTROLLER_PORT}
BS_FL_CONTROLLER_TIMEOUT=10
EOF

# Done
echo "$0 Done."
echo "Start devstack as:"
echo "   cd ~/${DEVSTACK_DIR}; ./stack.sh"
echo ""
