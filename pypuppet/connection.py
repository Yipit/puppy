import json
import queue
import time

from concurrent.futures import ThreadPoolExecutor
from threading import Thread

import websocket


class Connection:
    def __init__(self, endpoint):
        self.endpoint = endpoint
        self.closed = False
        self._ws = websocket.create_connection(self.endpoint, enable_multithread=True)

        self.messages = {}
        self.events_queue = queue.Queue()
        self.events_threadpool = ThreadPoolExecutor(max_workers=5)
        self.event_handlers = {}

        self._message_id = 0
        self._recv_thread = Thread(target=self._recv_loop)
        self._recv_thread.daemon = True
        self._recv_thread.start()

        self._handle_event_thread = Thread(target=self._handle_event_loop)
        self._handle_event_thread.setDaemon(True)
        self._handle_event_thread.start()

    # TODO: do real error handling
    def _recv_loop(self):
        while not self.closed:
            message_raw = self._ws.recv()
            # print('message -- ', message_raw)
            message = json.loads(message_raw)
            if 'id' in message:
                if 'error' in message:
                    self.messages[message['id']] = {'error': 'ERROR'}
                    print('Error returned from websocket server: {}'.format(message['error']['message']))
                else:
                    result = message.get('result')
                self.messages[message['id']] = result
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
                    try:
                        self.events_threadpool.submit(cb, **event['params'])
                    except Exception as e:
                        print('error in event handler: {}'.format(e))

            # self.events_queue.task_done()

    def send(self, method, **kwargs):
        id_ = self._send({'method': method, 'params': kwargs})
        return self._wait_for_response(id_)

    def on(self, method, cb):
        self.event_handlers[method] = self.event_handlers.get(method, [])
        self.event_handlers[method].append(cb)

    def _send(self, message):
        if 'id' not in message:
            message['id'] = self.message_id()
        self._ws.send(json.dumps(message))
        # print('sent -- ', json.dumps(message))
        return message['id']

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
