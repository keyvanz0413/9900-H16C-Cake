"""
Email Agent - Email reading and management with memory

Purpose: Read, search, and manage your email inbox (Gmail and/or Outlook)
Pattern: Use ConnectOnion email tools + Memory system + Calendar + Shell + Plugins
"""

import json
import os
import re
import sys
from typing import Literal

from connectonion import Agent, Memory, WebFetch, Shell, TodoList, llm_do
from pydantic import BaseModel

from plugins import calendar_approval_plugin, gmail_approval_plugin, re_act

MODEL_NAME = os.getenv("AGENT_MODEL", "co/claude-sonnet-4-5")
PENDING_EMAIL_INTENT_PROMPT = """
You classify the user's latest message about a pending email draft.

Return exactly one intent:
- confirm_send: the user is clearly approving the already drafted email to be sent now.
- cancel_send: the user is clearly telling the assistant not to send the drafted email.
- edit_draft: the user wants the draft changed, refined, rewritten, shortened, expanded, translated, or otherwise edited before sending.
- other: the message is ambiguous, unrelated, or does not safely indicate send/cancel/edit intent.

The user message may be written in any language.
Be conservative:
- If there is any ambiguity about whether the user wants to send right now, return "other".
- Only return "confirm_send" when the user's latest message is a clear approval to send the already drafted email now.
- Only return "cancel_send" when the user's latest message is a clear instruction to stop/discard the pending draft.

Important nuance:
- If the user accepts the current draft and asks to proceed now, that is "confirm_send" even if the wording is casual, colloquial, indirect, polite, or slightly hedged.
- Messages equivalent to "looks good, go ahead", "that's fine, send it", or "没啥问题，直接发吧" should be treated as "confirm_send".
- Messages equivalent to "don't send it", "cancel it", or "算了先别发" should be treated as "cancel_send".
- Requests to revise, shorten, rewrite, translate, or tweak the draft before sending are "edit_draft".
"""
DRAFT_CLEANUP_PROMPT = """
You clean an email draft before it is shown to the user or sent.

Rules:
- Preserve the user's intent, language, factual content, and tone.
- Remove ALL unresolved placeholders, template markers, bracketed variables, or meta text.
- Placeholders appear in any language inside brackets: [Your Name], [Name], [你的名字], [签名], [Topic], [日期], [Content], [正文], etc. Remove them entirely.
- The closing signature is the most common place for placeholders. If the sender name is unknown, end with just "Best," or "Cheers," — never write a bracketed name.
- Do not add facts that are not already present.
- Keep the draft concise and natural.
- Return only the cleaned draft fields requested by the schema.
"""
SIGNATURE_CLOSINGS = {
    "all the best",
    "best",
    "best regards",
    "cheers",
    "kind regards",
    "many thanks",
    "regards",
    "sincerely",
    "thank you",
    "thanks",
    "warmly",
    "此致",
    "此致敬礼",
    "祝好",
    "致礼",
    "谢谢",
    "顺祝商祺",
}
SIGNATURE_PLACEHOLDER_RE = re.compile(
    r"^\s*(?:\[[^\]\n]{1,40}\]|your name|sender name|your signature|signature|name|你的名字|您的名字|签名)\s*$",
    re.IGNORECASE,
)


class PendingEmailIntent(BaseModel):
    intent: Literal["confirm_send", "cancel_send", "edit_draft", "other"]


class CleanSendDraft(BaseModel):
    subject: str
    body: str


class CleanReplyDraft(BaseModel):
    body: str


def _normalize_signature_line(line: str) -> str:
    return line.strip().rstrip(",，").strip().lower()


def _finalize_signature(body: str, sender_name: str = "") -> str:
    lines = [(line or "").rstrip() for line in (body or "").replace("\r\n", "\n").split("\n")]
    filtered_lines = []
    removed_placeholder = False

    for line in lines:
        if SIGNATURE_PLACEHOLDER_RE.fullmatch(line.strip()):
            removed_placeholder = True
            continue
        filtered_lines.append(line)

    while filtered_lines and not filtered_lines[-1].strip():
        filtered_lines.pop()

    sender_name = sender_name.strip()
    if sender_name and filtered_lines:
        last_non_empty = next((line for line in reversed(filtered_lines) if line.strip()), "")
        if filtered_lines[-1].strip() != sender_name and _normalize_signature_line(last_non_empty) in SIGNATURE_CLOSINGS:
            filtered_lines.append(sender_name)
    elif sender_name and removed_placeholder:
        return sender_name

    result = "\n".join(filtered_lines).strip()
    return re.sub(r"\n{3,}", "\n\n", result)


