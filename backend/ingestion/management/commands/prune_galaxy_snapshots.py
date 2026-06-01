from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Prune superseded Galaxy snapshots and their dependent rows."

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--retain-superseded-per-scope",
            type=int,
            default=0,
            help="Keep the newest N non-current snapshots per scope/season pair.",
        )
        parser.add_argument(
            "--execute",
            action="store_true",
            help="Actually delete rows. Without this flag the command only reports candidates.",
        )

    def handle(self, *args, **options) -> None:
        from ingestion.services.galaxy import prune_galaxy_snapshots

        stats = prune_galaxy_snapshots(
            retain_superseded_per_scope=options["retain_superseded_per_scope"],
            dry_run=not options["execute"],
        )
        mode = "DRY RUN" if stats["dry_run"] else "EXECUTED"
        self.stdout.write(f"Galaxy snapshot prune {mode}")
        self.stdout.write(f"retain_superseded_per_scope={stats['retain_superseded_per_scope']}")
        self.stdout.write(f"snapshots={stats['snapshots']}")
        self.stdout.write(f"similarities={stats['similarities']}")
        self.stdout.write(f"embeddings={stats['embeddings']}")
        self.stdout.write(f"archetypes={stats['archetypes']}")
        for key in (
            "deleted_similarities",
            "deleted_embeddings",
            "deleted_archetypes",
            "deleted_snapshots",
        ):
            if key in stats:
                self.stdout.write(f"{key}={stats[key]}")
