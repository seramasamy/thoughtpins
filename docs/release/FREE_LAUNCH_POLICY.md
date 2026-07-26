# Free Initial Release Policy

Thought Pins' initial public release is free to use. The shipped clients contain
no subscription, in-app purchase, external checkout, advertising, or paid-tier
interface. Operational rate limits may protect reliability and provider cost,
but they do not unlock a paid plan in this release.

The machine-readable contract is `deploy/store/commerce-policy.json` and the
release gate enforces it through `scripts/check_free_launch.py`. A future paid
release requires a deliberate product and legal change: new store metadata,
updated terms and privacy disclosures, platform-compliant billing, restore and
refund behavior, regional testing, and a new App Review submission. Paid
plumbing must not be hidden or dormant in the initial binary.

This policy is a release constraint, not a promise that every future version
will remain free. Users must receive clear notice before any future pricing
change, and existing data export and account deletion controls must remain
available independently of payment status.
