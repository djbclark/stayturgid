import argparse
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.append(str(REPO_ROOT))

import hmac

import uvicorn
from mcp.server.fastmcp import Context, FastMCP
from starlette.middleware.base import BaseHTTPMiddleware
from starlette.responses import JSONResponse

import control.bin.firerpa_heal as heal
from control.lib.firerpa_auth import certificate_path
from control.lib.firerpa_consent import HealSession, check_consent
from control.lib.firerpa_fleet import get_fleet
from control.lib.site_logging import WARNING, log

LOG_NAME = "firerpa-mcp.log"


def _log(level: int, msg: str) -> None:
    # stdout is the MCP stdio transport's JSON-RPC protocol channel when
    # this server runs with --transport stdio — never print diagnostics
    # there, the log file is the only sink.
    log(LOG_NAME, level, msg)


try:
    from lamda.client import Device
except ImportError:
    Device = None


def get_bearer_token() -> str | None:
    try:
        res = subprocess.run(
            [
                "sudo",
                "-n",
                "-u",
                "_secretspec",
                "/usr/local/libexec/stayturgid-secretspec-wrapper.sh",
                "get",
                "firerpa_mcp_token",
            ],
            capture_output=True,
            text=True,
            check=True,
        )
        token = res.stdout.strip()
        return token if token else None
    except Exception:
        return None


def get_tailscale_ip() -> str:
    res = subprocess.run(["tailscale", "ip", "-4"], capture_output=True, text=True, check=False)
    if res.returncode == 0:
        for line in res.stdout.strip().splitlines():
            line = line.strip()
            if line and not line.startswith("Warning"):
                return line
    return "127.0.0.1"


class TokenAuthMiddleware(BaseHTTPMiddleware):
    def __init__(self, app, token: str):
        super().__init__(app)
        self.token = token

    async def dispatch(self, request, call_next):
        auth_header = request.headers.get("Authorization")
        if not auth_header or not auth_header.startswith("Bearer "):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        token = auth_header.split(" ")[1]
        if not hmac.compare_digest(token, self.token):
            return JSONResponse({"error": "Unauthorized"}, status_code=401)
        return await call_next(request)


mcp = FastMCP("FIRERPA")


@mcp.tool()
def list_fleet() -> list[dict]:
    fleet = get_fleet()
    return [{"alias": f.alias, "ip": f.ip} for f in fleet]


def _resolve_host(host_alias: str):
    fleet = get_fleet()
    for f in fleet:
        if f.alias == host_alias:
            return f
    return None


def _connect(host_alias: str):
    if Device is None:
        raise RuntimeError("lamda-client not installed")
    f = _resolve_host(host_alias)
    if not f:
        raise ValueError(f"Unknown host alias: {host_alias}")
    try:
        return Device(f.ip, port=f.port, certificate=certificate_path())
    except Exception as e:
        raise RuntimeError(f"Failed to connect to FIRERPA on {host_alias}: {e}")


@mcp.tool()
def device_status(host: str) -> dict:
    try:
        d = _connect(host)
        info = d.server_info()
        return {
            "firerpa": info.version,
            "sshd": "up" if heal.is_sshd_alive(d) else "down",
            "shizuku": "up" if heal.is_port_5555_alive(d) else "down",
            "bootloop": "up" if heal.is_bootloop_alive(d) else "down",
        }
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def heal_device(host: str, ctx: Context) -> dict:
    try:
        _resolve_host(host)
    except Exception as e:
        return {"error": str(e)}

    if not await check_consent(f"heal_device on {host}", ctx):
        return {"status": "refused"}
    try:
        d = _connect(host)
        session = HealSession(d, host)
        try:
            results = {}
            sshd_alive = heal.is_sshd_alive(d)
            port5555_alive = heal.is_port_5555_alive(d)
            bootloop_alive = heal.is_bootloop_alive(d)

            results["sshd"] = "up" if sshd_alive else "down"
            results["shizuku"] = "up" if port5555_alive else "down"
            results["bootloop"] = "up" if bootloop_alive else "down"

            if not sshd_alive:
                session.add_action("remove_sshd_down")
                results["sshd_down_file"] = heal.remove_sshd_down(d)
                if not heal.is_sshd_alive(d):
                    session.add_action("restart_sshd")
                    results["sshd_restart"] = heal.restart_sshd(d)

            if not port5555_alive:
                session.add_action("restart_shizuku")
                results["shizuku_restart"] = heal.restart_shizuku(d)

            if not bootloop_alive:
                session.add_action("restart_bootloop")
                results["bootloop_restart"] = heal.restart_bootloop(d)

            results["sshd_final"] = "up" if heal.is_sshd_alive(d) else "down"
            results["shizuku_final"] = "up" if heal.is_port_5555_alive(d) else "down"

            return results
        finally:
            session.close()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def restart_sshd(host: str, ctx: Context) -> dict:
    try:
        _resolve_host(host)
    except Exception as e:
        return {"error": str(e)}

    if not await check_consent(f"restart_sshd on {host}", ctx):
        return {"status": "refused"}
    try:
        d = _connect(host)
        session = HealSession(d, host)
        try:
            session.add_action("remove_sshd_down")
            heal.remove_sshd_down(d)
            session.add_action("restart_sshd")
            res = heal.restart_sshd(d)
            return {"status": res, "consent": "proceeded"}
        finally:
            session.close()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def restart_shizuku(host: str, ctx: Context) -> dict:
    try:
        _resolve_host(host)
    except Exception as e:
        return {"error": str(e)}

    if not await check_consent(f"restart_shizuku on {host}", ctx):
        return {"status": "refused"}
    try:
        d = _connect(host)
        session = HealSession(d, host)
        try:
            session.add_action("restart_shizuku")
            res = heal.restart_shizuku(d)
            return {"status": res}
        finally:
            session.close()
    except Exception as e:
        return {"error": str(e)}


@mcp.tool()
async def restart_bootloop(host: str, ctx: Context) -> dict:
    try:
        _resolve_host(host)
    except Exception as e:
        return {"error": str(e)}

    if not await check_consent(f"restart_bootloop on {host}", ctx):
        return {"status": "refused"}
    try:
        d = _connect(host)
        session = HealSession(d, host)
        try:
            session.add_action("restart_bootloop")
            res = heal.restart_bootloop(d)
            return {"status": res}
        finally:
            session.close()
    except Exception as e:
        return {"error": str(e)}


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--transport", choices=["stdio", "streamable-http"], default="stdio")
    parser.add_argument("--host", default=None)
    parser.add_argument("--port", type=int, default=8000)
    args = parser.parse_args()

    if args.transport == "stdio":
        mcp.run("stdio")
    elif args.transport == "streamable-http":
        app = mcp.streamable_http_app()
        token = get_bearer_token()
        if token:
            app.add_middleware(TokenAuthMiddleware, token=token)
        else:
            _log(WARNING, "Starting HTTP transport without token authentication. This is insecure!")

        host = args.host or get_tailscale_ip()
        uvicorn.run(app, host=host, port=args.port)


if __name__ == "__main__":
    main()
