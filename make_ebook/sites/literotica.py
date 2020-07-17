from html.parser import HTMLParser
import re

from ..helpers import futures, gather_bits, soupify_request
from .base import Chapter, Story
from .registry import register

# TODO: new site format...


@register(domain="literotica.com")
class LitSeries(Story):
    publisher = "Literotica.com"
    chapters = None

    def __init__(self, first_story_id):
        super(LitSeries, self).__init__()

        self.first = s = LitStory(first_story_id)
        div = s.get_page(s.num_pages).find(id="b-series")
        self.chapters = [s]
        if div:
            self.chapters += [LitStory(a["href"]) for a in div.findAll("a")]
        self.extra = []

    @property
    def title(self):
        if self.first.series_name:
            return self.first.series_name[: self.first.series_name.rfind(":")]
        else:
            return self.first.title

    @property
    def author(self):
        return self.first.author

    @property
    def id(self):
        return self.first.id

    @property
    def default_out_name(self):
        return self.id


class LitStory(Chapter):
    def __init__(self, id):
        super(LitStory, self).__init__()

        if "literotica.com/" in id:
            pat = r"https?:\/\/(?:www\.)?literotica.com/s/([^\?]*)\??.*"
            id = re.match(pat, id).group(1)

        self.id = str(id)
        self.url = "https://www.literotica.com/s/{}".format(self.id)
        self._meta_dict = None

    def get_pages(self, nums):
        reqs = [futures.get(f"{self.url}?page={n}") for n in nums]
        return [soupify_request(req) for req in reqs]

    def get_page(self, num):
        return self.get_pages([num])[0]

    author = property(lambda self: self._meta()["author"])
    author_link = property(lambda self: self._meta()["author_link"])
    title = property(lambda self: self._meta()["title"])
    category = property(lambda self: self._meta()["category"])
    description = property(lambda self: self._meta()["description"])
    num_pages = property(lambda self: self._meta()["num_pages"])
    rating = property(lambda self: self._meta()["rating"])
    date = property(lambda self: self._meta()["date"])
    series_name = property(lambda self: self._meta()["series_name"])

    def _meta(self):
        if self._meta_dict:
            return self._meta_dict

        self._meta_dict = d = {}
        p = self.get_page(1)

        author_link = p.find("span", class_="b-story-user-y").find("a")
        d["author"] = author_link.get_text()
        d["author_link"] = author_link["href"]

        t = p.find("title").get_text()
        t = HTMLParser().unescape(t)
        # rip out " - Literotica.com"
        d["title"], d["category"] = t[:-17].rsplit(" - ", 1)

        d["description"] = p.find("meta", {"name": "description"})["content"]

        s = p.find("span", class_="b-pager-caption-t").text
        d["num_pages"] = int(re.match("(\d+) Pages?:?$", s).group(1))

        author_page = soupify_request(futures.get(d["author_link"]))
        a = author_page.find("a", href=lambda s: self.id in s)
        d["rating"] = re.match(".*\(([\d\.]+)\)", a.next_sibling).group(1)
        tr = a.find_parent("tr")

        dt = tr.find(class_="dt")  # in series
        if dt is None:
            dt = tr.find_all("td")[-1]
        d["date"] = dt.text

        if "sl" in tr["class"]:
            d["series_name"] = tr.find_previous_sibling(class_="ser-ttl").text
        else:
            d["series_name"] = None
        return d

    @property
    def text(self):
        if not getattr(self, "_text", None):
            pages = self.get_pages(range(1, self.num_pages + 1))

            bits = []
            for p in pages:
                div = p.find("div", class_="b-story-body-x")
                assert len(div.contents) == 1
                (sub,) = div.contents
                assert sub.name == "div"
                bits.extend(sub.contents)
            self._text = gather_bits(bits)

        return self._text

    @property
    def toc_extra(self):
        return "({}; {})".format(self.date, self.rating)

    def __repr__(self):
        return "Story({!r})".format(self.id)
