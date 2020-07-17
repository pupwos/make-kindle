import io
import os
import shutil
import subprocess
import sys

import jinja2


book_format = r"""
<!doctype html>
<html lang="en">
<head>
    <meta charset="utf-8" />
    <title>{{ story.title }}</title>
    <style type="text/css">
        .pagebreak { page-break-before: always; }

        h1, h2 { text-align: center; }
        .notelink { text-align: center; font-size: 70%; margin: 2ex; }
    </style>
</head>
<body>

<div id="toc">
    <h1>Table of Contents</h1>
    <ul>
        {% for chap in story.chapters %}
            <li><a href="#{{ chap.id }}">{{ chap.title }}</a> {{ chap.toc_extra }}</li>
        {% endfor %}
        {% if story.any_notes %}
            <li><a href="#notes">Notes</a></li>
        {% endif %}
    </ul>
</div>
<div class="pagebreak"></div>

<div id="book-start"></div>
{% for chap in story.chapters %}
    <h1 id="{{ chap.id }}">{{ chap.title }}</h1>
    {% for name, text in chap.notes_pre %}
        {% with key = "note-{}-pre-{}".format(chap.id, loop.index) %}
            <div class="notelink">
                <a id="source-{{ key }}" href="#{{ key }}"
                   epub:type="noteref">{{ name }}</a>
            </div>
        {% endwith %}
    {% endfor %}

    {{ chap.text }}

    {% for name, text in chap.notes_post %}
        {% with key = "note-{}-post-{}".format(chap.id, loop.index) %}
            <div class="notelink">
                <a id="source-{{ key }}" href="#{{ key }}"
                   epub:type="noteref">{{ name }}</a>
            </div>
        {% endwith %}
    {% endfor %}

    <div class="pagebreak"></div>
{% endfor %}

{% if story.any_notes %}
    <h1 id="notes">Notes</h1>
    {% for chap in story.chapters %}
        {% for name, text in chap.notes_pre %}
            {% with key = "note-{}-pre-{}".format(chap.id, loop.index) %}
                <aside id="{{ key }}" epub:type="footnote">
                    <a epub:type="noteref" href="#source-{{ key }}"
                        >{{ chap.title}}: {{ name }}</a>
                    {{ text }}
                </aside>
                <hr/>
            {% endwith %}
        {% endfor %}
        {% for name, text in chap.notes_post %}
            {% with key = "note-{}-post-{}".format(chap.id, loop.index) %}
                <aside id="{{ key }}" epub:type="footnote">
                    <a epub:type="noteref" href="#source-{{ key }}"
                        >{{ chap.title}}: {{ name }}</a>
                    {{ text }}
                </aside>
                <hr/>
            {% endwith %}
        {% endfor %}
        {% if not loop.last %}<div class="pagebreak"></div>{% endif %}
    {% endfor %}
{% endif %}

</body>
</html>
""".strip()

opf_format = r"""
<?xml version="1.0" encoding="iso-8859-1"?>
<package unique-identifier="uid"
         xmlns:opf="http://www.idpf.org/2007/opf"
         xmlns:asd="http://www.idpf.org/asdfaf">
    <metadata>
        <dc-metadata xmlns:dc="http://purl.org/metadata/dublin_core"
                     xmlns:oebpackage="http://openebook.org/namespaces/oeb-package/1.0/">
            <dc:Title>{{ story.title }}</dc:Title>
            <dc:Language>en</dc:Language>
            <dc:Creator>{{ story.author }}</dc:Creator>
            <dc:Copyrights>Copyright by the author</dc:Copyrights>
            <dc:Publisher>Published on {{ story.publisher }}</dc:Publisher>
        </dc-metadata>
    </metadata>
    <manifest>
        <item id="ncx" media-type="application/x-dtbncx+xml" href="toc.ncx" />
        <item id="text" media-type="text/x-oeb1-document" href="content.html" />
        {% for extra in story.extra %}
          <item id="{{ extra.id }}"
                media-type="{{ extra.mimetype }}"
                href="{{ extra.name }}"
                {{ extra.extra_attrs }} />
        {% endfor %}
    </manifest>
    <spine toc="ncx">
        <itemref idref="text"/>
    </spine>
    <guide>
        <reference type="toc" title="Table of Contents" href="content.html#toc"/>
        <reference type="text" title="Book" href="content.html#book-start"/>
        <reference type="notes" title="Notes" href="content.html#notes"/>
    </guide>
</package>
""".strip()

toc_format = r"""
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
        {% if story.any_notes %}
        <navPoint id="notes" playOrder="{{ story.chapters|length + 2 }}">
            <navLabel><text>Notes</text></navLabel>
            <content src="content.html#notes" />
        </navPoint>
        {% endif %}
    </navMap>
</ncx>
""".strip()


def make_mobi(story, out_name=None, move_to=None):
    if out_name is None:
        out_name = story.default_out_name
    os.makedirs(out_name)

    env = jinja2.Environment(undefined=jinja2.StrictUndefined)
    d = {"out_name": out_name, "story": story}
    for name, template in [
        ("toc.ncx", toc_format),
        ("{}.opf".format(out_name), opf_format),
        ("content.html", book_format),
    ]:
        with io.open(os.path.join(out_name, name), "w") as f:
            for bit in env.from_string(template).stream(**d):
                f.write(bit)

    for extra in story.extra:
        with io.open(os.path.join(out_name, extra.name), "wb") as f:
            f.write(extra.content)

    # print("Output will be in {}/{}.mobi".format(out_name, out_name))
    ret = subprocess.call(
        ["kindlegen", "-c1", os.path.join(out_name, "{}.opf".format(out_name))]
    )

    out_path = "{n}/{n}.mobi".format(n=out_name)

    if ret != 0:
        if not os.path.exists(out_path):
            print("ERROR: {}".format(ret), file=sys.stderr)
            sys.exit(ret)

        print("WARNING: return code {}; proceeding anyway".format(ret), file=sys.stderr)

    if move_to is not None:
        dest = os.path.join(move_to, "{}.mobi".format(out_name))
        shutil.move(out_path, dest)
        shutil.rmtree(out_name)
        print("Output in {}".format(dest))
