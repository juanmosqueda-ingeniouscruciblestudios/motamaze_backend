provider "google" {
  project = "motamaze"
  region  = "us-central1"
}

module "env" {
  source = "../../modules/motamaze-env"

  project_id      = "motamaze"
  environment     = "prod"
  cloud_run_image = "" # Set when INFRA-003 image exists
}

output "backend_sa_email" { value = module.env.backend_sa_email }
output "cloud_run_url"    { value = module.env.cloud_run_url }

# NOTE: prod resources already exist from INFRA-001 (created manually).
# Run `terraform import` for each resource before `terraform apply`.
# Import commands are documented in the INFRA-006 changelog.
