import re
import constants as const

class Node(object):
    def __init__(self, node_config, env):
        self.dst_dir               = const.DST_DIR
        self.bash_script_path      = None
        self.puppet_script_path    = None
        self.selinux_script_path   = None
        self.log                   = const.LOG_FILE
        self.hostname              = node_config['hostname']
        self.role                  = node_config['role'].lower()
        self.skip                  = node_config['skip']
        self.deploy_ivs            = node_config['deploy_ivs']
        self.os                    = node_config['os'].lower()
        self.os_version            = str(node_config['os_version']).split(".")[0]
        self.bsnstacklib_version   = node_config['bsnstacklib_version']
        self.user                  = node_config['user']
        self.passwd                = node_config['passwd']

        self.uplink_interfaces     = []
        for intf in node_config['uplink_interfaces']:
            self.uplink_interfaces.append(intf['interface'])

        self.bcf_controllers       = []
        for controller in env.bcf_controllers:
            self.bcf_controllers.append(controller['controller'])

        self.bcf_controller_user   = env.bcf_controller_user
        self.bcf_controller_passwd = env.bcf_controller_passwd
        self.physnet               = env.physnet
        self.lower_vlan            = env.lower_vlan
        self.upper_vlan            = env.upper_vlan
        self.setup_node_ip         = env.setup_node_ip
        self.setup_node_dir        = env.setup_node_dir
        self.selinux_mode          = env.selinux_mode
        self.fuel_cluster_id       = env.fuel_cluster_id
        self.ivs_pkg_map           = env.ivs_pkg_map
        self.ivs_pkg               = None
        self.ivs_debug_pkg         = None
        if self.os in const.RPM_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['rpm']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_rpm']
        elif self.os in const.DEB_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['deb']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_deb']


    def set_os(self, os):
        """
        reset by fuel
        """
        self.os = os.lower()
        # update ivs pkgs accordingly
        if self.os in const.RPM_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['rpm']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_rpm']
        elif self.os in const.DEB_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['deb']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_deb']


    def set_os_version(self, os_version):
        """
        reset by fuel
        """
        self.os_version = os_version.split(".")[0]


    def set_uplink_interfaces(self, uplink_interfaces):
        """
        reset by fuel
        """
        self.uplink_interfaces = uplink_interfaces


    def is_ready_to_deploy(self):
        if self.deploy_ivs and self.ivs_pkg != None:
            return True
        if not self.deploy_ivs:
            return True
        return False


    def set_bash_script_path(self, bash_script_path):
        self.bash_script_path = bash_script_path


    def set_puppet_script_path(self, puppet_script_path):
        self.puppet_script_path = puppet_script_path


    def set_selinux_script_path(self, selinux_script_path):
        self.selinux_script_path = selinux_script_path


    def get_network_vlan_ranges(self):
        return (r'''%(physnet)s:%(lower_vlan)s:%(upper_vlan)s''' %
               {'physnet'    : self.physnet,
                'lower_vlan' : self.lower_vlan,
                'upper_vlan' : self.upper_vlan})


    def get_uplink_intfs_for_ivs(self):
        uplink_interfaces = []
        for intf in self.uplink_interfaces:
            uplink_interfaces.append(' -u ')
            uplink_interfaces.append(intf)
        return ''.join(uplink_interfaces)


    def get_controllers_for_neutron(self):
        return ','.join(self.bcf_controllers)


    def __str__(self):
        return (r'''
dst_dir                : %(dst_dir)s,
bash_script_path       : %(bash_script_path)s,
puppet_script_path     : %(puppet_script_path)s,
selinux_script_path    : %(selinux_script_path)s,
log                    : %(log)s,
hostname               : %(hostname)s,
role                   : %(role)s,
skip                   : %(skip)s,
deploy_ivs             : %(deploy_ivs)s,
os                     : %(os)s,
os_version             : %(os_version)s,
bsnstacklib_version    : %(bsnstacklib_version)s,
user                   : %(user)s,
passwd                 : %(passwd)s,
uplink_interfaces      : %(uplink_interfaces)s,
bcf_controllers        : %(bcf_controllers)s,
bcf_controller_user    : %(bcf_controller_user)s,
bcf_controller_passwd  : %(bcf_controller_passwd)s,
physnet                : %(physnet)s,
lower_vlan             : %(lower_vlan)s,
upper_vlan             : %(upper_vlan)s,
setup_node_ip          : %(setup_node_ip)s,
setup_node_dir         : %(setup_node_dir)s,
selinux_mode           : %(selinux_mode)s,
fuel_cluster_id        : %(fuel_cluster_id)s,
ivs_pkg                : %(ivs_pkg)s,
ivs_debug_pkg          : %(ivs_debug_pkg)s,
''' %
{
'dst_dir'               : self.dst_dir,
'bash_script_path'      : self.bash_script_path,
'puppet_script_path'    : self.puppet_script_path,
'selinux_script_path'   : self.selinux_script_path,
'log'                   : self.log,
'hostname'              : self.hostname,
'role'                  : self.role,
'skip'                  : self.skip,
'deploy_ivs'            : self.deploy_ivs,
'os'                    : self.os,
'os_version'            : self.os_version,
'bsnstacklib_version'   : self.bsnstacklib_version,
'user'                  : self.user,
'passwd'                : self.passwd,
'uplink_interfaces'     : self.uplink_interfaces,
'bcf_controllers'       : self.bcf_controllers,
'bcf_controller_user'   : self.bcf_controller_user,
'bcf_controller_passwd' : self.bcf_controller_passwd,
'physnet'               : self.physnet,
'lower_vlan'            : self.lower_vlan,
'upper_vlan'            : self.upper_vlan,
'setup_node_ip'         : self.setup_node_ip,
'setup_node_dir'        : self.setup_node_dir,
'selinux_mode'          : self.selinux_mode,
'fuel_cluster_id'       : self.fuel_cluster_id,
'ivs_pkg'               : self.ivs_pkg,
'ivs_debug_pkg'         : self.ivs_debug_pkg,
})
