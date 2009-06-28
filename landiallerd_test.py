# $Id: landiallerd_test.py,v 1.18 2004/10/03 10:28:58 ashtong Exp $


import mock
import time
import unittest
import threading
import xmlrpclib

import landiallerd


class MockTime:

    def __init__(self, offset):
        self._offset = offset

    def time(self):
        return time.time() + self._offset


class TimerTest(unittest.TestCase):

    def test_start(self):
        """Check we can start the timer"""
        timer = landiallerd.Timer()
        timer.start()
        try:
            real_time = landiallerd.time
            offset = (39 * 60) + 23
            landiallerd.time = MockTime(offset)
            self.assertEqual(timer.elapsed_seconds, offset)
        finally:
            landiallerd.time = real_time

    def test_reset(self):
        """Check we can reset the timer"""
        timer = landiallerd.Timer()
        timer.start()
        try:
            real_time = landiallerd.time
            offset = (39 * 60) + 23
            landiallerd.time = MockTime(offset)
            timer.reset()
            self.assertEqual(timer.elapsed_seconds, 0)
        finally:
            landiallerd.time = real_time

    def test_stop(self):
        """Check we can stop the timer"""
        timer = landiallerd.Timer()
        timer.start()
        try:
            real_time = landiallerd.time
            offset = (39 * 60) + 23
            landiallerd.time = MockTime(offset)
            timer.stop()
            self.assertEqual(timer.elapsed_seconds, offset)
            landiallerd.time = MockTime((45 * 60) + 32)
            self.assertEqual(timer.elapsed_seconds, offset)
        finally:
            landiallerd.time = real_time

    def test_elapsed_seconds(self):
        """Check we can keep track of elapsed seconds"""
        timer = landiallerd.Timer()
        timer.start()
        try:
            real_time = landiallerd.time
            landiallerd.time = MockTime((10 * 60) + 23)
            timer.stop()
            self.assertEqual(timer.elapsed_seconds, 623)
        finally:
            landiallerd.time = real_time

    def test_timer_stopped_by_default(self):
        """Check timer is stopped by default"""
        timer = landiallerd.Timer()
        self.assertEqual(timer.is_running, False)


class ModemTest(unittest.TestCase):

    SUCCESSFUL_COMMAND = 'ls / > /dev/null'
    FAILING_COMMAND = 'ls /missing.file 2> /dev/null'

    def test_dial(self):
        """Check we can dial the modem and receive the return code"""
        config = mock.Mock({'get': self.SUCCESSFUL_COMMAND})
        modem = landiallerd.Modem(config)
        try:
            real_os = landiallerd.os
            mock_os = mock.Mock()
            landiallerd.os = mock_os
            modem.connect()
            command = mock_os.getNamedCalls('system')[0].getParam(0)
            self.assertEqual(command, self.SUCCESSFUL_COMMAND)
        finally:
            landiallerd.os = real_os

    def test_disconnect(self):
        """Check we can hang up the modem and receive the return code"""
        config = mock.Mock({'get': self.SUCCESSFUL_COMMAND})
        modem = landiallerd.Modem(config)
        try:
            real_os = landiallerd.os
            mock_os = mock.Mock()
            landiallerd.os = mock_os
            modem.disconnect()
            command = mock_os.getNamedCalls('system')[0].getParam(0)
            self.assertEqual(command, self.SUCCESSFUL_COMMAND)
        finally:
            landiallerd.os = real_os

    def test_is_connected(self):
        """Check we can test if we're connected"""
        config = mock.Mock({'get': self.SUCCESSFUL_COMMAND})
        modem = landiallerd.Modem(config)
        try:
            real_os = landiallerd.os
            mock_os = mock.Mock({'system': 0})
            landiallerd.os = mock_os
            self.assertEqual(modem.is_connected(), True)
            mock_os = mock.Mock({'system': 1})
            landiallerd.os = mock_os
            self.assertEqual(modem.is_connected(), False)
        finally:
            landiallerd.os = real_os

    def test_timer(self):
        """Check the timer is stopped when we hang up"""
        config = mock.Mock({'get': self.SUCCESSFUL_COMMAND})
        modem = landiallerd.Modem(config)
        modem.connect()
        modem.is_connected()
        self.assertEqual(modem.timer.is_running, True)
        try:
            real_time = landiallerd.time
            offset = (39 * 60) + 23
            landiallerd.time = MockTime(offset)
            modem.is_connected()
            self.assertEqual(modem.timer.elapsed_seconds, offset)
            modem.disconnect()
            landiallerd.time = MockTime(offset + 1)
            self.assertEqual(modem.timer.elapsed_seconds, offset)
            modem.connect()
            self.assertEqual(modem.timer.elapsed_seconds, 0)
        finally:
            landiallerd.time = real_time

    def test_timer_not_started_unless_online(self):
        """Check the timer not started when not connected"""
        config = mock.Mock({'get': self.FAILING_COMMAND})
        modem = landiallerd.Modem(config)
        modem.is_connected()
        try:
            real_time = landiallerd.time
            landiallerd.time = MockTime(18)
            self.assertEqual(modem.timer.elapsed_seconds, 0)
        finally:
            landiallerd.time = real_time
        

