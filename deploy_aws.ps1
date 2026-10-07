<#
.SYNOPSIS
    Deploys AI Job Finder to AWS Lambda + Amazon EventBridge (100% Free Tier).

.DESCRIPTION
    1. Builds Docker container from Dockerfile.lambda
    2. Authenticates and pushes to Amazon ECR (Elastic Container Registry)
    3. Creates/updates AWS Lambda function with 512MB RAM & 120s timeout
    4. Sets up Amazon EventBridge Schedule rule to trigger Lambda every 8 hours
#>

param (
    [string]$Region = "ap-south-1",
    [string]$RepoName = "ai-job-finder",
    [string]$FunctionName = "ai-job-finder-cron",
    [string]$ScheduleExpression = "cron(0 2,10,18 * * ? *)"
)

# Ensure AWS CLI is found in PATH
if (Test-Path "C:\Program Files\Amazon\AWSCLIV2") {
    $env:PATH = "C:\Program Files\Amazon\AWSCLIV2;" + $env:PATH
}

Write-Host ""
Write-Host "=== AWS Serverless Job Finder Deployer ===" -ForegroundColor Cyan

# 1. Check AWS CLI
try {
    $callerIdentity = aws sts get-caller-identity --output json | ConvertFrom-Json
    $accountId = $callerIdentity.Account
    Write-Host "[OK] AWS CLI Authenticated: Account $accountId in $Region" -ForegroundColor Green
} catch {
    Write-Host "[ERROR] AWS CLI is not authenticated or not installed. Run 'aws configure' first." -ForegroundColor Red
    exit 1
}

# 2. Check Docker
try {
    docker --version | Out-Null
    Write-Host "[OK] Docker is installed and running." -ForegroundColor Green
} catch {
    Write-Host "[ERROR] Docker is not running. Please start Docker Desktop and retry." -ForegroundColor Red
    exit 1
}

$ecrUri = "$accountId.dkr.ecr.$Region.amazonaws.com/$RepoName"

# 3. Create ECR repository if not exists
Write-Host ""
Write-Host "Checking ECR repository: $RepoName..." -ForegroundColor Yellow
aws ecr describe-repositories --repository-names $RepoName --region $Region 2>$null | Out-Null
if ($LASTEXITCODE -ne 0) {
    Write-Host "Creating private ECR repository $RepoName..." -ForegroundColor Yellow
    aws ecr create-repository --repository-name $RepoName --region $Region --image-scanning-configuration scanOnPush=true | Out-Null
}
Write-Host "[OK] ECR Repository Ready: $ecrUri" -ForegroundColor Green

# 4. Authenticate Docker with ECR
Write-Host ""
Write-Host "Logging in Docker to ECR..." -ForegroundColor Yellow
aws ecr get-login-password --region $Region | docker login --username AWS --password-stdin "$accountId.dkr.ecr.$Region.amazonaws.com"

# 5. Build and tag Docker image
Write-Host ""
Write-Host "Building Lambda container image from Dockerfile.lambda..." -ForegroundColor Yellow
docker build -t "$RepoName`:latest" -f Dockerfile.lambda .
docker tag "$RepoName`:latest" "$ecrUri`:latest"

# 6. Push to ECR
Write-Host ""
Write-Host "Pushing image to Amazon ECR..." -ForegroundColor Yellow
docker push "$ecrUri`:latest"

# 7. Create or Update IAM Execution Role
$roleName = "ai-job-finder-lambda-role"
$roleArn = ""

try {
    $roleInfo = aws iam get-role --role-name $roleName --output json 2>$null | ConvertFrom-Json
    $roleArn = $roleInfo.Role.Arn
    Write-Host ""
    Write-Host "[OK] Using existing IAM Role: $roleArn" -ForegroundColor Green
} catch {
    Write-Host ""
    Write-Host "Creating IAM Role for Lambda: $roleName..." -ForegroundColor Yellow
    $trustPolicy = '{"Version":"2012-10-17","Statement":[{"Effect":"Allow","Principal":{"Service":"lambda.amazonaws.com"},"Action":"sts:AssumeRole"}]}'
    $newRole = aws iam create-role --role-name $roleName --assume-role-policy-document $trustPolicy --output json | ConvertFrom-Json
    $roleArn = $newRole.Role.Arn
    aws iam attach-role-policy --role-name $roleName --policy-arn "arn:aws:iam::aws:policy/service-role/AWSLambdaBasicExecutionRole"
    Write-Host "Waiting 10s for IAM role replication..." -ForegroundColor Gray
    Start-Sleep -Seconds 10
}

