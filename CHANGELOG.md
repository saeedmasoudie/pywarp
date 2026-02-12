# Changelog

All notable changes to this project will be documented in this file.

## v1.3.4 - 2026-02-13
### Changes
- Fixed incorrect warning shown in WireGuard proxy mode
- Optimized protocol detection by using saved data instead of running a command each time
- Added connection test support for WARP-based protocols
- Introduced a live DNS logs window
- Resolved MASQUE-related issue in the status handler
- Added a new example to the connection states section
- Updated application size for the latest release
- Fixed styling issues in the new window and drawer table
- Updated Persian translation
- Added Windows installer
- Added macOS and Linux installers

## v1.3.3 - 2025-12-02
### Changes
- Optimized IP fetcher function for faster and more reliable lookups
- Smart MASQUE now checks all protocols on startup (previously it restored the last-checked protocol)
- Improved performance of tree list rendering in Exclude Apps
- Updated Auto MASQUE: when Proxy Mode is active, HTTP/2 is excluded due to compatibility issues
- Replace the existing update checker with a more user‑friendly version, as the previous one was not functioning properly
- fix a few problems on smart masque
- update persian language

## v1.3.2 - 2025-11-29
### Changes
- Resolved issue where proxy address was not displayed in the status label
- Replaced legacy, resource‑heavy IP fetcher class with a lightweight function
- Enhanced IP fetcher to respect proxy mode, ensuring the correct IP is shown when connected through a proxy
- Update persian translate

## v1.3.1 - 2025-11-27
### Changes
- Add automatic protocol selection in MASQUE options
- Add warning when using proxy mode with MASQUE over HTTP/2
- Fix HTTP/2 stats inaccuracies for packet loss and ping
- Improve smart MASQUE handling and fallback behavior
- Remove dead code and perform general cleanup
- Simplify WARP status messages for clearer, user-friendly wording
- update persian language

## v1.3.0 - 2025-11-24
### Changes
- Improved input handling in ExclusionManager
- Streamlined addition method with intelligent IP/domain detection
- Enhanced Persian language support
- General stability and minor bug fixes

## v1.2.9 - 2025-11-18
### Changes
- Added Smart MASQUE feature to automatically check all HTTP protocols and connect to the working one
- Reworked and optimized power button functionality for improved performance
- Updated GitHub release content with new information
- Added Intel and AMD64 .pkg support for macOS in the download table
- Performed minor fixes and code cleanup

## v1.2.8 - 2025-11-11
### Highlights
- New status handler for faster and lighter performance.
- Unified UI for connection status and proxy label.
- Added "Exclude App" feature across Windows, Linux, and macOS.

### Changes
- Replaced legacy status handler with a more efficient and lightweight implementation.
- Switched all data fetching to JSON format for consistency and performance.
- Updated and optimized statistics classes for better responsiveness.
- Introduced "Exclude App" functionality with cross-platform support.
- Added additional IP ranges and domains for popular apps using the "Exclude App" feature.
- Refactored exclude IP/domain logic for improved accuracy and maintainability.
- Reworked power button behavior to rely on the new status data.
- Refreshed tutorial content for clarity and completeness.
- Merged connection status and proxy label into a single, streamlined UI component.
- Updated Persian translation for improved localization quality.

## v1.2.7 - 2025-09-24
### Highlights
- New auto-restart feature when changing language settings.
- Improved shutdown flow: tray exit and restart now always force quit instead of hiding.
- Better reliability for portable `warp-cli` execution.

### Changes
- Added auto-restart support after language change for a smoother user experience.
- Fixed tray menu "Exit" option to always quit the app instead of hiding it.
- Improved close event logic to bypass "hide/close" preference during restart or forced exit.
- Corrected execution of portable `warp-cli` commands to ensure proper behavior across platforms.
- Proxy status is now displayed immediately at startup for better clarity.
- Updated macOS universal build workflow for improved compatibility.
- Introduced SECURITY.md file with clear instructions for reporting vulnerabilities.
- General stability and performance improvements across background workers and shutdown flow.

## v1.2.6 - 2025-09-07
### Changes
- fixed update checker crash problem on v1.2.5

## v1.2.5 - 2025-09-07
### Changes
- Fixed font rendering issue in Advanced Settings when switching to certain Persian fonts.
- Updated Persian language translations for improved clarity and consistency.
- Removed asyncio usage from handler classes to improve stability.
- Added a loading screen to accelerate app startup.
- Replaced raw threads with structured objects in key classes.
- Switched from threading.Thread to FunctionWorker to prevent runtime crashes.
- Enhanced power button logic with additional safety checks.
- Optimized set_mode function for faster execution and improved reliability.
- Deferred protocol updates using a timer instead of triggering them immediately on launch.
- Added delayed initialization for objects and threads to reduce startup load.
- Unified close() and disconnect_on_close() logic into a single, robust shutdown function.
- Implemented startup safety check for users running Portable Warp.
- Added "Remember this option" checkbox on close window for user preference retention.
- Improved IP fetcher class for more accurate and consistent results.
- Removed incorrect lock on power button during connection state, allowing users to disconnect while connecting.

## v1.2.4 - 2025-09-03
### Changes
- show correct ip when its on proxy mode
- make button style better
- avoid some crashes on button states
- update and upgrade the macos and linux builds

## v1.2.3 - 2025-08-28
### Changes
- add masque-options to change protocl settings
- removed unused functions
- fixed tos problem on linux and mac
- add support for linux 22.04

## v1.2.2 - 2025-08-24
### Added
### UI & Theme Improvements
- Centralized all theme-related functions for cleaner architecture
- Fully redesigned application theme with modern visuals and improved accessibility
- Added font customization feature with live preview and fallback support

### UX Enhancements
- Introduced "Silent Mode" toggle in the main menu for distraction-free usage
- Reworked tray icon and menu layout for better clarity and responsiveness

### Language & Localization
- Implemented full multi-language support using `.qm` files and embedded resources
- Added Persian (`fa`) language support with proper RTL layout handling
- Language switching now supports restart logic for full UI refresh

### System & Backend Updates
- Integrated structured logging system with file output and log levels
- Updated WARP integration for improved stability and compatibility