def _normalize_email_args(tool_name: str, args: dict) -> dict:
    if tool_name == "send":
        return {
            "to": args.get("to", ""),
            "subject": args.get("subject", ""),
            "body": args.get("body", ""),
            "cc": args.get("cc") or "",
            "bcc": args.get("bcc") or "",
        }

    return {
        "email_id": args.get("email_id", ""),
        "body": args.get("body", ""),
    }


def _get_pending_email(agent) -> dict | None:
    pending = agent.current_session.get("gmail_pending_draft")
    if pending:
        return pending

    trace = agent.current_session.get("trace", [])
    for entry in reversed(trace):
        entry_type = entry.get("type")
        if entry_type == "email_draft_cleared":
            return None
        if entry_type == "email_draft_pending":
            pending = {
                "tool_name": entry.get("tool_name"),
                "args": entry.get("args", {}),
                "turn": entry.get("turn"),
            }
            agent.current_session["gmail_pending_draft"] = pending
            return pending

    return None


def _record_pending_email(agent, tool_name: str, args: dict) -> None:
    if hasattr(agent, "_record_trace"):
        agent._record_trace({
            "type": "email_draft_pending",
            "tool_name": tool_name,
            "args": dict(args),
            "turn": agent.current_session.get("turn"),
        })


def _clear_pending_email(agent, reason: str) -> None:
    agent.current_session.pop("gmail_pending_draft", None)
    if hasattr(agent, "_record_trace"):
        agent._record_trace({
            "type": "email_draft_cleared",
            "reason": reason,
            "turn": agent.current_session.get("turn"),
        })


def _has_interactive_confirmation_path(agent) -> bool:
    return bool(getattr(agent, "io", None)) or (sys.stdin.isatty() and sys.stdout.isatty())


def _get_email_tool(agent):
    tools = getattr(agent, "tools", None)
    if tools is None:
        return None

    gmail = getattr(tools, "gmail", None)
    if gmail is not None:
        return gmail

    outlook = getattr(tools, "outlook", None)
    if outlook is not None:
        return outlook

    return None


def _send_pending_email_now(agent, pending: dict) -> str:
    email_tool = _get_email_tool(agent)
    if email_tool is None:
        raise RuntimeError("No email tool configured for pending draft delivery.")

    if hasattr(email_tool, "_deliver_pending_email_now"):
        return email_tool._deliver_pending_email_now(pending)

    args = pending.get("args", {})
    if pending.get("tool_name") == "send":
        return email_tool.send(
            to=args.get("to", ""),
            subject=args.get("subject", ""),
            body=args.get("body", ""),
            cc=args.get("cc") or None,
            bcc=args.get("bcc") or None,
        )

    return email_tool.reply(
        email_id=args.get("email_id", ""),
        body=args.get("body", ""),
    )


def _mark_email_action_success(agent, result: str) -> str:
    if agent is not None:
        agent.current_session["stop_signal"] = True
        agent.current_session["result_override"] = (
            f"{result}\n\n如果你还想继续处理别的事情，直接告诉我。"
        )
    return result


def _mark_email_action_failure(agent, error: Exception) -> None:
    if agent is not None:
        agent.current_session["stop_signal"] = True
        agent.current_session["result_override"] = (
            f"邮件发送失败：{error}\n\n草稿已保留。你可以重试发送，或告诉我需要怎么修改。"
        )


def _run_email_action(agent, action) -> str:
    try:
        result = action()
    except Exception as error:
        _mark_email_action_failure(agent, error)
        raise
    return _mark_email_action_success(agent, result)


