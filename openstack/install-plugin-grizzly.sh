#!/usr/bin/env bash
#
# This script patches the OpenStack Quantum Folsom Ubuntu packages installation
# with the Big Switch Network's Quantum Plugin.
#
# Supported Ubuntu version: 12.10
# Big Switch Plugin: https://github.com/bigswitch/quantum/tree/grizzly/stable
#
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: January 27 2013
#
# See usage below:
USAGE="$0 db_user db_password bsn-conotroller-ip:port[,bsn-controller-ip:port]* <interface-type ('ovs' or 'ivs')> [<db_ip> <db_port>]"

set -e
XTRACE=$(set +o | grep xtrace)
set +o xtrace

umask 022

DATABASE_USER=$1
DATABASE_PASSWORD=$2
RESTPROXY_CONTROLLER=$3
VIF_TYPE=$4
TEMP_DIR='/tmp/bsn'
Q_DB_NAME='quantum'
PLUGIN_URL='https://github.com/bigswitch/quantum/archive/grizzly/stable.tar.gz'
PLUGIN_TAR='bsn.tar.gz'
NOVA_REPO_BASE='https://raw.github.com/bigswitch/nova/kbenton/ivssupport_grizzly/'
HORIZON_REPO_BASE='https://raw.github.com/bigswitch/horizon/grizzly/router_rules/'
TEMP_PLUGIN_PATH='/neutron-grizzly-stable/quantum/plugins/bigswitch'
TEMP_PLUGIN_CONF_PATH='/neutron-grizzly-stable/etc/quantum/plugins/bigswitch'
Q_PLUGIN_CLASS="quantum.plugins.bigswitch.plugin.QuantumRestProxyV2"
QUANTUM_CONF_FILENAME="quantum.conf"
DHCP_AGENT_CONF_FILENAME="dhcp_agent.ini"
DATABASE_HOST=${5:-'127.0.0.1'}
DATABASE_PORT=${6:-'3306'}
PLUGIN_NAME="bigswitch"
Q_LOCK_PATH='/run/lock/quantum'

# Gracefully cp only if source file/dir exists
# cp_it source destination
function cp_it {
    if [ -e $1 ] || [ -d $1 ]; then
        cp -pRL $1 $2
    fi
}


