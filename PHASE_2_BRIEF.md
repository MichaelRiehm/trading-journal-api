# Phase 2 brief: EKS, Terraform, CI/CD to ECR

Status: draft for Michael's approval (issue #17). It follows on from [PROJECT_BRIEF.md](PROJECT_BRIEF.md), whose working rules, docs rules and quality bar still apply.

## Goal

**Run the Phase 1 API on AWS:**
- on Kubernetes (EKS)
- with every resource created by Terraform
- with images built by CI and pushed to ECR
- behind a public HTTPS URL on our own domain

This closes the brief's other two skill gaps: Kubernetes and AWS infrastructure.

**The bar is the same as Phase 1:** every resource and every setting is one Michael can explain and defend in an interview. Prefer the explainable, standard choice over the clever one. Accuracy over embellishment.

## Decisions already made (by Michael)

| Question | Decision |
|---|---|
| AWS account | His **existing** account. The project's resources are isolated by tags, naming and a dedicated IAM role (see "Guardrails"). |
| Lifecycle | **Up for demos only.** `make env-up` creates the environment, and `make env-down` destroys it. Only near-free pieces stay up permanently. |
| Domain | A **new domain registered through Route 53**, so DNS and certificates live in the same account and in Terraform. |
| Region | **Tokyo, `ap-northeast-1`.** It's close to Japan-based viewers and to the employers being targeted. In demo-only mode it costs only a few dollars a month more than `us-east-1`. |

## Architecture

```
Internet ── HTTPS ──▶ Route 53 (api.<domain>) ──▶ ALB (ACM certificate, created by the
                                                       AWS Load Balancer Controller)
                                                    │
                     ┌──────────────── VPC, 2 AZs ──┼──────────────────────────────┐
                     │ public subnets:  ALB, NAT gateway (one, for cost)           │
                     │ private subnets: EKS managed node group (2× Graviton)       │
                     │                    └ pods: api (2 replicas), migrate Job,   │
                     │                      LB controller, external-dns,           │
                     │                      External Secrets Operator             │
                     │                  RDS PostgreSQL (single-AZ, private)        │
                     └─────────────────────────────────────────────────────────────┘
GitHub Actions ── OIDC (no stored AWS keys) ──▶ ECR (immutable tags, scan on push)
                                             └▶ helm upgrade, when the environment is up
```

### Two Terraform layers, so "demo-only" stays cheap

- **`infra/foundation/`** stays up permanently and costs about $2/month:
  - the Terraform state bucket (S3, with S3-native state locking: no DynamoDB table)
  - the ECR repository
  - the Route 53 hosted zone
  - the GitHub OIDC provider and its IAM roles
  - the AWS Budgets alarms
- **`infra/environment/`** is created and destroyed on demand, about 20 minutes each way:
  - the VPC and NAT gateway
  - the EKS cluster and node group
  - RDS
  - the Secrets Manager secrets
  - the ACM certificate
  - the cluster add-ons
- **The split is the cost model.** The environment layer reads the foundation's outputs, and nothing in the foundation depends on the environment.

### Choices, each to get its own ADR in the stage that makes it

**Compute and deployment**
- **Managed node group on Graviton (`t4g`), not EKS Auto Mode or Fargate.**
  - It's the standard, fully explainable baseline: you can see and reason about the nodes.
  - Auto Mode adds a per-instance management fee (roughly 12% on top of EC2) and hides the parts an interview asks about.
  - Graviton is about 20% cheaper than x86.
  - The image is built for `linux/arm64` on GitHub's native arm runners (free for public repos).
- **Helm chart in the repo (`deploy/helm/trading-journal-api`)** for the app.
  - Migrations run as a Helm pre-install/pre-upgrade hook Job, using the same image as the API (designed for this since Stage 0).
  - Probes: `/health` for liveness and `/ready` for readiness.
  - Hardening: resource requests and limits, a non-root and read-only-root-filesystem `securityContext`, and a PodDisruptionBudget.

**Identity and data**
- **IAM for pods via EKS Pod Identity,** not IRSA: it's the current AWS recommendation and has simpler trust policies. Cluster access goes through **EKS access entries**, not the legacy `aws-auth` ConfigMap.
- **Database: RDS for PostgreSQL** (the newest major version RDS offers, checked in Stage 3), `db.t4g.micro`, single-AZ, in private subnets, reachable only from the nodes' security group.
  - Demo data is re-seeded by a script after `env-up`. A real Multi-AZ setup is described in the ADR but not paid for.
- **Secrets in AWS Secrets Manager** (the database credentials, managed by RDS, and the JWT key), synced into Kubernetes Secrets by the **External Secrets Operator**. No secret is in Git, in Terraform state outputs, or in Helm values.

**Ingress**
- **AWS Load Balancer Controller + Ingress → ALB,** with TLS from **ACM** (free).
- **external-dns** points `api.<domain>` at the ALB, so DNS follows the ALB whenever the environment is recreated.

**Pipeline**
- **CI/CD with GitHub Actions and OIDC,** with no long-lived AWS keys anywhere:
  - **On every PR:** `terraform fmt -check`, `validate`, tflint and Checkov for the Terraform; `helm lint` plus a kubeconform schema check for the chart.
  - **On merge to `main`:** build the arm64 image, push it to ECR tagged with the git SHA (immutable), and scan it.
  - **Deploy:** a `deploy` workflow (manual, or automatic on merge when the environment exists) runs `helm upgrade --install` with that SHA.
  - **Terraform `apply`** runs from Michael's machine through `make` targets in Phase 2. Applying from CI is a Phase 2+ follow-up, once the plan/apply roles are worth the setup.

