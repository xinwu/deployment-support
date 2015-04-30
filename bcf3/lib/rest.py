import json
import httplib
import constants as const
from membership_rule import MembershipRule


class RestLib(object):
    @staticmethod
    def request(url, prefix="/api/v1/data/controller/", method='GET',
                data='', hashPath=None, host="127.0.0.1:8443", cookie=None):
        headers = {'Content-type': 'application/json'}

        if cookie:
            headers['Cookie'] = 'session_cookie=%s' % cookie

        if hashPath:
            headers[const.HASH_HEADER] = hashPath

        connection = httplib.HTTPSConnection(host)

        try:
            connection.request(method, prefix + url, data, headers)
            response = connection.getresponse()
            ret = (response.status, response.reason, response.read(),
                   response.getheader(const.HASH_HEADER))
            with open(const.LOG_FILE, "a") as log_file:
                log_file.write('Controller REQUEST: %s %s:body=%r' %
                              (method, host + prefix + url, data))
                log_file.write('Controller RESPONSE: status=%d reason=%r, data=%r,'
                               'hash=%r' % ret)
            return ret
        except Exception as e:
            raise Exception("Controller REQUEST exception: %s" % e)


    @staticmethod
    def get(cookie, url, server, port, hashPath=None):
        host = "%s:%d" % (server, port)
        return RestLib.request(url, hashPath=hashPath, host=host, cookie=cookie)


    @staticmethod
    def post(cookie, url, server, port, data, hashPath=None):
        host = "%s:%d" % (server, port)
        return RestLib.request(url, method='POST', hashPath=hashPath, host=host,
                               data=data, cookie=cookie)


    @staticmethod
    def patch(cookie, url, server, port, data, hashPath=None):
        host = "%s:%d" % (server, port)
        return RestLib.request(url, method='PATCH', hashPath=hashPath, host=host,
                               data=data, cookie=cookie)


    @staticmethod
    def put(cookie, url, server, port, data, hashPath=None):
        host = "%s:%d" % (server, port)
        return RestLib.request(url, method='PUT', hashPath=hashPath, host=host,
                               data=data, cookie=cookie)


    @staticmethod
    def delete(cookie, url, server, port, hashPath=None):
        host = "%s:%d" % (server, port)
        return RestLib.request(url, method='DELETE', hashPath=hashPath, host=host,
                               cookie=cookie)


    @staticmethod
    def auth_bcf(server, username, password, port=const.BCF_CONTROLLER_PORT):
        login = {"user": username, "password": password}
        host = "%s:%d" % (server, port)
        ret = RestLib.request("/api/v1/auth/login", prefix='',
                               method='POST', data=json.dumps(login),
                               host=host)
        session = json.loads(ret[2])
        if ret[0] != 200:
            raise Exception(ret)
        if ("session_cookie" not in session):
            raise Exception("Failed to authenticate: session cookie not set")
        return session["session_cookie"]

    @staticmethod
    def logout_bcf(cookie, server, port=const.BCF_CONTROLLER_PORT):
        url = "core/aaa/session[auth-token=\"%s\"]" % cookie
        ret = RestLib.delete(cookie, url, server, port)
        return ret


    @staticmethod
    def get_active_bcf_controller(servers, username, password, port=const.BCF_CONTROLLER_PORT):
        for server in servers:
            try:
                cookie = RestLib.auth_bcf(server, username, password, port)
                url = 'core/controller/role'
                res = RestLib.get(cookie, url, server, port)[2]
                if 'active' in res:
                    return server, cookie
            except Exception as e:
                continue
        return None, None


    @staticmethod
    def get_os_mgmt_segments(server, cookie, port=const.BCF_CONTROLLER_PORT):
        url = (r'''applications/bcf/info/endpoint-manager/segment[tenant="%(tenant)s"]''' %
              {'tenant' : const.OS_MGMT_TENANT})
        ret = RestLib.get(cookie, url, server, port)
        if ret[0] != 200:
            raise Exception(ret)
        res = json.loads(ret[2])
        segments = []
        for segment in res:
            # 'management' or 'Management' segment does not matter
            segments.append(segment['name'].lower())
        return segments


    @staticmethod
    def program_segment_and_membership_rule(server, cookie, rule, port=const.BCF_CONTROLLER_PORT):
        segment_url = (r'''applications/bcf/tenant[name="%(tenant)s"]/segment[name="%(segment)s"]''' %
                      {'tenant' : const.OS_MGMT_TENANT, 'segment' : rule.br_key})
        segment_data = {"name": rule.br_key}
        ret = RestLib.put(cookie, segment_url, server, port, json.dumps(segment_data))
        if ret[0] != 204:
            raise Exception(ret)

        if rule.br_vlan:
            vlan = int(rule.br_vlan)
        else:
            vlan = -1

        intf_rule_url = (r'''applications/bcf/tenant[name="%(tenant)s"]/segment[name="%(segment)s"]/switch-port-membership-rule[interface="%(interface)s"][switch="%(switch)s"][vlan=%(vlan)d]''' %
                       {'tenant'    : const.OS_MGMT_TENANT,
                        'segment'   : rule.br_key,
                        'interface' : const.ANY,
                        'switch'    : const.ANY,
                        'vlan'      : vlan})
        rule_data = {"interface" : const.ANY, "switch" : const.ANY, "vlan" : vlan}
        ret = RestLib.put(cookie, intf_rule_url, server, port, json.dumps(rule_data))
        if ret[0] != 204:
            raise Exception(ret)

        pg_rule_url = (r'''applications/bcf/tenant[name="%(tenant)s"]/segment[name="%(segment)s"]/port-group-membership-rule[port-group="%(pg)s"][vlan=%(vlan)d]''' %
                       {'tenant'    : const.OS_MGMT_TENANT,
                        'segment'   : rule.br_key,
                        'pg'        : const.ANY,
                        'vlan'      : vlan})
        rule_data = {"port-group" : const.ANY, "vlan" : vlan}
        ret = RestLib.put(cookie, pg_rule_url, server, port, json.dumps(rule_data))
        if ret[0] != 204:
            raise Exception(ret)

        specific_rule_url = (r'''applications/bcf/tenant[name="%(tenant)s"]/segment[name="%(segment)s"]/switch-port-membership-rule[interface="%(interface)s"][switch="%(switch)s"][vlan=%(vlan)d]''' %
                       {'tenant'    : const.OS_MGMT_TENANT,
                        'segment'   : rule.br_key,
                        'interface' : rule.br_key,
                        'switch'    : const.ANY,
                        'vlan'      : -1})
        rule_data = {"interface" : rule.br_key, "switch" : const.ANY, "vlan" : -1}
        ret = RestLib.put(cookie, specific_rule_url, server, port, json.dumps(rule_data))
        if ret[0] != 204:
            raise Exception(ret)



