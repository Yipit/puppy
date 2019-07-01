class Target:
    def __init__(self, id_, browser, page_factory):
        self._id = id_
        self._browser = browser
        self._page_factory = page_factory

    def page(self):
        return self._page_factory(self._browser.connection, self._id, self._browser, self._browser.proxy_uri)
