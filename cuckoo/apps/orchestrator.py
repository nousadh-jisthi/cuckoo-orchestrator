# Copyright (C) 2015-2019 Cuckoo Foundation.
# This file is part of Cuckoo Sandbox - http://www.cuckoosandbox.org
# See the file 'docs/LICENSE' for copying permission.

import errno
import json
import logging
import os.path
import re
import signal
import socket
import stat
import subprocess
import sys
import urllib

from time import sleep
from threading import Thread, Lock, Event

from cuckoo.common.colors import red
from cuckoo.misc import version as __version__

log = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.free_cuckoo_hosts = [{
            'ip': "192.168.56.129",
            'identifier': "host1",
            'venv': '/home/cuckoo/.virtualenvs/cuckoo-development/bin/activate',
            'user': 'cuckoo'
            }]
        self.busy_cuckoo_hosts = []
        self.lock = Lock()
        self.terminated = Event()
    

    def free_host(self, ip):
        self.lock.acquire()
        self.busy_cuckoo_hosts.remove(ip)
        self.free_cuckoo_hosts.append(ip)
        self.lock.release()

    
    def use_host(self):
        self.lock.acquire()
        used_host = self.free_cuckoo_hosts.pop(0)
        self.busy_cuckoo_hosts.append(used_host)
        self.lock.release()
        return used_host
    

    def http_handler(self, conn):
        request = b""
        request = conn.recv(2048)
        #print(request)

        post_data = request.decode().split("\r\n")[-1]
        post_data_urldecoded = urllib.unquote_plus(urllib.unquote(post_data).decode('utf8'))
        print(post_data_urldecoded)
        post_list = post_data_urldecoded.split("&")

        identifier = post_list[0].split("=")[1]
        data = json.loads(post_list[1].split("=")[1])
        task_id = post_list[2].split("=")[1]
        
        print "Host: " + identifier + " completed task id: " + task_id
        print(data)


        self.free_host("192.168.56.128")
        
        conn.send("HTTP/1.1 200 OK\r\n\\r\n\\r\n".encode())


    def submit_to_host(self):
        # TODO: Getting a list of files for submission
        # TODO: transferring files to remote host

        filename = "/home/cuckoo/test.sh"
        while not self.terminated.is_set():
            if len(self.free_cuckoo_hosts) > 0 :
                
                host = self.use_host()
                command = "ssh " + host['user'] + "@" + host['ip'] +" \""
                
                # if venv is set on host
                if host['venv'] != "":
                    command += "source "+host['venv']+" && "
            
                command += "cuckoo submit "+filename+ "\""

                ret = subprocess.check_output(command, shell=True)
                submitted_id = ret.split()[-1][1:]
                print "New job submitted on :" + host['ip']
                # print ret
                print "Job ID on remote Host: " + ret.split()[-1][1:]
            else:
                sleep(5)

def cuckoo_orchestrator(host="192.168.56.128",port=8888):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
        s.listen(10)

        orchestrator = Orchestrator()

        submit_thread = Thread(target=orchestrator.submit_to_host)
        submit_thread.start()

        while True:
            connection, addr = s.accept()
            t = Thread(target=orchestrator.http_handler, args=(connection,))
            t.start()
            
    except KeyboardInterrupt:
        orchestrator.terminated.set()
        pass
    except Exception as e:
        print("Error running orchestrator")
        print(e)



