from threading import Thread
from dbus.mainloop.glib import DBusGMainLoop
import dbus.mainloop.glib
from gi.repository import GLib
import dbus
import re
from drop_queue import DropQueue

class PipewireFrameGenerator(Thread):
    loop = None
    bus = None
    portal = None
    session = None

    request_iface = 'org.freedesktop.portal.Request'
    screen_cast_iface = 'org.freedesktop.portal.ScreenCast'

    request_token = 0
    session_token = 0
    sender_name = None

    def __init__(self, settings: dict, buf: DropQueue):
        super().__init__()
        self.loop = DBusGMainLoop()
        dbus.set_default_main_loop(self.loop)
        self.framebuf = buf
        self.settings = settings
        self.bus = dbus.SessionBus()
        self.sender_name = re.sub(r'\.', r'_', self.bus.get_unique_name()[1:])

    def path_request(self):
        self.request_token = self.request_token + 1
        token = 'u%d'%self.request_token
        path = '/org/freedesktop/portal/desktop/request/%s/%s'%(self.sender_name, token)
        return (path, token)

    def session_request(self):
        self.session_token = self.session_token + 1
        token = 'u%d'%self.session_token
        path = '/org/freedesktop/portal/desktop/session/%s/%s'%(self.sender_name, token)
        return (path, token)

    def screen_cast_call(self, method, callback, *args, options={}):
        (request_path, request_token) = self.path_request()
        self.bus.add_signal_receiver(callback,
                                    'Response',
                                    self.request_iface,
                                    'org.freedesktop.portal.Desktop',
                                    request_path)
        # options['handle_token'] = request_token
        if args != ():
            method(args[0], options, dbus_interface=self.screen_cast_iface)
        else:
            method(options, dbus_interface=self.screen_cast_iface)
        # method(*(args + (options, )),
        #    dbus_interface=self.screen_cast_iface)

    def open_window_fd(self):
        fd: dbus.UnixFd = self.portal.OpenPipeWireRemote({}, dbus_interface="org.freedesktop.portal.ScreenCast")
        fd = fd.take()

    def on_window_capture_started(self, response, results) -> bool:
        print("response")
        if response != 0:
            print("ERROR!")
            print(results)
            return False

        self.open_window_fd()
        return True

    def on_window_selected(self, response, results) -> bool:
        print("response")
        if response != 0:
            print("ERROR!")
            print(results)
            return False

        self.screen_cast_call(self.portal.Start, self.on_window_capture_started, self.session, '')
        return True

    def on_session_started(self, response, results) -> bool:
        print("response")
        if response != 0:
            print("ERROR!")
            print(results)
            return False
        
        self.session = results['session_handle']
        options = {
            "multiple": False,
            "types": dbus.UInt32(1)
        }
        self.screen_cast_call(self.portal.SelectSources, self.on_window_selected, self.session, options=options)
        return True

    def request_window(self):
        self.portal = self.bus.get_object("org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop")

        (request_path, request_token) = self.path_request()
        self.bus.add_signal_receiver(handler_function=self.on_window_capture_started,
                                signal_name="Response",
                                dbus_interface=self.request_iface,
                                bus_name="org.freedesktop.portal.Desktop",
                                path=request_path)

        self.screen_cast_call(self.portal.ScreenCast, self.on_window_capture_started)
    
    def request_session(self):
        self.portal = self.bus.get_object("org.freedesktop.portal.Desktop",
            "/org/freedesktop/portal/desktop")

        (session_path, session_token) = self.session_request()
        self.bus.add_signal_receiver(handler_function=self.on_session_started,
                                signal_name="Response",
                                dbus_interface=self.request_iface,
                                bus_name="org.freedesktop.portal.Desktop",
                                path=session_path)

        options = {
            'session_handle_token': session_token
        }
        self.screen_cast_call(self.portal.CreateSession, self.on_session_started, options=options)

    def run(self):
        self.request_session()
        GLib.MainLoop().run()