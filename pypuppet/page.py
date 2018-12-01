import time
from urllib.parse import urlparse

from pypuppet.connection import Connection


class Page:
    def __init__(self, websocket_endpoint, proxy_uri=None):
        self.proxy_uri = proxy_uri
        self.connection = Connection(websocket_endpoint)
        self.connection.send('Page.enable')
        self.connection.send('Page.setLifecycleEventsEnabled', enabled=True)
        self._lifecycle_events = {}
        self.connection.on('Page.lifecycleEvent', self._add_lifecycle_event)
        self.responses = []

        self.connection.send('Network.enable', enabled=True)
        self.connection.send('Network.setRequestInterception', patterns=[{'urlPattern': '*'}])

        def _on_request_intercepted(**kwargs):
            interception_id = kwargs.get('interceptionId')
            if kwargs.get('authChallenge'):
                parsed_proxy_uri = urlparse(proxy_uri)
                username = parsed_proxy_uri.username
                password = parsed_proxy_uri.password
                self.connection.send('Network.continueInterceptedRequest',
                                     interceptionId=interception_id,
                                     authChallengeResponse={
                                         'response': 'ProvideCredentials',
                                         'username': username,
                                         'password': password
                                     })
                return

            self.connection.send('Network.continueInterceptedRequest', interceptionId=interception_id)

        self.connection.on('Network.requestIntercepted', _on_request_intercepted)

    def _add_lifecycle_event(self, loaderId, name, **kwargs):
        self._lifecycle_events[loaderId] = self._lifecycle_events.get(loaderId, [])
        self._lifecycle_events[loaderId].append(name)

    # TODO: these get stuck behind other events and block the main thread. use a separate queue?
    def _wait_for_lifecycle_event(self, loader_id, name, timeout=100):
        # TODO: make sure name is a valid event
        waited = 0.0
        while waited < timeout:
            if name in self._lifecycle_events.get(loader_id, []):
                self._lifecycle_events = {}
                return
            time.sleep(0.1)
            waited += 0.1
        raise Exception('Timed out waiting for lifecycle event')

    def authenticate(self):
        pass

    def goto(self, url, wait_until='load'):
        res = self.connection.send('Page.navigate', url=url)
        self._wait_for_lifecycle_event(res['loaderId'], wait_until)

    def content(self):
        document_element_res = self.connection.send('Runtime.evaluate', expression='document.documentElement')
        if document_element_res['result']['type'] == 'object':
            res = self.connection.send('Runtime.evaluate', expression='document.documentElement.outerHTML')
            return res['result']['value']
        else:
            return None

    # TODO: any way to speed this up?
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
