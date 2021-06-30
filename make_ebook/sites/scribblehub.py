import re
from urllib.parse import urljoin, urlparse
import warnings

from bs4 import Tag

from ..helpers import cached, futures, gather_bits, hashify, soupify_request
from .base import Chapter, Extra, Story
from .registry import register


series_re = re.compile(r"^/series/(\d+)/([^/]+)/")
chapter_re = re.compile(r"^/read/(\d+)-([^/]+)/chapter/(\d+)/$")
series_fmt = "https://www.scribblehub.com/series/{}/{}/"
sh_chapter_fmt = "https://www.scribblehub.com/read/{}-{}/chapter/{}"

_sh_extras = {}

emoji_css = None
emoji_map = {}
emoji_css_url = (
    "https://www.scribblehub.com/wp-content/themes/writeit-child/js/fic_emojis.css"
)
emoji_loc_re = re.compile(r"background:\s*url\(([^)]+)\)")


def get_sh_emoji_url(name):
    global emoji_css
    if name not in emoji_map:
        if emoji_css is None:
            r = cached.get(emoji_css_url)
            if not r.ok:
                raise IOError("Error: {}".format(r.status_code))
            emoji_css = r.text

        header = ".{}{{".format(name)
        start = emoji_css.index(header)
        end = emoji_css.index("}", start)
        block = emoji_css[start + len(header) : end]
        url = emoji_loc_re.search(block).group(1)
        emoji_map[name] = urljoin(emoji_css_url, url)

    return emoji_map[name]


def get_sh_extra(url):
    if url not in _sh_extras:
        _sh_extras[url] = ScribbleHubExtra(url)
    return _sh_extras[url]


class ScribbleHubExtra(Extra):
    def __init__(self, url):
        self.url = url
        super(ScribbleHubExtra, self).__init__(url, hashify(url))


@register(domain="scribblehub.com")
class ScribbleHubStory(Story):
    publisher = "scribblehub.com"
    author = chapters = title = None

    def __init__(self, id, slug=None):
        super(ScribbleHubStory, self).__init__()

        if "scribblehub.com/" in id:
            r = urlparse(id)
            assert r.netloc in {"scribblehub.com", "www.scribblehub.com"}
            m = series_re.match(r.path)
            if m:
                id, slug = m.groups()
            else:
                m = chapter_re.match(r.path)
                if m:
                    id, slug, _ = m.groups()
                else:
                    raise ValueError("Can't parse url {!r}".format(id))

        self.id = int(id)
        self.slug = slug
        self.url = series_fmt.format(self.id, self.slug)

        p = soupify_request(futures.get(self.url))
        self.author = p.select_one(".auth_name_fic").text.strip()
        self.title = p.select_one(".fic_title").text.strip()
        self.cover_img = get_sh_extra(p.select_one(".fic_image img").attrs["src"])
        self.cover_img.attrs["properties"] = "cover-image"

        chaps_ul = soupify_request(
            futures.post(
                "https://www.scribblehub.com/wp-admin/admin-ajax.php",
                data={
                    "action": "wi_gettocchp",
                    "strSID": self.id,
                    "strmypostid": "0",
                    "strFic": "yes",
                },
            )
        )
        self.chapters = [
            ScribbleHubChapter(a.attrs["href"], gather_bits([a.attrs["title"]]))
            for a in reversed(chaps_ul.select(".li_toc a"))
        ]

    def __repr__(self):
        return "ScribbleHubStory({!r})".format(self.id)

    @property
    def extra(self):
        extra_urls = set()
        for chap in self.chapters:
            extra_urls.update(chap.get_extra_urls())
        return [self.cover_img] + [get_sh_extra(url) for url in extra_urls]


