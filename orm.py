import os
import logging
from datetime import datetime

from peewee_migrate import Router
from peewee_migrate.router import compile_migrations

logger = logging.getLogger(__name__)


class PeeweeManager:
    def __init__(self, database, models):
        self.database = database
        self.migrations_directory = f"{os.path.dirname(__file__)}/migrations"
        self.models = models

    def makemigrations(self):
        router = Router(self.database, migrate_dir=self.migrations_directory)

        for migration in router.diff:
            router.run_one(migration, router.migrator, fake=True)

        migrations = compile_migrations(router.migrator, self.models)

        if migrations:
            date = datetime.today().strftime("%d%m%U")
            name = router.compile(f"auto_{date}", migrations, None)
            logger.info(f"Migration {name} created")
            return

        logger.info("No migrations required")

    def migrate(self):
        Router(self.database, migrate_dir=self.migrations_directory).run()

    def rollback(self, name):
        Router(self.database, migrate_dir=self.migrations_directory).rollback(
            name
        )
