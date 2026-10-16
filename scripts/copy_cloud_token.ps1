[CmdletBinding(DefaultParameterSetName='Copy')]
param(
    [ValidatePattern('^[A-Za-z0-9][A-Za-z0-9_-]*$')][string]$App = 'sensevoice-asr',
    [string]$ServiceName = 'sensevoice-xsuaa',
    [Parameter(ParameterSetName='Check')][switch]$CheckOnly,
    [Parameter(ParameterSetName='Show')][switch]$ShowToken,
    [Parameter(ParameterSetName='Return')][switch]$PassThru
)
$ErrorActionPreference = 'Stop'
$taskProject = Split-Path $PSScriptRoot -Parent
$taskSession = Join-Path $taskProject ('.cache\token-session-' + [guid]::NewGuid().ToString('N'))
$taskConfigDirectory = Join-Path $taskSession '.cf'
$taskConfig = Join-Path $taskConfigDirectory 'config.json'
$taskOriginalCfHome = $env:CF_HOME
$taskSourceHome = if ($env:CF_HOME) { $env:CF_HOME } else { $env:USERPROFILE }
try {
    $taskCf = (Get-Command cf -ErrorAction Stop).Source
    $taskSource = Join-Path $taskSourceHome '.cf\config.json'
    $taskTarget = Get-Content -LiteralPath $taskSource -Raw | ConvertFrom-Json
    if (-not $taskTarget.Target -or -not $taskTarget.SpaceFields.GUID) {
        throw 'Use cf login and cf target to select your application space first.'
    }
    New-Item -ItemType Directory -Force $taskConfigDirectory | Out-Null
    Copy-Item -LiteralPath $taskSource -Destination $taskConfig
    $env:CF_HOME = $taskSession
    $taskGuid = & $taskCf app $App --guid 2>$null
    if ($LASTEXITCODE -ne 0 -or [string]$taskGuid -notmatch '^[0-9a-fA-F-]{36}$') {
        throw 'Application not found in the currently targeted space.'
    }
    $taskRaw = & $taskCf curl ('/v3/apps/' + $taskGuid.Trim() + '/env') 2>$null
    if ($LASTEXITCODE -ne 0) { throw 'CF 登录已失效，请先重新登录。' }
    $taskBinding = ($taskRaw | ConvertFrom-Json).system_env_json.VCAP_SERVICES.xsuaa |
        Where-Object { $_.name -eq $ServiceName }
    if (@($taskBinding).Count -ne 1) { throw '未找到本项目的 XSUAA 服务绑定。' }
    $taskCredentials = $taskBinding.credentials
    $taskTokenUri = $taskCredentials.url.TrimEnd('/') + '/oauth/token'
    $taskParsedUri = [uri]$taskTokenUri
    if (-not $taskParsedUri.IsAbsoluteUri -or $taskParsedUri.Scheme -ne 'https' -or
        $taskParsedUri.UserInfo -or $taskParsedUri.Query -or $taskParsedUri.Fragment) {
        throw 'The XSUAA binding must provide a valid HTTPS URL.'
    }
    $taskBasic = [Convert]::ToBase64String([Text.Encoding]::UTF8.GetBytes(
        $taskCredentials.clientid + ':' + $taskCredentials.clientsecret))
    $taskResponse = Invoke-RestMethod -Uri $taskTokenUri -Method Post -TimeoutSec 60 -MaximumRedirection 0 `
        -Headers @{Authorization=('Basic ' + $taskBasic)} `
        -ContentType 'application/x-www-form-urlencoded' -Body 'grant_type=client_credentials'
    if (-not $taskResponse.access_token) { throw 'XSUAA 未返回访问令牌。' }
    $taskExpires = (Get-Date).AddSeconds([int]$taskResponse.expires_in).ToString('HH:mm:ss')
    if ($CheckOnly) {
        Write-Host ('令牌获取验证通过，有效至本机时间 ' + $taskExpires + '；未写入剪贴板。')
    } elseif ($PassThru) {
        Write-Output ([string]$taskResponse.access_token)
    } else {
        Set-Clipboard -Value ([string]$taskResponse.access_token)
        Write-Host ('令牌已复制到剪贴板，有效至本机时间 ' + $taskExpires + '。')
        if ($ShowToken) {
            Write-Host 'access_token（完整的一行）：'
            Write-Host ([string]$taskResponse.access_token)
        }
        Write-Host ('打开你部署的 ' + $App + ' 应用地址。')
        Write-Host '点击“访问令牌”输入框，按 Ctrl+V，然后点击“识别文件”或“开始录音”。'
        Write-Host '直接粘贴即可，不加 Bearer 前缀。过期后重新运行本脚本。'
    }
} catch {
    Write-Host '获取令牌失败。请确认已登录应用所在的 CF 空间，且 App / ServiceName 参数正确，并能访问网络。' -ForegroundColor Red
    exit 1

} finally {
    $env:CF_HOME = $taskOriginalCfHome
    if (Test-Path -LiteralPath $taskConfig) { [IO.File]::Delete($taskConfig) }
    $taskPluginDirectory = Join-Path $taskConfigDirectory 'plugins'
    foreach ($taskDirectory in @($taskPluginDirectory, $taskConfigDirectory, $taskSession)) {
        if ([IO.Directory]::Exists($taskDirectory) -and
            [IO.Directory]::GetFileSystemEntries($taskDirectory).Length -eq 0) {
            [IO.Directory]::Delete($taskDirectory)
        }
    }
    $taskRaw = $null; $taskBinding = $null; $taskCredentials = $null
    $taskBasic = $null; $taskResponse = $null
}
