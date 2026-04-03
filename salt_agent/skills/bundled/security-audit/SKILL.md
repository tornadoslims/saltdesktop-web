---
name: security-audit
description: Review code for security vulnerabilities
user-invocable: true
---
# Security Audit

Perform a security review of the codebase:

1. Dependency analysis:
   - Check for known vulnerabilities: `pip audit`, `npm audit`, `cargo audit`
   - Identify outdated dependencies with known CVEs
2. Code review for common vulnerabilities:
   - SQL injection: raw string interpolation in queries
   - XSS: unescaped user input in templates/responses
   - Command injection: user input in shell commands
   - Path traversal: user-controlled file paths without sanitization
   - Hardcoded secrets: API keys, passwords, tokens in source
   - Insecure deserialization: pickle, eval, yaml.load without SafeLoader
3. Authentication and authorization:
   - Password hashing (bcrypt/argon2, not MD5/SHA1)
   - Token expiration and rotation
   - CORS configuration
   - Rate limiting
4. Configuration security:
   - Debug mode disabled in production
   - HTTPS enforced
   - Secure cookie flags
5. Report findings with severity (critical/high/medium/low) and remediation steps
