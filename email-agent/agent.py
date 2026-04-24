"""
Email Agent - Email reading and management with memory

Purpose: Read, search, and manage your email inbox (Gmail and/or Outlook)
Pattern: Use ConnectOnion email tools + Memory system + Calendar + Shell + Plugins
"""

import os
import inspect
from pathlib import Path

from connectonion import Agent, Memory, WebFetch, Shell, TodoList
from connectonion.useful_plugins import re_act
from plugins.calendar_approval_plugin import calendar_approval_plugin
from plugins.gmail_sync_plugin import build_gmail_sync_plugin
from tools.attachment_text_tool import extract_recent_attachment_texts_from_email_tool
from tools.unsubscribe_tool import (
    build_get_unsubscribe_info_tool,
    post_one_click_unsubscribe,
)
from intent_layer import (
    IntentLayerOrchestrator,
    MarkdownMemoryStore,
    PythonSkillExecutor,
    build_tool_function_map,
)

MODEL_NAME = os.getenv("AGENT_MODEL", "co/claude-sonnet-4-5")
INTENT_MODEL_NAME = os.getenv("INTENT_LAYER_MODEL", MODEL_NAME)
PLANNER_MODEL_NAME = os.getenv("PLANNER_MODEL", INTENT_MODEL_NAME)
SKILL_INPUT_RESOLVER_MODEL_NAME = os.getenv(
    "SKILL_INPUT_RESOLVER_MODEL",
    PLANNER_MODEL_NAME,
)
FINALIZER_MODEL_NAME = os.getenv("FINALIZER_MODEL", os.getenv("SKILL_FINALIZER_MODEL", INTENT_MODEL_NAME))
WRITING_STYLE_MODEL_NAME = os.getenv("WRITING_STYLE_MODEL", INTENT_MODEL_NAME)
USER_MEMORY_MODEL_NAME = os.getenv("USER_MEMORY_MODEL", INTENT_MODEL_NAME)
AGENT_TIMEZONE = os.getenv("AGENT_TIMEZONE", os.getenv("TZ", "Australia/Sydney"))

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


class UnavailableConfiguredAgent:
    """Import-safe stand-in when LLM credentials are unavailable in test/CI environments."""

    def __init__(
        self,
        *,
        name: str,
        tools,
        plugins=None,
        max_iterations: int,
        model: str,
        reason: str,
    ):
        self.name = name
        self.tools = tools
        self.plugins = plugins or []
        self.max_iterations = max_iterations
        self.current_session = None
        self.llm = type("LLM", (), {"model": model})()
        self._reason = reason

    def input(
        self,
        prompt: str,
        max_iterations: int | None = None,
        session: dict | None = None,
        images: list[str] | None = None,
        files: list[dict] | None = None,
    ) -> str:
        del prompt, max_iterations, images, files
        if isinstance(session, dict):
            self.current_session = session
        raise RuntimeError(self._reason)


class ToolHandle:
    """Compatibility wrapper exposing the legacy `.name` attribute in tests."""

    def __init__(self, name: str, target):
        self.name = name
        self.target = target


class ToolCollection(list):
    """Flatten tool sources into iterable named handles while preserving provider attrs."""

    def __init__(self, tool_sources: list):
        handles: list[ToolHandle] = []
        for source in tool_sources:
            if inspect.isfunction(source) or inspect.ismethod(source) or inspect.isbuiltin(source):
                name = getattr(source, "__name__", "")
                if name and not name.startswith("_"):
                    handles.append(ToolHandle(name, source))
                continue

            for name, member in inspect.getmembers(source):
                if name.startswith("_") or not callable(member):
                    continue
                handles.append(ToolHandle(name, member))

        super().__init__(handles)

    def names(self) -> list[str]:
        """Return stable tool names for runtime metadata extraction."""
        return list(dict.fromkeys(handle.name for handle in self))


class UnavailableEmailProvider:
    """Placeholder provider when the installed connectonion build lacks that backend."""

    def __init__(self, provider_name: str):
        self.provider_name = provider_name

    def _raise_unavailable(self):
        raise RuntimeError(
            f"{self.provider_name.title()} support is unavailable in the installed connectonion package."
        )

    def read_inbox(self, *args, **kwargs):
        self._raise_unavailable()

    def search_emails(self, *args, **kwargs):
        self._raise_unavailable()

    def send(self, *args, **kwargs):
        self._raise_unavailable()

    def mark_read(self, *args, **kwargs):
        self._raise_unavailable()

    def get_unanswered_emails(self, *args, **kwargs):
        self._raise_unavailable()

    def get_my_identity(self, *args, **kwargs):
        self._raise_unavailable()

    def detect_all_my_emails(self, *args, **kwargs):
        self._raise_unavailable()


def _build_configured_agent(*, reason_prefix: str, **kwargs):
    try:
        return Agent(**kwargs)
    except ValueError as exc:
        if "API key required" not in str(exc):
            raise
        return UnavailableConfiguredAgent(
            name=kwargs["name"],
            tools=kwargs.get("tools", []),
            plugins=kwargs.get("plugins", []),
            max_iterations=kwargs.get("max_iterations", 1),
            model=kwargs.get("model", MODEL_NAME),
            reason=f"{reason_prefix}: {exc}",
        )

# Create shared tool instances
memory = Memory(memory_file="data/memory.md")
web = WebFetch()  # For analyzing contact domains
shell = Shell()  # For running shell commands (e.g., get current date)
todo = TodoList()  # For tracking multi-step tasks

def _env_flag(name: str) -> bool:
    return os.getenv(name, "").strip().lower() == "true"


