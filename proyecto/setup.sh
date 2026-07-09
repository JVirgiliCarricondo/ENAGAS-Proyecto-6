#!/usr/bin/env bash
# setup.sh - crea/actualiza el entorno del prototipo y verifica que esta completo.
# Uso (desde la carpeta proyecto/):  bash setup.sh
# Idempotente: se puede relanzar tras cada `git pull` sin romper nada.
set -euo pipefail

proyecto="$(cd "$(dirname "$0")" && pwd)"
venv_python="$proyecto/.venv/bin/python"

# 1. Crear el entorno virtual si no existe (Python 3.10, ver .python-version)
if [ ! -x "$venv_python" ]; then
    echo "Creando entorno virtual en proyecto/.venv ..."
    python3 -m venv "$proyecto/.venv"
else
    echo "Entorno virtual proyecto/.venv ya existe."
fi

# 2. Instalar las dependencias pineadas
echo "Instalando dependencias de requirements.txt ..."
"$venv_python" -m pip install -r "$proyecto/requirements.txt"

# 3. Activar los hooks de git versionados (.githooks): tras cada `git pull`
#    que cambie requirements.txt, el entorno se actualiza solo (post-merge).
git -C "$proyecto" config core.hooksPath .githooks && \
    echo "Hooks de git activados (core.hooksPath = .githooks)."
chmod +x "$proyecto/../.githooks/"* 2>/dev/null || true

# 4. Verificar que todo importa
echo ""
echo "Verificando el entorno ..."
"$venv_python" "$proyecto/check_entorno.py"

echo ""
echo "Listo. Activa el entorno con:  source .venv/bin/activate"
echo "Y arranca la app con:          streamlit run src/app/streamlit_app.py"
