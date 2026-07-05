"""A simple HTTP server that serves files from multiple root directories."""

import json
import subprocess
from pathlib import Path
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer


import os
from dotenv import load_dotenv

load_dotenv()
WEB_SERVER_PORT = int(os.getenv("PORT", "8000"))

root_dir = Path(__file__).parent.parent
dataset_dir = root_dir / "datasets"

# Directories to serve files from
REAL_DIRS = [
    dataset_dir,
    dataset_dir / "assets",
    root_dir / "results",
    root_dir / "web",
]


class CustomHandler(SimpleHTTPRequestHandler):
    """HTTP request handler that serves files from multiple root directories."""

    def _is_ajax(self) -> bool:
        xrw = (self.headers.get("X-Requested-With") or "").lower()
        accept = (self.headers.get("Accept") or "").lower()
        return xrw == "xmlhttprequest" or "application/json" in accept

    def _send_json(self, status_code: int, payload: dict) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status_code)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def send_header(self, keyword, value):
        # Ensure text/html and application/json responses include charset=utf-8
        if keyword.lower() == "content-type" and "charset" not in (value or "").lower():
            if (value or "").startswith("text/html") or (value or "").startswith("application/json"):
                value = f"{value}; charset=utf-8"
        super().send_header(keyword, value)

    def send_error(self, code, message=None, explain=None):
        if self._is_ajax():
            # JSON error payload for AJAX
            payload = {
                "status": "error",
                "code": code,
                "message": message or self.responses.get(code, ("", ""))[0],
                "path": self.path,
                "method": self.command,
            }
            body = json.dumps(payload).encode("utf-8")
            self.send_response(code, message)
            self.send_header("Content-Type", "application/json; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)
        else:
            super().send_error(code, message, explain)

    def translate_path(self, path):
        """Map URL path to one of the ROOTS directories."""
        # Strip leading slash
        rel_path = path.lstrip("/")

        # Special handling for image files: serve from root assets directory
        if rel_path.endswith((".jpg", ".svg")):
            rel_path = Path(rel_path).name

        # Try to find the file in each folder
        for root in REAL_DIRS:
            candidate = Path(root) / rel_path
            if candidate.exists():
                return candidate.as_posix()

        # Default: 404 Not Found
        return "Resource not found"

    def do_POST(self):
        """Handle POST requests to execute commands."""
        content_length = int(self.headers.get("Content-Length", 0))
        body = self.rfile.read(content_length)
        data = json.loads(body)
        args = data.get("args", [])
        kwargs = data.get("kwargs", {})

        # Build and run the command
        module = self.path.lstrip("/").replace("/", ".")
        # Build command as a list (avoid shell when possible) and split kwargs
        cmd = ["python", "-m", module] + [str(arg) for arg in args]
        for key, value in kwargs.items():
            if isinstance(value, bool) and value:
                cmd.append(f"--{key}")
            else:
                cmd.extend([f"--{key}", str(value)])

        # Capture stdout/stderr and return them as text
        result = subprocess.run(cmd, capture_output=True, text=True, check=False)

        if result.returncode != 0:
            self._send_json(500, {"status": "error", "message": result.stderr or "", "returncode": result.returncode})
        else:
            self._send_json(200, {"status": "ok", "result": result.stdout or ""})


def run(port=WEB_SERVER_PORT):
    """Start the HTTP server on the specified port."""

    httpd = ThreadingHTTPServer(("", port), CustomHandler)
    print(f"Serving multiple roots at http://localhost:{port}")
    print("Serving from the following directories:")
    print("-Real Root Directories:")
    for p in REAL_DIRS:
        print(f"  - {p}")
    httpd.serve_forever()


if __name__ == "__main__":
    run()
