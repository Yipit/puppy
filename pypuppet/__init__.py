import time

from subprocess import Popen, PIPE, STDOUT
from requests.exceptions import ConnectionError

import pychrome


class PuppetMaster:
    def __init__(self):
        pass

    def _connect_to_chrome(self, url, timeout=5):
        while timeout >= 0:
            try:
                return pychrome.Browser(url=url)
            except ConnectionError:
                time.sleep(0.5)
                timeout -= 0.5
        raise Exception('Could not connect to Chrome')

    def _get_new_tab(self, timeout=5):
        while timeout >= 0:
            try:
                return self.browser.new_tab()
            except ConnectionError:
                time.sleep(0.5)
                timeout -= 0.5
        raise Exception('Could not get browser tab')

    def __enter__(self):
        self.chrome_proc = Popen(
            ['/Applications/Chromium.app/Contents/MacOS/Chromium', '--remote-debugging-port=9222'],
            stdout=PIPE,
            stderr=STDOUT
        )
        self.browser = self._connect_to_chrome('http://localhost:9222')
        self.tab = self._get_new_tab()
        self.tab.start()
        return Tab(self.tab, self.browser)

    def __exit__(self, *args, **kwargs):
        self.browser.close_tab(self.tab)
        self.chrome_proc.terminate()


class Tab:
    def __init__(self, tab, browser):
        self._tab = tab
        self.browser = browser
        self._tab.call_method('Network.enable')

        def _print_url(**kwargs):
            print(kwargs.get('request')['url'])

        # self._tab.set_listener('Network.requestWillBeSent', _print_url)

        def _print_load(*args, **kwargs):
            print('YOOOOO')
            print(args)
            print(kwargs)

        self._tab.set_listener('Page.domContentEventFired', _print_load)
        self._tab.set_listener('Page.loadEventFired', _print_load)
        self._tab.set_listener('Page.lifecycleEvent', _print_load)

    def goto(self, url, timeout=100):
        self._tab._send({
            'method': 'Page.navigate',
            'params': {'url': url}
        })
        time.sleep(10)
