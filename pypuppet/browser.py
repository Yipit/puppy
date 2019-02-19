import json
import os
import shutil
import subprocess
import tempfile
import time

from urllib.parse import urlparse
from urllib.request import urlopen, URLError

from pypuppet.chromium_downloader import download_chromium, get_executable_path
from pypuppet.connection import Connection
from pypuppet.page import Page


class Browser:
    # TODO: choose a random open port
    PORT = 9222

    def __init__(self,
                 headless=True,
                 proxy_uri=None,
                 user_data_dir=None,
                 executable_path=None,
                 debug=False,
                 *args,
                 **kwargs):
        if not executable_path:
            executable_path = get_executable_path()
            if not os.path.exists(executable_path):
                download_chromium()
        cmd = [
            executable_path,
            'about:blank',
            '--remote-debugging-port={}'.format(self.PORT)
        ]

        if headless is True:
            cmd.append('--headless')

        self._tmp_user_data_dir = None
        if user_data_dir is None:
            self._tmp_user_data_dir = tempfile.mkdtemp(dir='/tmp')
        cmd.append('--user-data-dir={}'.format(user_data_dir or self._tmp_user_data_dir))

        self._proxy_uri = proxy_uri
        if self._proxy_uri is not None:
            parsed_uri = urlparse(self._proxy_uri)
            proxy_address = '{}://{}:{}'.format(parsed_uri.scheme, parsed_uri.hostname, parsed_uri.port)
            cmd.append('--proxy-server={}'.format(proxy_address))

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.websocket_endpoint = self._wait_for_ws_endpoint('http://localhost:{}/json/version'.format(self.PORT))
        self.connection = Connection(self.websocket_endpoint, debug=debug)
        pages = json.loads(urlopen('http://localhost:{}/json/list'.format(self.PORT)).read())

        self._pages = []
        pages = [p for p in pages if p['type'] == 'page']
        if len(pages):
            for page in pages:
                self._pages.append(Page(self.connection, page['id'], proxy_uri=self._proxy_uri))
            self.page = self._pages[0]
        else:
            self.page = self.new_page()

    def new_page(self, url='about:blank'):
        response = self.connection.send('Target.createTarget', url=url)
        target_id = response['targetId']
        self.page = Page(self.connection, target_id, proxy_uri=self._proxy_uri)
        self._pages.append(self.page)
        return self.page

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

    def _clear_temp_user_data_dir(self, timeout=5):
        waited = 0.0
        while self.process.poll() is None:
            time.sleep(0.1)
            waited += 0.1
            if waited >= timeout:
                raise Exception('Timeout waiting for Chrome to close')
        shutil.rmtree(self._tmp_user_data_dir)

    def close(self):
        self.connection.send('Browser.close')
        self.connection.close()
        self.process.terminate()
        if self._tmp_user_data_dir is not None:
            self._clear_temp_user_data_dir()
