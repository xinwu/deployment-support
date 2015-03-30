import os
import sys
import time
import socket
import string
import threading
import constants as const
import subprocess32 as subprocess
from node import Node
from threading import Lock


class Helper(object):

    # lock to serialize stdout of different threads
    __print_lock = Lock()

    @staticmethod
    def __read_output__(pipe, func):
        """
        Read from a pipe, remove unknown spaces.
        """
        for lines in iter(pipe.readline, ''):
            for line in lines.splitlines(True):
                l = ''.join(filter(lambda x: 32 <= ord(x) <= 126, line.strip()))
                if len(l):
                    func(l + '\n')
        pipe.close()


    @staticmethod
    def __kill_on_timeout__(command, event, timeout, proc):
        """
        Kill a thread when timeout expires.
        """
        if not event.wait(timeout):
            Helper.safe_print('Timeout when running %s' % command)
            proc.kill()


    @staticmethod
    def get_setup_node_ip():
        """
        Get the setup node's eth0 ip
        """
        s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        s.connect(('bigswitch.com', 0))
        return s.getsockname()[0]


    @staticmethod
    def run_command_on_local(command, timeout=1800):
        """
        Use subprocess to run a shell command on local node.
        A watcher threading stops the subprocess when it expires.
        stdout and stderr are captured.
        """
        event = threading.Event()
        p = subprocess.Popen(
            command, shell=True, stdout=subprocess.PIPE,
            stderr=subprocess.PIPE, close_fds=True, bufsize=1)

        tout = threading.Thread(
            target=Helper.__read_output__, args=(p.stdout, Helper.safe_print))
        terr = threading.Thread(
            target=Helper.__read_output__, args=(p.stderr, Helper.safe_print))
        for t in (tout, terr):
            t.daemon = True
            t.start()

        watcher = threading.Thread(
            target=Helper.__kill_on_timeout__, args=(command, event, timeout, p))
        watcher.daemon = True
        watcher.start()

        p.wait()
        event.set()
        for t in (tout, terr):
            t.join()


    @staticmethod
    def safe_print(message):
        """
        Grab the lock and print to stdout.
        The lock is to serialize messages from
        different thread. 'stty sane' is to
        clean up any hiden space.
        """
        with Helper.__print_lock:
            Helper.run_command_on_local('stty sane')
            sys.stdout.write(message)
            sys.stdout.flush()
            Helper.run_command_on_local('stty sane')


    @staticmethod
    def run_command_on_remote_with_passwd(node, cmd):
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s >> %(log)s 2>&1 "echo %(pwd)s | sudo -S %(remote_cmd)s"''' %
                   {'user'       : node.user,
                    'hostname'   : node.hostname,
                    'pwd'        : node.passwd,
                    'log'        : node.log,
                    'remote_cmd' : cmd
                   })
        Helper.run_command_on_local(local_cmd)


    @staticmethod
    def copy_file_to_remote_with_passwd(node, src_file, dst_dir, dst_file, mode=777):
        """
        Copy file from local node to remote node,
        create directory if remote directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_remote_with_passwd(node, mkdir_cmd)
        scp_cmd = (r'''sshpass -p %(pwd)s scp %(src_file)s  %(user)s@%(hostname)s:%(dst_dir)s/%(dst_file)s >> %(log)s 2>&1''' %
                  {'user'       : node.user,
                   'hostname'   : node.hostname,
                   'pwd'        : node.passwd,
                   'log'        : node.log,
                   'src_file'   : src_file,
                   'dst_dir'    : dst_dir,
                   'dst_file'   : dst_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(dst_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'dst_file' : dst_file
                    })
        Helper.run_command_on_remote_with_passwd(node, chmod_cmd)


    @staticmethod
    def run_command_on_remote_with_key():
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(hostname)s >> %(log)s 2>&1 "%(remote_cmd)s"''' %
                   {'hostname'   : node.hostname,
                    'log'        : node.log,
                    'remote_cmd' : cmd
                   })
        Helper.run_command_on_local(local_cmd)


    @staticmethod
    def copy_file_to_remote_with_key():
        """
        Copy file from local node to remote node,
        create directory if remote directory doesn't exist,
        change the file mode as well.
        """
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        Helper.run_command_on_remote_with_key(node, mkdir_cmd)
        scp_cmd = (r'''scp %(src_file)s %(hostname)s:%(dst_dir)s/%(dst_file)s >> %(log)s 2>&1''' %
                  {'hostname'   : node.hostname,
                   'log'        : node.log,
                   'src_file'   : src_file,
                   'dst_dir'    : dst_dir,
                   'dst_file'   : dst_file
                  })
        Helper.run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(dst_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'dst_file' : dst_file
                    })
        Helper.run_command_on_remote_with_key(node, chmod_cmd)


    @staticmethod
    def generate_scripts_for_centos(node):
        deploy_mode = const.WITH_IVS
        if not node.deploy_ivs:
            deploy_mode = const.NO_IVS

        # generate bash script
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(bash_template_dir)s/%(bash_template)s_%(os_version)s.sh''' %
                  {'setup_node_dir'    : node.setup_node_dir,
                   'deploy_mode'       : deploy_mode,
                   'bash_template_dir' : const.BASH_TEMPLATE_DIR,
                   'bash_template'     : const.CENTOS,
                   'os_version'        : node.os_version}), "r") as bash_template_file:
            bash_template = bash_template_file.read()
            bash = (bash_template %
                   {'bsnstacklib_version' : node.bsnstacklib_version,
                    'dst_dir'             : node.dst_dir,
                    'hostname'            : node.hostname,
                    'ivs_pkg'             : node.ivs_pkg,
                    'ivs_debug_pkg'       : node.ivs_debug_pkg})
        bash_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.sh''' %
                           {'setup_node_dir'       : node.setup_node_dir,
                            'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                            'hostname'             : node.hostname})
        with open(bash_script_path, "w") as bash_file:
            bash_file.write(bash)
        node.set_bash_script_path(bash_script_path)

        # generate puppet script
        ivs_daemon_args = (const.IVS_DAEMON_ARGS %
                          {'inband_vlan' : const.INBAND_VLAN,
                           'uplink_interfaces' : node.get_uplink_intfs_for_ivs()})
        with open((r'''%(setup_node_dir)s/%(deploy_mode)s/%(puppet_template_dir)s/%(puppet_template)s_%(role)s.pp''' %
                  {'setup_node_dir'      : node.setup_node_dir,
                   'deploy_mode'         : deploy_mode,
                   'puppet_template_dir' : const.PUPPET_TEMPLATE_DIR,
                   'puppet_template'     : const.CENTOS,
                   'role'                : node.role}), "r") as puppet_template_file:
            puppet_template = puppet_template_file.read()
            puppet = (puppet_template %
                     {'ivs_daemon_args'       : ivs_daemon_args,
                      'network_vlan_ranges'   : node.network_vlan_ranges,
                      'bcf_controllers'       : node.get_controllers_for_neutron(),
                      'bcf_controller_user'   : node.bcf_controller_user,
                      'bcf_controller_passwd' : node.bcf_controller_passwd,
                      'selinux_mode'          : node.selinux_mode})
        puppet_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.pp''' %
                             {'setup_node_dir'       : node.setup_node_dir,
                              'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                              'hostname'             : node.hostname})
        with open(puppet_script_path, "w") as puppet_file:
            puppet_file.write(puppet)
        node.set_puppet_script_path(puppet_script_path)

        # generate selinux script
        selinux_script_path = (r'''%(setup_node_dir)s/%(generated_script_dir)s/%(hostname)s.te''' %
                              {'setup_node_dir'       : node.setup_node_dir,
                               'generated_script_dir' : const.GENERATED_SCRIPT_DIR,
                               'hostname'             : node.hostname})
        subprocess.call(r'''cp %(setup_node_dir)s/%(deploy_mode)s/%(selinux_template_dir)s/%(selinux_template)s.te %(selinux_script_path)s''' %
                       {'setup_node_dir'       : node.setup_node_dir,
                        'deploy_mode'          : deploy_mode,
                        'selinux_template_dir' : const.SELINUX_TEMPLATE_DIR,
                        'selinux_template'     : const.CENTOS,
                        'selinux_script_path'  : selinux_script_path}, shell=True)
        node.set_selinux_script_path(selinux_script_path)


    @staticmethod
    def load_bcf_config(config, env):
        """
        Parse yaml file and return a dictionary
        """
        node_dic = {}
        for node_config in config['nodes']:
            if 'deploy_ivs' not in node_config:
                node_config['deploy_ivs'] = config['default_deploy_ivs']
            if 'os' not in node_config:
                node_config['os'] = config['default_os']
            if 'os_version' not in node_config:
                node_config['os_version'] = config['default_os_version']
            if 'bsnstacklib_version' not in node_config:
                node_config['bsnstacklib_version'] = config['default_bsnstacklib_version']
            if 'role' not in node_config:
                node_config['role'] = config['default_role']

            user = None
            if 'default_user' in config:
                user = config['default_user']
            if 'user' in node_config:
                user = node_config['user']
            node_config['user'] = user

            passwd = None
            if 'default_passwd' in config:
                passwd = config['default_passwd']
            if 'passwd' in node_config:
                passwd = node_config['passwd']
            node_config['passwd'] = passwd

            intfs = None
            if 'default_uplink_interfaces' in config:
                intfs = config['default_uplink_interfaces']
            if 'uplink_interfaces' in node_config:
                intfs = node_config['uplink_interfaces']
            node_config['uplink_interfaces'] = intfs

            node = Node(node_config, env)
            node_dic[node.hostname] = node
        return node_dic


    @staticmethod
    def common_setup_node_preparation(env):
        # clean up from previous installation
        setup_node_dir = os.getcwd()
        subprocess.call("rm -rf ~/.ssh/known_hosts", shell=True)
        subprocess.call("rm -rf %(log)s" %
                       {'log' : const.LOG_FILE}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.rpm" %
                       {'setup_node_dir' : setup_node_dir}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/*ivs*.deb" %
                       {'setup_node_dir' : setup_node_dir}, shell=True)
        subprocess.call("mkdir -p %(setup_node_dir)s/%(generated_script)s" %
                       {'setup_node_dir'   : setup_node_dir,
                        'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)
        subprocess.call("rm -rf %(setup_node_dir)s/%(generated_script)s/*" %
                       {'setup_node_dir'   : setup_node_dir,
                        'generated_script' : const.GENERATED_SCRIPT_DIR}, shell=True)

        # wget ivs packages
        code_web = 1
        code_local = 1
        for pkg_type, url in env.ivs_url_map.iteritems():
            if 'http://' in url or 'https://' in url:
                code_web = subprocess.call("wget --no-check-certificate %(url)s -P %(setup_node_dir)s" %
                                          {'url' : url, 'setup_node_dir' : setup_node_dir},
                                           shell=True)
        for pkg_type, url in env.ivs_url_map.iteritems():
            if os.path.isfile(url):
                code_local = subprocess.call("cp %(url)s %(setup_node_dir)s" %
                                            {'url' : url, 'setup_node_dir' : setup_node_dir},
                                             shell=True)
        if env.deploy_ivs and code_web != 0 and code_local != 0:
            Helper.safe_print("Required packages are not correctly downloaded.\n")
            exit(1)


    @staticmethod
    def copy_pkg_scripts_to_remote_with_passwd(node):
        # copy ivs to node
        if node.deploy_ivs:
            Helper.safe_print("Copy %(ivs_pkg)s to %(hostname)s\n" %
                              {'ivs_pkg'  : node.ivs_pkg,
                               'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
                (r'''%(src_dir)s/%(ivs_pkg)s''' %
                {'src_dir' : node.setup_node_dir,
                 'ivs_pkg' : node.ivs_pkg}),
                node.dst_dir,
                node.ivs_pkg)
            if node.ivs_debug_pkg != None:
                Helper.safe_print("Copy %(ivs_debug_pkg)s to %(hostname)s\n" %
                                 {'ivs_debug_pkg'  : node.ivs_debug_pkg,
                                  'hostname'       : node.hostname})
                Helper.copy_file_to_remote_with_passwd(node,
                    (r'''%(src_dir)s/%(ivs_debug_pkg)s''' %
                    {'src_dir'       : node.setup_node_dir,
                     'ivs_debug_pkg' : node.ivs_debug_pkg}),
                    node.dst_dir,
                    node.ivs_debug_pkg)

        # copy bash script to node
        Helper.safe_print("Copy bash script to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote_with_passwd(node,
           node.bash_script_path,
           node.dst_dir,
           "%(hostname)s.sh" % {'hostname' : node.hostname})

        # copy puppet script to node
        Helper.safe_print("Copy puppet script to %(hostname)s\n" %
                         {'hostname' : node.hostname})
        Helper.copy_file_to_remote_with_passwd(node,
           node.puppet_script_path,
           node.dst_dir,
           "%(hostname)s.pp" % {'hostname' : node.hostname})

        # copy selinux script to node
        if node.os in const.RPM_OS_SET:
            Helper.safe_print("Copy bsn selinux policy to %(hostname)s\n" %
                             {'hostname' : node.hostname})
            Helper.copy_file_to_remote_with_passwd(node,
               node.selinux_script_path,
               node.dst_dir,
               "%(hostname)s.te" % {'hostname' : node.hostname})