def _classify_pending_email_intent(agent, pending: dict, tool_name: str | None = None, args: dict | None = None) -> str:
    user_prompt = (agent.current_session.get("user_prompt") or "").strip()
    if not user_prompt:
        return "other"

    pending_tool_name = tool_name or pending.get("tool_name", "")
    current_args = _normalize_email_args(pending_tool_name, args or pending.get("args", {}))
    model_name = getattr(getattr(agent, "llm", None), "model", MODEL_NAME)
    intent_summary = (agent.current_session.get("intent") or "").strip()

    prompt_lines = [
        f"Latest user message:\n{user_prompt}",
    ]
    if intent_summary:
        prompt_lines.extend([
            "",
            "Current-turn intent summary from the agent's own reasoning:",
            intent_summary,
        ])
    prompt_lines.extend([
        "",
        f"Pending tool: {pending.get('tool_name', '')}",
        "Pending draft:",
        json.dumps(pending.get("args", {}), ensure_ascii=False, indent=2, sort_keys=True),
        "",
        f"Current tool under consideration: {pending_tool_name}",
        "Current tool arguments:",
        json.dumps(current_args, ensure_ascii=False, indent=2, sort_keys=True),
    ])
    prompt = "\n".join(prompt_lines)

    try:
        result = llm_do(
            input=prompt,
            output=PendingEmailIntent,
            system_prompt=PENDING_EMAIL_INTENT_PROMPT,
            model=model_name,
            temperature=0,
            max_tokens=40,
        )
        return result.intent
    except Exception:
        return "other"


def _clean_email_args_with_llm(agent, tool_name: str, args: dict) -> dict:
    model_name = getattr(getattr(agent, "llm", None), "model", MODEL_NAME) if agent else MODEL_NAME
    user_prompt = (agent.current_session.get("user_prompt") or "").strip() if agent else ""
    intent_summary = (agent.current_session.get("intent") or "").strip() if agent else ""
    sender_name = _current_sender_name()

    prompt_lines = []
    if user_prompt:
        prompt_lines.extend([
            "Latest user request:",
            user_prompt,
            "",
        ])
    if intent_summary:
        prompt_lines.extend([
            "Current-turn intent summary:",
            intent_summary,
            "",
        ])
    if sender_name:
        prompt_lines.extend([
            "Sender name for the signature:",
            sender_name,
            "",
        ])
    prompt_lines.extend([
        f"Tool: {tool_name}",
        "Draft arguments:",
        json.dumps(args, ensure_ascii=False, indent=2, sort_keys=True),
    ])
    prompt = "\n".join(prompt_lines)

    try:
        if tool_name == "send":
            cleaned = llm_do(
                input=prompt,
                output=CleanSendDraft,
                system_prompt=DRAFT_CLEANUP_PROMPT,
                model=model_name,
                temperature=0,
                max_tokens=1500,
            )
            subject = cleaned.subject.strip()
            body = _finalize_signature(cleaned.body.strip(), sender_name)
            if not subject or not body:
                return {
                    "to": args.get("to", ""),
                    "subject": args.get("subject", ""),
                    "body": _finalize_signature(args.get("body", ""), sender_name),
                    "cc": args.get("cc") or "",
                    "bcc": args.get("bcc") or "",
                }
            return {
                "to": args.get("to", ""),
                "subject": subject,
                "body": body,
                "cc": args.get("cc") or "",
                "bcc": args.get("bcc") or "",
            }

        cleaned = llm_do(
            input=prompt,
            output=CleanReplyDraft,
            system_prompt=DRAFT_CLEANUP_PROMPT,
            model=model_name,
            temperature=0,
            max_tokens=1500,
        )
        body = _finalize_signature(cleaned.body.strip(), sender_name)
        if not body:
            return {
                "email_id": args.get("email_id", ""),
                "body": _finalize_signature(args.get("body", ""), sender_name),
            }
        return {
            "email_id": args.get("email_id", ""),
            "body": body,
        }
    except Exception:
        if tool_name == "send":
            return {
                "to": args.get("to", ""),
                "subject": args.get("subject", ""),
                "body": _finalize_signature(args.get("body", ""), sender_name),
                "cc": args.get("cc") or "",
                "bcc": args.get("bcc") or "",
            }
        return {
            "email_id": args.get("email_id", ""),
            "body": _finalize_signature(args.get("body", ""), sender_name),
        }


