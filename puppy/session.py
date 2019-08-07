from six.moves import queue
from threading import Thread

from . import settings
from .exceptions import BrowserError


class Session:
    def __init__(self, connection, session_id):
        self._connection = connection
        self._session_id = session_id

        self.messages = {}
        self.events_queue = queue.Queue()
        self.event_handlers = {}

        self._message_id = 0

        self._handle_event_thread = Thread(target=self._handle_event_loop)
        self._handle_event_thread.setDaemon(True)
        self._handle_event_thread.start()

    def on_message(self, message):
        if 'method' in message:
            self.events_queue.put(message)

    def _handle_event_loop(self):
        while self._connection and self._connection.connected:
            try:
                event = self.events_queue.get(timeout=1)
            except queue.Empty:
                continue

            if event['method'] in self.event_handlers:
                for cb in self.event_handlers[event['method']]:
                    cb(**event['params'])

            self.events_queue.task_done()

    def send(self, method, **kwargs):
        return self._connection.send(method, self._session_id, **kwargs)

    def on(self, method, cb):
        self.event_handlers[method] = self.event_handlers.get(method, [])
        self.event_handlers[method].append(cb)

    def message_id(self):
        id_ = self._message_id
        self._message_id += 1
        return id_

    def close(self):
        for message in self.messages.values():
            if not message['event'].is_set():
                message['result'] = None
                message['event'].set()
        self.event_handlers.clear()
