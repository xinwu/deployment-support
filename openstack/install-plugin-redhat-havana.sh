#!/usr/bin/env bash
#
# This script patches a RedHat openstack havana install with BigSwitch changes
#
# Big Switch Plugin: https://github.com/bigswitch/neutron/tree/havana/stable
#
# @author: Kevin Benton, Big Switch Networks, Inc.
# @date: July 20, 2013
#
# See usage below:
USAGE="$0 bsn-conotroller-ip:port[,bsn-controller-ip:port]* db-admin-user [db-admin-password db_ip db_port]"

DATE=$(date +"%Y%m%d%H%M")
exec >  >(tee -a patchlog-$DATE.log | grep -v '^+')
exec 2> >(tee -a patchlog-$DATE.log | grep -v '^+' >&2)
trap "sleep 1" exit
set -x
set -e

umask 022

RESTPROXY_CONTROLLER=$1
DATABASE_USER=$2
DATABASE_PASSWORD=$3
TEMP_DIR='/tmp/bsn'
Q_DB_NAME='restproxy_neutron'
PLUGIN_URL='https://github.com/bigswitch/neutron/archive/havana/stable.tar.gz'
PLUGIN_TAR='bsn.tar.gz'
HORIZON_URL='https://github.com/bigswitch/horizon/archive/stable/havana_routerrules.tar.gz'
TEMP_PLUGIN_PATH='/neutron-havana-stable/neutron/plugins/bigswitch'
TEMP_PLUGIN_CONF_PATH='/neutron-havana-stable/etc/neutron/plugins/bigswitch'
Q_PLUGIN_CLASS="neutron.plugins.bigswitch.plugin.NeutronRestProxyV2"
NEUTRON_CONF_FILENAME="neutron.conf"
DHCP_AGENT_CONF_FILENAME="dhcp_agent.ini"
DATABASE_HOST=${4:-'127.0.0.1'}
DATABASE_PORT=${5:-'3306'}
PLUGIN_NAME="bigswitch"
Q_LOCK_PATH='/run/lock/neutron'
DB_PLUGIN_USER=neutronUser
DB_PLUGIN_PASS="$RANDOM$RANDOM"
DHCP_LEASE_TIME=43200
NEUTRON_ID="Quantum"

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

function SetupDB() {
    mysql -u$DATABASE_USER $DB_PASS_PARAMS --host=$DATABASE_HOST --port=$DATABASE_PORT -e "CREATE DATABASE IF NOT EXISTS $Q_DB_NAME;" 
    mysql -u$DATABASE_USER $DB_PASS_PARAMS --host=$DATABASE_HOST --port=$DATABASE_PORT -e "GRANT ALL ON $Q_DB_NAME.* TO '$DB_PLUGIN_USER'@'%' IDENTIFIED BY '$DB_PLUGIN_PASS';" $Q_DB_NAME
}

