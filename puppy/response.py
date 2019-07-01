class Response:
    def __init__(self, response_data, request, session):
        self._response_data = response_data
        self._session = session
        self.request = request

    @property
    def url(self):
        return self._response_data['url']

    @property
    def status(self):
        return self._response_data['status']

    @property
    def status_text(self):
        return self._response_data['statusText']

    @property
    def headers(self):
        return self._response_data['headers']

    @property
    def mime_type(self):
        return self._response_data['mimeType']

    def text(self):
        response = self._session.send('Network.getResponseBody', requestId=self.request.request_id)
        return response.get('body')
