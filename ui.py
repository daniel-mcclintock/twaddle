import arrow
import math
import os
import re
import sys
import termios
import threading
import time
import tty
from enum import Enum, auto
from multiprocessing import Pool

from twat import Twat, get_tweets

BORDERS = ["╒", "═", "╕", "│", "╰", "╯", "─"]
NO_BORDERS = [" ", " ", " ", " ", " ", " ", " "]
HIDE_CURSOR = "\033[?25l"
SHOW_CURSOR = "\033[?25h"
CLEAR_SCREEN = "\033[2J"
INVERSE_COLORS = "\033[7m"
NORMAL_COLORS = "\033[27m"
RESET_MODE = "\033[0m"
BOLD = "\033[1m"
UNDERLINE = "\033[4m"
NO_UNDERLINE = "\033[24m"

ALL_ESCAPE_SEQUENCES = [
    HIDE_CURSOR,
    SHOW_CURSOR,
    CLEAR_SCREEN,
    INVERSE_COLORS,
    NORMAL_COLORS,
    RESET_MODE,
    BOLD,
    UNDERLINE,
    NO_UNDERLINE,
]

MAX_TWAT_HANDLE_LEN = 20


class Align(Enum):
    LEFT = auto()
    CENTER = auto()
    RIGHT = auto()


def set_terminal():
    fd = sys.stdin.fileno()
    old_settings = termios.tcgetattr(fd)
    tty.setraw(sys.stdin.fileno())
    return fd, old_settings


def restore_terminal(fd, old_settings):
    termios.tcsetattr(fd, termios.TCSADRAIN, old_settings)


def getch():
    fd, old_settings = set_terminal()
    try:
        c = sys.stdin.read(1)
    finally:
        restore_terminal(fd, old_settings)

    return c


# TODO: Rename this
def getpos(x, y, msg):
    return f"\033[{y};{x}H{msg}"


def render_border(_min, _max, borders, title=None):
    bb = ""
    # Border corners
    #
    #  x        x
    #
    #
    #
    #  x        x
    #
    bb += getpos(_min[0], _min[1], borders[0])
    bb += getpos(_max[0], _min[1], borders[2])
    bb += getpos(_min[0], _max[1], borders[4])
    bb += getpos(_max[0], _max[1], borders[5])

    # X Lines
    #
    #   xxxxxxxx
    #
    #
    #
    #   xxxxxxxx
    #
    if title:
        title = f" {title} "
        title_start = (
            math.floor((_max[0] - (_min[0])) / 2) + _min[0]
        ) - math.floor((len(title)) / 2)
        title_i = 0

    for x in range(_min[0] + 1, _max[0], 1):
        if title and x >= title_start and title_i < len(title):
            bb += getpos(x, _min[1], title[title_i])
            title_i += 1
        else:
            bb += getpos(x, _min[1], borders[1])

        bb += getpos(x, _max[1], borders[6])

    # Y Lines
    #
    #
    #  x        x
    #  x        x
    #  x        x
    #
    #
    for y in range(_min[1] + 1, _max[1], 1):
        bb += getpos(_min[0], y, borders[3])
        bb += getpos(_max[0], y, borders[3])

    return bb


def fetch_tweets(name):
    return [t for t in get_tweets(name, limit=100)]


class InputModal:
    def __init__(self, title, width, height, callback, borders=BORDERS):
        self.borders = borders
        self.contents = ""
        self.title = title
        self.callback = callback
        self.width = width
        self.half_width = math.floor(width / 2)
        self.height = height
        self.half_height = math.floor(height / 2)

    def render(self):
        _max = os.get_terminal_size()
        center = (math.floor(_max[0] / 2), math.floor(_max[1] / 2))

        bb = ""
        line = " " * self.width

        for y in range(
            center[1] - self.half_height, center[1] + self.half_height, 1
        ):
            pos = (center[0] - self.half_width, y)
            bb += getpos(*pos, line)

        bb += getpos(
            center[0] - self.half_width + 2,
            center[1] - self.half_height + 2,
            self.contents,
        )

        _min = (center[0] - self.half_width, center[1] - self.half_height)
        _max = (center[0] + self.half_width, center[1] + self.half_height)
        bb += render_border(_min, _max, self.borders, self.title)

        return bb

    def input(self, key):
        if key == "\r" and self.callback:
            self.callback(self.contents)

        if re.match("[a-zA-Z0-9]", key):
            self.contents += key


