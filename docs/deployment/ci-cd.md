# CI/CD Integration

Bifröst is small enough to run inside any CI pipeline, and the SDK is the right surface for that. Two common patterns:

1. **Run the SDK as a deployment gate** — fail the build if a Grafana environment is unhealthy, dashboards are missing, alerts are firing, or datasources are broken.
2. **Run the MCP server as a sidecar** — give an AI agent in CI access to a real Grafana for dynamic checks.

This page covers both. Examples are in GitHub Actions, GitLab CI, and Jenkins.

## Pattern 1: SDK as a deployment gate

The fastest way to wire Bifröst into CI is to use the Python SDK directly. No server, no transports, just `pip install grafana-mcp-sdk` and a small Python script.

### Example: pre-deploy health check

```python
# scripts/check_grafana_health.py
import sys
from grafana_mcp_sdk import GrafanaMCP

def main() -> int:
    mcp = GrafanaMCP.from_env()
    with mcp.sync() as g:
        health = g.health_check()
        if health.status != "ok":
            print(f"❌ Grafana unhealthy: {health.error}", file=sys.stderr)
            return 1

        # Verify the critical dashboards still exist
        required = {"api-health", "postgres-overview", "kafka-prod"}
        dashboards = g.list_dashboards(tags=["critical"])
        present = {d.uid for d in dashboards}
        missing = required - present
        if missing:
            print(f"❌ Missing critical dashboards: {missing}", file=sys.stderr)
            return 1

        # Verify no alerts are currently firing
        firing = g.list_alert_instances(state="firing")
        if firing:
            print(f"❌ {len(firing)} alerts firing — refusing to deploy", file=sys.stderr)
            for a in firing:
                print(f"  • {a.rule_title}", file=sys.stderr)
            return 1

        print("✓ Grafana healthy, all critical dashboards present, no firing alerts")
        return 0

if __name__ == "__main__":
    sys.exit(main())
```

Run with:

```bash
GRAFANA_MCP_ACTIVE_ENVIRONMENT=prod \
GRAFANA_MCP_ACTIVE_ROLE=viewer \
GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL=https://grafana.company.com \
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER=$PROD_VIEWER_TOKEN \
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__EDITOR=$PROD_EDITOR_TOKEN \
GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN=$PROD_ADMIN_TOKEN \
python scripts/check_grafana_health.py
```

The exit code is the only thing CI needs to gate on.

### GitHub Actions

```yaml
# .github/workflows/pre-deploy-checks.yml
name: Pre-deploy checks

on:
  workflow_call:
    inputs:
      environment:
        required: true
        type: string

jobs:
  grafana-health:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4

      - uses: actions/setup-python@v5
        with:
          python-version: "3.13"

      - name: Install Bifröst SDK
        run: pip install grafana-mcp-sdk

      - name: Check Grafana health
        env:
          GRAFANA_MCP_ACTIVE_ENVIRONMENT: ${{ inputs.environment }}
          GRAFANA_MCP_ACTIVE_ROLE: viewer
          GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL: https://grafana.company.com
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER: ${{ secrets.GRAFANA_PROD_VIEWER }}
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__EDITOR: ${{ secrets.GRAFANA_PROD_EDITOR }}
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN: ${{ secrets.GRAFANA_PROD_ADMIN }}
        run: python scripts/check_grafana_health.py
```

Three things to notice:

1. **All three tokens are required** even though the script only uses `viewer` — the SDK validates the env block on construct.
2. **Secrets come from GitHub Actions secrets**, never from the repo.
3. **`grafana-mcp-sdk` is the only install** — no server, no Docker, no UI.

### GitLab CI

```yaml
# .gitlab-ci.yml
grafana-health:
  stage: pre-deploy
  image: python:3.13-slim
  variables:
    GRAFANA_MCP_ACTIVE_ENVIRONMENT: prod
    GRAFANA_MCP_ACTIVE_ROLE: viewer
    GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL: https://grafana.company.com
  script:
    - pip install grafana-mcp-sdk
    - python scripts/check_grafana_health.py
  rules:
    - if: $CI_COMMIT_BRANCH == "main"
```

GitLab masks secrets via the project's CI/CD variables. Set `GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER` etc. as masked variables.

### Jenkins