class MockTimer:

    elapsed_seconds = 14


class ModemProxyTest(unittest.TestCase):

    def test_dial_called_once(self):
        """Check the proxy knows when the modem is dialling"""
        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        proxy.add_client('client-id-2')
        self.assertEqual(len(modem.getNamedCalls('connect')), 1)

    def test_dial_called_again(self):
        """Check the modem can be dialled multiple times per session"""
        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('connect')), 1)
        proxy.remove_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 1)
        proxy.add_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('connect')), 2)

    def test_proxy_knows_when_dialling_successful(self):
        """Check proxy knows when dialling has completed"""
        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        proxy.is_connected()
        self.assertEqual(proxy._is_dialling, True)
        modem = mock.Mock({'is_connected': True})
        proxy._modem = modem
        proxy.is_connected()
        self.assertEqual(proxy._is_dialling, False)

    def test_dont_dial_if_connected(self):
        """Check proxy doesn't dial up if modem connected"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('connect')), 0)

    def test_is_connected(self):
        """Check proxy knows when we're connected"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        self.assert_(proxy.is_connected())

        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        self.failIf(proxy.is_connected())

    def test_client_counting(self):
        """Check proxy keeps track of number of connected clients"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        proxy.add_client('client-id-2')
        proxy.add_client('client-id-2')
        self.assertEqual(proxy.count_clients(), 2)

        proxy.remove_client('client-id-1')
        self.assertEqual(proxy.count_clients(), 1)
        proxy.remove_client('client-id-2')
        self.assertEqual(proxy.count_clients(), 0)

        proxy.remove_client('bad-client-id')  # mustn't raise

    def test_automatic_disconnect(self):
        """Check modem hung up when no clients remain"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)

        proxy.add_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('is_connected')), 1)

        proxy.remove_client('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('is_connected')), 2)
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 1)

    def test_force_hangup(self):
        """Check the proxy can forcefully drop modem connection"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)

        proxy.add_client('client-id-1')
        proxy.add_client('client-id-2')

        proxy.remove_client('client-id-1')
        proxy.disconnect()
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 1)

    def test_timer(self):
        """Check the proxy can return time spent online"""
        timer = MockTimer()
        modem = landiallerd.Modem(mock.Mock())
        modem.timer = timer
        proxy = landiallerd.ModemProxy(modem)
        self.assertEqual(proxy.get_time_connected(), 14)

    def test_forget_old_clients(self):
        """Check the proxy forgets about old clients"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        self.assertEqual(proxy.count_clients(), 1)
        try:
            real_time = landiallerd.time
            offset = landiallerd.ModemProxy.CLIENT_TIMEOUT
            landiallerd.time = MockTime(offset)
            proxy.remove_old_clients()
            self.assertEqual(proxy.count_clients(), 0)
        finally:
            landiallerd.time = real_time

    def test_forgetting_drops_connection(self):
        """Check forgetting the last client drops the connection"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        try:
            real_time = landiallerd.time
            offset = landiallerd.ModemProxy.CLIENT_TIMEOUT
            landiallerd.time = MockTime(offset)
            proxy.remove_old_clients()
            self.assertEqual(proxy.count_clients(), 0)
            disconnect_calls = modem.getNamedCalls('disconnect')
            self.assertEqual(len(disconnect_calls), 1)
        finally:
            landiallerd.time = real_time
        
    def test_refresh_client(self):
        """Check refreshing a client updates time client was last seen"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        try:
            real_time = landiallerd.time
            offset = landiallerd.ModemProxy.CLIENT_TIMEOUT
            landiallerd.time = MockTime(offset)
            proxy.refresh_client('client-id-1')
            self.assertEqual(proxy.count_clients(), 1)
            disconnect_calls = modem.getNamedCalls('disconnect')
            self.assertEqual(len(disconnect_calls), 0)
        finally:
            landiallerd.time = real_time


