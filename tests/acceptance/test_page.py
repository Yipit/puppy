import json
import pytest
import pytest_httpbin

from unittest import TestCase

from puppy.exceptions import PageError
from puppy.js_handle import JSHandle, ElementHandle

from ..test_helpers import page_context


@pytest_httpbin.use_class_based_httpbin
class PageCase(TestCase):

    def test_goto(self):
        # TODO: seems response here is often None, could be a problem with goto
        with page_context() as page:
            # When I call page.goto...
            response = page.goto(self.httpbin + '/status/200')
            # ... I get a response object with the correct status code
            self.assertEqual(response.status, 200)
            # ... and the correct status text
            self.assertEqual(response.status_text, 'OK')
            # ... and the correct url
            self.assertEqual(response.url, self.httpbin + '/status/200')

    def test_content(self):
        with page_context() as page:
            page.goto(self.httpbin + '/html')
            content = page.content()
            self.assertIn('<h1>Herman Melville - Moby-Dick</h1>', content)  # good enough?

    def test_evaluate(self):
        with page_context() as page:
            # When I evaluate a javascipt expression that returns a primitive...
            result = page.evaluate('2 + 2')
            # ... I get a Python primitive back
            self.assertEqual(result, 4)

            # And when the expression returns a Javascript object...
            result = page.evaluate('window.document')
            #  ... I get a remote object reference
            self.assertIsInstance(result, JSHandle)
            self.assertEqual(result.description, '#document')

    def test_evaluate_on_new_document(self):
        with page_context() as page:
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
        with page_context() as page:
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
        with page_context() as page:
            page.goto(self.httpbin + '/html')
            # When I try to select an element by xpath...
            element_list = page.xpath('*//h1')
            # ... I get back a list of all matching ElementHandle objects
            self.assertIsInstance(element_list, list)
            self.assertEqual(len(element_list), 1)
            self.assertIsInstance(element_list[0], ElementHandle)
            self.assertEqual(element_list[0].text, 'Herman Melville - Moby-Dick')
            self.assertEqual(element_list[0].html, '<h1>Herman Melville - Moby-Dick</h1>')

    def test_focus(self):
        with page_context() as page:
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
        with page_context() as page:
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

    def test_wait_for_xpath(self):
        with page_context() as page:
            page.goto(self.httpbin + '/html')

            # JS script to create a new div, pause 5 seconds asyncronously, and add it to the dom
            page.evaluate('''
                newElement = document.createElement('div')
                newElement.id = 'new-element'
                newElement.textContent = 'I am a new element'
                setTimeout(function() {
                    document.body.appendChild(newElement)
            }, 5000)
            ''')

            elements = page.xpath('*//div[@id="new-element"]')
            self.assertEqual(len(elements), 0)  # element should not be there yet

            # When I call page.wait_for_xpath, the code will wait until one or more matching elemnts appear and return them
            elements = page.wait_for_xpath('*//div[@id="new-element"]')
            self.assertIsInstance(elements, list)
            self.assertIsInstance(elements[0], ElementHandle)
            self.assertEqual(elements[0].get_property('id'), 'new-element')
            self.assertEqual(elements[0].text, 'I am a new element')

            # If I specify visible=True and there are no matching visible elements, I get an error
            page.evaluate('''
                invisibleHeader = document.createElement('h1')
                invisibleHeader.className = 'new-header'
                invisibleHeader.textContent = 'I am not visible'
                invisibleHeader.style['visibility'] = 'hidden'
                setTimeout(function() {
                    document.body.appendChild(invisibleHeader)
            }, 0)
            ''')
            with pytest.raises(PageError, match=r'Timed out waiting for element'):
                elements = page.wait_for_xpath('*//h1[@class="new-header"]', visible=True, timeout=3)

            # And if there are visible elements, only those are returned
            page.evaluate('''
                visibleHeader = document.createElement('h1')
                visibleHeader.className = 'new-header'
                visibleHeader.textContent = 'I am visible'
                setTimeout(function() {
                    document.body.appendChild(visibleHeader)
            }, 0)
            ''')
            elements = page.wait_for_xpath('*//h1[@class="new-header"]', visible=True, timeout=3)
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0].text, 'I am visible')

            # But if I specify hidden=True, only hidden elements are returned
            elements = page.wait_for_xpath('*//h1[@class="new-header"]', hidden=True, timeout=3)
            self.assertEqual(len(elements), 1)
            self.assertEqual(elements[0].text, 'I am not visible')

    def test_dom_interaction(self):
        with page_context() as page:
            # When I visit a page...
            page.goto(self.httpbin + '/forms/post')
            # ... I can enter data into input boxes...
            page.type('*//input[@name="custname"]', 'YipitData')
            page.type('*//input[@name="custtel"]', '212-555-1234')
            # ... and click on form elements and buttons...
            page.click('*//input[@name="size"][@value="large"]')
            page.click('*//input[@name="topping"][@value="bacon"]')
            page.click('*//input[@name="topping"][@value="cheese"]')
            # ... and I can pause my code while a navigation event happens
            with page.wait_for_navigation():
                page.click('*//button[contains(text(), "Submit order")]')
            self.assertEqual(page.url(), self.httpbin + '/post')
            data = json.loads(page.xpath('*//pre')[0].text)
            self.assertEqual(data['form']['custname'], 'YipitData')
            self.assertEqual(data['form']['custtel'], '212-555-1234')
            self.assertEqual(data['form']['size'], 'large')
            self.assertEqual(data['form']['topping'], ['bacon', 'cheese'])
