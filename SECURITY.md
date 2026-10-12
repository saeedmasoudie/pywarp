# Security Policy

## Reporting a vulnerability

Report suspected PyWarp vulnerabilities privately through one of these
channels:

- [Open a private GitHub security advisory](https://github.com/saeedmasoudie/pywarp/security/advisories/new)
- Email [info@saeedmasoudie.ir](mailto:info@saeedmasoudie.ir)

Do not open a public issue, discussion, or pull request for an unpatched
vulnerability. Reports are accepted in English or Persian.

Include as much of the following as is safe to share:

- A concise description of the issue and its potential impact
- The affected PyWarp version, operating system, and `warp-cli` version
- Reproduction steps or a minimal proof of concept
- Relevant logs with license keys, account data, device identifiers, IP
  addresses, organization names, and other personal data removed
- Whether the issue is already being exploited or publicly discussed
- Any suggested mitigation or patch

Do not send active credentials, WARP license keys, private signing material, or
unnecessary personal data.

## Supported versions

Security fixes are provided for the latest published PyWarp 1.x release.

| Version | Support |
| --- | --- |
| Latest 2.x release | Actively supported |
| Older 1.x releases | Upgrade required |
| 0.x and earlier | Unsupported |

Always reproduce an issue against the latest release when possible. The current
application version is defined by `CURRENT_VERSION` in
`backend/app_controller.py`.

## Response targets

After receiving a complete report, the project aims to:

1. Acknowledge receipt within 48 hours.
2. Provide an initial assessment within five business days.
3. Develop a patch or practical mitigation within 14 days for confirmed issues
   when the complexity and severity allow.
4. Coordinate a disclosure date with the reporter.

These are targets rather than guarantees. Complex vulnerabilities, upstream
dependencies, and third-party service behavior can require additional time.
Please allow a reasonable remediation period before public disclosure.

## Scope

The following are in scope when they affect PyWarp users:

- WARP command construction, execution, and output parsing
- Privilege boundaries in the confirmed Linux WARP installation flow
- Registration, license, organization, endpoint, and split-tunnel handling
- Local settings, logs, cached Smart Route results, and downloaded installers
- Update metadata, release asset selection, and download handling
- Public IP and geolocation request handling
- Qt/QML interface paths that expose data or bypass a security decision
- Packaging, GitHub Actions, release generation, and published artifacts

Integration vulnerabilities caused by how PyWarp invokes or interprets an
upstream service are in scope even when the underlying upstream product is not.

## Out of scope

Unless PyWarp introduces or materially worsens the issue, this policy does not
cover:

- Vulnerabilities in Cloudflare WARP, Cloudflare infrastructure, GitHub, Qt,
  Python, Requests, operating systems, or other third-party dependencies
- Service availability, network blocking, censorship, or ISP behavior
- Findings that require an already fully compromised local administrator
- Social engineering, phishing, or physical attacks
- Automated scanner output without a reproducible security impact
- Feature requests, ordinary bugs, or support questions

Report third-party vulnerabilities to the affected vendor. If you are unsure
whether PyWarp is responsible, send the report privately and explain the
suspected integration impact.

## Safe-harbor expectations

Good-faith research should:

- Use accounts, devices, and networks you own or are authorized to test
- Avoid accessing, modifying, retaining, or disclosing other people's data
- Avoid service disruption, destructive testing, persistence, and lateral
  movement
- Stop testing and report promptly if sensitive data is encountered
- Follow applicable laws and third-party terms

The project will not pursue action against good-faith research that follows
these expectations. This statement cannot authorize testing against third-party
services or waive their policies.

## Windows Defender and SmartScreen

PyWarp release binaries may be unsigned. Windows can warn about unsigned,
newly published, or low-reputation networking applications. This warning is
not proof of malware, but users should verify the download before choosing to
run it:

1. Download only from the official
   [PyWarp Releases page](https://github.com/saeedmasoudie/pywarp/releases).
2. Compare the file's SHA-256 digest with the checksum in its release notes.
3. Do not bypass a warning if the source or checksum cannot be verified.
4. Submit unexpected detections or behavior through the private reporting
   channels above.

## Disclosure and advisories

For a confirmed vulnerability, the project may:

- Publish a GitHub Security Advisory and request a CVE when appropriate
- Release corrected packages and checksums
- Document the fix in `CHANGELOG.md` and the release notes
- Credit the reporter with permission, or keep the report anonymous

Sensitive report details are shared only with people needed to investigate and
remediate the issue.
