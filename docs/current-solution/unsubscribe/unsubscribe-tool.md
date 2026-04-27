# Unsubscribe Tool

## Purpose

`email-agent/tools/unsubscribe_tool.py` exposes the low-level unsubscribe helpers used by discovery and execution skills.

## Tools

- `get_unsubscribe_info(email_ids, max_manual_links=5)`: reads `List-Unsubscribe` headers and message body links, then returns normalized metadata.
- `post_one_click_unsubscribe(url, timeout_seconds=10)`: sends an RFC 8058-compatible POST request.

## Design

These two tools replace several earlier fine-grained tool ideas. The goal is to avoid asking the LLM to manually combine header parsing, body parsing, mailto handling, and POST behavior.

## Output Shape

The metadata should identify available methods, evidence, candidate ids, sender information, manual links, and any safety notes.

## Safety

The tool layer should not browse arbitrary websites. One-click POST is allowed only for compliant one-click URLs. Website links are returned for manual action.
