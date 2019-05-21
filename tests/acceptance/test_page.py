import pytest
import pytest_httpbin

from contextlib import contextmanager
from envelop import Environment
from unittest import TestCase

from puppy import Browser
from puppy.exceptions import PageError
from puppy.js_object import JSObject, Element


env = Environment()


@pytest_httpbin.use_class_based_httpbin
class PageCase(TestCase):
    @contextmanager
    def _page_context(self, headless=True):
        browser_args = ['--no-sandbox'] if env.get_bool('NO_SANDBOX_CHROME') else None
        try:
            browser = Browser(headless=headless, args=browser_args)
            yield browser.page
        finally:
            browser.close()

    def test_goto(self):
        # TODO: seems response here is often None, could be a problem with goto
        with self._page_context() as page:
            # When I call page.goto...
            response = page.goto(self.httpbin + '/status/200')
            # ... I get a response object with the correct status code
            self.assertEqual(response.status, 200)
            # ... and the correct status text
            self.assertEqual(response.status_text, 'OK')
            # ... and the correct url
            self.assertEqual(response.url, self.httpbin + '/status/200')

    def test_content(self):
        with self._page_context() as page:
            page.goto(self.httpbin + '/html')
            content = page.content()
            self.assertIn('<h1>Herman Melville - Moby-Dick</h1>', content)  # good enough?

    def test_evaluate(self):
        with self._page_context() as page:
            # When I evaluate a javascipt expression that returns a primitive...
            result = page.evaluate('2 + 2')
            # ... I get a Python primitive back
            self.assertEqual(result, 4)

            # And when the expression returns a Javascript object...
            result = page.evaluate('window.document')
            #  ... I get a remote object reference
            self.assertIsInstance(result, JSObject)
            self.assertEqual(result.description, '#document')

    def test_evaluate_on_new_document(self):
        with self._page_context() as page:
            # When I define a script to be evaluate on a new document...
            page.evaluate_on_new_document('window._WAS_EVALUATED = true;')
            # ... And I visit a new page...
            page.goto(self.httpbin.url)
            # ... My script will have been executed
            self.assertTrue(page.evaluate('window._WAS_EVALUATED'))

            # And if I visit a page again...
            page.evaluate('window._WAS_EVALUATED = false;')
            page.goto(self.httpbin.url)
            # ... the script will have been executed again
            self.assertTrue(page.evaluate('window._WAS_EVALUATED'))

    def test_url(self):
        with self._page_context() as page:
            # When I visit a page...
            page.goto(self.httpbin + '/anything/some-url')
            # ...page.url() will return the url of the page I am currently on
            self.assertEqual(page.url(), self.httpbin + '/anything/some-url')

            # And when I visit a page that redirects...
            redirect_url = self.httpbin + '/anything/some-redirect'
            page.goto(self.httpbin + '/redirect-to?url={}&status_code=200'.format(redirect_url))
            # ... page.url() returns the url of the page I was redirected to
            self.assertEqual(page.url(), redirect_url)

    def test_xpath(self):
        with self._page_context() as page:
            page.goto(self.httpbin + '/html')
            # When I try to select an element by xpath...
            element_list = page.xpath('*//h1')
            # ... I get back a list of all matching Element objects
            self.assertIsInstance(element_list, list)
            self.assertEqual(len(element_list), 1)
            self.assertIsInstance(element_list[0], Element)
            self.assertEqual(element_list[0].text, 'Herman Melville - Moby-Dick')
            self.assertEqual(element_list[0].html, '<h1>Herman Melville - Moby-Dick</h1>')

    def test_focus(self):
        with self._page_context() as page:
            page.goto(self.httpbin + '/forms/post')
            # When I try to focus an element by xpath...
            input_xpath = '*//input[@type="tel"]'
            input_element = page.xpath(input_xpath)[0]
            page.focus(input_xpath)
            # ... That element becomes the active element on the page
            active_element = page.evaluate('document.activeElement')
            self.assertEqual(active_element.html, input_element.html)

            # And if I try to focus a non-existant xpath...
            # ... A PageError is raised
            with pytest.raises(PageError):
                page.focus('*//input[@type="does-not-exist"]')

    def test_type(self):
        with self._page_context() as page:
            page.goto(self.httpbin + '/forms/post')

            # When I try to type some text into a input on the page...
            input_xpath = '*//input[@type="tel"]'
            page.type(input_xpath, 'i have typed')

            # The element now contains the text I typed
            input_element = page.xpath(input_xpath)[0]
            self.assertEqual(input_element.get_property('value'), 'i have typed')

            # And when I try to type in a non-existant element...
            # ... A PageError is raised
            with pytest.raises(PageError):
                page.type('*//input[@type="does-not-exist"]', 'i have typed')
