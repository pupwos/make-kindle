#!/usr/bin/env python
# Partially, loosely, based on https://github.com/hrroon/literoticapi/.
# That's GPL, so this is too.

# pip install -r requirements.txt

from __future__ import print_function, unicode_literals

from functools import partial
import HTMLParser
import os
import re
import subprocess

from bs4 import BeautifulSoup
from cachecontrol import CacheControl
from cachecontrol.caches import FileCache
from cachecontrol.heuristics import ExpiresAfter
import jinja2
import requests
from requests_futures.sessions import FuturesSession


soupify = partial(BeautifulSoup, features='html5lib')

cached = CacheControl(requests.Session(), heuristic=ExpiresAfter(hours=1),
                      cache=FileCache('.webcache'))
futures = FuturesSession(session=cached, max_workers=5)


class Story(object):
    def __init__(self, id):
        if 'literotica.com/' in id:
            pat = r'https?:\/\/(?:www\.)?literotica.com/s/([^\?]*)\??.*'
            id = re.match(pat, id).group(1)

        self.id = unicode(id)
        self.url = "https://www.literotica.com/s/%s" %(id)
        self._meta_dict = None

    def get_pages(self, nums):
        reqs = [futures.get('{}?page={}'.format(self.url, n)) for n in nums]

        responses = []
        for req in reqs:
            r = req.result()
            if not r.ok:
                raise IOError("Error: {}".format(r.status_code))
            responses.append(soupify(r.content))
        return responses

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
        t = HTMLParser.HTMLParser().unescape(t)
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
        d['date'] = tr.find(class_='dt').text
        if 'sl' in tr['class']:
            d['series_name'] = tr.find_previous_sibling(class_='ser-ttl').text
        else:
            d['series_name'] = None
        return d

    def text(self):
        if not getattr(self, '_text', None):
            pages = self.get_pages(xrange(1, self.num_pages + 1))

            bits = []
            for p in pages:
                div = p.find('div', class_='b-story-body-x')
                assert len(div.contents) == 1
                sub, = div.contents
                assert sub.name == 'div'
                bits.extend(sub.contents)
            self._text = '\n'.join(unicode(b) for b in bits)

        return self._text

    def __repr__(self):
        return u'Story({!r})'.format(self.id)


def get_series(story_id):
    s = Story(story_id)
    div = s.get_page(s.num_pages).find(id='b-series')
    stories = [s]
    if div:
        stories += [Story(a['href']) for a in div.findAll('a')]
    return stories


book_format = r'''
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>{{ title }}</title>
</head>
<body>

<div id="toc">
    <h2>Table of Contents</h2>
    <ul>
    {% for story in stories %}
        <li><a href="#{{ story.id }}">{{ story.title }}</a> ({{ story.date }}; {{ story.rating }})</li>
    {% endfor %}
    </ul>
</div>
<div class="pagebreak"></div>

{% for story in stories %}
    <h1 id="{{ story.id }}">{{ story.title }}</h1>

    {{ story.text() }}

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
            <dc:Title>{{ title }}</dc:Title>
            <dc:Language>en</dc:Language>
            <dc:Creator>{{ author }}</dc:Creator>
            <dc:Copyrights>Copyright by the author</dc:Copyrights>
            <dc:Publisher>Published on Literotica.com</dc:Publisher>
        </dc-metadata>
    </metadata>
    <manifest>
        <item id="content" media-type="text/x-oeb1-document" href="content.html"></item>
        <item id="ncx" media-type="application/x-dtbncx+xml" href="toc.ncx"/>
        <item id="text" media-type="text/x-oeb1-document" href="content.html"></item>
    </manifest>
    <spine toc="ncx">
        <itemref idref="content"/>
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
         <text>{{ title }}</text>
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
        {% for story in stories %}
        <navPoint id="{{ story.id }}" playOrder="{{ loop.index + 1 }}">
            <navLabel>
                <text>{{ story.title }}</text>
            </navLabel>
            <content src="content.html#{{ story.id }}" />
        </navPoint>
        {% endfor %}
    </navMap>
</ncx>
'''.strip()


def make_mobi(url, out_name=None):
    stories = get_series(url)
    first = stories[0]

    if first.series_name:
        title = first.series_name[:first.series_name.rfind(':')]

    if out_name is None:
        out_name = first.id
    os.makedirs(out_name)

    d = dict(out_name=out_name, title=title, stories=stories,
             author=first.author)

    for name, template in [('toc.ncx', toc_format),
                           ('{}.opf'.format(out_name), opf_format),
                           ('content.html', book_format)]:
        with open(os.path.join(out_name, name), 'w') as f:
            for bit in jinja2.Template(template).stream(**d):
                f.write(bit.encode('utf-8'))

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
