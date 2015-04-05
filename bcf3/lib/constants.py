
# max number of threads, each thread sets up one node
MAX_WORKERS = 20

# root access to all the nodes is required
DEFAULT_USER = 'root'

# key words to specify node role in yaml config
ROLE_NEUTRON_SERVER = 'controller'
ROLE_COMPUTE        = 'compute'

# deployment with/out ivs
WITH_IVS = 'with_ivs'
NO_IVS   = 'no_ivs'

# constant file, directory names for each node
PRE_REQUEST_BASH     = 'pre_request.sh'
DST_DIR              = '/tmp'
GENERATED_SCRIPT_DIR = 'generated_script'
BASH_TEMPLATE_DIR    = 'bash_template'
PUPPET_TEMPLATE_DIR  = 'puppet_template'
SELINUX_TEMPLATE_DIR = 'selinux_template'
LOG_FILE             = "/var/log/bcf_setup.log"

# constants for ivs config
INBAND_VLAN     = 4092
IVS_DAEMON_ARGS = (r'''DAEMON_ARGS=\"--syslog --inband-vlan %(inband_vlan)d%(uplink_interfaces)s --pipeline=bvs-1.0\"''')

# constants of supported OSes and versions
CENTOS          = 'centos'
CENTOS_VERSIONS = [7]
UBUNTU          = 'ubuntu'
UBUNTU_VERSIONS = [14]

# OSes that uses rpm or deb packages
RPM_OS_SET = [CENTOS]
DEB_OS_SET = [UBUNTU]

# regular expressions
EXISTING_NETWORK_VLAN_RANGE_EXPRESSION  = '^\s*network_vlan_ranges\s*=\s*(\S*)\s*:\s*(\S*)\s*:\s*(\S*)\s*$'
NETWORK_VLAN_RANGE_EXPRESSION   = '^\s*(\S*)\s*:\s*(\S*)\s*:\s*(\S*)\s*$'
VLAN_RANGE_CONFIG_PATH          = '/etc/neutron/plugins/ml2/ml2_conf.ini'
SELINUX_MODE_EXPRESSION         = '^\s*SELINUX\s*=\s*(\S*)\s*$'
SELINUX_CONFIG_PATH             = '/etc/selinux/config'


# openrc
FUEL_OPENRC            = '/root/openrc'
PACKSTACK_OPENRC       = '/root/keystonerc_admin'


# fuel constants
NONE_IP                = 'none'
BR_KEY_PRIVATE         = 'private'
BR_KEY_MGMT            = 'management'
BR_KEY_EXCEPTION       = ['fw-admin', BR_KEY_PRIVATE, BR_KEY_MGMT]
OS_MGMT_TENANT         = 'os-mgmt'
HASH_HEADER            = 'BCF-SETUP'
BCF_CONTROLLER_PORT    = 8443
ANY                    = 'any'
FUEL_GUI_TO_BR_KEY_MAP = {'management' : BR_KEY_MGMT,
    'storage' : 'storage',
    'public'  : 'ex',
    'private' : BR_KEY_PRIVATE}


