#!/usr/bin/env python3
"""NOVA v0.1 — a small, local workspace launcher for Linux desktops."""

from __future__ import annotations

import json
import os
import configparser
import re
import shlex
import subprocess
import time
import tkinter as tk
import uuid
from pathlib import Path
from tkinter import messagebox, simpledialog, ttk
from urllib.parse import unquote, urlparse


APP_DIR = Path.home() / ".local" / "share" / "nova"
DATA_FILE = APP_DIR / "workspaces.json"


class NovaApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("NOVA · Workspaces")
        self.geometry("820x610")
        self.minsize(680, 500)
        (self.workspaces, self.workspace_desktops,
         self.workspace_groups, self.desktop_labels) = self.load_data()
        self.workspace_names: list[str] = []
        self.desktop_ids: list[str] = []
        self._build_ui()
        self.refresh_workspaces()

    def load_data(self):
        try:
            data = json.loads(DATA_FILE.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                if isinstance(data.get("workspaces"), dict):
                    workspaces = {str(k): v for k, v in data["workspaces"].items() if isinstance(v, list)}
                    desktops = {str(k): int(v) for k, v in data.get("workspace_desktops", {}).items()
                                if str(k) in workspaces and isinstance(v, int) and v >= 0}
                    labels = {str(k): str(v) for k, v in data.get("desktop_labels", {}).items()
                              if str(k) in workspaces}
                    labels.update({key: key for key in workspaces if key not in labels})
                    groups = {str(k): [str(v) for v in values if str(v) in workspaces]
                              for k, values in data.get("workspace_groups", {}).items()
                              if isinstance(values, list)}
                else:
                    # Preserve all previously saved desktop sessions under one
                    # logical workspace; the user can split them into groups later.
                    workspaces = {str(k): v for k, v in data.items() if isinstance(v, list)}
                    desktops = {name: index for index, name in enumerate(workspaces)}
                    labels = {name: name for name in workspaces}
                    groups = {"Workspace 1": list(workspaces)} if workspaces else {}
                assigned = {child for values in groups.values() for child in values}
                ungrouped = [key for key in workspaces if key not in assigned]
                if ungrouped:
                    group_name = "Workspace 1" if "Workspace 1" not in groups else "Workspace"
                    suffix = 2
                    while group_name in groups:
                        group_name = f"Workspace {suffix}"
                        suffix += 1
                    groups[group_name] = ungrouped
                used = set(desktops.values())
                next_slot = 0
                for name in workspaces:
                    if name not in desktops:
                        while next_slot in used:
                            next_slot += 1
                        desktops[name] = next_slot
                        used.add(next_slot)
                for key in workspaces:
                    labels.setdefault(key, key)
                return workspaces, desktops, groups, labels
        except (OSError, json.JSONDecodeError):
            pass
        return {}, {}, {}, {}

    def save_data(self) -> None:
        APP_DIR.mkdir(parents=True, exist_ok=True)
        temp = DATA_FILE.with_suffix(".tmp")
        data = {"workspaces": self.workspaces, "workspace_desktops": self.workspace_desktops,
                "workspace_groups": self.workspace_groups, "desktop_labels": self.desktop_labels}
        temp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        temp.replace(DATA_FILE)
        self.status.set(f"Saved locally · {DATA_FILE}")

    def _build_ui(self) -> None:
        self.columnconfigure(1, weight=1)
        self.rowconfigure(1, weight=1)
        ttk.Label(self, text="NOVA", font=("TkDefaultFont", 20, "bold")).grid(
            row=0, column=0, sticky="w", padx=(18, 8), pady=14
        )
        ttk.Label(self, text="Keep your work together.", font=("TkDefaultFont", 11)).grid(
            row=0, column=1, sticky="w", pady=14
        )

        left = ttk.Frame(self, padding=(14, 0, 8, 10))
        left.grid(row=1, column=0, sticky="nsew")
        left.rowconfigure(1, weight=1)
        left.rowconfigure(5, weight=1)
        ttk.Label(left, text="WORKSPACES").grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.workspace_list = tk.Listbox(left, width=22, activestyle="none", exportselection=False)
        self.workspace_list.grid(row=1, column=0, sticky="nsew")
        self.workspace_list.bind("<<ListboxSelect>>", self.select_workspace)
        ttk.Button(left, text="＋ New workspace", command=self.new_workspace).grid(
            row=2, column=0, sticky="ew", pady=(8, 0)
        )
        group_actions = ttk.Frame(left)
        group_actions.grid(row=3, column=0, sticky="ew", pady=(5, 10))
        for column in range(2):
            group_actions.columnconfigure(column, weight=1)
        ttk.Button(group_actions, text="Rename", command=self.rename_workspace).grid(row=0, column=0, sticky="ew")
        ttk.Button(group_actions, text="Delete", command=self.delete_workspace).grid(row=0, column=1, sticky="ew", padx=(4, 0))
        ttk.Label(left, text="DESKTOPS IN WORKSPACE").grid(row=4, column=0, sticky="w", pady=(0, 6))
        self.desktop_list = tk.Listbox(left, width=22, height=5, activestyle="none", exportselection=False)
        self.desktop_list.grid(row=5, column=0, sticky="nsew")
        self.desktop_list.bind("<<ListboxSelect>>", self.select_desktop)
        ttk.Button(left, text="＋ Add desktop", command=self.new_desktop).grid(
            row=6, column=0, sticky="ew", pady=(7, 0)
        )
        desktop_actions = ttk.Frame(left)
        desktop_actions.grid(row=7, column=0, sticky="ew", pady=(5, 0))
        for column in range(2):
            desktop_actions.columnconfigure(column, weight=1)
        ttk.Button(desktop_actions, text="Rename desktop", command=self.rename_desktop).grid(row=0, column=0, sticky="ew")
        ttk.Button(desktop_actions, text="Remove desktop", command=self.delete_desktop).grid(row=0, column=1, sticky="ew", padx=(4, 0))

        main = ttk.Frame(self, padding=(8, 0, 18, 10))
        main.grid(row=1, column=1, sticky="nsew")
        main.rowconfigure(1, weight=1)
        main.columnconfigure(0, weight=1)
        self.heading = ttk.Label(main, text="Choose or create a workspace", font=("TkDefaultFont", 15, "bold"))
        self.heading.grid(row=0, column=0, sticky="w", pady=(0, 8))
        self.items = ttk.Treeview(main, columns=("kind", "value"), show="headings", selectmode="browse")
        self.items.heading("kind", text="TYPE")
        self.items.heading("value", text="ITEM")
        self.items.column("kind", width=90, stretch=False)
        self.items.column("value", width=440)
        self.items.grid(row=1, column=0, sticky="nsew")
        self.items.bind("<Delete>", lambda _e: self.remove_item())
        actions = ttk.Frame(main)
        actions.grid(row=2, column=0, sticky="ew", pady=10)
        for i in range(3):
            actions.columnconfigure(i, weight=1)
        ttk.Button(actions, text="＋ App command", command=self.add_app).grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(actions, text="＋ File or folder", command=self.add_path).grid(row=0, column=1, sticky="ew", padx=5)
        ttk.Button(actions, text="＋ Website", command=self.add_url).grid(row=0, column=2, sticky="ew", padx=(5, 0))
        ttk.Button(actions, text="Remove selected", command=self.remove_item).grid(row=1, column=0, sticky="ew", padx=(0, 5), pady=(6, 0))
        ttk.Button(actions, text="Save workspace", command=self.save_data).grid(row=1, column=1, sticky="ew", padx=5, pady=(6, 0))
        ttk.Button(actions, text="Restore desktop ▶", command=self.restore).grid(row=1, column=2, sticky="ew", padx=(5, 0), pady=(6, 0))
        ttk.Button(actions, text="Capture current desktop session", command=self.capture_session).grid(
            row=2, column=0, columnspan=3, sticky="ew", pady=(8, 0)
        )
        ttk.Button(actions, text="Launch all desktops ▶", command=self.restore_all).grid(
            row=3, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )
        ttk.Button(actions, text="Launch workspace ▶", command=self.launch_workspace).grid(
            row=4, column=0, columnspan=3, sticky="ew", pady=(2, 0)
        )
        self.status = tk.StringVar(value="Local only · workspace data stays on this computer")
        ttk.Label(self, textvariable=self.status, relief="sunken", anchor="w", padding=(10, 5)).grid(
            row=2, column=0, columnspan=2, sticky="ew"
        )

    def current_group(self) -> str | None:
        selected = self.workspace_list.curselection()
        return self.workspace_names[selected[0]] if selected else None

    def current_name(self) -> str | None:
        selected = self.desktop_list.curselection()
        return self.desktop_ids[selected[0]] if selected and selected[0] < len(self.desktop_ids) else None

    def refresh_workspaces(self, select: str | None = None, select_desktop: str | None = None) -> None:
        self.workspace_names = sorted(self.workspace_groups, key=str.casefold)
        self.workspace_list.delete(0, tk.END)
        self.workspace_list.selection_clear(0, tk.END)
        for name in self.workspace_names:
            self.workspace_list.insert(tk.END, name)
        if select in self.workspace_names:
            index = self.workspace_names.index(select)
            self.workspace_list.selection_set(index)
        elif self.workspace_names:
            self.workspace_list.selection_set(0)
        if self.workspace_names:
            self.select_workspace(desktop=select_desktop)
        else:
            self.heading.configure(text="Choose or create a workspace")
            self.desktop_list.delete(0, tk.END)
            self.desktop_ids = []
            self.render_items([])

    def select_workspace(self, _event=None, desktop: str | None = None) -> None:
        group = self.current_group()
        children = self.workspace_groups.get(group, []) if group else []
        self.desktop_ids = children[:]
        self.desktop_list.delete(0, tk.END)
        self.desktop_list.selection_clear(0, tk.END)
        for desktop_id in children:
            slot = self.workspace_desktops.get(desktop_id, 0) + 1
            label = self.desktop_labels.get(desktop_id, "Desktop")
            self.desktop_list.insert(tk.END, f"{label}  ·  Desktop {slot}")
        if desktop in children:
            index = children.index(desktop)
        else:
            index = 0 if children else None
        if index is not None:
            self.desktop_list.selection_set(index)
            self.select_desktop()
        else:
            self.heading.configure(text=f"{group} · no desktops" if group else "Choose or create a workspace")
            self.render_items([])

    def select_desktop(self, _event=None) -> None:
        name = self.current_name()
        group = self.current_group()
        desktop = self.workspace_desktops.get(name, 0) + 1 if name else None
        label = self.desktop_labels.get(name, "Desktop") if name else ""
        self.heading.configure(text=f"{group} · {label} · Cinnamon Desktop {desktop}"
                               if name else f"{group} · select or add a desktop" if group
                               else "Choose or create a workspace")
        self.render_items(self.workspaces.get(name, []) if name else [])

    def render_items(self, entries: list[dict[str, str]]) -> None:
        self.items.delete(*self.items.get_children())
        for entry in entries:
            label = entry.get("value", "")
            if entry.get("type") == "session_window":
                label = entry.get("title") or entry.get("wmclass", "Window")
                if entry.get("open_folder"):
                    label += f" · {entry['open_folder']}"
                if entry.get("cwd"):
                    label += f" · {entry['cwd']}"
                elif entry.get("cwd_unknown"):
                    label += " · terminal folder unknown"
            self.items.insert("", tk.END, values=(entry.get("type", "item").replace("_", " ").upper(), label))

    def new_workspace(self) -> None:
        name = simpledialog.askstring("New workspace", "Workspace name:", parent=self)
        if not name or not name.strip():
            return
        name = name.strip()
        if name in self.workspace_groups:
            messagebox.showinfo("Already exists", "Choose a different workspace name.", parent=self)
            return
        self.workspace_groups[name] = []
        self.add_desktop_to_group(name, "Desktop 1")
        self.save_data()
        self.refresh_workspaces(name)

    def add_desktop_to_group(self, group: str, label: str) -> str:
        desktop_id = uuid.uuid4().hex
        self.workspaces[desktop_id] = []
        self.desktop_labels[desktop_id] = label
        used = set(self.workspace_desktops.values())
        slot = 0
        while slot in used:
            slot += 1
        self.workspace_desktops[desktop_id] = slot
        self.workspace_groups.setdefault(group, []).append(desktop_id)
        return desktop_id

    def new_desktop(self) -> None:
        group = self.current_group()
        if not group:
            messagebox.showinfo("Choose a workspace", "Select a workspace first.", parent=self)
            return
        suggested = f"Desktop {len(self.workspace_groups.get(group, [])) + 1}"
        label = simpledialog.askstring("Add desktop", "Desktop name:", initialvalue=suggested, parent=self)
        if not label or not label.strip():
            return
        label = label.strip()
        if any(self.desktop_labels.get(key) == label for key in self.workspace_groups[group]):
            messagebox.showinfo("Already exists", "Choose a different desktop name in this workspace.", parent=self)
            return
        desktop_id = self.add_desktop_to_group(group, label)
        self.save_data()
        self.refresh_workspaces(group, desktop_id)

    def rename_workspace(self) -> None:
        old = self.current_group()
        if not old:
            return
        new = simpledialog.askstring("Rename workspace", "New name:", initialvalue=old, parent=self)
        if not new or not new.strip() or new.strip() == old:
            return
        new = new.strip()
        if new in self.workspace_groups:
            messagebox.showinfo("Already exists", "Choose a different workspace name.", parent=self)
            return
        self.workspace_groups[new] = self.workspace_groups.pop(old)
        self.save_data()
        self.refresh_workspaces(new)

    def rename_desktop(self) -> None:
        desktop_id = self.current_name()
        group = self.current_group()
        if not desktop_id or not group:
            return
        old = self.desktop_labels.get(desktop_id, "Desktop")
        new = simpledialog.askstring("Rename desktop", "New name:", initialvalue=old, parent=self)
        if not new or not new.strip():
            return
        new = new.strip()
        if any(key != desktop_id and self.desktop_labels.get(key) == new
               for key in self.workspace_groups[group]):
            messagebox.showinfo("Already exists", "Choose a different desktop name in this workspace.", parent=self)
            return
        self.desktop_labels[desktop_id] = new
        self.save_data()
        self.refresh_workspaces(group, desktop_id)

    def delete_workspace(self) -> None:
        name = self.current_group()
        if name and messagebox.askyesno("Delete workspace", f"Delete '{name}' and all its saved desktops?", parent=self):
            for desktop_id in self.workspace_groups.pop(name, []):
                self.workspaces.pop(desktop_id, None)
                self.workspace_desktops.pop(desktop_id, None)
                self.desktop_labels.pop(desktop_id, None)
            self.save_data()
            self.refresh_workspaces()

    def delete_desktop(self) -> None:
        group = self.current_group()
        desktop_id = self.current_name()
        label = self.desktop_labels.get(desktop_id, "Desktop") if desktop_id else ""
        if (group and desktop_id and messagebox.askyesno(
                "Remove desktop", f"Remove '{label}' and its saved windows from '{group}'?", parent=self)):
            self.workspace_groups[group].remove(desktop_id)
            self.workspaces.pop(desktop_id, None)
            self.workspace_desktops.pop(desktop_id, None)
            self.desktop_labels.pop(desktop_id, None)
            self.save_data()
            self.refresh_workspaces(group)

    def add_entry(self, kind: str, value: str) -> None:
        name = self.current_name()
        if not name:
            messagebox.showinfo("Choose a workspace", "Create or select a workspace first.", parent=self)
            return
        self.workspaces[name].append({"type": kind, "value": value})
        self.render_items(self.workspaces[name])
        self.save_data()

    def add_app(self) -> None:
        command = simpledialog.askstring(
            "Add app command", "Command and arguments (example: firefox):\nNo shell syntax is run.", parent=self
        )
        if command and command.strip():
            try:
                parts = shlex.split(command)
                if not parts:
                    return
            except ValueError as error:
                messagebox.showerror("Invalid command", str(error), parent=self)
                return
            self.add_entry("app", command.strip())

    def add_path(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(title="Choose a file")
        if not path:
            path = filedialog.askdirectory(title="Choose a folder")
        if path:
            self.add_entry("path", str(Path(path).resolve()))

    def add_url(self) -> None:
        url = simpledialog.askstring("Add website", "Website URL (https://…):", parent=self)
        if url and url.strip():
            parsed = urlparse(url.strip())
            if parsed.scheme not in ("http", "https") or not parsed.netloc:
                messagebox.showerror("Invalid website", "Enter a full http:// or https:// URL.", parent=self)
                return
            self.add_entry("url", url.strip())

    def remove_item(self) -> None:
        name = self.current_name()
        selected = self.items.selection()
        if name and selected:
            index = self.items.index(selected[0])
            del self.workspaces[name][index]
            self.render_items(self.workspaces[name])
            self.save_data()

    @staticmethod
    def desktop_windows() -> list[dict]:
        """Read visible X11 window geometry from wmctrl."""
        try:
            output = subprocess.check_output(
                ["wmctrl", "-l", "-p", "-G", "-x"], text=True, stderr=subprocess.DEVNULL
            )
        except (OSError, subprocess.CalledProcessError):
            return []
        result = []
        for line in output.splitlines():
            fields = line.split(None, 9)
            if len(fields) < 10:
                continue
            try:
                # With -x, wmctrl prints WM_CLASS before the client machine;
                # titles are the remainder (and can contain spaces).
                wid, desktop, pid, x, y, width, height, wmclass, _host, title = fields
                result.append({"wid": wid, "desktop": int(desktop), "pid": int(pid),
                               "x": int(x), "y": int(y), "width": int(width),
                               "height": int(height), "wmclass": wmclass, "title": title})
            except ValueError:
                continue
        return result

    @staticmethod
    def shell_cwd_for_window(window: dict) -> str | None:
        """Use WINDOWID when the terminal exports it; fall back only if unambiguous."""
        shells = []
        try:
            proc_entries = list(Path("/proc").iterdir())
        except OSError:
            return None
        for proc in proc_entries:
            if not proc.name.isdigit():
                continue
            try:
                comm = (proc / "comm").read_text().strip()
                if comm not in {"bash", "zsh", "fish", "sh"}:
                    continue
                env = (proc / "environ").read_bytes().split(b"\0")
                window_id = next((v.split(b"=", 1)[1].decode(errors="ignore") for v in env
                                  if v.startswith(b"WINDOWID=")), "")
                cwd = os.readlink(proc / "cwd")
                shells.append((window_id.lower(), cwd))
            except (OSError, PermissionError):
                continue
        wid = window["wid"].lower().removeprefix("0x")
        matches = [cwd for window_id, cwd in shells if window_id.removeprefix("0x") == wid]
        if len(matches) == 1:
            return matches[0]
        # GNOME Terminal commonly includes the shell's current folder in its
        # title even when it does not export WINDOWID to the shell.
        title = window.get("title", "")
        match = re.search(r":\s*(~(?:/.*)?|/.*)$", title)
        if match:
            candidate = match.group(1).strip()
            for suffix in (" — Terminal", " - Terminal", " — GNOME Terminal", " — bash", " - bash"):
                if candidate.endswith(suffix):
                    candidate = candidate[:-len(suffix)].rstrip()
            if candidate.startswith(("~/", "/")):
                folder = Path(candidate).expanduser()
                if folder.is_dir():
                    return str(folder.resolve())
        if len(shells) == 1:
            return shells[0][1]
        return None

    @staticmethod
    def folder_for_window(window: dict) -> str | None:
        """Find a project folder passed to an editor process for this window."""
        pid = window.get("pid", 0)
        seen = set()
        for _ in range(10):
            if not pid or pid in seen:
                break
            seen.add(pid)
            proc = Path("/proc") / str(pid)
            try:
                argv = [part.decode(errors="ignore") for part in (proc / "cmdline").read_bytes().split(b"\0") if part]
                status = (proc / "status").read_text()
                match = re.search(r"^PPid:\s+(\d+)", status, re.M)
                parent = int(match.group(1)) if match else 0
            except (OSError, ValueError):
                break
            # Editors accept a project path as a positional argument; only
            # preserve arguments that currently resolve to directories.
            for arg in reversed(argv[1:]):
                if arg.startswith("-"):
                    continue
                candidate = Path(arg).expanduser()
                if not candidate.is_absolute():
                    try:
                        candidate = Path(os.readlink(proc / "cwd")) / candidate
                    except OSError:
                        continue
                try:
                    if candidate.is_dir():
                        return str(candidate.resolve())
                except OSError:
                    pass
            pid = parent
        return None

    @staticmethod
    def editor_folder_for_title(title: str) -> str | None:
        """Resolve an editor window's displayed project name from its workspace records."""
        roots = [Path.home() / ".config/Antigravity IDE/User/workspaceStorage",
                 Path.home() / ".config/Antigravity/User/workspaceStorage",
                 Path.home() / ".config/Code/User/workspaceStorage"]
        # Antigravity's Electron process often omits the project argument from
        # /proc after startup, but keeps each window's file URI in workspace.json.
        candidates = []
        for root in roots:
            try:
                records = root.glob("*/workspace.json")
                for record in records:
                    try:
                        uri = json.loads(record.read_text(encoding="utf-8")).get("folder", "")
                        if not uri.startswith("file://"):
                            continue
                        folder = Path(unquote(urlparse(uri).path)).expanduser()
                        if folder.is_dir() and folder.name and re.search(
                                rf"(?<![A-Za-z0-9_-]){re.escape(folder.name)}(?![A-Za-z0-9_-])",
                                title, re.IGNORECASE):
                            candidates.append(folder.resolve())
                    except (OSError, ValueError, json.JSONDecodeError):
                        continue
            except OSError:
                continue
        unique = list(dict.fromkeys(candidates))
        return str(unique[0]) if len(unique) == 1 else None

    @staticmethod
    def editor_launch_for_folder(launch: list[str], folder: str) -> list[str]:
        """Use the desktop entry's real executable when passing editor flags."""
        if len(launch) >= 2 and launch[0] == "gtk-launch":
            roots = [Path.home() / ".local/share/applications", Path("/usr/share/applications")]
            for root in roots:
                desktop_file = root / f"{launch[1]}.desktop"
                try:
                    parser = configparser.ConfigParser(interpolation=None)
                    parser.read(desktop_file, encoding="utf-8")
                    command = [arg for arg in shlex.split(parser["Desktop Entry"].get("Exec", ""))
                               if not arg.startswith("%")]
                    if command:
                        return command + ["--new-window", folder]
                except (OSError, KeyError, configparser.Error, ValueError):
                    continue
        return list(launch) + ["--new-window", folder]

    @staticmethod
    def desktop_launcher(wmclass: str, pid: int | None = None) -> list[str] | None:
        """Find a launcher by WM_CLASS, then by the window process executable."""
        components = {re.sub(r"[^a-z0-9]", "", part.lower()) for part in wmclass.split(".")}
        components.discard("")
        full_class = re.sub(r"[^a-z0-9]", "", wmclass.lower())
        if full_class:
            components.add(full_class)
        if not components:
            return None
        roots = [Path.home() / ".local/share/applications", Path("/usr/share/applications")]
        candidates = []
        process_exe = None
        if pid and pid > 0:
            try:
                process_exe = Path(os.readlink(f"/proc/{pid}/exe")).resolve()
            except OSError:
                pass
        for root in roots:
            try:
                files = sorted(root.glob("*.desktop"))
            except OSError:
                continue
            for file in files:
                parser = configparser.ConfigParser(interpolation=None)
                try:
                    parser.read(file, encoding="utf-8")
                    entry = parser["Desktop Entry"]
                    startup = re.sub(r"[^a-z0-9]", "", entry.get("StartupWMClass", "").lower())
                    name = re.sub(r"[^a-z0-9]", "", entry.get("Name", "").lower())
                    stem = re.sub(r"[^a-z0-9]", "", file.stem.lower())
                    if entry.get("Terminal", "false").lower() == "true" or entry.get("Hidden", "false").lower() == "true":
                        continue
                    # Prefer an explicit StartupWMClass. Name and desktop filename
                    # are only fallbacks, and must match a whole WM_CLASS component.
                    if startup and startup in components:
                        return ["gtk-launch", file.stem]
                    if name in components or stem in components:
                        candidates.append(file.stem)
                    if process_exe:
                        command = shlex.split(entry.get("Exec", ""))
                        command = [part for part in command if not part.startswith("%")]
                        if command:
                            executable = Path(os.path.expanduser(command[0]))
                            if executable.is_absolute():
                                try:
                                    if executable.resolve() == process_exe:
                                        return ["gtk-launch", file.stem]
                                except OSError:
                                    pass
                except (OSError, KeyError, configparser.Error):
                    continue
        if len(candidates) == 1:
            return ["gtk-launch", candidates[0]]
        return None

    def capture_session(self) -> None:
        name = self.current_name()
        if not name:
            messagebox.showinfo("Choose a workspace", "Create or select a workspace first.", parent=self)
            return
        # The user chooses the group explicitly so selection works across
        # Cinnamon desktops and does not silently omit the other apps.
        windows = [w for w in self.desktop_windows()
                   if w["title"].strip() not in {"Desktop", "NOVA · Workspaces"}]
        if not windows:
            messagebox.showerror(
                "Could not capture windows",
                "NOVA could not read windows on the active desktop. Capture works on an X11 session with wmctrl installed.",
                parent=self,
            )
            return
        windows = self.choose_windows(windows)
        if not windows:
            return
        captured = []
        skipped = []
        target_desktop = self.workspace_desktops.get(name, 0)
        for window in windows:
            wmclass = window["wmclass"]
            is_terminal = "terminal" in wmclass.lower() or "gnome-terminal" in wmclass.lower()
            launch = ["gnome-terminal", "--window"] if is_terminal else self.desktop_launcher(wmclass, window["pid"])
            if not launch:
                skipped.append(window["title"] or wmclass)
                continue
            entry = {
                "type": "session_window", "title": window["title"], "wmclass": wmclass,
                "launch": launch, "desktop_id": launch[1] if launch and launch[0] == "gtk-launch" else None,
                "geometry": {k: window[k] for k in ("x", "y", "width", "height")},
                "target_desktop": target_desktop,
                "maximized": self.window_is_maximized(window["wid"]),
            }
            # App launchers open the app itself, but often lose the specific
            # project when two editor windows belong to different folders.
            # Save a per-window directory from the editor's process arguments.
            if any(token in wmclass.lower() for token in ("antigravity", "code", "vscode")):
                folder = (self.folder_for_window(window) or
                          self.editor_folder_for_title(window.get("title", "")))
                if folder:
                    entry["open_folder"] = folder
            if is_terminal:
                cwd = self.shell_cwd_for_window(window)
                if cwd:
                    entry["cwd"] = cwd
                else:
                    entry["cwd_unknown"] = True
            captured.append(entry)
        if not captured:
            messagebox.showwarning("No supported windows", "NOVA could not match any open windows to launchers.", parent=self)
            return
        self.workspaces[name] = captured
        self.save_data()
        self.render_items(captured)
        note = (f"Captured {len(captured)} window(s), including their positions. "
                f"This desktop layout restores to Cinnamon Desktop {target_desktop + 1}.")
        if skipped:
            note += "\n\nCould not identify:\n" + "\n".join(skipped[:8])
        unknown = sum(1 for item in captured if item.get("cwd_unknown"))
        if unknown:
            note += f"\n\nCould not read the folder for {unknown} terminal(s); those will open in the default folder."
        editor_windows = [item for item in captured
                          if any(token in item.get("wmclass", "").lower()
                                 for token in ("antigravity", "code", "vscode"))]
        unknown_projects = sum(1 for item in editor_windows if not item.get("open_folder"))
        if unknown_projects:
            note += (f"\n\nCould not detect a project folder for {unknown_projects} editor window(s). "
                     "Those windows will open without a specific folder.")
        messagebox.showinfo("Session captured", note, parent=self)

    def choose_windows(self, windows: list[dict]) -> list[dict] | None:
        """Let the user explicitly assign open windows to this NOVA workspace."""
        dialog = tk.Toplevel(self)
        dialog.title("Choose windows to capture")
        dialog.geometry("860x440")
        dialog.transient(self)
        dialog.grab_set()
        ttk.Label(
            dialog,
            text="Select only the windows for this NOVA workspace. Use Ctrl-click or Shift-click for multiple windows.",
            wraplength=820,
        ).pack(anchor="w", padx=14, pady=(14, 8))
        body = ttk.Frame(dialog, padding=(14, 0, 14, 8))
        body.pack(fill="both", expand=True)
        body.rowconfigure(0, weight=1)
        body.columnconfigure(0, weight=1)
        listing = tk.Listbox(body, selectmode=tk.EXTENDED, exportselection=False, font=("TkDefaultFont", 10))
        scroll = ttk.Scrollbar(body, orient="vertical", command=listing.yview)
        listing.configure(yscrollcommand=scroll.set)
        listing.grid(row=0, column=0, sticky="nsew")
        scroll.grid(row=0, column=1, sticky="ns")
        for window in windows:
            desktop = "all desktops" if window["desktop"] < 0 else f"Cinnamon Desktop {window['desktop'] + 1}"
            listing.insert(tk.END, f"{window['title']}   ·   {window['wmclass']}   ·   {desktop}")

        chosen: list[dict] | None = None

        def capture_selected() -> None:
            nonlocal chosen
            indices = listing.curselection()
            if not indices:
                messagebox.showinfo("Select windows", "Choose at least one window to capture.", parent=dialog)
                return
            chosen = [windows[index] for index in indices]
            dialog.destroy()

        controls = ttk.Frame(dialog, padding=(14, 0, 14, 14))
        controls.pack(fill="x")
        ttk.Button(controls, text="Cancel", command=dialog.destroy).pack(side="right", padx=(6, 0))
        ttk.Button(controls, text="Capture selected", command=capture_selected).pack(side="right")
        dialog.wait_window()
        return chosen

    @staticmethod
    def window_is_maximized(wid: str) -> bool:
        try:
            state = subprocess.check_output(
                ["xprop", "-id", wid, "_NET_WM_STATE"], text=True, stderr=subprocess.DEVNULL
            )
            return "_NET_WM_STATE_MAXIMIZED_VERT" in state and "_NET_WM_STATE_MAXIMIZED_HORZ" in state
        except (OSError, subprocess.CalledProcessError):
            return False

    def restore(self) -> None:
        name = self.current_name()
        if not name:
            return
        entries = self.workspaces.get(name, [])
        if not entries:
            self.status.set("This desktop is empty. Capture windows or add items first.")
            return
        label = self.desktop_labels.get(name, "Desktop")
        if not messagebox.askyesno("Restore desktop", f"Open {len(entries)} saved item(s) in '{label}'?", parent=self):
            return
        target_desktop = self.workspace_desktops.get(name, 0)
        self.restore_group(label, entries, target_desktop)

    def launch_workspace(self) -> None:
        group = self.current_group()
        if not group:
            self.status.set("Select a workspace to launch.")
            return
        groups = [(self.desktop_labels.get(desktop_id, "Desktop"),
                   self.workspaces.get(desktop_id, []), self.workspace_desktops.get(desktop_id, 0))
                  for desktop_id in self.workspace_groups.get(group, [])
                  if self.workspaces.get(desktop_id, [])]
        if not groups:
            self.status.set(f"'{group}' has no saved desktops to launch.")
            return
        item_count = sum(len(entries) for _, entries, _ in groups)
        if not messagebox.askyesno(
                "Launch workspace",
                f"Open {item_count} saved item(s) across {len(groups)} desktop(s) in '{group}'?",
                parent=self):
            return
        self.launch_desktop_groups(groups, f"workspace '{group}'")

    def restore_all(self) -> None:
        groups = [(self.desktop_labels.get(desktop_id, "Desktop"),
                   self.workspaces.get(desktop_id, []), self.workspace_desktops.get(desktop_id, 0))
                  for desktop_id in self.workspaces if self.workspaces.get(desktop_id, [])]
        if not groups:
            self.status.set("There are no saved workspaces to launch.")
            return
        item_count = sum(len(entries) for _, entries, _ in groups)
        if not messagebox.askyesno(
                "Launch all desktops",
                f"Open {item_count} saved item(s) across {len(groups)} desktop(s) in all workspaces?",
                parent=self):
            return
        self.launch_desktop_groups(groups, "all workspaces")

    def launch_desktop_groups(self, groups: list[tuple[str, list[dict], int]], description: str) -> None:
        groups.sort(key=lambda group: group[2])

        def launch_group(index: int) -> None:
            if index >= len(groups):
                self.status.set(f"Launch requested across {len(groups)} desktops in {description}")
                return
            name, entries, target_desktop = groups[index]
            self.restore_group(name, entries, target_desktop,
                              on_complete=lambda: launch_group(index + 1))

        launch_group(0)

    def restore_group(self, name: str, entries: list[dict], target_desktop: int,
                      on_complete=None) -> None:
        self.ensure_desktop_exists(target_desktop)
        subprocess.run(["wmctrl", "-s", str(target_desktop)], check=False,
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        failures = []
        restore_windows = []
        before_ids = {w["wid"] for w in self.desktop_windows()}
        for entry in entries:
            kind, value = entry.get("type"), entry.get("value", "")
            try:
                if kind == "session_window":
                    # Re-resolve using the current strict matcher. Earlier NOVA
                    # versions could store a wrong desktop launcher here.
                    is_terminal = "terminal" in entry.get("wmclass", "").lower()
                    launch = (entry.get("launch") or
                              (["gnome-terminal", "--window"] if is_terminal else
                               (["gtk-launch", entry["desktop_id"]] if entry.get("desktop_id") else
                                self.desktop_launcher(entry.get("wmclass", "")) or [])))
                    if not launch:
                        failures.append(f"{entry.get('title', entry.get('wmclass', 'Window'))}: no matching app launcher")
                        continue
                    if entry.get("cwd") and is_terminal:
                        launch = list(launch) + [f"--working-directory={entry['cwd']}"]
                    open_folder = (entry.get("open_folder") or
                                   (self.editor_folder_for_title(entry.get("title", ""))
                                    if any(token in entry.get("wmclass", "").lower()
                                           for token in ("antigravity", "code", "vscode")) else None))
                    if open_folder:
                        # VS Code and Antigravity accept --new-window followed
                        # by a folder; invoke their actual executable so GTK
                        # does not treat editor flags as URI arguments.
                        launch = self.editor_launch_for_folder(launch, open_folder)
                    subprocess.Popen(launch, start_new_session=True)
                    restore_windows.append(entry)
                    continue
                if kind == "app":
                    subprocess.Popen(shlex.split(value), start_new_session=True)
                elif kind == "url" and urlparse(value).scheme in ("http", "https"):
                    subprocess.Popen(["xdg-open", value], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                elif kind == "path" and Path(value).exists():
                    subprocess.Popen(["xdg-open", value], start_new_session=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                else:
                    failures.append(value or "invalid saved item")
            except (OSError, ValueError) as error:
                failures.append(f"{value}: {error}")
        if failures:
            messagebox.showwarning("Restore finished with issues", "Could not open:\n\n" + "\n".join(failures), parent=self)
        if restore_windows:
            deadline = time.monotonic() + 20
            self.after(700, lambda: self.apply_saved_geometry(
                restore_windows, before_ids, deadline, target_desktop, on_complete=on_complete))
        elif on_complete:
            on_complete()
        self.status.set(f"Restore requested for '{name}' · apps may take a moment to open")

    @staticmethod
    def ensure_desktop_exists(target_desktop: int) -> None:
        try:
            output = subprocess.check_output(["wmctrl", "-d"], text=True, stderr=subprocess.DEVNULL)
            desktop_ids = [int(line.split()[0]) for line in output.splitlines() if line.split()]
            count = max(desktop_ids, default=-1) + 1
            if count <= target_desktop:
                subprocess.run(["wmctrl", "-n", str(target_desktop + 1)], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except (OSError, subprocess.CalledProcessError, ValueError):
            pass

    def apply_saved_geometry(self, entries: list[dict], before_ids: set[str], deadline: float,
                             target_desktop: int, settled: bool = False, on_complete=None) -> None:
        """Wait for newly launched windows, then lay out only this workspace's windows."""
        windows = self.desktop_windows()
        new_windows = [w for w in windows if w["wid"] not in before_ids]
        counts: dict[str, int] = {}
        for entry in entries:
            cls = entry.get("wmclass", "")
            counts[cls] = counts.get(cls, 0) + 1
        found: dict[str, list[dict]] = {}
        for cls, expected in counts.items():
            matches = [w for w in new_windows if w["wmclass"] == cls]
            found[cls] = matches
            if len(matches) < expected and time.monotonic() < deadline:
                self.after(700, lambda e=entries, b=before_ids, d=deadline, t=target_desktop:
                           self.apply_saved_geometry(e, b, d, t, on_complete=on_complete))
                return
        if not settled and time.monotonic() < deadline:
            self.after(1600, lambda e=entries, b=before_ids, d=deadline, t=target_desktop:
                       self.apply_saved_geometry(e, b, d, t, True, on_complete))
            return

        # Match by exact title first (useful for multiple terminals), then pair
        # remaining same-class windows in the order they were captured.
        assigned: set[str] = set()
        arranged = []
        missed = []
        for entry in entries:
            cls = entry.get("wmclass", "")
            candidates = [w for w in found.get(cls, []) if w["wid"] not in assigned]
            title = entry.get("title", "")
            window = next((w for w in candidates if w["title"] == title), None)
            if window is None and candidates:
                window = candidates[0]
            # If an app reused its existing window, only reuse an old exact-title
            # match. Never move an unrelated window from another workspace.
            if window is None:
                window = next((w for w in windows if w["wid"] in before_ids and
                               w["wid"] not in assigned and w["wmclass"] == cls and
                               w["title"] == title), None)
            if not candidates:
                if window is None:
                    missed.append(entry.get("title", cls))
                    continue
            if window is None:
                missed.append(entry.get("title", cls))
                continue
            assigned.add(window["wid"])
            g = entry.get("geometry", {})
            try:
                if not entry.get("maximized"):
                    subprocess.run(["wmctrl", "-ir", window["wid"], "-b", "remove,maximized_vert,maximized_horz"],
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                geometry = f"0,{g['x']},{g['y']},{g['width']},{g['height']}"
                subprocess.run(["wmctrl", "-ir", window["wid"], "-e", geometry], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                subprocess.run(["wmctrl", "-ir", window["wid"], "-t", str(target_desktop)], check=False,
                               stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                if entry.get("maximized"):
                    subprocess.run(["wmctrl", "-ir", window["wid"], "-b", "add,maximized_vert,maximized_horz"],
                                   check=False, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
                arranged.append(entry.get("title", cls))
            except (OSError, KeyError, ValueError):
                missed.append(entry.get("title", cls))
        self.status.set(f"Restored layout for {len(arranged)} of {len(entries)} windows")
        if missed:
            messagebox.showwarning(
                "Some windows could not be placed",
                "NOVA couldn't match these windows to the saved layout:\n\n" + "\n".join(missed[:10]),
                parent=self,
            )
        if on_complete:
            on_complete()


if __name__ == "__main__":
    NovaApp().mainloop()
