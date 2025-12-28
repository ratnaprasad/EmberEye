# Security Policy

## Reporting a Vulnerability

If you discover a security vulnerability in EmberEye, **please do not open a public issue**. Instead, email your findings to [security@embereye.dev](mailto:security@embereye.dev).

Please include:
- Description of the vulnerability
- Steps to reproduce
- Potential impact
- Suggested fix (if any)

We will acknowledge receipt within 48 hours and work on a fix promptly.

## Supported Versions

| Version | Supported |
|---------|-----------|
| 1.0.0   | ✅ Yes    |

## Known Security Considerations

- Thermal data contains sensitive location/activity information; ensure proper access controls
- Network streams should use encryption if transmitted over untrusted networks
- Credential files should not be committed to version control
- Update dependencies regularly with `pip install --upgrade -r requirements.txt`

## Security Best Practices

1. **Keep software updated** - Run security updates for Python and dependencies
2. **Protect credentials** - Store API keys/passwords outside of code
3. **Use HTTPS** - For any remote connections
4. **Minimize permissions** - Run EmberEye with least-privilege accounts
5. **Audit logs** - Regularly check error and access logs

Thank you for helping keep EmberEye secure!
