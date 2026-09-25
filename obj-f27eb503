# Test 405 fix for lock-password and permissions endpoints

$baseUrl = "http://127.0.0.1:8000/api/v1/roles"

# Login
$loginBody = @{ username = "admin"; password = "admin123" } | ConvertTo-Json
$loginResponse = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8000/api/v1/auth/login" -Body $loginBody -ContentType "application/json"
$token = $loginResponse.access_token
Write-Host "Token: $token"

# Test lock-password endpoint
$headers = @{ Authorization = "Bearer $token"; "Content-Type" = "application/json" }
$body = @{ password = "testpassword123" } | ConvertTo-Json

try {
    $response = Invoke-RestMethod -Method Post -Uri "$baseUrl/lock-password" -Headers $headers -Body $body -ContentType "application/json"
    Write-Host "lock-password: SUCCESS" -ForegroundColor Green
    Write-Host ($response | ConvertTo-Json -Depth 3)
} catch {
    Write-Host "lock-password: ERROR - $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        Write-Host "Response: $body"
        Write-Host "Status: $($_.Exception.Response.StatusCode)"
    }
}

# Test permissions endpoint
$permBody = @{ feature_key = "test.module"; description = "Test permission" } | ConvertTo-Json
try {
    $response = Invoke-RestMethod -Method Post -Uri "$baseUrl/permissions" -Headers $headers -Body $permBody -ContentType "application/json"
    Write-Host "permissions: SUCCESS" -ForegroundColor Green
    Write-Host ($response | ConvertTo-Json -Depth 3)
} catch {
    Write-Host "permissions: ERROR - $($_.Exception.Message)" -ForegroundColor Red
    if ($_.Exception.Response) {
        $stream = $_.Exception.Response.GetResponseStream()
        $reader = New-Object System.IO.StreamReader($stream)
        $body = $reader.ReadToEnd()
        Write-Host "Response: $body"
        Write-Host "Status: $($_.Exception.Response.StatusCode)"
    }
}