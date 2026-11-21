#!/usr/bin/env bash
# Deploys the Nexus agents and skills (ai-tools/) into ~/.claude through symbolic links.
#
#   skills/<name>/     → ~/.claude/skills/<name>
#   agents/<name>.md   → ~/.claude/agents/<name>.md
#
# A change in the repository takes effect at once: the script only needs to be run again
# for a new skill or agent, or after removing one.
#
# The script never replaces a folder or a file that is not a link to the repository:
# it reports it, and David decides. It only removes dead links that pointed to the
# repository (skill or agent deleted from the repository).
#
# Usage: ai-tools/deploy.sh [--essai]
#   --essai   shows what would be done, without changing anything.
# CLAUDE_DIR replaces ~/.claude (useful to test the script).

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

# Runs the command, or only prints it in dry-run mode.
faire() {
	if $essai; then
		echo "  (essai) $*"
	else
		"$@"
	fi
}

# Creates the link $2 → $1, unless $2 already exists and is not a link to the repository.
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

# Removes from $1 the dead links that pointed to the repository.
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
