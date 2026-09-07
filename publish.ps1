<#
publish.ps1

Inicializa el repo local, hace commit y push al remoto GitHub y opcionalmente añade secrets.

Uso:
  .\publish.ps1                      # usa repo por defecto naimmeliana-prog/antigmac
  .\publish.ps1 -Repo "owner/repo" -Branch main
  .\publish.ps1 -SetSecrets         # pedirá los valores y los guardará con `gh secret set`

Requisitos:
 - `git` instalado
 - (Opcional) `gh` CLI autenticado si usas `-SetSecrets`
#>

param(
    [string]$Repo = 'naimmeliana-prog/antigmac',
    [string]$Branch = 'main',
    [switch]$SetSecrets
)

function Run-Git([string]$args) {
    Write-Host "git $args"
    git $args
}

if (-not (Test-Path .git)) {
    Write-Host 'Inicializando repositorio git...'
    Run-Git "init"
    Run-Git "checkout -b $Branch"
} else {
    Write-Host 'Repositorio git ya inicializado.'
    Run-Git "checkout $Branch" 2>$null
}

Write-Host 'Añadiendo y comiteando cambios...'
Run-Git 'add .'
try {
    Run-Git 'commit -m "Initial import: MacToXtreamAntig"'
} catch {
    Write-Host 'No changes to commit or commit failed (continuando)'
}

$remoteUrl = "https://github.com/$Repo.git"
try {
    $existing = git remote get-url origin 2>$null
    if ($existing) {
        Write-Host "Actualizando remote origin -> $remoteUrl"
        Run-Git "remote set-url origin $remoteUrl"
    }
} catch {
    Write-Host "Añadiendo remote origin -> $remoteUrl"
    Run-Git "remote add origin $remoteUrl"
}

Write-Host "Empujando a origin/$Branch..."
Run-Git "push -u origin $Branch"

if ($SetSecrets) {
    Write-Host "Configurando secrets via gh CLI (asegúrate de haber hecho 'gh auth login')"
    if (-not (Get-Command gh -ErrorAction SilentlyContinue)) {
        Write-Error "No se encontró 'gh' CLI. Instálalo e inténtalo de nuevo."
        exit 1
    }

    $cfApi = Read-Host 'CF_API_TOKEN (pegar aquí)'
    $cfAccount = Read-Host 'CF_ACCOUNT_ID (pegar aquí)'
    $portalUrl = Read-Host 'PORTAL_URL (ej: http://mag.greatott.me:80/c/)'
    $portalMac = Read-Host 'PORTAL_MAC (ej: 00:1A:79:74:B1:B9)'

    Write-Host 'Guardando secrets en GitHub...'
    gh secret set CF_API_TOKEN -b"$cfApi" -R $Repo
    gh secret set CF_ACCOUNT_ID -b"$cfAccount" -R $Repo
    gh secret set PORTAL_URL -b"$portalUrl" -R $Repo
    gh secret set PORTAL_MAC -b"$portalMac" -R $Repo

    Write-Host 'Secrets guardados.'
}

Write-Host 'Hecho.'
