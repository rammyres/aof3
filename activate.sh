#!/bin/bash

# ==========================================
# CONFIGURAÇÕES DO SERVIÇO
# ==========================================
SERVICE_NAME="aof3"
SERVICE_DESC="Serviço Flask - AOF3"
WORK_DIR="/home/ubuntu/code/aof3"
VENV_DIR="${WORK_DIR}/venv"
EXEC_COMMAND="${VENV_DIR}/bin/python3 app.py" 

RUN_AS_USER="ubuntu"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo "=== Garantindo dependências do sistema ==="
sudo apt-get update && sudo apt-get install -y python3-venv python3-pip

echo "=== Configurando o Ambiente Virtual (venv) ==="
if [ ! -d "$VENV_DIR" ]; then
    echo "Criando o ambiente virtual em $VENV_DIR..."
    python3 -m venv "$VENV_DIR"
else
    echo "Ambiente virtual já existe."
fi

echo "=== Ativando venv e instalando requirements.txt ==="
# Ativa o venv no contexto deste script script
source "${VENV_DIR}/bin/activate"

# Atualiza o pip e instala os pacotes
pip install --upgrade pip
if [ -f "${WORK_DIR}/requirements.txt" ]; then
    echo "Instalando dependências do requirements.txt..."
    pip install -r "${WORK_DIR}/requirements.txt"
else
    echo "AVISO: requirements.txt não encontrado em ${WORK_DIR}."
fi

# Desativa o venv para o restante do script shell
deactivate

echo "=== Criando arquivo de serviço do systemd ==="
sudo bash -c "cat > ${SERVICE_FILE}" <<EOF
[Unit]
Description=${SERVICE_DESC}
After=network.target

[Service]
Type=simple
User=${RUN_AS_USER}
WorkingDirectory=${WORK_DIR}
ExecStart=${EXEC_COMMAND}
Restart=always
RestartSec=5
StandardOutput=syslog
StandardError=syslog
SyslogIdentifier=${SERVICE_NAME}

# Variáveis de ambiente úteis para o Flask
Environment=FLASK_ENV=development
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=multi-user.target
EOF

echo "Arquivo de serviço criado em: ${SERVICE_FILE}"

echo "=== Ativando e iniciando o serviço ==="
sudo systemctl daemon-reload
sudo systemctl enable ${SERVICE_NAME}.service
sudo systemctl start ${SERVICE_NAME}.service

echo "=== Status do serviço ==="
sudo systemctl status ${SERVICE_NAME}.service