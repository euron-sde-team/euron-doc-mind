# Deploy to AWS

This guide deploys a complete environment with one command: network, keys, database,
cache, storage, the ingestion queue, the web app, the API, the worker and monitoring. Two
environments ship with the repository: `aws-dev` (a cheaper full copy) and `aws-prod`. Both
call the same module, `infra/terraform/modules/deployment`, with different sizes and safety
switches.

After deployment you have:

| URL | Application |
| --- | --- |
| `https://app.<domain>` | Web app |
| `https://api.<domain>` | API (`/api/v1`, interactive reference at `/docs`) |

The worker has no URL: it consumes the ingestion queue.

## Prerequisites

| Requirement | Notes |
| --- | --- |
| An AWS account and credentials | With permission to create the resources below; the deploy runs as you |
| Terraform 1.10 or later | `versions.tf` requires `>= 1.10.0`, the AWS provider `~> 6.70` and `random ~> 3.9` |
| Docker with `buildx` | Images are built for `linux/arm64` (Fargate on Graviton) |
| AWS CLI v2 | ECR login, waiting for services, one-off tasks |
| `python3` | Used by the deploy scripts to read Terraform output |
| A domain | The apps are served at `app.` and `api.` under it |

Set your region in the shell to the same value you put in `terraform.tfvars`. The deploy
script uses `AWS_REGION` first, then your CLI default region, then the `region` in the
tfvars file:

```bash
export AWS_REGION=us-east-1
```

## 1. Configure the environment

```bash
cp infra/terraform/envs/aws-dev/terraform.tfvars.example infra/terraform/envs/aws-dev/terraform.tfvars
```

`terraform.tfvars` is git-ignored. Variables:

| Variable | Required | Default | Meaning |
| --- | --- | --- | --- |
| `region` | no | `us-east-1` | AWS region |
| `name_prefix` | no | `docmind-dev` / `docmind-prod` | Prefix for every resource name. The bucket name derives from it, so make it globally unique (for example `acme-docmind-dev`) |
| `domain` | yes | | Base domain, for example `docmind.example.com` |
| `route53_zone_id` | one of these two | `null` | Hosted zone for the domain: automatic certificate and DNS records |
| `certificate_arn` | one of these two | `null` | An existing regional ACM certificate covering `app.` and `api.<domain>`, when the zone is not in Route53 |
| `product_name` | no | `Euron DocMind` | Shown in the web app and the API reference |
| `image_tag` | set by `make aws-deploy` | `latest` | Image tag to deploy; set it here only to pin a release for `terraform` runs by hand |
| `db_instance_class` | no | `db.t4g.medium` | RDS instance class |
| `cache_node_type` | no | `cache.t4g.small` | ElastiCache node type |
| `alarm_email` | no | `null` | Address subscribed to the alarm topic (confirm the subscription email) |
| `llm_provider` | no | `none` | `none` (offline extractive answers), `openai` or `ollama` |
| `llm_model`, `llm_base_url` | with a provider | empty, OpenAI | The model and the OpenAI-compatible base URL |
| `llm_api_key_secret_arn` | with a hosted provider | `null` | A Secrets Manager reference for `LLM_API_KEY`, in the ECS `valueFrom` form (`arn:...:secret:<name>:LLM_API_KEY::`). Create the secret yourself; the key never appears in Terraform |

Minimal example:

```hcl
region          = "us-east-1"
name_prefix     = "acme-docmind-dev"
domain          = "docmind.example.com"
route53_zone_id = "<ROUTE53_HOSTED_ZONE_ID>"
alarm_email     = "oncall@example.com"
```

The module has more inputs with sensible defaults (task sizes and counts, worker
concurrency, VPC CIDR, flow log retention, `extra_environment` for non-secret settings);
see `infra/terraform/modules/deployment/variables.tf`. `extra_environment` values land in
the ECS task definition in plain text, so never put secrets there.

### Remote state

State contains the generated application secrets. For anything shared, store it in S3:

```bash
cp infra/terraform/envs/aws-dev/backend.tf.example infra/terraform/envs/aws-dev/backend.tf
```

Uncomment the block and fill in a bucket that is private, versioned and encrypted, with
access limited to the people who deploy. The example uses S3-native locking
(`use_lockfile = true`), so no DynamoDB table is needed.

