# Database

`migrate.sql` is mounted into the postgres container at
`/docker-entrypoint-initdb.d/01-migrate.sql` and runs on first start of an empty
data volume.

If you need to re-run it (schema iteration during MVP), nuke the volume:

```bash
make clean    # docker compose down -v
make up
```

For real migrations later, plug in Alembic.
