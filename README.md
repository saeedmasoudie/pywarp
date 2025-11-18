# **Pywarp**

🚀 **Pywarp** is a powerful replacement for the official Cloudflare WARP app, offering more advanced options in an intuitive and feature-rich user interface. With Pywarp, you can configure DNS modes, manage WARP protocols (masque and WireGuard), and set custom endpoints—all designed and all of the current offical app capabalaties to make WARP functionality accessible and convenient.

---

## Features
- 🌟 **Enhanced Protocol Support**: Includes UI for changing protocols.
- 🌐 **DNS Mode Management**: Easily toggle between "off," "block adult-content" and "block malware" DNS filters.
- 🔗 **Custom Endpoint Configuration**: Set, save, and reset connection endpoints directly in the app.
- 🛠 **Intuitive UI**: No more command lines! All WARP commands are built into a sleek, user-friendly interface.
- 🎨 **Dynamic Theme Compatibility**: Automatically adapts to your system's dark/light mode.
- 🗂 **Resource Integration**: Bundles settings and assets directly into the app with Qt Resource System for portability.
- ⚡ **Exclude IP/Domain**: Manage exclusions directly from the Advanced Settings.
- 🖥️ **Per-App Split Tunneling**: Configure split tunnel rules per application on Windows, macOS, and Linux.
- 🚀 **Smart MASQUE Protocol**: Automatically selects the fastest working HTTP protocol for improved connection speed and reliability.

---

## 📥 Download

You can always grab the latest version of the app from the **[GitHub Releases](../../releases/latest)** page.  
Choose the package that matches your operating system:

[![Download for Windows](https://img.shields.io/badge/Download-Windows-blue?logo=windows)](../../releases/latest)
[![Download for macOS](https://img.shields.io/badge/Download-macOS-lightgrey?logo=apple)](../../releases/latest)
[![Download for Linux](https://img.shields.io/badge/Download-Linux-green?logo=linux)](../../releases/latest)

---

## 🚧 Roadmap

**Completed:**
- ✅ Major Fixes
- ✅ Rework on Theme
- ✅ Multi Language support
- ✅ Change Settings Section
- ✅ Split Tunnel Future

**Planned / In Progress:**
- 🌟 MTM (Masque to Masque)
- 🌐 Support Russian and Chinese language

---

## 💖 Support the Project

If you enjoy my work and want to support future development, you can donate here:

👉 [Donate via my official website](https://www.saeedmasoudie.ir/donate.html)

Every contribution helps keep the project alive. Thank you!

---
## **Screenshots**
![PyWarp Dark Mode](screenshots/Screenshot-1.jpg)
![PyWarp Normal](screenshots/Screenshot-2.jpg)
---

## 🛠 Build from Source

If you prefer to build the app yourself instead of downloading the prebuilt release:

### Prerequisites
- Python 3.x installed on your machine
- Install required libraries:
  ```bash
  pip install -r requirements.txt

### Build
- Clone the repository
- Run the build scripts provided in the repo
- Generated binaries will be available in the dist/ folder

## 🚀 Usage (Recommended)

For most users, downloading the prebuilt app is easier:

- Download the app from [Releases](../../releases/latest)
- Make sure you have the official version of WARP installed (open the app for links)
- Close the official WARP app (you don’t need it anymore once this is running)
- Enjoy 🎉

## **Contributing**
We welcome contributions from the community! To contribute:
1- Fork this repository.
2- Create your feature branch:
```bash
git checkout -b feature/AmazingFeature
```
3- Commit your changes:
```bash
git commit -m "Add some AmazingFeature"
```
4- Push to the branch:
```bash
git push origin feature/AmazingFeature
```
5- Open a pull request.

---

## **License**
This project is licensed under the GNU GPL v3, ensuring all modifications and derivatives remain open-source.

---

## 🔐 Security

If you discover a security vulnerability in PyWarp, please follow our [security policy](./SECURITY.md) for responsible disclosure.

We accept reports in **English** or **Persian (فارسی)** and aim to respond within 48 hours.

---

## **Acknowledgments**
- Inspired by Cloudflare WARP, with extended features that simplify advanced commands.
- Built with PySide6 for a seamless user experience.
