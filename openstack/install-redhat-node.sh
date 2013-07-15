#!/bin/bash

### Copyright 2013, Big Switch Networks
###
### Name: install-redhat-node.sh
### Desc: Sets up an all-in-one nova controller or compute node with the bigswitch controller
###

###
### Variables
###
OPENSTACK_URL="http://rdo.fedorapeople.org/openstack/openstack-grizzly/rdo-release-grizzly-3.noarch.rpm"
PACKSTACK_PKG="openstack-packstack-2013.1.1-0.5.dev538.el6.noarch"
PACKSTACK_PKG="openstack-packstack"
VERSION="Red Hat Enterprise Linux Server release 6.4 (Santiago)"
BSN_KMOD=kmod-openvswitch-1.9.0-1.el6.x86_64.rpm
BSN_OPENVSWITCH=openvswitch-1.9.0-1.x86_64.rpm
# username and pass set for quantum
QUANTUMUSER=quantumUser
QUANTUMPASS=quantumPass




## DO NOT EDIT BELOW THIS LINE
#############################

#exit on errors
set -e

#check version
CHECKVERSION=`grep "$VERSION" /etc/redhat-release | tr -d '\n'`
if [ -z "$CHECKVERSION" ]
then
    echo "This script is only for release '$VERSION'"
    exit
fi


usage () {
echo "Options"
echo "======="
echo "Required:"
echo "-c <bigswitchcontrolleraddress>: Address of Big Switch Controller"
echo "-n <novacontrolleraddress>: Address of Nova Controller"
echo "Optional:"
echo "-m <mode>: Mode for packstack to run (controller or node). Do not specifiy to skip packstack."
echo "-a <answersfile>: Path to packstack answers file when installing in node mode"
echo ""
echo "Examples"
echo "======="
echo "Sets up an all-in-one nova controller. The server's IP is 10.192.3.245 and the Big Switch Controller is 10.192.22.134"
echo "./install-redhat-node.sh -c 10.192.22.134:6633 -n 10.192.3.245 -m controller"
echo ""
echo "Sets up a compute node referencing the a nova controller at 10.192.3.245 and a Big Switch Controller at 10.192.22.134"
echo "./install-redhat-node.sh -c 10.192.22.134:6633 -n 10.192.3.245 -m node -a packstack-answers.txt"
}



#check file exists

if [ ! -e "$BSN_KMOD" ]
then
   echo "File $BSN_KMOD does not exist. Please verify the path in the BSN_KMOD variable"
   exit 1
fi

if [ ! -e "$BSN_OPENVSWITCH" ]
then
   echo "File $BSN_OPENVSWITCH does not exist. Please verify the path in the BSN_OPENVSWITCH variable"
   exit 1
fi



PACKSTACKMODE=''
PACKSTACKANSWERS=''
#parse arguments
while getopts ":m:a:c:n:r" opt; do
  case $opt in
    m)
      if [ "$OPTARG" == 'controller' ]
      then
         PACKSTACKMODE='controller'
      elif [ "$OPTARG" == 'node' ]
      then
         PACKSTACKMODE='node'
      else
         echo "Invalid option: $OPTARG" >&2
         usage
         exit 1
      fi
      ;;
    n)
      if [ ! -z "$OPTARG" ]
      then
         NOVACONTROLLER=$OPTARG
      else
         echo "Invalid Nova Controller option: $OPTARG" >&2
         usage
         exit 1
      fi
      ;;
    a)
      PACKSTACKANSWERS=$OPTARG
      if [ ! -e "$PACKSTACKANSWERS" ]
      then
         echo "packstack answers file $PACKSTACKANSWERS does not exist"
         exit 1
      fi
      ;;
    r)
	echo "You selected remove option which deletes any openstack databases and removes packages for a re-install."
	read -p "Press [Enter] key to continue or ctrl+c to abort..."
	echo "removing packages."
	PKGES=`yum list installed | grep "@openstack-grizzly" | awk -F' ' '{ print $1 }' | tr -d '\n'`
        if [ ! -z "$PKGES" ]
        then
		yum list installed | grep "@openstack-grizzly" | awk -F' ' '{ print $1 }' | xargs yum -y remove
        fi
        yum -y remove nagios-common python-swiftclient puppet
	! read -d '' sqlcleanup <<"EOF"
	DROP DATABASE IF EXISTS restproxy_quantum;
	DROP DATABASE IF EXISTS nova;
        DROP DATABASE IF EXISTS keystone;
        DROP DATABASE IF EXISTS glance;
        DROP DATABASE IF EXISTS cinder;
        DROP DATABASE IF EXISTS swift;
