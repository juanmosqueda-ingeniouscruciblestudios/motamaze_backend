variable "project_id" {
  description = "GCP project ID (motamaze-dev | motamaze-staging | motamaze)"
  type        = string
}

variable "environment" {
  description = "Environment name: dev | staging | prod"
  type        = string
  validation {
    condition     = contains(["dev", "staging", "prod"], var.environment)
    error_message = "environment must be dev, staging, or prod."
  }
}

variable "region" {
  description = "Primary GCP region for Cloud Run and other regional resources"
  type        = string
  default     = "us-central1"
}

variable "bq_location" {
  description = "BigQuery dataset location"
  type        = string
  default     = "US"
}

variable "firestore_location" {
  description = "Firestore multi-region location"
  type        = string
  default     = "nam5"
}

variable "cloud_run_image" {
  description = "Docker image URL for Cloud Run service (Artifact Registry). Empty string skips Cloud Run deploy."
  type        = string
  default     = ""
}