## 2. Deploy

```bash
make aws-deploy ENV=aws-dev
```

`ENV` defaults to `aws-dev`. `TAG` defaults to the first 12 characters of the current
commit hash; pass `TAG=...` to choose one. The target runs `scripts/aws-deploy.sh <env>
<tag>`, which:

1. checks that `terraform`, `docker` and `aws` are installed and that
   `envs/<env>/terraform.tfvars` exists, and notes if the working tree has uncommitted
   changes (the images are built from the tree as it is);
2. runs `terraform init`;
3. **registries**: `terraform apply -target=module.docmind.module.ecr` (the ECR repositories
   for `api` and `web`, and the KMS key that encrypts them);
4. logs Docker in to ECR;
5. **images**: builds `api` and `web` with `docker buildx build --platform linux/arm64` from
   `infra/docker/*.Dockerfile` and pushes `<repo>:<tag>`;
6. **infrastructure**: `terraform apply` of everything else with that `image_tag`;
7. **rollout**: `aws ecs wait services-stable` for the `api`, `worker` and `web` services;
8. prints the `urls` output and the next step.

Database migrations run when the API boots (`MIGRATE_ON_BOOT=true`), under an advisory lock,
so several tasks starting together are safe. To run them as an explicit step instead:

```bash
make aws-migrate ENV=aws-dev
```

To preview changes without applying:

```bash
make aws-plan ENV=aws-dev
```

ECR tags are immutable, so every deployment needs a tag that has not been pushed before:
commit first, or pass a new `TAG`.

## 3. DNS

### With a Route53 zone (`route53_zone_id`)

Everything is automatic: the ACM certificate and its validation records, and `A` aliases for
`app.` and `api.<domain>` to the load balancer.

### Without a Route53 zone (`certificate_arn`)

Request or import an ACM certificate for `app.<domain>` and `api.<domain>` in the
deployment region yourself, pass its ARN as `certificate_arn`, then after the first apply
point both names at the load balancer with `CNAME` records at your DNS provider:

```bash
terraform -chdir=infra/terraform/envs/aws-dev output load_balancer_dns_name
```

## 4. Create the first account

Open `https://app.<domain>`. While the deployment has no account, the sign-in page offers
**Set up DocMind**: the first account created there becomes the administrator. Do this
before sharing the URL. Then create a workspace and add people from Settings, Members; new
members receive a temporary password you pass on to them. Sign-up stays closed for everyone
else unless you set `ALLOW_SIGNUP=true` through `extra_environment`.

Every DocMind CLI command can also run as a one-off Fargate task with the API's network,
secrets and database access, for example to reindex a workspace:

```bash
make aws-cli ENV=aws-dev ARGS="reindex --workspace northwind"
```

`scripts/aws-run-task.sh` starts the task, waits for it, and prints its recent logs
(`/docmind/<name_prefix>/cli`). Avoid passing passwords as arguments: task overrides are
visible in the ECS API and CloudTrail.

## Sizing

Values from `envs/aws-dev/main.tf`, `envs/aws-prod/main.tf` and the module defaults:

| Setting | aws-dev | aws-prod |
| --- | --- | --- |
| Availability zones | 2 | 3 |
| NAT gateways | 1 (shared) | 1 per AZ |
| Interface endpoints (KMS, Secrets Manager) | off | on |
| WAF | off | on |
| Database instance | `db.t4g.medium` | `db.t4g.medium` |
| Database Multi-AZ | no | yes |
| Database storage | 30 GiB gp3, autoscaling to 200 GiB | same |
| Automated backup retention | 3 days | 14 days |
| Deletion protection (RDS, ALB) and final DB snapshot | off | on |
| Cache | `cache.t4g.small`, no replica | `cache.t4g.small`, one replica with failover |
| S3 bucket and ECR force-destroy | on | off |
| KMS key deletion window | 7 days | 30 days |
| Secrets recovery window | 0 (immediate) | 30 days |
| API tasks (min to max) | 1 to 2 | 2 to 6 |
| Worker tasks (min to max) | 1 to 2 | 2 to 8 |
| Web tasks (min to max) | 1 to 2 | 2 to 6 |
| API and worker task size | 1 vCPU, 2 GiB | same |
| Web task size | 0.25 vCPU, 0.5 GiB | same |
| Documents per worker task | 2 (`worker_concurrency`) | same |
| Application log retention | 14 days | 365 days |