EOF
        echo $sqlcleanup | mysql -u root
        rm -rf ~/keystonerc_admin || :
	rm -rf /etc/swift /var/cache/swift /etc/nagios /usr/lib64/nagios /var/spool/nagios /var/lib/puppet
      ;;
    c)
      IFS=':' read -ra arr <<< "$OPTARG"
      CONTROLLERIP=${arr[0]}
      CONTROLLERPORT=${arr[1]}
      if [ -z "$CONTROLLERPORT" ]
      then
         CONTROLLERPORT=6633
      fi
      ;;
    \?)
      usage
      exit 1
      ;;
    :)
      echo "Option -$OPTARG requires an argument." >&2
      exit 1
      ;;
  esac
done

if [ -z "$CONTROLLERPORT" ]
then
    echo "-c is required to specify the Big Switch Controller address" >&2
    usage
    exit 1
fi

if [ -z "$NOVACONTROLLER" ]
then
    echo "-n is required to specify the Nova Controller address" >&2
    usage
    exit 1
fi


## define function for setting config options in files
## first argument is file to perform operation on
## second argument is lines to remove using grep
## third argument is line to add to end of file
## optional fourth argument to specify location to insert if no matches
function filelinereplace {
 echo "Attempting to substitute '$3' for '$2' in '$1'"
 if [ ! -e "$1" ]
 then
   echo "File $1 does not exist"
   exit 1
 fi
 check=`grep "$2" "$1"  | tr -d '\n'`
 if [ -z "$check" ]
 then

 if [ -z "$4" ]
   then
     echo "Pattern $2 is not present in $1"
     exit 1
   else
     sed -i "2i $2" $1
   fi
 fi
 sed -i "s/.*$2.*/$(echo $3 | sed -e 's/\\/\\\\/g' -e 's/\//\\\//g' -e 's/&/\\\&/g')/g" "$1"

}



#install items with yum
echo "Getting openstack package from $OPENSTACK_URL"
yum install -y $OPENSTACK_URL || yum update $OPENSTACK_URL

echo "Getting packstack package $PACKSTACK_PKG"
yum install -y $PACKSTACK_PKG || yum update $PACKSTACK_PKG


case $PACKSTACKMODE in
   controller)
	#yum install nagios
	#echo "" > /etc/init.d/nagios
      packstack --allinone --nagios-install=n
   ;;
   node)
      if [ -z "$PACKSTACKANSWERS" ]
      then
         echo "Must specify answerfile with -a option for node setup"
         exit 1
      fi
      packstack --answer-file="$PACKSTACKANSWERS"
   ;;
esac

rpm -ivh "$BSN_KMOD" || :

echo "Removing default openvswitch package..."
yum remove -y openvswitch.x86_64
rpm -ivh "$BSN_OPENVSWITCH" || :
/etc/init.d/openvswitch restart

## remove default networks
echo "Removing default networks"
set -vx
virsh net-destroy default 2>/dev/null || :
virsh net-undefine default 2>/dev/null || :
virsh net-destroy br-int 2>/dev/null || :
virsh net-undefine br-int 2>/dev/null || :
set +vx

## prepare XML file
! read -d '' brintxml <<"EOF"
<network>
<name>br-int</name>
<forward mode='bridge'/>
<bridge name='br-int'/>
<virtualport type='openvswitch'/>
<portgroup name='vlan-01' default='yes'>
</portgroup>
</network>
EOF

## Load into virsh
echo "Loading XML into virsh"
echo $brintxml
echo "$brintxml" > br-int.xml
set -vx
virsh net-define br-int.xml
set +vx


## Create OVS bridge with tunnel
echo "Adding tunnel to OVS bridge"
ovs-vsctl del-br br-int ||:
ovs-vsctl add-br br-int
echo tun-loopback > /etc/bsn_tunnel_interface
ovs-vsctl add-port br-int tun-bsn -- set interface tun-bsn type=gre
ovs-vsctl add-port br-int tun-loopback -- set interface tun-loopback type=internal
ovs-vsctl set-controller br-int tcp:$CONTROLLERIP:$CONTROLLERPORT





