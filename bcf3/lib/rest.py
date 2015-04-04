import json
import httplib
import constants as const


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
            raise Exception(session["error_message"])
        if ("session_cookie" not in session):
            raise Exception("Failed to authenticate: session cookie not set")
        return session["session_cookie"]

    @staticmethod
    def logout(cookie, server, port=const.BCF_CONTROLLER_PORT):
        url = "core/aaa/session[auth-token=\"%s\"]" % cookie
        ret = RestLib.delete(cookie, url, server, port)
        return ret



