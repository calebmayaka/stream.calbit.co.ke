"""
Summarise playback quality reported by the player.

    .venv\\Scripts\\python manage.py playbackstats            (last 30 days)
    .venv\\Scripts\\python manage.py playbackstats --days 7

Shows, per delivery method and for home vs. remote viewers: how many watches,
time to first picture (median / 90th percentile), and how often playback
stalled. Use it to judge changes (e.g. moving the VPS) with data.
"""

from collections import defaultdict
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.utils import timezone

from catalog.models import PlaybackStat


def pct(values, p):
    if not values:
        return 0
    values = sorted(values)
    return values[min(len(values) - 1, int(round(p / 100 * (len(values) - 1))))]


class Command(BaseCommand):
    help = "Summarise playback startup time and buffering from player reports."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30)

    def handle(self, days, **options):
        since = timezone.now() - timedelta(days=days)
        rows = list(PlaybackStat.objects.filter(created_at__gte=since))
        if not rows:
            self.stdout.write(f"No playback reports in the last {days} days yet.")
            return

        groups = defaultdict(list)
        for r in rows:
            groups[("remote" if r.remote else "home", r.method)].append(r)
            groups[("all", "all")].append(r)

        self.stdout.write(f"Playback, last {days} days ({len(rows)} watches)\n")
        header = f"{'where':<7} {'method':<10} {'watches':>7} {'start p50':>10} {'start p90':>10} {'stalled':>8} {'stall s/hr':>11}"
        self.stdout.write(header)
        self.stdout.write("-" * len(header))
        for (where, method), items in sorted(groups.items(), key=lambda kv: (kv[0][0] == "all", kv[0])):
            starts = [r.startup_ms / 1000 for r in items if r.startup_ms]
            stalled = sum(1 for r in items if r.stalls) / len(items)
            hours = sum(r.watched_seconds for r in items) / 3600 or 1
            stall_rate = sum(r.stall_ms for r in items) / 1000 / hours
            self.stdout.write(
                f"{where:<7} {method:<10} {len(items):>7} {pct(starts, 50):>9.1f}s {pct(starts, 90):>9.1f}s "
                f"{stalled:>7.0%} {stall_rate:>10.0f}s"
            )

        codecs = defaultdict(lambda: defaultdict(int))
        for r in rows:
            codecs[r.codec or "?"][r.method] += 1
        self.stdout.write("\nSource codec -> how it was delivered:")
        for codec, methods in sorted(codecs.items()):
            self.stdout.write(f"  {codec:<6} " + ", ".join(f"{m} {n}" for m, n in sorted(methods.items())))
