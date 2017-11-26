#!/usr/bin/env python
# Partially, loosely, based on https://github.com/hrroon/literoticapi/.
# That's GPL, so this is too.

# pip install -r requirements.txt

from __future__ import print_function, unicode_literals

import io
import os
import re
import subprocess
import unicodedata
from collections import namedtuple
from functools import partial

from bs4 import BeautifulSoup, Comment
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter
import jinja2
import requests
from requests_futures.sessions import FuturesSession
from six import text_type
from six.moves import html_parser, map, range
from six.moves.urllib import parse


soupify = partial(BeautifulSoup, features='html5lib')

cached = CacheControl(requests.Session(), heuristic=ExpiresAfter(hours=1),
                      cache=FileCache('.webcache'))
futures = FuturesSession(session=cached, max_workers=5)


def soupify_request(req):
    r = req.result()
    if not r.ok:
        raise IOError("Error: {}".format(r.status_code))
    return soupify(r.content)

# Chapter should have properties: id, title, toc_extra, text
# Story should have id, author, title, publisher, chapters

################################################################################
### literotica

class LitStory(object):
    def __init__(self, id):
        if 'literotica.com/' in id:
            pat = r'https?:\/\/(?:www\.)?literotica.com/s/([^\?]*)\??.*'
            id = re.match(pat, id).group(1)

        self.id = text_type(id)
        self.url = "https://www.literotica.com/s/{}".format(self.id)
        self._meta_dict = None

    def get_pages(self, nums):
        reqs = [futures.get('{}?page={}'.format(self.url, n)) for n in nums]
        return [soupify_request(req) for req in reqs]

    def get_page(self, num):
        return self.get_pages([num])[0]

    author      = property(lambda self: self._meta()['author'])
    author_link = property(lambda self: self._meta()['author_link'])
    title       = property(lambda self: self._meta()['title'])
    category    = property(lambda self: self._meta()['category'])
    description = property(lambda self: self._meta()['description'])
    num_pages   = property(lambda self: self._meta()['num_pages'])
    rating      = property(lambda self: self._meta()['rating'])
    date        = property(lambda self: self._meta()['date'])
    series_name = property(lambda self: self._meta()['series_name'])

    def _meta(self):
        if self._meta_dict:
            return self._meta_dict

        self._meta_dict = d = {}
        p = self.get_page(1)

        author_link = p.find('span', class_='b-story-user-y').find('a')
        d['author'] = author_link.get_text()
        d['author_link'] = author_link['href']

        t = p.find('title').get_text()
        t = html_parser.HTMLParser().unescape(t)
        # rip out " - Literotica.com"
        d['title'], d['category'] = t[:-17].rsplit(' - ', 1)

        d['description'] = p.find(
            'meta', {'name': 'description'})['content']

        s = p.find('span', class_='b-pager-caption-t').text
        d['num_pages'] = int(re.match('(\d+) Pages?:?$', s).group(1))

        r = cached.get(d['author_link'])
        if not r.ok:
            raise IOError("Error: {}".format(r.status_code))
        author_page = soupify(r.content)
        a = author_page.find('a', href=lambda s: self.id in s)
        d['rating'] = re.match('.*\(([\d\.]+)\)', a.next_sibling).group(1)
        tr = a.find_parent('tr')

        dt = tr.find(class_='dt')  # in series
        if dt is None:
            dt = tr.find_all('td')[-1]
        d['date'] = dt.text

        if 'sl' in tr['class']:
            d['series_name'] = tr.find_previous_sibling(class_='ser-ttl').text
        else:
            d['series_name'] = None
        return d

    @property
    def text(self):
        if not getattr(self, '_text', None):
            pages = self.get_pages(range(1, self.num_pages + 1))

            bits = []
            for p in pages:
                div = p.find('div', class_='b-story-body-x')
                assert len(div.contents) == 1
                sub, = div.contents
                assert sub.name == 'div'
                bits.extend(sub.contents)
            self._text = '\n'.join(text_type(b) for b in bits)

        return self._text

    @property
    def toc_extra(self):
        return "({}; {})".format(self.date, self.rating)

    def __repr__(self):
        return 'Story({!r})'.format(self.id)


class LitSeries(object):
    publisher = 'Literotica.com'

    def __init__(self, first_story_id):
        self.first = s = LitStory(first_story_id)
        div = s.get_page(s.num_pages).find(id='b-series')
        self.chapters = [s]
        if div:
            self.chapters += [LitStory(a['href']) for a in div.findAll('a')]
        self.extra = []

    @property
    def title(self):
        if self.first.series_name:
            return self.first.series_name[:self.first.series_name.rfind(':')]
        else:
            return self.first.title

    @property
    def author(self):
        return self.first.author

    @property
    def id(self):
        return self.first.id


