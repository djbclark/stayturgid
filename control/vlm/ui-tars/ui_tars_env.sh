# shellcheck shell=bash
# Thin compat shim — delegates to ui_tars_env.py. Source this from shell scripts.
_UI_TARS_PY="$(dirname "${BASH_SOURCE[0]:-$0}")/ui_tars_env.py"

ui_tars_home()            { python3 "$_UI_TARS_PY" --get home; }
ui_tars_model_dir()       { python3 "$_UI_TARS_PY" --get model_dir; }
ui_tars_port()            { python3 "$_UI_TARS_PY" --get port; }
ui_tars_pid_file()        { python3 "$_UI_TARS_PY" --get pid_file; }
ui_tars_log_file()        { python3 "$_UI_TARS_PY" --get log_file; }
ui_tars_working_dir()     { python3 "$_UI_TARS_PY" --get working_dir; }
ui_tars_ngl()             { python3 "$_UI_TARS_PY" --get ngl; }
ui_tars_llama_server_bin(){ python3 "$_UI_TARS_PY" --get llama_server_bin; }
ui_tars_health_url()      { python3 "$_UI_TARS_PY" --get health_url; }
ui_tars_service_label()   { python3 "$_UI_TARS_PY" --get service_label; }
ui_tars_service_plist()   { python3 "$_UI_TARS_PY" --get service_plist; }
ui_tars_legacy_service_label()  { python3 "$_UI_TARS_PY" --get legacy_service_label; }
ui_tars_legacy_service_plist()  { python3 "$_UI_TARS_PY" --get legacy_service_plist; }

ui_tars_healthy() {
    curl -sf "http://127.0.0.1:$(ui_tars_port)/health" >/dev/null 2>&1
}

ui_tars_service_installed() {
    [[ -f "$(ui_tars_service_plist)" ]]
}
