"""
Setup and auth checks for Email Agent CLI.
"""

from pathlib import Path
import os
import sys
from rich.console import Console
from rich.panel import Panel
from rich.markdown import Markdown
from rich.prompt import Prompt

console = Console()


def check_user_profile() -> None:
    """Prompt for user profile info if missing. Writes to agent memory.

    Currently collects: preferred sender name.
    Absence of data is the first-run signal - safe to call repeatedly.
    """
    from agent import memory, has_gmail
    try:
        from agent import _gmail
    except ImportError:
        _gmail = None

    existing = memory.read_memory("preference-sender-name")
    if not existing.startswith("Memory not found"):
        return

    if not sys.stdin.isatty():
        console.print(
            "[yellow]⚠ Sender name not set. Run "
            "[cyan]docker compose exec -it email-agent python cli.py profile[/cyan] "
            "to configure.[/yellow]"
        )
        return

    default = ""
    if has_gmail and _gmail is not None:
        try:
            default = _gmail.get_sender_name() or ""
        except Exception:
            default = ""

    console.print(Panel(
        "[bold]First-time profile setup[/bold]\n\n"
        "Your sender name is used to sign outgoing emails.\n"
        "[dim]This is stored once in agent memory and reused in future sessions.[/dim]",
        title="[bold]User Profile[/bold]",
        border_style="cyan",
        padding=(1, 2),
    ))

    try:
        answer = Prompt.ask(
            "What name should sign your emails?",
            default=default or None,
        )
    except (EOFError, KeyboardInterrupt):
        console.print("[yellow]Skipped. Run [cyan]email profile[/cyan] later to set this up.[/yellow]")
        return

    answer = (answer or "").strip()
    if not answer:
        console.print("[yellow]No name provided. Skipped.[/yellow]")
        return

    memory.write_memory("preference-sender-name", answer)
    console.print(f"[green]✓[/green] Saved sender name: [bold]{answer}[/bold]")
    console.print("[dim]New requests will pick this up automatically.[/dim]")


def check_setup(skip_init: bool = False) -> bool:
    """Check auth and CRM setup. Returns True if ready to proceed.

    Args:
        skip_init: If True, skip CRM init check (for commands that don't need it)
    """
    # Check if auth is set up (both LLM API key and Google tokens)
    has_llm_key = any([
        os.getenv('OPENAI_API_KEY'),
        os.getenv('ANTHROPIC_API_KEY'),
        os.getenv('GEMINI_API_KEY'),
        os.getenv('OPENROUTER_API_KEY'),
        os.getenv('OPENONION_API_KEY')
    ])
    has_google_token = os.getenv('GOOGLE_ACCESS_TOKEN')

    if not has_llm_key or not has_google_token:
        if not has_llm_key and not has_google_token:
            title = "LLM + Google Auth Required"
            body = (
                "You need an LLM provider key and Google auth before using the email agent.\n"
                "This will open a browser to grant Gmail permissions."
            )
            manual_steps = (
                "1. Set one LLM key in `.env` ([cyan]OPENAI_API_KEY[/cyan], [cyan]ANTHROPIC_API_KEY[/cyan], "
                "[cyan]GEMINI_API_KEY[/cyan], [cyan]OPENROUTER_API_KEY[/cyan], or [cyan]OPENONION_API_KEY[/cyan]) "
                "[dim]or run `co auth` for OpenOnion[/dim]\n"
                "2. [cyan]co auth google[/cyan]   (authenticate Google Gmail)\n\n"
                "Then restart this CLI."
            )
        elif not has_llm_key:
            title = "LLM Auth Required"
            body = (
                "You need an LLM provider key before using the email agent.\n"
                "You can use your own provider key in `.env` or run `co auth` for OpenOnion."
            )
            manual_steps = (
                "1. Set one LLM key in `.env` ([cyan]OPENAI_API_KEY[/cyan], [cyan]ANTHROPIC_API_KEY[/cyan], "
                "[cyan]GEMINI_API_KEY[/cyan], [cyan]OPENROUTER_API_KEY[/cyan], or [cyan]OPENONION_API_KEY[/cyan])\n"
                "2. Optional: [cyan]co auth[/cyan] if you want to use [cyan]co/*[/cyan] models\n\n"
                "Then restart this CLI."
            )
        else:
            title = "Google Auth Required"
            body = (
                "You already have an LLM key.\n"
                "You only need to authenticate with Google to grant Gmail permissions."
            )
            manual_steps = (
                "1. [cyan]co auth google[/cyan]   (authenticate Google Gmail)\n\n"
                "Then restart this CLI."
            )

        console.print(Panel(
            f"[bold red]{title}[/bold red]\n\n{body}",
            title="[bold]Setup Required[/bold]",
            border_style="red",
            padding=(1, 2)
        ))

        from connectonion import pick, Shell, Agent

        choice = pick("Run authentication now?", [
            "Yes, run authentication",
            "No, I'll do it manually"
        ])

        if "Yes" in choice:
            console.print("\n[dim]Running authentication...[/dim]\n")
            shell = Shell()
            auth_agent = Agent("auth-helper", tools=[shell], log=False)
            auth_agent.input("Run these commands: co auth, then co auth google")
            console.print("\n[green]✓ Please restart the CLI.[/green]\n")
        else:
            console.print(Panel(
                "[bold yellow]Manual Setup Required[/bold yellow]\n\n"
                "[bold]Please run these commands:[/bold]\n\n"
                f"{manual_steps}",
                border_style="yellow",
                padding=(1, 2)
            ))
        return False

    # Check if CRM is initialized (optional)
    if not skip_init:
        contacts_path = Path("data/contacts.csv")
        needs_init = not contacts_path.exists() or contacts_path.stat().st_size < 100

        if needs_init:
            console.print(Panel(
                "[bold yellow]CRM Not Initialized[/bold yellow]\n\n"
                "Initialize the CRM to:\n"
                "  • Extract contacts from emails\n"
                "  • Categorize people, services, notifications\n"
                "  • Set up your contact database\n\n"
                "[dim]Takes 2-3 minutes, only needs to run once.[/dim]",
                title="[bold]First Time Setup[/bold]",
                border_style="yellow",
                padding=(1, 2)
            ))

            from connectonion import pick
            choice = pick("Initialize CRM now?", [
                "Yes, initialize now",
                "Skip, I'll do it later with /init"
            ])

            if "Yes" in choice:
                console.print("\n[dim]Starting CRM initialization...[/dim]\n")
                from .core import do_init
                with console.status("[bold blue]Processing...[/bold blue]"):
                    result = do_init()
                console.print(Panel(Markdown(result), title="[bold green]✓ Done[/bold green]", border_style="green"))

    return True
