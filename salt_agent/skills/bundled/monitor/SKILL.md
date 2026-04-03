---
name: monitor
description: Check system and application health
user-invocable: true
---
# Monitor System Health

Check the health of the system and running services:

1. System resources:
   - CPU usage: `top -l 1 | head -5` (macOS) or `top -bn1 | head -5` (Linux)
   - Memory: `vm_stat` (macOS) or `free -h` (Linux)
   - Disk: `df -h`
   - Load average: `uptime`
2. Running processes:
   - Check for expected services: `ps aux | grep <service>`
   - Port listeners: `lsof -i -P -n | grep LISTEN`
3. Application health:
   - Hit health check endpoints if configured
   - Check application logs for recent errors
   - Verify database connectivity
4. Git status: any uncommitted changes or unpushed commits
5. Dependency status: check for outdated or vulnerable packages
6. Summarize findings with a clear health/warning/critical status
