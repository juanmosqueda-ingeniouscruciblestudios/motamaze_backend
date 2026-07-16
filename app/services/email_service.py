import asyncio
import logging

logger = logging.getLogger(__name__)


def _send_sync(api_key: str, from_email: str, to_email: str, subject: str, html: str) -> None:
    import sendgrid
    from sendgrid.helpers.mail import Mail
    sg = sendgrid.SendGridAPIClient(api_key=api_key)
    message = Mail(
        from_email=from_email,
        to_emails=to_email,
        subject=subject,
        html_content=html,
    )
    response = sg.send(message)
    if response.status_code >= 400:
        raise RuntimeError(f"SendGrid returned {response.status_code}: {response.body}")


async def send_parental_consent_email(
    to_email: str,
    child_name: str,
    consent_url: str,
    api_key: str,
    from_email: str,
    company_website_url: str,
    privacy_email: str,
) -> None:
    """Sends the COPPA email-plus parental consent request to the parent."""
    subject = f"Parental Consent Required — {child_name}’s MotaMaze Account"
    html = _build_consent_html(child_name, consent_url, company_website_url, privacy_email)
    await asyncio.to_thread(_send_sync, api_key, from_email, to_email, subject, html)


def _build_consent_html(
    child_name: str,
    consent_url: str,
    company_website_url: str,
    privacy_email: str,
) -> str:
    safe_name = child_name.replace("<", "&lt;").replace(">", "&gt;")
    safe_url = consent_url.replace('"', "%22")
    safe_website = company_website_url.replace('"', "%22")
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>MotaMaze Parental Consent</title>
<style>
  body {{ font-family: Arial, sans-serif; background:#f4f4f4; margin:0; padding:24px; color:#222; }}
  .card {{ background:#fff; border-radius:8px; max-width:520px; margin:0 auto; padding:32px; }}
  h1 {{ font-size:22px; margin:0 0 16px; }}
  p {{ line-height:1.6; margin:0 0 16px; }}
  .btn {{ display:inline-block; background:#1a73e8; color:#fff; text-decoration:none;
          padding:14px 28px; border-radius:6px; font-size:16px; font-weight:bold; }}
  .footer {{ font-size:12px; color:#888; margin-top:24px; }}
</style>
</head>
<body>
<div class="card">
  <h1>Parental Consent Request</h1>
  <p>Hello,</p>
  <p><strong>{safe_name}</strong> has created an account in <strong>MotaMaze</strong>,
  a mobile maze game developed by Ingenious Crucible Studios. Because they are under the
  age of consent in their country, we need your approval before they can continue using the app.</p>
  <p><strong>What we collect:</strong> account name, gameplay progress, and country of registration.
  We do not collect precise location, contacts, or payment information from minors. Their account
  will not show ads, appear on public leaderboards, or share scores until you explicitly approve
  those features in the future.</p>
  <p>To approve their account, click the button below. This link is valid for <strong>72 hours</strong>.</p>
  <p><a class="btn" href="{safe_url}">Approve Account</a></p>
  <p>If you did not expect this email or do not wish to approve, simply ignore it.
  The account will remain inactive.</p>
  <p class="footer">
    Ingenious Crucible Studios &mdash; <a href="{safe_website}">MotaMaze</a><br>
    Questions? Contact us at <a href="mailto:{privacy_email}">{privacy_email}</a>
  </p>
</div>
</body>
</html>"""
