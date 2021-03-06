import SimpleHTTPServer
import SocketServer
import os
import shutil
from subprocess import check_call
import tempfile
import threading
import unittest
import errno
import socket


class ClusterInitTest(unittest.TestCase):
    
    @classmethod
    def setUpClass(clz):
        clz.jetpack = tempfile.mkdtemp("jetpack")
        os.chdir(clz.jetpack)
        for port in range(8180, 8280):
            try:
                clz.http_server = SocketServer.TCPServer(("", port), SimpleHTTPServer.SimpleHTTPRequestHandler)
                clz.port = port
                break
            except socket.error as e:
                if e.errno != errno.EADDRINUSE:
                    raise
        
        def run_server():
            try:
                clz.http_server.serve_forever(.1)
            except Exception:
                pass
        
        threading.Thread(target=run_server).start()
        
        # mock jetpack
        with open("jetpack", "w") as fw:
            fw.write("""#/bin/bash -e
curl http://localhost:%s/$(echo $2 | sed s/\\\\./\\\\//g) > response 2>/dev/null
grep '\<body\>' response 1>&2 > /dev/null

if [ $? == 0 ]; then
    if [ "$3" != "" ]; then
       printf $3
        exit
    else
        exit 1
    fi
else
    cat response
fi""" % clz.port)
        
        os.system("chmod +x jetpack")

    def setUp(self):
        if os.path.exists("/tmp/azurecc.profile"):
            os.remove("/tmp/azurecc.profile")
                    
        self.symphony_top = tempfile.mkdtemp("symphony_top")
        os.makedirs(os.path.join(self.symphony_top, "conf"))
        with open(os.path.join(self.symphony_top, "conf", "symphony.conf"), "w") as fw:
            fw.write("# comment\n")
            fw.write("SYM_LOCAL_RESOURCES=\"[resource canary]\"\n")
            fw.write("SOME_TIMEOUT=100\n")
        
    def tearDown(self):
        shutil.rmtree(self.symphony_top)
        for fil in os.listdir(ClusterInitTest.jetpack):
            if fil == "jetpack":
                continue
            
            path = os.path.join(self.jetpack, fil)
            if os.path.isdir(path):
                shutil.rmtree(path)
            else:
                os.remove(path)
        
    @classmethod
    def tearDownClass(clz):
        clz.http_server.server_close()
        clz.http_server.shutdown()
        shutil.rmtree(clz.jetpack)
        
    def _create_jetpack_config(self, data, cwd=None):
        if cwd is None:
            cwd = os.getcwd()
            
        # create files so that self.http_server can serve them
        for key, value in data.iteritems():
            
            new_file = os.path.join(cwd, key)
            print new_file
            if isinstance(value, dict):
                os.makedirs(new_file)
                self._create_jetpack_config(value, new_file)
            else:
                with open(new_file, "w") as fw:
                    fw.write(str(value))
                    
    def test_execute_create_azurecc_profile(self):
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                            "local_etc": "/tmp",
                                            "custom_env_names": "name1 name2",
                                            "custom_env": {"name1": "value1",
                                                           "name2": "value2"}}})
        self._call("00-create-azurecc-profile.sh")
        self._assert_profile_equals({"export name1": "value1", "export name2": "value2"})
        
    def test_execute_create_azurecc_profile_empty(self):
        assert not os.path.exists("/tmp/azurecc.profile")        
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "local_etc": "/tmp"}})
        self._call("00-create-azurecc-profile.sh")
        self._assert_profile_equals({})
        
    def test_modify_symphony_local_resources_disable(self):
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "skip_modify_local_resources": 1,
                                             "attributes": {"custom1": "custom_value1",
                                                            "custom2": "custom_value2"},
                                             "attribute_names": "custom1 custom2"}})
        self._call("00-create-azurecc-profile.sh")
        self._call("01-modify-symphony-local-resources.sh")
        self._assert_local_resources_equals('"[resource canary]"')
        
    def test_modify_symphony_local_resources_skip_because_uri(self):
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "local_etc": self.symphony_top + "/conf",
                                             "custom_script_uri": "anything",
                                             "attributes": {"custom1": "custom_value1",
                                                            "custom2": "custom_value2"},
                                             "attribute_names": "custom1 custom2"}})
        self._call("00-create-azurecc-profile.sh")
        self._call("01-modify-symphony-local-resources.sh")
        self._assert_local_resources_equals('"[resource canary]"')
        
    def test_modify_symphony_local_resources(self):
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "local_etc": self.symphony_top + "/conf",
                                             "attributes": {"custom1": "custom_value1"},
                                             "attribute_names": "custom1"}})
        self._call("00-create-azurecc-profile.sh")
        self._call("01-modify-symphony-local-resources.sh")
        self._assert_local_resources_equals('" [resourcemap custom_value1*custom1]"')
        
    def test_modify_symphony_local_resources2(self):
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "local_etc": self.symphony_top + "/conf",
                                             "attributes": {"custom1": "custom_value1",
                                                            "custom2": "custom_value2"},
                                             "attribute_names": "custom1 custom2"}})
        self._call("00-create-azurecc-profile.sh")
        self._call("01-modify-symphony-local-resources.sh")
        self._assert_local_resources_equals('" [resourcemap custom_value1*custom1] [resourcemap custom_value2*custom2]"')
        
    def test_run_custom_script_uri(self):
        with open("custom_script.sh", "w") as fw:
            fw.write("#!/bin/bash -e\n")
            fw.write('echo SYM_LOCAL_RESOURCES=$name1 and $name2 > %s/conf/symphony.conf' % self.symphony_top)
        os.system("chmod +x custom_script.sh")
        # so we will skip step 01 and just 
        self._create_jetpack_config({"symphony": {"symphony_top": self.symphony_top,
                                             "local_etc": self.symphony_top + "/conf",
                                             "custom_script_uri": "file://%s" % os.path.abspath("custom_script.sh"),
                                             "custom_env_names": "name1 name2",
                                             "attributes": {"custom1": "True", "custom2": "falsE"},
                                             "attribute_names": "custom1 custom2",
                                             "custom_env": {"name1": "value1",
                                                           "name2": "value2"}}})
        self._call("00-create-azurecc-profile.sh")
        self._call("01-modify-symphony-local-resources.sh")
        self._assert_local_resources_equals('"[resource canary]"')
        self._call("02-run-custom-script-uri.sh")
        self._assert_local_resources_equals('value1 and value2')
        
    def _call(self, script_name):
        script = os.path.join(os.path.dirname(__file__), "..", "..", "..", "..", "..", "execute", "cluster-init", "scripts", script_name)
        script = os.path.abspath(script)
        os.system("chmod +x %s" % script)
        self.assertTrue(os.path.exists(script), script)
        env = {}
        env.update(os.environ)
        env["PATH"] = ".:" + env["PATH"]
        check_call([script], env=env)
        
    def _parse(self, path):
        with open(path) as fr:
            key_vals = {}
            
            for line in fr:
                line = line.strip()
                if line.startswith("#"):
                    continue
                assert "=" in line, line
                key, value = line.split("=", 1)
                key_vals[key.strip()] = value.strip()
    
        return key_vals 
    
    def _assert_profile_equals(self, expected):
        profile_vars = self._parse("/tmp/azurecc.profile")
        #profile_vars = self._parse(os.path.join(self.symphony_top, "conf", "azurecc.profile"))
        self.assertEquals(expected, profile_vars)
        
    def _assert_local_resources_equals(self, expected):
        symphony_conf_vars = self._parse(os.path.join(self.symphony_top, "conf", "symphony.conf"))
        self.assertEquals(expected.strip(), symphony_conf_vars["Symphony_LOCAL_RESOURCES"].strip())


if __name__ == "__main__":
    unittest.main()
