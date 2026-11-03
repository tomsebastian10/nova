# NOVA v0.2

A local Linux desktop session helper. NOVA can capture supported open windows, remember their X11 positions and sizes, and launch them again later. It also supports manually saved app commands, files/folders, and websites.

## Run

Open a terminal in this folder and run:

```sh
python3 nova.py
```

Python 3 and Tkinter are required. Session capture and window placement require an X11 desktop and `wmctrl`. NOVA does not install itself, add an autostart entry, replace Cinnamon, or change system configuration.

## Capture and restore a session

1. Create a named NOVA workspace for a project or activity. Each workspace can contain several named desktop layouts, and each layout is assigned its own Cinnamon desktop.
2. Select a desktop layout, arrange its windows and terminal folders, then click **Capture current desktop session**. In the picker, select only the windows for that layout. Repeat for each desktop layout in the workspace.
3. Click **Launch workspace** once to restore all saved desktops in the selected workspace. **Restore desktop** opens only the selected layout. **Launch all desktops** remains available to restore every saved layout across all workspaces.
4. NOVA creates the needed Cinnamon desktops if required, switches between them while restoring, and lays out each saved group. Existing NOVA desktop sessions are kept and grouped under **Workspace 1** when the updated app first loads; you can rename it or create additional workspaces.

NOVA uses installed `.desktop` launchers to identify apps, matching the X11 app class first and the window process executable as a fallback. Unidentified windows are skipped to avoid opening the wrong app. Some apps reuse an existing window, open with a different title, or do not allow multiple instances; those behaviors can prevent an exact match. Minimized state and unsaved application contents are not captured. If you used an earlier NOVA build, capture the session again after updating because earlier saved app classes may be incorrect.

NOVA identifies apps from their X11 app class and falls back to the window process executable. It launches the saved command for each selected window, waits for the windows to appear, then restores position, size, virtual desktop, and maximized state where supported. For Antigravity and VS Code windows, NOVA also tries to read the project folder from the app's process arguments and saves it per window, so separate windows can reopen separate projects. GNOME Terminal folders are saved from the shell's exported window ID or, when that is unavailable, from the folder shown in the terminal title. If NOVA cannot identify an app or folder, it marks that in the capture summary; unidentified apps will not be restored, and a terminal with an unknown folder opens in its default folder. Check the capture summary before relying on it.

NOVA stores workspace data in `~/.local/share/nova/workspaces.json`. Removing that file deletes only NOVA's saved lists. NOVA does not fix overheating or suspend behavior and does not change thermal controls, power settings, firmware, kernel, or boot configuration.
