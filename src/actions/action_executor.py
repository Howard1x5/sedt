"""
ActionExecutor - Executes actions on Windows endpoints.

This script runs on the Windows VM and receives commands from the
Linux-based DecisionEngine via SSH. It executes real Windows actions
that generate authentic Sysmon/Windows Event logs.

Usage:
    python action_executor.py --action '{"action_type": "open_application", "target": "notepad", "parameters": {}}'

The script outputs JSON to stdout for the RemoteExecutor to parse.
"""

import argparse
import json
import os
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from typing import Callable, Dict, Any


class ActionExecutor:
    """
    Executes Windows actions to generate realistic telemetry.

    Each action method should:
    1. Perform a real Windows operation
    2. Return success/failure status
    3. Generate authentic Sysmon events as a side effect
    """

    def __init__(self):
        """Initialize the action executor with available actions."""
        self.actions: Dict[str, Callable] = {
            "open_application": self.open_application,
            "close_application": self.close_application,
            "browse_web": self.browse_web,
            "create_file": self.create_file,
            "edit_file": self.edit_file,
            "delete_file": self.delete_file,
            "copy_file": self.copy_file,
            "check_email": self.check_email,
            "send_email": self.send_email,
            "idle": self.idle,
            "type_text": self.type_text,
            "click": self.click,
            "powershell": self.run_powershell,
            "file_operation": self.file_operation,
            # Document actions
            "edit_spreadsheet": self.edit_spreadsheet,
            "create_document": self.create_document,
            "create_presentation": self.create_presentation,
            # Download action
            "download_file": self.download_file,
        }

    def execute(self, action_type: str, target: str, parameters: dict) -> dict:
        """
        Execute an action and return the result.

        Args:
            action_type: The type of action to execute
            target: The target of the action
            parameters: Additional parameters

        Returns:
            Dictionary with success, output, error, duration_ms
        """
        start_time = time.time()

        if action_type not in self.actions:
            return {
                "success": False,
                "error": f"Unknown action type: {action_type}",
                "duration_ms": 0
            }

        try:
            result = self.actions[action_type](target, parameters)
            duration_ms = int((time.time() - start_time) * 1000)

            return {
                "success": True,
                "output": result if isinstance(result, str) else str(result),
                "error": "",
                "duration_ms": duration_ms
            }

        except Exception as e:
            duration_ms = int((time.time() - start_time) * 1000)
            return {
                "success": False,
                "output": "",
                "error": str(e),
                "duration_ms": duration_ms
            }

    # ==================== Application Actions ====================

    def open_application(self, target: str, parameters: dict) -> str:
        """
        Open an application by name.

        Generates: Sysmon Event ID 1 (Process Creation)
        """
        app_paths = {
            # System apps (always available)
            "notepad": "notepad.exe",
            "explorer": "explorer.exe",
            "cmd": "cmd.exe",
            "powershell": "powershell.exe",
            "calculator": "calc.exe",
            "paint": "mspaint.exe",
            "snipping_tool": "SnippingTool.exe",
            "wordpad": "notepad.exe",  # WordPad not on lean Win11
            # Edge browser (default on Windows 11)
            "edge": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "browser": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
            "chrome": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",  # Fallback to Edge
            # Office apps (may not be installed - fallback to alternatives)
            "word": "notepad.exe",  # Fallback to Notepad
            "excel": "notepad.exe",  # Fallback to Notepad
            "powerpoint": "notepad.exe",  # Fallback to Notepad
            "outlook": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",  # Open webmail
            "teams": r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",  # Open web teams
        }

        app_path = app_paths.get(target.lower(), target)
        app_path = os.path.expandvars(app_path)

        # For system apps, use full path in System32
        if not os.path.exists(app_path) and "\\" not in app_path:
            system32_path = os.path.join(os.environ.get("SystemRoot", "C:\\Windows"), "System32", app_path)
            if os.path.exists(system32_path):
                app_path = system32_path

        # Launch directly - parent will be python.exe
        # This creates cleaner process tree than using cmd.exe shell
        subprocess.Popen([app_path])

        return f"Opened {target}"

    def close_application(self, target: str, parameters: dict) -> str:
        """
        Close an application by process name.

        Generates: Sysmon Event ID 5 (Process Terminated)
        """
        process_name = target if target.endswith(".exe") else f"{target}.exe"

        subprocess.run(
            f'taskkill /IM "{process_name}" /F',
            shell=True,
            capture_output=True
        )

        return f"Closed {target}"

    # ==================== Browser Actions ====================

    def browse_web(self, target: str, parameters: dict) -> str:
        """
        Open a URL in the default browser.

        Generates:
        - Sysmon Event ID 1 (Process Creation for browser)
        - Sysmon Event ID 3 (Network Connection)
        - Sysmon Event ID 22 (DNS Query)
        """
        url = target if target.startswith("http") else f"https://{target}"
        duration = parameters.get("duration_seconds", 30)

        # Open URL in default browser
        subprocess.Popen(
            f'start "" "{url}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        # Simulate browsing time
        if duration > 0:
            time.sleep(min(duration, 5))  # Cap at 5 seconds for responsiveness

        return f"Browsed to {url}"

    # ==================== File Actions ====================

    def create_file(self, target: str, parameters: dict) -> str:
        """
        Create a new file with optional content.

        Generates: Sysmon Event ID 11 (File Created)
        """
        content = parameters.get("content", "")
        file_path = Path(os.path.expandvars(target))

        # Ensure parent directory exists
        file_path.parent.mkdir(parents=True, exist_ok=True)

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        return f"Created {file_path}"

    def edit_file(self, target: str, parameters: dict) -> str:
        """
        Edit/append to an existing file.

        Generates: Sysmon Event ID 11 (File Modified)
        """
        content = parameters.get("content", "")
        mode = parameters.get("mode", "append")  # "append" or "overwrite"
        file_path = Path(os.path.expandvars(target))

        if not file_path.exists():
            raise FileNotFoundError(f"File not found: {file_path}")

        write_mode = "a" if mode == "append" else "w"
        with open(file_path, write_mode, encoding="utf-8") as f:
            f.write(content)

        return f"Edited {file_path}"

    def delete_file(self, target: str, parameters: dict) -> str:
        """
        Delete a file.

        Generates: Sysmon Event ID 23 (File Delete)
        """
        file_path = Path(os.path.expandvars(target))

        if file_path.exists():
            file_path.unlink()
            return f"Deleted {file_path}"
        else:
            return f"File not found: {file_path}"

    def copy_file(self, target: str, parameters: dict) -> str:
        """
        Copy a file to a new location.

        Generates: Sysmon Event ID 11 (File Created)
        """
        destination = parameters.get("destination")
        if not destination:
            raise ValueError("destination parameter required for copy_file")

        source = Path(os.path.expandvars(target))
        dest = Path(os.path.expandvars(destination))

        import shutil
        shutil.copy2(source, dest)

        return f"Copied {source} to {dest}"

    def file_operation(self, target: str, parameters: dict) -> str:
        """
        Perform a file operation (create, copy, move, delete).

        Generates: Sysmon Event ID 11, 23 (File Created/Deleted)
        """
        import shutil
        import random
        import string

        # Use Downloads folder - Sysmon SwiftOnSecurity config monitors all files here
        base_path = Path(os.path.expandvars(parameters.get("path", "C:\\Users\\analyst\\Downloads")))
        base_path.mkdir(parents=True, exist_ok=True)

        # Generate realistic filename
        prefixes = ["Report", "Notes", "Draft", "Meeting", "Summary", "Budget", "Plan"]
        extensions = [".txt", ".docx", ".xlsx", ".pdf", ".csv"]
        filename = f"{random.choice(prefixes)}_{random.randint(1, 999)}{random.choice(extensions)}"
        file_path = base_path / filename

        if target == "create_file":
            content = f"Created at {datetime.now().isoformat()}\n"
            content += ''.join(random.choices(string.ascii_letters + ' ', k=random.randint(50, 200)))
            with open(file_path, "w", encoding="utf-8") as f:
                f.write(content)
            return f"Created {file_path}"

        elif target == "copy_file":
            # Find an existing file to copy
            existing = list(base_path.glob("*.*"))
            if existing:
                source = random.choice(existing)
                dest = base_path / f"Copy_of_{source.name}"
                shutil.copy2(source, dest)
                return f"Copied {source} to {dest}"
            return "No files to copy"

        elif target == "move_file":
            existing = list(base_path.glob("*.*"))
            if existing:
                source = random.choice(existing)
                archive = base_path / "Archive"
                archive.mkdir(exist_ok=True)
                dest = archive / source.name
                shutil.move(str(source), str(dest))
                return f"Moved {source} to {dest}"
            return "No files to move"

        elif target == "delete_file":
            # Only delete temp/draft files
            temp_files = list(base_path.glob("*.tmp")) + list(base_path.glob("Draft_*"))
            if temp_files:
                to_delete = random.choice(temp_files)
                to_delete.unlink()
                return f"Deleted {to_delete}"
            return "No temp files to delete"

        return f"Unknown file operation: {target}"

    def download_file(self, target: str, parameters: dict) -> str:
        """
        Download a file from a URL to the Downloads folder.

        Generates:
        - Sysmon Event ID 1 (Process Creation - PowerShell/curl)
        - Sysmon Event ID 3 (Network Connection)
        - Sysmon Event ID 11 (File Created)
        - Sysmon Event ID 22 (DNS Query)
        """
        import random
        import urllib.parse

        # Default safe URLs for benign downloads (public domain / safe sources)
        safe_urls = [
            "https://www.gutenberg.org/files/1342/1342-0.txt",  # Pride and Prejudice
            "https://www.gutenberg.org/files/84/84-0.txt",      # Frankenstein
            "https://www.gutenberg.org/files/11/11-0.txt",      # Alice in Wonderland
            "https://raw.githubusercontent.com/datasets/covid-19/main/data/countries-aggregated.csv",
            "https://raw.githubusercontent.com/datasets/population/master/data/population.csv",
        ]

        # Use provided URL or pick a safe default
        if target and target.startswith("http"):
            url = target
        else:
            url = random.choice(safe_urls)

        # Determine filename from URL or generate one
        filename = parameters.get("filename")
        if not filename:
            parsed = urllib.parse.urlparse(url)
            filename = os.path.basename(parsed.path) or f"download_{random.randint(1000, 9999)}.txt"

        # Download to Downloads folder
        download_path = Path(os.path.expandvars(r"C:\Users\analyst\Downloads"))
        download_path.mkdir(parents=True, exist_ok=True)
        file_path = download_path / filename

        # Use PowerShell Invoke-WebRequest for realistic telemetry
        # This generates process creation + network events
        ps_command = f'Invoke-WebRequest -Uri "{url}" -OutFile "{file_path}" -UseBasicParsing'

        try:
            result = subprocess.run(
                ["powershell", "-Command", ps_command],
                capture_output=True,
                text=True,
                timeout=60
            )

            if result.returncode != 0:
                # Try alternative method with curl if available
                curl_result = subprocess.run(
                    ["curl", "-L", "-o", str(file_path), url],
                    capture_output=True,
                    text=True,
                    timeout=60
                )
                if curl_result.returncode != 0:
                    raise RuntimeError(f"Download failed: {result.stderr or curl_result.stderr}")

            return f"Downloaded {url} to {file_path}"

        except subprocess.TimeoutExpired:
            return f"Download timed out for {url}"

    # ==================== Email Actions ====================

    def check_email(self, target: str, parameters: dict) -> str:
        """
        Simulate checking email by opening Outlook.

        Generates: Process creation events for Outlook
        """
        return self.open_application("outlook", parameters)

    def send_email(self, target: str, parameters: dict) -> str:
        """
        Simulate sending an email (opens compose window).

        For actual email sending, would need COM automation.
        """
        recipient = target
        subject = parameters.get("subject", "")
        body = parameters.get("body", "")

        # Use mailto: protocol
        mailto_url = f"mailto:{recipient}?subject={subject}&body={body}"
        subprocess.Popen(
            f'start "" "{mailto_url}"',
            shell=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )

        return f"Opened email compose to {recipient}"

    # ==================== Input Simulation ====================

    def type_text(self, target: str, parameters: dict) -> str:
        """
        Type text into the active window.

        Requires pyautogui or similar library.
        """
        try:
            import pyautogui
            pyautogui.typewrite(target, interval=0.05)
            return f"Typed {len(target)} characters"
        except ImportError:
            # Fallback: use PowerShell SendKeys
            escaped = target.replace("'", "''")
            ps_script = f"""
            Add-Type -AssemblyName System.Windows.Forms
            [System.Windows.Forms.SendKeys]::SendWait('{escaped}')
            """
            subprocess.run(["powershell", "-Command", ps_script], capture_output=True)
            return f"Typed {len(target)} characters (SendKeys)"

    def click(self, target: str, parameters: dict) -> str:
        """
        Click at specified coordinates or find and click element.

        Requires pyautogui.
        """
        x = parameters.get("x", 0)
        y = parameters.get("y", 0)

        try:
            import pyautogui
            pyautogui.click(x, y)
            return f"Clicked at ({x}, {y})"
        except ImportError:
            return "pyautogui not available for click action"

    # ==================== Utility Actions ====================

    def idle(self, target: str, parameters: dict) -> str:
        """
        Simulate idle time (worker taking a break, thinking, etc.)

        Generates: No events (intentionally quiet period)
        """
        duration = parameters.get("duration_minutes", 1)
        # Scale down for testing - 1 minute = 1 second
        time.sleep(min(duration, 5))
        return f"Idle for {duration} minutes"

    def run_powershell(self, target: str, parameters: dict) -> str:
        """
        Execute arbitrary PowerShell command.

        Generates: Sysmon Event ID 1 (PowerShell process)
        """
        result = subprocess.run(
            ["powershell", "-Command", target],
            capture_output=True,
            text=True,
            timeout=30
        )

        if result.returncode != 0:
            raise RuntimeError(f"PowerShell error: {result.stderr}")

        return result.stdout.strip()

    # ==================== Document Actions ====================

    def edit_spreadsheet(self, target: str, parameters: dict) -> str:
        """
        Create or edit a spreadsheet (CSV format since Office not installed).

        Generates: Sysmon Event ID 11 (File Created/Modified)
        """
        import csv
        import random

        # Default to Downloads folder for Sysmon visibility
        if not target or target == "spreadsheet":
            base_path = Path(os.path.expandvars(r"C:\Users\analyst\Downloads"))
            base_path.mkdir(parents=True, exist_ok=True)
            filename = f"Budget_Report_{random.randint(100, 999)}.csv"
            file_path = base_path / filename
        else:
            file_path = Path(os.path.expandvars(target))

        # Generate realistic spreadsheet content
        content_type = parameters.get("content_type", "budget")
        rows = parameters.get("rows", random.randint(10, 30))

        data = []
        if content_type == "budget":
            headers = ["Category", "Q1", "Q2", "Q3", "Q4", "Total"]
            categories = ["Marketing", "Sales", "Operations", "IT", "HR", "R&D"]
            data.append(headers)
            for cat in categories[:rows]:
                q_values = [random.randint(5000, 50000) for _ in range(4)]
                data.append([cat] + q_values + [sum(q_values)])
        elif content_type == "contacts":
            headers = ["Name", "Email", "Phone", "Department"]
            data.append(headers)
            names = ["John Smith", "Jane Doe", "Bob Wilson", "Alice Chen", "Mike Johnson"]
            depts = ["Marketing", "Sales", "Engineering", "Support", "Finance"]
            for i in range(min(rows, len(names))):
                data.append([names[i], f"{names[i].lower().replace(' ', '.')}@company.com",
                           f"555-{random.randint(1000, 9999)}", random.choice(depts)])
        else:
            headers = ["Item", "Value", "Notes"]
            data.append(headers)
            for i in range(rows):
                data.append([f"Item_{i+1}", random.randint(1, 100), ""])

        # Write CSV file
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerows(data)

        # Open in notepad to simulate viewing/editing
        subprocess.Popen(["notepad.exe", str(file_path)])

        return f"Created spreadsheet {file_path} with {len(data)} rows"

    def create_document(self, target: str, parameters: dict) -> str:
        """
        Create a text document (RTF/TXT since Office not installed).

        Generates: Sysmon Event ID 11 (File Created)
        """
        import random

        # Default to Documents folder
        if not target or target == "document":
            base_path = Path(os.path.expandvars(r"C:\Users\analyst\Documents"))
            base_path.mkdir(parents=True, exist_ok=True)
            doc_types = ["Meeting_Notes", "Report", "Memo", "Summary", "Draft"]
            filename = f"{random.choice(doc_types)}_{datetime.now().strftime('%Y%m%d_%H%M')}.txt"
            file_path = base_path / filename
        else:
            file_path = Path(os.path.expandvars(target))

        # Generate realistic document content
        doc_type = parameters.get("doc_type", "meeting_notes")
        content = parameters.get("content", "")

        if not content:
            if doc_type == "meeting_notes":
                content = f"""Meeting Notes - {datetime.now().strftime('%B %d, %Y')}

Attendees: Marketing Team

Agenda:
1. Q4 Campaign Review
2. Budget Discussion
3. Upcoming Initiatives

Notes:
- Discussed performance metrics from Q4
- Budget allocation for next quarter approved
- Action items assigned to team leads

Next Meeting: TBD
"""
            elif doc_type == "report":
                content = f"""Weekly Status Report
Date: {datetime.now().strftime('%Y-%m-%d')}
Author: Analyst

Summary:
This week's activities included regular operational tasks,
team meetings, and project updates.

Key Accomplishments:
- Completed quarterly review
- Updated documentation
- Attended training session

Next Week:
- Continue project work
- Prepare monthly report
"""
            else:
                content = f"Document created at {datetime.now().isoformat()}\n\n[Content placeholder]"

        # Write document
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Open in notepad
        subprocess.Popen(["notepad.exe", str(file_path)])

        return f"Created document {file_path}"

    def create_presentation(self, target: str, parameters: dict) -> str:
        """
        Create a presentation outline (TXT since PowerPoint not installed).

        Generates: Sysmon Event ID 11 (File Created)
        """
        import random

        # Default to Documents folder
        if not target or target == "presentation":
            base_path = Path(os.path.expandvars(r"C:\Users\analyst\Documents"))
            base_path.mkdir(parents=True, exist_ok=True)
            topics = ["Quarterly_Review", "Project_Update", "Strategy", "Training"]
            filename = f"{random.choice(topics)}_Presentation_{datetime.now().strftime('%Y%m%d')}.txt"
            file_path = base_path / filename
        else:
            file_path = Path(os.path.expandvars(target))

        # Generate presentation outline
        topic = parameters.get("topic", "Quarterly Review")
        slides = parameters.get("slides", random.randint(5, 10))

        content = f"""PRESENTATION OUTLINE
====================
Title: {topic}
Date: {datetime.now().strftime('%B %d, %Y')}

---

SLIDE 1: Title Slide
- {topic}
- Presented by: Marketing Team

SLIDE 2: Agenda
- Overview
- Key Points
- Discussion
- Q&A

SLIDE 3: Executive Summary
- Main takeaways
- Key metrics
- Recommendations

"""
        for i in range(4, slides + 1):
            content += f"""SLIDE {i}: Topic {i-3}
- Point 1
- Point 2
- Supporting data

"""

        content += """FINAL SLIDE: Questions?
- Contact information
- Next steps
"""

        # Write presentation outline
        file_path.parent.mkdir(parents=True, exist_ok=True)
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)

        # Open in notepad
        subprocess.Popen(["notepad.exe", str(file_path)])

        return f"Created presentation outline {file_path}"


