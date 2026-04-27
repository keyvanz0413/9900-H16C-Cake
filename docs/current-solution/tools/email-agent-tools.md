# Email Agent Tools

## Purpose

This document summarizes the tool surface available to the current email agent. Tools are injected by provider branch and by skill `used_tools` declarations.

## Major Tool Groups

- Mailbox search and message body retrieval.
- Sending and replying.
- Contact and CRM-style updates.
- Attachment text extraction.
- Calendar event reads and writes.
- Unsubscribe discovery and execution helpers.
- Memory and local runtime helpers.

## Provider Scope

Gmail has the complete tool set today, including unsubscribe and attachment extraction. Outlook has a smaller tool set and needs follow-up work for parity.

## Skill Scope

Skills should receive only the tools listed in their registry entry. This keeps workflows predictable and prevents a read-only skill from accidentally gaining write tools.

## Safety

Calendar writes go through approval when the plugin is active. Unsubscribe execution distinguishes automatic one-click or mailto actions from manual website links.
