import os
import stat
import subprocess
import sys

from urllib.request import urlretrieve

from appdirs import AppDirs


CHROMIUM_REVISION = '624087'
BASE_URL = 'https://storage.googleapis.com/chromium-browser-snapshots'
DOWNLOAD_URLS = {
    'linux': '{}/Linux_x64/{}/{}'.format(BASE_URL, CHROMIUM_REVISION, 'chrome-linux.zip'),
    'mac': '{}/Mac/{}/{}'.format(BASE_URL, CHROMIUM_REVISION, 'chrome-mac.zip'),
    'win32': '{}/Win/{}/{}'.format(BASE_URL, CHROMIUM_REVISION, 'chrome-win32.zip'),
    'win64': '{}/Win_x64/{}/{}'.format(BASE_URL, CHROMIUM_REVISION, 'chrome-win64.zip')
}
EXECUTABLE_PATHS = {
    'linux': 'chrome-linux/chrome',
    'mac': 'chrome-mac/Chromium.app/Contents/MacOS/Chromium',
    'win32': 'chrome-win32/chrome.exe',
    'win64': 'chrome-win64/chrome.exe'
}


def _get_download_location():
    base_dir = os.getenv('PUPPY_HOME', AppDirs('puppy').user_data_dir)
    return os.path.join(base_dir, 'local-chromium')


def _get_platform():
    if sys.platform.startswith('linux'):
        return 'linux'
    elif sys.platform.startswith('darwin'):
        return 'mac'
    elif (sys.platform.startswith('win') or
          sys.platform.startswith('msys') or
          sys.platform.startswith('cyg')):
        return 'win32' if sys.maxsize > 2 ** 31 - 1 else 'win64'
    else:
        raise OSError('Platform not supported: {}'.format(sys.platform))


# TODO: Get this to work on all platforms. ZipFile should work elsewhere but doesn't on mac
def download_chromium():
    platform = _get_platform()
    destination = _get_download_location()
    exec_path = get_executable_path()
    if os.path.exists(exec_path):
        print('Chrome executable already exists; aborting')
        return
    if not os.path.exists(destination):
        os.makedirs(destination)

    print('Hold tight, chromium is downloading')
    url = DOWNLOAD_URLS[platform]
    zip_path = os.path.join(destination, 'chrome.zip')
    urlretrieve(url, zip_path)

    print('Extracting zip file')
    proc = subprocess.run(
        ['unzip', zip_path],
        cwd=destination,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT
    )
    if proc.returncode != 0:
        print(proc.stdout.decode())
        raise IOError('Failed to extract chromium zip')

    if not os.path.exists(exec_path):
        raise IOError('Failed to extract chromium zip')
    os.chmod(exec_path, os.stat(exec_path).st_mode | stat.S_IXOTH | stat.S_IXGRP | stat.S_IXUSR)
    os.unlink(zip_path)
    print('Done! Chromium binary located at {}'.format(exec_path))


def get_executable_path():
    return os.path.join(
        _get_download_location(),
        EXECUTABLE_PATHS[_get_platform()]
    )