class ListContainer:
    def __init__(self, title, borders=BORDERS):
        self.borders = borders
        self.contents = []
        self.window_items = []  # items renderable in this terminal size
        self.window_offset = 0  # scroll offset for this window
        self.title = title
        self.select = None
        self.focus_callback = None

    def input(self, key):
        {
            # "h": lambda: self.focus_left(),
            "j": lambda: self.focus_down(),
            "k": lambda: self.focus_up(),
            # "l": lambda: self.focus_right(),
        }[key]()

    def focus_down(self):
        if self.contents:
            if not self.select:
                self.select = self.window_items[0]
                self.select.focus = True
            else:
                window_items = self.window_items
                i = window_items.index(self.select)

                if i == len(self.contents) - 1:
                    i = -1

                window_item = window_items[i + 1]
                self.select.focus = False
                self.select = window_item
                self.select.focus = True

            if self.focus_callback:
                self.focus_callback()

    def focus_up(self):
        if self.contents:
            if not self.select:
                self.select = self.window_items[-1]
                self.select.focus = True
            else:
                window_items = self.window_items
                i = window_items.index(self.select)
                window_item = window_items[i - 1]
                self.select.focus = False
                self.select = window_item
                self.select.focus = True

            if self.focus_callback:
                self.focus_callback()

    def render(self, _min, _max):
        bb = ""

        self.window_items = self.contents

        line = -1
        for twat in self.window_items:
            line += 1

            if _min[1] + line <= _max[1]:
                new_bb = twat.render((_min[0], _min[1] + line), _max)
                if new_bb:
                    bb += new_bb

            else:
                break

        return bb


class Container:
    def __init__(self, title, borders=BORDERS):
        self.mp_pool = Pool(processes=2)
        self.title = title
        self.borders = borders

        self.set_twats()
        self.set_tweets()

        self.footer = None
        self.views = {}

        # "back-buffer"
        self.bb = ""
        self.render_loop = True

        # lolcache!?
        self.tweet_cache = {}
        self.last_getch = None
        self.modal = None

    def set_twats(self):
        self.twats = ListContainer(title="Fucking Twats!")
        self.twat_containers = {}

        self.twats.focus_callback = lambda: (
            self.render_tweets(self.twats.select.content),
            self.tweets.select.__setattr__("focus", False),
            # self.tweets.__setattr__("select", None),
            self.tweets.focus_down(),
        )

        self.refresh_twats()
        self.focus = self.twats

    def set_tweets(self):
        self.tweets = ListContainer(title="Tweets")
        self.refresh_tweets()

    def focus_left(self):
        self.focus = self.twats

        if self.tweets.select:
            self.tweets.select.focus = False
            self.tweets.select = None

        if not self.focus.select:
            self.focus.focus_down()

    def focus_right(self):
        self.focus = self.tweets

        if self.tweets.select:
            self.tweets.select.focus = False
            self.tweets.select = None

        if not self.focus.select:
            self.focus.focus_down()

    def set_modal(self, modal, new_focus):
        self.modal = modal

        if new_focus is None:
            self.focus = modal
        else:
            self.focus = new_focus

    def follow(self, handle):
        _ = Twat.get_or_create(username=handle)
        self.set_modal(None, self.twats)
        self.refresh_twats()
        self.refresh_tweets(handle)
        # Todo test username

    def remove_twat(self, handle):
        try:
            Twat.get(username=handle).delete().execute()
            self.refresh_twats()
        except:
            pass

    def input(self, key):
        try:
            self.focus.input(key)
        except:
            {
                "f": lambda: (
                    self.set_modal(
                        InputModal(
                            "Follow",
                            23,
                            4,
                            self.follow,
                        ),
                        None,
                    )
                ),
                "r": lambda: (self.set_twats(), self.set_tweets()),
                "d": lambda: self.remove_twat(
                    [t for t in self.twat_containers.keys()][self.twats.select]
                ),
                "q": lambda: self.__setattr__("render_loop", False),
                "h": lambda: self.focus_left(),
                "l": lambda: self.focus_right(),
            }.get(key, lambda: False)()

    def refresh_twats(self):
        self.twat_containers = {
            twat.username: Content(twat.username) for twat in Twat.select()
        }

        self.twats.contents = [c for c in self.twat_containers.values()]

    def refresh_tweets(self, twat=None):
        if twat and twat in self.twat_containers.keys():
            self.twat_containers[twat].spinner = 0
            self.load_tweets(twat)
        else:
            for twat in self.twat_containers.keys():
                self.twat_containers[twat].spinner = 0
                self.load_tweets(twat)

    def render_tweets(self, which_twat):
        _ = [
            "id",
            "conversation_id",
            "created_at",
            "date",
            "timezone",
            "place",
            "tweet",
            "language",
            "hashtags",
            "cashtags",
            "user_id",
            "user_id_str",
            "username",
            "name",
            "day",
            "hour",
            "link",
            "urls",
            "photos",
            "video",
            "thumbnail",
            "retweet",
            "nlikes",
            "nreplies",
            "nretweets",
            "quote_url",
            "search",
            "near",
            "geo",
            "source",
            "user_rt_id",
            "user_rt",
            "retweet_id",
            "reply_to",
            "retweet_date",
            "translate",
            "trans_src",
            "trans_dest",
        ]

        tweets = self.tweet_cache.get(which_twat, [])
        self.tweets.contents = []

        for tweet in tweets:
            date = str(arrow.get(tweet["date"]).date())
            the_tweet = str(tweet["tweet"])
            # urls = f"urls: {len(tweet['urls'])}"
            # _conversation = str(tweet["conversation_id"])
            # _video = f"vid: {tweet['video']}"
            # _photos = f"fots: {tweet['photos']}"
            # _thumb = f"thumb: {tweet['thumbnail']}"
            # _link = str(tweet["link"])

            content = ",".join(
                [
                    date,
                    the_tweet,
                ]
            )
            self.tweets.contents.append(Content(content.strip()))

    def load_tweets(self, which_twat, tweets=None):
        if tweets:
            tweets = tweets[0]
            tweets.reverse()
            self.tweet_cache[which_twat] = tweets
            self.twat_containers[which_twat].spinner = -1
        else:
            self.mp_pool.map_async(
                fetch_tweets,
                [which_twat],
                callback=lambda tweets: self.load_tweets(which_twat, tweets),
            )

    def render(self, _min=None, _max=None):
        if (_min or _max) and not all([_min, _max]):
            raise ValueError(
                "Either both _min and _max should be set or neither should be."
            )

        if not (_min and _max):
            _min = (1, 1)
            _max = os.get_terminal_size()
            _max = (_max[0], _max[1])

        self.bb = CLEAR_SCREEN

        footer_border_min = (_min[0], _max[1] - 2)
        self.bb += render_border(footer_border_min, _max, self.borders, "Key")

        if self.footer:
            footer_min = (_min[0] + 1, _max[1] - 1)
            start_x = math.floor((_max[0] - footer_min[0]) / len(self.footer))

            for content in self.footer:
                max_x = footer_min[0] + start_x
                self.bb += content.render(footer_min, (max_x, _max[1]))
                footer_min = (max_x, footer_min[1])

        max_twat_handle_len = max(
            [len(twat) + 3 for twat in self.twat_containers.keys()]
            + [len("Fucking Twats") + 6]
        )
        twats_min = (_min[0] + 2, _min[1] + 1)
        twats_max = (_min[0] + max_twat_handle_len, footer_border_min[1] - 1)
        self.bb += render_border(
            _min, twats_max, self.borders, self.twats.title
        )
        self.bb += self.twats.render(twats_min, twats_max)

        tweets_min = (_min[0] + max_twat_handle_len + 1, _min[1])
        tweets_max = (_max[0], footer_border_min[1] - 1)
        self.bb += render_border(
            tweets_min, tweets_max, self.borders, self.tweets.title
        )
        self.bb += self.tweets.render(
            (tweets_min[0] + 2, tweets_min[1] + 1),
            (tweets_max[0] - 1, tweets_max[1] - 1),
        )

        if self.modal:
            self.bb += self.modal.render()

    def loop(self):
        self.render_loop = True

        def rloop():
            while self.render_loop:
                self.render()
                print(self.bb)
                time.sleep(1 / 10)

        render_loop = threading.Thread(target=rloop)
        render_loop.start()

        exit_text = ""
        while self.render_loop:
            try:
                self.input(getch())
            except Exception as ex:
                self.render_loop = False
                exit_text = str(ex)

        render_loop.join()
        return exit_text