## Install quantum
yum install -y openstack-quantum

## Setup database for quantum plugin
echo "Setting up MySQL"
! read -d '' sqlcommands <<"EOF"
DROP DATABASE IF EXISTS restproxy_quantum;
CREATE DATABASE IF NOT EXISTS restproxy_quantum;
use restproxy_quantum;
EOF
echo $sqlcommands | mysql -u root
echo "GRANT ALL ON restproxy_quantum.* TO '$QUANTUMUSER'@'%' IDENTIFIED BY '$QUANTUMPASS';" | mysql -u root

echo "Setting up config files"

filelinereplace /etc/quantum/quantum.conf "core_plugin =" "core_plugin = quantum.plugins.bigswitch.plugin.QuantumRestProxyV2"
filelinereplace /etc/quantum/quantum.conf "allow_overlapping_ips =" "allow_overlapping_ips = False"
filelinereplace /etc/quantum/quantum.conf "rpc_backend =" "rpc_backend = quantum.openstack.common.rpc.impl_qpid"
filelinereplace /etc/quantum/quantum.conf "qpid_hostname =" "qpid_hostname = $NOVACONTROLLER"

filelinereplace /etc/quantum/quantum.conf "auth_host =" "auth_host = $NOVACONTROLLER"
filelinereplace /etc/quantum/quantum.conf "auth_strategy =" "auth_strategy = keystone"
filelinereplace /etc/quantum/quantum.conf "admin_user =" "admin_user = $QUANTUMUSER"
filelinereplace /etc/quantum/quantum.conf "admin_password =" "admin_password = $QUANTUMPASS"
filelinereplace /etc/quantum/quantum.conf "admin_tenant_name =" '#admin_tenant_name ='


filelinereplace /etc/quantum/dhcp_agent.ini "use_namespaces =" "use_namespaces = False"

filelinereplace /etc/nova/nova.conf "libvirt_type=" "libvirt_type=kvm" "2"
filelinereplace /etc/nova/nova.conf "libvirt_ovs_bridge=" "libvirt_ovs_bridge=br-int" "2"
filelinereplace /etc/nova/nova.conf "libvirt_vif_type=" "libvirt_vif_type=ethernet" "2"
filelinereplace /etc/nova/nova.conf "libvirt_vif_driver=" "libvirt_vif_driver=nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver" "2"
filelinereplace /etc/nova/nova.conf "libvirt_use_virtio_for_bridges=" "libvirt_use_virtio_for_bridges=True" "2"
filelinereplace /etc/nova/nova.conf "network_api_class=" "network_api_class=nova.network.quantumv2.api.API" "2"
filelinereplace /etc/nova/nova.conf "quantum_url=" "quantum_url=http://$NOVACONTROLLER:9696" "2"
filelinereplace /etc/nova/nova.conf "quantum_auth_strategy=" "quantum_auth_strategy=keystone" "2"
filelinereplace /etc/nova/nova.conf "quantum_admin_tenant_name=" "quantum_admin_tenant_name=services" "2"
filelinereplace /etc/nova/nova.conf "quantum_admin_username=" "quantum_admin_username=$QUANTUMUSER" "2"
filelinereplace /etc/nova/nova.conf "quantum_admin_password=" "quantum_admin_password=$QUANTUMPASS" "2"
filelinereplace /etc/nova/nova.conf "quantum_admin_auth_url=" "quantum_admin_auth_url=http://$NOVACONTROLLER:35357/v2.0" "2"
filelinereplace /etc/nova/nova.conf "libvirt_vif_driver=" "libvirt_vif_driver=nova.virt.libvirt.vif.LibvirtHybridOVSBridgeDriver" "2"


echo "Downloading quantum plugin"
rm stable.zip || :
rm -rf neutron-grizzly-stable || :
wget "https://github.com/bigswitch/neutron/archive/grizzly/stable.zip" -O stable.zip
unzip stable.zip
cp -r neutron-grizzly-stable/quantum/plugins/bigswitch /usr/lib/python2.6/site-packages/quantum/plugins/ || :
mkdir /etc/quantum/plugins/bigswitch || :
cp neutron-grizzly-stable/etc/quantum/plugins/bigswitch/restproxy.ini /etc/quantum/plugins/bigswitch/ || :

