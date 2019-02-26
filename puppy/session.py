import json
import queue

from threading import Event, Thread

from .exceptions import BrowserError


class Session:
    def __init__(self, connection, session_id):
        self._connection = connection
        self._session_id = session_id
        self.closed = False

        self.messages = {}
        self.events_queue = queue.Queue()
        self.event_handlers = {}

        self._message_id = 0

        self._handle_event_thread = Thread(target=self._handle_event_loop)
        self._handle_event_thread.setDaemon(True)
        self._handle_event_thread.start()

    def on_message(self, message):
        if 'id' in message:
            if 'error' in message:
                self.messages[message['id']]['error'] = message['error']
            else:
                self.messages[message['id']]['result'] = message.get('result')
            self.messages[message['id']]['event'].set()
        elif 'method' in message:
            self.events_queue.put(message)

    def _handle_event_loop(self):
        while not self.closed:
            try:
                event = self.events_queue.get(timeout=1)
            except queue.Empty:
                continue

            if event['method'] in self.event_handlers:
                for cb in self.event_handlers[event['method']]:
                    cb(**event['params'])

            self.events_queue.task_done()

    def send(self, method, **kwargs):
        message = {'method': method, 'params': kwargs}
        id_ = self.message_id()
        message['id'] = id_
        event_ = Event()
        self.messages[id_] = {'event': event_}
        self._connection.send('Target.sendMessageToTarget',
                              message=json.dumps(message),
                              sessionId=self._session_id)
        event_.wait()
        if 'error' in self.messages[id_]:
            # print(BrowserError(self.messages[id_]['error']))
            raise BrowserError(self.messages[id_]['error'])
        else:
            return self.messages[id_]['result']

    def on(self, method, cb):
        self.event_handlers[method] = self.event_handlers.get(method, [])
        self.event_handlers[method].append(cb)

    def message_id(self):
        id_ = self._message_id
        self._message_id += 1
        return id_

    def close(self):
        self.closed = True
