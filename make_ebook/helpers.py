from functools import lru_cache, partial
import hashlib
import re

from bs4 import BeautifulSoup, Comment
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter
import requests
from requests_futures.sessions import FuturesSession
import unicodedata


cached = CacheControl(
    requests.Session(), heuristic=ExpiresAfter(hours=1), cache=FileCache(".webcache")
)
futures = FuturesSession(session=cached, max_workers=5)


soupify = partial(BeautifulSoup, features="html5lib")


def soupify_request(req):
    r = req.result()
    if not r.ok:
        raise IOError("Error: {}".format(r.status_code))
    return soupify(r.content)


def slugify(s):
    s = unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode("ascii")
    s = re.sub(r"(^-+)|(-+$)", "", re.sub(r'[-\s:!\'",\.]+', "-", s))
    return s.lower()


@lru_cache(maxsize=512)
def hashify(s, alg="sha1"):
    return getattr(hashlib, alg)(s.encode("utf-8")).hexdigest()


def stripright(s, end):
    return s[: -len(end)] if s.endswith(end) else s


def gather_bits(bits):
    return "".join(
        [
            unicodedata.normalize("NFKC", str(b))
            .encode("ascii", "xmlcharrefreplace")
            .decode("ascii")
            for b in bits
            if not isinstance(b, Comment)
        ]
    ).strip()
