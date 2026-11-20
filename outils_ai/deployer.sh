#!/usr/bin/env bash
# Déploie les agents et skills de Nexus (outils_ai/) dans ~/.claude par liens symboliques.
#
#   skills/<nom>/      → ~/.claude/skills/<nom>
#   agents/<nom>.md    → ~/.claude/agents/<nom>.md
#
# Une modification dans le dépôt est prise en compte tout de suite : on ne relance ce
# script que pour un nouveau skill ou agent, ou après en avoir retiré un.
#
# Le script ne remplace jamais un dossier ou un fichier qui n'est pas un lien vers le
# dépôt : il le signale, et c'est à David de décider. Il retire seulement les liens
# morts qui pointaient vers le dépôt (skill ou agent supprimé du dépôt).
#
# Usage : outils_ai/deployer.sh [--essai]
#   --essai   affiche ce qui serait fait, sans rien changer.
# CLAUDE_DIR remplace ~/.claude (utile pour tester le script).

set -euo pipefail

depot="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
claude_dir="${CLAUDE_DIR:-$HOME/.claude}"
essai=false

case "${1:-}" in
	"") ;;
	--essai) essai=true ;;
	*) echo "Usage : $0 [--essai]" >&2; exit 2 ;;
esac

problemes=0

# Exécute la commande, ou l'affiche seulement en mode essai.
faire() {
	if $essai; then
		echo "  (essai) $*"
	else
		"$@"
	fi
}

# Crée le lien $2 → $1, sauf si $2 existe déjà et n'est pas un lien vers le dépôt.
lier() {
	local source="$1" cible="$2"
	if [[ -L "$cible" ]]; then
		local actuel
		actuel="$(readlink "$cible")"
		if [[ "$actuel" == "$source" ]]; then
			echo "ok      $cible"
			return
		fi
		if [[ "$actuel" == "$depot"/* ]]; then
			echo "relié   $cible (pointait vers $actuel)"
			faire ln -sfn "$source" "$cible"
			return
		fi
		echo "IGNORÉ  $cible : lien vers $actuel, hors du dépôt" >&2
		problemes=$((problemes + 1))
	elif [[ -e "$cible" ]]; then
		echo "IGNORÉ  $cible : existe déjà et n'est pas un lien (à déplacer dans le dépôt ?)" >&2
		problemes=$((problemes + 1))
	else
		echo "nouveau $cible"
		faire ln -s "$source" "$cible"
	fi
}

# Retire de $1 les liens morts qui pointaient vers le dépôt.
nettoyer() {
	local dossier="$1" lien actuel
	for lien in "$dossier"/*; do
		[[ -L "$lien" && ! -e "$lien" ]] || continue
		actuel="$(readlink "$lien")"
		[[ "$actuel" == "$depot"/* ]] || continue
		echo "retiré  $lien (n'existe plus dans le dépôt)"
		faire rm "$lien"
	done
}

faire mkdir -p "$claude_dir/skills" "$claude_dir/agents"

shopt -s nullglob

echo "Skills"
for skill in "$depot"/skills/*/; do
	skill="${skill%/}"
	lier "$skill" "$claude_dir/skills/$(basename "$skill")"
done
[[ -d "$claude_dir/skills" ]] && nettoyer "$claude_dir/skills"

echo "Agents"
for agent in "$depot"/agents/*.md; do
	lier "$agent" "$claude_dir/agents/$(basename "$agent")"
done
[[ -d "$claude_dir/agents" ]] && nettoyer "$claude_dir/agents"

if ((problemes > 0)); then
	echo "$problemes élément(s) ignoré(s), voir ci-dessus." >&2
	exit 1
fi