echo "Setting up plugin"
filelinereplace /etc/quantum/plugins/bigswitch/restproxy.ini "sql_connection =" "sql_connection = mysql://$QUANTUMUSER:$QUANTUMPASS@$NOVACONTROLLER:3306/restproxy_quantum"
filelinereplace /etc/quantum/plugins/bigswitch/restproxy.ini "servers=" "servers=$CONTROLLERIP:80"
filelinereplace /etc/quantum/plugins/bigswitch/restproxy.ini "server_auth=" "server_auth=$QUANTUMUSER:$QUANTUMPASS"
filelinereplace /etc/quantum/plugins/bigswitch/restproxy.ini "server_ssl=" "server_ssl=False"

filelinereplace /etc/init.d/quantum-server "daemon --user quantum" 'daemon --user quantum --pidfile $pidfile "$exec --config-file $config --config-file /etc/quantum/plugins/bigswitch/restproxy.ini --log-file $logfile &>/dev/null & echo \$! > $pidfile"'
chmod +x /etc/init.d/quantum-server

echo "Setting up root wrapper"
sed -e 's|^[^#]\W*root_helper\W|#&|' -e 's|root_helper\W=\Wsudo|&\nroot_helper =sudo /usr/bin/quantum-rootwrap /etc/quantum/rootwrap.conf|' -i /etc/quantum/quantum.conf

echo "Disable legacy nova network service"
nova-manage service disable --host $NOVACONTROLLER --service nova-network || :

echo "Starting services"
/etc/init.d/quantum-server start
/etc/init.d/quantum-dhcp-agent start


echo "Keystone setup"
source ~/keystonerc_admin
export OS_AUTH_URL=$OS_AUTH_URL
#export OS_TENANT_NAME=$OS_TENANT_NAME
#export OS_PASSWORD=$OS_PASSWORD
#export OS_USERNAME=$OS_USERNAME
export OS_SERVICE_TOKEN=`grep "admin_token =" /etc/keystone/keystone.conf | grep -v '#' | awk -F' = ' '{ print $2 }'`
export OS_SERVICE_ENDPOINT=$OS_AUTH_URL
set -vx
keystone service-create --name quantum --type network --description 'OpenStack Networking Service'
SERVICEID=`keystone service-list | grep "OpenStack Networking Service" | tail -n 1 | awk -F' ' '{ print $2 }'`
keystone endpoint-create --region RegionOne --service-id $SERVICEID --publicurl "http://$NOVACONTROLLER:9696/" --adminurl "http://$NOVACONTROLLER:9696/" --internalurl "http://$NOVACONTROLLER:9696/"
TENANTID=`keystone tenant-list | grep services | tail -n 1 | awk -F' ' '{ print $2 }'`
USERPRESENT=`keystone user-list | grep "$QUANTUMUSER" | tr -d '\n'`
if [ -z "$USERPRESENT" ]
then
keystone user-create --name=$QUANTUMUSER --pass=$QUANTUMPASS --email=quantum@example.com --tenant-id $TENANTID
fi
keystone role-list | grep admin
keystone user-list | grep quantumUser
set +vx
keystone user-password-update --pass "$OS_PASSWORD" $OS_USERNAME

echo "opening firewall for openstack requests"

iptables -A INPUT -p tcp -m multiport --dports 5672 -m comment --comment "001 qpid incoming" -j ACCEPT
iptables -A INPUT -p tcp -m multiport --dports 9696 -m comment --comment "quantum incoming" -j ACCEPT
cp /etc/sysconfig/iptables /etc/sysconfig/iptables.backup_$(date +"%F-%H:%M")
iptables-save > /etc/sysconfig/iptables

# restart services
echo "restarting services..."
ls /etc/init.d/openstack-* | while read N; do sudo ${N} restart ||:; done


#Print out some instructions
! read -d '' instructions <<"EOF"

===========================================================================
+          		INSTALLATION COMPLETE                             +
===========================================================================


Add physical interfaces to the bridge with the following example command:
ovs-vsctl add-port br-int eth1;  ifconfig eth1 0.0.0.0 up

Assign an IP address to the tunnel adapter with the following example command:
ifconfig tun-loopback 10.192.1.10/24

Setup a route with the following example command:
route add -net 10.192.2.0 netmask 255.255.255.0 gw 10.192.1.1 dev tun-loopback
EOF

echo "$instructions"