function PatchNeutron() {
    DHCP_INTERFACE_DRIVER="neutron.agent.linux.interface.OVSInterfaceDriver"
    BSN_VIF_TYPE="ovs"

    local DOWNLOAD_DIR="$TEMP_DIR"
    local DOWNLOAD_FILE="$DOWNLOAD_DIR/$PLUGIN_TAR"

    # Create a directory for the downloaded plugin tar
    mkdir -p $DOWNLOAD_DIR
    echo "Downloading BigSwitch neutron files"
    wget -c $PLUGIN_URL -O $DOWNLOAD_FILE
    if [[ $? -ne 0 ]]; then
        echo "Not found: $DOWNLOAD_DIR"
        exit
    fi
    tar -zxf $DOWNLOAD_FILE -C "$DOWNLOAD_DIR"


    local neutron_conf=`rpm -ql openstack-neutron | grep "$NEUTRON_CONF_FILENAME"`
    local nova_conf=`rpm -ql openstack-nova-common | grep "/nova.conf"`
    local neutron_conf_dir=`dirname $neutron_conf`
    local neutron_conf_orig="$neutron_conf.orig"
    local dhcp_conf=`rpm -ql openstack-neutron | grep "$DHCP_AGENT_CONF_FILENAME"`
    local dhcp_conf_dir=`dirname $dhcp_conf`
    local dhcp_conf_orig="$dhcp_conf.orig"
    if [ ! -f $neutron_conf_orig ];
    then
       cp $neutron_conf $neutron_conf_orig
    fi
    if [ ! -f $dhcp_conf_orig ];
    then
       cp $dhcp_conf $dhcp_conf_orig
    fi
    if [ ! -f "$neutron_conf_dir/plugin.ini.orig" ];
    then
       cp "$neutron_conf_dir/plugin.ini" "$neutron_conf_dir/plugin.ini.orig"
    fi
    local neutron_conf_plugins_dir="$neutron_conf_dir/plugins"
    local neutron_conf_bigswitch_plugins_dir="$neutron_conf_plugins_dir/$PLUGIN_NAME"
    mkdir -p $neutron_conf_bigswitch_plugins_dir
    #local plugin_conf_file="$neutron_conf_bigswitch_plugins_dir/restproxy.ini"
    local plugin_conf_file="$neutron_conf_dir/plugin.ini"
    iniset $neutron_conf DEFAULT core_plugin $Q_PLUGIN_CLASS
    iniset $neutron_conf DEFAULT allow_overlapping_ips False
    iniset $neutron_conf DEFAULT ovs_use_veth False
    iniset $neutron_conf DEFAULT force_gateway_on_subnet True
    iniset $neutron_conf DEFAULT dhcp_lease_duration $DHCP_LEASE_TIME
    echo "" > $plugin_conf_file
    iniset $plugin_conf_file RESTPROXY servers $RESTPROXY_CONTROLLER
    iniset $plugin_conf_file restproxy neutron_id $NEUTRON_ID
    iniset $plugin_conf_file DATABASE sql_connection "mysql://$DB_PLUGIN_USER:$DB_PLUGIN_PASS@$DATABASE_HOST:$DATABASE_PORT/$Q_DB_NAME"
    iniset $plugin_conf_file NOVA vif_type $BSN_VIF_TYPE
    iniset $dhcp_conf DEFAULT interface_driver $DHCP_INTERFACE_DRIVER
    iniset $dhcp_conf DEFAULT use_namespaces False
    iniset $dhcp_conf DEFAULT dhcp_lease_time $DHCP_LEASE_TIME
    iniset $nova_conf DEFAULT security_group_api nova
    iniset $nova_conf DEFAULT firewall_driver nova.virt.libvirt.firewall.IptablesFirewallDriver
    iniset $nova_conf DEFAULT service_neutron_metadata_proxy False
    
    echo "Patching neutron files"
    local baseneutron_install_path=`python -c "import neutron; print neutron.__path__[0]"`
    cp -R "$DOWNLOAD_DIR/neutron-havana-stable/neutron/plugins/bigswitch" "$baseneutron_install_path/plugins/"
    local NEUTRON_FILES_TO_PATCH=('agent/linux/interface.py' 'extensions/portbindings.py')
    local undocommand=''

    for to_patch in "${NEUTRON_FILES_TO_PATCH[@]}"
    do
        undocommand="$undocommand mv '$baseneutron_install_path/$to_patch.orig' '$baseneutron_install_path/$to_patch';"
        echo "Patching: $baseneutron_install_path/$to_patch <- $DOWNLOAD_DIR/neutron-havana-stable/neutron/$to_patch"
        mv "$baseneutron_install_path/$to_patch" "$baseneutron_install_path/$to_patch.orig"
        cp_it "$DOWNLOAD_DIR/neutron-havana-stable/neutron/$to_patch" "$baseneutron_install_path/$to_patch"
    done

    echo "To revert this patch:"
    echo "mv $neutron_conf_orig $neutron_conf; mv $dhcp_conf_orig $dhcp_conf; $undocommand"
    rm -rf $DOWNLOAD_DIR
    /etc/init.d/neutron-openvswitch-agent stop ||:
    /etc/init.d/neutron-l3-agent stop ||:
    /etc/init.d/neutron-metadata-agent stop ||:
    /etc/init.d/neutron-lbaas-agent stop ||:
    chkconfig neutron-openvswitch-agent off
    chkconfig neutron-l3-agent off
    chkconfig neutron-metadata-agent off
    chkconfig neutron-lbaas-agent off
    iptables -D FORWARD -j REJECT --reject-with icmp-host-prohibited ||:
    sed -i 's/-A FORWARD -j REJECT --reject-with icmp-host-prohibited/# Commented out by BigSwitch script\n#-A FORWARD -j REJECT --reject-with icmp-host-prohibited/g' /etc/sysconfig/iptables
    iptables -D INPUT -j REJECT --reject-with icmp-host-prohibited ||:
    sed -i 's/-A INPUT -j REJECT --reject-with icmp-host-prohibited/# Commented out by BigSwitch script\n#-A INPUT -j REJECT --reject-with icmp-host-prohibited/g' /etc/sysconfig/iptables
    echo 1 > /proc/sys/net/ipv4/ip_forward
    sed -i 's/net.ipv4.ip_forward = 0/net.ipv4.ip_forward = 1/g' /etc/sysctl.conf
    ip addr add 169.254.169.254/32 scope link dev lo ||:
    INTCONF=$(cat <<EOF
      ISALIAS=yes
      DEVICE=lo:0
      ONBOOT=yes
      BOOTPROTO=none
      IPADDR=169.254.169.254
      NETMASK=255.255.255.255
EOF
)
    echo "$INTCONF" > /etc/sysconfig/network-scripts/ifcfg-lo:0
    ln /etc/sysconfig/network-scripts/ifcfg-lo:0 /etc/sysconfig/networking/devices/ifcfg-lo:0 ||:
    ln /etc/sysconfig/network-scripts/ifcfg-lo:0 /etc/sysconfig/networking/profiles/default/ifcfg-lo:0 ||:
    iptables -t nat -A PREROUTING -d 169.254.169.254/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination 169.254.169.254:8775
    sed -i 's/-A PREROUTING -j nova-api-PREROUTING/-A PREROUTING -j nova-api-PREROUTING\n-A PREROUTING -d 169.254.169.254\/32 -p tcp -m tcp --dport 80 -j DNAT --to-destination 169.254.169.254:8775/g' /etc/sysconfig/iptables
}