class ScribbleHubChapter(Chapter):
    title = None

    def __init__(self, url, title):
        self.url = url
        self.title = title
        self.series_id, self.slug, self.chapter_id = chapter_re.match(
            urlparse(url).path
        ).groups()
        self.id = "{}_{}".format(self.series_id, self.chapter_id)
        self.req = futures.get(self.url)
        self.comments_req = futures.post(
            "https://www.scribblehub.com/wp-admin/admin-ajax.php",
            data=dict(
                action="wi_getcomment_pagination_chapters",
                pagenum=1,
                comments_perpage=100,
                mypostid=self.chapter_id,
            ),
        )
        self.toc_extra = ""
        self.extra_urls = set()

    def __repr__(self):
        return "ScribbleHubChapter({!r}, {!r})".format(self.url, self.title)

    @property
    def soup(self):
        if not hasattr(self, "_soup"):
            self._soup = soupify_request(self.req)
        return self._soup

    @property
    def comments_soup(self):
        if not hasattr(self, "_comments_soup"):
            self._comments_soup = soupify_request(self.comments_req)
        return self._comments_soup

    def get_extra_urls(self):
        # make sure we've processed everything
        self.text
        self.notes_pre
        self.notes_post
        return self.extra_urls

    def handle_extras(self, soup):
        for x in soup.find_all(True, {"src": True}):
            if x.attrs["src"].startswith("extra-"):
                continue

            matches = [c for c in x.get("class", []) if c.startswith("mceSmilieSprite")]
            if len(matches) >= 2:
                klass = next(c for c in matches if c != "mceSmilieSprite")
                url = get_sh_emoji_url(klass)
            else:
                url = x.attrs["src"]
            self.extra_urls.add(url)
            x.attrs["src"] = get_sh_extra(url).name
        return soup

    @property
    def text(self):
        if not hasattr(self, "_text"):
            self._text = gather_bits(
                [
                    self.handle_extras(bit)
                    for bit in self.soup.select_one("#chp_raw")
                    if isinstance(bit, Tag)
                    and not any(c.startswith("wi_") for c in bit.get("class", []))
                ]
            )
        return self._text

    def handle_note(self, block, clsname):
        if clsname == "wi_news":
            return (
                gather_bits(block.select_one(".wi_news_title")),
                gather_bits(self.handle_extras(block.select_one(".wi_news_body"))),
            )
        elif clsname == "wi_authornotes":
            return (
                "Author's Note",
                gather_bits(
                    self.handle_extras(block.select_one(".wi_authornotes_body"))
                ),
            )
        else:
            raise ValueError("unknown class {}".format(clsname))

    def find_notes(self, entries, cutoff=5):
        notes = []
        for chunk, i in zip(entries, range(cutoff)):
            if isinstance(chunk, Tag):
                classes = chunk.get("class", [])
                c = next((c for c in classes if c.startswith("wi_")), None)
                if c:
                    notes.append(self.handle_note(chunk, c))
        return notes

    @property
    def notes_pre(self):
        if not hasattr(self, "_notes_pre"):
            self._notes_pre = self.find_notes(self.soup.select_one("#chp_raw").contents)
        return self._notes_pre

    @property
    def notes_post(self):
        if not hasattr(self, "_notes_post"):
            backwards = reversed(self.soup.select_one("#chp_raw").contents)
            self._notes_post = list(reversed(self.find_notes(backwards)))

            # TODO: actually handle pagination and replies?
            comments = []
            for c in self.comments_soup.select(".comment-body"):
                body = c.select_one(".comment")
                for b in body.select("div.cmtquote"):
                    text = b.select_one(".profilereportpop_quote_qt")
                    text.name = "blockquote"
                    text.attrs = {}
                    b.replace_with(text)

                cl = next(cl for cl in c["class"] if cl.startswith("depth_"))
                depth = int(cl[len("depth_") :])

                comments.append(
                    f"""<div style='margin-left: {(depth - 1) * 2}em'>
                          <h3>
                            <b>{c.select_one(".comment-author .fn").text.strip()}</b>
                            ({c.select_one(".com_date").text.strip()})
                          </h3>
                          {
                            gather_bits(
                                self.handle_extras(c.select_one(".comment")).contents
                            ).strip()
                          }
                        </div>"""
                )
            if comments:
                self._notes_post.append(
                    ("{} comments".format(len(comments)), "\n".join(comments))
                )

        return self._notes_post
