from make_kindle import *


class TakeALemonChapter(Chapter):
    def __init__(self, id):
        self.id = id
        self.req = futures.get(f'http://www.takealemon.com/story/?p={id}')

    @property
    def result(self):
        if not hasattr(self, '_result'):
            self._result = soupify_request(self.req)
        return self._result

    @property
    def title(self):
        return gather_bits(self.result.find(rel='bookmark').text)

    @property
    def toc_extra(self):
        date, _, __ = self.result.find_all(class_='postmetadata')
        return f'({date.text.strip()})'

    @property
    def text(self):
        entry = self.result.find(class_='postentry')
        # there's a clearly-a-mistake img in chapter 54
        for x in entry.find_all('img'):
            x.extract()
        return gather_bits(
            c for c in entry.contents
            if 'adsense' not in getattr(c, 'attrs', {}).get('class', []))

    @property
    def notes_post(self):
        comments = []
        for c in self.result.find_all(class_='comment-body'):
            auth = c.find(class_='comment-author').find('cite').text
            when = c.find(class_='comment-meta').text.strip()
            text = gather_bits(s for s in c.contents
                               if s.name != 'div').strip()
            comments.append(f'<h3><b>{auth}</b> ({when})</h3>{text}')

        if not comments:
            return []
        return [(f"{len(comments)} comments", '\n'.join(comments))]

    def next_chapter(self):
        n = self.result.find(rel='next')
        if n is None:
            return None
        url = n.attrs['href']
        prefix = 'http://www.takealemon.com/story/?p='
        assert url.startswith(prefix)
        return TakeALemonChapter(int(url[len(prefix):]))


class TakeALemonStory(Story):
    id = 'take-a-lemon'
    author = 'Russell Gold'
    publisher = 'takealemon.com'
    default_out_name = 'take-a-lemon'
    title = 'Take A Lemon'
    extra = []


story = TakeALemonStory()
story.chapters = [TakeALemonChapter(3)]
l = 0
while True:
    n = story.chapters[-1].next_chapter()
    if n is None:
        break
    l = max(len(n.title), l)
    print(n.title + ' ' * (l - len(n.title)), end='\r')
    story.chapters.append(n)
print()

make_mobi(story, move_to=default_move_to())

