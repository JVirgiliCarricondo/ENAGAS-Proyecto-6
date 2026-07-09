# setup.ps1 - crea/actualiza el entorno del prototipo y verifica que esta completo.
# Uso (desde la carpeta proyecto/):  .\setup.ps1
# Idempotente: se puede relanzar tras cada `git pull` sin romper nada.
$ErrorActionPreference = "Stop"

$proyecto = $PSScriptRoot
$venvPython = Join-Path $proyecto ".venv\Scripts\python.exe"

# 1. Crear el entorno virtual si no existe (Python 3.10, ver .python-version)
if (-not (Test-Path $venvPython)) {
    Write-Host "Creando entorno virtual en proyecto\.venv ..."
    python -m venv (Join-Path $proyecto ".venv")
} else {
    Write-Host "Entorno virtual proyecto\.venv ya existe."
}

# 2. Instalar las dependencias pineadas
Write-Host "Instalando dependencias de requirements.txt ..."
& $venvPython -m pip install -r (Join-Path $proyecto "requirements.txt")
if ($LASTEXITCODE -ne 0) { throw "pip install fallo (codigo $LASTEXITCODE)." }

# 3. Activar los hooks de git versionados (.githooks): tras cada `git pull`
#    que cambie requirements.txt, el entorno se actualiza solo (post-merge).
git -C $proyecto config core.hooksPath .githooks
if ($LASTEXITCODE -eq 0) { Write-Host "Hooks de git activados (core.hooksPath = .githooks)." }

# 4. Verificar que todo importa
Write-Host ""
Write-Host "Verificando el entorno ..."
& $venvPython (Join-Path $proyecto "check_entorno.py")
if ($LASTEXITCODE -ne 0) { throw "El entorno esta incompleto (ver lineas FALTA)." }

Write-Host ""
Write-Host "Listo. Activa el entorno con:  .venv\Scripts\Activate.ps1"
Write-Host "Y arranca la app con:          streamlit run src\app\streamlit_app.py"
