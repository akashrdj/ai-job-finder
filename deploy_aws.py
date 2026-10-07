"""
AWS Serverless Deployer (Python / Boto3)
========================================
Creates and configures:
1. IAM Role (ai-job-finder-lambda-role)
2. AWS Lambda Function (ai-job-finder-cron) using the ECR image
3. Environment variables synced from backend/.env
4. Amazon EventBridge Schedule (Every 8 hours)
5. Test invocation to verify end-to-end execution
"""

import os
import sys
import json
import time
from pathlib import Path

def load_env_vars() -> dict:
    env_file = Path("backend/.env")
    env_vars = {}
    if env_file.exists():
        with open(env_file, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith("#") and "=" in line:
                    k, v = line.split("=", 1)
                    k, v = k.strip(), v.strip()
                    if k and v:
                        env_vars[k] = v
    return env_vars

import sys
if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

def deploy():
    import boto3
    from botocore.exceptions import ClientError

    region = "ap-south-1"
    repo_name = "ai-job-finder"
    func_name = "ai-job-finder-cron"
    role_name = "ai-job-finder-lambda-role"
    rule_name = "ai-job-finder-8hr-schedule"
    schedule_expr = "cron(0 2,10,18 * * ? *)"

    print("\n=== [DEPLOYER] AWS Serverless Deployer (Boto3) ===")
    
    sts = boto3.client("sts", region_name=region)
    identity = sts.get_caller_identity()
    account_id = identity["Account"]
    user_arn = identity["Arn"]
    print(f"[OK] Authenticated: Account {account_id} | User {user_arn} in {region}")

    image_uri = f"{account_id}.dkr.ecr.{region}.amazonaws.com/{repo_name}:latest"
    print(f"[OK] Target ECR Image: {image_uri}")

    # 1. IAM Role
    iam = boto3.client("iam")
    trust_policy = {
        "Version": "2012-10-17",
        "Statement": [
            {
                "Effect": "Allow",
                "Principal": {"Service": "lambda.amazonaws.com"},
                "Action": "sts:AssumeRole"
            }
        ]
    }

    try:
        role_resp = iam.get_role(RoleName=role_name)
        role_arn = role_resp["Role"]["Arn"]
        print(f"[OK] Using existing IAM Role: {role_arn}")
    except iam.exceptions.NoSuchEntityException:
        print(f"Creating IAM execution role: {role_name}...")
        role_resp = iam.create_role(
            RoleName=role_name,
            AssumeRolePolicyDocument=json.dumps(trust_policy),
            Description="Execution role for AI Job Finder Lambda"
        )
        role_arn = role_resp["Role"]["Arn"]
        iam.attach_role_policy(
            RoleName=role_name,
            PolicyArn="arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
        )
        print(f"[OK] Created IAM Role: {role_arn}")
        print("Waiting 10s for IAM propagation...")
        time.sleep(10)

    # 2. Lambda Function
    lambda_client = boto3.client("lambda", region_name=region)
    env_vars = load_env_vars()
    print(f"Loaded {len(env_vars)} environment variables from backend/.env")

    try:
        func = lambda_client.get_function(FunctionName=func_name)
        print(f"Updating existing Lambda function: {func_name}...")
        lambda_client.update_function_code(
            FunctionName=func_name,
            ImageUri=image_uri
        )
        # Wait for code update to be active
        print("Waiting for function update...")
        waiter = lambda_client.get_waiter("function_updated_v2")
        waiter.wait(FunctionName=func_name)
        
        lambda_client.update_function_configuration(
            FunctionName=func_name,
            Role=role_arn,
            Timeout=300,
            MemorySize=512,
            Environment={"Variables": env_vars}
        )
        print(f"[OK] Lambda function updated successfully: {func_name}")
    except lambda_client.exceptions.ResourceNotFoundException:
        print(f"Creating new Lambda function: {func_name}...")
        create_resp = lambda_client.create_function(
            FunctionName=func_name,
            PackageType="Image",
            Code={"ImageUri": image_uri},
            Role=role_arn,
            Timeout=300,
            MemorySize=512,
            Environment={"Variables": env_vars}
        )
        print(f"[OK] Lambda function created: {create_resp['FunctionArn']}")
        print("Waiting for function to be active...")
        waiter = lambda_client.get_waiter("function_active_v2")
        waiter.wait(FunctionName=func_name)

    func_info = lambda_client.get_function(FunctionName=func_name)
    func_arn = func_info["Configuration"]["FunctionArn"]

    # 3. Amazon EventBridge Schedule (Every 8 hours)
    events_client = boto3.client("events", region_name=region)
    print(f"\nConfiguring Amazon EventBridge rule: {rule_name} ({schedule_expr})...")
    rule_resp = events_client.put_rule(
        Name=rule_name,
        ScheduleExpression=schedule_expr,
        Description="Triggers AI Job Finder every 8 hours",
        State="ENABLED"
    )
    rule_arn = rule_resp["RuleArn"]
    print(f"[OK] EventBridge Rule: {rule_arn}")

    # Add Lambda permission for EventBridge
    try:
        lambda_client.add_permission(
            FunctionName=func_name,
            StatementId=f"EventBridgeInvoke-{rule_name}",
            Action="lambda:InvokeFunction",
            Principal="events.amazonaws.com",
            SourceArn=rule_arn
        )
        print("[OK] Added EventBridge invoke permission to Lambda.")
    except lambda_client.exceptions.ResourceConflictException:
        print("[OK] EventBridge invoke permission already in place.")

    # Put Target
    events_client.put_targets(
        Rule=rule_name,
        Targets=[
            {
                "Id": "1",
                "Arn": func_arn
            }
        ]
    )
    print("[OK] Linked Lambda as target for EventBridge schedule.")

    print("\n" + "="*50)
    print("[SUCCESS] DEPLOYMENT COMPLETE! YOUR JOB FINDER IS LIVE ON AWS!")
    print(f"Lambda Function: {func_name}")
    print(f"Schedule: Runs automatically every 8 hours ({schedule_expr})")
    print("="*50 + "\n")

    # 4. Trigger test invocation
    print("Triggering test invocation on AWS Lambda now (Async Event)...")
    invoke_resp = lambda_client.invoke(
        FunctionName=func_name,
        InvocationType="Event"
    )
    print(f"HTTP Status: {invoke_resp.get('StatusCode')} (Invocation Accepted)")

if __name__ == "__main__":
    deploy()
