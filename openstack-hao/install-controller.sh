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

if [ -z "$HOME" ]; then
    # We must be running in upstart which doesn't have a user's environment.
    # Manually set HOME which is needed by mysql.
    export HOME=/root
fi

# Set current working directory to where the script is located
cd $(dirname $0)

# Definitions that can be customized per installation

# This hostname should resolve to the IP of the interface on management
# network, often em1.
HOSTNAME_CONTROLLER=controller

# We must use IP (not DNS hostname) of BSN controller in "ovs-vsctl set-controller ..." command.
BSN_CONTROLLER=10.203.0.21

# FIXME: this needs to be auto-generated
MGMT_IF=em1
MGMT_IP=10.203.0.13

# FIXME: this needs to be defined elsewhere
DATA_IF=em2
DATA_IP=10.203.1.13
DATA_MASK=255.255.255.0

# Do NOT use any non-alphanumerical characters that require quoting in
# passwords below. They would break this script.
MYSQL_ROOT_PASSWORD=bsn
KEYSTONE_DB_PASSWORD=KEYSTONE_DBPASS
KEYSTONE_ADMIN_PASSWORD=ADMIN_PASS
KEYSTONE_ADMIN_EMAIL=hao.li@bigswitch.com
GLANCE_DB_PASSWORD=GLANCE_DBPASS
GLANCE_ADMIN_PASSWORD=GLANCE_PASS
GLANCE_ADMIN_EMAIL=hao.li@bigswitch.com
NOVA_DB_PASSWORD=NOVA_DBPASS
NOVA_ADMIN_PASSWORD=NOVA_PASS
NOVA_ADMIN_EMAIL=hao.li@bigswitch.com
CINDER_DB_PASSWORD=CINDER_DBPASS
CINDER_ADMIN_PASSWORD=CINDER_PASS
CINDER_ADMIN_EMAIL=hao.li@bigswitch.com
NEUTRON_DB_PASSWORD=NEUTRON_DBPASS
NEUTRON_ADMIN_PASSWORD=NEUTRON_PASS
NEUTRON_ADMIN_EMAIL=hao.li@bigswitch.com

keep_stock_conf() {
    CONF=$1
    if [ ! -f $CONF.stock ]; then
        mv $CONF $CONF.stock
    fi
}

configure_network() {
    # FIXME: Test that $HOSTNAME_CONTROLLER is this host.

    if ! ifconfig -s | egrep -qs "^$DATA_IF\b"; then
        cat >> /etc/network/interfaces <<EOF

auto $DATA_IF
iface $DATA_IF inet manual
EOF

        ifconfig $DATA_IF up
    fi
}

install_extra_packages() {
    apt-get -y install vim-nox debconf-utils python-mysqldb curl
}

# http://docs.openstack.org/trunk/install-guide/install/apt/content/basics-database.html
install_mysql () {
    echo mysql-server mysql-server/root_password password $MYSQL_ROOT_PASSWORD | debconf-set-selections
    echo mysql-server mysql-server/root_password_again password $MYSQL_ROOT_PASSWORD | debconf-set-selections
    apt-get -y install mysql-server

    apt-get -y install expect
    expect -c "
set timeout 10
spawn mysql_secure_installation
expect \"Enter current password for root (enter for none):\"
send \"$MYSQL_ROOT_PASSWORD\r\"
expect \"Change the root password?\"
send \"n\r\"
expect \"Remove anonymous users?\"
send \"y\r\"
expect \"Disallow root login remotely?\"
send \"y\r\"
expect \"Remove test database and access to it?\"
send \"y\r\"
expect \"Reload privilege tables now?\"
send \"y\r\"
expect eof
"

    sed -i '/^bind-address/s/^/# /' /etc/mysql/my.cnf
    service mysql restart

    cat > $HOME/.my.cnf <<EOF
[client]
password="$MYSQL_ROOT_PASSWORD"
EOF
    chmod 600 $HOME/.my.cnf
}

# http://docs.openstack.org/trunk/install-guide/install/apt/content/basics-queue.html
install_rabbitmq() {
    apt-get -y install rabbitmq-server

    # To change default guest/guest account, uncomment line below.
    #rabbitmqctl change_password guest NEW_PASS
}

