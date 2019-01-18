import json
import queue
import time

from threading import Event, Thread

import websocket
from websocket._exceptions import WebSocketConnectionClosedException

from pypuppet.exceptions import BrowserError
from pypuppet.session import Session


class Connection:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.closed = False
        self._ws = websocket.create_connection(self.endpoint, enable_multithread=True)

        self.messages = {}
        self._sessions = {}
        self.events_queue = queue.Queue()
        self.event_handlers = {}

        self._message_id = 0
        self._recv_thread = Thread(target=self._recv_loop)
        self._recv_thread.daemon = True
        self._recv_thread.start()

        self._handle_event_thread = Thread(target=self._handle_event_loop)
        self._handle_event_thread.setDaemon(True)
        self._handle_event_thread.start()

    def new_session(self, target_id):
        response = self.send('Target.attachToTarget', targetId=target_id)
        session_id = response['sessionId']
        session = Session(self, session_id)
        self._sessions[session_id] = session
        return session

    def _recv_loop(self):
        while not self.closed:
            try:
                message_raw = self._ws.recv()
                # print('recieved -- ', message_raw[:1000])
            except WebSocketConnectionClosedException:
                if self.closed:
                    continue
                else:
                    raise
            message = json.loads(message_raw)

            # Messages meant to be passed to some session
            if message.get('method') == 'Target.receivedMessageFromTarget':
                message_from_target = json.loads(message['params']['message'])
                session_id = message['params']['sessionId']
                self._sessions.get(session_id).on_message(message_from_target)

            # Responses to messages sent from this connection
            elif 'id' in message:
                if 'error' in message:
                    self.messages[message['id']]['error'] = message['error']
                else:
                    self.messages[message['id']]['result'] = message.get('result')
                self.messages[message['id']]['event'].set()

            # Events fired for this connection
            elif 'method' in message:
                self.events_queue.put(message)
        self._ws.close()

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
        return self._send(message)

    def _send(self, message):
        if 'id' not in message:
            id_ = self.message_id()
            message['id'] = id_
        event_ = Event()
        self.messages[id_] = {'event': event_}
        # print('sent -- ', json.dumps(message))
        self._ws.send(json.dumps(message))
        event_.wait()
        if 'error' in self.messages[id_]:
            # print(BrowserError(self.messages[id_]['error']))
            raise BrowserError(self.messages[id_]['error'])
        else:
            return self.messages[id_]['result']

    def _send_no_wait(self, message):
        if 'id' not in message:
            id_ = self.message_id()
            message['id'] = id_
        self._ws.send(json.dumps(message))

    def on(self, method, cb):
        self.event_handlers[method] = self.event_handlers.get(method, [])
        self.event_handlers[method].append(cb)

    def _wait_for_response(self, id_, timeout=5):
        waited = 0.0
        while waited < timeout:
            response = self.messages.pop(id_, None)
            if response is not None:
                return response
            else:
                time.sleep(0.1)
                waited += 0.1
        raise Exception('Timed out waiting for response from websocket server')

    def message_id(self):
        id_ = self._message_id
        self._message_id += 1
        return id_

    def close(self):
        self.closed = True
