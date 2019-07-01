import time

from contextlib import contextmanager
from threading import Event

from .exceptions import BrowserError, PageError
from .frame import FrameManager
from .request import Request
from .response import Response


class Page:
    # TODO: don't need to pass around the proxy uri everywhere... use an authenticate_proxy method
    # or something instead
    def __init__(self, connection, target_id, browser, proxy_uri=None):
        self._proxy_uri = proxy_uri
        self._target_id = target_id
        self._connection = connection
        self._browser = browser

        self.closed = False

        self._requests_by_url = {}
        self._requests_by_id = {}
        self._frames = {}

        self._loader_id = None
        self._frame_id = None
        self._navigation_url = None
        self._navigation_event = Event()
        self._default_navigation_timeout = None

        self._viewport = None
        self._emulating_mobile = False
        self._emulating_touch = False

        self.session = self.create_devtools_session()

        self._frame_manager = FrameManager(self.session, self)

        self.session.send('Network.enable', enabled=True)
        self.session.on('Network.requestWillBeSent', self._on_request_will_be_sent)
        self.session.on('Network.responseReceived', self._on_response_recieved)

        self.session.send('Page.enable', enabled=True)
        self.session.on('Page.frameNavigated', self._on_frame_navigated)

    @property
    def browser(self):
        return self._browser

    @property
    def main_frame(self):
        return self._frame_manager._main_frame

    # Public API #

    def click(self, xpath_expression, button='left', click_count=1, delay=0):
        """Click an element on the page.

        Args:
            xpath_expression (str): The expression to search the page for. The first matching element will
                be clicked.
            button (str, optional): Mouse button to use when simulating the click ("left", "right", or "middle").
                Defaults to "left".
            click_count (int, optional): The number of times to fire the mouse event. Defaults to 1.
            delay (int, optional): The number of miliseconds to wait between pressing and releasing the mouse button.
                Defaults to 0.

        Returns:
            None.

        Raises:
            PageError: If no matching elements are found.
        """
        # TODO: Should this take xpath, css seclector, or both?
        element_list = self.xpath(xpath_expression)
        if not len(element_list):
            raise PageError('Element with xpath %s does not exist' % xpath_expression)
        element_list[0].click(button=button, click_count=click_count, delay=delay)

    def close(self):
        """Close the page."""
        if self.closed:
            return
        self.closed = True
        response = self._connection.send('Target.closeTarget', targetId=self._target_id)
        if not response['success']:
            raise BrowserError('Could not close page')

    def content(self):
        """Get the page's rendered HTML content.

        Returns:
           The rendered HTML of the current page.
        """
        return self.document._prop('documentElement').html

    def cookies(self, urls=None):
        """Return cookies for the current page, or for the given list of `urls`

        Args:
            urls: (list, optional): The urls to match when retrieving cookies. If not provided, the page's
                current url is used.

        Returns:
            A list of dictionaries with the following keys:
                - name (str)
                - value (str)
                - domain (str)
                - path (str)
                - expires (int, Unix timestamp in seconds)
                - http_only (bool)
                - secure (bool)
                - session (bool)
        """
        if urls is None:
            response = self.session.send('Network.getCookies')
        else:
            response = self.session.send('Network.getCookies', urls=urls)
        return [{
            'name': c.get('name'),
            'value': c.get('value'),
            'domain': c.get('domain'),
            'path': c.get('path'),
            'expires': c.get('expires'),
            'http_only': c.get('httpOnly'),
            'secure': c.get('secure'),
            'session': c.get('session')
        } for c in response['cookies']]

    def get_cookies_dict(self, urls=None):
        """Helper method to return as a dictionary in the format {`name`: `value`, `name`: `value`, etc.}"""
        raw_cookies = self.cookies(urls)
        return {r['name']: r['value'] for r in raw_cookies}

    def create_devtools_session(self):
        """Create a new session to send messages to the running Chrome devtools server.

        Args:
            raise_on_closed_connection (bool, optional): Whether or not raise an error if an attempt is made
                to send a message after the connection with the browser is closed. Defaults to True. Setting
                to False is useful for sessions that will process background tasks, like the RequestManager.

        Returns:
            a Session object.
        """
        return self._connection.new_session(self._target_id)

    @property
    def document(self):
        """An ElementHandle representing the current page's `document` object."""
        return self.evaluate('document')

    def evaluate(self, expression):
        """Send an expression to be evaluated in the browser's JavaScript console.

        Args:
           expression (str): The javascript expression to evaluate.

        Returns:
           The result returned by the remote code execution. Could be an int, str, bool, or None
           if the remote code returns a primitive type, or a dict describing a remote object if
           the code returns a complex type.
        """
        return self.main_frame.evaluate(expression)

    def evaluate_on_new_document(self, script):
        """Set a script to be evaluated on each new page visiti.

        Args:
            script (str): The javascript code to evaluate.

        Returns:
            None.
        """
        self.session.send('Page.addScriptToEvaluateOnNewDocument', source=script)

    # TODO: referrer is not tested
    def goto(self,
             url,
             timeout=None,
             wait_until='load',
             referrer=None):
        """Visit a url.

        Args:
            url (str): The url to visit.
            timeout (int, optional): Maximum number of seconds to wait for the navigation to finish. Defaults to 30.
            wait_until (str, optional): When to consider the navigation as having succeeded. Defaults to "load".

        Returns:
            The response recieved for the navigation request.
        """
        timeout = timeout or self._default_navigation_timeout or 30
        return self._frame_manager.navigate_frame(self._frame_manager._main_frame,
                                                  url,
                                                  timeout,
                                                  wait_until,
                                                  referrer)

    def focus(self, xpath_expression):
        """Focus an element on the page.

        Args:
            xpath_expression (str): The expression to search the page for. The first matching element will
                be focused.

        Returns:
            None.

        Raises:
            PageError: If no matching elements are found.
        """
        element_list = self.xpath(xpath_expression)
        if not len(element_list):
            raise PageError('Element with xpath %s does not exist' % xpath_expression)
        element_list[0].focus()

    def reload(self, wait_until='load', timeout=30):
        """Refresh the page.

        Args:
            wait_until (str, optional): When to consider the navigation as having succeeded. Defaults to "load".
            timeout (int, optional): Maximum number of seconds to wait for the navigation to finish. Defaults to 30.
        """
        self._navigation_event.clear()
        with self.wait_for_navigation(wait_until=wait_until, timeout=timeout):
            self.session.send('Page.reload')
        self._navigation_event.wait(timeout=3)
        return self._wait_for_response(self._navigation_url, timeout=3)

    def query_selector(self, selector):
        """Search the current page for elements matching a CSS selector.

        Args:
            selector (str): The CSS selector expression to search for.

        Returns:
            A list of ElementHandle objects representing the HTML nodes found on the page.
        """
        return self.document.querySelectorAll(selector)

    @property
    def requests(self):
        """All the requests this page has made."""
        return list(self._requests_by_url.values())

    def select(self, selector, *values):
        """Selects a list of options in a given HTML <select> element.

        Args:
            selector (str): A css selector used to locate the <select> element.
            values (str, variable length): The values to select.

        Returns:
            A list of option values that have been successfully selected.

        Raises:
            PageError: If no element matching `selector` is found.
        """
        element_list = self.query_selector(selector)
        if not len(element_list):
            raise PageError('Element at {} not found'.format(selector))
        element = element_list[0]
        return element.select(*values)

    def set_default_navigation_timeout(self, timeout):
        """Set the default timeout for page navigation events.

        Args:
            timeout (int): The new default timeout.
        """
        self._default_navigation_timeout = timeout

    def set_extra_http_headers(self, headers):
        """Define additional headers to be sent with every network request.

        Args:
            headers (dict): Additional headers to be added.

        Returns:
            None.
        """
        self._frame_manager.request_manager.set_extra_http_headers(headers)

    def set_viewport(self, viewport):
        """Set a viewport for the page to emulate. Will force page to reload if turning mobile or touch
           emulation after already having navigated to a page.

        Args:
            viewport (dict):
                - height (int)
                - width (int)
                - device_scale_factor (int, optional: defaults to 1)
                - mobile (bool, optional: defaults to False)
                - has_touch (bool, optional: defaults to False)
                - is_landscape (bool, optional: defaults to False)

        Returns:
            None.
        """
        mobile = viewport.get('mobile', False)
        has_touch = viewport.get('has_touch', False)
        if viewport.get('is_landscape'):
            screen_orientation = {'angle': 90, 'type': 'landscapePrimary'}
        else:
            screen_orientation = {'angle': 0, 'type': 'portraitPrimary'}

        self.session.send('Emulation.setDeviceMetricsOverride',
                          width=viewport.get('width'),
                          height=viewport.get('height'),
                          deviceScaleFactor=viewport.get('device_scale_factor', 1),
                          mobile=mobile,
                          screenOrientation=screen_orientation)
        self.session.send('Emulation.setTouchEmulationEnabled', enabled=has_touch)
        reload_needed = self._emulating_mobile != mobile or self._emulating_touch != has_touch
        self._emulating_mobile = mobile
        self._emulating_touch = has_touch
        self._viewport = viewport
        if self._navigation_url and reload_needed:
            self.reload()

    def type(self, xpath_expression, text, delay=0):
        """Give an element focus, then simulate a series of keyboard events.

        Args:
            xpath_expression (str): The expression to search the page for. The first matching element will
                be focused.
            text (str): The text to type. The text will be typed by sending a keypress event for each character
                in the string.
            delay (int, optional): The number of seconds to delay between each keypress. Defaults to 0.

        Returns:
            None.

        Raises:
            PageError: If no matching elements are found.
        """
        self.focus(xpath_expression)
        for char in text:
            time.sleep(delay)
            self.session.send('Input.dispatchKeyEvent', type='char', text=char)

    def url(self):
        """Return the URL of the current page."""
        response = self.session.send('Target.getTargetInfo', targetId=self._target_id)
        return response.get('targetInfo', {}).get('url')

    @contextmanager
    def wait_for_navigation(self, wait_until='load', timeout=30):
        """A context manager used to run a command and pause execution until the page completes
           a navigation. Useful, for example, for waiting for a navigation to finish after clicking
           a link on the page:

           ```
           with page.wait_for_navigation():
               page.click('*//a[@id="nav-link"]')
           ```

        Args:
            wait_until (str, optional): When to consider the navigation as having succeeded. Defaults to "load".
            timeout (int, optional): Maximum number of seconds to wait for the navigation to finish. Defaults to 30.
        """
        with self._frame_manager.wait_for_navigation(self._frame_manager._main_frame, wait_until, timeout):
            yield

    def viewport(self):
        """Returns the page's viewport."""
        return self._viewport

    def wait_for_xpath(self, xpath_expr, visible=False, hidden=False, timeout=30):
        """Pause execution until an element is present on the page.

        Args:
            xpath_expression (str): The xpath expression to wait for. When at least one matching element is
                found, waiting will end.
            visible (bool, optional): If True, don't match elements that have `display: none` or
                `visibility: hidden` CSS properties.
            timeout (int, optional): The number of seconds to wait before throwing an error.

        Returns:
            A list of elements matching the xpath expression.

        Raises:
            PageError: If no matching element is found before the given timeout.
        """
        slept = 0.0
        interval = 0.1
        element_list = []
        while slept < timeout:
            element_list = self.xpath(xpath_expr)
            if element_list:
                if visible:
                    visible_elements = [e for e in element_list if e.is_visible]
                    if len(visible_elements):
                        return visible_elements
                elif hidden:
                    hidden_elements = [e for e in element_list if not e.is_visible]
                    if len(hidden_elements):
                        return hidden_elements
                else:
                    return element_list
            time.sleep(interval)
            slept += interval
        raise PageError('Timed out waiting for element at `%s`' % xpath_expr)

    def xpath(self, expression):
        """Search the current page for elements matching an xpath expression.

        Args:
            expression (str): The xpath expression to search for.

        Returns:
            A list of ElementHandle objects representing the HTML nodes found on the page.
        """
        return self.document.xpath(expression)

    def blacklist_url_patterns(self, url_patterns):
        self._frame_manager.request_manager.blacklist_url_patterns(url_patterns)

    def blacklist_resource_types(self, *args):
        self._frame_manager.request_manager.blacklist_resource_types(*args)

    def get_responses(self, urls=None):
        responses = [request.response for request in self._requests_by_url.values() if request.response]

        if urls is None:
            return responses

        matching_responses = []
        for response in responses:
            for url in urls:
                if url in response.url:
                    matching_responses.append(response)
        return matching_responses

    # Private methods
    def _on_request_will_be_sent(self, **kwargs):
        request = Request(kwargs['request'], kwargs['requestId'])
        self._requests_by_id[request.request_id] = request
        self._requests_by_url[request.url] = request

    def _on_response_recieved(self, **kwargs):
        request_id = kwargs['requestId']
        request = self._requests_by_id.get(request_id)
        if request is not None:
            response = Response(kwargs['response'], request, self)
            request.set_response(response)

    def _on_frame_navigated(self, **kwargs):
        is_main_frame = not bool(kwargs.get('parentId'))
        if is_main_frame:
            self._frame_id = kwargs['frame']['id']
            self._navigation_url = kwargs['frame']['url']
            self._navigation_event.set()

    def _wait_for_response(self, url, timeout, force=False):
        waited = 0
        delay = 0.001
        while waited < timeout:
            if url in self._requests_by_url and self._requests_by_url[url].response:
                return self._requests_by_url[url].response
            time.sleep(delay)
            waited += delay
        if force:
            raise PageError('Timed out waiting for response; url: {}'.format(url))
