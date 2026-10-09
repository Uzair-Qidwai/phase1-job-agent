# Saved digest review

The default `DIGEST_DELIVERY_MODE=review` makes pipeline runs save an unsent batch
instead of contacting Gmail. Apply `python -m src.migrations` before updating the
API or scheduler. Migration 004 adds the saved-batch table; do not edit earlier SQL.

## Browser workflow

Start the API on loopback and open `/review` (linked from `/dashboard`). Enter the
locally configured API token; it is held only in the page, not browser storage.
All batch reads and actions require authentication even when general read auth is
disabled. The public page shell contains no private job or CV data.

1. Run the pipeline to discover, rank and generate validated CVs, or choose
   **Prepare next batch** for already tailored, unsent jobs. The default batch
   contains up to five jobs. Preparing or loading a batch never sends mail.
2. Review the recipient, exact saved email, captured descriptions and CV previews.
3. Choose **Approve this preview**. This records approval but sends nothing.
4. Choose **Send approved email**. It sends the saved HTML and subject without CV
   attachments. Sender and recipient must still match local configuration.

There is one open batch at a time. New eligible jobs stay queued for the next
batch. Cancel a pending/approved batch to select different jobs or regenerate a
changed preview. Cancellation does not delete jobs or CV history.

Model-generated change summaries and warnings are not factuality-validated, so
reviewed emails currently use a neutral CV-review notice. Useful, verified change
summaries remain a separate quality improvement. The CV previews are private
review material, never email attachments.

## Command-line workflow

```sh
python -m src.digest_review prepare --limit 3
python -m src.digest_review list
python -m src.digest_review preview BATCH_UUID --output .local/review-batch
python -m src.digest_review approve BATCH_UUID --fingerprint SHA256_FROM_PREVIEW
python -m src.digest_review send BATCH_UUID --fingerprint SHA256_FROM_PREVIEW
```

`prepare --job-id UUID --job-id UUID` selects specific tailored jobs (maximum 20).
The private preview directory contains the exact email, CV files and `review.json`
with recipient and fingerprint. Approval/send must reference that fingerprint.
`python -m src.digest_review cancel BATCH_UUID` cancels without sending.
These commands act on the configured database. Do not point them at a test copy
and assume its notification history represents another database.

## Invariants and recovery

The fingerprint covers sender, recipient, subject, HTML, job details, captured
requirements, CV version/body and source-CV fingerprint. Approval and sending
refuse changed content, changed configuration, changed source evidence, invalidated
CVs or already-notified jobs. The send does not rerender templates or run models.
The database execution lock prevents concurrent workers/sends; the batch's sending
state and ambiguous delivery attempt commit in one transaction before transport.
Successful delivery and the batch's sent state commit together with notifications.

An uncertain send keeps the batch in `sending`. Do not cancel it or create another
attempt. Use the existing [delivery reconciliation procedure](OPERATIONS.md):
verify the external outcome, stop workers and explicitly reconcile the attempt.
A confirmed sent outcome marks the batch sent. A confirmed not-sent outcome resets
it to pending and clears approval; review and approve again before retrying.
If the worker died, recover its stranded pipeline run as documented before retry.
A restored database is not evidence that an external email was never sent.

`DIGEST_DELIVERY_MODE=automatic` explicitly retains legacy automatic delivery for
previous deployments/tests; it bypasses per-batch human review when no open batch
exists. An open review batch blocks that path. Do not enable automatic mode as part
of the supervised pilot. The default and example configuration remain `review`.

## API

All endpoints below require the bearer token and return `Cache-Control: no-store`.

| Method | Path | Purpose |
|---|---|---|
| GET | `/digests` | Bounded batch summaries |
| POST | `/digests` | Prepare selected IDs or up to `limit` ready jobs |
| GET | `/digests/{id}` | Private exact snapshot and state |
| POST | `/digests/{id}/approve` | Approve supplied `fingerprint` |
| POST | `/digests/{id}/send` | Send supplied approved `fingerprint` once |
| POST | `/digests/{id}/cancel` | Cancel pending/approved batch |

This is a single-user operator interface using the existing API token. It is not
a multi-user login system or a publicly deployed service.
