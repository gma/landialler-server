#!/usr/bin/env python
#
# landiallerd.py - the LANdialler daemon
#
# Copyright (C) 2001-2004 Graham Ashton
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation; either version 2, or (at your option)
# any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 59 Temple Place - Suite 330, Boston, MA 02111-1307, USA.
#
# $Id: landiallerd.py,v 1.66 2004/10/03 10:28:58 ashtong Exp $


"""serves LANdialler clients, manages connections

LANdialler enables several computers on a home LAN to remotely control
a dial up device (e.g. modem) that is connected to a single Unix
workstation. This scenario is explained in more detail on the
LANdialler web site.

There are two programs that make up a complete LANdialler system; the
client (landialler.py) and the server (landiallerd.py). You're reading
the documentation for the server.

The client and server communicate via XML-RPC. The server runs in the
background (as a daemon) waiting for clients to connect to it and
request an Internet connection (through the LANdialler XML-RPC API).
By default the server listen for connections on port 6543.

The client/server API defines three procedures that the client can
call; connect(), disconnect() and get_status(). These are individually
documented below. Each procedure runs an external script/program to
perform their task, making the server more portable between different
versions of Unix, or distributions of Linux. Each command should
return immediately. Commands are specified in the [commands] section
of the landiallerd.conf configuration file.

A sample configuration file should be included with the package, but
the following should serve as a good example:

  [commands]
  connect: /usr/local/bin/start-connection.sh
  disconnet: /usr/local/bin/stop-connection.sh
  is_connected: /sbin/ifconfig ppp0 | grep "inet addr" >/dev/null

  [server]
  port: 6543

Note that you can also configure the TCP port number that landiallerd.py
uses to communicate with the clients.

The connect and disconnect scripts referenced in the config file
should both make sure that they exit immediately; the connect command
MUST NOT block before the connection has been made. If you have
managed to integrate LANdialler cleanly with your operating system's
dial up scripts please send your configuration to the author and they
will be made available on the web site (with credits).

More information on LANdialler is available at the project home page:

  http://landialler.sourceforge.net/

The author can be contacted at ashtong@users.sourceforge.net.

"""


import ConfigParser
import getopt
import os
import SimpleXMLRPCServer
import SocketServer
import sys
import syslog
import threading
import time
import xmlrpclib


class Logger:

    def __init__(self):
        ident = os.path.splitext(os.path.basename(sys.argv[0]))[0]
        syslog.openlog(ident, syslog.LOG_PID | syslog.LOG_CONS,
                       syslog.LOG_DAEMON)

    def info(self, msg):
        syslog.syslog(syslog.LOG_INFO, msg)

    def warn(self, msg):
        syslog.syslog(syslog.LOG_WARNING, msg)
        
    def error(self, msg):
        syslog.syslog(syslog.LOG_ERR, msg)


log = Logger()


class Timer(object):

    """Simple timer class to record elapsed times."""

    def __init__(self):
        """Run the start() method."""
        self._start_time = None  # seconds since epoch
        self._stop_time = None
        self.reset()
        self.is_running = False

    def start(self):
        """Start the timer."""
        self._start_time = time.time()
        self.is_running = True

    def stop(self):
        """Stop the timer."""
        self._stop_time = time.time()
        self.is_running = False

    def reset(self):
        """Reset the timer to zero.

        Note that reset() neither stops or starts the timer.

        """
        self._start_time = time.time()
        self._stop_time = time.time()

    def _get_elapsed_seconds(self):
        """Return seconds since timer started."""
        if self.is_running:
            return int('%.0f' % (time.time() - self._start_time))
        else:
            return int('%.0f' % (self._stop_time - self._start_time))

    elapsed_seconds = property(_get_elapsed_seconds)


class Modem(object):

    def __init__(self, config_parser):
        self._config_parser = config_parser
        self.timer = Timer()

    def connect(self):
        log.info('Connecting')
        self.timer.reset()
        os.system(self._config_parser.get('commands', 'connect'))

    def disconnect(self):
        log.info('Disconnecting, online for %s seconds' %
                 self.timer.elapsed_seconds)
        self.timer.stop()
        os.system(self._config_parser.get('commands', 'disconnect'))

    def is_connected(self):
        rval = os.system(self._config_parser.get('commands', 'is_connected'))
        if rval == 0:
            if not self.timer.is_running:
                self.timer.start()
            return True
        else:
            return False


