#!/usr/bin/env bash
#
# WARNING: This script points to the master branch so the code it references may change
#
# This script patches the OpenStack Neutron Ubuntu packages installation
# with the Big Switch Network's Neutron Plugin.
#
# Supported Ubuntu version: 12.10
# Big Switch Plugin: https://github.com/bigswitch/neutron/tree/master
#
# @author: Sumit Naiksatam, Big Switch Networks, Inc.
# @date: January 27 2013
#
# See usage below:
USAGE="$0 db_user db_password bsn-conotroller-ip:port[,bsn-controller-ip:port]* [interface-type ('ovs' or 'ivs')] [db_ip] [db_port]"

DATE=$(date +"%Y%m%d%H%M")
exec >  >(tee -a patchlog-$DATE.log | grep -v '^+') 
exec 2> >(tee -a patchlog-$DATE.log | grep -v '^+' >&2) 
trap "sleep 1" exit
set -x
set -e

umask 022

DATABASE_USER=$1
DATABASE_PASSWORD=$2
RESTPROXY_CONTROLLER=$3
VIF_TYPE=$4
TEMP_DIR='/tmp/bsn'
Q_DB_NAME='neutron'
PLUGIN_URL='https://github.com/bigswitch/quantum/archive/havana/stable.tar.gz'
PLUGIN_TAR='bsn.tar.gz'
HORIZON_URL='https://github.com/bigswitch/horizon/archive/stable/havana_routerrules.tar.gz'
TEMP_PLUGIN_PATH='/neutron-havana-stable/neutron/plugins/bigswitch'
TEMP_PLUGIN_CONF_PATH='/neutron-havana-stable/etc/neutron/plugins/bigswitch'
Q_PLUGIN_CLASS="neutron.plugins.bigswitch.plugin.NeutronRestProxyV2"
QUANTUM_CONF_FILENAME="neutron.conf"
DHCP_AGENT_CONF_FILENAME="dhcp_agent.ini"
DATABASE_HOST=${5:-'127.0.0.1'}
DATABASE_PORT=${6:-'3306'}
PLUGIN_NAME="bigswitch"
Q_LOCK_PATH='/run/lock/neutron'
DHCP_LEASE_TIME=43200

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
            QUANTUM_SERVER_CONF_FILE="/etc/default/neutron-server"
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
        die "Error: Package neutron-server is installed but could not find /etc/default/neutron-server"
    fi
    if [ "$VIF_TYPE" = "ovs" ]; then
        DHCP_INTERFACE_DRIVER="neutron.agent.linux.interface.OVSInterfaceDriver"
        BSN_VIF_TYPE="ovs"
    elif [ "$VIF_TYPE" = "ivs" ]; then
        DHCP_INTERFACE_DRIVER="neutron.agent.linux.interface.IVSInterfaceDriver"
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
    local plugin_install_path=`python -c "import neutron.plugins; print neutron.plugins.__path__[0]"`
    echo "Installing plugin in: $plugin_install_path/$PLUGIN_NAME"
    cp_it $DOWNLOAD_DIR$TEMP_PLUGIN_PATH $plugin_install_path
    local quantum_conf=`dpkg -L neutron-common | grep "$QUANTUM_CONF_FILENAME"`
    local quantum_conf_dir=`dirname $quantum_conf`
    local quantum_conf_orig="$quantum_conf.orig"
    local dhcp_conf=`dpkg -L neutron-dhcp-agent | grep "$DHCP_AGENT_CONF_FILENAME"`
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

    echo "Patching neutron files for IVS support"
    local basequantum_install_path=`python -c "import neutron; print neutron.__path__[0]"`
    local QUANTUM_FILES_TO_PATCH=('agent/linux/interface.py' 'extensions/portbindings.py' 'plugins/bigswitch/plugin.py')
    local undocommand=''
    for to_patch in "${QUANTUM_FILES_TO_PATCH[@]}"
    do
        undocommand="$undocommand mv '$basequantum_install_path/$to_patch.orig' '$basequantum_install_path/$to_patch';"
        mv "$basequantum_install_path/$to_patch" "$basequantum_install_path/$to_patch.orig"
        cp_it "$DOWNLOAD_DIR/neutron-havana-stable/neutron/$to_patch" "$basequantum_install_path/$to_patch"
    done

    echo "Plugin conf file: $plugin_conf_file"
    echo "To revert this patch:"
    echo "mv $quantum_conf_orig $quantum_conf;mv $QUANTUM_SERVER_CONF_FILE_orig $QUANTUM_SERVER_CONF_FILE; mv $dhcp_conf_orig $dhcp_conf; $undocommand"

    cp_it $DOWNLOAD_DIR$TEMP_PLUGIN_CONF_PATH $quantum_conf_plugins_dir

    iniset $quantum_conf DEFAULT core_plugin $Q_PLUGIN_CLASS
    iniset $quantum_conf DEFAULT allow_overlapping_ips False
    iniset $quantum_conf DEFAULT lock_path $Q_LOCK_PATH
    iniset $quantum_conf DEFAULT force_gateway_on_subnet True
    iniset $quantum_conf DEFAULT dhcp_lease_duration $DHCP_LEASE_TIME
    iniset $plugin_conf_file restproxy servers $RESTPROXY_CONTROLLER
    iniset $plugin_conf_file database sql_connection "mysql://$DATABASE_USER:$DATABASE_PASSWORD@$DATABASE_HOST:$DATABASE_PORT/$Q_DB_NAME"
    iniset $plugin_conf_file nova vif_type $BSN_VIF_TYPE
    iniset $dhcp_conf DEFAULT interface_driver $DHCP_INTERFACE_DRIVER
    iniset $dhcp_conf DEFAULT use_namespaces False
    iniset $dhcp_conf DEFAULT dhcp_lease_time $DHCP_LEASE_TIME
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
    local DOWNLOAD_DIR="$TEMP_DIR"
    local DOWNLOAD_FILE="$DOWNLOAD_DIR/$PLUGIN_TAR"
    local SETTINGS_PATH=`dpkg-query -L openstack-dashboard | grep local_settings.py | grep /etc/`

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
    mkdir -p /usr/lib/bigswitch/ ||:
    cp -R $DOWNLOAD_DIR/horizon-stable-havana_routerrules/* /usr/lib/bigswitch
    cp "$SETTINGS_PATH" "/usr/lib/bigswitch/openstack_dashboard/local/"
    rm -rf /usr/lib/bigswitch/static ||:

    ln -s `dpkg -L openstack-dashboard | grep local_settings.py | grep -v /etc | head -n 1| xargs dirname`/../static /usr/lib/bigswitch/static ||:
    sed -i "s/LOGIN_URL='\/horizon\/auth\/login\/'/LOGIN_URL='\/bigdashboard\/auth\/login\/'/g"  /usr/lib/bigswitch/openstack_dashboard/local/local_settings.py
    sed -i "s/LOGIN_REDIRECT_URL='\/horizon'/LOGIN_REDIRECT_URL='\/bigdashboard'/g"  /usr/lib/bigswitch/openstack_dashboard/local/local_settings.py
    APACHECONF=$(cat <<EOF
        RedirectMatch ^/$ /bigdashboard
        Redirect /horizon /bigdashboard
        Redirect /dashboard /bigdashboard

        WSGIDaemonProcess bigdashboard
        WSGIProcessGroup bigdashboard

        WSGIScriptAlias /bigdashboard /usr/lib/bigswitch/openstack_dashboard/wsgi/django.wsgi

        <Directory /usr/lib/bigswitch/openstack_dashboard/wsgi>
          <IfModule mod_deflate.c>
            SetOutputFilter DEFLATE
            <IfModule mod_headers.c>
              # Make sure proxies don’t deliver the wrong content
              Header append Vary User-Agent env=!dont-vary
            </IfModule>
          </IfModule>

          Require all granted
        </Directory>

        <Location /bigdashboard/i18n>
          <IfModule mod_expires.c>
            ExpiresActive On
            ExpiresDefault "access 6 month"
          </IfModule>
        </Location>
EOF
)
    if [ -d /etc/apache2/conf.d ]
    then
      echo "$APACHECONF" > /etc/apache2/conf.d/bigswitch-dashboard.conf
      MULTI=`echo "Order allow,deny\nAllow from all" | tr '\n' "\\n"`
      sed -i "s/Require all granted/${MULTI}/g" /etc/apache2/conf.d/bigswitch-dashboard.conf
      UNDO_HORIZON="sudo rm /etc/apache2/conf.d/bigswitch-dashboard.conf; sudo service apache2 reload"
    else
      echo "$APACHECONF" > /etc/apache2/conf-available/bigswitch-dashboard.conf
      a2enconf bigswitch-dashboard
      UNDO_HORIZON="sudo a2disconf bigswitch-dashboard; sudo service apache2 reload"
    fi
    rm -rf $DOWNLOAD_DIR
    service apache2 reload ||:
    echo "To undo the horizon patch, run the following:"
    echo $UNDO_HORIZON
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


echo "Patching Neutron installation with Big Switch plugin..."
# Determine what system we are running on.  This provides ``os_VENDOR``,
# ``os_RELEASE``, ``os_UPDATE``, ``os_PACKAGE``, ``os_CODENAME``
# and ``DISTRO``
GetDistro


# Error out if not on an explicitly supported distro,
if [[ ! ${DISTRO} =~ (saucy|oneiric|precise|quantal|raring|f16|f17) ]]; then
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

if is_package_installed neutron-server; then
    is_package_installed neutron-server || die "Error: Package neutron-server is not installed."
    is_package_installed python-neutron || die "Error: Package python-neutron is not installed."
    is_package_installed neutron-dhcp-agent || die "Error: Package neutron-dhcp-agent is not installed."

    #recreate_database_mysql $Q_DB_NAME utf8
    InstallPluginOnUbuntu
    echo "Done. Please restart Neutron server to continue."
else
    echo "neutron-server not found. Skipping Neutron patch"
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
