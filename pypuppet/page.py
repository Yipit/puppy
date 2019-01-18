import json

from pypuppet.js_object import Element
from pypuppet.lifecycle_watcher import LifecycleWatcher
from pypuppet.request_manager import RequestManager


class Page:
    def __init__(self, connection, target_id, proxy_uri=None):
        self._proxy_uri = proxy_uri
        self._target_id = target_id
        self._connection = connection
        self._lifecycle_watcher = LifecycleWatcher(self)
        self._request_manager = RequestManager(self, self._proxy_uri)

        self.responses = []
        self.closed = False

        self.session = self.create_devtools_session()
        self.session.send('Network.enable', enabled=True)

    # Public API #
    # TODO: Documentation

    def goto(self, url, wait_until='load', timeout=30):
        if wait_until not in LifecycleWatcher.LIFECYCLE_EVENTS:
            raise Exception('Invalid wait_until')
        res = self.session.send('Page.navigate', url=url)
        self._lifecycle_watcher.wait_for_event(res['loaderId'], wait_until, timeout)

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
        self.session.send('Network.enable', enabled=True)

        def _on_response_received(**kwargs):
            response = kwargs['response']
            try:
                res = self.session.send('Network.getResponseBody', requestId=kwargs['requestId'])
                body = res['body']
            except Exception:
                body = None
            self.responses.append({
                'url': response['url'],
                'status': response['status'],
                'body': body
            })

        self.session.on('Network.responseReceived', _on_response_received)

    def create_devtools_session(self):
        return self._connection.new_session(self._target_id)

    def close(self):
        if self.closed:
            return
        self.closed = True
        response = self._connection.send('Target.closeTarget', targetId=self._target_id)
        if not response['success']:
            raise Exception('Could not close page')

    def blacklist_url_patterns(self, *args):
        self._request_manager.blacklist_url_patterns(*args)

    def blacklist_resource_types(self, *args):
        self._request_manager.blacklist_resource_types(*args)
