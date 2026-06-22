# DEFERRED — 2026-06-22 decision: staging activates ~1 month after prod launch.
# Do NOT run terraform apply here until that date. Project motamaze-staging exists
# (created in INFRA-006 ST-01) but billing is not linked and no resources deployed.

provider "google" {
  project = "motamaze-staging"
  region  = "us-central1"
}

module "env" {
  source = "../../modules/motamaze-env"

  project_id      = "motamaze-staging"
  environment     = "staging"
  cloud_run_image = "" # Set when INFRA-003 image exists
}

output "backend_sa_email" { value = module.env.backend_sa_email }
output "cloud_run_url"    { value = module.env.cloud_run_url }
