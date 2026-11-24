<div align="center">

# 💿 METAISO.net

**Operating systems archive with the newest versions to download.**

[![Website](https://shields.io)](https://github.io)
[![License](https://shields.io)](LICENSE)
[![OS Families](https://shields.io)](#-supported-operating-systems)
[![Releases](https://shields.io)](#-supported-operating-systems)
[![Checksums](https://shields.io)](#-features)

---

*A lightweight, retro-styled operating system archive providing direct access to verified ISO images across Linux, BSD, Windows, macOS, and Unix ecosystems.*

[Live Website](https://github.io) • [Features](#-features) • [OS Archive](#-supported-operating-systems) • [Add a System](#-contributing--adding-a-system)

</div>

## ✨ Features

* **🚀 Extensive Archive:** Over **100 releases** categorized into **20 distinct OS families** — from modern Linux distributions to legacy Windows builds.
* **🔐 SHA-256 Verified:** Every listed ISO release is reviewed and checked with **SHA-256** checksums to ensure file integrity and safety.
* **🏗️ Multi-Architecture Support:** Direct downloads separated by architecture (`x86-64-bit`, `ARM64`, and `32-bit`) with clear file size indicators.
* **⚡ Instant Search:** Built-in client-side filtering to locate any operating system or specific release in milliseconds.
* **🖥️ Classic Aesthetic:** Designed with a clean, distraction-free, old-school web layout for maximum speed and accessibility.
* **🚫 Zero Ads:** 100% free and ad-free non-profit project.

---

## 🗂️ Supported Operating Systems

The archive currently tracks **20 OS families**:

| Category | Operating Systems Included |
| :--- | :--- |
| **Linux (Mainstream & Desktop)** | Ubuntu (20–26 LTS / XFCE), Debian (10–13), Fedora (42, 44), Zorin OS, Pop!_OS, Manjaro, Nobara |
| **Linux (Advanced & Minimal)** | Arch Linux, Gentoo, Alpine Linux (Tiny / Static), Kali OS (2026.1) |
| **Enterprise & Server** | Red Hat Enterprise Linux (RHEL 8/9), Rocky Linux, CentOS Stream, Oracle Linux, SUSE (Server / Mate) |
| **BSD & Unix** | FreeBSD (13.1, 14.1), OpenBSD 10, Solaris (10, 11) |
| **Windows** | Windows 11, 10, 7, XP, ME, 2000, 98, 95 |
| **macOS** | Sequoia (15), Sonoma (14), Ventura (13), Monterey (12), Big Sur (11) |
| **Other & Embedded** | Raspberry Pi OS, ReactOS, MacroMag OS, Talis OS |

---

## 🛠️ Tech Stack & Deployment

This project is built as a fast, zero-dependency static web application and deployed automatically via **GitHub Actions** to **GitHub Pages**.

```text
meta-iso.github.io/
├── .github/
│   └── workflows/
│       └── static.yml    # Automated GitHub Pages deployment workflow
├── index.html            # Main application & OS database
├── LICENSE               # Apache-2.0 License
└── README.md             # Project documentation
```

---

## ➕ Contributing & Adding a System

Missing a distribution or a specific version? You can submit a new ISO entry directly through the **Add System** form on the [METAISO.net website](https://github.io):

1. Navigate to the **Add System** section on the page.
2. Provide the **OS Name**, **OS Family** (`Linux`, `Unix`, `BSD`, `QEMU`, `Other`), **Version**, **Owner/Company**, and a valid **`.iso` File URL**.
3. Submit the form — submissions are manually reviewed and verified within ~72 hours.

---

## 📄 License & Copyright

* **Repository License:** Distributed under the **Apache-2.0 License**. See [`LICENSE`](LICENSE) for more information.
* **Site Copyright:** © 2026 **Meta ISO Group Collective (Jim Seal)**.
* *All operating system trademarks, logos, and ISO copyrights belong to their respective owners.*
