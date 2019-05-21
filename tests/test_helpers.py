from contextlib import contextmanager
from envelop import Environment

from puppy import Browser


env = Environment()


@contextmanager
def page_context(headless=True):
    browser_args = ['--no-sandbox'] if env.get_bool('NO_SANDBOX_CHROME') else None
    try:
        browser = Browser(headless=headless, args=browser_args)
        yield browser.page
    finally:
        browser.close()
