# Changelog

All notable changes to this project will be documented in this file.

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
