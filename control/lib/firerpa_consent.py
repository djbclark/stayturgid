import os
import subprocess
import time
from typing import Any

from mcp.server.fastmcp import Context
from pydantic import BaseModel, Field

FIRERPA_HEAL_COUNTDOWN_SEC = 10


class ConsentSchema(BaseModel):
    consent: str = Field(
        description="Action consent: type 'proceed' to allow, 'refuse' to abort.",
        default="proceed",
    )


class HealSession:
    def __init__(self, device: Any, alias: str) -> None:
        self.device = device
        self.alias = alias
        self.actions: list[str] = []

    def add_action(self, action: str) -> None:
        self.actions.append(action)
        self.update_notifications()

    def update_notifications(self) -> None:
        now = time.strftime("%H:%M")
        summary = " · ".join(self.actions)
        msg = f"stayturgid heal {self.alias}: {summary} ({now})"
        cmd = f"termux-notification --id stayturgid-firerpa-heal --title 'FIRERPA Heal' --content '{msg}'"
        try:
            self.device.execute_script(cmd, timeout=5)
        except Exception:
            pass

    def close(self) -> None:
        try:
            self.device.execute_script("termux-notification-remove stayturgid-firerpa-heal", timeout=5)
        except Exception:
            pass

        if self.actions:
            mac_msg = f"healed {self.alias}: {', '.join(self.actions)} ({len(self.actions)} actions)"
            subprocess.run(
                ["osascript", "-e", f'display notification "{mac_msg}" with title "FIRERPA Heal"'],
                check=False,
            )


async def check_consent(action_summary: str, context: Context | None = None) -> bool:
    if os.environ.get("STAYTURGID_FIRERPA_HEAL_NOCONSENT") == "1":
        return True

    if os.environ.get("STAYTURGID_FIRERPA_HEAL_QUIET") == "1":
        return True

    # Try MCP Elicitation if supported
    if context:
        try:
            res = await context.elicit(
                f"A mutating heal tool has been requested: {action_summary}. Type 'proceed' or 'refuse'.",
                ConsentSchema,
            )
            if isinstance(res, dict):
                return res.get("consent", "proceed").lower() != "refuse"
            return res.consent.lower() != "refuse"
        except Exception:
            pass  # Fall back to osascript on error

    # Fallback to osascript
    script = f"""
    try
        display dialog "A mutating heal tool has been requested: {action_summary}." buttons {{"Refuse", "Proceed now"}} default button "Proceed now" giving up after {FIRERPA_HEAL_COUNTDOWN_SEC}
        set res to button returned of result
        if res is "Refuse" then
            return "refuse"
        else
            return "proceed"
        end if
    on error
        return "refuse"
    end try
    """
    res = subprocess.run(["osascript", "-e", script], capture_output=True, text=True, check=False)
    out = res.stdout.strip()
    return out != "refuse"
