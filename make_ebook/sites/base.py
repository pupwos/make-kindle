from abc import ABC, abstractmethod
import os
from urllib.parse import urlparse
from uuid import uuid4 as get_uuid

from ..helpers import futures, slugify


class Extra(object):
    """
    An image or similar to include in the ebook.
    """

    def __init__(self, url, name=None):
        self.url = url
        self.req = futures.get(self.url)

        basename, ext = os.path.splitext(os.path.basename(urlparse(url).path))
        if name is None:
            name = basename
        self.id = f"extra-{name}"
        self.name = f"extra-{name}{ext}"
        self.attrs = {}

    @property
    def extra_attrs(self):
        return " ".join('{}="{}"'.format(k, v) for k, v in self.attrs.items())

    @property
    def result(self):
        r = self.req.result()
        if not r.ok:
            raise IOError("Error on {}: {}".format(self.url, r.status_code))
        return r

    @property
    def mimetype(self):
        return self.result.headers["Content-Type"]

    @property
    def content(self):
        return self.result.content


class Chapter(ABC):
    """
    A chapter of a story.
    """
    notes_pre = property(lambda self: [])
    notes_post = property(lambda self: [])

    @property
    def id(self):
        if not hasattr(self, "_id"):
            self._id = get_uuid()
        return self._id

    @id.setter
    def id(self, val):
        self._id = val

    @property
    @abstractmethod
    def title(self):
        pass

    @property
    @abstractmethod
    def text(self):
        pass

    @property
    def toc_extra(self):
        if hasattr(self, "_toc_extra"):
            return self._toc_extra
        else:
            return ""

    @toc_extra.setter
    def toc_extra(self, val):
        self._toc_extra = val


class Story(ABC):
    @property
    def any_notes(self):
        return any(
            any(True for n in c.notes_pre) or any(True for n in c.notes_post)
            for c in self.chapters
        )

    @property
    def default_out_name(self):
        return slugify(self.title)

    @property
    def id(self):
        if not hasattr(self, "_id"):
            self._id = get_uuid()
        return self._id

    @id.setter
    def id(self, val):
        self._id = val

    @property
    @abstractmethod
    def author(self):
        pass

    @property
    @abstractmethod
    def title(self):
        pass

    @property
    @abstractmethod
    def publisher(self):
        pass

    @property
    @abstractmethod
    def chapters(self):
        pass

    @property
    def extra(self):
        if not hasattr(self, "_extra"):
            self._extra = []
        return self._extra

    @extra.setter
    def extra(self, val):
        self._extra = val
