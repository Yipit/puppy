import json
import logging

from six.moves import queue
from threading import Event, Thread

import websocket
from websocket._exceptions import WebSocketConnectionClosedException

from . import settings
from .exceptions import BrowserError
from .session import Session


logger = logging.getLogger(__name__)


class Connection:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.connected = True
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

    @property
    def ws(self):
        return self._ws

    def new_session(self, target_id):
        response = self.send('Target.attachToTarget', targetId=target_id, flatten=True)
        return self._sessions.get(response['sessionId'])

    def _recv_loop(self):
        while self.connected:
            try:
                message_raw = self._ws.recv()
                logger.debug('RECV - %s' % message_raw[:1000])
            # Will happen when this loop is still running after we close the browser.
            except WebSocketConnectionClosedException as e:
                logger.debug(e)
                continue
            message = json.loads(message_raw)

            if message.get('method') == 'Target.attachedToTarget':
                session_id = message['params']['sessionId']
                self._sessions[session_id] = Session(self, session_id)

            if 'sessionId' in message:
                self._sessions.get(message['sessionId']).on_message(message)

            # Messages meant to be passed to some session
            if message.get('method') == 'Target.receivedMessageFromTarget':
                message_from_target = json.loads(message['params']['message'])
                session_id = message['params']['sessionId']
                self._sessions.get(session_id).on_message(message_from_target)

            # Responses to messages sent from this connection
            elif 'id' in message:
                sent_msg = self.messages[message['id']]
                if 'error' in message:
                    sent_msg.set_response({'error': message['error']})
                else:
                    sent_msg.set_response({'result': message.get('result')})

            # Events fired for this connection
            elif 'method' in message:
                self.events_queue.put(message)

    def _handle_event_loop(self):
        while self.connected:
            try:
                event = self.events_queue.get(timeout=1)
            except queue.Empty:
                continue

            if event['method'] in self.event_handlers:
                for cb in self.event_handlers[event['method']]:
                    cb(**event['params'])

            self.events_queue.task_done()

    def send(self, method, session_id=None, **kwargs):
        kwargs = {k: v for k, v in kwargs.items() if v is not None}
        message_dict = {'method': method, 'params': kwargs}
        sent_msg = Message(message_dict, session_id, self)
        sent_msg.send()
        response = sent_msg.get_response()

        if method == 'Browser.close':
            self._on_closed()

        if 'error' in response:
            raise BrowserError(response['error'])
        else:
            return response['result']

    def raw_send(self, message_dict):
        message = Message(message_dict, self)
        message.send()
        return message

    def on(self, method, cb):
        self.event_handlers[method] = self.event_handlers.get(method, [])
        self.event_handlers[method].append(cb)

    def next_message_id(self):
        id_ = self._message_id
        self._message_id += 1
        return id_

    def _on_closed(self):
        self.connected = False

        for message in self.messages.values():
            if not message._response_event.is_set():
                message.set_response({'result': None})

        for session in self._sessions.values():
            session.close()


class Message:
    def __init__(self, message_dict, session_id, connection):
        self._connection = connection
        self._session_id = session_id
        self._message_dict = message_dict
        self._id = self._message_dict.pop('id', None)
        if self._id is None:
            self._id = self._connection.next_message_id()
        self._response_event = Event()
        self._response = None
        self._connection.messages[self._id] = self

    @property
    def id(self):
        return self._id

    def send(self):
        self._message_dict['id'] = self._id
        if self._session_id:
            self._message_dict['sessionId'] = self._session_id
        logger.debug('SEND - %s' % json.dumps(self._message_dict))

        # if the WS connection is closed and we didn't intentional close this connection
        if not self._connection.ws.connected:
            raise BrowserError('Connection with browser is closed')

        self._connection.ws.send(json.dumps(self._message_dict))

    def get_response(self):
        if not self._response_event.wait(timeout=settings.MESSAGE_TIMEOUT):
            raise BrowserError('Timed out waiting for response from browser')
        return self._response

    def set_response(self, response):
        self._response_event.set()
        self._response = response
