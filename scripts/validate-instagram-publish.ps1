param(
    [switch]$CreateOnly,
    [switch]$Publish
)

$ErrorActionPreference = 'Stop'

function Load-EnvFile($Path) {
    if (-not (Test-Path $Path)) { return }
    Get-Content $Path | ForEach-Object {
        $line = $_.Trim()
        if (-not $line -or $line.StartsWith('#')) { return }
        $parts = $line -split '=', 2
        if ($parts.Count -eq 2) {
            [System.Environment]::SetEnvironmentVariable($parts[0].Trim(), $parts[1].Trim())
        }
    }
}

Load-EnvFile (Join-Path $PSScriptRoot '..\.env')

$appId = $env:POST_RELAY_META_APP_ID
$appSecret = $env:POST_RELAY_META_APP_SECRET
$userToken = $env:POST_RELAY_USER_ACCESS_TOKEN
$igAccountId = $env:POST_RELAY_INSTAGRAM_ACCOUNT_ID
$imageUrl = $env:POST_RELAY_TEST_IMAGE_URL
$caption = $env:POST_RELAY_TEST_CAPTION

if (-not $appId -or -not $userToken -or -not $igAccountId) {
    throw 'Missing required env vars. Set POST_RELAY_META_APP_ID, POST_RELAY_USER_ACCESS_TOKEN, and POST_RELAY_INSTAGRAM_ACCOUNT_ID in a local .env file.'
}

if (-not $imageUrl) {
    throw 'Missing POST_RELAY_TEST_IMAGE_URL in local .env file.'
}

$base = 'https://graph.facebook.com/v25.0'

function Invoke-GraphPost($Uri, $Body) {
    try {
        return Invoke-RestMethod -Method Post -Uri $Uri -Body $Body -ContentType 'application/x-www-form-urlencoded'
    }
    catch {
        if ($_.Exception.Response) {
            $reader = New-Object System.IO.StreamReader($_.Exception.Response.GetResponseStream())
            $reader.BaseStream.Position = 0
            $reader.DiscardBufferedData()
            $responseBody = $reader.ReadToEnd()
            throw "Graph API error: $responseBody"
        }
        throw
    }
}

$createUri = "$base/$igAccountId/media"
$createBody = @{
    image_url = $imageUrl
    caption = $(if ($caption) { $caption } else { 'Post Relay validation test' })
    access_token = $userToken
}

Write-Host 'Creating media container...'
$createResult = Invoke-GraphPost -Uri $createUri -Body $createBody
$creationId = $createResult.id

if (-not $creationId) {
    throw 'No creation id returned from media container creation.'
}

Write-Host "Media container created successfully. Creation ID: $creationId"

if ($CreateOnly -or -not $Publish) {
    Write-Host 'Create-only mode complete. No publish attempted.'
    exit 0
}

$publishUri = "$base/$igAccountId/media_publish"
$publishBody = @{
    creation_id = $creationId
    access_token = $userToken
}

Write-Host 'Publishing media container...'
$publishResult = Invoke-GraphPost -Uri $publishUri -Body $publishBody
Write-Host ('Publish result: ' + ($publishResult | ConvertTo-Json -Compress))
