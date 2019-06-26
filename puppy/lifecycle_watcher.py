from threading import Event

from .exceptions import PageError


class LifecycleWatcher:
    LIFECYCLE_EVENTS = {
        'load': 'load',
        'DOMContentLoaded': 'domcontentloaded',
        'networkIdle': 'networkidle0',
        'networkAlmostIdle': 'networkidle2'
    }

    def __init__(self, page, wait_until, require_new_loader=True):
        self._page = page

        self._wait_until = wait_until if isinstance(wait_until, list) else [wait_until]
        if any([w not in self.LIFECYCLE_EVENTS.values() for w in self._wait_until]):
            raise ValueError('wait_util must be one of: {}'.format(', '.join(self.LIFECYCLE_EVENTS.values())))

        self._require_new_loader = require_new_loader
        self._session = self._page.create_devtools_session()
        self._initial_loader_id = page.loader_id
        self._loader_id = None
        self._lifecycle_events = set()
        self._lifecycle_complete_event = Event()

        self._session.send('Page.enable')
        self._session.send('Page.setLifecycleEventsEnabled', enabled=True)
        self._session.on('Page.lifecycleEvent', self._on_lifecycle_event)

    def _on_lifecycle_event(self, loaderId, name, **kwargs):
        if name == 'init':
            self._loader_id = loaderId
            self._lifecycle_events.clear()
            return
        elif name not in self.LIFECYCLE_EVENTS:
            return

        if self._loader_id != loaderId:
            return

        if not self._require_new_loader or loaderId != self._initial_loader_id:
            self._lifecycle_events.add(self.LIFECYCLE_EVENTS[name])
        if self._check_events():
            self._lifecycle_complete_event.set()

    def _check_events(self):
        for event in self._wait_until:
            if event not in self._lifecycle_events:
                return False
        return True

    def wait(self, timeout):
        if not self._lifecycle_complete_event.wait(timeout=timeout):
            raise PageError('Navigation not completed after %s seconds.' % timeout)
