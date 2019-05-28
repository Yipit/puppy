import logging

from envelop import Environment

from .browser import Browser


env = Environment()

log_level = env.get('LOGLEVEL', 'WARN').upper()


_logger = logging.getLogger('puppy')
_handler = logging.StreamHandler()
_formatter = logging.Formatter('%(asctime) - 5s - [%(levelname)s:%(name)s] - %(message)s', '%m-%d-%Y %H:%M:%S')
_handler.setFormatter(_formatter)
_handler.setLevel(logging.DEBUG)
_logger.addHandler(_handler)
_logger.setLevel(log_level)
_logger.propagate = False


__all__ = ['Browser']