def run_server(host: str = "0.0.0.0", port: int = 9999):
    """
    Run ActionExecutor as a persistent socket server.

    This allows the executor to be started at login (via Startup folder)
    and have explorer.exe as its parent process, creating realistic
    process trees for spawned applications.
    """
    import socket

    executor = ActionExecutor()

    server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind((host, port))
    server.listen(5)

    print(f"ActionExecutor server listening on {host}:{port}", flush=True)

    while True:
        try:
            client, addr = server.accept()

            # Receive JSON command
            data = b""
            while True:
                chunk = client.recv(4096)
                if not chunk:
                    break
                data += chunk
                # Check for complete JSON (simple heuristic)
                if data.strip().endswith(b"}"):
                    break

            if not data:
                client.close()
                continue

            try:
                payload = json.loads(data.decode('utf-8'))
                result = executor.execute(
                    action_type=payload.get("action_type", ""),
                    target=payload.get("target", ""),
                    parameters=payload.get("parameters", {})
                )
            except json.JSONDecodeError as e:
                result = {"success": False, "error": f"Invalid JSON: {e}"}
            except Exception as e:
                result = {"success": False, "error": str(e)}

            # Send response
            client.sendall(json.dumps(result).encode('utf-8'))
            client.close()

        except Exception as e:
            print(f"Server error: {e}", flush=True)


def main():
    """CLI entry point for ActionExecutor."""
    parser = argparse.ArgumentParser(description="Execute Windows actions")
    parser.add_argument(
        "--action",
        help='JSON action payload: {"action_type": "...", "target": "...", "parameters": {}}'
    )
    parser.add_argument(
        "--server",
        action="store_true",
        help="Run in persistent server mode (listens on port 9999)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=9999,
        help="Port for server mode (default: 9999)"
    )

    args = parser.parse_args()

    if args.server:
        run_server(port=args.port)
    elif args.action:
        try:
            payload = json.loads(args.action)
        except json.JSONDecodeError as e:
            print(json.dumps({"success": False, "error": f"Invalid JSON: {e}"}))
            sys.exit(1)

        executor = ActionExecutor()
        result = executor.execute(
            action_type=payload.get("action_type", ""),
            target=payload.get("target", ""),
            parameters=payload.get("parameters", {})
        )

        print(json.dumps(result))
    else:
        parser.print_help()


if __name__ == "__main__":
    main()
