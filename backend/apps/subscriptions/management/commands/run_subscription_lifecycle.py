# backend/apps/subscriptions/management/commands/run_subscription_lifecycle.py
from django.core.management.base import BaseCommand

from apps.subscriptions import lifecycle


class Command(BaseCommand):
    """
    Runs the daily subscription job by hand (support, QA): the same code the beat entry
    "subscription-lifecycle-daily" runs (apps/subscriptions/lifecycle.py). There is no HTTP endpoint for it.

      --dry-run   prints who would get a reminder or be moved to Free, and writes nothing
                  (no row, no mail, no notification, no lock)

    It is safe to run twice: a step already done for a period is never done again.
    """
    help = "Sends the plan-expiry reminders and moves accounts to Free after their plan and grace ended."

    def add_arguments(self, parser):
        parser.add_argument('--dry-run', action='store_true', help='Print what would happen; change nothing.')

    def handle(self, *args, **options):
        dry = options['dry_run']
        report = lifecycle.run(dry_run=dry)
        out = self.stdout.write
        out(f"{'DRY RUN - nothing is changed. ' if dry else ''}Billing day: {report['today']} "
            f"({lifecycle.billing_tz().key})")
        if report['skipped']:
            out(self.style.WARNING(f"Skipped: another run holds the lock ({report['skipped']})."))
            return
        verb = 'would be reminded' if dry else 'reminded'
        out(f"Reminders ({len(report['reminders'])}): {verb}")
        for row in report['reminders']:
            detail = row['would'] if dry else (
                f"bell={'yes' if row['bell'] else 'no'} email={'sent' if row['email_claimed'] else 'failed' if row.get('email_failed') else 'not sent'}"
            )
            out(f"  {row['email']}  {row['plan']}  ends {row['period_end']:%Y-%m-%d %H:%M} UTC "
                f"(in {row['days_left']} day(s))  {detail}")
        verb = 'would be moved to Free' if dry else 'moved to Free'
        out(f"Downgrades ({len(report['downgrades'])}): {verb}")
        for row in report['downgrades']:
            note = ' [suspended: no mail, no bell]' if row['suspended'] else ''
            detail = row['would'] if dry else (
                f"downgraded={'yes' if row['downgraded'] else 'no'} bell={'yes' if row['bell'] else 'no'} "
                f"email={'sent' if row['email_claimed'] else 'failed' if row.get('email_failed') else 'not sent'}"
            )
            out(f"  {row['email']}  {row['plan']}  ended {row['period_end']:%Y-%m-%d %H:%M} UTC  {detail}{note}")
