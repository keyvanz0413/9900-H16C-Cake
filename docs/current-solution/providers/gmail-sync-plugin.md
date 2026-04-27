# Gmail Sync Plugin

## Purpose

The Gmail sync plugin updates CRM-style contact metadata after successful sends or replies. This keeps contact `last_contact` state current without requiring every skill to call `update_contact` manually.

## Trigger

The plugin runs in an `after_each_tool` hook and checks whether the executed tool was a send-like Gmail operation with a non-empty recipient.

## Behavior

- Resolve the active Gmail tool instance.
- Call `update_contact` for the recipient.
- Clear `next_contact_date` after a successful send.
- Log failures without interrupting the user-facing flow.

## Scope

The plugin is mounted only in the Gmail branch. Outlook does not currently have equivalent CRM synchronization.

## Skill Relationship

`send_prepared_email` sends the message. The plugin handles the side effect after the send succeeds.
