#!/usr/bin/env bash
# ─────────────────────────────────────────────────────────────────────────────
# AutoJuri — abre 80/443 no iptables da instancia Oracle Cloud (Ubuntu ARM).
#
# GOTCHA nº1 do Oracle: as portas ficam bloqueadas em DUAS camadas.
#   (1) Security List / NSG da VCN  -> abra 80 e 443 no console OCI (manual).
#   (2) iptables da propria VM       -> a imagem Ubuntu do Oracle so libera 22 e
#       tem um REJECT no fim. ESTE script cuida da camada (2).
#
# Sem os dois, o Caddy sobe mas voce ve "connection refused" de fora.
#
# Uso (no VPS Oracle):
#   bash scripts/deploy/oracle_open_ports.sh
# ─────────────────────────────────────────────────────────────────────────────
set -euo pipefail

for p in 80 443; do
	if sudo iptables -C INPUT -p tcp --dport "$p" -j ACCEPT 2>/dev/null; then
		echo "[oracle] porta $p ja liberada no iptables."
		continue
	fi
	# Insere o ACCEPT ANTES da 1a regra REJECT/DROP do INPUT (senao o REJECT do
	# Oracle vence). Se nao houver REJECT, faz append.
	line="$(sudo iptables -L INPUT --line-numbers -n | awk '/REJECT|DROP/{print $1; exit}')"
	if [[ -n "${line:-}" ]]; then
		sudo iptables -I INPUT "$line" -p tcp --dport "$p" -j ACCEPT
	else
		sudo iptables -A INPUT -p tcp --dport "$p" -j ACCEPT
	fi
	echo "[oracle] porta $p liberada."
done

# Persiste as regras (senao somem no reboot).
if ! command -v netfilter-persistent >/dev/null 2>&1; then
	echo "[oracle] instalando iptables-persistent..."
	sudo DEBIAN_FRONTEND=noninteractive apt-get update
	sudo DEBIAN_FRONTEND=noninteractive apt-get install -y iptables-persistent
fi
sudo netfilter-persistent save

echo "[oracle] regras persistidas. Confira com: sudo iptables -L INPUT -n --line-numbers"
echo "[oracle] LEMBRE: abra 80 e 443 TAMBEM na Security List da VCN (console OCI)."
