import time

from contextlib import contextmanager

from .exceptions import BrowserError, PageError
from .js_object import Element
from .lifecycle_watcher import LifecycleWatcher
from .request import Request
from .request_manager import RequestManager
from .response import Response


class Page:
    def __init__(self, connection, target_id, proxy_uri=None):
        self._proxy_uri = proxy_uri
        self._target_id = target_id
        self._connection = connection
        self._request_manager = RequestManager(self, self._proxy_uri)

        self.closed = False

        self._requests_by_url = {}
        self._requests_by_id = {}
        self._frames = {}

        self._loader_id = None
        self._frame_id = None
        self._navigation_url = None

        self.session = self.create_devtools_session()

        self.session.send('Network.enable', enabled=True)
        self.session.on('Network.requestWillBeSent', self._on_request_will_be_sent)
        self.session.on('Network.responseReceived', self._on_response_recieved)

        self.session.send('Page.enable', enabled=True)
        self.session.send('Page.setLifecycleEventsEnabled', enabled=True)
        self.session.on('Page.lifecycleEvent', self._on_lifecycle_event)

        self.session.on('Page.frameNavigated', self._on_frame_navigated)

    # Public API #

    def click(self, xpath_expression):
        """Click an element on the page.

        Args:
            xpath_expression (str): The expression to search the page for. The first matching element will
                be clicked.

        Returns:
            None.

        Raises:
            PageError: If no matching elements are found.
        """
        # TODO: Should this take xpath, css seclector, or both?
        element_list = self.xpath(xpath_expression)
        # TODO: Can we check if the element is clickable?
        if not len(element_list):
            raise PageError('Element with xpath %s does not exist' % xpath_expression)
        element_list[0].click()

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

    def create_devtools_session(self):
        """Create a new session to send messages to the running Chrome devtools server."""
        return self._connection.new_session(self._target_id)

    @property
    def document(self):
        """An Element representing the current page's `document` object."""
        response = self.evaluate('document')
        return Element(response['objectId'], response['description'], self)

    def evaluate(self, expression):
        """Send an expression to be evaluated in the browser's JavaScript console.

        Args:
           expression (str): The javascript expression to evaluate.

        Returns:
           The result returned by the remote code execution. Could be an int, str, bool, or None
           if the remote code returns a primitive type, or a dict describing a remote object if
           the code returns a complex type.
        """
        response = self.session.send('Runtime.evaluate', expression=expression)
        if 'value' in response['result']:
            return response['result']['value']
        else:
            return response['result']

    def evaluate_on_new_document(self, script):
        """Set a script to be evaluated on each new page visiti.

        Args:
            script (str): The javascript code to evaluate.

        Returns:
            None.
        """
        self.session.send('Page.addScriptToEvaluateOnNewDocument', source=script)

    # TODO: implement referer
    def goto(self,
             url,
             timeout=30,
             wait_until='load'):
        """Visit a url.

        Args:
            url (str): The url to visit.
            timeout (int, optional): Maximum number of seconds to wait for the navigation to finish. Defaults to 30.
            wait_until (str, optional): When to consider the navigation as having succeeded. Defaults to "load".

        Returns:
            The response recieved for the navigation request.
        """
        lifecyle_watcher = LifecycleWatcher(self, wait_until)
        self.session.send('Page.navigate', url=url)
        lifecyle_watcher.wait(timeout)
        if self._navigation_url in self._requests_by_url:
            return self._requests_by_url[self._navigation_url].response

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

    def reload(self):
        """Refresh the page."""
        with self.wait_for_navigation(wait_until='load'):
            self.session.send('Page.reload')

    @property
    def requests(self):
        """All the requests this page has made."""
        return list(self._requests_by_url.values())

    def select(self, selector):
        """Search the current page for elements matching a CSS selector.

        Args:
            selector (str): The CSS selector expression to search for.

        Returns:
            A list of Element objects representing the HTML nodes found on the page.
        """
        return self.document.querySelectorAll(selector)

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
        lifecycle_watcher = LifecycleWatcher(self, wait_until, False)
        yield
        lifecycle_watcher.wait(timeout)

    def wait_for_xpath(self, xpath_expr, visible=False, timeout=30):
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
            A list of Element objects representing the HTML nodes found on the page.
        """
        return self.document.xpath(expression)

    def blacklist_url_patterns(self, *args):
        self._request_manager.blacklist_url_patterns(*args)

    def blacklist_resource_types(self, *args):
        self._request_manager.blacklist_resource_types(*args)

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

    @property
    def loader_id(self):
        return self._loader_id

    def _on_lifecycle_event(self, **kwargs):
        if kwargs['name'] == 'init':
            self._loader_id = kwargs['loaderId']

    def _on_frame_navigated(self, **kwargs):
        is_main_frame = not bool(kwargs.get('parentId'))
        if is_main_frame:
            self._frame_id = kwargs['frame']['id']
            self._navigation_url = kwargs['frame']['url']
