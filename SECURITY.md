<div style="border:2px solid #d73a49; border-radius:10px; padding:16px; margin-bottom:24px; background:#fff5f5;">
  <h2 style="margin-top:0; color:#b31d28;">⚠️ Windows Defender & SmartScreen Notice</h2>

  <p><strong>Important for Windows users:</strong></p>

  <p>
    When downloading or running <strong>PyWarp</strong> on Windows, you may see security warnings such as:
    <br>
    <em>“Windows protected your PC”</em> or <em>“This app might put your PC at risk”</em>.
  </p>

  <ul>
    <li>The Windows binary is <strong>not code-signed</strong></li>
    <li>PyWarp is a <strong>networking / VPN-related open-source tool</strong></li>
    <li>Microsoft flags <strong>new or low-reputation executables</strong> by default</li>
  </ul>

  <p><strong>This does NOT mean PyWarp is malicious.</strong></p>

  <p>
    👉 To run the app: click <strong>More info</strong> → <strong>Run anyway</strong> (first run only).
  </p>

  <hr style="margin:16px 0;">

  <div dir="rtl" style="text-align:right;">
    <p><strong>اطلاعیه مهم برای کاربران ویندوز:</strong></p>

<p>
  هنگام دانلود یا اجرای <strong>PyWarp</strong> ممکن است با پیام‌های امنیتی زیر مواجه شوید:
  <br>
  <em>«Windows از رایانه شما محافظت کرد»</em> یا <em>«این برنامه ممکن است خطرناک باشد»</em>
</p>

<ul>
  <li>فایل اجرایی ویندوز <strong>امضای دیجیتال ندارد</strong></li>
  <li>PyWarp یک ابزار <strong>متن‌باز با عملکرد شبکه / VPN</strong> است</li>
  <li>مایکروسافت فایل‌های جدید یا کم‌اعتبار را به‌صورت پیش‌فرض مسدود می‌کند</li>
</ul>

<p><strong>این هشدار به‌معنای مخرب بودن PyWarp نیست.</strong></p>

<p>
  👉 برای اجرا: روی <strong>More info</strong> کلیک کرده و <strong>Run anyway</strong> را انتخاب کنید (فقط بار اول).
</p>

  </div>
</div>

# Security Policy

## 📬 Reporting a Vulnerability

If you discover a security issue in PyWarp, please report it **privately** to:

* Email: [info@saeedmasoudie.ir](mailto:info@saeedmasoudie.ir)
* GitHub: [Open a private security advisory](https://github.com/saeedmasoudie/pywarp/security/advisories)

Please **do not** disclose vulnerabilities publicly until we’ve had a chance to investigate and release a fix.

---

## 🔐 Supported Versions

| Version | Status              | Security Fixes |
| ------- | ------------------- | -------------- |
| v1.x    | Actively maintained | ✅ Yes          |
| v0.x    | Legacy support      | ❌ No           |

We recommend using the latest release for full security coverage.

---

## 🧭 Disclosure Policy

We follow **responsible disclosure** practices. Upon receiving a report, we aim to:

* Acknowledge within **48 hours**
* Investigate and reproduce within **5 business days**
* Release a patch or mitigation within **14 days**, if applicable

---

## 🌐 Localization

Security reports are accepted in **English** or **Persian (فارسی)**. Please include:

* A clear description of the issue
* Steps to reproduce (if possible)
* Potential impact

---

## 🛡️ Scope

This policy covers:

* PyWarp’s proxy engine and networking logic
* Artifact packaging and release workflows
* CI/CD scripts and automation tools

It does **not** cover third-party dependencies unless explicitly bundled.

---

## 📢 Public Advisories

If a vulnerability is confirmed and patched, we will:

* Publish a GitHub advisory
* Include details in the changelog (`CHANGELOG.md`)
* Notify users via release notes
