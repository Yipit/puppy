import json
import os
import shutil
import subprocess
import tempfile
import time

from six.moves.urllib.parse import urlparse
from six.moves.urllib.request import urlopen
from six.moves.urllib.error import URLError

from .chromium_downloader import download_chromium, get_executable_path
from .connection import Connection
from .exceptions import BrowserError
from .page import Page
from .target import Target
from .utils import get_free_port


DEFAULT_ARGS = [
  '--disable-background-networking',
  '--enable-features=NetworkService,NetworkServiceInProcess',
  '--disable-background-timer-throttling',
  '--disable-backgrounding-occluded-windows',
  '--disable-breakpad',
  '--disable-client-side-phishing-detection',
  '--disable-default-apps',
  '--disable-dev-shm-usage',
  '--disable-extensions',
  '--disable-features=site-per-process,TranslateUI,BlinkGenPropertyTrees',
  '--disable-hang-monitor',
  '--disable-ipc-flooding-protection',
  '--disable-popup-blocking',
  '--disable-prompt-on-repost',
  '--disable-renderer-backgrounding',
  '--disable-sync',
  '--force-color-profile=srgb',
  '--metrics-recording-only',
  '--no-first-run',
  '--enable-automation',
  '--password-store=basic',
  '--use-mock-keychain',
]


class Browser:
    def __init__(self,
                 headless=True,
                 proxy_uri=None,
                 user_agent=None,
                 user_data_dir=None,
                 executable_path=None,
                 args=None,
                 ignore_default_args=False,
                 no_sandbox=False,
                 default_viewport=None,
                 page_class=None):
        self._PAGE_CLASS = page_class or Page
        if not executable_path:
            executable_path = get_executable_path()
            if not os.path.exists(executable_path):
                download_chromium()
        self._port = get_free_port()
        cmd = [
            executable_path,
            'about:blank',
            '--remote-debugging-port={}'.format(self._port)
        ]

        chrome_args = [] if ignore_default_args else DEFAULT_ARGS.copy()

        if args is not None:
            chrome_args.extend(args)

        if headless is True and '--headless' not in chrome_args:
            chrome_args.append('--headless')

        if user_agent is not None and not any([a.startswith('--user-agent=') for a in chrome_args]):
            chrome_args.append('--user-agent={}'.format(user_agent))

        if no_sandbox and '--no-sandbox' not in chrome_args:
            chrome_args.append('--no-sandbox')

        cmd.extend(chrome_args)

        self._tmp_user_data_dir = None
        if user_data_dir is None:
            self._tmp_user_data_dir = tempfile.mkdtemp(dir='/tmp')
        cmd.append('--user-data-dir={}'.format(user_data_dir or self._tmp_user_data_dir))

        self.proxy_uri = proxy_uri
        if self.proxy_uri is not None:
            parsed_uri = urlparse(self.proxy_uri)
            proxy_address = '{}://{}:{}'.format(parsed_uri.scheme, parsed_uri.hostname, parsed_uri.port)
            cmd.append('--proxy-server={}'.format(proxy_address))

        self._default_viewport = default_viewport or {'width': 800, 'height': 600}
        if not any('--window-size' in arg for arg in cmd):
            cmd.append('--window-size={},{}'.format(self._default_viewport['width'],
                                                    self._default_viewport['height']))

        self.process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        self.websocket_endpoint = self._wait_for_ws_endpoint('http://localhost:{}/json/version'.format(self._port))
        self.connection = Connection(self.websocket_endpoint)

        self._targets = []
        targets = json.loads(urlopen('http://localhost:{}/json/list'.format(self._port)).read())
        valid_targets = [p for p in targets if p['type'] == 'page']
        if len(valid_targets):
            for target in valid_targets:
                self._targets.append(Target(target['id'], self, self._PAGE_CLASS))
        else:
            self._targets.append(self._create_target())

        self.page = self._targets[0].page()
        self.page.set_viewport(self._default_viewport)

    def _create_target(self, url='about:blank'):
        response = self.connection.send('Target.createTarget', url=url)
        return Target(response['targetId'], self, self._PAGE_CLASS)

    def _wait_for_ws_endpoint(self, url, timeout=5):
        PAUSE = 0.01
        waited = 0.0
        while waited < timeout:
            try:
                response = urlopen(url)
                return json.loads(response.read())['webSocketDebuggerUrl']
            except URLError:
                time.sleep(PAUSE)
                waited += PAUSE
        raise BrowserError('Timed out waiting for Chrome to open')

    def _clear_temp_user_data_dir(self, timeout=5):
        waited = 0.0
        while self.process.poll() is None:
            time.sleep(0.1)
            waited += 0.1
            if waited >= timeout:
                raise BrowserError('Timeout waiting for Chrome to close')
        shutil.rmtree(self._tmp_user_data_dir)

    def close(self):
        try:
            # Try to close browser the normal way
            self.connection.send('Browser.close')
        except BrowserError:
            # If it doesn't respond, just terminate the process and clean the rest up
            pass
        self.process.terminate()
        if self._tmp_user_data_dir is not None:
            self._clear_temp_user_data_dir()
