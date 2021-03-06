import json

import logging
from urllib import urlencode


try:
    import cyclecli
except ImportError:
    import cyclecliwrapper as cyclecli
    

class Cluster:
    
    def __init__(self, cluster_name, provider_config, logger=None):
        self.cluster_name = cluster_name
        self.provider_config = provider_config
        self.logger = logger or logging.getLogger()
    
    def status(self):
        '''pprint.pprint(json.dumps(json.loads(dougs_example)))'''
        return self.get("/clusters/%s/status" % self.cluster_name)

    def add_nodes(self, request):
        return self.post("/clusters/%s/nodes/create" % self.cluster_name, json=request)
    
    def all_nodes(self):
        return self.get("/clusters/%s/nodes" % self.cluster_name)

    def nodes(self, request_ids):
        responses = {}
        for request_id in request_ids:
            responses[request_id] = self.get("/clusters/%s/nodes" % self.cluster_name, request_id=request_id)
        return responses

    def terminate(self, machines):
        machine_ids = [machine["machineId"] for machine in machines]
        response_raw = self.post("/clusters/%s/nodes/terminate" % self.cluster_name, json={"ids": machine_ids})
        response = json.loads(response_raw)

        # kludge: work around
        # if Symphony may have a stale machineId -> hostname mapping, so find the existing instance with that hostname and kill it
        machine_names = [ machine["name"].split(".")[0] for machine in machines if machine.get("name") ]
        if machine_names:
            self.logger.warn("Terminating the following nodes by machine_names: %s", machine_names)

            f = urlencode({"instance-filter": 'HostName in {%s}' % ",".join('"%s"' % x for x in machine_names)})
            try:
                self.post("/cloud/actions/terminate_node/%s?%s" % (self.cluster_name, f))
            except cyclecli.UserError as e:
                if "No instances were found matching your query" in unicode(e):
                   return
                raise

            
    def _session(self):
        config = {"verify_certificates": False,
                  "username": self._get_or_raise("cyclecloud.config.username"),
                  "password": self._get_or_raise("cyclecloud.config.password"),
                  "cycleserver": {
                      "timeout": 60
                  }
        }
        return cyclecli.get_session(config=config)
    
    def _get_or_raise(self, key):
        value = self.provider_config.get(key)
        if not value:
            #  jetpack.config.get will raise a ConfigError above.
            raise cyclecli.ConfigError("Please define key %s in the provider config." % key)
        return value
    
    def post(self, url, data=None, json=None, **kwargs):
        root_url = self._get_or_raise("cyclecloud.config.web_server")
        self.logger.debug("POST %s with data %s json %s kwargs %s", root_url + url, data, json, kwargs)
        session = self._session()
        response = session.post(root_url + url, data, json, **kwargs)
        if response.status_code < 200 or response.status_code > 299:
            raise ValueError(response.content)
        return response.content
        
    def get(self, url, **params):
        root_url = self._get_or_raise("cyclecloud.config.web_server")
        self.logger.debug("GET %s with params %s", root_url + url, params)
        session = self._session()
        response = session.get(root_url + url, params=params)
        if response.status_code < 200 or response.status_code > 299:
            raise ValueError(response.content)
        return json.loads(response.content)