class EmailAgent(Agent):
    """Agent variant that can intentionally pause after a tool asks for user confirmation."""

    def input(
        self,
        prompt: str,
        max_iterations: int | None = None,
        session: dict | None = None,
        images: list[str] | None = None,
        files: list[dict] | None = None,
    ) -> str:
        self.system_prompt = _build_system_prompt()
        return super().input(
            prompt,
            max_iterations=max_iterations,
            session=session,
            images=images,
            files=files,
        )

    def _maybe_handle_pending_email_turn(self) -> str | None:
        pending = _get_pending_email(self)
        if not pending:
            return None

        if self.current_session.get("turn") == pending.get("turn"):
            return None

        if _has_interactive_confirmation_path(self):
            return None

        intent = _classify_pending_email_intent(self, pending)
        self._record_trace({
            "type": "pending_email_intent",
            "intent": intent,
            "tool_name": pending.get("tool_name"),
            "turn": self.current_session.get("turn"),
        })

        if intent == "cancel_send":
            _clear_pending_email(self, "cancelled")
            return "Canceled the pending email draft. No email was sent."

        if intent == "confirm_send":
            result = _send_pending_email_now(self, pending)
            _clear_pending_email(self, "sent")
            return result

        return None

    def _run_iteration_loop(self, max_iterations: int) -> str:
        pending_result = self._maybe_handle_pending_email_turn()
        if pending_result is not None:
            return pending_result

        while self.current_session['iteration'] < max_iterations:
            self.current_session['iteration'] += 1

            self._invoke_events('before_iteration')

            response = self._get_llm_decision()

            if not response.tool_calls:
                content = response.content if response.content else "Task completed."
                return content

            self._execute_and_record_tools(response.tool_calls)
            self._invoke_events('after_iteration')

            if self.current_session.pop('halt_turn', None):
                return self.current_session.pop('result_override', "Awaiting user confirmation.")

            if self.current_session.pop('stop_signal', None):
                self._invoke_events('on_stop_signal')
                return self.current_session.pop('result_override', "What would you like me to do?")

        return f"Task incomplete: Maximum iterations ({max_iterations}) reached."


