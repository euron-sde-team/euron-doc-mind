# Security Incident Response Runbook

Owner: Dana Whitfield, Chief Information Security Officer. Reviewed every quarter.

## Severity levels

| Severity | Examples | Acknowledge within | Who is paged |
| --- | --- | --- | --- |
| SEV1 | Customer data exposed, fleet-wide outage, robot safety incident | 15 minutes | On-call incident commander through PagerDuty service northwind-sev1, then the CISO |
| SEV2 | Single customer site down, suspected account compromise | 1 hour | Security on-call engineer |
| SEV3 | Phishing report, policy violation without data exposure | Next business day | Security team queue |

For a SEV1, page the on-call incident commander through the PagerDuty service northwind-sev1 and notify the CISO
within 30 minutes. If you cannot reach anyone, call the security hotline at +1 512 555 0142.

## Response steps

1. Detect and report. Anyone can declare an incident in the #security channel.
2. Triage. The incident commander confirms the severity and opens an incident document.
3. Contain. Isolate affected accounts, robots or services. Preserve evidence before changing anything.
4. Eradicate. Remove the cause: revoke credentials, patch, or roll back.
5. Recover. Restore service and watch closely for 24 hours.
6. Learn. Hold a blameless postmortem within 5 business days and track every action item to completion.

## Evidence handling

Take screenshots and export logs before restarting anything. Store evidence in the restricted incident folder and
record who accessed it. Never send evidence over chat or personal email.

## Customer communication

Customer Success sends the first customer update for a SEV1 within 2 hours of declaration, after review by Legal.
Updates follow every 4 hours until the incident is resolved.
