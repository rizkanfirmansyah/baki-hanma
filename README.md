# BAKI HANMA

**BAKI HANMA** stands for **Bash Kit Hamachi Network Manager**.
It is a native Linux desktop application built with **Python 3.12** and **PyQt6** for managing **LogMeIn Hamachi** from a modern GUI while still using the system-installed `hamachi` CLI underneath.

The project is designed for users who want a faster operational workflow than the default terminal-only Hamachi experience on Linux: inspect networks, monitor members, run commands, watch logs, and launch SSH sessions from one desktop interface.

## Project Goals

- Provide a native Linux desktop GUI for Hamachi administration
- Reduce repeated terminal work for common Hamachi actions
- Make peer and network monitoring easier to read in daily use
- Improve operational visibility with logs, traffic trends, and status indicators
- Keep the architecture modular and maintainable without switching to Electron or a browser-based stack

## Target Environment

- Ubuntu 22.04
- Ubuntu 24.04
- Debian 12
- Python 3.12
- PyQt6
- LogMeIn Hamachi CLI installed and available in `PATH`
- A running Hamachi daemon with proper user permission to access it

## Main Features

### Dashboard

- Hamachi status
- Login status
- Client ID
- Nickname
- Hamachi IPv4
- Hamachi IPv6
- LogMeIn account
- Attach status
- Online state

### Network and Member Monitoring

- Network list with quick selection
- Dominant member table for daily monitoring
- Member columns focused on operational use:
  - Nickname
  - IPv4
  - IPv6
  - Status
  - Direct / Relay
  - Endpoint
  - Client ID
  - Connection Type
- Live member search by:
  - nickname
  - IPv4
  - IPv6
  - endpoint
  - status
  - direct / relay state
  - client ID
  - connection type

### Command and Logs

- Live log panel for every executed action
- Embedded Hamachi command console
- All command execution recorded in the UI log
- Better workflow for `refresh -> inspect -> execute -> verify`

### Member Actions

Right-click member actions include:

- Ping Member
- Copy Hamachi IP
- Copy Client ID
- SSH to Host

### Traffic Monitoring

- Upload trend monitoring
- Download trend monitoring
- Numeric transfer summary
- Trend state visibility
- Interface selection support for traffic source switching

### Automation and QoL

- Auto refresh every 5 seconds
- System tray support
- Tray notifications for status changes
- Export member list to CSV and Excel
- Dark theme optimized for monitoring workflows
- MTU tuning helper for safer SSH/web traffic over Hamachi
- Configurable MTU from the `More` menu

## Why This Project Exists

Hamachi on Linux is functional, but the default workflow is still heavily terminal-driven. For administrators who frequently inspect peers, verify routes, reconnect clients, or launch SSH sessions, that approach is slower than it should be.

BAKI HANMA exists to solve that gap by wrapping Hamachi operations in a focused native desktop dashboard without replacing the original CLI behavior.

## Architecture Overview

```text
hamachiApps/
├── main.py
├── build.sh
├── requirements.txt
├── README.md
├── scripts/
├── systemd/
└── hamachi_manager/
    ├── app.py
    ├── models.py
    ├── ui/
    │   └── main_window.py
    ├── widgets/
    │   ├── command_console.py
    │   ├── log_panel.py
    │   ├── status_indicator.py
    │   └── traffic_monitor.py
    ├── services/
    │   ├── hamachi_service.py
    │   ├── logger.py
    │   └── parser.py
    ├── styles/
    │   └── dark_theme.py
    ├── icons/
    └── resources/
```

## Installation

### 1. Install system packages

```bash
sudo apt update
sudo apt install -y python3 python3-venv python3-pip
```

If Hamachi is not installed yet, install it first and confirm that this works:

```bash
hamachi --help
```

### 2. Create the virtual environment

```bash
cd /home/rayyan/app/hamachiApps
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
```

### 3. Run the application

```bash
python3 main.py
```

### 4. Optional desktop launcher

```bash
mkdir -p ~/.local/share/applications
cp "/home/rayyan/app/hamachiApps/BAKI HANMA.desktop" ~/.local/share/applications/
chmod +x ~/.local/share/applications/"BAKI HANMA.desktop"
```

## Build Helper

You can also use the included helper script:

```bash
chmod +x build.sh
./build.sh
```

## Usage

1. Start the Hamachi daemon and make sure your user can access it.
2. Open `BAKI HANMA`.
3. Use `Login`, `Refresh`, `Logout`, and `More` from the top toolbar.
4. Select a network from the left panel.
5. Review members in the main table.
6. Use the search bar to filter members quickly.
7. Watch live logs in the bottom panel.
8. Run additional `hamachi` commands from the embedded command console.
9. Use right-click actions on members for ping, copy, and SSH workflows.

