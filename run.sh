#!/bin/bash

# Exit on error
set -e

echo "=========================================================="
echo "    Iniciador de Dashboard de Sensores Tuya / SmartLife    "
echo "=========================================================="
echo ""

# Check for Python 3
if ! command -v python3 &> /dev/null; then
    echo "❌ Error: Python 3 no está instalado. Por favor instala Python 3 para continuar."
    exit 1
fi

# Create virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "📦 Creando entorno virtual de Python (venv)..."
    python3 -m venv venv
    echo "✅ Entorno virtual creado con éxito."
fi

# Activate virtual environment
echo "🔌 Activando entorno virtual..."
source venv/bin/activate

# Upgrade pip
echo "🔄 Actualizando pip..."
pip install --upgrade pip

# Install requirements
echo "📥 Instalando dependencias de requirements.txt..."
pip install -r requirements.txt
echo "✅ Dependencias instaladas con éxito."

echo ""
echo "🚀 Iniciando el servidor del Dashboard..."
echo "--------------------------------------------------------"
echo "El servidor estará corriendo en: http://127.0.0.1:5000"
echo "--------------------------------------------------------"
echo "Presiona Ctrl+C para detener el servidor."
echo ""

# Run the application
python app.py