class OpenAICompatibleGmailMixin:
    """Patch tool schemas and enforce conversational confirmation for send/reply."""

    def bulk_update_contacts(self, updates: list[dict]) -> str:
        return super().bulk_update_contacts(updates)

    def _deliver_pending_email_now(self, pending: dict) -> str:
        args = pending.get("args", {})
        if pending.get("tool_name") == "send":
            return super(OpenAICompatibleGmailMixin, self).send(
                to=args.get("to", ""),
                subject=args.get("subject", ""),
                body=args.get("body", ""),
                cc=args.get("cc") or None,
                bcc=args.get("bcc") or None,
            )

        return super(OpenAICompatibleGmailMixin, self).reply(
            email_id=args.get("email_id", ""),
            body=args.get("body", ""),
        )

    def _pending_email_matches(self, pending: dict | None, tool_name: str, args: dict) -> bool:
        if not pending:
            return False
        return pending.get("tool_name") == tool_name and pending.get("args") == _normalize_email_args(tool_name, args)

    def _consume_forced_send(self, agent, tool_name: str, args: dict) -> bool:
        forced = agent.current_session.get("gmail_force_send")
        if not forced:
            return False

        matches = (
            forced.get("tool_name") == tool_name
            and _normalize_email_args(tool_name, forced.get("args", {})) == _normalize_email_args(tool_name, args)
        )
        if matches:
            agent.current_session.pop("gmail_force_send", None)
            return True
        return False

    def _has_interactive_approval_bypass(self, agent, tool_name: str, args: dict) -> bool:
        session = agent.current_session
        if self._consume_forced_send(agent, tool_name, args):
            return True
        if session.get("gmail_approve_all", False):
            return True
        if tool_name in session.get("gmail_approved_tools", set()):
            return True
        if tool_name == "send" and args.get("to", "") in session.get("gmail_approved_recipients", set()):
            return True
        if tool_name == "reply" and session.get("gmail_approve_replies", False):
            return True
        return False

    def _build_conversation_draft_message(self, tool_name: str, args: dict, updated: bool) -> str:
        header = "Updated draft ready for confirmation." if updated else "Draft ready for confirmation."
        lines = [header, "NO EMAIL HAS BEEN SENT YET.", ""]

        if tool_name == "send":
            lines.extend([
                f"To: {args.get('to', '')}",
            ])
            if args.get("cc"):
                lines.append(f"CC: {args.get('cc')}")
            if args.get("bcc"):
                lines.append(f"BCC: {args.get('bcc')}")
            lines.extend([
                f"Subject: {args.get('subject', '')}",
                "",
                args.get("body", ""),
            ])
        else:
            lines.extend([
                f"Reply to thread: {args.get('email_id', '')}",
                "",
                args.get("body", ""),
            ])

        lines.extend([
            "",
            "If everything looks good, confirm to send. If you'd like changes, just tell me what to adjust.",
        ])
        return "\n".join(lines)

    def _build_confirmation_response(self, tool_name: str, args: dict, updated: bool) -> str:
        intro = "Here’s the updated draft." if updated else "Here’s the draft."
        details = self._build_conversation_draft_message(tool_name, args, updated=updated)
        return f"{intro}\n\n{details}"

    def _pause_for_confirmation(self, agent, response_text: str) -> str:
        agent.current_session["halt_turn"] = True
        agent.current_session["result_override"] = response_text
        return response_text

    def _stage_pending_email(self, agent, tool_name: str, args: dict, updated: bool) -> str:
        cleaned_args = _clean_email_args_with_llm(agent, tool_name, args)
        normalized_args = _normalize_email_args(tool_name, cleaned_args)
        agent.current_session["gmail_pending_draft"] = {
            "tool_name": tool_name,
            "args": normalized_args,
            "turn": agent.current_session.get("turn"),
        }
        _record_pending_email(agent, tool_name, normalized_args)
        return self._pause_for_confirmation(
            agent,
            self._build_confirmation_response(tool_name, normalized_args, updated=updated),
        )

    def _maybe_send_or_stage(self, agent, tool_name: str, args: dict, send_now):
        if agent is None:
            return send_now()

        if self._has_interactive_approval_bypass(agent, tool_name, args):
            result = _run_email_action(agent, send_now)
            pending = _get_pending_email(agent)
            if self._pending_email_matches(pending, tool_name, args):
                _clear_pending_email(agent, "sent")
            return result

        pending = _get_pending_email(agent)
        pending_intent = "other"
        if pending and agent.current_session.get("turn") != pending.get("turn"):
            pending_intent = _classify_pending_email_intent(agent, pending, tool_name, args)
            if pending_intent == "cancel_send":
                _clear_pending_email(agent, "cancelled")
                return self._pause_for_confirmation(
                    agent,
                    "Canceled the pending email draft. No email was sent.",
                )
            if pending_intent == "confirm_send":
                result = _run_email_action(
                    agent,
                    lambda: self._deliver_pending_email_now(pending),
                )
                _clear_pending_email(agent, "sent")
                return result

        if self._pending_email_matches(pending, tool_name, args):
            if agent.current_session.get("turn") != pending.get("turn"):
                result = _run_email_action(agent, send_now)
                _clear_pending_email(agent, "sent")
                return result
            return self._pause_for_confirmation(
                agent,
                self._build_confirmation_response(tool_name, pending["args"], updated=False),
            )

        return self._stage_pending_email(agent, tool_name, args, updated=bool(pending))

    def send(self, to: str, subject: str, body: str, cc: str = None, bcc: str = None, agent=None) -> str:
        args = {"to": to, "subject": subject, "body": body, "cc": cc, "bcc": bcc}
        return self._maybe_send_or_stage(
            agent,
            "send",
            args,
            lambda: super(OpenAICompatibleGmailMixin, self).send(to=to, subject=subject, body=body, cc=cc, bcc=bcc),
        )

    def reply(self, email_id: str, body: str, agent=None) -> str:
        args = {"email_id": email_id, "body": body}
        return self._maybe_send_or_stage(
            agent,
            "reply",
            args,
            lambda: super(OpenAICompatibleGmailMixin, self).reply(email_id=email_id, body=body),
        )

# Create shared tool instances
memory = Memory(memory_file="data/memory.md")
web = WebFetch()  # For analyzing contact domains
shell = Shell()  # For running shell commands (e.g., get current date)
todo = TodoList()  # For tracking multi-step tasks

# Build tools list based on .env flags
# Note: Only one email provider at a time (tools have overlapping method names)
has_gmail = os.getenv("LINKED_GMAIL", "").lower() == "true"
has_outlook = os.getenv("LINKED_OUTLOOK", "").lower() == "true"

tools = []
plugins = [re_act]

# Prefer Gmail if both are linked (can only use one due to method name conflicts)
if has_gmail:
    from connectonion import Gmail, GoogleCalendar

    class GmailCompat(OpenAICompatibleGmailMixin, Gmail):
        def get_sender_name(self) -> str:
            """Return the user's display name from Gmail sendAs settings."""
            try:
                service = self._get_service()
                send_as_list = service.users().settings().sendAs().list(userId='me').execute()
                for alias in send_as_list.get('sendAs', []):
                    name = alias.get('displayName', '').strip()
                    if name:
                        return name
            except Exception:
                pass
            return ""

        def get_my_identity(self) -> str:
            base = super().get_my_identity()
            name = self.get_sender_name()
            if name:
                return f"Display name: {name}\n" + base
            return base

    _gmail = GmailCompat()
    tools.append(_gmail)
    tools.append(GoogleCalendar())
    plugins.append(gmail_approval_plugin)
    plugins.append(calendar_approval_plugin)
