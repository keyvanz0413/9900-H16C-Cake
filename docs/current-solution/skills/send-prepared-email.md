# Send Prepared Email Skill

## Purpose

`send_prepared_email` sends an already prepared message with explicit `to`, `subject`, and `body` fields.

## Contract

The skill should not invent missing message content. It requires validated send arguments from the resolver or a prior draft step.

## Flow

1. Validate recipient, subject, and body.
2. Call the provider send tool.
3. Return send status, recipient, subject, and any tool evidence.

## Side Effects

On Gmail, `gmail_sync_plugin` may update CRM contact metadata after the send succeeds. The skill itself does not own that synchronization.

## Finalizer Expectations

Say the email was sent only when the send tool succeeded. Include recipient and subject for confirmation.
