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
        self.deploy_ivs            = node_config['deploy_ivs']
        self.os                    = node_config['os'].lower()
        self.os_version            = node_config['os_version'].split(".")[0]
        self.bsnstacklib_version   = node_config['bsnstacklib_version']
        self.user                  = node_config['user']
        self.passwd                = node_config['passwd']

        self.uplink_interfaces          = []
        for intf in node_config['uplink_interfaces']:
            self.uplink_interfaces.append(intf['interface'])

        bcf_controllers            = []
        for controller in env.bcf_controllers:
            self.bcf_controllers.append(controller['controller'])

        self.bcf_controller_user   = env.bcf_controller_user
        self.bcf_controller_passwd = env.bcf_controller_passwd
        self.network_vlan_ranges   = env.network_vlan_ranges
        self.setup_node_ip         = env.setup_node_ip
        self.setup_node_user       = env.setup_node_user
        self.setup_node_passwd     = env.setup_node_passwd
        self.setup_node_dir        = env.setup_node_dir
        self.selinux_mode          = env.selinux_mode

        self.ivs_debug_pkg         = None
        if self.os in const.RPM_OS_SET:
            self.ivs_pkg           = env.ivs_pkg_map['rpm']
            self.ivs_debug_pkg     = env.ivs_pkg_map['debug_rpm']
        elif self.os in const.DEB_OS_SET:
            self.ivs_pkg           = env.ivs_pkg_map['deb']
            self.ivs_debug_pkg     = env.ivs_pkg_map['debug_deb']


    def set_bash_script_path(self, bash_script_path):
        self.bash_script_path = bash_script_path


    def set_puppet_script_path(self, puppet_script_path):
        self.puppet_script_path = puppet_script_path


    def set_selinux_script_path(self, selinux_script_path):
        self.selinux_script_path = selinux_script_path


    # TODO: get intf and bcf controller string


    def __str__(self):
        return (r'''
dst_dir                : %(dst_dir)s,
bash_script_path       : %(bash_script_path)s,
puppet_script_path     : %(puppet_script_path)s,
selinux_script_path    : %(selinux_script_path)s,
log                    : %(log)s,
hostname               : %(hostname)s,
role                   : %(role)s,
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
network_vlan_ranges    : %(network_vlan_ranges)s,
setup_node_ip          : %(setup_node_ip)s,
setup_node_user        : %(setup_node_user)s,
setup_node_passwd      : %(setup_node_passwd)s,
setup_node_dir         : %(setup_node_dir)s,
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
'network_vlan_ranges'   : self.network_vlan_ranges,
'setup_node_ip'         : self.setup_node_ip,
'setup_node_user'       : self.setup_node_user,
'setup_node_passwd'     : self.setup_node_passwd,
'setup_node_dir'        : self.setup_node_dir,
'ivs_pkg'               : self.ivs_pkg,
'ivs_debug_pkg'         : self.ivs_debug_pkg,
})
