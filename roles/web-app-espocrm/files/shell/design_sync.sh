#!/usr/bin/env sh
# Param $1: "present" installs the payload, "absent" removes what an earlier run installed.
# Param $2: name of the corporate theme the payload declares.
# Param $3: title EspoCRM shows as applicationName; empty restores the upstream name.
# Param $4: module directory of the theme metadata, relative to the EspoCRM root.
# Param $5: directory of the served theme files, relative to the EspoCRM root.
# Param stdin: one "<module|assets>/<path> <base64 content>" line per file.
# Output: CHANGED when a file or a config value moved.
set -eu

state="${1:?state is required}"
theme="${2:?theme name is required}"
title="${3}"
module="${4:?module directory is required}"
assets="${5:?assets directory is required}"
upstream_theme=Espo
upstream_title=EspoCRM
changed=false

cd /var/www/html

stage="$(mktemp -d)"
trap 'rm -rf "$stage"' EXIT
mkdir -p "$stage/module" "$stage/assets"
while read -r path data; do
	[ -n "$path" ] || continue
	mkdir -p "$stage/$(dirname "$path")"
	printf '%s' "$data" | base64 -d >"$stage/$path"
done

applied_title=""
if [ -f "$assets/title" ]; then
	applied_title="$(cat "$assets/title")"
fi

sync_tree() {
	if [ "$state" = present ]; then
		if [ -d "$2" ] && diff -r "$1" "$2" >/dev/null 2>&1; then
			return 0
		fi
		rm -rf "$2"
		mkdir -p "$(dirname "$2")"
		cp -R "$1" "$2"
	else
		[ -e "$2" ] || return 0
		rm -rf "$2"
	fi
	changed=true
}

espo_command() {
	espo_rc=0
	espo_out="$(php command.php "$@")" || espo_rc=$?
	if [ "$espo_rc" -ne 0 ]; then
		printf 'design_sync: command.php %s exited %s: %s\n' "$1" "$espo_rc" "$espo_out" >&2
		return "$espo_rc"
	fi
	printf '%s\n' "$espo_out"
}

sync_tree "$stage/module" "$module"
sync_tree "$stage/assets" "$assets"

current_theme="$(espo_command config:get theme)"
if [ "$state" = present ] && [ "$current_theme" = "$upstream_theme" ]; then
	espo_command config:set theme "$theme" >/dev/null
	changed=true
elif [ "$state" = absent ] && [ "$current_theme" = "$theme" ]; then
	espo_command config:set theme "$upstream_theme" >/dev/null
	changed=true
fi

desired_title="$upstream_title"
if [ "$state" = present ] && [ -n "$title" ]; then
	desired_title="$title"
fi
current_title="$(espo_command config:get applicationName)"
if [ "$current_title" != "$desired_title" ] && { [ "$current_title" = "$upstream_title" ] || [ "$current_title" = "$applied_title" ]; }; then
	espo_command config:set applicationName "$desired_title" >/dev/null
	changed=true
fi

if [ "$changed" = true ]; then
	espo_command clear-cache >/dev/null
	espo_command update-app-timestamp >/dev/null
	echo CHANGED
fi
