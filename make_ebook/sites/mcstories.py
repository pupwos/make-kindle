from urllib.parse import urlparse

from ..helpers import futures, gather_bits, soupify_request
from .base import Story, Chapter
from .registry import register


@register(domain="mcstories.com")
class MCSStory(Story):
    publisher = "mcstories.com"
    author = chapters = title = None

    def __init__(self, id):
        super(MCSStory, self).__init__()

        if "mcstories.com" in id:
            r = urlparse(id)
            assert r.netloc == "mcstories.com"
            assert r.path.startswith("/")
            id = r.path[1:].split("/")[0]
        self.id = id

        url = "https://mcstories.com/{}/".format(id)
        p = soupify_request(futures.get(url))

        self.title = p.find("h3", class_="title").text.strip()
        self.author = p.find("h3", class_="byline").text.strip()
        assert self.author.startswith("by ")
        self.author = self.author[3:]

        self.extra = []

        self.chapters = []
        tab = p.find("table", id="index")
        if tab is not None:
            for i, tr in enumerate(tab.find_all("tr")):
                if i == 0:
                    assert tr.find("th").text.strip() == "Chapter"
                    continue

                name, length, added = tr.find_all("td")
                a = name.find("a")
                assert "/" not in a["href"]
                self.chapters.append(
                    MCSChapter(futures.get(url + a["href"]), i, name.text, added.text)
                )
        else:
            a = p.find("div", class_="chapter").find("a")
            self.chapters.append(
                MCSChapter(futures.get(url + a["href"]), 1, a.text, "")
            )


class MCSChapter(Chapter):
    title = None

    def __init__(self, req, id, title, toc_extra):
        super(MCSChapter, self).__init__()

        self.req = req
        self.id = id
        self.title = title
        self.toc_extra = toc_extra

    @property
    def soup(self):
        if not hasattr(self, "_soup"):
            self._soup = soupify_request(self.req)
        return self._soup

    @property
    def text(self):
        return gather_bits(
            x
            for sec in self.soup("article")[0]("section", recursive=False)
            for x in sec
        )

    # TODO: notes_pre, notes_post; don't seem entirely consistent
