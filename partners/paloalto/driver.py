#!/usr/bin/python

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
This module synchronizes membership in virtual networks with dynamic objects
on various firewalls.  
"""

import sys
import bsc
import fw
import time
import ConfigParser
import logging
import threading


class Driver():

    # Initialize list of firewalls and controller
    # Expects config file with DEFAULT section and at least one FIREWALL
    def __init__(self, configFile='paconfig.cfg', logger=None):
       
        self.firewalls = []
        self.bsn = None
        self.prevState = {}

        if logger:
            global log
            self.logger = log = logger
        else:
            self.logger = log = logging

        config = ConfigParser.ConfigParser()
        config.read(configFile)

        try:
            self.numrules = int(config.get('DEFAULT', 'number-of-rules'))
            bsc_ip = config.get('DEFAULT', 'bsc-ip-address')
            self.delay = int(config.get('DEFAULT', 'delay'))
        except:
            print "Please specify number_of_objects, bsc-ip-address, and delay"
            exit(1)

        self.bsc = bsc.Controller(bsc_ip)

        for section in config.sections():
            try:
                ip = config.get(section, "ip-address")
                user = config.get(section, "username")
                password = config.get(section, "password")
                fwall = fw.paserver(ip, user, password)
                self.firewalls.append(fwall)
            except:
                print "Each section must specify ip-address, username, and password"
                exit(1)

    def sync(self, fwall, device_info):
        curState = {}

        # Get new state (network segments and ips)  for the sdn controller
        for d in device_info:
            if len(d['device']['ipv4']) > 0:
                if len(d['iface']) > 0:
                    for rule in d['iface']:
                        if rule['parentRule'] != None and not rule['parentRule']['multipleAllowed']:
                            name = d['iface'][0]['parentBVS']['name']
                            if not name == "default":
                                if not name in curState.keys():
                                    curState[name] = list(d['device']['ipv4'])
                                else:
                                    curState[name] = curState[name] + list(d['device']['ipv4'])
                                    
                             
        # Synchronize this state with each registered firewall dynamic objects
        for name in curState.keys():
            if name in self.prevState.keys():
                # Network segment in both previous and current
                # Sync ips
                for ip in curState[name]:
                    if not ip in self.prevState[name]:
                        # Add it
                        for i in range(self.numrules):
                            fwall.add_mapping(name + str(i), ip)
                            self.logger.debug('Existing: adding new ip %s%s %s' % 
                                              (name, str(i), ip))

                for ip in self.prevState[name]:
                    if not ip in curState[name]:
                        # Remove it
                        for i in range(self.numrules):
                            fwall.remove_mapping(name + str(i), ip)
                            self.logger.debug('Existing: removing new ip %s%s %s' %
                                              (name, str(i), ip))
            else:
                # In current state but not added previously, add it
                for ip in curState[name]:
                    for i in range(self.numrules):
                        fwall.add_mapping(name + str(i), ip) 
                        self.logger.debug('New: adding new ip %s%s %s' %
                                          (name, str(i), ip))

        for name in self.prevState.keys():
            if not name in curState.keys():
                # In previous state but not current, remove it
                for i in range(self.numrules):
                    fwall.clear_mapping(name + str(i))
                    self.logger.debug('Stale: removing new ip %s%s' %
                                      (name, str(i)))

        # Store current state for next sync
        self.prevState = dict(curState)

    # Loop forever synchronizing state
    def run(self):
        self.clean()
        while True:
            bsc_info = self.bsc.device_interface_get()
            for fwall in self.firewalls:
                self.sync(fwall, bsc_info)
            time.sleep(self.delay)
    
    # Remove dynamic objects from all firewalls
    def clean(self):
        bsc_info = self.bsc.bvs_get()
        for fwall in self.firewalls:
            for bvs in bsc_info:
                for i in range(self.numrules):
                    fwall.clear_mapping(bvs["id"] + str(i))

    # Show objects present in all firewalls.  
    # Note objects are not visible unless used in rules
    def show(self):
        for fwall in self.firewalls:
            print "Firewall " + fwall.server
            fwall.list_mapping()

#######
# Main thread
#######

def main():
    driver = Driver()

    if len(sys.argv) >= 2:
        action = sys.argv[1]
    else:
        action = None
        
    if action == 'clean':
        driver.clean()
    elif action == 'show':
        driver.show()
    else:
        driver.run()
            
##
# Main entry point
if __name__ == '__main__':
   main()