```groovy
// Jenkinsfile
pipeline {
    agent any
    stages {
        stage('Grafana Health') {
            environment {
                GRAFANA_MCP_ACTIVE_ENVIRONMENT = 'prod'
                GRAFANA_MCP_ACTIVE_ROLE = 'viewer'
                GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL = 'https://grafana.company.com'
                GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER = credentials('grafana-prod-viewer')
                GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__EDITOR = credentials('grafana-prod-editor')
                GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN  = credentials('grafana-prod-admin')
            }
            steps {
                sh 'pip install grafana-mcp-sdk'
                sh 'python scripts/check_grafana_health.py'
            }
        }
    }
}
```

## Pattern 2: MCP server as a CI sidecar

If your CI runs an AI agent (e.g., Claude Code in a GitHub Action), you can give the agent live Grafana access by booting Bifröst as a sidecar service.

### GitHub Actions example

```yaml
name: AI Grafana audit

on:
  schedule:
    - cron: "0 9 * * 1"   # Mondays at 9am UTC

jobs:
  audit:
    runs-on: ubuntu-latest
    services:
      bifrost:
        image: gpadidala/bifrost-core:1.3.0
        ports:
          - 8769:8769
        env:
          GRAFANA_MCP_ACTIVE_ENVIRONMENT: prod
          GRAFANA_MCP_ACTIVE_ROLE: viewer
          GRAFANA_MCP_TRANSPORT__MODE: http
          GRAFANA_MCP_TRANSPORT__PORT: 8769
          GRAFANA_MCP_ENVIRONMENTS__PROD__BASE_URL: https://grafana.company.com
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__VIEWER: ${{ secrets.GRAFANA_PROD_VIEWER }}
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__EDITOR: ${{ secrets.GRAFANA_PROD_EDITOR }}
          GRAFANA_MCP_ENVIRONMENTS__PROD__SERVICE_ACCOUNTS__ADMIN:  ${{ secrets.GRAFANA_PROD_ADMIN }}
        options: >-
          --health-cmd "curl -fsS http://localhost:8769/healthz || exit 1"
          --health-interval 10s
          --health-retries 5

    steps:
      - uses: actions/checkout@v4

      - name: Run Claude Code with Bifröst tools
        uses: anthropics/claude-code-action@v1
        with:
          prompt: |
            Use the grafana MCP server (http://localhost:8769) to audit our prod Grafana:
            1. Are any datasources unhealthy?
            2. Are any critical dashboards missing panels?
            3. Are any alert rules in 'no_data' state for more than 24 hours?
            Open a GitHub issue for each problem with details and recommended fix.
          mcp-servers: |
            {
              "grafana": { "type": "http", "url": "http://localhost:8769/mcp/messages" }
            }
```

The agent gets the same tool surface a developer gets in VSCode, scoped to whatever role the sidecar was started with. **Always start the sidecar in `viewer` mode unless you intentionally want write access** — CI is not a place for accidental admin token use.

## Best practices

### Always use the lowest role you can

If your CI script only needs to read, use `viewer`. The SDK + server enforce this — calling a write tool from a viewer-scoped process raises `PermissionError`. Defense in depth.

### Pin the SDK / image version

```bash
pip install grafana-mcp-sdk==1.3.0
```

```yaml
image: gpadidala/bifrost-core:1.3.0
```

CI is not the place to discover that a minor SDK rev changed a tool's output schema.

### Validate config on first run

Add a `grafana-mcp validate-config` step at the very top of the pipeline. It catches token rotation lapses *before* the rest of the pipeline runs, with a clear error.

```yaml
- name: Validate Grafana config
  run: uvx grafana-mcp validate-config
```

(`uvx` is the `uv tool run` shorthand — it runs the `grafana-mcp` CLI in an ephemeral env without a permanent install.)

### Rotate tokens via your secrets manager

The Bifröst tokens are just Grafana service-account tokens. Rotate them on the same cadence as any other service-account credential. Vault, AWS Secrets Manager, GitHub Actions secrets, GitLab CI variables — all work fine.

### Treat the SDK script like any other CI dep

`scripts/check_grafana_health.py` belongs in version control alongside your tests. Lint it, type-check it, test it locally with `python scripts/check_grafana_health.py` against your dev env before pushing. It's a real Python module, not a YAML snippet.

## Related

- [Python SDK reference](../api/sdk-reference.md)
- [Configuration reference](../getting-started/configuration.md)
- [Role model](../architecture/role-model.md)
