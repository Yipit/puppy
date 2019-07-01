from contextlib import contextmanager

from .exceptions import PageError
from .execution_context import ExecutionContext
from .lifecycle_watcher import LifecycleWatcher
from .request_manager import RequestManager


class FrameManager:
    UTILITY_WORLD_NAME = '__puppy_utility_world__'

    def __init__(self, session, page, *args, **kwargs):
        self._session = session
        self._page = page
        self._frames = {}
        self._main_frame = None
        self._request_manager = RequestManager(self._page.create_devtools_session, self._page._proxy_uri)
        self._isolated_worlds = set()

        self._session.send('Page.setLifecycleEventsEnabled', enabled=True)
        self._session.send('Runtime.enable')

        self._session.on('Page.frameAttached', self._on_frame_attached)
        self._session.on('Page.frameNavigated', lambda **e: self._on_frame_navigated(**e['frame']))
        self._session.on('Page.frameStoppedLoading', self._on_frame_stopped_loading)
        self._session.on('Network.requestWillBeSent', self._on_request_will_be_sent)
        self._session.on('Network.responseReceived', self._on_response_received)
        self._session.on('Page.lifecycleEvent', self._on_lifecylce_event)
        self._session.on('Runtime.executionContextCreated', self._on_execution_context_created)

        frame_tree = self._session.send('Page.getFrameTree')['frameTree']
        self._handle_frame_tree(frame_tree)
        self._ensure_isolated_world(self.UTILITY_WORLD_NAME)

    @property
    def request_manager(self):
        return self._request_manager

    def navigate_frame(self, frame, url, timeout, wait_until, referrer):
        lifecycle_watcher = frame.create_lifecycle_watcher(self._session, wait_until, timeout)
        referrer = (referrer or
                    self._request_manager.extra_http_headers.get('Referer') or
                    self._request_manager.extra_http_headers.get('referer'))
        response = self._session.send('Page.navigate', url=url, frameId=frame.id, referrer=referrer)
        if 'errorText' in response:
            raise PageError(response['errorText'])
        lifecycle_watcher.wait()
        return lifecycle_watcher.get_navigation_response()

    @contextmanager
    def wait_for_navigation(self, frame, wait_until, timeout):
        lifecycle_watcher = frame.create_lifecycle_watcher(self._session, wait_until, timeout)
        yield
        lifecycle_watcher.wait()

    def _on_lifecylce_event(self, **event):
        self._all_lifecycle_events.append(event)
        if event['frameId'] not in self._frames:
            return
        self._frames[event['frameId']].on_lifecycle_event(**event)

    def _on_frame_attached(self, **event):
        if event['frameId'] in self._frames:
            return
        parent_frame = self._frames.get(event['parentFrameId'])
        self._frames[event['frameId']] = Frame(event['frameId'], self._session, frame_manager=self, parent_frame=parent_frame)

    def _on_frame_navigated(self, **navigated_frame):
        is_main_frame = 'parentId' not in navigated_frame
        frame = self._main_frame if is_main_frame else self._frames.get(navigated_frame['id'])
        if frame is not None:
            # TODO: detach all child frames?
            pass
        if is_main_frame:
            if frame is not None:
                del self._frames[frame.id]
                frame.id = navigated_frame['id']
            else:
                frame = Frame(navigated_frame['id'], self._session, frame_manager=self)
            self._frames[navigated_frame['id']] = frame
            self._main_frame = frame
        frame.handle_navigation(navigated_frame)

    def _on_frame_stopped_loading(self, **event):
        if event['frameId'] not in self._frames:
            return
        self._frames[event['frameId']].on_loading_stopped()

    def _handle_frame_tree(self, frame_tree):
        if 'parentId' in frame_tree['frame']:
            self._on_frame_attached(frame_tree['frame']['id'], frame_tree['frame']['parentId'])
        self._on_frame_navigated(**frame_tree['frame'])
        if 'childFrames' in frame_tree:
            for child_frame in frame_tree['childFrames']:
                self._handle_frame_tree(child_frame)

    def _on_request_will_be_sent(self, **event):
        frame_id = event['frameId']
        if frame_id not in self._frames:
            return
        self._frames[frame_id].on_request_will_be_sent(**event)

    def _on_response_received(self, **event):
        frame_id = event['frameId']
        if frame_id not in self._frames:
            return
        self._frames[frame_id].on_response_received(**event)

    def _on_execution_context_created(self, **event):
        frame_id = event['context'].get('auxData', {}).get('frameId')
        if frame_id not in self._frames:
            return
        self._frames[frame_id].on_execution_context_created(**event)

    def _ensure_isolated_world(self, name):
        if name in self._isolated_worlds:
            return
        self._isolated_worlds.add(name)
        for frame in self._frames.values():
            self._session.send('Page.createIsolatedWorld',
                               frameId=frame.id,
                               worldName=name)


class Frame:
    def __init__(self, id_, session, **kwargs):
        self._id = id_
        self._navigation_url = None
        self._url = None
        self._name = None
        self._loader_id = None
        self._lifecycle_events = set()
        self._lifecycle_watcher = None
        self._execution_context = None
        self._session = session
        self._frame_manager = kwargs.pop('frame_manager')
        self._parent_frame = kwargs.get('parent_frame')
        self._child_frames = {}
        if self._parent_frame:
            self._parent_frame.child_frames[self.id] = self

    @property
    def child_frames(self):
        return self._child_frames

    @property
    def id(self):
        return self._id

    @id.setter
    def id(self, id_):
        self._id = id_

    @property
    def loader_id(self):
        return self._loader_id

    @property
    def lifecycle_events(self):
        return self._lifecycle_events

    def evaluate(self, expression):
        return self._execution_context.evaluate(expression)

    def handle_navigation(self, navigated_frame):
        self._url = navigated_frame['url']
        self._navigation_url = navigated_frame['url']
        self._name = navigated_frame.get('name')

    def on_lifecycle_event(self, **event):
        if event['name'] == 'init':
            self._loader_id = event['loaderId']
            self._lifecycle_events.clear()
            # return
        if event['name'] not in LifecycleWatcher.LIFECYCLE_EVENTS:
            return
        if event['loaderId'] != self._loader_id:
            return
        self._lifecycle_events.add(LifecycleWatcher.LIFECYCLE_EVENTS[event['name']])
        if self._lifecycle_watcher:
            self._lifecycle_watcher.check_lifecycle()

    def on_loading_stopped(self):
        self._lifecycle_events.add('load')
        self._lifecycle_events.add('domcontentloaded')
        if self._lifecycle_watcher:
            self._lifecycle_watcher.check_lifecycle()

    def create_lifecycle_watcher(self, session, wait_until, timeout):
        self._lifecycle_watcher = LifecycleWatcher(self, session, wait_until, timeout)
        return self._lifecycle_watcher

    def on_request_will_be_sent(self, **event):
        is_navigation_request = event['loaderId'] == event['requestId'] and event['type'] == 'Document'
        if is_navigation_request and self._lifecycle_watcher:
            self._lifecycle_watcher.on_navigation_request(**event)

    def on_response_received(self, **event):
        if self._lifecycle_watcher and self._lifecycle_watcher._navigation_request:
            if self._lifecycle_watcher._navigation_request.request_id == event['requestId']:
                self._lifecycle_watcher.on_navigation_response(**event)

    def on_execution_context_created(self, **event):
        self._execution_context = ExecutionContext(event['context']['id'],
                                                   event['context']['origin'],
                                                   event['context']['name'],
                                                   event['context'].get('auxData'),
                                                   self._session)
