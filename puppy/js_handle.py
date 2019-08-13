import time

from .exceptions import BrowserError, PageError


class JSHandle:
    '''An interface for interacting with javascript objects in browser runtime'''

    def __init__(self, object_id, description, execution_context, session):
        self._object_id = object_id
        self._description = description
        self._execution_context = execution_context
        self._session = session

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self._description)

    @property
    def description(self):
        return self._description

    @property
    def object_id(self):
        return self._object_id

    def get_property(self, property_name):
        return self._prop(property_name)

    def get_properties(self):
        response = self._session.send('Runtime.getProperties', objectId=self.object_id, ownProperties=True)
        result = {}
        for prop in response['result']:
            prop_name = prop['name']
            prop_value = prop['value']
            result[prop_name] = self._get_return_value(prop_value)
        return result

    def _method(self, method, *args):
        function = '(element, ...args) => element.{method}(...args)'.format(method=method)
        args = [self] + list(args)
        return self._remote_call(function, args)

    def _prop(self, prop):
        function = '(element) => element.{prop}'.format(prop=prop)
        args = [self]
        return self._remote_call(function, args)

    def _remote_call(self, function, args, return_by_value=False):
        response = self._execution_context.call_function_on(function, args, return_by_value)
        # If the remote call raised and exception, raise it here
        if 'exceptionDetails' in response:
            raise PageError('Exception raised in remote javascript call: "{}"'
                            .format(response['exceptionDetails']['exception']['description']))

        return self._get_return_value(response['result'])

    def _get_return_value(self, protocol_result):
        # If the result is a primitive value return that
        if 'value' in protocol_result:
            return protocol_result['value']
        # Or return an Element if it's a DOM node, or a generic object
        elif protocol_result['type'] == 'object':
            if protocol_result.get('subtype') == 'node':
                return ElementHandle(protocol_result['objectId'],
                                     protocol_result['description'],
                                     self._execution_context,
                                     self._session)
            else:
                return JSHandle(protocol_result['objectId'],
                                protocol_result['description'],
                                self._execution_context,
                                self._session)
        elif protocol_result['type'] == 'undefined':
            return None
        else:
            raise BrowserError('Unknown response from remote javascipt call')  # TODO: Find out if this can happen


class ElementHandle(JSHandle):
    '''A special kind of JSHandle with extra helper methods'''

    ORDERED_NODE_SNAPSHOT_TYPE = 7  # TODO: can get this code from JS?

    def xpath(self, expression):
        document = self._execution_context.evaluate('document')
        xpath_result = document._method('evaluate', expression, self, None, self.ORDERED_NODE_SNAPSHOT_TYPE)
        element_count = xpath_result._prop('snapshotLength')
        results = []
        for i in range(element_count):
            results.append(xpath_result._method('snapshotItem', i))
        return results

    def querySelector(self, selector):
        return self._method('querySelector', selector)

    def querySelectorAll(self, selector):
        query_selector_all_result = self._method('querySelectorAll', selector)
        length = query_selector_all_result._prop('length')
        results = []
        for i in range(length):
            results.append(query_selector_all_result._method('item', i))
        return results

    @property
    def html(self):
        return self._prop('outerHTML')

    @property
    def text(self):
        return self._prop('textContent')

    def focus(self):
        return self._method('focus')

    def _scroll_into_view_if_needed(self):
        # This is how puppeteer does it
        self._remote_call(
            '''
            async (element) => {
                if (!element.isConnected) {
                    throw new Error('Node is detached from document')
                }
                const visibleRatio = await new Promise(resolve => {
                    const observer = new IntersectionObserver(entries => {
                        resolve(entries[0].intersectionRatio)
                        observer.disconnect()
                    })
                    observer.observe(element)
                })
                if (visibleRatio != 1.0) {
                    element.scrollIntoView({block: 'center', inline: 'center', behavior: 'instant'})
                }
                return false
            }
            ''',
            [self]
        )

    def _get_clickable_point(self):
        '''Loop through the list of quads to find one with enough area to be clickable; raise an error if none are.'''
        quads = self._session.send('DOM.getContentQuads', objectId=self._object_id)['quads']
        for quad in quads:
            points = [
                {'x': quad[0], 'y': quad[1]},
                {'x': quad[2], 'y': quad[3]},
                {'x': quad[4], 'y': quad[5]},
                {'x': quad[6], 'y': quad[7]},
            ]
            if self._compute_quad_area(points) > 1:
                x = sum([point['x'] for point in points]) / 4
                y = sum([point['y'] for point in points]) / 4
                return x, y
        raise PageError('Element is not clickable')

    def _compute_quad_area(self, points):
        '''Estimate area based on set of points. see https://github.com/GoogleChrome/puppeteer/blob/
           084cf021195dbe125d26496796f590a4300fb844/lib/JSHandle.js#L503-L513'''
        area = 0
        for i in range(len(points)):
            p1 = points[i]
            p2 = points[(i + 1) % len(points)]
            area += (p1['x'] * p2['y'] - p2['x'] * p1['y']) / 2
        return abs(area)

    def click(self, button='left', click_count=1, delay=0):
        self._scroll_into_view_if_needed()
        x, y = self._get_clickable_point()
        self._session.send('Input.dispatchMouseEvent', type='mouseMoved', x=x, y=y)
        self._session.send('Input.dispatchMouseEvent',
                           type='mousePressed',
                           x=x,
                           y=y,
                           button=button,
                           clickCount=click_count)
        time.sleep(delay / 1000)
        self._session.send('Input.dispatchMouseEvent',
                           type='mouseReleased',
                           x=x,
                           y=y,
                           button=button,
                           clickCount=click_count)

    @property
    def is_visible(self):
        style = self._remote_call('window.getComputedStyle', [self])
        visibility = style._prop('visibility')
        has_visible_bounding_box = self._remote_call(
            '''
            (element) => {
                const rect = element.getBoundingClientRect();
                return !!(rect.top || rect.bottom || rect.width || rect.height);
            }
            ''',
            [self]
        )
        return visibility != 'hidden' and has_visible_bounding_box

    def select(self, *values):
        script = '''
            (element, values) => {
                const options = Array.from(element.options);
                element.value = undefined;
                for (const option of element.options) {
                    option.selected = values.includes(option.value);
                    if (option.selected && !element.multiple) {
                        break;
                    }
                }
                element.dispatchEvent(new Event('input', {'bubbles': true}))
                element.dispatchEvent(new Event('change', {'bubbles': true}))
                return options.filter(option => option.selected).map(option => option.value)
            }
        '''
        res = self._remote_call(script, [self, values], return_by_value=True)
        return res
