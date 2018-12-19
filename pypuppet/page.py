import json

from threading import Event
from urllib.parse import urlparse

from pypuppet.connection import Connection
from pypuppet.element import Element


class Page:
    LIFECYCLE_EVENTS = [
        'DOMContentLoaded',
        'firstContentfulPaint',
        'firstImagePaint',
        'firstMeaningfulPaint',
        'firstMeaningfulPaintCandidate',
        'firstPaint',
        'firstTextPaint',
        'init',
        'load',
        'networkAlmostIdle',
        'networkIdle'
    ]

    def __init__(self, websocket_endpoint, proxy_uri=None):
        self.proxy_uri = proxy_uri
        self.websocket_enpoint = websocket_endpoint
        self._connections = []
        self._lifecycle_events = {}
        self.responses = []

        self.connection = self.create_devtools_connection()
        self.connection.send('Network.enable', enabled=True)

        # self.connection.send('Runtime.enable')
        # self.connection.on('Runtime.executionContextCreated', lambda **e: print ('created -- ', e))

        self.lifecycle_watcher = self.create_devtools_connection()
        self.lifecycle_watcher.send('Page.enable')
        self.lifecycle_watcher.send('Page.setLifecycleEventsEnabled', enabled=True)
        self.lifecycle_watcher.on('Page.lifecycleEvent', self._on_lifecycle_event)

        self.request_manager = self.create_devtools_connection()
        self.request_manager.send('Network.setRequestInterception', patterns=[{'urlPattern': '*'}])
        self.request_manager.on('Network.requestIntercepted', self._on_request_intercepted)

    def create_devtools_connection(self):
        connection = Connection(self.websocket_enpoint)
        self._connections.append(connection)
        return connection

    def _on_lifecycle_event(self, loaderId, name, **kwargs):
        self._lifecycle_events[loaderId] = self._lifecycle_events.get(loaderId, {e: Event() for e in self.LIFECYCLE_EVENTS})
        self._lifecycle_events[loaderId][name].set()

    def _on_request_intercepted(self, **kwargs):
        interception_id = kwargs.get('interceptionId')
        if kwargs.get('authChallenge'):
            parsed_proxy_uri = urlparse(self.proxy_uri)
            username = parsed_proxy_uri.username
            password = parsed_proxy_uri.password
            self.request_manager.send('Network.continueInterceptedRequest',
                                      interceptionId=interception_id,
                                      authChallengeResponse={
                                          'response': 'ProvideCredentials',
                                          'username': username,
                                          'password': password
                                      })
            return
        self.request_manager.send('Network.continueInterceptedRequest', interceptionId=interception_id)

    def _wait_for_lifecycle_event(self, loader_id, name, timeout):
        # TODO: Have to set up these events in both places cause we don't know which will happen first.
        # If we can out the loaderId earlier we can have this already set up
        self._lifecycle_events[loader_id] = self._lifecycle_events.get(loader_id, {e: Event() for e in self.LIFECYCLE_EVENTS})
        self._lifecycle_events[loader_id][name].wait(timeout)
        self._lifecycle_events = {}

    def goto(self, url, wait_until='load', timeout=30):
        res = self.connection.send('Page.navigate', url=url)
        self._wait_for_lifecycle_event(res['loaderId'], wait_until, timeout)

    def content(self):
        return self.document._prop('documentElement').html

    def evaluate(self, expression):
        response = self.session.send('Runtime.evaluate', expression=expression)
        if 'result' not in response:
            # TODO: Maybe sometimes there is expected to be no result?
            raise Exception('no result in {}'.format(json.dumps(response)))
        if 'value' in response['result']:
            return response['result']['value']
        else:
            return response['result']

    @property
    def document(self):
        response = self.evaluate('document')
        return Element(response['objectId'], response['description'], self)

    def xpath(self, expression):
        return self.document.xpath(expression)

    def click(self, xpath_expression):
        element_list = self.xpath(xpath_expression)
        # TODO: Raise error if element is not clickable.
        if not len(element_list):
            raise Exception(f'Element with xpath {xpath_expression} does not exist')
        element_list[0].click()
    def track_network_responses(self):
        self.connection.send('Network.enable', enabled=True)

        def _on_response_received(**kwargs):
            response = kwargs['response']
            res = self.connection.send('Network.getResponseBody', requestId=kwargs['requestId'])
            self.responses.append({
                'url': response['url'],
                'status': response['status'],
                'body': res['body']
            })

        self.connection.on('Network.responseReceived', _on_response_received)

    def close(self):
        for connection in self._connections:
            connection.close()
