output "queue_url" {
  description = "SQS_QUEUE_URL for the API and the worker."
  value       = aws_sqs_queue.ingest.url
}

output "queue_arn" {
  description = "Ingestion queue ARN, for IAM policies."
  value       = aws_sqs_queue.ingest.arn
}

output "queue_name" {
  description = "Ingestion queue name, for CloudWatch alarms."
  value       = aws_sqs_queue.ingest.name
}

output "dlq_url" {
  description = "Dead-letter queue URL."
  value       = aws_sqs_queue.dlq.url
}

output "dlq_name" {
  description = "Dead-letter queue name, for CloudWatch alarms."
  value       = aws_sqs_queue.dlq.name
}
