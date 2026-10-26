param(
    [Parameter(Mandatory = $true)]
    [string]$HostName,
    [string]$UserName = "root",
    [int]$Port = 22,
    [string]$KeyPath = "",
    [string]$RemotePackage = "/tmp/joker_qq_admin_release"
)

$ErrorActionPreference = "Stop"
$root = (Resolve-Path (Join-Path $PSScriptRoot "..")).Path

if (-not (Get-Command ssh -ErrorAction SilentlyContinue)) {
    throw "未找到 ssh，请先安装 OpenSSH Client。"
}
if (-not (Get-Command scp -ErrorAction SilentlyContinue)) {
    throw "未找到 scp，请先安装 OpenSSH Client。"
}

$sshOptions = @("-p", $Port.ToString())
$scpOptions = @("-P", $Port.ToString())
if ($KeyPath) {
    $resolvedKey = (Resolve-Path -LiteralPath $KeyPath).Path
    $sshOptions += @("-i", $resolvedKey)
    $scpOptions += @("-i", $resolvedKey)
}

$target = "$UserName@$HostName"
& ssh @sshOptions $target "mkdir -p '$RemotePackage'"

$items = @("README.md", ".env.example", ".gitignore", "requirements.txt", "run.py", "api.py", "app.py", "config.py", "dashboard.py", "gateway.py", "storage.py", "webhook.py", "features", "deploy")
foreach ($item in $items) {
    $source = Join-Path $root $item
    & scp @scpOptions -r $source "$target`:$RemotePackage/"
}

& ssh @sshOptions $target "cd '$RemotePackage' && JOKER_QQ_ADMIN_DIR=/www/wwwroot/joker_qq_admin bash deploy/install.sh"
Write-Host "程序已上传并执行 Linux 安装脚本。请在服务器配置 /etc/joker_qq_admin/joker_qq_admin.env 后再次执行安装脚本。"
