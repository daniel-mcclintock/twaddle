import logging
from datetime import datetime, timedelta

import twint
from peewee import Model, CharField, SqliteDatabase

from orm import PeeweeManager

logger = logging.getLogger(__name__)
DATABASE = SqliteDatabase("twats.db")


class Twat(Model):
    username = CharField(primary_key=True)
    name = CharField(null=True)

    class Meta:
        database = DATABASE
        table_name = "twats"


def get_orm_manager():
    return PeeweeManager(DATABASE, [Twat])


def get_tweets(twat, limit=10):
    c = twint.Config()

    c.Username = twat.replace("@", "")
    c.Pandas = True
    c.Hide_output = True
    c.Limit = limit
    c.Since = (datetime.today() - timedelta(hours=1000)).strftime(
        "%Y-%m-%d %H:%M:%S"
    )

    twint.run.Search(c)

    for index, tweet in twint.storage.panda.Tweets_df.sort_values(
        by=["date"],
        axis=0,
        ascending=True,
    ).iterrows():
        yield tweet
