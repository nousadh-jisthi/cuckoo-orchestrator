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

from threading import Thread

from cuckoo.common.colors import red
from cuckoo.misc import version as __version__

log = logging.getLogger(__name__)

def handler(conn):
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
    
    conn.send("HTTP/1.1 200 OK\r\n\\r\n\\r\n".encode())

def cuckoo_orchestrator(host="192.168.182.128",port=8888):
    try:
        s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        s.bind((host, port))
        s.listen(10)

        while True:
            connection, addr = s.accept()
            t = Thread(target=handler, args=(connection,))
            t.start()
    except KeyboardInterrupt:
        pass
    except Exception as e:
        print("Error running orchestrator")
        print(e)



