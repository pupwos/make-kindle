import requests
from requests_futures.sessions import FuturesSession
from urllib.parse import urljoin

from ..helpers import gather_bits, soupify, soupify_request
from .base import Chapter, Story
from .registry import register


@register("hentai-foundry.com")
class HFStory(Story):
    publisher = "hentai-foundry.com"
    author = chapters = title = None

    def __init__(self, url):
        self.url = url

        # need to be slightly careful around cookies/etc
        self.session = requests.Session()
        self.session.headers["User-Agent"] = "Mozilla/5"
        self.futures = FuturesSession(session=self.session, max_workers=5)

        r = self.session.get(self.url)
        if not r.ok:
            raise IOError("Error: {}".format(r.status_code))
        self.soup = soupify(r.content)

        a = self.soup.find(id="frontPage_link")
        if a:
            r = self.session.get(
                urljoin(self.url, a["href"] + "&size=1000"), cookies=r.cookies
            )
            if not r.ok:
                raise IOError("Error: {}".format(r.status_code))
            self.soup = soupify(r.content)

        if self.soup.find(id="viewChapter"):
            self.url = url = urljoin(
                url, self.soup.select_one(".storyRead a:not(.pdfLink)")["href"]
            )
            self.soup = soupify_request(self.futures.get(url))

        self.author = self.soup.select_one(".storyInfo a[href^='/user']").text.strip()
        self.title = self.soup.select_one(".titlebar a[href^='/stories']").text.strip()

        box = self.soup.find("h2", text="Chapters").parent.find(class_="boxbody")
        self.chapters = [
            HFChapter(self.futures.get(urljoin(self.url, p.find("a")["href"])))
            for p in box.find_all("p")
        ]


class HFChapter(Chapter):
    def __init__(self, req):
        self.req = req

    @property
    def soup(self):
        if not hasattr(self, "_soup"):
            self._soup = soupify_request(self.req)
        return self._soup

    @property
    def title(self):
        return self.soup.select_one("#viewChapter .titleSemantic").text.strip()

    @property
    def text(self):
        return gather_bits(self.soup.select_one("#viewChapter .boxbody"))