class Content:
    def __init__(self, content, align=Align.LEFT):
        if any(
            [check in content for check in ["\n", "\r"] + ALL_ESCAPE_SEQUENCES]
        ):
            raise ValueError("Content may not contain new line characters")

        if not isinstance(content, str):
            raise TypeError(
                f"Content is not of type 'str', {content.__class__} {content}"
            )

        self.focus = False
        self.truncate = True
        self.spinner = -1
        self.content = content
        self.align = align

    def render(self, _min, _max):

        diff = _max[0] - (_min[0] + len(self.content))

        content = self.content if diff >= 0 else self.content[:diff]
        content = self._render(content, _min, _max)

        return content

    def _render(self, in_content, _min, _max):
        inverse = INVERSE_COLORS
        normal = NORMAL_COLORS
        content = in_content

        if self.focus:
            inverse = NORMAL_COLORS
            normal = INVERSE_COLORS

        if self.spinner != -1:
            if self.spinner == len(content):
                self.spinner = 0
            content = [c for c in content]

            for i in range(0, len(content), 1):
                if self.spinner == i:
                    content[i] = inverse + content[i] + normal

            content = "".join(content)
            self.spinner += 1

        if self.align == Align.CENTER:
            offset = math.ceil(len(in_content) / 2)
            center = math.ceil((_max[0] - _min[0]) / 2)

            pos = (_min[0] + center - offset + 2, _min[1])

            return getpos(*pos, content)

        if self.align == Align.RIGHT:
            pos = (_max[0] - (len(in_content)), _min[1])
            return getpos(*pos, content)

        return normal + getpos(*_min, content) + NORMAL_COLORS
