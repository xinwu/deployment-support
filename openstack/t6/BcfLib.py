import os
import sys
import yaml
import time
import string
import threading
import subprocess32 as subprocess
from threading import Lock

class BcfLib(object):
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
            target=read_output, args=(p.stdout, safe_print))
        terr = threading.Thread(
            target=read_output, args=(p.stderr, safe_print))
        for t in (tout, terr):
            t.daemon = True
            t.start()

        watcher = threading.Thread(
            target=kill_on_timeout, args=(command, event, timeout, p))
        watcher.daemon = True
        watcher.start()

        p.wait()
        event.set()
        for t in (tout, terr):
            t.join()


    @staticmethod
    def safe_print(print_lock, message):
        """
        Grab the lock and print to stdout.
        The lock is to serialize messages from
        different thread. 'stty sane' is to
        clean up any hiden space.
        """
        with print_lock:
            run_command_on_local('stty sane')
            sys.stdout.write(message)
            sys.stdout.flush()
            run_command_on_local('stty sane')


    @staticmethod
    def get_raw_value_from_yaml_dic(dic, key):
        """
        Get the raw value from a yaml dictionary.
        """
        value = dic[key]
        if type(value) in (tuple, list):
            value = value[0]
        return value


    @staticmethod
    def run_command_on_remote_with_passwd(node, cmd):
        """
        Run cmd on remote node.
        """
        local_cmd = (r'''sshpass -p %(pwd)s ssh -t -oStrictHostKeyChecking=no -o LogLevel=quiet %(user)s@%(hostname)s >> %(log)s 2>&1 "echo %(pwd)s | sudo -S %(remote_cmd)s"''' %
                   {'user'       : node.user,
                    'hostname'   : node.hostname,
                    'pwd'        : node.pwd,
                    'log'        : node.log_file,
                    'remote_cmd' : cmd
                   })
        run_command_on_local(local_cmd)


    @staticmethod
    def copy_file_to_remote_with_passwd(node, src_file, dst_dir, dst_file, mode=777):
        """
        Copy file from local node to remote node,
        create directory if remote directory doesn't exist,
        change the file mode as well.
        """
        if dst_dir[-1] == '/':
            dst_dir = dst_dir[:-1]
        mkdir_cmd = (r'''mkdir -p %(dst_dir)s''' % {'dst_dir' : dst_dir})
        run_command_on_remote_with_passwd(node, mkdir_cmd)
        scp_cmd = (r'''sshpass -p %(pwd)s scp %(src_file)s  %(user)s@%(hostname)s:%(dst_dir)s/%(dst_file)s >> %(log)s 2>&1''' %
                  {'user'       : node.user,
                   'hostname'   : node.hostname,
                   'pwd'        : node.pwd,
                   'log'        : node.log_file,
                   'src_file'   : src_file,
                   'dst_dir'    : dst_dir,
                   'dst_file'   : dst_file
                  })
        run_command_on_local(scp_cmd)
        chmod_cmd = (r'''chmod -R %(mode)d %(dst_dir)s/%(dst_file)s''' %
                    {'mode'     : mode,
                     'dst_dir'  : dst_dir,
                     'dst_file'   : dst_file
                    })
        run_command_on_remote_with_passwd(node, chmod_cmd)


    @staticmethod
    def run_command_on_remote_with_key():
        pass


    @staticmethod
    def copy_file_to_remote_with_key():
        pass

