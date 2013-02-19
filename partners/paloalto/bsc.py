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


import httplib
import json
import logging
import urllib


class Controller(object):
    """
    Controller interfaces for a big switch controller
    """

    def __init__(self, server='localhost', port=80, logger=None):
        self.server = server
        self.port = port
        if logger:
            global log
            self.logger = log = logger
        else:
            self.logger = log = logging

    # added
    def device_interface_get(self):
        ret = self.get('device-interface', namespace='bvs')
        return ret

    def role_get(self):
        role = self.get('ha/role', namespace='system')
        if role is not None:
            role = role.get('role')
        return role

    def feature_get(self):
        return self.get('feature')[0]

    def feature_set(self, feature, value=True):
        features = self.feature_get()
        features[feature] = value
        return self.set('feature', features)

    def feature_dump(self):
        return self.dump('feature', 'Controller Features')

    # note - origin must be None, not quantum
    def bvs_get(self, origin=None, id=None):
        filters = {}
        if origin is not None:
            filters['origin'] = origin
        if id is not None:
            filters['id'] = id
        if not filters:
            filters = None

        networks = self.get('bvs-definition', filters=filters)
        return networks

    def address_space_create(self, address_space_name, origin='quantum'):
        return self.set('address-space', {
            'name': address_space_name,
            'origin': origin,
            'active': True,
        })

    def bvs_create(self, bvsname, origin='quantum'):
        return self.set('bvs-definition', {
            'id': bvsname,
            'origin': origin,
            'active': True,
        })
    
    def bvs_id(self, bvsname):
        return bvsname

    def bvs_delete(self, bvsname):
        return self.delete('bvs-definition/%s' % self.bvs_id(bvsname))

    def address_space_name(self, address_space_name):
        return address_space_name

    def address_space_delete(self, address_space_name):
        return self.delete('address-space/%s' % self.address_space_name(address_space_name))

    def bvs_dump(self):
        return self.dump('bvs-definition', 'BVS Definitions')

    def host_get(self, host=None):
        filters=None
        if host is not None:
            filters = {
                'mac': host,
            }
        return self.get('host-config', filters=filters)

    def host_create(self, hostmac, vlan=None):
        if vlan is not None:
            return self.set('host-config', {
                'mac': hostmac,
                'vlan': vlan,
            })
        else:
            return self.set('host-config', {
                'mac': hostmac,
            })

    def host_id(self, hostmac, vlan=None):
        return hostmac

    def host_delete(self, hostmac, vlan=None):
        return self.delete('host-config/%s' % self.host_id(hostmac, vlan))

    def host_dump(self):
        return self.dump('host-config', 'Configured Hosts')

    def host_alias_get(self, host=None, id=None):
        filters = {}
        if host is not None:
            filters['host'] = host
        if id is not None:
            filters['id'] =id
        if not filters:
            filters = None
        return self.get('host-alias', filters=filters)

    def host_alias_create(self, mac, alias):
        return self.set('host-alias', {
            'id': alias,
            'host': mac,
        })
    
    def host_alias_id(self, alias):
        return alias

    def host_alias_delete(self, alias):
        return self.delete('host-alias/%s' % self.host_alias_id(alias))

    def host_alias_dump(self):
        return self.dump('host-alias', 'Hosts Aliases')

    def ifrule_get(self, id=None):
        filters = None
        if id is not None:
            filters = {
                    'id': id,
            }
        return self.get('bvs-interface-rule', filters=filters)

    def ifrule_create(self,
            bvsname, rulename, ruletype, val,
            allow_multiple=False):
        if ruletype == 'tags' and len(val.split('|')) == 3:
            val = '%s.%s=%s' % tuple(val.split('|'))
        return self.set('bvs-interface-rule', {
            'rule': rulename,
            'bvs': bvsname,
            ruletype: val,
            'allow-multiple': allow_multiple,
            'active': True,
        })

    def ifrule_id(self, bvsname, rulename):
        return '%s|%s' % (bvsname, rulename)

    def ifrule_delete(self, bvsname, rulename):
        return self.delete('bvs-interface-rule/%s' %
                self.ifrule_id(bvsname, rulename))

    def ifrule_dump(self):
        return self.dump('bvs-interface-rule', 'Interface Rules',
                         prnkey=lambda x: x.split('|')[1])

    def tag_get(self, namespace='quantum', name=None):
        filters = {
            'namespace': namespace,
        }
        if name is not None:
            filters['name'] = name
        tags = self.get('tag', filters=filters)
        return tags

    def tag_create(self, name, namespace='quantum', value='true'):
        return self.set('tag', {
            'namespace': namespace,
            'name': name,
            'value': value,
            'persist': True,
        })

    def tag_id(self, name, namespace='quantum', value='true'):
        return '%s|%s|%s' % (namespace, name, value)

    def tag_delete(self, name, namespace='quantum', value='true'):
        return self.delete('tag/%s' %
                self.tag_id(name, namespace, value))

    def tag_dump(self):
        return self.dump('tag', 'Tags')

    def tagmapping_get(self, tagids=None):
        obj = 'tag-mapping'
        if tagids is not None and len(tagids) == 1:
            obj = obj + '?tag=' + tagids[0]
        tagmappings = self.get(obj)

        if tagmappings and tagids is not None and len(tagids) > 1:
            tagmappings = filter(
                lambda tagmapping : tagmapping.get('tag') in tagids,
                tagmappings)
        return tagmappings

    def tagmapping_create(self, tag, hostmac, tagtype='Host'):
        return self.set('tag-mapping', {
            'tag': tag,
            'mac': hostmac,
        })

    def tagmapping_id(self, tagid, hostmac):
        return '%s|%s|||' % (tagid, hostmac)

    def tagmapping_delete(self, tagid, hostmac):
        return self.delete('tag-mapping/%s' %
                self.tagmapping_id(tagid, hostmac))

    def tagmapping_dump(self):
        return self.dump('tag-mapping', 'Tag Mappings')

    def get(self, objtype, filters=None, namespace='model'):
        ret = self.rest_call(objtype, {}, 'GET',
                             filters=filters, namespace=namespace)
        data = None
        if self.rest_ok(ret):
            try:
                # we always expect a valid json, else data should be None
                data = json.loads(ret[2])
            except:
                pass
        return data

    def set(self, objtype, data, namespace='model'):
        ret = self.rest_call(objtype, data, 'PUT', namespace=namespace)
        return self.rest_ok(ret)

    def delete(self, objtype, data={}, namespace='model'):
        ret = self.rest_call(objtype, data, 'DELETE', namespace=namespace)
        return self.rest_ok(ret)

    def rest_call(self, objtype, data, action, filters=None, namespace='model'):
        path = '/rest/v1/%s/%s' % (namespace, objtype)
        if filters:
            path = path+'?'+urllib.urlencode(filters)
        headers = {
            'Content-type': 'application/json',
            'Accept': 'application/json',
        }
        body = json.dumps(data)
        self.logger.debug('Controller REST: %s %s: headers=%r, body=%r' %
                          (action, path, headers, body))


        conn = httplib.HTTPConnection(self.server, self.port, timeout=15)
        conn.request(action, path, body, headers)
        response = conn.getresponse()
        ret = (response.status, response.reason, response.read())
        conn.close()

        self.logger.debug('Controller REST: status=%d, reason=%r, data=%r' %
                          ret)
        return ret

    def rest_ok(self, ret):
        return ret[0] == 200

    def dump(self, objtype, title, key='id', prnkey=lambda x: x):
        ret = []
        ret.append('%s' % title)
        data = self.get(objtype)
        if data:
            for obj in sorted(data, key=lambda x: x[key]):
                ret.append('  %s:' % prnkey(obj[key]))
                for name in sorted(obj):
                    ret.append('    %-16s : %s' % (name, obj[name]))
        elif data is None:
            ret.append('  <Error>')
        else:
            ret.append('  <None>')
        return '\n'.join(ret)
