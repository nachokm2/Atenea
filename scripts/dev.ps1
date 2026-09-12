<#
.SYNOPSIS
    Comandos habituales de desarrollo de Atenea (Windows / PowerShell).

.DESCRIPTION
    Envoltorio unico para levantar la base de datos, migrar, sembrar, arrancar la API
    o el worker y pasar las pruebas. Todos los comandos de Python se ejecutan desde
    `backend/`, que es donde viven `alembic.ini` y el paquete `app`.

.PARAMETER Command
    Accion a ejecutar. `.\scripts\dev.ps1 help` lista todas.

.EXAMPLE
    .\scripts\dev.ps1 db
    .\scripts\dev.ps1 migrate
    .\scripts\dev.ps1 api
#>
[CmdletBinding()]
param(
    [Parameter(Position = 0)]
    [ValidateSet('help', 'install', 'db', 'db-stop', 'db-reset', 'db-shell',
                 'migrate', 'downgrade', 'revision', 'seed',
                 'api', 'worker', 'test', 'lint', 'format', 'check', 'tables')]
    [string]$Command = 'help',

    [Parameter(Position = 1, ValueFromRemainingArguments = $true)]
    [string[]]$Rest
)

$ErrorActionPreference = 'Stop'

$Root    = Split-Path -Parent $PSScriptRoot
$Backend = Join-Path $Root 'backend'
$Python  = 'python'

function Invoke-Backend {
    param([string]$Exe, [string[]]$Arguments)
    Push-Location $Backend
    try {
        & $Exe @Arguments
        if ($LASTEXITCODE -ne 0) { throw "$Exe $($Arguments -join ' ') fallo con codigo $LASTEXITCODE" }
    }
    finally { Pop-Location }
}

function Show-Help {
    Write-Host ''
    Write-Host 'Atenea - comandos de desarrollo' -ForegroundColor Cyan
    Write-Host '  install    Instala requirements.txt y requirements-dev.txt'
    Write-Host '  db         Levanta PostgreSQL 16 + pgvector (docker compose up -d db)'
    Write-Host '  db-stop    Para los contenedores'
    Write-Host '  db-reset   Borra el volumen de datos y vuelve a levantar la base (DESTRUCTIVO)'
    Write-Host '  db-shell   Abre psql dentro del contenedor atenea-db'
    Write-Host '  migrate    alembic upgrade head'
    Write-Host '  downgrade  alembic downgrade -1  (o `downgrade base`)'
    Write-Host '  revision   alembic revision --autogenerate -m "<mensaje>"'
    Write-Host '  seed       Carga las semillas (python -m app.seeds)'
    Write-Host '  api        uvicorn app.main:app --reload'
    Write-Host '  worker     python -m app.worker'
    Write-Host '  test       pytest -q'
    Write-Host '  lint       ruff check .'
    Write-Host '  format     ruff format . ; ruff check --fix .'
    Write-Host '  check      alembic check (deriva entre modelos y base de datos)'
    Write-Host '  tables     Imprime las tablas de Base.metadata y las de la base real'
    Write-Host ''
}

switch ($Command) {
    'help' { Show-Help }

    'install' {
        Invoke-Backend $Python @('-m', 'pip', 'install', '-r', 'requirements.txt', '-r', 'requirements-dev.txt')
    }

    'db' {
        Push-Location $Root
        try { docker compose up -d db } finally { Pop-Location }
        Write-Host 'Base de datos en postgresql+psycopg://atenea:atenea_dev@localhost:55432/atenea' -ForegroundColor Green
    }

    'db-stop' {
        Push-Location $Root
        try { docker compose down } finally { Pop-Location }
    }

    'db-reset' {
        Write-Warning 'Esto BORRA todos los datos locales de Atenea.'
        Push-Location $Root
        try {
            docker compose down -v
            docker compose up -d db
        } finally { Pop-Location }
        Start-Sleep -Seconds 5
        Invoke-Backend 'alembic' @('upgrade', 'head')
    }

    'db-shell' { docker exec -it atenea-db psql -U atenea -d atenea }

    'migrate'   { Invoke-Backend 'alembic' @('upgrade', 'head') }
    'downgrade' { Invoke-Backend 'alembic' (@('downgrade') + $(if ($Rest) { $Rest } else { @('-1') })) }

    'revision' {
        if (-not $Rest) { throw 'Indica el mensaje: .\scripts\dev.ps1 revision "descripcion del cambio"' }
        Invoke-Backend 'alembic' @('revision', '--autogenerate', '-m', ($Rest -join ' '))
    }

    'seed'   { Invoke-Backend $Python @('-m', 'app.seeds') }
    'api'    { Invoke-Backend 'uvicorn' @('app.main:app', '--reload', '--host', '0.0.0.0', '--port', '8000') }
    'worker' { Invoke-Backend $Python @('-m', 'app.worker') }
    'test'   { Invoke-Backend $Python (@('-m', 'pytest', '-q') + $Rest) }
    'lint'   { Invoke-Backend 'ruff' @('check', '.') }

    'format' {
        Invoke-Backend 'ruff' @('format', '.')
        Invoke-Backend 'ruff' @('check', '--fix', '.')
    }

    'check'  { Invoke-Backend 'alembic' @('check') }

    'tables' {
        Invoke-Backend $Python @('-c', @'
import app.models
from sqlalchemy import create_engine, inspect
from app.core.config import settings
from app.core.db import Base
meta = sorted(Base.metadata.tables)
print(len(meta), "tablas en Base.metadata")
real = sorted(t for t in inspect(create_engine(settings.database_url)).get_table_names() if t != "alembic_version")
print(len(real), "tablas en la base")
falta = set(meta) - set(real)
sobra = set(real) - set(meta)
print("faltan en la base:", sorted(falta) or "ninguna")
print("sobran en la base:", sorted(sobra) or "ninguna")
'@)
    }
}
