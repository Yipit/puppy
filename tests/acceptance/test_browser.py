import json
import pytest_httpbin
from envelop import Environment
from unittest import TestCase

from puppy import Browser

env = Environment()


TEST_BROWSER_KWARGS = {
    'no_sandbox': env.get_bool('NO_SANDBOX_CHROME')
}


@pytest_httpbin.use_class_based_httpbin
class BrowserCase(TestCase):
    def test_headless(self):
        # When I launch the browser in headless mode...
        browser = Browser(headless=True, **TEST_BROWSER_KWARGS)
        try:
            # ... chrome is launched with the `--headless` command line flag
            response = browser.connection.send('Browser.getBrowserCommandLine')
            self.assertIn('--headless', response['arguments'])
        finally:
            browser.close()

    def test_not_headless(self):
        # When I launch the browser not in headless mode...
        browser = Browser(headless=False, **TEST_BROWSER_KWARGS)
        try:
            # ... chrome is launched without the `--headless` command line flag
            response = browser.connection.send('Browser.getBrowserCommandLine')
            self.assertNotIn('--headless', response['arguments'])
        finally:
            browser.close()

    def test_proxy_uri(self):
        # When I launch the Browser with a proxy_uri...
        browser = Browser(proxy_uri='http://user:password@1.2.3.4:9999', **TEST_BROWSER_KWARGS)
        try:
            # ... chrome is configured to use the correct proxy
            response = browser.connection.send('Browser.getBrowserCommandLine')
            self.assertIn('--proxy-server=http://1.2.3.4:9999', response['arguments'])
        finally:
            browser.close()

    def test_user_agent(self):
        # When I launch the Browser with a specified user agent...
        browser = Browser(user_agent='fake-user-agent', **TEST_BROWSER_KWARGS)
        try:
            # ... chrome will use that user agent when making requests
            response = browser.page.goto(self.httpbin + '/user-agent')
            response_data = json.loads(response.text())
            self.assertEqual(response_data['user-agent'], 'fake-user-agent')
        finally:
            browser.close()

    def test_args(self):
        # When I launch the Browser with custom args...
        browser = Browser(args=['--custom-arg-1', '--custom-arg-2'], **TEST_BROWSER_KWARGS)
        try:
            # ... chrome will be launched with those args
            response = browser.connection.send('Browser.getBrowserCommandLine')
            self.assertIn('--custom-arg-1', response['arguments'])
            self.assertIn('--custom-arg-2', response['arguments'])
        finally:
            browser.close()

    def test_no_sandbox(self):
        # When I launch the Browser with the no_sanbox flag
        browser = Browser(no_sandbox=True)
        try:
            # ... chrome is launched with the `--no-sandbox` command line argument
            response = browser.connection.send('Browser.getBrowserCommandLine')
            self.assertIn('--no-sandbox', response['arguments'])
        finally:
            browser.close()
