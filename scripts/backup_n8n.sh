#!/bin/bash
# ─────────────────────────────────────────────────────────────────────────────
# Backup do banco de dados e workflows do n8n
# Uso: ./backup_n8n.sh [--restore <backup_file>] [--schedule]
# ─────────────────────────────────────────────────────────────────────────────

set -euo pipefail

BACKUP_DIR="${BACKUP_DIR:-.}"
VOLUME_NAME="autojuri_n8n_data"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)
BACKUP_FILE="$BACKUP_DIR/n8n_backup_$TIMESTAMP.tar.gz"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

log_info() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

log_warn() {
    echo -e "${YELLOW}[WARN]${NC} $1"
}

log_error() {
    echo -e "${RED}[ERROR]${NC} $1" >&2
}

# Verificar se Docker está rodando
check_docker() {
    if ! docker ps &>/dev/null; then
        log_error "Docker não está rodando. Inicie o Docker e tente novamente."
        exit 1
    fi
}

# Fazer backup
backup() {
    check_docker
    
    log_info "Iniciando backup do volume $VOLUME_NAME..."
    
    if ! docker volume ls | grep -q "$VOLUME_NAME"; then
        log_error "Volume $VOLUME_NAME não encontrado."
        exit 1
    fi
    
    mkdir -p "$BACKUP_DIR"
    
    log_info "Criando arquivo comprimido: $BACKUP_FILE"
    docker run --rm \
        -v "$VOLUME_NAME:/data" \
        -v "$BACKUP_DIR:/backup" \
        busybox tar czf "/backup/$(basename $BACKUP_FILE)" -C /data .
    
    if [ -f "$BACKUP_FILE" ]; then
        SIZE=$(du -h "$BACKUP_FILE" | cut -f1)
        log_info "Backup concluído com sucesso!"
        log_info "Arquivo: $BACKUP_FILE ($SIZE)"
        echo "$BACKUP_FILE"
    else
        log_error "Falha ao criar arquivo de backup."
        exit 1
    fi
}

# Restaurar backup
restore() {
    local backup_file="$1"
    
    if [ ! -f "$backup_file" ]; then
        log_error "Arquivo de backup não encontrado: $backup_file"
        exit 1
    fi
    
    check_docker
    
    log_warn "ATENÇÃO: Esta operação irá SUBSTITUIR os dados atuais do n8n!"
    read -p "Continuar com a restauração? (s/n): " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Ss]$ ]]; then
        log_info "Restauração cancelada."
        exit 0
    fi
    
    log_info "Parando container n8n..."
    docker compose stop n8n || true
    
    log_info "Removendo volume atual..."
    docker volume rm "$VOLUME_NAME" || true
    
    log_info "Recreando volume..."
    docker volume create "$VOLUME_NAME"
    
    log_info "Restaurando dados do backup..."
    docker run --rm \
        -v "$VOLUME_NAME:/data" \
        -v "$(dirname $backup_file):/backup" \
        busybox tar xzf "/backup/$(basename $backup_file)" -C /data
    
    log_info "Iniciando container n8n..."
    docker compose start n8n
    
    # Aguardar health check
    log_info "Aguardando n8n ficar healthy..."
    for i in {1..30}; do
        if docker compose ps n8n | grep -q healthy; then
            log_info "Restauração concluída com sucesso!"
            exit 0
        fi
        sleep 2
    done
    
    log_warn "n8n não ficou healthy dentro do tempo limite. Verifique os logs com: docker compose logs n8n"
}

# Agendar backup automaticamente (cron)
schedule_backup() {
    CRON_TIME="${CRON_TIME:-0 2 * * *}"  # 02:00 todos os dias por padrão
    SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/backup_n8n.sh"
    
    log_info "Adicionando backup agendado ao crontab..."
    
    (crontab -l 2>/dev/null || echo "") | grep -v "backup_n8n.sh" | {
        cat
        echo "$CRON_TIME BACKUP_DIR=/backups/n8n $SCRIPT_PATH >> /var/log/n8n_backup.log 2>&1"
    } | crontab -
    
    log_info "Backup agendado para: $CRON_TIME"
    log_info "Logs em: /var/log/n8n_backup.log"
}

# Listar backups disponíveis
list_backups() {
    if [ ! -d "$BACKUP_DIR" ]; then
        log_info "Nenhum backup encontrado em $BACKUP_DIR"
        exit 0
    fi
    
    log_info "Backups disponíveis em $BACKUP_DIR:"
    find "$BACKUP_DIR" -name "n8n_backup_*.tar.gz" -type f -printf "%T+ %p\n" | sort -r | while read -r date file; do
        size=$(du -h "$file" | cut -f1)
        echo "  $(basename $file) ($size) - $date"
    done
}

# Limpar backups antigos
cleanup_old_backups() {
    local days="${1:-30}"
    
    log_info "Limpando backups com mais de $days dias..."
    
    find "$BACKUP_DIR" -name "n8n_backup_*.tar.gz" -type f -mtime +$days -delete
    
    log_info "Limpeza concluída."
}

# Menu principal
main() {
    if [ $# -eq 0 ]; then
        backup
    else
        case "$1" in
            --restore)
                if [ $# -lt 2 ]; then
                    log_error "Uso: $0 --restore <arquivo_backup>"
                    exit 1
                fi
                restore "$2"
                ;;
            --list)
                list_backups
                ;;
            --cleanup)
                cleanup_old_backups "${2:-30}"
                ;;
            --schedule)
                schedule_backup
                ;;
            --help|-h)
                cat << EOF
Uso: $0 [OPCAO]

Opcoes:
  (sem opcao)      Criar novo backup
  --restore FILE   Restaurar de um arquivo de backup
  --list           Listar backups disponíveis
  --cleanup DAYS   Remover backups com mais de DAYS dias (padrão: 30)
  --schedule       Agendar backup automático via cron (diariamente às 02:00)
  --help, -h       Mostrar esta mensagem

Exemplos:
  $0                                    # Fazer backup agora
  $0 --list                            # Listar backups disponíveis
  $0 --restore ./n8n_backup_20260528.tar.gz  # Restaurar backup específico
  $0 --cleanup 7                       # Remover backups com mais de 7 dias

Variáveis de ambiente:
  BACKUP_DIR       Diretório para armazenar backups (padrão: .)
  CRON_TIME        Tempo cron para backup agendado (padrão: 0 2 * * *)

EOF
                exit 0
                ;;
            *)
                log_error "Opção desconhecida: $1"
                echo "Use '$0 --help' para ver as opções disponíveis."
                exit 1
                ;;
        esac
    fi
}

main "$@"
