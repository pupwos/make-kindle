from collections import namedtuple
import re
from urllib.parse import parse_qs, urljoin, urlparse

from ..helpers import futures, gather_bits, soupify_request
from .base import Story, Chapter, Extra
from .registry import register


fm_urls = {
    "x": "https://fictionmania.tv/stories/readxstory.html?storyID={}",
    "html": "https://fictionmania.tv/stories/readhtmlstory.html?storyID={}",
}
fm_js_start = "javascript:newPopwin('"


class FMChapter(Chapter):
    # could probably use dataclasses, if we want a py3.7 dep
    title = text = None

    def __init__(self, **kwargs):
        super(FMChapter, self).__init__()
        for k, v in kwargs.items():
            setattr(self, k, v)


@register(domain="fictionmania.tv")
@register(prefix=fm_js_start)
class FMStory(Story):
    publisher = "fictionmania.tv"
    author = chapters = title = None

    def __init__(self, id, mode=None):
        super(FMStory, self).__init__()

        if id.startswith(fm_js_start):
            assert id.endswith("')")
            id = "https://fictionmania.tv" + id[len(fm_js_start) : -2]

        if "fictionmania.tv" in id:
            r = urlparse(id)
            assert r.netloc == "fictionmania.tv"
            if r.path == "/stories/readxstory.html":
                if mode is None:
                    mode = "x"
            elif r.path == "/stories/readhtmlstory.html":
                if mode is None:
                    mode = "html"
            else:
                raise ValueError("bad URL {}".format(r.path))

            qs = parse_qs(r.query)
            (id,) = map(int, qs["storyID"])

        self.id = id
        if mode is None:
            mode = "x"
        self.mode = mode

        url = fm_urls[mode].format(id)

        p = soupify_request(futures.get(url))

        if mode == "x":
            (h2,) = p.find_all("h2")
            self.title = h2.text

            self.author = p.select_one(
                'a[href^="/searchdisplay/authordisplay.html?"]'
            ).text

            end = p.find("a", href=re.compile("^/stories/report.html")).parent
            bits = []
            for tag in p.find("hr").next_siblings:
                if tag is end:
                    break
                bits.append(tag)
            else:
                raise ValueError("hr structure was surprising")
            self.extra = []
        elif mode == "html":
            menu = p.find("div", id="menu")

            self.title = menu.find_next_sibling("p").find("font").text

            tab = menu.find_next_sibling("table")
            self.author = tab.select_one(
                'a[href^="/searchdisplay/authordisplay.html?"]'
            ).text

            div = tab.find_next_sibling("div")

            self.extra = []
            for i, x in enumerate(div.find_all(True, {"src": True})):
                ex = Extra(urljoin(url, x.attrs["src"]), f"extra-{i}")
                self.extra.append(ex)
                x.attrs["src"] = ex.name

            bits = div.contents
        else:
            raise ValueError("bad mode {}".format(mode))

        text = gather_bits(bits)

        self.chapters = [FMChapter(title=self.title, text=text)]