## Guardrails (an existing account, real money)

- **Every resource is tagged** `Project=trading-journal` (through the AWS provider's `default_tags`), and cost allocation by that tag is enabled.
- **AWS Budgets alarms** at $20 and $40 per month (actual) and at $40 forecast, by email.
- **A nightly teardown:** a scheduled workflow destroys the environment layer at 03:00 JST if it's still up. Forgetting `env-down` can then cost at most one day (about $7).
- **Least privilege:**
  - GitHub's roles can push to *this* ECR repository and deploy to *this* cluster, and nothing else.
  - Terraform runs under a dedicated role, not root.
- **Cluster security:**
  - The cluster API endpoint is public but restricted to Michael's IP range.
  - Nodes use IMDSv2 only.
  - The VPC CNI enforces Kubernetes NetworkPolicies: the API may reach only RDS and DNS.

## Cost estimate (to re-verify in Stage 0)

Tokyo, on-demand. These are estimates from AWS's published rates and third-party price trackers. Stage 0 re-checks them in the AWS Pricing Calculator and records the result in an ADR.

| While the environment is up | Per hour |
|---|---|
| EKS control plane (same price in every region) | $0.10 |
| 2 × `t4g.medium` nodes | ~$0.09 |
| NAT gateway (plus $0.062/GB processed) | ~$0.06 |
| ALB | ~$0.03 |
| RDS `db.t4g.micro` | ~$0.03 |
| Public IPv4 addresses (NAT, ALB) | ~$0.02 |
| **Total** | **~$0.33/hour, about $8/day** |

| Always on | Per month |
|---|---|
| Domain (.com, about $15/year) | ~$1.25 |
| Route 53 hosted zone | $0.50 |
| ECR storage and S3 state | < $0.50 |

**Typical month** (about 40 hours up for development and demos): about **$15**.

**Always on,** for comparison: about $240/month in Tokyo, or about $200 in `us-east-1`.

## Stages

Each stage follows the Phase 1 process: issue → branch → plan mode → approval → PR → CI → Michael merges. A stage's AWS cost while it's being built is noted next to it.

0. **Accounts, guardrails and Terraform bootstrap** (≈ $0).
   - Michael's one-time steps: install the AWS CLI and Terraform, set up an SSO/admin profile, and confirm MFA on root.
   - Code: the state bucket (bootstrapped once, then managed by Terraform itself), the tags, the budgets, and the GitHub OIDC provider.
   - CI: the Terraform lint/scan checks.
   - Verify the prices and pin the tool versions (Terraform, AWS provider, EKS version).
1. **ECR and the image pipeline** (≈ $0).
   - The ECR repository (immutable tags, scan on push, a lifecycle policy that keeps the last 20 images).
   - An arm64 build on merge to `main`, pushed through OIDC.
   - The `image` CI job also builds arm64.
2. **Network and cluster** (a few dollars, created and destroyed while building).
   - The VPC, the NAT gateway, EKS with a managed node group, access entries, and the core add-ons (VPC CNI with network policy, CoreDNS, kube-proxy, Pod Identity agent).
   - `make env-up` / `make env-down`, and the nightly teardown.
3. **Database and secrets.** RDS, the Secrets Manager secrets, the External Secrets Operator, Pod Identity, and the seed script.
4. **The app on Kubernetes.** The Helm chart, the migration hook Job, probes, security context, PDB and NetworkPolicy. Verify through `kubectl port-forward`.
5. **A public HTTPS URL.**
   - Register the domain. Michael does this himself: it's a purchase in his name.
   - The hosted zone, ACM, the Load Balancer Controller, the Ingress, and external-dns.
   - `https://api.<domain>/docs` works.
6. **Continuous deployment and wrap-up.**
   - The deploy workflow (merge → image → `helm upgrade`).
   - A runbook (`docs/runbook.md`: up, down, deploy, roll back, read logs, rotate the JWT key).
   - The README's "Deploying" section and the Phase 2 learning-log and interview-prep entries.

## Out of scope for Phase 2

- **Multi-AZ RDS, multiple NAT gateways, and an always-on production environment:** described in ADRs, not paid for.
- **GitOps (Argo CD or Flux), Karpenter, and a service mesh:** worth knowing, and named in interview prep as next steps.
- **Observability beyond logs:** container logs go to CloudWatch Logs. Prometheus, Grafana and OpenTelemetry tracing are Phase 2+ follow-ups.
- **Applying Terraform from CI, and multiple environments** (staging and prod): follow-ups.
- **WAF and rate limiting:** noted as a risk for a public demo; the environment being down most of the time limits the exposure.
- **The Phase 3 integrations** (TradingView, Webull).

## Working rules (in addition to PROJECT_BRIEF.md)

- **Michael approves every action that spends money or touches the account outside Terraform:**
  - buying the domain
  - a first `apply` that creates billable resources
  - changing a budget
- **The environment is destroyed at the end of every working session.** Each stage's PR says how to verify it and how to tear it down.
- **What never goes into the repo or a CI log:**
  - AWS account IDs where avoidable, and access keys
  - Terraform state, and secrets
  - Michael's IP address
- **Terraform conventions:**
  - Terraform code is formatted, validated and scanned in CI like the Python code.
  - Modules come from the official `terraform-aws-modules` only where they save real work (the VPC and EKS); everything else is written directly, so it can be explained.
  - Versions are pinned: Terraform and providers in `.terraform.lock.hcl`, Helm charts by version.
