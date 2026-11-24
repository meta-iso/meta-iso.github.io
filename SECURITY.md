# Security Policy

## ISO Integrity & SHA-256 Verification

**METAISO.net** prioritizes user safety by indexing only verified operating system images checked against official **SHA-256** cryptographic hashes.

### Verifying Your Download

Before flashing an ISO image to a USB drive or running it in a virtual machine, verify its checksum using our CLI tool or standard system utilities:

```bash
# Using METAISO CLI
./metaiso --verify path/to/image.iso <expected_sha256_hash>

# Using Linux sha256sum
sha256sum path/to/image.iso
```

## Reporting a Broken Link or Compromised Mirror

If you discover a dead download link, an outdated checksum, or a suspicious mirror URL:

1. **Do not** open a public issue if it involves an active security threat.
2. Report it immediately through the repository's **Security Advisories** tab or contact the maintainers directly.
3. All reports are reviewed within **24–72 hours**.