################################################################################
### tgstorytime
# NOTE: tgstorytime has epubs:
# http://www.tgstorytime.com/modules/epubversion/epubs/4189/all/Recovery.epub
# But might as well do it this way for consistency.

# their https cert is broken :|
tgs_url_fmt = ("http://www.tgstorytime.com/viewstory.php?sid={}&chapter={}"
               "&ageconsent=ok")

# TODO: story / chapter notes, metadata, ...

class TGSChapter(object):
    def __init__(self, req, id, title):
        self.req = req
        self.id = id
        self.title = title

    @property
    def soup(self):
        if not hasattr(self, '_soup'):
            self._soup = soupify_request(self.req)
        return self._soup

    @property
    def toc_extra(self):
        return ''

    @property
    def text(self):
        div = self.soup.find('div', id='story')
        sub, = div.contents
        assert sub.name == 'span'
        return '\n'.join(map(str, sub.contents))

    def __repr__(self):
        return 'TGSChapter<{}, chapter={}>'.format(self.title, self.id)


class TGSStory(object):
    publisher = 'tgstorytime.com'

    def __init__(self, id):
        if 'tgstorytime.com/' in id:
            r = parse.urlparse(id)
            assert r.netloc in {'www.tgstorytime.com', 'tgstorytime.com'}
            assert r.path == '/viewstory.php'
            qs = parse.parse_qs(r.query)
            id, = map(int, qs['sid'])

        self.id = id

        p = soupify_request(self.req_chapter(1))

        self.title, self.author = [
            a.text for a in
            p.find('div', id='pagetitle').find_all('a', recursive=False)]

        ct = {}
        for o in p.find('div', class_='jumpmenu').find_all('option'):
            n = int(o.attrs['value'])
            pre = '{}. '.format(n)
            assert o.text.startswith(pre)
            ct[n] = o.text[len(pre):]
        chaps = range(1, len(ct) + 1)
        assert set(ct) == set(chaps)

        self.chapters = [TGSChapter(req, n, ct[n])
                         for n, req in zip(chaps, self.req_chapters(chaps))]
        self.extra = []

    def req_chapters(self, chapters):
        return [futures.get(tgs_url_fmt.format(self.id, c)) for c in chapters]

    def req_chapter(self, chapter):
        return next(iter(self.req_chapters([chapter])))

    def __repr__(self):
        return 'TGSStory({})'.format(self.id)


################################################################################
### fictionmania.tv

# TODO: SWI support

fm_urls = {
    'x': 'https://fictionmania.tv/stories/readxstory.html?storyID={}',
    'html': 'https://fictionmania.tv/stories/readhtmlstory.html?storyID={}',
}

FMChapter = namedtuple('FMChapter', 'id title toc_extra text')


class FMExtra(object):
    def __init__(self, n, path):
        self.n = n
        self.path = path
        self.name = 'extra-{}{}'.format(n, os.path.splitext(path)[1])
        self.url = 'https://fictionmania.tv' + path
        self.req = futures.get(self.url)

    @property
    def result(self):
        r = self.req.result()
        if not r.ok:
            raise IOError("Error on {}: {}".format(self.url, r.status_code))
        return r

    @property
    def mimetype(self):
        return self.result.headers['Content-Type']

    @property
    def content(self):
        return self.result.content

    @property
    def id(self):
        return 'extra-{}'.format(self.n)


class FMStory(object):
    publisher = 'fictionmania.tv'

    def __init__(self, id, mode=None):
        if 'fictionmania.tv' in id:
            r = parse.urlparse(id)
            assert r.netloc == 'fictionmania.tv'
            if r.path == '/stories/readxstory.html':
                if mode is None:
                    mode = 'x'
            elif r.path == '/stories/readhtmlstory.html':
                if mode is None:
                    mode = 'html'
            else:
                raise ValueError("bad URL {}".format(r.path))

            qs = parse.parse_qs(r.query)
            id, = map(int, qs['storyID'])

        self.id = id
        if mode is None:
            mode = 'x'
        self.mode = mode

        url = fm_urls[mode].format(id)

        p = soupify_request(futures.get(url))

        if mode == 'x':
            h2, = p.find_all('h2')
            self.title = h2.text

            self.author = p.select_one(
                'a[href^="/searchdisplay/authordisplay.html?"]').text

            hrs = p.find_all('hr')
            end = hrs[-2].parent
            bits = []
            for tag in hrs[0].next_siblings:
                if tag is end:
                    break
                bits.append(tag)
            else:
                raise ValueError("hr structure was surprising")
            self.extra = []
        elif mode == 'html':
            menu = p.find('div', id='menu')

            self.title = menu.find_next_sibling('p').find('font').text

            tab = menu.find_next_sibling('table')
            self.author = tab.select_one(
                'a[href^="/searchdisplay/authordisplay.html?"]').text

            div = tab.find_next_sibling('div')

            self.extra = []
            for i, x in enumerate(div.find_all(True, {'src': True})):
                ex = FMExtra(i, x.attrs['src'])
                self.extra.append(ex)
                x.attrs['src'] = ex.name

            bits = div.contents
        else:
            raise ValueError("bad mode {}".format(mode))

        text = '\n'.join([
            unicodedata.normalize('NFKC', text_type(b))
            for b in bits if not isinstance(b, Comment)
        ]).strip()

        self.chapters = [
            FMChapter(id=1, title=self.title, toc_extra='', text=text)
        ]