class APITest(unittest.TestCase):

    def test_connect_return_code(self):
        """Check connect() returns True"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        self.assertEqual(api.connect('client-id-1'), True)

    def test_disconnect_return_code(self):
        """Check disconnect() returns True"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        self.assertEqual(api.disconnect('client-id-1'), True)

    def test_connect_when_connected(self):
        """Check that connect() adds a client connected"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        self.assertEqual(proxy.count_clients(), 1)
        
    def test_connect_when_not_connected(self):
        """Check that connect() adds a client when not connected"""
        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        self.assertEqual(proxy.count_clients(), 1)

    def test_disconnect_when_connected(self):
        """Check the disconnect() return code when connected"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        self.assertEqual(proxy.count_clients(), 1)
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 0)
        api.disconnect('client-id-1')
        self.assertEqual(proxy.count_clients(), 0)
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 1)

    def test_disconnect_not_connected(self):
        """Check the disconnect() return code when not connected"""
        modem = mock.Mock({'is_connected': False})
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.disconnect('client-id-1')

    def test_disconnect_all_users(self):
        """Check disconnect() can drop the connection for everybody"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        api.connect('client-id-2')
        api.connect('client-id-3')
        api.disconnect('client-id-1')
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 0)
        api.disconnect('client-id-2', all=True)
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 1)

    def test_client_refresh(self):
        """Check get_status() refreshes client"""
        modem = mock.Mock({'is_connected': True})
        modem.timer = MockTimer()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        try:
            real_time = landiallerd.time
            offset = landiallerd.ModemProxy.CLIENT_TIMEOUT - 1
            landiallerd.time = MockTime(offset)
            api.get_status('client-id-1')
            offset = landiallerd.ModemProxy.CLIENT_TIMEOUT + 1
            landiallerd.time = MockTime(offset)
            self.assertEqual(proxy.count_clients(), 1)
        finally:
            landiallerd.time = real_time

    def test_get_num_clients(self):
        """Check get_status() returns number of clients"""
        modem = mock.Mock({'is_connected': True})
        modem.timer = MockTimer()
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id-1')
        proxy.add_client('client-id-2')
        proxy.add_client('client-id-3')
        api = landiallerd.API(proxy)
        self.assertEqual(api.get_status('client-id-1')[0], 3)

    def test_get_connection_status(self):
        """Check get_status() returns connection status"""
        modem = mock.Mock({'is_connected': True})
        modem.timer = MockTimer()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        self.assertEqual(api.get_status('client-id-1')[1], xmlrpclib.True)

        modem = mock.Mock({'is_connected': False})
        modem.timer = MockTimer()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        self.assertEqual(api.get_status('client-id-1')[1], xmlrpclib.False)
        
    def test_get_time_online(self):
        """Check get_status() returns time online"""
        modem = mock.Mock()
        modem.timer = MockTimer()
        proxy = landiallerd.ModemProxy(modem)
        api = landiallerd.API(proxy)
        api.connect('client-id-1')
        self.assertEqual(api.get_status('client-id-1')[2],
                         MockTimer.elapsed_seconds)


class AutoDisconnecThreadTest(unittest.TestCase):

    def tearDown(self):
        for thread in threading.enumerate():
            if 'AutoDisconnect' in thread.getName():
                thread.join()

    def let_thread_work(self):
        time.sleep(0.01)

    def test_connection_dropped_no_users(self):
        """Check connection automatically dropped when there are no users"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id')
        try:
            real_time = landiallerd.time
            landiallerd.time = MockTime(proxy.CLIENT_TIMEOUT + 1)
            thread = landiallerd.AutoDisconnectThread(proxy)
            thread.start()
            self.let_thread_work()
            thread.finished.set()
            self.assert_(len(modem.getNamedCalls('disconnect')) > 0)
        finally:
            landiallerd.time = real_time

    def test_connection_not_dropped_with_users(self):
        """Check connection not dropped when there are active users"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id')
        thread = landiallerd.AutoDisconnectThread(proxy)
        thread.start()
        self.let_thread_work()
        thread.finished.set()
        self.assertEqual(len(modem.getNamedCalls('disconnect')), 0)

    def test_thread_runs_continually(self):
        """Check the auto disconnect thread runs continually"""
        modem = mock.Mock({'is_connected': True})
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-id')
        thread = landiallerd.AutoDisconnectThread(proxy)
        thread.start()
        self.let_thread_work()
        thread.finished.set()
        self.assert_(len(modem.getNamedCalls('is_connected')) > 0)

    def test_daemon_thread(self):
        """Check the auto disconnect thread is a daemon thread"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        thread = landiallerd.AutoDisconnectThread(proxy)
        self.assert_(thread.isDaemon())
        thread.finished.set()
        
    def test_old_clients_removed(self):
        """Check the thread causes old clients to be removed"""
        modem = mock.Mock()
        proxy = landiallerd.ModemProxy(modem)
        proxy.add_client('client-1')
        self.assertEqual(proxy.count_clients(), 1)
        try:
            real_time = landiallerd.time
            landiallerd.time = MockTime(63)
            thread = landiallerd.AutoDisconnectThread(proxy)
            thread.start()
            self.let_thread_work()
            thread.finished.set()
            self.assertEqual(proxy.count_clients(), 0)
        finally:
            landiallerd.time = real_time
        

if __name__ == '__main__':
    unittest.main()
