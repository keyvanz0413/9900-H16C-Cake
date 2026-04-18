"""
Email Agent - Email reading and management with memory

Purpose: Read, search, and manage your email inbox (Gmail and/or Outlook)
Pattern: Use ConnectOnion email tools + Memory system + Calendar + Shell + Plugins
"""

import os
from pathlib import Path

from connectonion import Agent, Memory, WebFetch, Shell, TodoList
from connectonion.useful_plugins import re_act, gmail_plugin, calendar_plugin
from tools.attachment_text_tool import extract_recent_attachment_texts_from_email_tool
from intent_layer import (
    IntentLayerOrchestrator,
    MarkdownMemoryStore,
    PythonSkillExecutor,
    build_tool_function_map,
)

MODEL_NAME = os.getenv("AGENT_MODEL", "co/claude-sonnet-4-5")
INTENT_MODEL_NAME = os.getenv("INTENT_LAYER_MODEL", MODEL_NAME)
SKILL_SELECTOR_MODEL_NAME = os.getenv("SKILL_SELECTOR_MODEL", INTENT_MODEL_NAME)
SKILL_FINALIZER_MODEL_NAME = os.getenv("SKILL_FINALIZER_MODEL", INTENT_MODEL_NAME)
WRITING_STYLE_MODEL_NAME = os.getenv("WRITING_STYLE_MODEL", INTENT_MODEL_NAME)
USER_MEMORY_MODEL_NAME = os.getenv("USER_MEMORY_MODEL", INTENT_MODEL_NAME)

BASE_DIR = Path(__file__).resolve().parent
PROMPTS_DIR = BASE_DIR / "prompts"
SKILL_REGISTRY_PATH = BASE_DIR / "skills" / "registry.yaml"
USER_PROFILE_PATH = BASE_DIR / "USER_PROFILE.md"
USER_HABITS_PATH = BASE_DIR / "USER_HABITS.md"
WRITING_STYLE_PATH = BASE_DIR / "WRITING_STYLE.md"


class OpenAICompatibleGmailMixin:
    """Patch ConnectOnion's bare `list` annotation for OpenAI tool schemas."""

    def bulk_update_contacts(self, updates: list[dict]) -> str:
        return super().bulk_update_contacts(updates)

# Create shared tool instances
memory = Memory(memory_file="data/memory.md")
web = WebFetch()  # For analyzing contact domains
shell = Shell()  # For running shell commands (e.g., get current date)
todo = TodoList()  # For tracking multi-step tasks

def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _get_primary_email_tool():
    for tool in tools:
        if hasattr(tool, "_get_service"):
            return tool
    return None


def extract_recent_attachment_texts(days: int = 7, max_results: int = 10) -> str:
    """Extract text from attachments in recent Gmail inbox emails.

    Args:
        days: Look back over the most recent N days.
        max_results: Maximum number of recent attachment-bearing emails to scan.

    Returns:
        A readable summary of recent emails with attachment metadata and extracted text.
    """
    email_tool = _get_primary_email_tool()
    if email_tool is None:
        return "Recent attachment text extraction is only available when Gmail is connected."
    return extract_recent_attachment_texts_from_email_tool(
        email_tool=email_tool,
        days=days,
        max_results=max_results,
    )


# Build tools list based on .env flags or existing provider tokens.
# Note: Only one email provider at a time (tools have overlapping method names)
tools = []
plugins = [re_act]

has_gmail = _env_flag("LINKED_GMAIL") or bool(
    os.getenv("GOOGLE_ACCESS_TOKEN") or os.getenv("GOOGLE_REFRESH_TOKEN")
)
has_outlook = _env_flag("LINKED_OUTLOOK") or bool(
    os.getenv("MICROSOFT_ACCESS_TOKEN") or os.getenv("MICROSOFT_REFRESH_TOKEN")
)

# Prefer Gmail if both are linked (can only use one due to method name conflicts)
if has_gmail:
    from connectonion import Gmail, GoogleCalendar

    class GmailCompat(OpenAICompatibleGmailMixin, Gmail):
        pass

    tools.append(GmailCompat())
    tools.append(GoogleCalendar())
    plugins.append(gmail_plugin)
    plugins.append(calendar_plugin)
elif has_outlook:
    from connectonion import Outlook, MicrosoftCalendar
    tools.append(Outlook())
    tools.append(MicrosoftCalendar())

# Warn if no email provider configured
if not tools:
    print("\n⚠️  No email account connected. Use /link-gmail or /link-outlook to connect.\n")

# Select prompt based on linked provider
if has_gmail:
    system_prompt = PROMPTS_DIR / "gmail_agent.md"
elif has_outlook:
    system_prompt = PROMPTS_DIR / "outlook_agent.md"
else:
    system_prompt = PROMPTS_DIR / "gmail_agent.md"  # Default

# Create init sub-agent for CRM database setup
init_crm = Agent(
    name="crm-init",
    system_prompt=PROMPTS_DIR / "crm_init.md",
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
if has_gmail:
    tools.append(extract_recent_attachment_texts)

# Create main execution agent
main_agent = Agent(
    name="email-agent",
    system_prompt=system_prompt,
    tools=tools,
    plugins=plugins,
    max_iterations=15,
    model=MODEL_NAME,
)

# Intent and routing helper agents are lightweight single-step LLM calls.
intent_agent = Agent(
    name="email-agent-intent-layer",
    system_prompt=PROMPTS_DIR / "intent_layer.md",
    tools=[],
    max_iterations=1,
    model=INTENT_MODEL_NAME,
)

skill_selector_agent = Agent(
    name="email-agent-skills-selector",
    system_prompt=PROMPTS_DIR / "skills_selector.md",
    tools=[],
    max_iterations=1,
    model=SKILL_SELECTOR_MODEL_NAME,
)

skill_finalizer_agent = Agent(
    name="email-agent-skill-finalizer",
    system_prompt=PROMPTS_DIR / "skill_finalizer.md",
    tools=[],
    max_iterations=1,
    model=SKILL_FINALIZER_MODEL_NAME,
)

user_memory_writer_agent = Agent(
    name="email-agent-user-memory-writer",
    system_prompt=PROMPTS_DIR / "user_memory_writer.md",
    tools=[],
    max_iterations=1,
    model=USER_MEMORY_MODEL_NAME,
)

writing_style_writer_agent = Agent(
    name="email-agent-writing-style-writer",
    system_prompt=PROMPTS_DIR / "writing_style_writer.md",
    tools=[],
    max_iterations=1,
    model=WRITING_STYLE_MODEL_NAME,
)

memory_store = MarkdownMemoryStore(
    profile_path=USER_PROFILE_PATH,
    habits_path=USER_HABITS_PATH,
    writer_agent=user_memory_writer_agent,
)

skill_executor = PythonSkillExecutor(
    skills_directory=BASE_DIR / "skills",
    tool_function_map=build_tool_function_map(tools),
    skill_runtime={
        "agents": {
            "writing_style_writer": writing_style_writer_agent,
        },
        "paths": {
            "writing_style_markdown": WRITING_STYLE_PATH,
        },
    },
)

agent = IntentLayerOrchestrator(
    main_agent=main_agent,
    intent_agent=intent_agent,
    skill_selector_agent=skill_selector_agent,
    skill_finalizer_agent=skill_finalizer_agent,
    skill_executor=skill_executor,
    memory_store=memory_store,
    skill_registry_path=SKILL_REGISTRY_PATH,
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
