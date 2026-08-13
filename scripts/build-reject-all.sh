#!/usr/bin/env bash
set -Eeuo pipefail

repo_root=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd)
mihomo_bin=${MIHOMO_BIN:-mihomo}
custom_source=${CUSTOM_REJECT_SOURCE:-"$repo_root/reject.yaml"}
output=${REJECT_ALL_OUTPUT:-"$repo_root/reject-all.mrs"}
stats_file=${STATS_FILE:-}

for command in curl python3; do
  command -v "$command" >/dev/null || {
    printf 'Required command not found: %s\n' "$command" >&2
    exit 1
  }
done
if [[ ! -x "$mihomo_bin" ]] && ! command -v "$mihomo_bin" >/dev/null 2>&1; then
  printf 'Mihomo executable not found: %s\n' "$mihomo_bin" >&2
  exit 1
fi
[[ -f "$custom_source" ]] || {
  printf 'Custom reject source not found: %s\n' "$custom_source" >&2
  exit 1
}

work_dir=$(mktemp -d)
trap 'rm -rf -- "$work_dir"' EXIT

declare -A source_urls=(
  [category-ads-all]='https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/category-ads-all.mrs'
  [category-httpdns-cn]='https://raw.githubusercontent.com/MetaCubeX/meta-rules-dat/meta/geo/geosite/category-httpdns-cn.mrs'
  [reject]='https://raw.githubusercontent.com/wwqgtxx/clash-rules/release/reject.mrs'
  [adblockmihomolite]='https://raw.githubusercontent.com/217heidai/adblockfilters/main/rules/adblockmihomolite.mrs'
)
source_names=(category-ads-all category-httpdns-cn reject adblockmihomolite)

printf 'Mihomo: '
"$mihomo_bin" -v

input_mrs_bytes=0
text_inputs=()
for name in "${source_names[@]}"; do
  mrs="$work_dir/$name.mrs"
  text="$work_dir/$name.txt"
  printf 'Downloading %s\n' "$name"
  curl --fail --location --silent --show-error \
    --retry 4 --retry-all-errors --connect-timeout 20 --max-time 180 \
    "${source_urls[$name]}" --output "$mrs"
  [[ -s "$mrs" ]] || {
    printf 'Downloaded an empty ruleset: %s\n' "$name" >&2
    exit 1
  }
  "$mihomo_bin" convert-ruleset domain mrs "$mrs" "$text"
  count=$(wc -l < "$text")
  bytes=$(wc -c < "$mrs")
  (( count > 0 )) || {
    printf 'Downloaded ruleset has no domain rules: %s\n' "$name" >&2
    exit 1
  }
  printf '%-24s rules=%8d  bytes=%9d\n' "$name" "$count" "$bytes"
  printf -v "${name//-/_}_count" '%s' "$count"
  input_mrs_bytes=$((input_mrs_bytes + bytes))
  text_inputs+=("$text")
done

# Build custom-reject from its repository source. Never download reject.mrs
# from this repository, which would create a generated-artifact dependency loop.
custom_mrs="$work_dir/custom-reject.mrs"
custom_text="$work_dir/custom-reject.txt"
custom_build_log="$work_dir/custom-reject-build.log"
if ! "$mihomo_bin" convert-ruleset domain yaml "$custom_source" "$custom_mrs" 2> "$custom_build_log"; then
  cat "$custom_build_log" >&2
  exit 1
fi
if [[ -s "$custom_build_log" ]]; then
  cat "$custom_build_log" >&2
fi
if grep --ignore-case --quiet 'invalid domain' "$custom_build_log"; then
  printf 'Custom reject source contains a domain unsupported by this Mihomo CLI\n' >&2
  exit 1
fi
"$mihomo_bin" convert-ruleset domain mrs "$custom_mrs" "$custom_text"
custom_reject_count=$(wc -l < "$custom_text")
custom_mrs_bytes=$(wc -c < "$custom_mrs")
(( custom_reject_count > 0 )) || {
  printf 'Custom reject source has no accepted domain rules\n' >&2
  exit 1
}
printf '%-24s rules=%8d  bytes=%9d\n' custom-reject "$custom_reject_count" "$custom_mrs_bytes"
input_mrs_bytes=$((input_mrs_bytes + custom_mrs_bytes))
text_inputs+=("$custom_text")

normalized="$work_dir/reject-all.txt"
normalize_stats="$work_dir/normalize.stats"
python3 "$repo_root/scripts/normalize-domain-rules.py" \
  "${text_inputs[@]}" --output "$normalized" --stats "$normalize_stats"
