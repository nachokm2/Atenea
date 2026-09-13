<#
.SYNOPSIS
    Envoltorio de la CLI de Railway para Windows.

.DESCRIPTION
    Existe por un detalle que cuesta media hora descubrir. El paquete `railway`
    de npm, que es el que evalua `.railway/railway.ts`, comprueba la version de
    la CLI ejecutando lo que encuentre en la variable de entorno `_`, y si no la
    encuentra prueba con `railway` a secas. En Windows eso no resuelve a ningun
    ejecutable, porque lo que hay instalado es `railway.ps1` y `railway.cmd`, asi
    que la comprobacion falla y responde que la CLI es demasiado vieja aunque
    este al dia.

    Este envoltorio apunta `_` al `railway.exe` de verdad y le pasa los
    argumentos tal cual.

.EXAMPLE
    .\scripts\railway.ps1 config plan
    .\scripts\railway.ps1 config apply
#>
[CmdletBinding()]
param([Parameter(ValueFromRemainingArguments = $true)][string[]]$Argumentos)

$candidatos = @(
    "$env:APPDATA\npm\node_modules\@railway\cli\bin\railway.exe",
    "$env:LOCALAPPDATA\Programs\railway\railway.exe",
    "$env:USERPROFILE\.railway\bin\railway.exe"
)
$exe = $candidatos | Where-Object { Test-Path $_ } | Select-Object -First 1
if (-not $exe) {
    throw "No encuentro railway.exe. Instala la CLI con: npm i -g @railway/cli"
}

$env:_ = $exe
& $exe @Argumentos
exit $LASTEXITCODE
