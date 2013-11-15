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


# Definitions that can be customized per installation

# This hostname should resolve to the IP of the interface on management
# network, often em1.
HOSTNAME_CONTROLLER=controller

# The interface on openstack "internal" network.
INTERNAL_IF=em2
INTERNAL_IP=10.203.1.13
INTERNAL_NETMASK=255.255.255.0

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


configure_network() {
    # FIXME: Test that $HOSTNAME_CONTROLLER is this host.

    if ! ifconfig -s | egrep -qs "^$INTERNAL_IF\b"; then
        cat >> /etc/network/interfaces <<EOF
# The OpenStack internal interface
auto $INTERNAL_IF
iface $INTERNAL_IF inet static
address $INTERNAL_IP
netmask $INTERNAL_NETMASK
EOF
        /sbin/ifup $INTERNAL_IF
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

    export OS_USERNAME=admin
    export OS_PASSWORD=$KEYSTONE_ADMIN_PASSWORD
    export OS_TENANT_NAME=admin
    export OS_AUTH_URL=http://$HOSTNAME_CONTROLLER:35357/v2.0
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
    if [ -z "$(glance image-list --name='CirrOS 0.3.1' | sed '/^$/d')" ]; then
        curl -O http://cdn.download.cirros-cloud.net/0.3.1/cirros-0.3.1-x86_64-disk.img
        glance image-create --name="CirrOS 0.3.1" --disk-format=qcow2 \
            --container-format=bare --is-public=true < cirros-0.3.1-x86_64-disk.img
        glance image-list
    fi
}

install_nova() {
    apt-get -y install nova-novncproxy novnc nova-api \
        nova-ajax-console-proxy nova-cert nova-conductor \
        nova-consoleauth nova-doc nova-scheduler \
        python-novaclient

    if ! egrep -qs '^\[database\]' /etc/nova/nova.conf; then
        cat >> /etc/nova/nova.conf <<EOF
my_ip=$INTERNAL_IP
vncserver_listen=$INTERNAL_IP
vncserver_proxyclient_address=$INTERNAL_IP
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

    # Command below will fail if $INTERNAL_IP is not up.
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

    service apache2 restart
}


# Execution starts here

configure_network
install_extra_packages
install_mysql
install_rabbitmq
install_keystone
configure_auth

export OS_USERNAME=admin
export OS_PASSWORD=$KEYSTONE_ADMIN_PASSWORD
export OS_TENANT_NAME=admin
export OS_AUTH_URL=http://$HOSTNAME_CONTROLLER:35357/v2.0

install_glance
verify_glance
install_nova
install_horizon
