import re
from urllib.parse import parse_qs, urljoin, urlparse

from ..helpers import futures, gather_bits, soupify_request, stripright
from .base import Chapter, Extra, Story
from .registry import register


url_fmt = "http://www.tgstorytime.com/viewstory.php?sid={}&chapter={}&ageconsent=ok"

js_re = re.compile(r"location\s*=\s*'(.*)'")


@register(domain="tgstorytime.com")
@register(prefix="javascript:newPopwin")
class TGSStory(Story):
    publisher = "tgstorytime.com"

    author = None
    chapters = None
    title = None

    def __init__(self, id):
        super().__init__()

        id = str(id)
        if id.startswith("javascript:"):
            id = "https://tgstorytime.com/" + js_re.search(id).group(1)

        if "tgstorytime.com/" in id:
            r = urlparse(id)
            assert r.netloc in {"www.tgstorytime.com", "tgstorytime.com"}
            assert r.path == "/viewstory.php"
            qs = parse_qs(r.query)
            (id,) = map(int, qs["sid"])

        self.id = int(id)

        first_chapter = TGSChapter(self.id, 1)

        p = first_chapter.soup
        self.title, self.author = [a.text for a in p.select("div#pagetitle > a")]

        chapter_titles = {}
        for o in p.find("div", class_="jumpmenu").find_all("option"):
            n = int(o.attrs["value"])
            pre = f"{n}. "
            assert o.text.startswith(pre)
            chapter_titles[n] = o.text[len(pre) :]

        if len(chapter_titles) == 0:
            chapter_titles[1] = self.title
        first_chapter.title = chapter_titles[1]

        assert set(chapter_titles) == set(range(1, len(chapter_titles) + 1))

        self.chapters = [first_chapter] + [
            TGSChapter(self.id, n, title=chapter_titles[n])
            for n in range(2, len(chapter_titles) + 1)
        ]

    @property
    def extra(self):
        return [x for chap in self.chapters for x in chap.extra]

    def __repr__(self):
        return "TGSStory({})".format(self.id)


class TGSChapter(Chapter):
    title = None

    def __init__(self, story_id, chapter_num, title=None):
        super().__init__()

        self.story_id = story_id
        self.chapter_num = chapter_num
        self.url = url_fmt.format(story_id, chapter_num)
        self.req = futures.get(self.url)
        self.title = title

    @property
    def soup(self):
        if not hasattr(self, "_soup"):
            self._soup = soupify_request(self.req)

            # populate extras, modify text to refer to it
            self._extra = []
            div = self.soup.find("div", id="story")
            for i, x in enumerate(div.find_all(True, {"src": True})):
                ex = Extra(urljoin(self.url, x.attrs["src"]), f"{self.id}-{i}")
                self._extra.append(ex)
                x.attrs["src"] = ex.name
        return self._soup

    @property
    def text(self):
        div = self.soup.find("div", id="story")
        (sub,) = div.contents
        assert sub.name == "span"
        return gather_bits(sub.contents)

    def _get_notes(self, method_name):
        story = self.soup.find("div", id="story")
        notes = getattr(story, method_name)("div", class_="notes")
        return [
            (
                stripright(note.find(class_="title").text.strip(), ":"),
                gather_bits(note.find(class_="noteinfo").contents),
            )
            for note in notes
        ]

    @property
    def notes_pre(self):
        return reversed(self._get_notes("find_previous_siblings"))

    @property
    def notes_post(self):
        return self._get_notes("find_next_siblings")

    @property
    def extra(self):
        self.soup  # make sure it's populated....
        return self._extra

    def __repr__(self):
        return f"TGSChapter({self.story_id}, {self.chapter_num})"