# shellcheck disable=SC1090
source "$normalize_stats"

candidate="$work_dir/reject-all.mrs"
"$mihomo_bin" convert-ruleset domain text "$normalized" "$candidate"
[[ -s "$candidate" ]] || {
  printf 'Generated reject-all.mrs is empty\n' >&2
  exit 1
}

# Parsing with domain behavior verifies the MRS header behavior and payload.
dumped="$work_dir/reject-all.dump.txt"
"$mihomo_bin" convert-ruleset domain mrs "$candidate" "$dumped"
final_count=$(wc -l < "$dumped")
(( final_count > 0 )) || {
  printf 'Generated reject-all.mrs dump has no rules\n' >&2
  exit 1
}
if "$mihomo_bin" convert-ruleset ipcidr mrs "$candidate" "$work_dir/invalid-ipcidr-dump.txt" >/dev/null 2>&1; then
  printf 'Generated MRS unexpectedly declares ipcidr behavior\n' >&2
  exit 1
fi

# Re-normalizing the dump also rejects bare IP addresses and CIDR strings.
python3 "$repo_root/scripts/normalize-domain-rules.py" \
  "$dumped" --output "$work_dir/validated-dump.txt" --stats "$work_dir/validated.stats"
cmp --silent "$normalized" "$work_dir/validated-dump.txt" || {
  printf 'Generated MRS round-trip changed the normalized rules\n' >&2
  exit 1
}
python3 "$repo_root/scripts/validate-domain-coverage.py" \
  --custom "$custom_text" --final "$dumped"

final_bytes=$(wc -c < "$candidate")
exact_duplicates=$((merged_before - exact_unique))
dedup_rate=$(python3 -c 'import sys; a,b=map(int,sys.argv[1:]); print(f"{(a-b)*100/a:.2f}")' "$merged_before" "$exact_unique")
savings_rate=$(python3 -c 'import sys; a,b=map(int,sys.argv[1:]); print(f"{(a-b)*100/a:.2f}")' "$input_mrs_bytes" "$final_bytes")

mkdir -p -- "$(dirname -- "$output")"
mv -- "$candidate" "$output"
# Keep the legacy custom-only artifact synchronized with reject.yaml.
mv -- "$custom_mrs" "$repo_root/reject.mrs"

printf '\nUnified reject rules statistics\n'
printf '%-34s %d\n' 'category-ads-all original rules:' "$category_ads_all_count"
printf '%-34s %d\n' 'category-httpdns-cn original rules:' "$category_httpdns_cn_count"
printf '%-34s %d\n' 'reject original rules:' "$reject_count"
printf '%-34s %d\n' 'adblockmihomolite original rules:' "$adblockmihomolite_count"
printf '%-34s %d\n' 'custom-reject accepted rules:' "$custom_reject_count"
printf '%-34s %d\n' 'merged rules before deduplication:' "$merged_before"
printf '%-34s %d\n' 'exact duplicate rules removed:' "$exact_duplicates"
printf '%-34s %d (%s%%)\n' 'rules after exact deduplication:' "$exact_unique" "$dedup_rate"
printf '%-34s %d\n' 'safely covered rules pruned:' "$pruned"
printf '%-34s %d\n' 'final reject-all.mrs rules:' "$final_count"
printf '%-34s %d\n' 'input MRS total bytes:' "$input_mrs_bytes"
printf '%-34s %d\n' 'reject-all.mrs bytes:' "$final_bytes"
printf '%-34s %s%%\n' 'MRS byte savings:' "$savings_rate"

if [[ -n "$stats_file" ]]; then
  {
    printf 'category_ads_all_count=%s\n' "$category_ads_all_count"
    printf 'category_httpdns_cn_count=%s\n' "$category_httpdns_cn_count"
    printf 'reject_count=%s\n' "$reject_count"
    printf 'adblockmihomolite_count=%s\n' "$adblockmihomolite_count"
    printf 'custom_reject_count=%s\n' "$custom_reject_count"
    printf 'merged_before=%s\n' "$merged_before"
    printf 'exact_unique=%s\n' "$exact_unique"
    printf 'exact_duplicates=%s\n' "$exact_duplicates"
    printf 'dedup_rate=%s\n' "$dedup_rate"
    printf 'pruned=%s\n' "$pruned"
    printf 'final_count=%s\n' "$final_count"
    printf 'input_mrs_bytes=%s\n' "$input_mrs_bytes"
    printf 'final_bytes=%s\n' "$final_bytes"
    printf 'savings_rate=%s\n' "$savings_rate"
  } >> "$stats_file"
fi