Autoscaling targets 60 percent average CPU. The worker's CPU is what embedding uses, so a
bulk import scales the worker service out until the queue drains.

## Alarms

Alarms are named `<name_prefix>-<alarm>` and publish to the `<name_prefix>-alarms` SNS topic
(emailed to `alarm_email` when set); the CloudWatch dashboard shows the same signals.

| Alarm | Fires when |
| --- | --- |
| `api-5xx`, `web-5xx` | More than 25 responses with a 5xx status from the tasks in 5 minutes |
| `api-unhealthy`, `web-unhealthy` | Any task failing load balancer health checks |
| `api-cpu`, `worker-cpu`, `web-cpu` | CPU above 85 percent for 5 minutes |
| `api-memory`, `worker-memory`, `web-memory` | Memory above 85 percent for 5 minutes |
| `ingest-backlog` | The oldest queued document has waited more than 10 minutes |
| `ingest-dead-letters` | Any message in the dead-letter queue (a document gave up after repeated failures) |
| `db-cpu`, `db-storage`, `db-connections` | Database CPU above 80 percent, free storage below 5 GiB, connections above 80 percent of the configured ceiling (`db_max_connections`, 200) |

What to do when one fires: [operations.md](operations.md).

## Cost notes

No prices are quoted here; use the AWS Pricing Calculator for your region. What drives the
bill, roughly in order:

- **Always-on tasks**: the minimum task counts run around the clock (3 tasks in `aws-dev`,
  6 in `aws-prod`), plus Container Insights metrics.
- **The database**: Multi-AZ runs a standby instance; storage, backups beyond the free
  allowance, Performance Insights and Enhanced Monitoring add to it.
- **The cache**: one node per replica.
- **NAT gateways**: hourly per gateway plus per-GB processing. `aws-prod` runs three. S3
  traffic avoids NAT through the gateway endpoint.
- **Interface endpoints** (`aws-prod`): hourly per endpoint per AZ.
- **Load balancer and WAF**: hourly plus capacity units; WAF per request and per rule.
- **CloudWatch Logs**: ingestion and the 365-day retention in `aws-prod`.
- **A hosted model**, when `llm_provider` is set: per token, reduced by the answer cache.
  The insights page shows the tokens actually sent.

To reduce `aws-dev` cost further, lower the task counts and destroy the environment when
idle.

## Updating

Commit, then run `make aws-deploy ENV=<env>` again. The services roll with a circuit
breaker: a deployment whose tasks fail health checks is rolled back automatically.

To go back to an earlier release, apply its tag; its images are still in ECR (the
repositories keep the 30 most recent images):

```bash
terraform -chdir=infra/terraform/envs/aws-dev apply -var image_tag=<earlier tag>
```

`make aws-deploy` cannot be used for this, because it builds and pushes, and ECR refuses to
overwrite an existing tag.

Migrations only move forward; an older image runs against a newer schema only when the
migrations in between were additive. Check `apps/api/src/docmind/migrations/versions/`
before rolling back across a schema change.

## Tearing down

Take a manual database snapshot first if you need the data. In `aws-prod` a final snapshot
is taken only while deletion protection is on, and turning protection off (below) also turns
the final snapshot off.

`aws-dev`:

```bash
terraform -chdir=infra/terraform/envs/aws-dev destroy -var image_tag=<deployed tag>
```

`aws-prod` has deletion protection on. To destroy it, set `deletion_protection = false` in
`envs/aws-prod/main.tf`, apply, empty the versioned documents bucket (all object versions)
and delete the images in the ECR repositories, then run `destroy`. The KMS key is scheduled
for deletion after its 30-day window and the secrets after their 30-day recovery window; you
can cancel either during that time.

## Next steps

- Day-two operations: [operations.md](operations.md)
- Every setting: [configuration.md](configuration.md)
- Security controls and the operator checklist: [security.md](../architecture/security.md#operator-checklist)
