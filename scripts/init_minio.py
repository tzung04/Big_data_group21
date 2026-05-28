import boto3

client = boto3.client('s3',
    endpoint_url='http://localhost:9000',
    aws_access_key_id='minioadmin',
    aws_secret_access_key='minioadmin'
)

for bucket in ['raw-data', 'spark-checkpoints', 'spark-output']:
    try:
        client.create_bucket(Bucket=bucket)
        print(f'Created: {bucket}')
    except Exception as e:
        print(f'Skipped {bucket}: {e}')

#python scripts/init_minio.py