## Embedded Console Examples

The embedded console accepts Hamachi commands such as:

```bash
hamachi list
hamachi login
hamachi logout
hamachi attach user@example.com
hamachi join 123-456-789 secret
hamachi leave 123-456-789
hamachi peer 123-456-789
```

## Strengths

- Native desktop application, no browser or Electron dependency
- Practical monitoring-first layout
- Better visibility for peer IPs and connection state
- Centralized logs and command execution
- Faster SSH and peer inspection workflow
- Useful MTU tuning support for Hamachi-related TCP instability
- Modular service/UI separation for future development

## Current Limitations

- The application still depends on the external `hamachi` CLI and daemon behavior
- Some advanced Hamachi actions still require daemon permissions or authentication prompts
- MTU tuning may require elevated privileges through `pkexec` or systemd helper installation
- Traffic monitoring is interface-based, not protocol-deep traffic analysis
- Output parsing depends on Hamachi CLI output format stability
- SSH launch depends on an available terminal emulator on the local desktop

## Improvement Opportunities

These are reasonable next improvements for future versions:

- Persist application preferences such as MTU, window state, and selected traffic interface
- Add advanced member search syntax such as `status:online`, `ip:25.`, or `id:220-`
- Add network detail cards with richer health summaries
- Add configurable notifications and sound alerts
- Improve SSH launcher with saved usernames per member or per network
- Add ping latency history and packet-loss mini charts
- Add daemon diagnostics panel for faster troubleshooting
- Add packaging for `.deb` or AppImage distribution
- Add automated tests for parsing and service workflows
- Improve privilege handling for MTU tuning in hardened desktop environments

## Troubleshooting

### Permission denied when talking to Hamachi

Hamachi on Linux often requires explicit daemon ACL permission.

Edit:

```text
/var/lib/logmein-hamachi/h2-engine-override.cfg
```

Add your login user:

```text
Ipc.User your-username
```

Then restart Hamachi:

```bash
sudo systemctl restart logmein-hamachi
```

### Hamachi daemon not running

```bash
sudo systemctl restart logmein-hamachi
```

If your system still uses the SysV wrapper, this may also work:

```bash
sudo /etc/init.d/logmein-hamachi restart
```

### Manual approval required

The network owner must approve your client. Use the LogMeIn web panel or ask the owner to approve your node.

### Invalid password

The supplied network password is wrong. Retry the join flow with the correct password.

### Not attached account

Attach the client first:

```bash
hamachi attach email@example.com
```

or use the `Attach` action from the UI.

### Automatic MTU tuning before Login/Join

The app attempts to apply safer Hamachi tuning automatically before `login`, `join`, and `reconnect`.

Current safe profile:

```text
MTU 1250
TCP MSS clamp-to-pmtu
```

You can also change the preferred MTU directly from the `More -> Set MTU` action.

If authentication is requested, allow `pkexec` so the app can apply the network change from the GUI.

### Permanent Hamachi systemd + MTU fix

The project includes helper files for a more reliable Hamachi daemon setup and persistent network tuning:

```text
scripts/hamachid-systemd-wrapper.sh
scripts/hamachi-network-tune.sh
scripts/install_hamachi_systemd_fix.sh
systemd/logmein-hamachi.service
systemd/hamachi-network-tune.service
```

Install them with:

```bash
cd /home/rayyan/app/hamachiApps
sudo ./scripts/install_hamachi_systemd_fix.sh
```

### SSH launcher does not open

The app tries these terminal emulators in order:

- `x-terminal-emulator`
- `gnome-terminal`
- `konsole`
- `xfce4-terminal`
- `xterm`

Install at least one of them.

### `python: command not found` or `externally-managed-environment`

Use `python3` to create the virtual environment on Ubuntu and Debian:

```bash
python3 -m venv venv
source venv/bin/activate
python -m pip install --upgrade pip
python -m pip install -r requirements.txt
python3 main.py
```

### Qt xcb platform plugin error

If you see:

```text
Could not load the Qt platform plugin "xcb"
```

Install the required runtime packages:

```bash
sudo apt update
sudo apt install -y   libxcb-cursor0   libxkbcommon-x11-0   libxcb-icccm4   libxcb-image0   libxcb-keysyms1   libxcb-randr0   libxcb-render-util0   libxcb-shape0   libxcb-xfixes0   libxcb-xinerama0   libgl1   libegl1
```

## Screenshot Placeholder

```text
[ Dashboard Screenshot Placeholder ]
[ Members Table Screenshot Placeholder ]
[ Logs and Command Console Placeholder ]
```

## License

This project currently has no explicit open-source license file in the repository. Add one before public distribution if licensing clarity is required.
