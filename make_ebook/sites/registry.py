from urllib.parse import urlparse

_domain_registry = {}
_prefix_registry = {}


def register(domain=None, prefix=None):
    if domain is not None:
        assert prefix is None

        def the_decorator(cls):
            assert domain not in _domain_registry
            _domain_registry[domain] = cls
            return cls

    elif prefix is not None:

        def the_decorator(cls):
            assert prefix not in _prefix_registry
            _prefix_registry[prefix] = cls
            return cls

    return the_decorator


def get_site(path):
    for pref, cls in _prefix_registry.items():
        if path.startswith(pref):
            return cls

    netloc = urlparse(path).netloc
    while "." in netloc and netloc not in _domain_registry:
        _, netloc = netloc.split(".", 1)
    if netloc in _domain_registry:
        return _domain_registry[netloc]

    raise ValueError(f"Couldn't find registered site for {path}")
