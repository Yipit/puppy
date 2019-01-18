from threading import Event


class LifecycleWatcher:
    LIFECYCLE_EVENTS = [
        'DOMContentLoaded',
        'firstContentfulPaint',
        'firstImagePaint',
        'firstMeaningfulPaint',
        'firstMeaningfulPaintCandidate',
        'firstPaint',
        'firstTextPaint',
        'init',
        'load',
        'networkAlmostIdle',
        'networkIdle'
    ]

    def __init__(self, page):
        self._page = page
        self._session = self._page.create_devtools_session()
        self._events = {}

        self._session.send('Page.enable')
        self._session.send('Page.setLifecycleEventsEnabled', enabled=True)
        self._session.on('Page.lifecycleEvent', self._on_lifecycle_event)

    def _on_lifecycle_event(self, loaderId, name, **kwargs):
        self._set_events_key(loaderId)
        self._events[loaderId][name].set()

    def wait_for_event(self, loader_id, event_name, timeout):
        self._set_events_key(loader_id)
        # TODO: Raise a custom exception here instead of whatever normally happens
        self._events[loader_id][event_name].wait(timeout)
        self._events.clear()

    def _set_events_key(self, loader_id):
        # Need to make sure the key in the _events dict is initialized before we recieve or wait for an event
        if loader_id not in self._events:
            self._events[loader_id] = {e: Event() for e in self.LIFECYCLE_EVENTS}