def _provider_is_linked(flag_name: str, *token_env_names: str) -> bool:
    explicit_flag = os.getenv(flag_name)
    if explicit_flag is not None:
        return explicit_flag.strip().lower() == "true"

    if os.getenv("PYTEST_CURRENT_TEST") or os.getenv("CI"):
        return False

    return any(os.getenv(token_name) for token_name in token_env_names)


def _get_primary_email_tool():
    for tool in tools:
        if hasattr(tool, "_get_service"):
            return tool
    return None


def extract_recent_attachment_texts(query: str, max_results: int = 10) -> str:
    """Extract text from attachments in recent Gmail inbox emails.

    Args:
        query: Gmail search query used to select emails whose attachments should be extracted.
        max_results: Maximum number of recent attachment-bearing emails to scan.

    Returns:
        A readable summary of recent emails with attachment metadata and extracted text.
    """
    email_tool = _get_primary_email_tool()
    if email_tool is None:
        return "Recent attachment text extraction is only available when Gmail is connected."
    return extract_recent_attachment_texts_from_email_tool(
        email_tool=email_tool,
        query=query,
        max_results=max_results,
    )
get_unsubscribe_info = build_get_unsubscribe_info_tool(_get_primary_email_tool)


# Build tools list based on .env flags or existing provider tokens.
# Note: Only one email provider at a time (tools have overlapping method names)
tools = []
plugins = [re_act]

has_gmail = _provider_is_linked(
    "LINKED_GMAIL",
    "GOOGLE_ACCESS_TOKEN",
    "GOOGLE_REFRESH_TOKEN",
)
has_outlook = _provider_is_linked(
    "LINKED_OUTLOOK",
    "MICROSOFT_ACCESS_TOKEN",
    "MICROSOFT_REFRESH_TOKEN",
)

# Prefer Gmail if both are linked (can only use one due to method name conflicts)
system_prompt = "prompts/main_agent_step.md"

if has_gmail:
    from connectonion import Gmail, GoogleCalendar

    class GmailCompat(OpenAICompatibleGmailMixin, Gmail):
        pass

    tools.append(GmailCompat())
    tools.append(GoogleCalendar())
    plugins.append(build_gmail_sync_plugin(_get_primary_email_tool))
    plugins.append(calendar_approval_plugin)
    system_prompt = "prompts/gmail_agent.md"
elif has_outlook:
    try:
        from connectonion import Outlook, MicrosoftCalendar
    except ImportError:
        tools.append(UnavailableEmailProvider("outlook"))
    else:
        tools.append(Outlook())
        tools.append(MicrosoftCalendar())
    system_prompt = "prompts/outlook_agent.md"

# Warn if no email provider configured
if not tools:
    print("\n⚠️  No email account connected. Use /link-gmail or /link-outlook to connect.\n")

# Create init sub-agent for CRM database setup
init_crm = _build_configured_agent(
    reason_prefix="CRM init agent is unavailable",
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
    tools.extend(
        [
            get_unsubscribe_info,
            post_one_click_unsubscribe,
        ]
    )

compat_tools = ToolCollection(tools)
if has_gmail and tools:
    compat_tools.gmail = tools[0]
elif has_outlook and tools:
    compat_tools.outlook = tools[0]

# Create main execution agent
main_agent = _build_configured_agent(
    reason_prefix="Main email agent is unavailable",
    name="email-agent",
    system_prompt=PROMPTS_DIR / "main_agent_step.md",
    tools=tools,
    plugins=plugins,
    max_iterations=15,
    model=MODEL_NAME,
)

# Intent and orchestration helper agents are lightweight single-step LLM calls.
intent_agent = _build_configured_agent(
    reason_prefix="Intent layer agent is unavailable",
    name="email-agent-intent-layer",
    system_prompt=PROMPTS_DIR / "intent_layer.md",
    tools=[],
    max_iterations=1,
    model=INTENT_MODEL_NAME,
)

planner_agent = _build_configured_agent(
    reason_prefix="Planner agent is unavailable",
    name="email-agent-planner",
    system_prompt=PROMPTS_DIR / "planner.md",
    tools=[],
    max_iterations=1,
    model=PLANNER_MODEL_NAME,
)

skill_input_resolver_agent = _build_configured_agent(
    reason_prefix="Skill input resolver agent is unavailable",
    name="email-agent-skill-input-resolver",
    system_prompt=PROMPTS_DIR / "skill_input_resolver.md",
    tools=[],
    max_iterations=1,
    model=SKILL_INPUT_RESOLVER_MODEL_NAME,
)

finalizer_agent = _build_configured_agent(
    reason_prefix="Finalizer agent is unavailable",
    name="email-agent-finalizer",
    system_prompt=PROMPTS_DIR / "finalizer.md",
    tools=[],
    max_iterations=1,
    model=FINALIZER_MODEL_NAME,
)

user_memory_writer_agent = _build_configured_agent(
    reason_prefix="User memory writer agent is unavailable",
    name="email-agent-user-memory-writer",
    system_prompt=PROMPTS_DIR / "user_memory_writer.md",
    tools=[],
    max_iterations=1,
    model=USER_MEMORY_MODEL_NAME,
)

writing_style_writer_agent = _build_configured_agent(
    reason_prefix="Writing style writer agent is unavailable",
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
    planner_agent=planner_agent,
    skill_input_resolver_agent=skill_input_resolver_agent,
    finalizer_agent=finalizer_agent,
    skill_executor=skill_executor,
    memory_store=memory_store,
    skill_registry_path=SKILL_REGISTRY_PATH,
    writing_style_path=WRITING_STYLE_PATH,
    timezone_name=AGENT_TIMEZONE,
)
agent.tools = compat_tools

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
