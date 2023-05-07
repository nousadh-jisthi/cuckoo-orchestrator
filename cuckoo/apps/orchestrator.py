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
from cuckoo.misc import cwd, mkdir

from .apps import enumerate_files

from cuckoo.common.exceptions import (
    CuckooOperationalError, CuckooDatabaseError, CuckooDependencyError
)
from cuckoo.common.mongo import mongo
from cuckoo.common.objects import Dictionary, File
from cuckoo.common.utils import to_unicode
from cuckoo.core.database import (
    Database, TASK_FAILED_PROCESSING, TASK_REPORTED
)

log = logging.getLogger(__name__)

class Orchestrator:
    def __init__(self):
        self.free_cuckoo_hosts = [{
            'ip': "192.168.56.129",
            'identifier': "host1",
            'venv': '/home/cuckoo/.virtualenvs/cuckoo-development/bin/activate',
            'user': 'cuckoo',
            'cwd': '/home/cuckoo/.cuckoo/'
            }]
        self.busy_cuckoo_hosts = []
        self.lock = Lock()
        self.terminated = Event()
        # TODO: Check if this works => self.db = Database()
    

    def free_host(self, host):
        self.lock.acquire()
        self.busy_cuckoo_hosts.remove(host)
        self.free_cuckoo_hosts.append(host)
        self.lock.release()

    def get_busy_host(self, identifier):
        for busy_host in self.busy_cuckoo_hosts:
            if busy_host['identifier'] == identifier:
                return busy_host
    
    def use_host(self):
        self.lock.acquire()
        used_host = self.free_cuckoo_hosts.pop(0)
        self.busy_cuckoo_hosts.append(used_host)
        self.lock.release()
        return used_host
    

    def http_handler(self, conn):

        db = Database()

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

        host = self.get_busy_host(identifier)
        # print(data)

        row = db.orchestrator_complete(assigned_to=identifier, remote_job_id=task_id)

        # TODO: Suppress SCP output
        # print (row)
        if row:
            print "Host: " + identifier + " completed (remote) task id: " + task_id
            # Transfer file to host
            client = host['user'] + "@" + host['ip']

            orchestrator_storage_path = cwd("storage", "orchestrator")
            p = subprocess.Popen(["scp","-r", client+":"+host["cwd"]+"/storage/analyses/"+str(task_id), orchestrator_storage_path+"/"+str(row.id)])
            os.waitpid(p.pid, 0)

            print "Orchestrator sample : " + str(row.id) + " finished processing."
            

        self.free_host(host)
        
        # TODO: Check this
        conn.send("HTTP/1.1 200 OK\r\n\\r\n\\r\n".encode())


    def submit_to_host(self):
        db = Database()

        while not self.terminated.is_set():
            if len(self.free_cuckoo_hosts) > 0 :
                
                sample = db.orchestrator_fetch()

                if sample:
                    filename = sample.target.split("/")[-1]   # last item on target is filename

                    host = self.use_host()


                    # Transfer file to host
                    client = host['user'] + "@" + host['ip']
                    p = subprocess.Popen(["scp", sample.target, client+":/tmp/"])
                    os.waitpid(p.pid, 0)

                    # Run the cuckoo submit command
                    command = "ssh " + client +" \""
                    
                    # if venv is used on host
                    if host['venv'] != "":
                        command += "source "+host['venv']+" && "
                
                    command += "cuckoo submit /tmp/"+filename+ "\""

                    ret = subprocess.check_output(command, shell=True)
                    submitted_id = ret.split()[-1][1:]

                    print "New job submitted on :" + host['ip']
                    # print ret
                    print "Job ID on remote Host: " + ret.split()[-1][1:]
                    print "Sample ID on orchestrator: " + str(sample.id)
                
                    db.orchestrator_update(sample_id=sample.id, assigned_to=host['identifier'], remote_job_id=int(ret.split()[-1][1:]))

                else:
                    sleep(5)

            else:
                sleep(5)

def cuckoo_orchestrator(host="192.168.56.128",port=8888):
    try:
        # create storage directory for orchestrator if it does not already exist
        path = cwd("storage", "orchestrator")
        if not os.path.isdir(path):
            mkdir(path)

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


def cuckoo_orchestrator_submit(target):
    # Some of this code was copied over from submit_tasks

    db = Database()

    files = []
    for path in target:
        files.extend(enumerate_files(os.path.abspath(path), pattern=''))
    
    for filepath in files:
        if not os.path.getsize(filepath):
            print "%s: sample %s (skipping file)" % (
                bold(yellow("Empty")), filepath
            )
            continue

        else:
            sample_id = db.orchestrator_add_path(file_path=filepath)
            # TODO: keep track of file ids
            yield filepath, sample_id

