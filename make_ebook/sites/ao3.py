from urllib.parse import urlparse

from ..helpers import futures, gather_bits, soupify_request, stripright
from .base import Story, Chapter
from .registry import register


work_fmt = "https://archiveofourown.org/works/{}?view_adult=true"
chap_fmt = "https://archiveofourown.org/works/{}/chapters/{}?view_adult=true"


@register(domain="archiveofourown.org")
class AO3Story(Story):
    publisher = "archiveofourown.org"
    author = chapters = title = None

    def __init__(self, id):
        super(AO3Story, self).__init__()

        if "archiveofourown.org/" in id:
            r = urlparse(id)
            assert r.netloc in {"www.archiveofourown.org", "archiveofourown.org"}
            assert r.path.startswith("/works/")
            pth = r.path[len("/works/") :]
            if "/" in pth:
                pth = pth[: pth.index("/")]
            id = int(pth)

        self.id = id
        self.url = work_fmt.format(self.id)

        p = soupify_request(futures.get(self.url))
        self.title = p.find(class_="title heading").text.strip()
        self.author = p.find(class_="byline heading").text.strip()
        self.extra = []

        selector = p.find(id="selected_id")
        if selector:
            self.chapters = [
                AO3Chapter(self.id, o.attrs["value"])
                for o in selector.find_all("option")
            ]
        else:
            self.chapters = [AO3Chapter(self.id, only_chapter)]

    def __repr__(self):
        return "AO3Story({})".format(self.id)


only_chapter = ("all",)


class AO3Chapter(Chapter):
    def __init__(self, work_id, chap_id):
        super(AO3Chapter, self).__init__()

        self.work_id = work_id
        self.chap_id = chap_id
        self.id = f"{work_id}_{chap_id}"
        if chap_id == only_chapter:
            self.url = chap_fmt.format(work_id, chap_id)
        else:
            self.url = work_fmt.format(work_id)
        self.req = futures.get(self.url)

    def __repr__(self):
        return "AO3Chapter({}, {})".format(self.work_id, self.chap_id)

    @property
    def soup(self):
        if not hasattr(self, "_soup"):
            self._soup = soupify_request(self.req)
        return self._soup

    @property
    def _preface(self):
        if not hasattr(self, "_preface_div"):
            self._preface_div = self.soup.find(class_="preface group")
        return self._preface_div

    @property
    def _chapter(self):
        if not hasattr(self, "_chapter_div"):
            chaps = self.soup.select("div#chapters > div")
            assert len(chaps) == 1
            self._chapter_div = chaps[0]
        return self._chapter_div

    @property
    def title(self):
        elt = self._chapter.find(class_="title")
        if not elt:
            elt = self.soup.find(class_="title")
        return elt.text.strip()

    @property
    def text(self):
        if not hasattr(self, "_text"):
            cs = self.soup.find(role="article").contents

            def is_null(s):
                if not isinstance(s, str):
                    return False
                return not s.strip()

            while is_null(cs[0]):
                cs.pop(0)

            t = cs[0]
            if t.name == "h3" and t.text.strip() == "Chapter Text":
                cs.pop(0)

            while is_null(cs[0]):
                cs.pop(0)

            self._text = cs
        return gather_bits(self._text)

    def _handle_note(self, note):
        head = note.find("h3")
        title = stripright(head.text.strip(), ":")
        rest = []
        for thing in head.find_next_siblings():
            if thing.name.lower() == "blockquote":
                rest.extend(thing.contents)
            else:
                rest.append(thing)
        return (title, gather_bits(rest))

    @property
    def notes_pre(self):
        if not hasattr(self, "_notes_pre"):
            notes = []

            for div in self._preface.find_all(role="complementary"):
                bq = div.find("blockquote")
                if bq:
                    content = gather_bits(bq.contents)
                    title = stripright(div.find("h3").text.strip(), ":")
                    notes.append((title, content))

            notes += [
                self._handle_note(note)
                for note in self._chapter.select(".preface .notes:not(.end)")
            ]
            self._notes_pre = notes

        return self._notes_pre

    @property
    def notes_post(self):
        if not hasattr(self, "_notes_post"):
            self._notes_post = [
                self._handle_note(note)
                for note in self._chapter.select(".preface .notes.end")
            ]
        return self._notes_post