# http://docs.openstack.org/trunk/install-guide/install/apt/content/keystone-install.html
install_keystone() {
    apt-get -y install keystone
    sed -i "s|^connection = sqlite:.*$|connection = mysql://keystone:$KEYSTONE_DB_PASSWORD@$HOSTNAME_CONTROLLER/keystone|" /etc/keystone/keystone.conf
    rm -f /var/lib/keystone/keystone.sqlite
    echo "
CREATE DATABASE IF NOT EXISTS keystone;
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'localhost' IDENTIFIED BY '$KEYSTONE_DB_PASSWORD';
GRANT ALL PRIVILEGES ON keystone.* TO 'keystone'@'%' IDENTIFIED BY '$KEYSTONE_DB_PASSWORD';
" | mysql -u root
    keystone-manage db_sync
    service keystone restart
    sleep 1
}

# http://docs.openstack.org/trunk/install-guide/install/apt/content/keystone-users.html
configure_auth() {
    TOKEN=$(openssl rand -hex 10)
    sed -i "s/^.*admin_token = .*$/admin_token = $TOKEN/" /etc/keystone/keystone.conf
    service keystone restart
    sleep 1
    unset OS_USERNAME OS_PASSWORD OS_TENANT_NAME OS_AUTH_URL
    export OS_SERVICE_TOKEN=$TOKEN
    export OS_SERVICE_ENDPOINT=http://$HOSTNAME_CONTROLLER:35357/v2.0

    if ! keystone tenant-get admin; then
        keystone tenant-create --name=admin --description="Admin Tenant"
    fi
    if ! keystone tenant-get service; then
        keystone tenant-create --name=service --description="Service Tenant"
    fi
    if ! keystone user-get admin; then
        keystone user-create --name=admin --pass=$KEYSTONE_ADMIN_PASSWORD --email=$KEYSTONE_ADMIN_EMAIL
    fi
    if ! keystone role-get admin; then
        keystone role-create --name=admin
        keystone user-role-add --user=admin --tenant=admin --role=admin
    fi

    if ! keystone service-get keystone; then
        keystone service-create --name=keystone --type=identity --description="Keystone Identity Service"
        id=$(keystone service-get keystone | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:5000/v2.0 \
            --internalurl=http://$HOSTNAME_CONTROLLER:5000/v2.0 \
            --adminurl=http://$HOSTNAME_CONTROLLER:35357/v2.0
    fi

    unset OS_SERVICE_TOKEN OS_SERVICE_ENDPOINT
    keystone --os-username=admin --os-password=$KEYSTONE_ADMIN_PASSWORD \
        --os-auth-url=http://$HOSTNAME_CONTROLLER:35357/v2.0 token-get
    keystone --os-username=admin --os-password=$KEYSTONE_ADMIN_PASSWORD \
        --os-tenant-name=admin \
        --os-auth-url=http://$HOSTNAME_CONTROLLER:35357/v2.0 token-get

    if [ ! -f $HOME/.openstackrc ]; then
        cat > $HOME/.openstackrc <<EOF
export OS_USERNAME=admin
export OS_PASSWORD=$KEYSTONE_ADMIN_PASSWORD
export OS_TENANT_NAME=admin
export OS_AUTH_URL=http://$HOSTNAME_CONTROLLER:35357/v2.0
EOF
        cat >> $HOME/.bashrc <<EOF
. ~/.openstackrc
EOF
    fi

    . $HOME/.openstackrc
    keystone token-get
    keystone user-list
}

# http://docs.openstack.org/havana/install-guide/install/apt/content/glance-install.html
install_glance() {
    apt-get -y install glance
    for file in glance-api.conf glance-registry.conf; do
        sed -i "s|^sql_connection = sqlite:.*$|sql_connection = mysql://glance:$GLANCE_DB_PASSWORD@$HOSTNAME_CONTROLLER/glance|" /etc/glance/$file
    done
    rm -f /var/lib/glance/glance.sqlite
    echo "
CREATE DATABASE IF NOT EXISTS glance;
GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'localhost' IDENTIFIED BY '$GLANCE_DB_PASSWORD';
GRANT ALL PRIVILEGES ON glance.* TO 'glance'@'%' IDENTIFIED BY '$GLANCE_DB_PASSWORD';
" | mysql -u root
    glance-manage db_sync

    if ! keystone user-get glance; then
        keystone user-create --name=glance --pass=$GLANCE_ADMIN_PASSWORD --email=$GLANCE_ADMIN_EMAIL
        keystone user-role-add --user=glance --tenant=service --role=admin
    fi

    for file in glance-api.conf glance-registry.conf; do
        sed -i \
            -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
            -e "s|%SERVICE_TENANT_NAME%|service|" \
            -e "s|%SERVICE_USER%|glance|" \
            -e "s|%SERVICE_PASSWORD%|$GLANCE_ADMIN_PASSWORD|" \
            /etc/glance/$file
    done

    for file in glance-api-paste.ini glance-registry-paste.ini; do
        if ! egrep -qs "^auth_host=" /etc/glance/$file; then
            sed -i "/keystoneclient\.middleware\.auth_token:filter_factory/a auth_host=$HOSTNAME_CONTROLLER\nadmin_user=glance\nadmin_tenant_name=service\nadmin_password=$GLANCE_ADMIN_PASSWORD" /etc/glance/$file
        fi
    done

    if ! keystone service-get glance; then
        keystone service-create --name=glance --type=image --description="Glance Image Service"
        id=$(keystone service-get glance | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:9292 \
            --internalurl=http://$HOSTNAME_CONTROLLER:9292 \
            --adminurl=http://$HOSTNAME_CONTROLLER:9292
    fi

    service glance-registry restart
    service glance-api restart
    sleep 1
}

# http://docs.openstack.org/havana/install-guide/install/apt/content/glance-verify.html
verify_glance() {
    glance image-list
    if [ -z "$(glance image-list --name='CirrOS-0.3.1' | sed '/^$/d')" ]; then
        curl -O http://cdn.download.cirros-cloud.net/0.3.1/cirros-0.3.1-x86_64-disk.img
        glance image-create --name=CirrOS-0.3.1 --disk-format=qcow2 \
            --container-format=bare --is-public=true < cirros-0.3.1-x86_64-disk.img
        glance image-list
    fi

    if [ -z "$(glance image-list --name='Ubuntu-12.04' | sed '/^$/d')" ]; then
        curl -O http://uec-images.ubuntu.com/precise/current/precise-server-cloudimg-amd64-disk1.img
        glance image-create --name=Ubuntu-12.04 --disk-format=qcow2 \
            --container-format=bare --is-public=true < precise-server-cloudimg-amd64-disk1.img
    fi
}

install_nova() {
    apt-get -y install nova-novncproxy novnc nova-api \
        nova-ajax-console-proxy nova-cert nova-conductor \
        nova-consoleauth nova-doc nova-scheduler \
        python-novaclient

    if ! egrep -qs '^\[database\]' /etc/nova/nova.conf; then
        cat >> /etc/nova/nova.conf <<EOF
my_ip=$MGMT_IP
vncserver_listen=$MGMT_IP
vncserver_proxyclient_address=$MGMT_IP
auth_strategy=keystone
rpc_backend=nova.rpc.impl_kombu
rabbit_host=$HOSTNAME_CONTROLLER

[database]
connection = mysql://nova:$NOVA_DB_PASSWORD@$HOSTNAME_CONTROLLER/nova
EOF
    fi
    rm -f /var/lib/nova/nova.sqlite
    echo "
CREATE DATABASE IF NOT EXISTS nova;
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'localhost' IDENTIFIED BY '$NOVA_DB_PASSWORD';
GRANT ALL PRIVILEGES ON nova.* TO 'nova'@'%' IDENTIFIED BY '$NOVA_DB_PASSWORD';
" | mysql -u root
    nova-manage db sync

    if ! keystone user-get nova; then
        keystone user-create --name=nova --pass=$NOVA_ADMIN_PASSWORD --email=$NOVA_ADMIN_EMAIL
        keystone user-role-add --user=nova --tenant=service --role=admin
    fi

    sed -i \
        -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
        -e "s|%SERVICE_TENANT_NAME%|service|" \
        -e "s|%SERVICE_USER%|nova|" \
        -e "s|%SERVICE_PASSWORD%|$NOVA_ADMIN_PASSWORD|" \
        /etc/nova/api-paste.ini

    if ! keystone service-get nova; then
        keystone service-create --name=nova --type=compute --description="Nova Compute service"
        id=$(keystone service-get nova | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:8774/v2/%\(tenant_id\)s \
            --internalurl=http://$HOSTNAME_CONTROLLER:8774/v2/%\(tenant_id\)s \
            --adminurl=http://$HOSTNAME_CONTROLLER:8774/v2/%\(tenant_id\)s
    fi

    service nova-api restart; sleep 1
    service nova-cert restart; sleep 1
    service nova-consoleauth restart; sleep 1
    service nova-scheduler restart; sleep 1
    service nova-conductor restart; sleep 1
    service nova-novncproxy restart; sleep 1

    nova image-list
}

install_horizon() {
    apt-get -y install apache2 memcached libapache2-mod-wsgi openstack-dashboard
    apt-get -y remove --purge openstack-dashboard-ubuntu-theme
    a2enmod wsgi
    a2enconf openstack-dashboard

    # Fix bug https://bugzilla.redhat.com/show_bug.cgi?id=888516 by telling
    # Horizon to use role "_member_" instead of "Member".
    sed -i 's/Member/_member_/' /etc/openstack-dashboard/local_settings.py

    # FIXME: Automatic redirect http://host/ to http://host/horizon/
    # cat > /var/www/index.html <<EOF
    # <html><head><meta http-equiv="refresh" content="0; URL=http://$HOSTNAME_CONTROLLER/horizon/"></head></html>
    # EOF

    service apache2 restart
}

install_cinder() {
    apt-get -y install cinder-api cinder-scheduler
    if ! egrep -qs '^\[database\]' /etc/cinder/cinder.conf; then
        cat >> /etc/cinder/cinder.conf <<EOF
rpc_backend = cinder.openstack.common.rpc.impl_kombu
rabbit_host = $HOSTNAME_CONTROLLER
rabbit_port = 5672
rabbit_userid = guest
rabbit_password = guest

[database]
connection = mysql://cinder:$CINDER_DB_PASSWORD@$HOSTNAME_CONTROLLER/cinder
EOF
    fi
    rm -f /var/lib/cinder/cinder.sqlite
    echo "
CREATE DATABASE IF NOT EXISTS cinder;
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'localhost' IDENTIFIED BY '$CINDER_DB_PASSWORD';
GRANT ALL PRIVILEGES ON cinder.* TO 'cinder'@'%' IDENTIFIED BY '$CINDER_DB_PASSWORD';
" | mysql -u root
    cinder-manage db sync

    if ! keystone user-get cinder; then
        keystone user-create --name=cinder --pass=$CINDER_ADMIN_PASSWORD --email=$CINDER_ADMIN_EMAIL
        keystone user-role-add --user=cinder --tenant=service --role=admin
    fi

    sed -i \
        -e "s|^auth_host = .*$|auth_host = $HOSTNAME_CONTROLLER|" \
        -e "s|%SERVICE_TENANT_NAME%|service|" \
        -e "s|%SERVICE_USER%|cinder|" \
        -e "s|%SERVICE_PASSWORD%|$CINDER_ADMIN_PASSWORD|" \
        /etc/cinder/api-paste.ini

    if ! keystone service-get cinder; then
        keystone service-create --name=cinder --type=volume --description="Cinder Volume Service"
        id=$(keystone service-get cinder | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:8776/v1/%\(tenant_id\)s \
            --internalurl=http://$HOSTNAME_CONTROLLER:8776/v1/%\(tenant_id\)s \
            --adminurl=http://$HOSTNAME_CONTROLLER:8776/v1/%\(tenant_id\)s
    fi

    if ! keystone service-get cinderv2; then
        keystone service-create --name=cinderv2 --type=volumev2 --description="Cinder Volume Service V2"
        id=$(keystone service-get cinderv2 | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:8776/v2/%\(tenant_id\)s \
            --internalurl=http://$HOSTNAME_CONTROLLER:8776/v2/%\(tenant_id\)s \
            --adminurl=http://$HOSTNAME_CONTROLLER:8776/v2/%\(tenant_id\)s
    fi

    service cinder-scheduler restart; sleep 1
    service cinder-api restart; sleep 1
}

# The function below installs cinder volume on controller, which is convenient
# but not best practice. Best pratice is to install cinder volume on dedicated
# hardware. That's done with install_cinder_node.sh.
install_cinder_node() {
    apt-get -y install cinder-volume lvm2 open-iscsi

    # Prep LVM
    LOOPDEV=/dev/loop2
    FILE=/data/cinder-volumes

    if ! vgdisplay cinder-volumes; then
        dd if=/dev/zero of=$FILE bs=1 count=0 seek=100G
        dd if=/dev/zero of=$FILE bs=512 count=1 conv=notrunc
        losetup $LOOPDEV $FILE
        # fdisk returns 1 even when done
        printf "n\np\n1\n\n\nt\n8e\nw\n" | fdisk $LOOPDEV || :
        pvcreate $LOOPDEV
        vgcreate cinder-volumes $LOOPDEV
    fi

    service cinder-volume restart; sleep 1
    service tgt restart; sleep 1
}

# There are 5 parts of neutron setup, based on
# http://docs.openstack.org/havana/install-guide/install/apt/content/neutron-install-network-node.html
#
# 1. MySQL and keystone setup. Done on controller.
# 2. Install neutron and OVS plugin on dedicated network node (which does L3 routing).
# 3. Install neutron and OVS plugin on controller (which only needs L2 config)
# 4. Install neutron and OVS plugin on compute node (which only needs L2 config)
# 5. Create base Neutron networks
#
# Steps 2, 3 and 4 are almost identical with subtle differences. It is better illustrated
# in this table:
#
# ----------------------------------------------------------------------------
# Where           neutron-server L3           L2 agents
# ----------------------------------------------------------------------------
# network node    -              Y            Y
# controller      Y              -            -
# compute node    -              -            Y
# ----------------------------------------------------------------------------

# http://docs.openstack.org/havana/install-guide/install/apt/content/neutron-install-network-node.html
prep_neutron() {
    rm -f /var/lib/neutron/neutron.sqlite
    echo "
CREATE DATABASE IF NOT EXISTS neutron;
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'localhost' IDENTIFIED BY '$NEUTRON_DB_PASSWORD';
GRANT ALL PRIVILEGES ON neutron.* TO 'neutron'@'%' IDENTIFIED BY '$NEUTRON_DB_PASSWORD';
" | mysql -u root

    if ! keystone user-get neutron; then
        keystone user-create --name=neutron --pass=$NEUTRON_ADMIN_PASSWORD --email=$NEUTRON_ADMIN_EMAIL
        keystone user-role-add --user=neutron --tenant=service --role=admin
    fi


    if ! keystone service-get neutron; then
        keystone service-create --name=neutron --type=network --description="OpenStack Networking Service"
        id=$(keystone service-get neutron | sed -n 's/^| *id *| \([0-9a-f]\+\) |$/\1/p')
        keystone endpoint-create \
            --service-id=$id \
            --publicurl=http://$HOSTNAME_CONTROLLER:9696 \
            --internalurl=http://$HOSTNAME_CONTROLLER:9696 \
            --adminurl=http://$HOSTNAME_CONTROLLER:9696
    fi
}

# http://docs.openstack.org/havana/install-guide/install/apt/content/neutron-install.dedicated-network-node.html
# Ideally this should be done on a separate box, but we decide to put it on controller box.
install_neutron_server() {
    # FIXME: Verify that the host has at least 3 network interfaces:
    # $MGMT_IF, $DATA_IF and $EXTERNAL_IF.
    # That's required only on the "dedicated network node" which does L3 routing
    # between the OpenStack DATA network and EXTERNAL network

    apt-get -y install neutron-server neutron-dhcp-agent openvswitch-switch openvswitch-datapath-dkms

    # Must disable metadata-agent for BSN plugin
    service neutron-metadata-agent stop
    echo manual > /etc/init/neutron-metadata-agent.override

    # Enable packet forwarding which is required for L3 routing.
    # Disable packet destination filtering which is required for network node and compute node.
    cat > /etc/sysctl.conf <<EOF
net.ipv4.ip_forward=1
net.ipv4.conf.all.rp_filter=0
net.ipv4.conf.default.rp_filter=0
EOF
    service procps restart; sleep 1

    # neutron.conf and api-paste.ini config which is common to all neutron installations
    keep_stock_conf /etc/neutron/neutron.conf
    cat > /etc/neutron/neutron.conf <<EOF
[DEFAULT]
state_path = /var/lib/neutron
lock_path = \$state_path/lock
core_plugin = neutron.plugins.openvswitch.ovs_neutron_plugin.OVSNeutronPluginV2
allow_overlapping_ips = True
rabbit_host = $HOSTNAME_CONTROLLER
rabbit_password = guest
rabbit_userid = guest
notification_driver = neutron.openstack.common.notifier.rpc_notifier
[quotas]
[agent]
root_helper = sudo /usr/bin/neutron-rootwrap /etc/neutron/rootwrap.conf
[keystone_authtoken]
auth_host = $HOSTNAME_CONTROLLER
auth_port = 35357
auth_protocol = http
admin_tenant_name = service
admin_user = neutron
admin_password = $NEUTRON_ADMIN_PASSWORD
signing_dir = \$state_path/keystone-signing
[database]
connection = mysql://neutron:$NEUTRON_DB_PASSWORD@$HOSTNAME_CONTROLLER/neutron
[service_providers]
service_provider=LOADBALANCER:Haproxy:neutron.services.loadbalancer.drivers.haproxy.plugin_driver.HaproxyOnHostPluginDriver:default
EOF

    if ! egrep -qs "^auth_host=" /etc/neutron/api-paste.ini; then
        sed -i "/keystoneclient\.middleware\.auth_token:filter_factory/a auth_host=$HOSTNAME_CONTROLLER\nauth_port = 35357\nauth_protocol = http\nadmin_tenant_name=service\nadmin_user=neutron\nadmin_password=$NEUTRON_ADMIN_PASSWORD" /etc/neutron/api-paste.ini
    fi

    # Tell Nova about Neutron
    if ! egrep -qs "^firewall_driver=" /etc/nova/nova.conf; then
        sed -i "/\[DEFAULT\]/a network_api_class=nova.network.neutronv2.api.API\nneutron_url=http://$HOSTNAME_CONTROLLER:9696\nneutron_auth_strategy=keystone\nneutron_admin_tenant_name=service\nneutron_admin_username=neutron\nneutron_admin_password=$NEUTRON_ADMIN_PASSWORD\nneutron_admin_auth_url=http://$HOSTNAME_CONTROLLER:35357/v2.0\nlibvirt_vif_driver=nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver\nlinuxnet_interface_driver=nova.network.linux_net.LinuxOVSInterfaceDriver\nfirewall_driver=nova.virt.libvirt.firewall.IptablesFirewallDriver" /etc/nova/nova.conf
    fi

    service neutron-server restart; sleep 1

    service nova-api restart; sleep 1
    service nova-cert restart; sleep 1
    service nova-consoleauth restart; sleep 1
    service nova-scheduler restart; sleep 1
    service nova-conductor restart; sleep 1
    service nova-novncproxy restart; sleep 1

    if ! ovs-vsctl br-exists br-int; then
        ovs-vsctl add-br br-int
        ovs-vsctl add-port br-int $DATA_IF
    fi
}

install_neutron_bsn_plugin() {
    ./install-plugin-havana.sh neutron $NEUTRON_DB_PASSWORD $BSN_CONTROLLER:80 ovs

    sed -i 's|^NEUTRON_PLUGIN_CONFIG=.*$|NEUTRON_PLUGIN_CONFIG="/etc/neutron/plugins/bigswitch/restproxy.ini"|' /etc/default/neutron-server
    service neutron-server restart; sleep 1

    ovs-vsctl set-controller br-int tcp:$BSN_CONTROLLER:6633
}

# Execution starts here

configure_network
install_extra_packages
install_mysql
install_rabbitmq
install_keystone
configure_auth
. $HOME/.openstackrc

install_glance
verify_glance
install_nova
install_horizon
install_cinder
install_cinder_node
prep_neutron
install_neutron_server
install_neutron_bsn_plugin

echo "OpenStack controller node installation completed."
