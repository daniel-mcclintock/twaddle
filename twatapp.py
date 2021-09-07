#!/bin/env python
from time import sleep
from os import get_terminal_size
from twat import get_orm_manager
from ui import (
    Align,
    Container,
    Content,
    HIDE_CURSOR,
    SHOW_CURSOR,
    getpos,
)

get_orm_manager().migrate()

c = Container("Fucking Twats!")
c.footer = [
    Content("hjkl: cursor", align=Align.CENTER),
    Content("d: crash", align=Align.CENTER),
    Content("f: follow", align=Align.CENTER),
    Content("r: refresh", align=Align.CENTER),
    Content("q: quit", align=Align.CENTER),
]

print(HIDE_CURSOR)

exit_text = c.loop()

x, y = get_terminal_size()

for _ in range(0, y, 1):
    print(getpos(x, y, ""))
    sleep(1 / 60)

print(exit_text)
print(SHOW_CURSOR)
