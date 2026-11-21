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
# Usage: ai-tools/deploy.sh [--dry-run]
#   --dry-run   shows what would be done, without changing anything.
# CLAUDE_DIR replaces ~/.claude (useful to test the script).

set -euo pipefail

repo="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
claude_dir="${CLAUDE_DIR:-$HOME/.claude}"
dry_run=false

case "${1:-}" in
	"") ;;
	--dry-run) dry_run=true ;;
	*) echo "Usage : $0 [--dry-run]" >&2; exit 2 ;;
esac

problems=0

# Runs the command, or only prints it in dry-run mode.
run() {
	if $dry_run; then
		echo "  (essai) $*"
	else
		"$@"
	fi
}

# Creates the link $2 → $1, unless $2 already exists and is not a link to the repository.
link() {
	local source="$1" target="$2"
	if [[ -L "$target" ]]; then
		local current
		current="$(readlink "$target")"
		if [[ "$current" == "$source" ]]; then
			echo "ok      $target"
			return
		fi
		if [[ "$current" == "$repo"/* ]]; then
			echo "relié   $target (pointait vers $current)"
			run ln -sfn "$source" "$target"
			return
		fi
		echo "IGNORÉ  $target : lien vers $current, hors du dépôt" >&2
		problems=$((problems + 1))
	elif [[ -e "$target" ]]; then
		echo "IGNORÉ  $target : existe déjà et n'est pas un lien (à déplacer dans le dépôt ?)" >&2
		problems=$((problems + 1))
	else
		echo "nouveau $target"
		run ln -s "$source" "$target"
	fi
}

# Removes from $1 the dead links that pointed to the repository.
prune() {
	local dir="$1" link_path current
	for link_path in "$dir"/*; do
		[[ -L "$link_path" && ! -e "$link_path" ]] || continue
		current="$(readlink "$link_path")"
		[[ "$current" == "$repo"/* ]] || continue
		echo "retiré  $link_path (n'existe plus dans le dépôt)"
		run rm "$link_path"
	done
}

run mkdir -p "$claude_dir/skills" "$claude_dir/agents"

shopt -s nullglob

echo "Skills"
for skill in "$repo"/skills/*/; do
	skill="${skill%/}"
	link "$skill" "$claude_dir/skills/$(basename "$skill")"
done
[[ -d "$claude_dir/skills" ]] && prune "$claude_dir/skills"

echo "Agents"
for agent in "$repo"/agents/*.md; do
	link "$agent" "$claude_dir/agents/$(basename "$agent")"
done
[[ -d "$claude_dir/agents" ]] && prune "$claude_dir/agents"

if ((problems > 0)); then
	echo "$problems élément(s) ignoré(s), voir ci-dessus." >&2
	exit 1
fi
