import re
import constants as const

class Node(object):
    def __init__(self, node_config, env):
        self.dst_dir               = const.DST_DIR
        self.bash_script_path      = None
        self.puppet_script_path    = None
        self.selinux_script_path   = None
        self.ospurge_script_path   = None
        self.log                   = const.LOG_FILE
        self.hostname              = node_config['hostname']
        self.role                  = node_config['role'].lower()
        self.skip                  = node_config['skip']
        self.deploy_mode           = node_config['deploy_mode']
        self.os                    = node_config['os'].lower()
        self.os_version            = str(node_config['os_version']).split(".")[0]
        self.user                  = node_config['user']
        self.passwd                = node_config['passwd']
        self.uplink_interfaces     = node_config['uplink_interfaces']
        self.install_ivs           = node_config['install_ivs']
        self.install_bsnstacklib   = node_config['install_bsnstacklib']
        self.install_all           = node_config['install_all']
        self.deploy_dhcp_agent     = node_config['deploy_dhcp_agent']
        self.bridges               = node_config.get('bridges')
        self.br_bond               = node_config.get('br_bond')

        self.openstack_release     = env.openstack_release
        self.bsnstacklib_version   = env.bsnstacklib_version
        self.bcf_controllers       = env.bcf_controllers
        self.bcf_controller_ips    = env.bcf_controller_ips
        self.bcf_controller_user   = env.bcf_controller_user
        self.bcf_controller_passwd = env.bcf_controller_passwd
        self.bcf_master            = env.bcf_master
        self.physnet               = env.physnet
        self.lower_vlan            = env.lower_vlan
        self.upper_vlan            = env.upper_vlan
        self.setup_node_ip         = env.setup_node_ip
        self.setup_node_dir        = env.setup_node_dir
        self.selinux_mode          = env.selinux_mode
        self.fuel_cluster_id       = env.fuel_cluster_id
        self.deploy_horizon_patch  = env.deploy_horizon_patch
        self.horizon_patch_url     = env.horizon_patch_url
        self.horizon_patch         = env.horizon_patch
        self.horizon_patch_dir     = env.horizon_patch_dir
        self.horizon_base_dir      = env.horizon_base_dir
        self.ivs_pkg_map           = env.ivs_pkg_map
        self.ivs_pkg               = None
        self.ivs_debug_pkg         = None
        self.ivs_version           = None
        self.old_ivs_version       = node_config.get('old_ivs_version')
        if self.os in const.RPM_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['rpm']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_rpm']
        elif self.os in const.DEB_OS_SET:
            self.ivs_pkg           = self.ivs_pkg_map['deb']
            self.ivs_debug_pkg     = self.ivs_pkg_map['debug_deb']
        self.error                 = node_config.get('error')

        # check os compatability
        if (((self.os == const.CENTOS) and (self.os_version not in const.CENTOS_VERSIONS))
           or ((self.os == const.UBUNTU) and (self.os_version not in const.UBUNTU_VERSIONS))):
            self.skip = True
            self.error = (r'''%(os)s %(os_version)s is not supported''' %
                         {'os' : self.os, 'os_version' : self.os_version})

        # get ivs version
        if self.ivs_pkg:
            temp = []
            subs = self.ivs_pkg.split('-')
            for sub in subs:
                temp.extend(sub.split('_'))
            for i in range(len(temp)):
                if temp[i].lower() == 'ivs':
                    self.ivs_version = temp[i+1]
                    break

        # check ivs compatability
        if self.deploy_mode == const.T6 and self.old_ivs_version:
            ivs_version_num = self.ivs_version.split('.')
            old_ivs_version_num = self.old_ivs_version.split('.')
            if not old_ivs_version_num[0].isdigit():
                return
            if old_ivs_version_num[0] == '0':
                return
            if str(self.ivs_version) in str(self.old_ivs_version):
                return
            diff = int(ivs_version_num[0]) - int(old_ivs_version_num[0])
            if self.ivs_version < self.old_ivs_version:
                self.skip = True
                self.error = (r'''Existing ivs %(old_ivs_version)s is newer than %(ivs_version)s''' %
                              {'old_ivs_version' : self.old_ivs_version, 'ivs_version' : self.ivs_version})
            elif diff > 1:
                self.skip = True
                self.error = (r'''Existing ivs %(old_ivs_version)s is %(diff)d version behind %(ivs_version)s''' %
                             {'old_ivs_version' : self.old_ivs_version, 'diff' : diff,
                              'ivs_version' : self.ivs_version})


    def set_bash_script_path(self, bash_script_path):
        self.bash_script_path = bash_script_path


    def set_puppet_script_path(self, puppet_script_path):
        self.puppet_script_path = puppet_script_path


    def set_selinux_script_path(self, selinux_script_path):
        self.selinux_script_path = selinux_script_path


    def set_ospurge_script_path(self, ospurge_script_path):
        self.ospurge_script_path = ospurge_script_path


    def get_network_vlan_ranges(self):
        return (r'''%(physnet)s:%(lower_vlan)s:%(upper_vlan)s''' %
               {'physnet'    : self.physnet,
                'lower_vlan' : self.lower_vlan,
                'upper_vlan' : self.upper_vlan})


    def get_uplink_intfs_for_ivs(self):
        uplink_intfs = []
        for intf in self.uplink_interfaces:
            uplink_intfs.append(' -u ')
            uplink_intfs.append(intf)
        return ''.join(uplink_intfs)


    def get_ivs_internal_ports(self):
        internal_ports = []
        if self.bridges:
            for br in self.bridges:
                internal_ports.append(' --internal-port=')
                internal_ports.append(br.br_key)
        return ''.join(internal_ports)


    def get_ivs_internal_port_ips(self):
        port_ips = []
        if not self.bridges:
            return ' '.join(port_ips)
        for br in self.bridges:
            port_ips.append(r'''"%(internal_port)s,%(ip)s"''' %
                                 {'internal_port' : br.br_key,
                                  'ip'            : br.br_ip})
        return ",".join(port_ips)


    def get_all_ovs_brs(self):
        ovs_brs = []
        if self.bridges:
            for br in self.bridges:
                ovs_brs.append(r'''"%(br)s"''' % {'br' : br.br_name})
            for br in const.TO_BE_CLEANED_BR_NAME:
                ovs_brs.append(r'''"%(br)s"''' % {'br' : br})
            ovs_brs.append(r'''"%(br)s"''' % {'br' : self.br_bond})
        return ' '.join(ovs_brs)


    def get_controllers_for_neutron(self):
        return ','.join(self.bcf_controllers)


    def __str__(self):
        return (r'''
dst_dir                : %(dst_dir)s,
bash_script_path       : %(bash_script_path)s,
puppet_script_path     : %(puppet_script_path)s,
selinux_script_path    : %(selinux_script_path)s,
ospurge_script_path    : %(ospurge_script_path)s,
log                    : %(log)s,
hostname               : %(hostname)s,
role                   : %(role)s,
skip                   : %(skip)s,
deploy_mode            : %(deploy_mode)s,
os                     : %(os)s,
os_version             : %(os_version)s,
user                   : %(user)s,
passwd                 : %(passwd)s,
uplink_interfaces      : %(uplink_interfaces)s,
install_ivs            : %(install_ivs)s,
install_bsnstacklib    : %(install_bsnstacklib)s,
install_all            : %(install_all)s,
deploy_dhcp_agent      : %(deploy_dhcp_agent)s,
bridges                : %(bridges)s,
br_bond                : %(br_bond)s,
openstack_release      : %(openstack_release)s,
bsnstacklib_version    : %(bsnstacklib_version)s,
bcf_controllers        : %(bcf_controllers)s,
bcf_controller_ips     : %(bcf_controller_ips)s,
bcf_controller_user    : %(bcf_controller_user)s,
bcf_controller_passwd  : %(bcf_controller_passwd)s,
bcf_master             : %(bcf_master)s,
physnet                : %(physnet)s,
lower_vlan             : %(lower_vlan)s,
upper_vlan             : %(upper_vlan)s,
setup_node_ip          : %(setup_node_ip)s,
setup_node_dir         : %(setup_node_dir)s,
selinux_mode           : %(selinux_mode)s,
fuel_cluster_id        : %(fuel_cluster_id)s,
deploy_horizon_patch   : %(deploy_horizon_patch)s,
horizon_patch_url      : %(horizon_patch_url)s,
horizon_patch          : %(horizon_patch)s,
horizon_patch_dir      : %(horizon_patch_dir)s,
horizon_base_dir       : %(horizon_base_dir)s,
ivs_pkg                : %(ivs_pkg)s,
ivs_debug_pkg          : %(ivs_debug_pkg)s,
ivs_version            : %(ivs_version)s,
old_ivs_version        : %(old_ivs_version)s,
error                  : %(error)s,
''' %
{
'dst_dir'               : self.dst_dir,
'bash_script_path'      : self.bash_script_path,
'puppet_script_path'    : self.puppet_script_path,
'selinux_script_path'   : self.selinux_script_path,
'ospurge_script_path'   : self.ospurge_script_path,
'log'                   : self.log,
'hostname'              : self.hostname,
'role'                  : self.role,
'skip'                  : self.skip,
'deploy_mode'           : self.deploy_mode,
'os'                    : self.os,
'os_version'            : self.os_version,
'user'                  : self.user,
'passwd'                : self.passwd,
'uplink_interfaces'     : self.uplink_interfaces,
'install_ivs'           : self.install_ivs,
'install_bsnstacklib'   : self.install_bsnstacklib,
'install_all'           : self.install_all,
'deploy_dhcp_agent'     : self.deploy_dhcp_agent,
'bridges'               : str(self.bridges),
'br_bond'               : self.br_bond,
'openstack_release'     : self.openstack_release,
'bsnstacklib_version'   : self.bsnstacklib_version,
'bcf_controllers'       : self.bcf_controllers,
'bcf_controller_ips'    : self.bcf_controller_ips,
'bcf_controller_user'   : self.bcf_controller_user,
'bcf_controller_passwd' : self.bcf_controller_passwd,
'bcf_master'            : self.bcf_master,
'physnet'               : self.physnet,
'lower_vlan'            : self.lower_vlan,
'upper_vlan'            : self.upper_vlan,
'setup_node_ip'         : self.setup_node_ip,
'setup_node_dir'        : self.setup_node_dir,
'selinux_mode'          : self.selinux_mode,
'fuel_cluster_id'       : self.fuel_cluster_id,
'deploy_horizon_patch'  : self.deploy_horizon_patch,
'horizon_patch_url'     : self.horizon_patch_url,
'horizon_patch'         : self.horizon_patch,
'horizon_patch_dir'     : self.horizon_patch_dir,
'horizon_base_dir'      : self.horizon_base_dir,
'ivs_pkg'               : self.ivs_pkg,
'ivs_debug_pkg'         : self.ivs_debug_pkg,
'ivs_version'           : self.ivs_version,
'old_ivs_version'       : self.old_ivs_version,
'error'                 : self.error,
})

    def __repr__(self):
        return self.__str__()



