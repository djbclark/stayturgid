#!/usr/bin/env uv run
# /// script
# requires-python = ">=3.12"
# dependencies = [
#     "pyyaml>=6.0.1",
# ]
# ///

import os
import json
import urllib.request
import subprocess
import yaml

def main():
    repo_root = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
    yaml_path = os.path.join(repo_root, "ansible_collections/stayturgid/android_common/roles/bootstrap_apks/defaults/main.yml")
    
    with open(yaml_path, 'r') as f:
        data = yaml.safe_load(f)
        
    apks = data.get('stayturgid_bootstrap_apks', [])
    updates = []
    
    for apk in apks:
        gh_repo = apk.get('gh_repo')
        gh_tag = apk.get('gh_tag')
        
        if not gh_repo or not gh_tag:
            continue
            
        url = f"https://api.github.com/repos/{gh_repo}/releases/latest"
        req = urllib.request.Request(url)
        req.add_header('User-Agent', 'stayturgid-updater')
        
        try:
            with urllib.request.urlopen(req) as response:
                release_data = json.loads(response.read().decode())
                latest_tag = release_data.get('tag_name')
                
                if latest_tag and latest_tag != gh_tag:
                    updates.append(f"{gh_repo}: {gh_tag} -> {latest_tag}")
        except urllib.error.HTTPError as e:
            if e.code == 404:
                # Some repos might not use releases, check tags instead
                url = f"https://api.github.com/repos/{gh_repo}/tags"
                req = urllib.request.Request(url)
                req.add_header('User-Agent', 'stayturgid-updater')
                try:
                    with urllib.request.urlopen(req) as response:
                        tags_data = json.loads(response.read().decode())
                        if tags_data:
                            latest_tag = tags_data[0].get('name')
                            if latest_tag and latest_tag != gh_tag:
                                updates.append(f"{gh_repo}: {gh_tag} -> {latest_tag}")
                except Exception as ex:
                    print(f"Error checking tags for {gh_repo}: {ex}")
            else:
                print(f"Error checking {gh_repo}: {e}")
        except Exception as e:
            print(f"Error checking {gh_repo}: {e}")
            
    if updates:
        message = "Stayturgid pinned APK Updates Available:\n" + "\n".join(updates)
        print(message)
        try:
            subprocess.run(["hermes", "chat", "-q", message], check=False)
        except FileNotFoundError:
            try:
                subprocess.run(["hermes", "-z", message], check=False)
            except FileNotFoundError:
                print("hermes CLI not found to send notification.")

if __name__ == "__main__":
    main()