# 8. Create or Update Lambda Function
Write-Host ""
Write-Host "Configuring AWS Lambda function: $FunctionName..." -ForegroundColor Yellow
aws lambda get-function --function-name $FunctionName --region $Region 2>$null | Out-Null
if ($LASTEXITCODE -eq 0) {
    Write-Host "Updating existing Lambda function code..." -ForegroundColor Yellow
    aws lambda update-function-code --function-name $FunctionName --image-uri "$ecrUri`:latest" --region $Region | Out-Null
} else {
    Write-Host "Creating new Lambda function from container image..." -ForegroundColor Yellow
    aws lambda create-function `
        --function-name $FunctionName `
        --package-type Image `
        --code ImageUri="$ecrUri`:latest" `
        --role $roleArn `
        --timeout 120 `
        --memory-size 512 `
        --region $Region | Out-Null
}

# 9. Sync environment variables from backend/.env via JSON file
Write-Host "Syncing environment variables from backend/.env..." -ForegroundColor Yellow
$envVars = @{}
if (Test-Path "backend\.env") {
    Get-Content "backend\.env" | ForEach-Object {
        $line = $_.Trim()
        if ($line -and -not $line.StartsWith("#") -and $line.Contains("=")) {
            $parts = $line.Split("=", 2)
            $k = $parts[0].Trim()
            $v = $parts[1].Trim()
            if ($k -and $v) {
                $envVars[$k] = $v
            }
        }
    }
}

if ($envVars.Count -gt 0) {
    $envConfig = @{ Variables = $envVars }
    $tempFile = [System.IO.Path]::GetTempFileName()
    $envConfig | ConvertTo-Json -Depth 5 | Set-Content -Path $tempFile -Encoding utf8
    aws lambda update-function-configuration --function-name $FunctionName --environment "file://$tempFile" --region $Region | Out-Null
    Remove-Item $tempFile -ErrorAction SilentlyContinue
    Write-Host "[OK] Environment variables synced to Lambda." -ForegroundColor Green
}

Write-Host "[OK] Lambda Function Configured successfully!" -ForegroundColor Green

# 10. Configure Amazon EventBridge Rule (Every 8 Hours)
$ruleName = "ai-job-finder-8hr-schedule"
Write-Host ""
Write-Host "Setting up Amazon EventBridge Schedule ($ScheduleExpression)..." -ForegroundColor Yellow

aws events put-rule `
    --name $ruleName `
    --schedule-expression $ScheduleExpression `
    --description "Triggers AI Job Finder every 8 hours" `
    --region $Region | Out-Null

$lambdaArn = (aws lambda get-function --function-name $FunctionName --region $Region --output json | ConvertFrom-Json).Configuration.FunctionArn

# Add permission for EventBridge to invoke Lambda
aws lambda add-permission `
    --function-name $FunctionName `
    --statement-id "EventBridgeInvoke-$ruleName" `
    --action "lambda:InvokeFunction" `
    --principal "events.amazonaws.com" `
    --source-arn (aws events describe-rule --name $ruleName --region $Region --output json | ConvertFrom-Json).Arn `
    --region $Region 2>$null | Out-Null

# Set Lambda as Target
aws events put-targets `
    --rule $ruleName `
    --targets "Id"="1","Arn"="$lambdaArn" `
    --region $Region | Out-Null

Write-Host "[OK] EventBridge Rule configured and linked to Lambda!" -ForegroundColor Green

Write-Host ""
Write-Host "==========================================" -ForegroundColor Green
Write-Host "DEPLOYMENT COMPLETE! Your pipeline is LIVE." -ForegroundColor Green
Write-Host "Schedule: Automatically runs every 8 hours." -ForegroundColor Green
Write-Host "==========================================" -ForegroundColor Green
Write-Host ""
Write-Host "Testing live invocation on AWS Lambda right now..." -ForegroundColor Cyan
aws lambda invoke --function-name $FunctionName --region $Region lambda_response.json
Write-Host "Lambda test invocation finished. Results saved in lambda_response.json" -ForegroundColor Green