elif has_outlook:
    from connectonion import Outlook, MicrosoftCalendar
    tools.append(Outlook())
    tools.append(MicrosoftCalendar())

# Warn if no email provider configured
if not tools:
    print("\n⚠️  No email account connected. Use /link-gmail or /link-outlook to connect.\n")

# Select prompt based on linked provider, appending shared draft examples
def _load_prompt(base: str, examples: str = "prompts/email_draft_examples.md", sender_name: str = "") -> str:
    with open(base, encoding="utf-8") as f:
        content = f.read()
    with open(examples, encoding="utf-8") as f:
        content += "\n\n" + f.read()
    if sender_name:
        content = f"The sender's name is: {sender_name}\nAlways use this name to sign emails.\n\n" + content
    return content

def _sender_name_from_memory() -> str:
    result = memory.read_memory("preference-sender-name")
    if result.startswith("Memory not found"):
        return ""
    header = "Memory: preference-sender-name\n\n"
    body = result[len(header):] if result.startswith(header) else result
    return body.strip()


def _current_sender_name() -> str:
    sender_name = _sender_name_from_memory()
    if sender_name:
        return sender_name
    if has_gmail:
        try:
            return _gmail.get_sender_name()
        except Exception:
            return ""
    return ""


_sender_name = ""


def _build_system_prompt() -> str:
    global _sender_name
    _sender_name = _current_sender_name()
    if has_gmail:
        return _load_prompt("prompts/gmail_agent.md", sender_name=_sender_name)
    if has_outlook:
        return _load_prompt("prompts/outlook_agent.md")
    return _load_prompt("prompts/gmail_agent.md")


system_prompt = _build_system_prompt()

# Create init sub-agent for CRM database setup
init_crm = EmailAgent(
    name="crm-init",
    system_prompt="prompts/crm_init.md",
    tools=tools + [memory, web],
    max_iterations=30,
    model=MODEL_NAME,
    log=False  # Don't create separate log file
)


def init_crm_database(max_emails: int = 500, top_n: int = 10, exclude_domains: str = "openonion.ai,connectonion.com") -> str:
    """Initialize CRM database by extracting and analyzing top contacts.

    Args:
        max_emails: Number of emails to scan for contacts (default: 500)
        top_n: Number of top contacts to analyze and save (default: 10)
        exclude_domains: Comma-separated domains to exclude (your org domains)

    Returns:
        Summary of initialization process including number of contacts analyzed
    """
    result = init_crm.input(
        f"Initialize CRM: Extract top {top_n} contacts from {max_emails} emails.\n"
        f"IMPORTANT: Use get_all_contacts(max_emails={max_emails}, exclude_domains=\"{exclude_domains}\")\n"
        f"Then use AI judgment to categorize and analyze the most important contacts."
    )
    # Return clear completion message so main agent knows not to call again
    return f"CRM INITIALIZATION COMPLETE. Data saved to memory. Use read_memory() to access:\n- crm:all_contacts\n- crm:needs_reply\n- crm:init_report\n- contact:email@example.com\n\nDetails: {result}"


# Add remaining tools to the list
tools.extend([memory, shell, todo, init_crm_database])

# Create main agent
agent = EmailAgent(
    name="email-agent",
    system_prompt=system_prompt,
    tools=tools,
    plugins=plugins,
    max_iterations=15,
    model=MODEL_NAME,
)

# Example usage
if __name__ == "__main__":
    print("=== Email Agent ===\n")

    # Example 1: Initialize CRM database using wrapper function
    print("1. Initialize CRM database...")
    result = agent.input(
        "Initialize the CRM database with top 5 contacts from recent 500 emails"
    )
    print(result)

    print("\n" + "="*50 + "\n")

    # Example 2: Query from MEMORY (should NOT re-fetch from API)
    print("2. Query from memory (should be fast)...")
    result = agent.input("Who do I email the most? Check memory first.")
    print(result)
