import gc
import socket


def get_free_port():
    """Get free port."""

    # This is how pyppeteer does it
    sock = socket.socket()
    sock.bind(('localhost', 0))
    port = sock.getsockname()[1]
    sock.close()
    del sock
    gc.collect()
    return port
