# Contributing to METAISO.net

Thank you for your interest in contributing to **METAISO.net**! We welcome community submissions for new operating system releases, checksum updates, and improvements to our web archive or C CLI tool.

## How to Add a New Operating System

You can submit a new ISO entry in two ways:

1. **Via Web Form:** Use the **Add System** form directly on [meta-iso.github.io](https://github.io).
2. **Via Pull Request:**
   * Fork this repository.
   * Add the OS entry in `index.html` under the appropriate OS family section.
   * Include the exact architecture (`x86-64-bit`, `ARM64`, or `32-bit`), accurate file size, and an official download source.
   * Open a Pull Request describing the added release.

## Submission Guidelines

* **Official Sources Only:** All `.iso` links must point to official vendor mirrors or verified open-source repositories.
* **No Modified/Cracked Images:** Unofficial repacks or modified proprietary OS images will be rejected immediately.
* **SHA-256 Verification:** Every release is verified against upstream SHA-256 checksums before merging.
