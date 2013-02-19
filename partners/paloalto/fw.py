#!/usr/sbin/env python    

# Copyright 2013, Big Switch Networks, Inc.
#
#    Licensed under the Apache License, Version 2.0 (the "License"); you may
#    not use this file except in compliance with the License. You may obtain
#    a copy of the License at
#
#         http://www.apache.org/licenses/LICENSE-2.0
#
#    Unless required by applicable law or agreed to in writing, software
#    distributed under the License is distributed on an "AS IS" BASIS, WITHOUT
#    WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied. See the
#    License for the specific language governing permissions and limitations
#    under the License.
#
# @author: Mike Cohen, Big Switch Networks, Inc.
#

"""                                                                                                 
This module acts as an interface layer to a firewall.  
It propogates information to dynamic address objects. 
"""

import httplib
import json
import urllib
from xml.dom.minidom import parseString
import sys

class paserver(object):

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

    def clear_mapping(self, tagid):
        ret = urllib.quote('/api/?type=user-id&action=set&key=' + self.apikey + '&vsys=vsys1' + '&cmd=<uid-message><version>1.0</version><type>update</type><payload><unregister><entry identifier="'+ tagid + '"/></unregister></payload></uid-message>' , "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        return ret

    def remove_mapping(self, tagid, ip):
        ret = urllib.quote('/api/?type=user-id&action=set&key=' + self.apikey + '&vsys=vsys1' + '&cmd=<uid-message><version>1.0</version><type>update</type><payload><unregister><entry identifier="'+ tagid + '" ip="'+ ip + '"/></unregister></payload></uid-message>' , "%:=&?~#+!$,;'@()*[]/")
        ret = self.rest_call(ret, {}, 'GET')
        return ret

    def add_mapping(self, tagid, ip):
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
