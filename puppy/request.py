class Request:
    def __init__(self, request_data, request_id):
        self._request_data = request_data
        self._response = None
        self._request_id = request_id

    @property
    def request_id(self):
        return self._request_id

    @property
    def headers(self):
        return self._request_data.get('headers')

    @property
    def method(self):
        return self._request_data.get('method')

    @property
    def post_data(self):
        return self._request_data.get('postData')

    @property
    def response(self):
        return self._response

    @property
    def url(self):
        return self._request_data.get('url')

    def set_response(self, response):
        self._response = response
