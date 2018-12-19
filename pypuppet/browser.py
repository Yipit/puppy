import json
import shutil
import subprocess
import tempfile
import time

from urllib.parse import urlparse
from urllib.request import urlopen, URLError

from pypuppet.connection import Connection
from pypuppet.page import Page


class Browser:
    PORT = 9222

    def __init__(self, headless=True, proxy_uri=None, user_data_dir=None, *args, **kwargs):
        cmd = [
            '/Applications/Chromium.app/Contents/MacOS/Chromium',
            'about:blank',
            '--remote-debugging-port={}'.format(self.PORT)
        ]

        if headless is True:
            cmd.append('--headless')

        self._tmp_user_data_dir = None
        if user_data_dir is None:
            self._tmp_user_data_dir = tempfile.mkdtemp(dir='/Users/samnarisi/tmp')
        cmd.append('--user-data-dir={}'.format(user_data_dir or self._tmp_user_data_dir))
        print(self._tmp_user_data_dir)

        if proxy_uri is not None:
            parsed_uri = urlparse(proxy_uri)
            proxy_address = '{}://{}:{}'.format(parsed_uri.scheme, parsed_uri.hostname, parsed_uri.port)
            cmd.append('--proxy-server={}'.format(proxy_address))

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.websocket_endpoint = self._wait_for_ws_endpoint('http://localhost:{}/json/version'.format(self.PORT))
        self.connection = Connection(self.websocket_endpoint)
        pages = json.loads(urlopen('http://localhost:{}/json/list'.format(self.PORT)).read())

        # TODO: Sometimes there a background page called 'CrytpoTokenExtension'. what's that about?
        target_page = [p for p in pages if p['type'] == 'page'][0]
        page_endpoint = target_page['webSocketDebuggerUrl']
        self.page = Page(page_endpoint, proxy_uri=proxy_uri)

    def _wait_for_ws_endpoint(self, url, timeout=5):
        PAUSE = 0.1
        waited = 0.0
        while waited < timeout:
            try:
                response = urlopen(url)
                return json.loads(response.read())['webSocketDebuggerUrl']
            except URLError:
                time.sleep(PAUSE)
                waited += PAUSE
        raise Exception('Timed out waiting for Chrome to open')
    def close(self):
        self.connection.send('Browser.close')
        self.connection.close()
        self.page.connection.close()
        self.browser_process.terminate()