class ModemProxy(object):

    CLIENT_TIMEOUT = 30

    def __init__(self, modem):
        self._modem = modem
        self._clients = {}
        self._is_dialling = False

    def add_client(self, client_id):
        if client_id not in self._clients:
            self._clients[client_id] = time.time()
        if not (self._is_dialling or self.is_connected()):
            self._is_dialling = True
            self._modem.connect()

    def refresh_client(self, client_id):
        self._clients[client_id] = time.time()

    def remove_client(self, client_id):
        if client_id in self._clients:
            del self._clients[client_id]
        if not self._clients:
            if self.is_connected() or self._is_dialling:
                self.disconnect()

    def remove_old_clients(self):
        for client_id, time_last_seen in self._clients.items():
            if (time.time() - time_last_seen) > self.CLIENT_TIMEOUT:
                self.remove_client(client_id)

    def count_clients(self):
        return len(self._clients.keys())

    def is_connected(self):
        if self._modem.is_connected():
            self._is_dialling = False
            return True
        else:
            return False

    def get_time_connected(self):
        return self._modem.timer.elapsed_seconds

    def disconnect(self):
        self._is_dialling = False
        self._modem.disconnect()


class API(object):
    
    """Implements the LANdialler API.

    All accessible methods in this class form a part of the LANdialler
    XML-RPC API, and are called directly whenever a client makes an
    HTTP request to the server.

    """

    def __init__(self, modem_proxy):
        self._modem_proxy = modem_proxy

    def connect(self, client_id):
        """Register this client and open the connection if necessary.

        Always returns True.

        """
        log.info('%s connected' % client_id)
        self._modem_proxy.add_client(client_id)
        return xmlrpclib.True

    def disconnect(self, client_id, all=xmlrpclib.False):
        """Disconnect this client and/or close the connection.

        Always returns True.

        The client argument should uniquely identify the client, and
        should be usable as a dictionary key.

        """
        message = '%s disconnected' % client_id
        if bool(all):
            message += ' (all users)'
        log.info(message)
        self._modem_proxy.remove_client(client_id)
        if bool(all):
            self._modem_proxy.disconnect()
        return xmlrpclib.True
                
    def get_status(self, client_id):
        """Returns the number of clients and connection status.

        The values returned are:

        current_clients    -- The number of users sharing the connection
        is_connected       -- True if connected, False otherwise
        seconds_connected  -- Number of seconds connected

        """
        self._modem_proxy.refresh_client(client_id)
        return (self._modem_proxy.count_clients(),
                self._modem_proxy.is_connected(),
                self._modem_proxy.get_time_connected())
    

class AutoDisconnectThread(threading.Thread):

    INTER_CHECK_PERIOD = 5  # seconds

    def __init__(self, modem_proxy):
        threading.Thread.__init__(self)
        self._modem_proxy = modem_proxy
        self.finished = threading.Event()
        self.setDaemon(True)
        self.setName('AutoDisconnect')

    def run(self):
        proxy = self._modem_proxy
        while not self.finished.isSet():
            proxy.remove_old_clients()
            self.finished.wait(self.INTER_CHECK_PERIOD)


class ReusableSimpleXMLRPCServer(SimpleXMLRPCServer.SimpleXMLRPCServer):

     allow_reuse_address = True

 
class App(object):

    def __init__(self):
        self._become_daemon = True
        self._config = self._load_config_file()
        modem = Modem(self._config)
        self._modem_proxy = ModemProxy(modem)

    def _load_config_file(self):
        try:
            config = ConfigParser.ConfigParser()
            config.read(['/usr/local/etc/landiallerd.conf',
                         '/etc/landiallerd.conf',
                         'landiallerd.conf'])
            return config
        except Exception, e:
            print 'Terminating - error reading config file: %s' % e
            sys.exit()

    def check_platform(self):
        if os.name != "posix":
            print "Sorry, only POSIX compliant systems are supported."
            sys.exit()

    def daemonise(self):
        """Become a daemon process (POSIX only)."""
        if not self._become_daemon:
            return

        # See "Python Standard Library", pg. 29, O'Reilly, for more
        # info on the following.
        pid = os.fork()
        if pid:  # we're the parent if pid is set
            os._exit(0)

        os.setpgrp()
        os.umask(0)

        class DevNull:

            def write(self, message):
                pass
            
        sys.stdin.close()
        sys.stdout = DevNull()
        sys.stderr = DevNull()

    def getopt(self):
        opts, args = getopt.getopt(sys.argv[1:], "dfhl:s")

        for o, v in opts:
            if o == "-f":
                self._become_daemon = False

    def main(self):
        log.info('Starting')
        self.check_platform()
        try:
            self.getopt()
            self.daemonise()
        except getopt.GetoptError, e:
            sys.stderr.write("%s\n" % e)
        
        thread = AutoDisconnectThread(self._modem_proxy)
        thread.start()

        addr = ('', self._config.getint('general', 'port'))
        server = ReusableSimpleXMLRPCServer(addr, logRequests=False)
        server.allow_reuse_address = True
        server.register_instance(API(self._modem_proxy))
        try:
            server.serve_forever()
        except KeyboardInterrupt:
            print "Caught Ctrl-C, shutting down."
            log.info('Exit')

    
if __name__ == "__main__":
    app = App()
    app.main()
