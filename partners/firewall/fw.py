"""                                                                                                 
This module acts as an interface layer to a firewall.  
It propogates information to dynamic address objects. 
"""

import paramiko
import httplib
import json
import urllib
from xml.dom.minidom import parseString
import sys,os, os.path
import socket, struct

DYNAMIC_CMD = '$FWDIR/bin/dynamic_objects'

def aton(ipstr):
    return struct.unpack('!L', socket.inet_aton(ipstr))[0]

def ntoa(ip):
    return socket.inet_ntoa(struct.pack('!L', ip))

class dynamic_object(object):
    def __init__(self, name, ranges):
        self.name = str(name)
        self.ranges = ranges
    def __repr__(self):
        return 'dynamic_object(' + self.name + ',' + repr(self.ranges) + ')'
    def range(self):
        if not len(self.ranges):
            return ''
        return ' -r ' + ' '.join([r[0] + ' ' + r[1] for r in self.ranges])

class checkpointserver(object):
    def __init__(self, server, user, password):
        self.server = str(server)
        self.user = str(user)
        self.password = str(password)
        
        self.ssh = paramiko.SSHClient()
        self.ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
        self.ssh.connect(self.server, username=self.user, password=self.password)
      
    def read_objects(self):
        stdin, stdout, stderr = self.ssh.exec_command(DYNAMIC_CMD + ' -l')
        
        objs = {}
        name = ''
        ranges = []

        for line in stdout.readlines():
            if line.startswith('object name :'):
                name = line[len('object name :'):].strip()
            if line.startswith('range '):
                range = line.partition(':')[2].strip()
                begin = range.partition('\t')[0].strip()
                end = range.partition('\t')[2].strip()
                ranges.append((begin, end))
            if line == '\n':
                if name:
                    objs[name] = dynamic_object(name, ranges)
                    ranges = []
                    name = ''
        return objs

    def get_object(self, tagid):
        objs = self.read_objects()
        if tagid not in objs:
            return None
        return objs[tagid]
                
    def add_object(self, tagid):
        objs = self.read_objects()
        if tagid in objs:
            raise Exception('Object already exists: ' + tagid)
        stdin, stdout, stderr = self.ssh.exec_command(DYNAMIC_CMD + ' -n '+ tagid)
        ret = stdout.readlines()
        return ret

    def del_object(self, tagid):
        objs = self.read_objects()
        if tagid not in objs:
            raise Exception('Object does not exist: ' + tagid)
        stdin, stdout, stderr = self.ssh.exec_command(DYNAMIC_CMD + ' -do '+ tagid)
        ret = stdout.readlines()
        #print repr(ret)
        return ret      

    def list_mapping(self):
        print repr(self.read_objects())
                                
    def clear_object(self, tagid):
        obj = self.get_object(tagid)
        if obj == None:
            return
        range = obj.range()
        if not range:
            # Object is already empty
            return
        stdin, stdout, stderr = self.ssh.exec_command(DYNAMIC_CMD + ' -o '+ tagid + range + ' -d')
        ret = stdout.readlines()
        #print repr(ret)
        return ret

    def remove_ip(self, tagid, ipstr):
        obj = self.get_object(tagid)
        if obj == None:
            return
        ip = aton(ipstr)
        ranges = []
        
        for r in obj.ranges:
            begin = aton(r[0])
            end = aton(r[1])
            
            if not (begin <= ip <= end):
                continue
            if begin < ip:
                ranges.append(ntoa(begin))
                ranges.append(ntoa(ip-1))
            if ip < end:
                ranges.append(ntoa(ip+1))
                ranges.append(ntoa(end))
            break
        else:
            # No matching range was found
            raise Exception('No such address ' + str(ipstr) + ' in range ' + str(obj.ranges)  + 'in object: ' + obj.name)

        cmd = DYNAMIC_CMD + ' -o ' + tagid + ' -r ' + r[0] + ' ' + r[1] + ' -d; '
        if len(ranges):
            cmd += DYNAMIC_CMD + ' -o ' + tagid + ' -r ' +  ' '.join(ranges) + ' -a'
            
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        ret = stdout.readlines()
        #print ret
        return ret

    def add_ip(self, tagid, ip):
        cmd = DYNAMIC_CMD + ' -o ' + tagid + ' -r ' + ip + ' ' + ip + ' -a'
        stdin, stdout, stderr = self.ssh.exec_command(cmd)
        ret = stdout.readlines()
        #print ret
        return ret

class paloaltoserver(object):

    def __init__(self, server, user, password):
        self.server = server
        self.user = user
        self.password = password

        ret = self.rest_call("/api/?type=keygen&user="+ self.user + "&password=" + self.password, {}, 'GET')
        tag = 'key'
        dom = parseString(ret[2])
        xmlTag = dom.getElementsByTagName(tag)[0].toxml()
        self.apikey = xmlTag.replace('<' +tag+'>','').replace('</'+tag+'>','')
  
    def list_mapping(self):
        ret = urllib.quote('/api/?type=op&cmd=<show><object><dynamic-address-object><all></all></dynamic-address-object></object></show>&key=' + self.apikey, "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        print ret
        return ret

    def clear_object(self, tagid):
        ret = urllib.quote('/api/?type=user-id&action=set&key=' + self.apikey + '&vsys=vsys1' + '&cmd=<uid-message><version>1.0</version><type>update</type><payload><unregister><entry identifier="'+ tagid + '"/></unregister></payload></uid-message>' , "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        return ret

    def remove_ip(self, tagid, ip):
        ret = urllib.quote('/api/?type=user-id&action=set&key=' + self.apikey + '&vsys=vsys1' + '&cmd=<uid-message><version>1.0</version><type>update</type><payload><unregister><entry identifier="'+ tagid + '" ip="'+ ip + '"/></unregister></payload></uid-message>' , "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        return ret

    def add_ip(self, tagid, ip):
        path = '/api/?type=user-id&action=set&key=' + self.apikey + '&vsys=vsys1' + '&cmd=<uid-message><version>1.0</version><type>update</type><payload><register><entry identifier="'+ tagid + '" ip="'+ ip + '"/></register></payload></uid-message>' 
        ret = urllib.quote(path, "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        return ret
        
    def rest_call(self, path, data, action):
        headers = {
            'Content-type': 'application/xml',
            'Accept': 'application/xml',
            }
        body = data
        conn = httplib.HTTPSConnection(self.server)
        conn.request(action, path, body, headers)
        response = conn.getresponse()
        ret = (response.status, response.reason, response.read())
        #print ret
        conn.close()
        return ret
