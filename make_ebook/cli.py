import os

from .formats import make_mobi
from .sites import get_story


def default_move_to():
    paths = ["/Volumes/Kindle/documents", "."]
    for pth in paths:
        if os.path.exists(pth) and os.access(pth, os.W_OK | os.X_OK):
            return pth
    return None


def main():
    import argparse

    parser = argparse.ArgumentParser()
    parser.add_argument("url")
    parser.add_argument("out_name", nargs="?")

    g = parser.add_mutually_exclusive_group()
    g.add_argument("--move-to", "-m", default=default_move_to())
    g.add_argument("--no-move", dest="move_to", action="store_const", const=None)
    args = parser.parse_args()

    story = get_story(args.url)
    make_mobi(story, out_name=args.out_name, move_to=args.move_to)
