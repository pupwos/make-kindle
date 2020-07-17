from .registry import get_site

from . import ao3
from . import fictionmania
from . import literotica
from . import mcstories
from . import scribblehub
from . import take_a_lemon
from . import tgs


def get_story(path):
    cls = get_site(path)
    return cls(path)