# Determine OS Vendor, Release and Update
# Tested with OS/X, Ubuntu, RedHat, CentOS, Fedora
# Returns results in global variables:
# os_VENDOR - vendor name
# os_RELEASE - release
# os_UPDATE - update
# os_PACKAGE - package type
# os_CODENAME - vendor's codename for release
# GetOSVersion
GetOSVersion() {
    # Figure out which vendor we are
    if [[ -n "`which sw_vers 2>/dev/null`" ]]; then
        # OS/X
        os_VENDOR=`sw_vers -productName`
        os_RELEASE=`sw_vers -productVersion`
        os_UPDATE=${os_RELEASE##*.}
        os_RELEASE=${os_RELEASE%.*}
        os_PACKAGE=""
        if [[ "$os_RELEASE" =~ "10.7" ]]; then
            os_CODENAME="lion"
        elif [[ "$os_RELEASE" =~ "10.6" ]]; then
            os_CODENAME="snow leopard"
        elif [[ "$os_RELEASE" =~ "10.5" ]]; then
            os_CODENAME="leopard"
        elif [[ "$os_RELEASE" =~ "10.4" ]]; then
            os_CODENAME="tiger"
        elif [[ "$os_RELEASE" =~ "10.3" ]]; then
            os_CODENAME="panther"
        else
            os_CODENAME=""
        fi
    elif [[ -x $(which lsb_release 2>/dev/null) ]]; then
        os_VENDOR=$(lsb_release -i -s)
        os_RELEASE=$(lsb_release -r -s)
        os_UPDATE=""
        if [[ "Debian,Ubuntu" =~ $os_VENDOR ]]; then
            os_PACKAGE="deb"
            QUANTUM_SERVER_CONF_FILE="/etc/default/quantum-server"
        else
            os_PACKAGE="rpm"
        fi
        os_CODENAME=$(lsb_release -c -s)
    elif [[ -r /etc/redhat-release ]]; then
        # Red Hat Enterprise Linux Server release 5.5 (Tikanga)
        # CentOS release 5.5 (Final)
        # CentOS Linux release 6.0 (Final)
        # Fedora release 16 (Verne)
        os_CODENAME=""
        for r in "Red Hat" CentOS Fedora; do
            os_VENDOR=$r
            if [[ -n "`grep \"$r\" /etc/redhat-release`" ]]; then
                ver=`sed -e 's/^.* \(.*\) (\(.*\)).*$/\1\|\2/' /etc/redhat-release`
                os_CODENAME=${ver#*|}
                os_RELEASE=${ver%|*}
                os_UPDATE=${os_RELEASE##*.}
                os_RELEASE=${os_RELEASE%.*}
                break
            fi
            os_VENDOR=""
        done
        os_PACKAGE="rpm"
    fi
    export os_VENDOR os_RELEASE os_UPDATE os_PACKAGE os_CODENAME
}


# Translate the OS version values into common nomenclature
# Sets ``DISTRO`` from the ``os_*`` values
function GetDistro() {
    GetOSVersion
    if [[ "$os_VENDOR" =~ (Ubuntu) ]]; then
        # 'Everyone' refers to Ubuntu releases by the code name adjective
        DISTRO=$os_CODENAME
    elif [[ "$os_VENDOR" =~ (Fedora) ]]; then
        # For Fedora, just use 'f' and the release
        DISTRO="f$os_RELEASE"
    else
        # Catch-all for now is Vendor + Release + Update
        DISTRO="$os_VENDOR-$os_RELEASE.$os_UPDATE"
    fi
    export DISTRO
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


# Distro-agnostic function to tell if a package is installed
# is_package_installed package [package ...]
function is_package_installed() {
    if [[ -z "$@" ]]; then
        return 1
    fi

    if [[ -z "$os_PACKAGE" ]]; then
        GetOSVersion
    fi
    if [[ "$os_PACKAGE" = "deb" ]]; then
        dpkg -l "$@" > /dev/null
        return $?
    else
        rpm --quiet -q "$@"
        return $?
    fi
}


function InstallPluginOnUbuntu() {
    if [ ! -f $QUANTUM_SERVER_CONF_FILE ];
    then
        die "Error: Package quantum-server is installed but could not find /etc/default/quantum-server"
    fi
    if [ "$VIF_TYPE" = "ovs" ]; then
        DHCP_INTERFACE_DRIVER="quantum.agent.linux.interface.OVSInterfaceDriver"
        BSN_VIF_TYPE="ovs"
    elif [ "$VIF_TYPE" = "ivs" ]; then
        DHCP_INTERFACE_DRIVER="quantum.agent.linux.interface.IVSInterfaceDriver"
        BSN_VIF_TYPE="ivs"
    else
        die "Unrecognized virtual interface type '$VIF_TYPE'. Available opions are 'ovs' and 'ivs'"
    fi
    local image_url=$1
    local token=$2
    local DOWNLOAD_DIR="$TEMP_DIR"
    local DOWNLOAD_FILE="$DOWNLOAD_DIR/$PLUGIN_TAR"

    # Create a directory for the downloaded plugin tar
    mkdir -p $DOWNLOAD_DIR
    wget -c $PLUGIN_URL -O $DOWNLOAD_FILE
    if [[ $? -ne 0 ]]; then
        echo "Not found: $DOWNLOAD_DIR"
        exit
    fi
    tar -zxf $DOWNLOAD_FILE -C "$DOWNLOAD_DIR"
    local plugin_install_path=`python -c "import quantum.plugins; print quantum.plugins.__path__[0]"`
    echo "Installing plugin in: $plugin_install_path/$PLUGIN_NAME"
    cp_it $DOWNLOAD_DIR$TEMP_PLUGIN_PATH $plugin_install_path
    local quantum_conf=`dpkg -L quantum-common | grep "$QUANTUM_CONF_FILENAME"`
    local quantum_conf_dir=`dirname $quantum_conf`
    local quantum_conf_orig="$quantum_conf.orig"
    local dhcp_conf=`dpkg -L quantum-dhcp-agent | grep "$DHCP_AGENT_CONF_FILENAME"`
    local dhcp_conf_dir=`dirname $dhcp_conf`
    local dhcp_conf_orig="$dhcp_conf.orig"
    local QUANTUM_SERVER_CONF_FILE_orig="$QUANTUM_SERVER_CONF_FILE.orig"
    if [ ! -f $quantum_conf_orig ];
    then
       cp $quantum_conf $quantum_conf_orig
    fi
    if [ ! -f $dhcp_conf_orig ];
    then
       cp $dhcp_conf $dhcp_conf_orig
    fi
    if [ ! -f $QUANTUM_SERVER_CONF_FILE_orig ];
    then
       cp $QUANTUM_SERVER_CONF_FILE $QUANTUM_SERVER_CONF_FILE_orig
    fi
    local quantum_conf_plugins_dir="$quantum_conf_dir/plugins"
    local quantum_conf_bigswitch_plugins_dir="$quantum_conf_plugins_dir/$PLUGIN_NAME"
    mkdir -p $quantum_conf_bigswitch_plugins_dir
    local plugin_conf_file="$quantum_conf_bigswitch_plugins_dir/restproxy.ini"

    echo "Patching quantum files for IVS support"
    local basequantum_install_path=`python -c "import quantum; print quantum.__path__[0]"`
    local QUANTUM_FILES_TO_PATCH=('agent/linux/interface.py' 'extensions/portbindings.py' 'plugins/bigswitch/plugin.py')
    local undocommand=''
    for to_patch in "${QUANTUM_FILES_TO_PATCH[@]}"
    do
        undocommand="$undocommand mv '$basequantum_install_path/$to_patch.orig' '$basequantum_install_path/$to_patch';"
        mv "$basequantum_install_path/$to_patch" "$basequantum_install_path/$to_patch.orig"
        cp_it "$DOWNLOAD_DIR/neutron-grizzly-stable/quantum/$to_patch" "$basequantum_install_path/$to_patch"
    done

    echo "Plugin conf file: $plugin_conf_file"
    echo "To revert this patch:"
    echo "mv $quantum_conf_orig $quantum_conf;mv $QUANTUM_SERVER_CONF_FILE_orig $QUANTUM_SERVER_CONF_FILE; mv $dhcp_conf_orig $dhcp_conf; $undocommand"

    cp_it $DOWNLOAD_DIR$TEMP_PLUGIN_CONF_PATH $quantum_conf_plugins_dir

    iniset $quantum_conf DEFAULT core_plugin $Q_PLUGIN_CLASS
    iniset $quantum_conf DEFAULT allow_overlapping_ips False
    iniset $quantum_conf DEFAULT lock_path $Q_LOCK_PATH
    iniset $plugin_conf_file RESTPROXY servers $RESTPROXY_CONTROLLER
    iniset $plugin_conf_file DATABASE sql_connection "mysql://$DATABASE_USER:$DATABASE_PASSWORD@$DATABASE_HOST:$DATABASE_PORT/$Q_DB_NAME"
    iniset $plugin_conf_file NOVA vif_type $BSN_VIF_TYPE
    iniset $dhcp_conf DEFAULT interface_driver $DHCP_INTERFACE_DRIVER
    iniset $dhcp_conf DEFAULT use_namespaces False
    sed -ie "s|^QUANTUM_PLUGIN_CONFIG=.*|QUANTUM_PLUGIN_CONFIG=\"$plugin_conf_file\"|" $QUANTUM_SERVER_CONF_FILE
    rm -rf $DOWNLOAD_DIR
}

function InstallNovaIVSSupportOnUbuntu() {
    local NOVA_FILES_TO_PATCH=( 'network/linux_net.py' 'network/model.py' 'virt/libvirt/vif.py' )
    local nova_install_path=`python -c "import nova; print nova.__path__[0]"`
    local undocommand=''
    for to_patch in "${NOVA_FILES_TO_PATCH[@]}"
    do
        undocommand="$undocommand mv '$nova_install_path/$to_patch.orig' '$nova_install_path/$to_patch';"
        mv "$nova_install_path/$to_patch" "$nova_install_path/$to_patch.orig"
        wget --quiet "$NOVA_REPO_BASE/nova/$to_patch" -O "$nova_install_path/$to_patch"
    done
    echo "To undo the nova patch, run the following:"
    echo $undocommand
}

function InstallHorizonRouterRuleSupportOnUbuntu() {
    local HORIZON_FILES_TO_PATCH=('openstack_dashboard/api/quantum.py'
                                  'openstack_dashboard/dashboards/admin/routers/routerrules/__init__.py'
                                  'openstack_dashboard/dashboards/admin/routers/routerrules/tables.py'
                                  'openstack_dashboard/dashboards/admin/routers/templates/routers/detail.html'
                                  'openstack_dashboard/dashboards/admin/routers/tabs.py'
                                  'openstack_dashboard/dashboards/admin/routers/views.py'
                                  'openstack_dashboard/dashboards/project/routers/urls.py'
                                  'openstack_dashboard/dashboards/project/routers/tabs.py'
                                  'openstack_dashboard/dashboards/project/routers/views.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/__init__.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/__init__.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/forms.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/rulemanager.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/tables.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/tabs.py'
                                  'openstack_dashboard/dashboards/project/routers/extensions/routerrules/views.py'
                                  'openstack_dashboard/dashboards/project/routers/templates/routers/detail.html'
                                  'openstack_dashboard/dashboards/project/routers/templates/routers/extensions/routerrules/_create.html'
                                  'openstack_dashboard/dashboards/project/routers/templates/routers/extensions/routerrules/create.html'
                                  'openstack_dashboard/dashboards/project/routers/templates/routers/extensions/routerrules/grid.html'
                                  'openstack_dashboard/dashboards/project/instances/tables.py')
    local horizon_install_path=`dpkg -L openstack-dashboard | grep "openstack_dashboard/dashboards/project/__init__.py" | xargs dirname | awk -F'openstack_dashboard/dashboards/' '{ print $1 }'`
    if [ ! -d "$horizon_install_path/openstack_dashboard" ]; then
        echo "Could not locate Horizon files to patch"
        return
    fi
    mkdir -p "$horizon_install_path/openstack_dashboard/dashboards/project/routers/templates/routers/routerrules/" ||:
    mkdir -p "$horizon_install_path/openstack_dashboard/dashboards/project/routers/extensions/routerrules/" ||:
    mkdir -p "$horizon_install_path/openstack_dashboard/dashboards/admin/routers/routerrules/" ||:
    local undocommand=''
    for to_patch in "${HORIZON_FILES_TO_PATCH[@]}"
    do
        if [ -f "$horizon_install_path/$to_patch" ]; then
            undocommand="$undocommand mv '$horizon_install_path/$to_patch.orig' '$horizon_install_path/$to_patch';"
            mv "$horizon_install_path/$to_patch" "$horizon_install_path/$to_patch.orig" ||:
        fi
        wget --quiet "$HORIZON_REPO_BASE/$to_patch" -O "$horizon_install_path/$to_patch"
    done
    echo "To undo the horizon patch, run the following:"
    echo $undocommand
}

# Prints "message" and exits
# die "message"
function die() {
    local exitcode=$?
    set +o xtrace
    echo $@
    exit $exitcode
}


function recreate_database_mysql {
    local db=$1
    local charset=$2
    echo "Dropping database $db is exists, and recreating it"
    mysql -u$DATABASE_USER -p$DATABASE_PASSWORD -e "DROP DATABASE IF EXISTS $db;"
    mysql -u$DATABASE_USER -p$DATABASE_PASSWORD -e "CREATE DATABASE $db CHARACTER SET $charset;"
}


echo "Patching Quantum installation with Big Switch plugin..."
# Determine what system we are running on.  This provides ``os_VENDOR``,
# ``os_RELEASE``, ``os_UPDATE``, ``os_PACKAGE``, ``os_CODENAME``
# and ``DISTRO``
GetDistro


# Error out if not on an explicitly supported distro,
if [[ ! ${DISTRO} =~ (oneiric|precise|quantal|raring|f16|f17) ]]; then
    echo "ERROR: $DISTRO distrubution is not supported"
    exit 1
else
    echo "OS Details"
    echo "Vendor: $os_VENDOR"
    echo "Release: $os_RELEASE"
    echo "Update: $os_UPDATE"
    echo "Package: $os_PACKAGE"
    echo "Distro: $DISTRO"
fi


# Validate args
if [ "${DATABASE_USER}"x = ""x ] ; then
    echo "ERROR: DATABASE_USER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${DATABASE_PASSWORD}"x = ""x ] ; then
    echo "ERROR: DATABASE_PASSWORD not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${RESTPROXY_CONTROLLER}"x = ""x ] ; then
    echo "ERROR: RESTPROXY_CONTROLLER not defined." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi
if [ "${VIF_TYPE}"x = ""x ] ; then
    echo "ERROR: interface type not defined. Specify 'ovs' or 'ivs'." 1>&2
    echo "USAGE: ${USAGE}" 2>&1
    exit 2
fi

if is_package_installed quantum-server; then
    is_package_installed quantum-server || die "Error: Package quantum-server is not installed."
    is_package_installed python-quantum || die "Error: Package python-quantum is not installed."
    is_package_installed quantum-dhcp-agent || die "Error: Package quantum-dhcp-agent is not installed."

    #recreate_database_mysql $Q_DB_NAME utf8
    InstallPluginOnUbuntu
    echo "Done. Please restart Quantum server to continue."
else
    echo "quantum-server not found. Skipping Quantum patch"
fi

if is_package_installed nova-compute; then

    InstallNovaIVSSupportOnUbuntu
    echo "Done. Please restart nova-compute to continue."
else
    echo "nova-compute not found. Skipping Nova patch"
fi

if is_package_installed openstack-dashboard; then
    InstallHorizonRouterRuleSupportOnUbuntu
    echo "Done. Restart apache2 to apply the horizon changes"
else
    echo "openstack-dashboard not found. Skipping Horizon patch"
fi

echo "Done patching services"