function InstallBigHorizon() {
    local DOWNLOAD_DIR="$TEMP_DIR"
    local DOWNLOAD_FILE="$DOWNLOAD_DIR/$PLUGIN_TAR"

    local SETTINGS_PATH=`rpm -ql openstack-dashboard | grep local_settings.py$`
    if [ -z "$SETTINGS_PATH" ]
    then
       echo "Horizon is not installed on this server. Skipping Horizon patch"
       return
    fi


    # Create a directory for the downloaded plugin tar
    mkdir -p $DOWNLOAD_DIR

    echo "Downloading BigSwitch Horizon files"
    wget -c $HORIZON_URL -O $DOWNLOAD_FILE
    if [[ $? -ne 0 ]]; then
        echo "Not found: $DOWNLOAD_DIR"
        exit
    fi
    tar -zxf $DOWNLOAD_FILE -C "$DOWNLOAD_DIR"
    mkdir -p /usr/lib/bigswitch/static
    cp -R $DOWNLOAD_DIR/horizon-stable-havana_routerrules/* /usr/lib/bigswitch
    cp "$SETTINGS_PATH" "/usr/lib/bigswitch/openstack_dashboard/local/"
    rm -rf /usr/lib/bigswitch/static ||:
    ln -s `rpm -ql openstack-dashboard | grep local_settings.py | xargs dirname`/../../static /usr/lib/bigswitch/static ||:
    sed -i "s/LOGIN_URL='\/dashboard\/auth\/login\/'/LOGIN_URL='\/bigdashboard\/auth\/login\/'/g"  /usr/lib/bigswitch/openstack_dashboard/local/local_settings.py
    sed -i "s/LOGIN_REDIRECT_URL='\/dashboard'/LOGIN_REDIRECT_URL='\/bigdashboard'/g"  /usr/lib/bigswitch/openstack_dashboard/local/local_settings.py

    APACHECONF=$(cat <<EOF
	WSGIDaemonProcess bigdashboard
	WSGIProcessGroup bigdashboard
	WSGISocketPrefix run/wsgi

	WSGIScriptAlias /bigdashboard /usr/lib/bigswitch/openstack_dashboard/wsgi/django.wsgi

	<Directory /usr/lib/bigswitch/openstack_dashboard/wsgi>
	  <IfModule mod_deflate.c>
	    SetOutputFilter DEFLATE
	    <IfModule mod_headers.c>
	      # Make sure proxies don’t deliver the wrong content
	      Header append Vary User-Agent env=!dont-vary
	    </IfModule>
	  </IfModule>

	  Order allow,deny
	  Allow from all
	</Directory>

	<Location /bigdashboard/i18n>
	  <IfModule mod_expires.c>
	    ExpiresActive On
	    ExpiresDefault "access 6 month"
	  </IfModule>
	</Location>
EOF
)
    echo "$APACHECONF" > /etc/httpd/conf.d/bigswitch-dashboard.conf
    rm -rf $DOWNLOAD_DIR
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
# Validate args
if [ "${DATABASE_USER}"x = ""x ] ; then
    echo "ERROR: DATABASE_USER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${DATABASE_PASSWORD}"x = ""x ] ; then
    DB_PASS_PARAMS=""
else
    DB_PASS_PARAMS="-p$DATABASE_PASSWORD"
fi
if [ "${RESTPROXY_CONTROLLER}"x = ""x ] ; then
    echo "ERROR: RESTPROXY_CONTROLLER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
SetupDB
InstallBigHorizon
PatchNeutron
SetOVSController
echo "Done patching services. Restarting services..."
/etc/init.d/neutron-server restart ||:
/etc/init.d/neutron-dhcp-agent restart ||:
/etc/init.d/httpd restart ||:
/etc/init.d/openstack-nova-api restart ||:
/etc/init.d/openstack-nova-compute restart ||:
