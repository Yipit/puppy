from six.moves.urllib.parse import urlparse


class RequestManager:
    def __init__(self, page, proxy_uri):
        self._page = page
        self._proxy_uri = proxy_uri
        if self._proxy_uri:
            parsed_proxy_uri = urlparse(self._proxy_uri)
            self._proxy_username = parsed_proxy_uri.username
            self._proxy_password = parsed_proxy_uri.password
        else:
            self._proxy_username = None
            self._proxy_password = None
        self._blacklisted_url_patterns = []
        self._blacklisted_resource_types = []
        self._session = self._page.create_devtools_session()
        self._session.send('Network.setRequestInterception', patterns=[{'urlPattern': '*'}])
        self._session.on('Network.requestIntercepted', self._on_request_intercepted)

    def blacklist_urls(self, *args):
        self._blacklisted_url_patterns.extend(args)

    def blacklist_resource_types(self, *args):
        self._blacklisted_resource_types.extend(args)

    def _on_request_intercepted(self, **kwargs):
        interception_id = kwargs.get('interceptionId')
        if kwargs.get('authChallenge'):
            self._session.send('Network.continueInterceptedRequest',
                               interceptionId=interception_id,
                               authChallengeResponse={
                                   'response': 'ProvideCredentials',
                                   'username': self._proxy_username,
                                   'password': self._proxy_password
                               })
            return

        if kwargs.get('resourceType') in self._blacklisted_resource_types:
            self._session.send('Network.continueInterceptedRequest', interceptionId=interception_id, errorReason='Aborted')
            return

        for url_pattern in self._blacklisted_url_patterns:
            if url_pattern in kwargs.get('request', {}).get('url', ''):
                self._session.send('Network.continueInterceptedRequest', interceptionId=interception_id, errorReason='Aborted')
                return

        self._session.send('Network.continueInterceptedRequest', interceptionId=interception_id)
