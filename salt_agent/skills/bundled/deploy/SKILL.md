---
name: deploy
description: Deploy application to production or staging
user-invocable: true
---
# Deploy

Deploy the application safely:

1. Verify the current branch and commit are clean: `git status`
2. Run the test suite to ensure everything passes
3. Check for environment-specific configuration:
   - Environment variables
   - Config files for the target environment
   - Secrets and credentials (never commit these)
4. Identify the deployment method:
   - Docker: build image, push to registry, update service
   - Cloud platform: use platform CLI (fly deploy, vercel, railway, etc.)
   - Traditional: rsync/scp to server, restart service
   - Kubernetes: apply manifests or helm upgrade
5. Execute the deployment
6. Verify the deployment succeeded:
   - Health check endpoint responds
   - Smoke tests pass
   - No error spikes in logs
7. Report the deployment status and URL