# Chapter should have properties: id, title, toc_extra, text
# Story should have author, chapters


################################################################################
### kindle generation and main logic

def get_story(url):
    if 'literotica.com' in url:
        return LitSeries(url)
    elif 'tgstorytime.com' in url:
        return TGSStory(url)
    elif 'fictionmania.tv' in url:
        return FMStory(url)
    else:
        raise ValueError("can't parse url {}".format(url))


book_format = r'''
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>{{ story.title }}</title>
</head>
<body>

<div id="toc">
    <h2>Table of Contents</h2>
    <ul>
    {% for chap in story.chapters %}
        <li><a href="#{{ chap.id }}">{{ chap.title }}</a> {{ chap.toc_extra }}</li>
    {% endfor %}
    </ul>
</div>
<div class="pagebreak"></div>

{% for chap in story.chapters %}
    <h1 id="{{ chap.id }}">{{ chap.title }}</h1>

    {{ chap.text }}

    {% if not loop.last %}
        <div class="pagebreak"></div>
    {% endif %}
{% endfor %}
</body>
</html>
'''.strip()

opf_format = r'''
<?xml version="1.0" encoding="iso-8859-1"?>
<package unique-identifier="uid" xmlns:opf="http://www.idpf.org/2007/opf" xmlns:asd="http://www.idpf.org/asdfaf">
    <metadata>
        <dc-metadata  xmlns:dc="http://purl.org/metadata/dublin_core" xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">
            <dc:Title>{{ story.title }}</dc:Title>
            <dc:Language>en</dc:Language>
            <dc:Creator>{{ story.author }}</dc:Creator>
            <dc:Copyrights>Copyright by the author</dc:Copyrights>
            <dc:Publisher>Published on {{ story.publisher }}</dc:Publisher>
        </dc-metadata>
    </metadata>
    <manifest>
        <item id="toc" media-type="application/x-dtbncx+xml" href="toc.ncx" />
        <item id="text" media-type="text/x-oeb1-document" href="content.html" />
        {% for extra in story.extra %}
          <item id="{{ extra.id }}" media-type="{{ extra.mimetype }}" href="{{ extra.name }}" />
        {% endfor %}
    </manifest>
    <spine toc="ncx">
        <itemref idref="toc"/>
        <itemref idref="text"/>
    </spine>
    <guide>
        <reference type="toc" title="Table of Contents" href="content.html"/>
        <reference type="text" title="Book" href="content.html"/>
    </guide>
</package>
'''.strip()

toc_format = r'''
<?xml version="1.0"?>
<!DOCTYPE ncx PUBLIC "-//NISO//DTD ncx 2005-1//EN"
 "http://www.daisy.org/z3986/2005/ncx-2005-1.dtd">
 <ncx xmlns="http://www.daisy.org/z3986/2005/ncx/" version="2005-1">
     <head>
     </head>
     <docTitle>
         <text>{{ story.title }}</text>
     </docTitle>
     <navMap>
        <navPoint id="toc" playOrder="1">
            <navLabel>
                <text>
                    Table of Contents
                </text>
            </navLabel>
            <content src="content.html#toc" />
        </navPoint>
        {% for chapter in story.chapters %}
        <navPoint id="{{ chapter.id }}" playOrder="{{ loop.index + 1 }}">
            <navLabel>
                <text>{{ chapter.title }}</text>
            </navLabel>
            <content src="content.html#{{ chapter.id }}" />
        </navPoint>
        {% endfor %}
    </navMap>
</ncx>
'''.strip()


def make_mobi(url, out_name=None):
    story = get_story(url)

    if out_name is None:
        out_name = text_type(story.id)
    os.makedirs(out_name)

    d = {'out_name': out_name, 'story': story}
    for name, template in [('toc.ncx', toc_format),
                           ('{}.opf'.format(out_name), opf_format),
                           ('content.html', book_format)]:
        with io.open(os.path.join(out_name, name), 'w') as f:
            for bit in jinja2.Template(template).stream(**d):
                f.write(bit)

    for extra in story.extra:
        with io.open(os.path.join(out_name, extra.name), 'wb') as f:
            f.write(extra.content)

    subprocess.check_call([
        'kindlegen', '-c1', os.path.join(out_name, '{}.opf'.format(out_name))])


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('url')
    parser.add_argument('out_name', nargs='?')
    args = parser.parse_args()
    make_mobi(**vars(args))


if __name__ == '__main__':
    main()
