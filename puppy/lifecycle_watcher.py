from threading import Event

from .exceptions import PageError
from .request import Request
from .response import Response


class LifecycleWatcher:
    LIFECYCLE_EVENTS = {
        'load': 'load',
        'DOMContentLoaded': 'domcontentloaded',
        'networkIdle': 'networkidle0',
        'networkAlmostIdle': 'networkidle2'
    }

    def __init__(self, frame, session, wait_until, timeout):
        self._frame = frame
        self._session = session
        self._timeout = timeout
        self._wait_until = wait_until if isinstance(wait_until, list) else [wait_until]
        if any([w not in self.LIFECYCLE_EVENTS.values() for w in self._wait_until]):
            raise ValueError('wait_util must be one of: {}'.format(', '.join(self.LIFECYCLE_EVENTS.values())))

        self._initial_loader_id = self._frame.loader_id
        self._loader_id = None
        self._lifecycle_complete_event = Event()
        self._navigation_response_received_event = Event()

        self._navigation_request = None

    def on_navigation_request(self, **event):
        self._navigation_request = Request(event['request'], event['requestId'])

    def on_navigation_response(self, **event):
        response = Response(event['response'],
                            self._navigation_request,
                            self._session)
        self._navigation_request.set_response(response)
        self._navigation_response_received_event.set()

    def get_navigation_response(self):
        if not self._navigation_response_received_event.wait(5):  # what timeout?
            raise PageError('Something happened getting the navigation response')
        return self._navigation_request.response

    def check_lifecycle(self):
        # Check if the frame has gotten all the events it needs
        for event in self._wait_until:
            if event not in self._frame.lifecycle_events:
                return
        self._lifecycle_complete_event.set()

    def check_frame_lifecycle(self, frame):
        for event in self._wait_until:
            if event not in frame._lifecycle_events:
                return False
        for child_frame in frame.child_frames:
            if not self.check_frame_lifecycle(child_frame):
                return False
        return True

    def wait(self):
        if not self._lifecycle_complete_event.wait(timeout=self._timeout):
            raise PageError('Navigation not completed after %s seconds.' % self._timeout)
