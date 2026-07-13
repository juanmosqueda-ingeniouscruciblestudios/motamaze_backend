provider "google" {
  project = "motamaze-dev"
  region  = "us-central1"
}

module "env" {
  source = "../../modules/motamaze-env"

  project_id         = "motamaze-dev"
  environment        = "dev"
  cloud_run_image    = "" # Set when INFRA-003 image exists: "us-central1-docker.pkg.dev/motamaze/backend/motamaze-backend:latest"
  firestore_location = "us-central1" # Dev was created manually with us-central1; module default is nam5
}

output "backend_sa_email" { value = module.env.backend_sa_email }
output "cloud_run_url"    { value = module.env.cloud_run_url }
