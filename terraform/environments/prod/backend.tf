terraform {
  backend "gcs" {
    bucket = "motamaze-terraform-state"
    prefix = "prod"
  }
}
