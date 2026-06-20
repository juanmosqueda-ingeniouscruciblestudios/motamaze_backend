terraform {
  backend "gcs" {
    bucket = "motamaze-terraform-state"
    prefix = "dev"
  }
}
