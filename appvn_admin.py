#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APPVN RETRO ADMIN PORTAL (Flask Edition) - Tomkids Repo
--------------------------------------------------------
Hỗ trợ 2 phân hệ chuyên biệt:
1. 🍎 KHO APPSTORE OTA:
   - Kéo thả & Chọn file trực tiếp từ máy tính (.ipa, .deb, .m4r, .mp3, .pdf)
   - Bóc tách Info.plist, trích xuất Icon, sinh manifest.plist
   - Tự động đẩy lên GitHub Releases (OTA-Storage)
   - Cập nhật ota_data.json / media_data.json

2. ⚡ CÀI ĐẶT NHANH DEB (CYDIA CLUSTER REPO):
   - Quản lý khu vực "CÀI ĐẶT NHANH DEB" trên trang chủ tomkidsrepo.cloud
   - Tự động bóc tách file control từ gói DEB (Package, Version, Name, Description)
   - Tự động lưu file DEB vào package_repo_A1 và Git Push (kích hoạt GitHub Actions tự sinh Packages.bz2 & sync Cydia)
   - Xem trước Live Preview nút bấm thời gian thực (màu sắc, badge iOS, ghi chú vàng)
   - Cập nhật quickinstall.json và đồng bộ siêu tốc lên web
   - Quản lý danh sách: Sắp xếp thứ tự (Lên/Xuống), Chỉnh sửa, Xóa nút
"""

import os
import re
import sys

if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except:
        pass
import json
import zipfile
import plistlib
import shutil
import io
import tarfile
import subprocess
import webbrowser
import requests
import datetime
from flask import Flask, request, jsonify, render_template_string

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
OTA_APPS_DIR = os.path.join(REPO_DIR, 'ota_apps')
ICONS_DIR = os.path.join(OTA_APPS_DIR, 'icons')
DATA_JSON_PATH = os.path.join(REPO_DIR, 'ota_data.json')
MEDIA_JSON_PATH = os.path.join(REPO_DIR, 'media_data.json')
QUICKINSTALL_JSON_PATH = os.path.join(REPO_DIR, 'quickinstall.json')
HOME_SETTINGS_PATH = os.path.join(REPO_DIR, 'home_settings.json')
AUTH_ACCOUNTS_PATH = os.path.join(REPO_DIR, 'auth_accounts.json')
APP_TABS_PATH = os.path.join(REPO_DIR, 'app_tabs.json')

def load_app_tabs():
    default_tabs = [
        {"id": "ALL", "name": "Tất cả", "icon": "🌐", "color": "#38bdf8", "type": "all", "system": True, "description": "Hiển thị tất cả ứng dụng theo quyền của tài khoản"},
        {"id": "GUEST", "name": "Guest", "icon": "🌟", "color": "#a855f7", "type": "curated", "system": True, "field": "show_on_guest", "description": "Dành cho khách, chỉ hiện các app được tích chọn"},
        {"id": "PRIVATE", "name": "Private", "icon": "🔒", "color": "#ec4899", "type": "curated", "system": False, "field": "show_on_private", "description": "Dành riêng cho chủ nhân hoặc tài khoản được cấp phép"},
        {"id": "Trò Chơi", "name": "Trò Chơi", "icon": "🎮", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Trò chơi / Game"},
        {"id": "Mạng Xã Hội", "name": "Mạng Xã Hội", "icon": "🌐", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Mạng xã hội / Chat"},
        {"id": "Giải Trí", "name": "Giải Trí", "icon": "🎵", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Giải trí / Media / Âm nhạc"},
        {"id": "Công Cụ", "name": "Công Cụ", "icon": "🛠️", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Tiện ích / Công cụ hệ điều hành"},
        {"id": "Hệ thống", "name": "Hệ thống", "icon": "⚙️", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Tinh chỉnh hệ thống"},
        {"id": "Jailbreak", "name": "Jailbreak", "icon": "🔓", "color": "#3b82f6", "type": "category", "system": True, "description": "Chuyên mục Ứng dụng Jailbreak"}
    ]
    if os.path.exists(APP_TABS_PATH):
        try:
            with open(APP_TABS_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, dict) and 'tabs' in data and isinstance(data['tabs'], list):
                return data['tabs']
            elif isinstance(data, list):
                return data
        except Exception:
            pass
    return default_tabs

def save_app_tabs(tabs):
    with open(APP_TABS_PATH, 'w', encoding='utf-8') as f:
        json.dump({'tabs': tabs}, f, ensure_ascii=False, indent=4)

def load_auth_accounts():
    default_auth = {'enabled': False, 'accounts': []}
    if os.path.exists(AUTH_ACCOUNTS_PATH):
        try:
            with open(AUTH_ACCOUNTS_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {
                    'enabled': bool(data.get('enabled', False)),
                    'accounts': list(data.get('accounts', []))
                }
        except Exception:
            pass
    return default_auth

def save_auth_accounts(data):
    with open(AUTH_ACCOUNTS_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

PACKAGE_REPO_A1_DIR = os.path.abspath(os.path.join(REPO_DIR, '..', 'package_repo_A1'))
INCOMING_DIR = os.path.join(REPO_DIR, 'incoming')

os.makedirs(OTA_APPS_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(INCOMING_DIR, exist_ok=True)

app = Flask(__name__)
# Cho phép upload file lên đến 2GB
app.config['MAX_CONTENT_LENGTH'] = 2048 * 1024 * 1024


# ==============================================================================
# 1. BÓC TÁCH & CHUYỂN ĐỔI DEB -> IPA / ĐỌC CONTROL TWEAK
# ==============================================================================
def read_deb_member(deb_path, target_name):
    with open(deb_path, 'rb') as f:
        magic = f.read(8)
        if magic != b'!<arch>\n':
            raise Exception("File DEB không hợp lệ (sai magic header)")
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[0:16].strip().decode('ascii', errors='replace')
            size = int(header[48:58].strip())
            data = f.read(size)
            if size % 2:
                f.read(1)
            if target_name in name:
                return data
    return None


def extract_deb_control(deb_path):
    """Trích xuất file control từ gói DEB và trả về dict metadata"""
    data_raw = read_deb_member(deb_path, 'control')
    if not data_raw:
        raise Exception("Không tìm thấy control.tar.* trong file DEB")

    ctrl_tar = tarfile.open(fileobj=io.BytesIO(data_raw), mode='r:*')
    ctrl_fobj = None
    for m in ctrl_tar.getmembers():
        base = os.path.basename(m.name)
        if base == 'control':
            ctrl_fobj = ctrl_tar.extractfile(m)
            break
    if not ctrl_fobj:
        raise Exception("Không tìm thấy file control bên trong control archive")

    content = ctrl_fobj.read().decode('utf-8', errors='replace')
    info = {}
    for line in content.split('\n'):
        if ':' in line and not line.startswith(' '):
            k, v = line.split(':', 1)
            info[k.strip().lower()] = v.strip()

    pkg_id = info.get('package', '')
    pkg_name = info.get('name') or pkg_id
    pkg_ver = info.get('version', '1.0')
    pkg_desc = info.get('description', '')

    return {
        "package_id": pkg_id,
        "name": pkg_name,
        "version": pkg_ver,
        "description": pkg_desc,
        "section": info.get('section', 'Tweaks'),
        "depends": info.get('depends', ''),
        "architecture": info.get('architecture', 'iphoneos-arm')
    }


def deb_to_ipa(deb_path, output_ipa_path):
    print(f"[*] Đang chuyển đổi DEB sang IPA: {deb_path}")
    data_raw = read_deb_member(deb_path, 'data')
    if not data_raw:
        raise Exception("Không tìm thấy data.tar.* trong file DEB")

    data_tar = tarfile.open(fileobj=io.BytesIO(data_raw), mode='r:*')
    app_dir_path = None
    for m in data_tar.getmembers():
        if m.isdir() and m.name.rstrip('/').endswith('.app'):
            if '/Applications/' in m.name or m.name.startswith('./Applications/'):
                app_dir_path = m.name.rstrip('/')
                break
    if not app_dir_path:
        for m in data_tar.getmembers():
            if m.isdir() and m.name.rstrip('/').endswith('.app'):
                app_dir_path = m.name.rstrip('/')
                break
    if not app_dir_path:
        raise Exception("Không tìm thấy bundle .app trong file DEB")

    app_name = os.path.basename(app_dir_path)
    payload_prefix = app_dir_path + '/'
    os.makedirs(os.path.dirname(output_ipa_path) or '.', exist_ok=True)

    with zipfile.ZipFile(output_ipa_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in data_tar.getmembers():
            if m.isfile() and m.name.startswith(payload_prefix):
                rel = m.name[len(payload_prefix):]
                arcname = f"Payload/{app_name}/{rel}"
                try:
                    fobj = data_tar.extractfile(m)
                    if fobj:
                        zf.writestr(arcname, fobj.read())
                except Exception as e:
                    print(f"  [!] Bỏ qua file {m.name}: {e}")

    print(f"[+] Đã tạo IPA thành công: {output_ipa_path}")
    return output_ipa_path


# ==============================================================================
# 2. TRÍCH XUẤT METADATA TỪ IPA
# ==============================================================================
def make_safe_slug(val, fallback='1.0'):
    s = re.sub(r'[^a-zA-Z0-9._-]+', '_', str(val or '').strip()).strip('._-')
    return s or fallback


def extract_ipa_info(ipa_path, custom_name=None, custom_version=None):
    print(f"[*] Đang phân tích file IPA: {ipa_path}")
    with zipfile.ZipFile(ipa_path, 'r') as ipa:
        info_plist_path = None
        for name in ipa.namelist():
            if name.startswith('Payload/') and name.endswith('.app/Info.plist') and name.count('/') == 2:
                info_plist_path = name
                break

        if not info_plist_path:
            raise Exception("Không tìm thấy Info.plist trong file IPA!")

        with ipa.open(info_plist_path) as f:
            plist = plistlib.load(f)

        app_name = (custom_name.strip() if custom_name and custom_name.strip() else None) or plist.get('CFBundleDisplayName') or plist.get('CFBundleName', 'App')
        version = (custom_version.strip() if custom_version and custom_version.strip() else None) or plist.get('CFBundleShortVersionString') or plist.get('CFBundleVersion', '1.0')
        bundle_id = plist.get('CFBundleIdentifier', 'com.tomkids.app')
        min_os = plist.get('MinimumOSVersion', '4.3')

        # Tìm Icon
        icon_names = []
        if 'CFBundleIconFiles' in plist:
            icon_names = plist['CFBundleIconFiles']
        elif 'CFBundleIcons' in plist and 'CFBundlePrimaryIcon' in plist.get('CFBundleIcons', {}):
            icon_names = plist['CFBundleIcons']['CFBundlePrimaryIcon'].get('CFBundleIconFiles', [])
        if not icon_names:
            icon_names = ['Icon', 'AppIcon', 'icon']

        app_folder = info_plist_path.replace('Info.plist', '')
        best_icon = None
        for name in ipa.namelist():
            if name.startswith(app_folder):
                basename = os.path.basename(name)
                for iname in icon_names:
                    if iname in basename and basename.endswith('.png'):
                        best_icon = name
                        if '@2x' in basename or '@3x' in basename:
                            break

        safe_bid = make_safe_slug(bundle_id, 'com.tomkids.app')
        safe_ver = make_safe_slug(version, '1.0')
        icon_rel_path = f"ota_apps/icons/{safe_bid}_{safe_ver}.png"
        icon_dest = os.path.join(REPO_DIR, icon_rel_path)
        if best_icon:
            with ipa.open(best_icon) as source, open(icon_dest, 'wb') as target:
                shutil.copyfileobj(source, target)
            print(f"[+] Đã trích xuất icon: {icon_rel_path}")
        else:
            icon_rel_path = "CydiaIcon.png"

        return {
            "name": app_name,
            "version": str(version),
            "bundle_id": bundle_id,
            "min_os": min_os,
            "icon": icon_rel_path
        }


# ==============================================================================
# 2.5. TỰ ĐỘNG LẤY TOKEN & UPLOAD LÊN GITHUB RELEASES (OTA-Storage)
# ==============================================================================
def get_github_token():
    token = os.environ.get('GITHUB_TOKEN', '').strip()
    if token:
        return token
    try:
        import win32cred
        targets = [
            'GitHub - https://api.github.com/tomkidsrepos',
            'git:https://github.com',
            'legacy_git:https://github.com',
            'GitHub - https://api.github.com/'
        ]
        for target in targets:
            try:
                cred = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
                raw = cred['CredentialBlob']
                t = raw.decode('utf-16') if b'\x00' in raw else raw.decode('utf-8', errors='ignore')
                t = t.strip().strip('\x00')
                if t and len(t) > 10:
                    return t
            except:
                pass

        # Quét toàn bộ credentials tìm token GitHub
        try:
            creds = win32cred.CredEnumerate(None, 0)
            for c in creds:
                target = c.get('TargetName', '')
                if 'github' in target.lower():
                    raw = c.get('CredentialBlob', b'')
                    if raw:
                        t = raw.decode('utf-16') if b'\x00' in raw else raw.decode('utf-8', errors='ignore')
                        t = t.strip().strip('\x00')
                        if t and (t.startswith('ghp_') or t.startswith('gho_') or t.startswith('github_pat_') or len(t) >= 30):
                            return t
        except:
            pass
    except:
        pass
    return ''


def git_push_repo(repo_path, commit_msg, branch='main'):
    if not os.path.exists(repo_path):
        return False, f"Thư mục repo không tồn tại: {repo_path}"
    try:
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, capture_output=True)

        repo_name = os.path.basename(repo_path)
        token = get_github_token()

        if token:
            for auth_pattern in [
                f"https://{token}@github.com/tomkidsrepos/{repo_name}.git",
                f"https://tomkidsrepos:{token}@github.com/tomkidsrepos/{repo_name}.git",
                f"https://oauth2:{token}@github.com/tomkidsrepos/{repo_name}.git",
                f"https://x-access-token:{token}@github.com/tomkidsrepos/{repo_name}.git"
            ]:
                res = subprocess.run(["git", "push", auth_pattern, branch], cwd=repo_path, capture_output=True, text=True, timeout=25)
                if res.returncode == 0:
                    print(f"[+] Git push {repo_name} thành công qua token!")
                    return True, f"Đã đẩy thành công lên {repo_name} ({branch})"

        # Thử đẩy bằng git CLI mặc định
        res = subprocess.run(["git", "push", "origin", branch], cwd=repo_path, capture_output=True, text=True, timeout=20)
        if res.returncode == 0:
            print(f"[+] Git push {repo_name} thành công qua git origin!")
            return True, f"Đã đẩy thành công lên {repo_name} ({branch})"

        print(f"[-] Git push {repo_name} cần đẩy qua GitHub Desktop")
        return False, f"Đã commit trên máy ({repo_name}). Bạn hãy mở GitHub Desktop và bấm 'Push origin' để hoàn tất!"
    except Exception as e:
        return False, str(e)


def load_quickinstall_data():
    if os.path.exists(QUICKINSTALL_JSON_PATH):
        try:
            with open(QUICKINSTALL_JSON_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except:
            pass
    return []


def save_quickinstall_data(items):
    with open(QUICKINSTALL_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(items, f, ensure_ascii=False, indent=2)


def upload_to_github_releases(file_path, target_filename=None):
    token = get_github_token()
    if not token:
        print("[!] Không tìm thấy GitHub token từ Windows Credential Manager.")
        return None

    if not target_filename:
        target_filename = os.path.basename(file_path)

    owner = "tomkidsrepos"
    repo = "tomkidsrepos.github.io"
    tag = "OTA-Storage"

    headers = {
        "Authorization": f"token {token}",
        "User-Agent": "TomkidsAppStore",
        "Accept": "application/vnd.github.v3+json"
    }

    rel_api = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    r = requests.get(rel_api, headers=headers)
    if r.status_code != 200:
        print(f"[!] Không thể đọc release {tag}: {r.status_code}")
        return None

    rel_data = r.json()
    rel_id = rel_data['id']
    assets = rel_data.get('assets', [])

    for a in assets:
        if a['name'] == target_filename:
            del_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{a['id']}"
            requests.delete(del_url, headers=headers)
            print(f"[*] Đã xóa asset cũ để ghi đè: {target_filename}")
            break

    upload_url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{rel_id}/assets?name={target_filename}"
    upload_headers = {
        "Authorization": f"token {token}",
        "User-Agent": "TomkidsAppStore",
        "Content-Type": "application/octet-stream"
    }

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"[*] Đang upload lên GitHub Releases: {target_filename} ({file_size_mb:.2f} MB)...")

    with open(file_path, 'rb') as f:
        res = requests.post(upload_url, headers=upload_headers, data=f)

    if res.status_code in (200, 201):
        dl_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{target_filename}"
        print(f"[+] Đã upload thành công lên GitHub Releases: {dl_url}")
        return dl_url
    else:
        print(f"[!] Lỗi upload GitHub Releases ({res.status_code}): {res.text[:150]}")
        return None


# ==============================================================================
# 3. TỰ SINH MANIFEST.PLIST & CẬP NHẬT ota_data.json / media_data.json
# ==============================================================================
def create_ota_plist(app_info, ipa_download_url):
    bundle_id = app_info["bundle_id"]
    name = app_info["name"]
    version = app_info["version"]
    icon_url = f"https://tomkidsrepo.cloud/{app_info['icon']}"

    safe_bid = make_safe_slug(bundle_id, 'com.tomkids.app')
    safe_ver = make_safe_slug(version, '1.0')
    plist_rel_path = f"ota_apps/{safe_bid}_{safe_ver}.plist"
    plist_full_path = os.path.join(REPO_DIR, plist_rel_path)

    xml_content = f'''<?xml version="1.0" encoding="UTF-8"?>
<!DOCTYPE plist PUBLIC "-//Apple//DTD PLIST 1.0//EN" "http://www.apple.com/DTDs/PropertyList-1.0.dtd">
<plist version="1.0">
<dict>
	<key>items</key>
	<array>
		<dict>
			<key>assets</key>
			<array>
				<dict>
					<key>kind</key>
					<string>software-package</string>
					<key>url</key>
					<string>{ipa_download_url}</string>
				</dict>
				<dict>
					<key>kind</key>
					<string>display-image</string>
					<key>needs-shine</key>
					<false/>
					<key>url</key>
					<string>{icon_url}</string>
				</dict>
			</array>
			<key>metadata</key>
			<dict>
				<key>bundle-identifier</key>
				<string>{bundle_id}</string>
				<key>bundle-version</key>
				<string>{version}</string>
				<key>kind</key>
				<string>software</string>
				<key>title</key>
				<string>{name}</string>
			</dict>
		</dict>
	</array>
</dict>
</plist>'''

    with open(plist_full_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)

    return plist_rel_path


def update_ota_json(category, app_record):
    with open(DATA_JSON_PATH, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    if category not in data:
        data[category] = []

    new_plist = (app_record.get('plist') or '').strip()
    new_name = (app_record.get('name') or '').strip().lower()
    new_ver = str(app_record.get('version') or '').strip().lower()

    updated = False
    for i, app in enumerate(data[category]):
        old_plist = (app.get('plist') or '').strip()
        old_name = (app.get('name') or '').strip().lower()
        old_ver = str(app.get('version') or '').strip().lower()

        if (new_plist and old_plist == new_plist) or (new_name and old_name == new_name and old_ver == new_ver):
            data[category][i] = app_record
            updated = True
            break

    if not updated:
        data[category].append(app_record)

    with open(DATA_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def update_media_json(section, item_record):
    data = {"books": [], "comics": [], "ringtones": [], "wallpapers": []}
    if os.path.exists(MEDIA_JSON_PATH):
        try:
            with open(MEDIA_JSON_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
        except:
            pass

    if section not in data:
        data[section] = []

    updated = False
    for i, item in enumerate(data[section]):
        if item.get('title') == item_record.get('title'):
            data[section][i] = item_record
            updated = True
            break

    if not updated:
        data[section].insert(0, item_record)

    with open(MEDIA_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


def load_home_settings():
    default_settings = {"hide_ota_section": False, "hidden_categories": []}
    if os.path.exists(HOME_SETTINGS_PATH):
        try:
            with open(HOME_SETTINGS_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return {
                    "hide_ota_section": bool(data.get("hide_ota_section", False)),
                    "hidden_categories": list(data.get("hidden_categories", []))
                }
        except:
            pass
    return default_settings


def save_home_settings(settings):
    with open(HOME_SETTINGS_PATH, 'w', encoding='utf-8') as f:
        json.dump(settings, f, ensure_ascii=False, indent=4)


def load_ota_data():
    if os.path.exists(DATA_JSON_PATH):
        try:
            with open(DATA_JSON_PATH, 'r', encoding='utf-8-sig') as f:
                data = json.load(f)
            if isinstance(data, dict):
                return data
        except:
            pass
    return {}


def save_ota_data(data):
    with open(DATA_JSON_PATH, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)


# ==============================================================================
# 4. GIAO DIỆN WEB QUẢN TRỊ 2 PHÂN HỆ
# ==============================================================================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tomkids AppStore & Cydia Admin</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0b0f19; color: #f1f5f9; padding: 25px 15px; }
        .container { max-width: 860px; margin: 0 auto; background: #131c31; padding: 30px; border-radius: 20px; box-shadow: 0 15px 40px rgba(0,0,0,0.6); border: 1px solid #1e293b; }
        
        /* TOP MODULE SWITCHER */
        .top-module-bar { display: flex; gap: 10px; margin-bottom: 25px; background: #080d1a; padding: 8px; border-radius: 14px; border: 1px solid #1e293b; }
        .module-tab-btn { flex: 1; padding: 13px 18px; font-size: 15px; font-weight: bold; border-radius: 10px; border: none; cursor: pointer; background: transparent; color: #94a3b8; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .module-tab-btn:hover { color: white; background: rgba(255, 255, 255, 0.05); }
        .module-tab-btn.active { background: #2563eb; color: white; box-shadow: 0 4px 15px rgba(37, 99, 235, 0.4); }

        .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 22px; }
        .logo-title { display: flex; align-items: center; gap: 12px; }
        .logo-title h1 { font-size: 22px; color: #38bdf8; }
        .badge { background: #2563eb; color: white; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 8px; }
        
        .tab-buttons { display: flex; gap: 8px; margin-bottom: 18px; border-bottom: 1px solid #1e293b; padding-bottom: 12px; flex-wrap: wrap; }
        .tab-btn { background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 9px 15px; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 13px; transition: 0.2s; }
        .tab-btn.active { background: #2563eb; color: white; border-color: #3b82f6; }

        .dropzone-box { border: 2px dashed #38bdf8; border-radius: 16px; padding: 35px 20px; text-align: center; background: rgba(56, 189, 248, 0.04); cursor: pointer; transition: 0.2s; position: relative; margin-bottom: 18px; }
        .dropzone-box:hover, .dropzone-box.dragover { background: rgba(56, 189, 248, 0.12); border-color: #60a5fa; transform: scale(1.005); }
        .dropzone-icon { font-size: 42px; margin-bottom: 10px; }
        .dropzone-text { font-size: 15px; font-weight: bold; color: #cbd5e1; margin-bottom: 5px; }
        .dropzone-sub { font-size: 12px; color: #64748b; }
        .file-input { display: none; }

        .file-selected-card { display: none; background: #1e293b; padding: 12px 16px; border-radius: 12px; margin-bottom: 18px; align-items: center; justify-content: space-between; border: 1px solid #3b82f6; }
        .file-name { font-weight: bold; color: #38bdf8; font-size: 14px; word-break: break-all; }
        .file-size { font-size: 12px; color: #94a3b8; margin-top: 3px; }
        .btn-remove-file { background: transparent; border: none; color: #ef4444; font-size: 18px; cursor: pointer; }

        label { display: block; margin-top: 14px; font-weight: bold; color: #94a3b8; font-size: 13px; margin-bottom: 5px; }
        select, input[type="text"], textarea { width: 100%; padding: 11px 13px; border-radius: 10px; border: 1px solid #334155; background: #0b0f19; color: white; font-size: 13px; outline: none; font-family: inherit; }
        select:focus, input[type="text"]:focus, textarea:focus { border-color: #38bdf8; }
        
        .form-row { display: grid; grid-template-columns: 1fr 1fr; gap: 14px; }
        @media (max-width: 600px) { .form-row { grid-template-columns: 1fr; } }

        .btn-submit { width: 100%; padding: 13px; background: #2563eb; color: white; border: none; border-radius: 12px; font-size: 15px; font-weight: bold; cursor: pointer; margin-top: 22px; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-submit:hover { background: #1d4ed8; }
        .btn-submit:disabled { background: #475569; cursor: not-allowed; }

        .progress-wrap { display: none; margin-top: 18px; }
        .progress-bar-bg { height: 9px; background: #1e293b; border-radius: 5px; overflow: hidden; }
        .progress-bar-fill { height: 100%; width: 0%; background: #38bdf8; transition: width 0.1s; }
        .progress-text { font-size: 12px; color: #94a3b8; margin-top: 6px; text-align: center; }

        .alert-box { padding: 14px; border-radius: 12px; margin-top: 18px; font-size: 13px; display: none; line-height: 1.5; }
        .alert-success { background: rgba(34, 197, 94, 0.15); border: 1px solid #22c55e; color: #4ade80; }
        .alert-error { background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; }

        .footer-tools { margin-top: 30px; border-top: 1px solid #1e293b; padding-top: 20px; display: flex; flex-wrap: wrap; gap: 10px; justify-content: space-between; align-items: center; }
        .btn-secondary { background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 9px 15px; border-radius: 10px; font-size: 13px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
        .btn-secondary:hover { background: #334155; color: white; }
        .btn-green { background: #16a34a; border-color: #22c55e; color: white; }
        .btn-green:hover { background: #15803d; }

        /* LIVE PREVIEW BOX CHO DEB */
        .preview-section { margin-top: 22px; background: #080d1a; border: 1px dashed #334155; border-radius: 14px; padding: 18px; }
        .preview-title { font-size: 12px; font-weight: bold; color: #94a3b8; text-transform: uppercase; letter-spacing: 1px; margin-bottom: 12px; display: flex; align-items: center; gap: 6px; }
        .preview-box { background: #050816; border-radius: 12px; padding: 18px; border: 1px solid #1e293b; text-align: center; }
        .step-btn-preview { color: white; padding: 12px 20px; border-radius: 12px; text-decoration: none; font-weight: bold; font-size: 14px; display: block; width: 100%; max-width: 500px; margin: 0 auto; text-align: center; box-sizing: border-box; transition: 0.2s; }
        .step-desc-preview { font-size: 11px; color: #64748b; margin-top: 6px; margin-bottom: 0; text-align: center; }
        .step-note-preview { font-size: 11px; color: #f59e0b; margin-top: 4px; margin-bottom: 0; text-align: center; font-style: italic; }

        /* DANH SÁCH CÁC NÚT HIỆN TẠI */
        .existing-card { margin-top: 35px; border-top: 1px solid #1e293b; padding-top: 25px; }
        .existing-header { display: flex; justify-content: space-between; align-items: center; margin-bottom: 15px; }
        .existing-item { background: #0e1626; border: 1px solid #1e293b; border-radius: 12px; padding: 12px 16px; margin-bottom: 10px; display: flex; align-items: center; justify-content: space-between; gap: 12px; }
        .existing-item:hover { border-color: #334155; }
        .item-info { flex: 1; }
        .item-title { font-weight: bold; font-size: 14px; color: #f8fafc; display: flex; align-items: center; gap: 8px; flex-wrap: wrap; }
        .item-pkg { font-family: monospace; font-size: 11px; color: #60a5fa; margin-top: 3px; }
        .item-desc { font-size: 12px; color: #94a3b8; margin-top: 3px; }
        .item-note { font-size: 11px; color: #f59e0b; font-style: italic; margin-top: 2px; }
        .item-actions { display: flex; align-items: center; gap: 6px; }
        .btn-action { background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 5px 9px; border-radius: 7px; font-size: 12px; cursor: pointer; }
        .btn-action:hover { background: #334155; color: white; }
        .btn-action-del { color: #f87171; }
        .btn-action-del:hover { background: #dc2626; color: white; border-color: #ef4444; }
    </style>
    <script>
        var currentSourceTab = 'file';
        var currentDebSourceTab = 'file';

        function switchModule(mod, ev) {
            if (ev) {
                try { ev.preventDefault(); ev.stopPropagation(); } catch(e) {}
            }
            var btnApp = document.getElementById('btn-module-appstore');
            var btnDeb = document.getElementById('btn-module-deb');
            var btnVis = document.getElementById('btn-module-visibility');
            var btnAcc = document.getElementById('btn-module-accounts');
            var btnTabs = document.getElementById('btn-module-tabs');
            var conApp = document.getElementById('module-appstore-container');
            var conDeb = document.getElementById('module-deb-container');
            var conVis = document.getElementById('module-visibility-container');
            var conAcc = document.getElementById('module-accounts-container');
            var conTabs = document.getElementById('module-tabs-container');

            if (btnApp) btnApp.className = (mod === 'appstore') ? 'module-tab-btn active' : 'module-tab-btn';
            if (btnDeb) btnDeb.className = (mod === 'deb') ? 'module-tab-btn active' : 'module-tab-btn';
            if (btnVis) btnVis.className = (mod === 'visibility') ? 'module-tab-btn active' : 'module-tab-btn';
            if (btnAcc) btnAcc.className = (mod === 'accounts') ? 'module-tab-btn active' : 'module-tab-btn';
            if (btnTabs) btnTabs.className = (mod === 'tabs') ? 'module-tab-btn active' : 'module-tab-btn';

            if (conApp) conApp.style.display = (mod === 'appstore') ? 'block' : 'none';
            if (conDeb) conDeb.style.display = (mod === 'deb') ? 'block' : 'none';
            if (conVis) conVis.style.display = (mod === 'visibility') ? 'block' : 'none';
            if (conAcc) conAcc.style.display = (mod === 'accounts') ? 'block' : 'none';
            if (conTabs) conTabs.style.display = (mod === 'tabs') ? 'block' : 'none';

            if (mod === 'deb') {
                if (typeof loadQuickInstallList === 'function') loadQuickInstallList();
                if (typeof loadDebIncomingList === 'function') loadDebIncomingList();
                if (typeof updateDebPreview === 'function') updateDebPreview();
            } else if (mod === 'visibility') {
                if (typeof loadVisibilityManager === 'function') loadVisibilityManager();
            } else if (mod === 'accounts') {
                if (typeof loadAccountsManager === 'function') loadAccountsManager();
            } else if (mod === 'tabs') {
                if (typeof loadTabsManager === 'function') loadTabsManager();
            }
        }

        function switchSourceTab(tab, ev) {
            if (ev) {
                try { ev.preventDefault(); ev.stopPropagation(); } catch(e) {}
            }
            currentSourceTab = tab;
            var btnFile = document.getElementById('btn-tab-file');
            var btnLink = document.getElementById('btn-tab-link');
            var btnInc = document.getElementById('btn-tab-incoming');

            if (btnFile) btnFile.className = (tab === 'file') ? 'tab-btn active' : 'tab-btn';
            if (btnLink) btnLink.className = (tab === 'link') ? 'tab-btn active' : 'tab-btn';
            if (btnInc) btnInc.className = (tab === 'incoming') ? 'tab-btn active' : 'tab-btn';

            var secFile = document.getElementById('section-file');
            var secLink = document.getElementById('section-link');
            var secInc = document.getElementById('section-incoming');

            if (secFile) secFile.style.display = (tab === 'file') ? 'block' : 'none';
            if (secLink) secLink.style.display = (tab === 'link') ? 'block' : 'none';
            if (secInc) secInc.style.display = (tab === 'incoming') ? 'block' : 'none';

            if (tab === 'incoming' && typeof loadIncomingFilesList === 'function') {
                loadIncomingFilesList();
            }
        }

        function switchDebSourceTab(tab, ev) {
            if (ev) {
                try { ev.preventDefault(); ev.stopPropagation(); } catch(e) {}
            }
            currentDebSourceTab = tab;
            var tabs = ['file', 'link', 'incoming', 'manual'];
            for (var i = 0; i < tabs.length; i++) {
                var t = tabs[i];
                var btn = document.getElementById('btn-debtab-' + t);
                var sec = document.getElementById('deb-sec-' + t);
                if (btn) btn.className = (t === tab) ? 'tab-btn active' : 'tab-btn';
                if (sec) sec.style.display = (t === tab) ? 'block' : 'none';
            }

            if (tab === 'incoming' && typeof loadDebIncomingList === 'function') {
                loadDebIncomingList();
            }
        }
    </script>
</head>
<body>
    <div class="container">
        
        <!-- THANH CHUYỂN PHÂN HỆ CHÍNH -->
        <div class="top-module-bar">
            <button type="button" class="module-tab-btn active" id="btn-module-appstore" onclick="switchModule('appstore', event)" style="font-size:13.5px; padding:12px 10px;">
                🍎 Kho AppStore OTA
            </button>
            <button type="button" class="module-tab-btn" id="btn-module-deb" onclick="switchModule('deb', event)" style="font-size:13.5px; padding:12px 10px;">
                ⚡ Cài Đặt Nhanh DEB
            </button>
            <button type="button" class="module-tab-btn" id="btn-module-visibility" onclick="switchModule('visibility', event)" style="font-size:13.5px; padding:12px 10px;">
                👁️ Ẩn/Hiện Kho App
            </button>
            <button type="button" class="module-tab-btn" id="btn-module-accounts" onclick="switchModule('accounts', event)" style="font-size:13.5px; padding:12px 10px;">
                👥 Quản Lý Tài Khoản
            </button>
            <button type="button" class="module-tab-btn" id="btn-module-tabs" onclick="switchModule('tabs', event)" style="font-size:13.5px; padding:12px 10px;">
                🏷️ Quản Lý Tab
            </button>
        </div>

        <!-- ================================================================= -->
        <!-- MODULE 1: QUẢN LÝ APPSTORE OTA (IPA, SÁCH, NHẠC, HÌNH NỀN) -->
        <!-- ================================================================= -->
        <div id="module-appstore-container">
            <div class="header">
                <div class="logo-title">
                    <h1>🍎 Tomkids AppStore Admin</h1>
                    <span class="badge">AppStore OTA</span>
                </div>
                <a href="https://tomkidsrepo.cloud/app/" target="_blank" class="btn-secondary">🌐 Mở Web AppStore</a>
            </div>

            <!-- TABS CHỌN NGUỒN FILE -->
            <div class="tab-buttons">
                <button type="button" class="tab-btn active" id="btn-tab-file" onclick="switchSourceTab('file', event)">📁 Chọn File từ Máy Tính</button>
                <button type="button" class="tab-btn" id="btn-tab-link" onclick="switchSourceTab('link', event)">🔗 Nhập Link Ngoài / Google Drive</button>
                <button type="button" class="tab-btn" id="btn-tab-incoming" onclick="switchSourceTab('incoming', event)">📂 File trong Thư mục incoming/</button>
            </div>

            <form id="upload-form" onsubmit="handleFormSubmit(event)">
                <!-- SECTION 1: CHỌN FILE TỪ MÁY TÍNH -->
                <div id="section-file">
                    <div class="dropzone-box" id="dropzone" onclick="document.getElementById('file-input').click()">
                        <div class="dropzone-icon">📥</div>
                        <div class="dropzone-text">Bấm vào đây để Chọn Một hoặc Nhiều File cùng lúc</div>
                        <div class="dropzone-sub">Hỗ trợ chọn hàng loạt hoặc Kéo thả nhiều file <b>.ipa, .deb, .m4r, .mp3, .pdf</b> cùng lúc</div>
                        <input type="file" id="file-input" class="file-input" accept=".ipa,.deb,.m4r,.mp3,.pdf,.jpg,.png" multiple onchange="onFileSelected(this.files)">
                    </div>

                    <div class="file-selected-card" id="file-selected-card">
                        <div>
                            <div class="file-name" id="file-selected-name">ten_file.ipa</div>
                            <div class="file-size" id="file-selected-size">Dung lượng: 15.4 MB</div>
                        </div>
                        <button type="button" class="btn-remove-file" onclick="removeSelectedFile()">✕</button>
                    </div>
                </div>

                <!-- SECTION 2: NHẬP LINK NGOÀI -->
                <div id="section-link" style="display:none;">
                    <label>Dán link tải trực tiếp (hoặc link Google Drive chia sẻ công khai):</label>
                    <input type="text" id="link-input" placeholder="https://drive.google.com/file/d/... hoặc https://.../app.ipa">
                </div>

                <!-- SECTION 3: CHỌN TỪ THƯ MỤC INCOMING -->
                <div id="section-incoming" style="display:none;">
                    <label>Chọn file có sẵn trong thư mục "incoming/":</label>
                    <select id="incoming-select">
                        <option value="">-- Bấm để tải danh sách file --</option>
                    </select>
                    <div style="margin-top:12px; display:flex; gap:10px;">
                        <button type="button" class="btn-secondary btn-green" onclick="processAllIncoming()">⚡ Xử Lý TOÀN BỘ File Trong Thư Mục</button>
                    </div>
                    <p style="font-size:12px; color:#64748b; margin-top:8px;">Bạn có thể copy hàng chục file vào thư mục incoming/ trên máy tính rồi bấm nút trên để hệ thống tự động xử lý toàn bộ!</p>
                </div>

                <!-- CHỌN CHUYÊN MỤC -->
                <label>Chọn Chuyên mục:</label>
                <select id="category-select" required>
                    <optgroup label="🍎 Kho Ứng Dụng & Game (IPA / DEB)">
                        <option value="Trò Chơi" selected>🎮 Trò Chơi</option>
                        <option value="Mạng Xã Hội">🌐 Mạng Xã Hội</option>
                        <option value="Giải Trí">🎵 Giải Trí / Media</option>
                        <option value="Công Cụ">🛠️ Công Cụ / Tiện ích</option>
                        <option value="Hệ thống">⚙️ Hệ thống</option>
                        <option value="Jailbreak">🔓 Jailbreak</option>
                    </optgroup>
                    <optgroup label="📚 Sách, Truyện & Đa Phương Tiện">
                        <option value="Sách">📖 Sách (PDF / ePub)</option>
                        <option value="Truyện">📚 Truyện (Truyện tranh / Manga)</option>
                        <option value="Nhạc chuông">🎵 Nhạc chuông (.m4r / .mp3)</option>
                        <option value="Hình nền">🖼️ Hình nền (.jpg / .png)</option>
                    </optgroup>
                </select>

                <!-- TÙY CHỌN TÊN & PHIÊN BẢN RIÊNG (CHỐNG TRÙNG VER) -->
                <div class="form-row" style="margin-top:12px;">
                    <div>
                        <label style="margin-top:0;">Tên hiển thị (Tùy chọn):</label>
                        <input type="text" id="custom-name-input" placeholder="Để trống = Tự đọc từ file IPA">
                    </div>
                    <div>
                        <label style="margin-top:0;">Phiên bản (Tùy chọn):</label>
                        <input type="text" id="custom-version-input" placeholder="VD: 1.3 hoặc 2.0 (Trống = Tự đọc IPA)">
                    </div>
                </div>

                <!-- TÙY CHỌN LINK GITHUB RELEASES -->
                <label>Đường dẫn tải trên GitHub Releases (Tùy chọn):</label>
                <input type="text" id="release-url-input" placeholder="Mặc định: https://github.com/.../releases/download/OTA-Storage/app.ipa">

                <!-- TÙY CHỌN HIỂN THỊ TRÊN TRANG CHỦ -->
                <div style="margin-top:14px; background:#0b1222; padding:12px 14px; border-radius:10px; border:1px solid #334155;">
                    <label style="display:flex; align-items:center; gap:10px; margin-top:0; cursor:pointer; color:#e2e8f0; font-size:13px; font-weight:600;">
                        <input type="checkbox" id="ota-show-on-home" style="width:17px; height:17px; cursor:pointer;">
                        <span>🏠 Hiện thêm ở mục "KHO ỨNG DỤNG (CÀI TRỰC TIẾP)" trên trang chủ</span>
                    </label>
                    <p style="font-size:11px; color:#94a3b8; margin-top:5px; margin-left:27px;">Mặc định bỏ tích: App mới sẽ chỉ xuất hiện trong Kho App (/app/), tránh bị lặp 2 lần ở trang chủ.</p>
                </div>

                <!-- NÚT BẮT ĐẦU XỬ LÝ -->
                <button type="submit" class="btn-submit" id="btn-submit">
                    <span>⚡ Bắt Đầu Xử Lý Tự Động</span>
                </button>

                <!-- THANH TIẾN TRÌNH UPLOAD -->
                <div class="progress-wrap" id="progress-wrap">
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" id="progress-bar-fill"></div>
                    </div>
                    <div class="progress-text" id="progress-text">Đang tải file lên máy chủ cục bộ: 0%</div>
                </div>

                <!-- THÔNG BÁO KẾT QUẢ -->
                <div class="alert-box" id="alert-box"></div>
            </form>

            <!-- FOOTER & CÔNG CỤ ĐỒNG BỘ -->
            <div class="footer-tools">
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openIncomingFolder()">📂 Mở Thư Mục incoming/</button>
                    <button type="button" class="btn-secondary" onclick="cleanIncomingFolder()" style="color:#f87171;">🧹 Dọn Sạch File Tạm</button>
                </div>
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openGitHubDesktop()">🖥️ Mở GitHub Desktop</button>
                    <button type="button" class="btn-secondary btn-green" id="btn-git-push" onclick="triggerGitPush()">⚡ Đồng Bộ Lên Web Tức Thì</button>
                </div>
            </div>
        </div>


        <!-- ================================================================= -->
        <!-- MODULE 2: QUẢN LÝ CÀI ĐẶT NHANH DEB (CYDIA CLUSTER REPO) -->
        <!-- ================================================================= -->
        <div id="module-deb-container" style="display:none;">
            <div class="header">
                <div class="logo-title">
                    <h1>⚡ Cài Đặt Nhanh DEB</h1>
                    <span class="badge" style="background:#16a34a;">Cydia Repo</span>
                </div>
                <a href="https://tomkidsrepo.cloud/" target="_blank" class="btn-secondary">🌐 Mở Cydia Repo Cloud</a>
            </div>

            <!-- TABS CHỌN NGUỒN CHO DEB -->
            <div class="tab-buttons">
                <button type="button" class="tab-btn active" id="btn-debtab-file" onclick="window.switchDebSourceTab('file', event)">📁 Chọn File DEB từ Máy Tính</button>
                <button type="button" class="tab-btn" id="btn-debtab-link" onclick="window.switchDebSourceTab('link', event)">🔗 Nhập Link Ngoài / Drive</button>
                <button type="button" class="tab-btn" id="btn-debtab-incoming" onclick="window.switchDebSourceTab('incoming', event)">📂 File trong incoming/</button>
                <button type="button" class="tab-btn" id="btn-debtab-manual" onclick="window.switchDebSourceTab('manual', event)">✏️ Nhập Thủ Công (Có Sẵn)</button>
            </div>

            <!-- SECTION NGUỒN DEB: CHỌN FILE -->
            <div id="deb-sec-file">
                <div class="dropzone-box" id="deb-dropzone" onclick="document.getElementById('deb-file-input').click()">
                    <div class="dropzone-icon">📦</div>
                    <div class="dropzone-text">Chọn hoặc Kéo thả file .deb vào đây</div>
                    <div class="dropzone-sub">Hệ thống sẽ tự động bóc tách file <b>control</b> và điền thông tin tweak ngay lập tức!</div>
                    <input type="file" id="deb-file-input" class="file-input" accept=".deb" onchange="onDebFileSelected(this.files)">
                </div>

                <div class="file-selected-card" id="deb-file-card">
                    <div>
                        <div class="file-name" id="deb-file-card-name">tweak.deb</div>
                        <div class="file-size" id="deb-file-card-size">Đã bóc tách metadata thành công!</div>
                    </div>
                    <button type="button" class="btn-remove-file" onclick="removeDebSelectedFile()">✕</button>
                </div>
            </div>

            <!-- SECTION NGUỒN DEB: NHẬP LINK -->
            <div id="deb-sec-link" style="display:none;">
                <label>Dán link tải trực tiếp file .deb (hoặc link Google Drive):</label>
                <div style="display:flex; gap:8px;">
                    <input type="text" id="deb-link-input" placeholder="https://.../tweak.deb hoặc link Google Drive">
                    <button type="button" class="btn-secondary btn-green" style="white-space:nowrap;" onclick="extractDebFromLink(event)">🔍 Đọc DEB</button>
                </div>
            </div>

            <!-- SECTION NGUỒN DEB: TỪ THƯ MỤC INCOMING -->
            <div id="deb-sec-incoming" style="display:none;">
                <label>Chọn file .deb có sẵn trong thư mục "incoming/":</label>
                <div style="display:flex; gap:8px;">
                    <select id="deb-incoming-select">
                        <option value="">-- Đang quét thư mục incoming/ --</option>
                    </select>
                    <button type="button" class="btn-secondary btn-green" style="white-space:nowrap;" onclick="extractDebFromIncoming(event)">🔍 Đọc DEB</button>
                </div>
            </div>

            <!-- SECTION NGUỒN DEB: NHẬP THỦ CÔNG -->
            <div id="deb-sec-manual" style="display:none;">
                <p style="font-size:12px; color:#38bdf8; background:rgba(56,189,248,0.08); padding:10px 14px; border-radius:10px; border:1px solid rgba(56,189,248,0.2);">
                    💡 <b>Chế độ Thủ công:</b> Bạn có thể tạo nút cài nhanh cho bất kỳ tweak nào đã có sẵn trên Cydia Repo (hoặc nhập Package ID bất kỳ).
                </p>
            </div>

            <!-- FORM CHI TIẾT NÚT CÀI ĐẶT NHANH -->
            <form id="deb-form" onsubmit="handleDebFormSubmit(event)">
                <input type="hidden" id="deb-edit-mode" value="0">
                <input type="hidden" id="deb-edit-orig-pkg" value="">
                <input type="hidden" id="deb-temp-filename" value="">

                <label>Tên hiển thị trên Nút Cài Nhanh (*):</label>
                <input type="text" id="deb-name" required placeholder="VD: Cài tweak GSAPort - Fix đăng nhập iCloud" oninput="updateDebPreview()">

                <div class="form-row">
                    <div>
                        <label>Package ID (*):</label>
                        <input type="text" id="deb-pkg-id" required placeholder="VD: com.podpod123.gsaport" oninput="updateDebPreview()">
                    </div>
                    <div>
                        <label>Phiên bản:</label>
                        <input type="text" id="deb-version" placeholder="VD: 1.0-12+debug" oninput="updateDebPreview()">
                    </div>
                </div>

                <div class="form-row">
                    <div>
                        <label>Phạm vi iOS (Badge hiển thị):</label>
                        <input type="text" id="deb-ios-range" placeholder="VD: iOS 6-8 hoặc iOS 5-10, iOS 6..." oninput="updateDebPreview()">
                    </div>
                    <div>
                        <label>Màu sắc nút:</label>
                        <select id="deb-color" onchange="updateDebPreview()">
                            <option value="green" selected>🟢 Màu Xanh Lá (Tiêu chuẩn các Tweak)</option>
                            <option value="blue">🔵 Màu Xanh Dương (Nguồn Cydia / Tiện ích)</option>
                            <option value="orange">🟠 Màu Cam (Cảnh báo / Tùy chọn đặc biệt)</option>
                        </select>
                    </div>
                </div>

                <label>Mô tả phụ bên dưới nút (Tùy chọn):</label>
                <input type="text" id="deb-desc" placeholder="VD: Sửa lỗi đăng nhập iCloud / Apple ID trên iOS 6" oninput="updateDebPreview()">

                <label>Hướng dẫn / Ghi chú quan trọng (Chữ vàng nghiêng - ⓘ):</label>
                <textarea id="deb-note" rows="2" placeholder="VD: Hướng dẫn: Lần 1 nhập mật khẩu iCloud, lấy mã OTP gửi về máy khác. Lần 2 chỉ nhập mã OTP vừa nhận vào ô mật khẩu" oninput="updateDebPreview()"></textarea>

                <div style="margin-top:14px; background:rgba(37,99,235,0.08); border:1px solid #1e3a8a; border-radius:10px; padding:12px 14px; display:flex; align-items:center; gap:10px;">
                    <input type="checkbox" id="deb-auto-repo" checked style="width:18px; height:18px; cursor:pointer;">
                    <label for="deb-auto-repo" style="margin:0; font-weight:normal; font-size:13px; color:#cbd5e1; cursor:pointer;">
                        ⚡ <b>Tự động copy file DEB vào package_repo_A1 & Đẩy lên GitHub</b> (Cydia tự động build Packages.bz2 & sync cluster repo)
                    </label>
                </div>

                <!-- LIVE PREVIEW BOX -->
                <div class="preview-section">
                    <div class="preview-title">👁️ Xem trước giao diện trên tomkidsrepo.cloud:</div>
                    <div class="preview-box">
                        <div id="deb-preview-btn-wrap" style="max-width:520px; margin:0 auto;">
                            <a id="deb-preview-btn" class="step-btn-preview" href="javascript:void(0)" style="background:#16a34a;">
                                <span id="deb-preview-name">Cài tweak GSAPort - Fix đăng nhập iCloud</span>
                                <span id="deb-preview-badge" style="background:#0f3460; color:#60a5fa; font-size:11px; padding:2px 7px; border-radius:20px; margin-left:6px; white-space:nowrap;">iOS 6-8</span>
                            </a>
                            <p id="deb-preview-desc" class="step-desc-preview">Sửa lỗi đăng nhập iCloud / Apple ID trên iOS 6</p>
                            <p id="deb-preview-note" class="step-note-preview">ⓘ Hướng dẫn: Lần 1 nhập mật khẩu iCloud...</p>
                        </div>
                    </div>
                </div>

                <!-- SUBMIT BUTTONS -->
                <div style="display:flex; gap:10px; margin-top:20px;">
                    <button type="submit" class="btn-submit" id="btn-deb-submit" style="margin-top:0;">
                        <span>⚡ Lưu Nút & Tự Động Build Vào Cydia</span>
                    </button>
                    <button type="button" class="btn-secondary" id="btn-deb-cancel-edit" style="display:none; padding:13px 20px;" onclick="cancelDebEdit()">
                        Hủy Chỉnh Sửa
                    </button>
                </div>

                <!-- PROGRESS & ALERT -->
                <div class="progress-wrap" id="deb-progress-wrap">
                    <div class="progress-bar-bg">
                        <div class="progress-bar-fill" id="deb-progress-bar-fill"></div>
                    </div>
                    <div class="progress-text" id="deb-progress-text">Đang xử lý...</div>
                </div>

                <div class="alert-box" id="deb-alert-box"></div>
            </form>

            <!-- DANH SÁCH CÁC NÚT HIỆN TẠI TRÊN TRANG CHỦ -->
            <div class="existing-card">
                <div class="existing-header">
                    <h3 style="font-size:16px; color:#38bdf8;">📋 Danh Sách Các Nút Cài Nhanh Hiện Có (Trang Chủ)</h3>
                    <span id="deb-count-badge" class="badge">Đang tải...</span>
                </div>
                <div id="deb-items-list">
                    <p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Đang tải danh sách các nút từ quickinstall.json...</p>
                </div>
            </div>

            <!-- FOOTER TOOLS CHO DEB -->
            <div class="footer-tools">
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openIncomingFolder()">📂 Mở Thư Mục incoming/</button>
                    <button type="button" class="btn-secondary" onclick="loadQuickInstallList()">🔄 Làm Mới Danh Sách</button>
                </div>
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openGitHubDesktop()">🖥️ Mở GitHub Desktop</button>
                    <button type="button" class="btn-secondary btn-green" onclick="triggerGitPush()">⚡ Đồng Bộ Lên Web Tức Thì</button>
                </div>
            </div>
        </div>

        <!-- ================================================================= -->
        <!-- PHÂN HỆ 4: QUẢN LÝ TÀI KHOẢN ĐĂNG NHẬP TOMKIDS APPSTORE -->
        <!-- ================================================================= -->
        <div id="module-accounts-container" style="display:none;">
            <div class="header" style="margin-bottom:20px;">
                <div class="logo-title">
                    <h1>👥 Quản Lý Tài Khoản AppStore</h1>
                    <span class="badge" style="background:#8b5cf6;">Bảo Mật Truy Cập</span>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <button type="button" class="btn-secondary" onclick="loadAccountsManager()">🔄 Làm Mới</button>
                    <a href="https://tomkidsrepo.cloud/app/" target="_blank" class="header-link">📱 Mở Kho App (/app)</a>
                </div>
            </div>

            <!-- CARD TRẠNG THÁI KHÓA BẢO VỆ -->
            <div class="existing-card" style="margin-top:0; margin-bottom:20px;">
                <div class="existing-header" style="margin-bottom:10px;">
                    <div>
                        <h3 style="font-size:16px; color:#a78bfa; margin-bottom:4px;">🔐 Yêu Cầu Đăng Nhập Khi Vào Kho App</h3>
                        <p style="font-size:12.5px; color:#94a3b8;">
                            Nếu BẬT: Người dùng bấm vào nút trên trang chủ hoặc vào <code>https://tomkidsrepo.cloud/app/</code> sẽ bắt buộc phải nhập đúng Tài khoản & Mật khẩu mới được vào.
                        </p>
                    </div>
                    <button type="button" id="btn-toggle-auth-protection" class="btn-action" onclick="toggleAuthProtection()" style="padding:10px 18px; font-size:13px; font-weight:bold;">
                        Đang tải...
                    </button>
                </div>
            </div>

            <!-- CARD FORM CẤP / SỬA TÀI KHOẢN -->
            <div class="existing-card" style="margin-top:0; margin-bottom:20px;">
                <div class="existing-header" style="margin-bottom:14px;">
                    <h3 id="acc-form-title" style="font-size:15px; color:#38bdf8;">➕ Cấp Tài Khoản Mới</h3>
                    <button type="button" id="btn-acc-cancel-edit" class="btn-secondary" onclick="resetAccountForm()" style="display:none; font-size:12px; padding:6px 12px;">Hủy Sửa</button>
                </div>
                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap:12px; margin-bottom:14px;">
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Tên Đăng Nhập (*):</label>
                        <input type="text" id="acc-username-input" placeholder="VD: user01, khachhang1" style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Mật Khẩu / Mã PIN (*):</label>
                        <input type="text" id="acc-password-input" placeholder="VD: 123456 hoặc mật khẩu dễ nhớ" style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Ghi Chú / Tên Người Dùng:</label>
                        <input type="text" id="acc-note-input" placeholder="VD: iPhone 4s của bạn An" style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                </div>

                <!-- PHÂN QUYỀN TRUY CẬP NỘI DUNG -->
                <div style="background:#0b1329; border:1px solid #1e3a8a; border-radius:12px; padding:14px 16px; margin-bottom:16px;">
                    <div style="display:flex; justify-content:space-between; align-items:center; margin-bottom:10px; flex-wrap:wrap; gap:8px;">
                        <span style="font-size:13px; font-weight:bold; color:#60a5fa;">🔑 Phân Quyền Truy Cập Nội Dung:</span>
                        <div id="perm-presets-container" style="display:flex; gap:6px; flex-wrap:wrap;">
                            <button type="button" class="btn-action" onclick="setPermPreset('ALL')" style="font-size:11px; padding:4px 9px;">Chọn Tất Cả</button>
                            <button type="button" class="btn-action" onclick="setPermPreset('GUEST')" style="font-size:11px; padding:4px 9px; background:#581c87; color:#e9d5ff; border-color:#9333ea;">🌟 Chỉ Xem Tab Guest</button>
                            <button type="button" class="btn-action" onclick="setPermPreset('PRIVATE')" style="font-size:11px; padding:4px 9px; background:#831843; color:#fce7f3; border-color:#db2777;">🔒 Chỉ Tab Private</button>
                            <button type="button" class="btn-action" onclick="setPermPreset('NONE')" style="font-size:11px; padding:4px 9px;">Bỏ Chọn</button>
                        </div>
                    </div>
                    
                    <div id="perm-checkboxes-container" style="display:grid; grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); gap:10px; font-size:12.5px; color:#e2e8f0;">
                        <span style="color:#64748b; font-size:12px;">Đang tải danh sách Tab phân quyền...</span>
                    </div>
                    <div id="perm-notes-container" style="font-size:11.5px; color:#94a3b8; margin-top:8px; line-height:1.6;">
                    </div>
                </div>
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <label style="display:flex; align-items:center; gap:8px; font-size:13px; color:#cbd5e1; cursor:pointer;">
                        <input type="checkbox" id="acc-active-checkbox" checked style="width:16px; height:16px;"> Cho phép tài khoản này đăng nhập
                    </label>
                    <button type="button" id="btn-save-account" class="btn-submit" onclick="submitSaveAccount()" style="padding:10px 24px; font-size:13px; background:#2563eb !important; cursor:pointer !important; opacity:1 !important; pointer-events:auto !important;">
                        💾 Lưu Tài Khoản
                    </button>
                </div>
            </div>

            <!-- CARD DANH SÁCH TÀI KHOẢN ĐÃ CẤP -->
            <div class="existing-card" style="margin-top:0;">
                <div class="existing-header" style="margin-bottom:12px;">
                    <h3 style="font-size:15px; color:#f8fafc;">📋 Danh Sách Tài Khoản Đã Cấp (<span id="acc-count-display">0</span>)</h3>
                </div>
                <div id="acc-list-container">
                    <div style="text-align:center; padding:30px; color:#64748b;">Đang nạp danh sách tài khoản...</div>
                </div>
                <div style="margin-top:20px; padding-top:16px; border-top:1px solid #1e293b; display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                    <span style="font-size:12px; color:#94a3b8;">💡 Sau khi thêm hoặc sửa tài khoản, hãy bấm Đồng Bộ Lên Web để áp dụng tức thì.</span>
                    <button type="button" class="btn-secondary btn-green" onclick="triggerGitPush()" style="padding:10px 18px;">⚡ Đồng Bộ Lên Web Tức Thì</button>
                </div>
            </div>
        </div>



        <!-- ================================================================= -->
        <!-- PHÂN HỆ 3: QUẢN LÝ ẨN / HIỆN KHO ỨNG DỤNG (TRANG CHỦ & /APP/) -->
        <!-- ================================================================= -->
        <div id="module-visibility-container" style="display:none;">
            <div class="header" style="margin-bottom:20px;">
                <h1>👁️ Quản Lý Ẩn / Hiện Kho App</h1>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <button type="button" class="btn-secondary" onclick="loadVisibilityManager()">🔄 Làm Mới</button>
                    <a href="https://tomkidsrepo.cloud/" target="_blank" class="header-link">🌐 Trang Chủ</a>
                    <a href="https://tomkidsrepo.cloud/app/" target="_blank" class="header-link">📱 Kho App (/app)</a>
                </div>
            </div>

            <!-- CÀI ĐẶT HIỂN THỊ TRÊN TRANG CHỦ -->
            <div class="existing-card" style="margin-top:0; margin-bottom:20px;">
                <div class="existing-header" style="margin-bottom:12px;">
                    <h3 style="font-size:15px; color:#38bdf8;">🏠 Khu Ứng Dụng (Cài Trực Tiếp) Trên Trang Chủ</h3>
                    <button type="button" id="btn-toggle-home-section" class="btn-action" onclick="toggleHomeSection()" style="padding:7px 14px; font-size:12px; font-weight:bold;">
                        Đang tải...
                    </button>
                </div>
                <p style="font-size:12px; color:#94a3b8; margin-bottom:12px;">
                    Ẩn/hiện từng chuyên mục ở phần "KHO ỨNG DỤNG (CÀI TRỰC TIẾP)" trên trang chủ (không ảnh hưởng tới kho /app/):
                </p>
                <div id="vis-categories-grid" style="display:flex; flex-wrap:wrap; gap:8px;">
                    <span style="font-size:12px; color:#64748b;">Đang tải chuyên mục...</span>
                </div>
            </div>

            <!-- DANH SÁCH TỪNG ỨNG DỤNG -->
            <div class="existing-card" style="margin-top:0;">
                <div class="existing-header" style="flex-wrap:wrap; gap:10px;">
                    <h3 style="font-size:15px; color:#38bdf8;">📱 Danh Sách Ứng Dụng Trong ota_data.json</h3>
                    <span id="vis-apps-count" class="badge">Đang tải...</span>
                </div>

                <div style="display:grid; grid-template-columns: 1.5fr 1fr 1fr; gap:10px; margin-bottom:14px;">
                    <input type="text" id="vis-search-input" placeholder="🔍 Tìm tên ứng dụng..." oninput="renderVisibilityApps()" style="margin-top:0; padding:9px 12px; font-size:13px;">
                    <select id="vis-cat-filter" onchange="renderVisibilityApps()" style="margin-top:0; padding:9px 12px; font-size:13px;">
                        <option value="ALL">📂 Tất cả chuyên mục</option>
                    </select>
                    <select id="vis-status-filter" onchange="renderVisibilityApps()" style="margin-top:0; padding:9px 12px; font-size:13px;">
                        <option value="ALL">👁️ Tất cả trạng thái</option>
                        <option value="HOME">🏠 Đang hiện trên Trang chủ</option>
                        <option value="APP_ONLY">📱 Chỉ hiện ở /app/</option>
                        <option value="GUEST">🌟 Được hiện ở Tab Guest</option>
                        <option value="PRIVATE">🔒 Được hiện ở Tab Private</option>
                        <option value="HIDDEN">🙈 Đang ẩn hoàn toàn</option>
                    </select>
                </div>

                <div id="vis-bulk-bar" style="display:none; margin-bottom:12px; padding:10px 12px; background:#0b1222; border:1px solid #334155; border-radius:10px; align-items:center; justify-content:space-between; gap:10px; flex-wrap:wrap;">
                    <span id="vis-bulk-label" style="font-size:12px; color:#cbd5e1;">Thao tác nhanh chuyên mục đang chọn:</span>
                    <div style="display:flex; gap:8px;">
                        <button type="button" class="btn-action" onclick="bulkSelectedCategoryHome(true)" style="background:#14532d; color:#bbf7d0; border-color:#16a34a;">🏠 Hiện tất cả lên Trang chủ</button>
                        <button type="button" class="btn-action" onclick="bulkSelectedCategoryHome(false)" style="background:#7c2d12; color:#fed7aa; border-color:#ea580c;">🙈 Ẩn tất cả khỏi Trang chủ</button>
                    </div>
                </div>

                <div id="vis-apps-list">
                    <p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Đang tải danh sách ứng dụng...</p>
                </div>
            </div>

            <!-- FOOTER TOOLS CHO VISIBILITY -->
            <div class="footer-tools">
                <div style="font-size:12px; color:#94a3b8; display:flex; align-items:center;">
                    💡 Thay đổi được lưu ngay vào JSON. Bấm Đồng Bộ để đẩy lên tomkidsrepo.cloud!
                </div>
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openGitHubDesktop()">🖥️ Mở GitHub Desktop</button>
                    <button type="button" class="btn-secondary btn-green" onclick="triggerGitPush()">⚡ Đồng Bộ Lên Web Tức Thì</button>
                </div>
            </div>
        </div>

        <!-- ================================================================= -->
        <!-- PHÂN HỆ 5: QUẢN LÝ TAB & CHUYÊN MỤC TRÊN WEB APPSTORE -->
        <!-- ================================================================= -->
        <div id="module-tabs-container" style="display:none;">
            <div class="header" style="margin-bottom:20px;">
                <div class="logo-title">
                    <h1>🏷️ Quản Lý Tab Kho App</h1>
                    <span class="badge" style="background:#0ea5e9;">Cấu Hình Động</span>
                </div>
                <div style="display:flex; gap:8px; flex-wrap:wrap;">
                    <button type="button" class="btn-secondary" onclick="loadTabsManager()">🔄 Làm Mới</button>
                    <a href="https://tomkidsrepo.cloud/app/" target="_blank" class="header-link">📱 Mở Kho App (/app)</a>
                </div>
            </div>

            <!-- CARD FORM THÊM / SỬA TAB -->
            <div class="existing-card" style="margin-top:0; margin-bottom:20px;">
                <div class="existing-header" style="margin-bottom:14px;">
                    <h3 id="tab-form-title" style="font-size:15px; color:#38bdf8;">➕ Thêm Tab Mới</h3>
                    <button type="button" id="btn-tab-cancel-edit" class="btn-secondary" onclick="resetTabForm()" style="display:none; font-size:12px; padding:6px 12px;">Hủy Sửa</button>
                </div>

                <div style="display:grid; grid-template-columns: repeat(auto-fit, minmax(200px, 1fr)); gap:12px; margin-bottom:14px;">
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Mã Tab / ID (*):</label>
                        <input type="text" id="tab-id-input" placeholder="VD: VIP, NHAC, PHIM..." style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                        <span style="font-size:11px; color:#64748b; margin-top:3px; display:block;">Không dấu, viết liền (VD: VIP, HOT, PRIVATE)</span>
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Tên Hiển Thị (*):</label>
                        <input type="text" id="tab-name-input" placeholder="VD: VIP, Tuyển Chọn, Phim..." style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Biểu Tượng (Icon Emoji):</label>
                        <input type="text" id="tab-icon-input" placeholder="VD: 👑, 🎬, 🌟, 🔒, 📱" value="🏷️" style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Màu Chủ Đạo (Màu Nút & Viền):</label>
                        <div style="display:flex; gap:8px; align-items:center;">
                            <input type="color" id="tab-color-picker" value="#3b82f6" onchange="document.getElementById('tab-color-input').value = this.value" style="width:40px; height:38px; border:none; background:transparent; cursor:pointer;">
                            <input type="text" id="tab-color-input" value="#3b82f6" oninput="document.getElementById('tab-color-picker').value = this.value" placeholder="#3b82f6" style="flex:1; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                        </div>
                    </div>
                    <div>
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Loại Tab (*):</label>
                        <select id="tab-type-select" style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                            <option value="curated">🌟 Tuyển Chọn (Curated) - Bạn tự tích chọn app đưa vào</option>
                            <option value="category">📂 Chuyên Mục (Category) - Nhóm tự động theo thể loại</option>
                        </select>
                    </div>
                    <div style="grid-column: 1 / -1;">
                        <label style="display:block; font-size:12px; color:#94a3b8; margin-bottom:5px; font-weight:600;">Mô Tả / Ghi Chú:</label>
                        <input type="text" id="tab-desc-input" placeholder="VD: Dành riêng cho thành viên VIP, các app độc quyền..." style="width:100%; padding:10px 12px; border-radius:8px; border:1px solid #334155; background:#0f172a; color:#fff; font-size:13px;">
                    </div>
                </div>

                <div style="display:flex; gap:10px; justify-content:flex-end;">
                    <button type="button" id="btn-save-tab" class="btn-action btn-active" onclick="submitSaveTab()" style="padding:10px 24px; font-size:13px; font-weight:bold; background:#0284c7; color:#fff; border:none; border-radius:8px; cursor:pointer;">
                        💾 Lưu Tab
                    </button>
                </div>
            </div>

            <!-- CARD DANH SÁCH CÁC TAB HIỆN CÓ -->
            <div class="existing-card" style="margin-top:0;">
                <div class="existing-header" style="flex-wrap:wrap; gap:10px;">
                    <h3 style="font-size:15px; color:#38bdf8;">📋 Danh Sách Tab Hiện Tại (<span id="tabs-count-display">0</span>)</h3>
                    <span style="font-size:12px; color:#94a3b8;">Dùng nút ⬆️ ⬇️ để đổi thứ tự xuất hiện trên thanh cuộn Web App</span>
                </div>

                <div id="tabs-list-container">
                    <p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Đang tải danh sách Tab...</p>
                </div>
            </div>

            <!-- FOOTER TOOLS CHO TABS -->
            <div class="footer-tools">
                <div style="font-size:12px; color:#94a3b8; display:flex; align-items:center;">
                    💡 Khi thêm/sửa/xóa Tab, toàn bộ mục Ẩn/Hiện Kho App, Phân Quyền Tài Khoản và Web App (/app/) đều tự động đồng bộ theo!
                </div>
                <div style="display:flex; gap:10px;">
                    <button type="button" class="btn-secondary" onclick="openGitHubDesktop()">🖥️ Mở GitHub Desktop</button>
                    <button type="button" class="btn-secondary btn-green" onclick="triggerGitPush()">⚡ Đồng Bộ Lên Web Tức Thì</button>
                </div>
            </div>
        </div>

    </div>

    <!-- ================================================================= -->
    <!-- SCRIPT ĐIỀU KHIỂN CLIENT TOÀN DIỆN -->
    <!-- ================================================================= -->
    <script>
        var chosenFiles = [];

        var dropzone = document.getElementById('dropzone');
        if (dropzone) {
            ['dragenter', 'dragover'].forEach(function(eName) {
                dropzone.addEventListener(eName, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    dropzone.classList.add('dragover');
                });
            });
            ['dragleave', 'drop'].forEach(function(eName) {
                dropzone.addEventListener(eName, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    dropzone.classList.remove('dragover');
                });
            });
            dropzone.addEventListener('drop', function(e) {
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    onFileSelected(e.dataTransfer.files);
                }
            });
        }

        function onFileSelected(files) {
            if (!files || files.length === 0) return;
            chosenFiles = Array.prototype.slice.call(files);
            document.getElementById('dropzone').style.display = 'none';
            var card = document.getElementById('file-selected-card');
            card.style.display = 'flex';

            if (chosenFiles.length === 1) {
                var f = chosenFiles[0];
                document.getElementById('file-selected-name').innerText = '📦 ' + f.name;
                var sizeMB = (f.size / (1024 * 1024)).toFixed(2);
                document.getElementById('file-selected-size').innerText = 'Dung lượng: ' + sizeMB + ' MB';
            } else {
                var totalBytes = 0;
                for (var i = 0; i < chosenFiles.length; i++) {
                    totalBytes += chosenFiles[i].size;
                }
                var totalMB = (totalBytes / (1024 * 1024)).toFixed(2);
                document.getElementById('file-selected-name').innerText = '📦 Đã chọn ' + chosenFiles.length + ' files cùng lúc';
                var names = chosenFiles.map(function(f){ return f.name; }).slice(0, 3).join(', ');
                if (chosenFiles.length > 3) names += '... và ' + (chosenFiles.length - 3) + ' file khác';
                document.getElementById('file-selected-size').innerText = 'Tổng dung lượng: ' + totalMB + ' MB (' + names + ')';
            }
        }

        function removeSelectedFile() {
            chosenFiles = [];
            document.getElementById('file-input').value = '';
            document.getElementById('dropzone').style.display = 'block';
            document.getElementById('file-selected-card').style.display = 'none';
        }

        function loadIncomingFilesList() {
            fetch('/api/list-incoming')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var sel = document.getElementById('incoming-select');
                    sel.innerHTML = '';
                    if (!data.files || data.files.length === 0) {
                        sel.innerHTML = '<option value="">(Thư mục incoming/ hiện đang trống)</option>';
                        return;
                    }
                    data.files.forEach(function(f) {
                        var opt = document.createElement('option');
                        opt.value = f;
                        opt.innerText = f;
                        sel.appendChild(opt);
                    });
                });
        }

        function uploadSingleFile(file, category, releaseUrl, onProgress, onDone) {
            var formData = new FormData();
            formData.append('source_type', 'file');
            formData.append('category', category);
            formData.append('release_url', releaseUrl);
            if (!chosenFiles || chosenFiles.length <= 1) {
                var cName = (document.getElementById('custom-name-input') || {}).value || '';
                var cVer = (document.getElementById('custom-version-input') || {}).value || '';
                if (cName.trim()) formData.append('custom_name', cName.trim());
                if (cVer.trim()) formData.append('custom_version', cVer.trim());
            }
            var showHomeEl = document.getElementById('ota-show-on-home');
            formData.append('show_on_home', (showHomeEl && showHomeEl.checked) ? 'true' : 'false');
            formData.append('file', file);

            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/process', true);
            xhr.upload.onprogress = function(evt) {
                if (evt.lengthComputable && onProgress) {
                    var percent = Math.round((evt.loaded / evt.total) * 100);
                    onProgress(percent);
                }
            };
            xhr.onload = function() {
                try {
                    var res = JSON.parse(xhr.responseText);
                    onDone(null, res);
                } catch(err) {
                    onDone('Lỗi phản hồi máy chủ: ' + xhr.responseText);
                }
            };
            xhr.onerror = function() {
                onDone('Không thể kết nối đến máy chủ xử lý!');
            };
            xhr.send(formData);
        }

        function handleFormSubmit(e) {
            e.preventDefault();
            var alertBox = document.getElementById('alert-box');
            alertBox.style.display = 'none';

            var category = document.getElementById('category-select').value;
            var releaseUrl = document.getElementById('release-url-input').value;

            var progressWrap = document.getElementById('progress-wrap');
            var progressFill = document.getElementById('progress-bar-fill');
            var progressText = document.getElementById('progress-text');

            if (currentSourceTab === 'file') {
                if (!chosenFiles || chosenFiles.length === 0) {
                    alert("Vui lòng chọn hoặc kéo thả ít nhất 1 file từ máy tính!");
                    return;
                }

                var btn = document.getElementById('btn-submit');
                btn.disabled = true;
                progressWrap.style.display = 'block';

                var totalFiles = chosenFiles.length;
                var currentIndex = 0;
                var batchResults = [];

                function processNext() {
                    if (currentIndex >= totalFiles) {
                        btn.disabled = false;
                        btn.innerHTML = '<span>⚡ Bắt Đầu Xử Lý Tự Động</span>';
                        progressWrap.style.display = 'none';
                        removeSelectedFile();

                        var successCount = 0;
                        var html = '<b>🎉 HOÀN TẤT XỬ LÝ ' + totalFiles + ' FILE:</b><br><ul style="margin: 8px 0 10px 20px; font-size:13px;">';
                        batchResults.forEach(function(r) {
                            if (r.success) {
                                successCount++;
                                html += '<li>✅ <b>' + r.name + '</b> (' + (r.version || '') + ') - Mục: ' + r.cat + '</li>';
                            } else {
                                html += '<li style="color:#f87171;">❌ <b>' + r.file + '</b>: ' + r.error + '</li>';
                            }
                        });
                        html += '</ul>';
                        html += '<b>Tổng kết: Đã đưa ' + successCount + '/' + totalFiles + ' file lên Tomkids AppStore & GitHub Releases thành công!</b><br>';
                        html += '👉 Hãy bấm nút <b>"Git Commit & Push Lên Web"</b> ở góc dưới để cập nhật lên tomkidsrepo.cloud!';
                        alertBox.className = 'alert-box alert-success';
                        alertBox.innerHTML = html;
                        alertBox.style.display = 'block';
                        return;
                    }

                    var currentFile = chosenFiles[currentIndex];
                    var fileNum = currentIndex + 1;
                    btn.innerHTML = '<span>⏳ Đang xử lý file [' + fileNum + '/' + totalFiles + ']... Vui lòng đợi</span>';
                    progressFill.style.width = '0%';
                    progressText.innerText = '[' + fileNum + '/' + totalFiles + '] Đang tải ' + currentFile.name + ': 0%';

                    uploadSingleFile(currentFile, category, releaseUrl, function(pct) {
                        progressFill.style.width = pct + '%';
                        progressText.innerText = '[' + fileNum + '/' + totalFiles + '] Đang tải & bóc tách ' + currentFile.name + ': ' + pct + '%';
                    }, function(err, res) {
                        if (err || !res.success) {
                            batchResults.push({
                                file: currentFile.name,
                                success: false,
                                error: err || (res ? res.error : 'Lỗi không xác định')
                            });
                        } else {
                            batchResults.push({
                                file: currentFile.name,
                                success: true,
                                name: res.app_name,
                                version: res.version,
                                cat: res.category
                            });
                        }
                        currentIndex++;
                        processNext();
                    });
                }

                processNext();
                return;
            }

            // Tab Link hoặc Incoming đơn lẻ
            var formData = new FormData();
            formData.append('category', category);
            formData.append('release_url', releaseUrl);
            var cNameSingle = (document.getElementById('custom-name-input') || {}).value || '';
            var cVerSingle = (document.getElementById('custom-version-input') || {}).value || '';
            if (cNameSingle.trim()) formData.append('custom_name', cNameSingle.trim());
            if (cVerSingle.trim()) formData.append('custom_version', cVerSingle.trim());
            var showHomeEl = document.getElementById('ota-show-on-home');
            formData.append('show_on_home', (showHomeEl && showHomeEl.checked) ? 'true' : 'false');
            formData.append('source_type', currentSourceTab);

            if (currentSourceTab === 'link') {
                var link = document.getElementById('link-input').value.trim();
                if (!link) {
                    alert("Vui lòng dán link file cần đưa lên!");
                    return;
                }
                formData.append('link', link);
            } else if (currentSourceTab === 'incoming') {
                var incFile = document.getElementById('incoming-select').value;
                if (!incFile) {
                    alert("Vui lòng chọn 1 file trong thư mục incoming/ hoặc bấm 'Xử Lý TOÀN BỘ File Trong Thư Mục'!");
                    return;
                }
                formData.append('incoming_file', incFile);
            }

            var btn = document.getElementById('btn-submit');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Đang xử lý tự động... Vui lòng đợi</span>';

            progressWrap.style.display = 'block';
            progressFill.style.width = '0%';

            var xhr = new XMLHttpRequest();
            xhr.open('POST', '/api/process', true);

            xhr.upload.onprogress = function(evt) {
                if (evt.lengthComputable) {
                    var percent = Math.round((evt.loaded / evt.total) * 100);
                    progressFill.style.width = percent + '%';
                    progressText.innerText = 'Đang tải file lên máy chủ: ' + percent + '%';
                }
            };

            xhr.onload = function() {
                btn.disabled = false;
                btn.innerHTML = '<span>⚡ Bắt Đầu Xử Lý Tự Động</span>';
                progressWrap.style.display = 'none';

                try {
                    var res = JSON.parse(xhr.responseText);
                    if (res.success) {
                        alertBox.className = 'alert-box alert-success';
                        alertBox.innerHTML = '<b>🎉 THÀNH CÔNG!</b><br>' +
                                             '• Đã bóc tách: <b>' + res.app_name + '</b> (' + (res.version || '') + ')<br>' +
                                             '• Bundle ID: <code>' + (res.bundle_id || 'N/A') + '</code><br>' +
                                             '• Đã cập nhật vào chuyên mục: <b>' + res.category + '</b><br><br>' +
                                             '👉 Bạn hãy bấm <b>"Git Commit & Push"</b> ở góc dưới để đưa lên web!';
                        alertBox.style.display = 'block';
                    } else {
                        alertBox.className = 'alert-box alert-error';
                        alertBox.innerText = 'Lỗi: ' + res.error;
                        alertBox.style.display = 'block';
                    }
                } catch(err) {
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerText = 'Lỗi phản hồi máy chủ: ' + xhr.responseText;
                    alertBox.style.display = 'block';
                }
            };

            xhr.onerror = function() {
                btn.disabled = false;
                btn.innerHTML = '<span>⚡ Bắt Đầu Xử Lý Tự Động</span>';
                progressWrap.style.display = 'none';
                alertBox.className = 'alert-box alert-error';
                alertBox.innerText = 'Không thể kết nối đến máy chủ xử lý!';
                alertBox.style.display = 'block';
            };

            xhr.send(formData);
        }

        function processAllIncoming() {
            if (!confirm("Hệ thống sẽ tự động quét toàn bộ file (.ipa, .deb, .pdf, .m4r, v.v.) trong thư mục incoming/, bóc tách metadata, tạo manifest, và tự động upload lên GitHub Releases (OTA-Storage). Bạn có muốn tiếp tục?")) {
                return;
            }

            var alertBox = document.getElementById('alert-box');
            alertBox.style.display = 'none';

            var progressWrap = document.getElementById('progress-wrap');
            var progressFill = document.getElementById('progress-bar-fill');
            var progressText = document.getElementById('progress-text');
            progressWrap.style.display = 'block';
            progressFill.style.width = '100%';
            progressText.innerText = '⚡ Đang quét và xử lý hàng loạt toàn bộ file trong thư mục incoming/...';

            var btn = document.getElementById('btn-submit');
            btn.disabled = true;

            var incForm = new FormData();
            var showHomeEl = document.getElementById('ota-show-on-home');
            incForm.append('show_on_home', (showHomeEl && showHomeEl.checked) ? 'true' : 'false');
            fetch('/api/process-all-incoming', { method: 'POST', body: incForm })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    btn.disabled = false;
                    progressWrap.style.display = 'none';
                    if (data.success) {
                        var html = '<b>🎉 HOÀN TẤT XỬ LÝ HÀNG LOẠT: ' + data.processed + '/' + data.total + ' FILE THÀNH CÔNG!</b><br><ul style="margin: 8px 0 10px 20px; font-size:13px;">';
                        data.results.forEach(function(r) {
                            if (r.success) {
                                html += '<li>✅ <b>' + r.name + '</b> (' + (r.version || '') + ') - Mục: ' + r.category + '</li>';
                            } else {
                                html += '<li style="color:#f87171;">❌ <b>' + r.file + '</b>: ' + r.error + '</li>';
                            }
                        });
                        html += '</ul>';
                        html += '👉 Tất cả file đã được đẩy lên GitHub Releases (OTA-Storage).<br>Hãy bấm <b>"Git Commit & Push Lên Web"</b> để hoàn tất đồng bộ lên tomkidsrepo.cloud!';
                        alertBox.className = 'alert-box alert-success';
                        alertBox.innerHTML = html;
                        alertBox.style.display = 'block';
                        loadIncomingFilesList();
                    } else {
                        alertBox.className = 'alert-box alert-error';
                        alertBox.innerText = 'Lỗi: ' + data.error;
                        alertBox.style.display = 'block';
                    }
                })
                .catch(function(err) {
                    btn.disabled = false;
                    progressWrap.style.display = 'none';
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerText = 'Lỗi kết nối máy chủ: ' + err;
                    alertBox.style.display = 'block';
                });
        }


        // ─── CÀI ĐẶT NHANH DEB MODULE LOGIC ──────────────────────────────
        var currentDebSourceTab = 'file';
        var quickInstallItems = [];

        window.switchDebSourceTab = function(tab, ev) {
            if (ev) {
                try { ev.preventDefault(); ev.stopPropagation(); } catch(ignore) {}
            }
            currentDebSourceTab = tab;
            var tabs = ['file', 'link', 'incoming', 'manual'];
            tabs.forEach(function(t) {
                var btn = document.getElementById('btn-debtab-' + t);
                var sec = document.getElementById('deb-sec-' + t);
                if (btn) btn.className = (t === tab) ? 'tab-btn active' : 'tab-btn';
                if (sec) sec.style.display = (t === tab) ? 'block' : 'none';
            });

            if (tab === 'incoming') {
                try { loadDebIncomingList(); } catch(e) {}
            }
        };

        var debDropzone = document.getElementById('deb-dropzone');
        if (debDropzone) {
            ['dragenter', 'dragover'].forEach(function(eName) {
                debDropzone.addEventListener(eName, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    debDropzone.classList.add('dragover');
                });
            });
            ['dragleave', 'drop'].forEach(function(eName) {
                debDropzone.addEventListener(eName, function(e) {
                    e.preventDefault(); e.stopPropagation();
                    debDropzone.classList.remove('dragover');
                });
            });
            debDropzone.addEventListener('drop', function(e) {
                if (e.dataTransfer && e.dataTransfer.files && e.dataTransfer.files.length > 0) {
                    onDebFileSelected(e.dataTransfer.files);
                }
            });
        }

        function onDebFileSelected(files) {
            if (!files || files.length === 0) return;
            var file = files[0];
            if (!file.name.toLowerCase().endsWith('.deb')) {
                alert("Vui lòng chọn file định dạng .deb!");
                return;
            }

            var debCard = document.getElementById('deb-file-card');
            var debDrop = document.getElementById('deb-dropzone');
            debDrop.style.display = 'none';
            debCard.style.display = 'flex';
            document.getElementById('deb-file-card-name').innerText = '📦 ' + file.name;
            document.getElementById('deb-file-card-size').innerText = '⏳ Đang bóc tách control file từ gói DEB...';

            var formData = new FormData();
            formData.append('source_type', 'file');
            formData.append('file', file);

            fetch('/api/quickinstall/extract-deb', { method: 'POST', body: formData })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        var info = data.info;
                        document.getElementById('deb-file-card-size').innerText = '✅ Đã bóc tách: ' + (info.name || info.package_id) + ' (v' + (info.version || '1.0') + ')';
                        document.getElementById('deb-temp-filename').value = data.temp_file || '';
                        
                        // Tự động điền form
                        if (!document.getElementById('deb-name').value || document.getElementById('deb-edit-mode').value === '0') {
                            document.getElementById('deb-name').value = 'Cài tweak ' + (info.name || info.package_id);
                        }
                        document.getElementById('deb-pkg-id').value = info.package_id || '';
                        document.getElementById('deb-version').value = info.version || '1.0';
                        if (info.description && !document.getElementById('deb-desc').value) {
                            document.getElementById('deb-desc').value = info.description;
                        }
                        updateDebPreview();
                    } else {
                        document.getElementById('deb-file-card-size').innerText = '❌ Lỗi bóc tách: ' + data.error;
                        alert('Không thể đọc metadata gói DEB: ' + data.error);
                    }
                })
                .catch(function(err) {
                    document.getElementById('deb-file-card-size').innerText = '❌ Lỗi kết nối: ' + err;
                });
        }

        function removeDebSelectedFile() {
            document.getElementById('deb-file-input').value = '';
            document.getElementById('deb-dropzone').style.display = 'block';
            document.getElementById('deb-file-card').style.display = 'none';
            document.getElementById('deb-temp-filename').value = '';
        }

        function extractDebFromLink(ev) {
            var link = document.getElementById('deb-link-input').value.trim();
            if (!link) {
                alert("Vui lòng dán link tải file .deb!");
                return;
            }

            var btn = ev ? ev.target : null;
            if (btn) {
                btn.disabled = true;
                btn.innerText = '⏳ Đang tải...';
            }

            var formData = new FormData();
            formData.append('source_type', 'link');
            formData.append('link', link);

            fetch('/api/quickinstall/extract-deb', { method: 'POST', body: formData })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '🔍 Đọc DEB';
                    }
                    if (data.success) {
                        var info = data.info;
                        document.getElementById('deb-temp-filename').value = data.temp_file || '';
                        document.getElementById('deb-name').value = 'Cài tweak ' + (info.name || info.package_id);
                        document.getElementById('deb-pkg-id').value = info.package_id || '';
                        document.getElementById('deb-version').value = info.version || '1.0';
                        if (info.description) document.getElementById('deb-desc').value = info.description;
                        updateDebPreview();
                        alert('✅ Đã tải và bóc tách metadata DEB thành công!');
                    } else {
                        alert('Lỗi: ' + data.error);
                    }
                })
                .catch(function(err) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '🔍 Đọc DEB';
                    }
                    alert('Lỗi kết nối: ' + err);
                });
        }

        function loadDebIncomingList() {
            fetch('/api/list-incoming')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var sel = document.getElementById('deb-incoming-select');
                    if (!sel) return;
                    sel.innerHTML = '';
                    var debFiles = (data.files || []).filter(function(f){ return f.toLowerCase().endsWith('.deb'); });
                    if (debFiles.length === 0) {
                        sel.innerHTML = '<option value="">(Không có file .deb nào trong incoming/)</option>';
                        return;
                    }
                    debFiles.forEach(function(f) {
                        var opt = document.createElement('option');
                        opt.value = f;
                        opt.innerText = f;
                        sel.appendChild(opt);
                    });
                });
        }

        function extractDebFromIncoming(ev) {
            var sel = document.getElementById('deb-incoming-select');
            var incFile = sel ? sel.value : '';
            if (!incFile) {
                alert("Vui lòng chọn 1 file .deb trong thư mục incoming/!");
                return;
            }

            var formData = new FormData();
            formData.append('source_type', 'incoming');
            formData.append('incoming_file', incFile);

            fetch('/api/quickinstall/extract-deb', { method: 'POST', body: formData })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        var info = data.info;
                        document.getElementById('deb-temp-filename').value = incFile;
                        document.getElementById('deb-name').value = 'Cài tweak ' + (info.name || info.package_id);
                        document.getElementById('deb-pkg-id').value = info.package_id || '';
                        document.getElementById('deb-version').value = info.version || '1.0';
                        if (info.description) document.getElementById('deb-desc').value = info.description;
                        updateDebPreview();
                        alert('✅ Đã bóc tách thông tin từ ' + incFile + ' thành công!');
                    } else {
                        alert('Lỗi: ' + data.error);
                    }
                });
        }

        function updateDebPreview() {
            var elName = document.getElementById('deb-name');
            var elIos = document.getElementById('deb-ios-range');
            var elColor = document.getElementById('deb-color');
            var elDesc = document.getElementById('deb-desc');
            var elNote = document.getElementById('deb-note');

            if (!elName || !elColor) return;

            var name = elName.value.trim() || 'Tên Nút Hiển Thị Cài Nhanh';
            var badgeText = elIos ? elIos.value.trim() : '';
            var color = elColor.value || 'green';
            var desc = elDesc ? elDesc.value.trim() : '';
            var note = elNote ? elNote.value.trim() : '';

            var btn = document.getElementById('deb-preview-btn');
            var nameSpan = document.getElementById('deb-preview-name');
            var badgeSpan = document.getElementById('deb-preview-badge');
            var descP = document.getElementById('deb-preview-desc');
            var noteP = document.getElementById('deb-preview-note');

            if (btn) {
                var bg = '#16a34a';
                if (color === 'blue') bg = '#2563eb';
                else if (color === 'orange') bg = '#ea580c';
                btn.style.background = bg;
            }

            if (nameSpan) nameSpan.innerText = name;

            if (badgeSpan) {
                if (badgeText) {
                    badgeSpan.style.display = 'inline-block';
                    badgeSpan.innerText = badgeText;
                } else {
                    badgeSpan.style.display = 'none';
                }
            }

            if (descP) {
                if (desc) {
                    descP.style.display = 'block';
                    descP.innerText = desc;
                } else {
                    descP.style.display = 'none';
                }
            }

            if (noteP) {
                if (note) {
                    noteP.style.display = 'block';
                    noteP.innerText = 'ⓘ ' + note;
                } else {
                    noteP.style.display = 'none';
                }
            }
        }

        function loadQuickInstallList() {
            fetch('/api/quickinstall/list')
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    var container = document.getElementById('deb-items-list');
                    var badge = document.getElementById('deb-count-badge');
                    if (!container) return;

                    if (!data.success || !data.items || data.items.length === 0) {
                        container.innerHTML = '<p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Chưa có nút cài nhanh nào. Hãy thêm nút đầu tiên ở trên!</p>';
                        if (badge) badge.innerText = '0 nút';
                        quickInstallItems = [];
                        return;
                    }

                    quickInstallItems = data.items;
                    if (badge) badge.innerText = quickInstallItems.length + ' nút';

                    var html = '';
                    quickInstallItems.forEach(function(item, idx) {
                        var isHidden = item.hidden === true;
                        var colorDot = item.color === 'blue' ? '🔵' : (item.color === 'orange' ? '🟠' : '🟢');
                        var badgeHtml = item.ios_range ? '<span style="background:#0f3460; color:#60a5fa; font-size:10px; padding:2px 6px; border-radius:10px; margin-left:6px;">' + item.ios_range + '</span>' : '';
                        var hiddenBadge = isHidden ? '<span style="background:#7f1d1d; color:#fca5a5; font-size:10px; padding:2px 7px; border-radius:10px; margin-left:6px;">🙈 Đang ẩn</span>' : '';
                        var itemStyle = isHidden ? ' style="opacity:0.6; border-style:dashed; border-color:#7f1d1d;"' : '';

                        html += '<div class="existing-item"' + itemStyle + '>' +
                                    '<div class="item-info">' +
                                        '<div class="item-title">' +
                                            '<span style="color:#64748b; font-size:12px; margin-right:4px;">#' + (idx + 1) + '</span> ' +
                                            colorDot + ' <b>' + item.name + '</b>' + badgeHtml + hiddenBadge +
                                        '</div>' +
                                        '<div class="item-pkg">ID: ' + item.package_id + ' (v' + (item.version || '1.0') + ')</div>' +
                                        (item.description ? '<div class="item-desc">' + item.description + '</div>' : '') +
                                        (item.note ? '<div class="item-note">ⓘ ' + item.note + '</div>' : '') +
                                    '</div>' +
                                    '<div class="item-actions">' +
                                        (idx > 0 ? '<button type="button" class="btn-action" title="Di chuyển lên" onclick="moveQuickInstallItem(' + idx + ', -1)">⬆️</button>' : '') +
                                        (idx < quickInstallItems.length - 1 ? '<button type="button" class="btn-action" title="Di chuyển xuống" onclick="moveQuickInstallItem(' + idx + ', 1)">⬇️</button>' : '') +
                                        '<button type="button" class="btn-action" title="' + (isHidden ? 'Hiện lại nút trên trang chủ' : 'Ẩn nút khỏi trang chủ') + '" onclick="toggleHideQuickInstallItem(' + idx + ')" style="' + (isHidden ? 'background:#14532d; color:#bbf7d0; border-color:#16a34a;' : 'background:#451a03; color:#fed7aa; border-color:#d97706;') + '">' + (isHidden ? '👁️ Hiện' : '🙈 Ẩn') + '</button>' +
                                        '<button type="button" class="btn-action" title="Chỉnh sửa nút này" onclick="editQuickInstallItem(' + idx + ')">✏️ Sửa</button>' +
                                        '<button type="button" class="btn-action btn-action-del" title="Xóa nút này" onclick="deleteQuickInstallItem(' + idx + ')">🗑️</button>' +
                                    '</div>' +
                                '</div>';
                    });
                    container.innerHTML = html;
                })
                .catch(function(err) {
                    var container = document.getElementById('deb-items-list');
                    if (container) container.innerHTML = '<p style="color:#f87171; font-size:13px; text-align:center;">Lỗi tải danh sách: ' + err + '</p>';
                });
        }

        function moveQuickInstallItem(idx, dir) {
            if (idx < 0 || idx >= quickInstallItems.length) return;
            var targetIdx = idx + dir;
            if (targetIdx < 0 || targetIdx >= quickInstallItems.length) return;

            var temp = quickInstallItems[idx];
            quickInstallItems[idx] = quickInstallItems[targetIdx];
            quickInstallItems[targetIdx] = temp;

            var newOrder = quickInstallItems.map(function(it){ return it.package_id; });

            fetch('/api/quickinstall/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ order: newOrder })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    loadQuickInstallList();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function editQuickInstallItem(idx) {
            var item = quickInstallItems[idx];
            if (!item) return;

            document.getElementById('deb-edit-mode').value = '1';
            document.getElementById('deb-edit-orig-pkg').value = item.package_id || '';
            document.getElementById('deb-name').value = item.name || '';
            document.getElementById('deb-pkg-id').value = item.package_id || '';
            document.getElementById('deb-version').value = item.version || '1.0';
            document.getElementById('deb-ios-range').value = item.ios_range || '';
            document.getElementById('deb-color').value = item.color || 'green';
            document.getElementById('deb-desc').value = item.description || '';
            document.getElementById('deb-note').value = item.note || '';

            document.getElementById('btn-deb-submit').innerHTML = '<span>💾 Lưu Thay Đổi Cài Đặt Nhanh</span>';
            document.getElementById('btn-deb-cancel-edit').style.display = 'inline-flex';

            switchDebSourceTab('manual');
            updateDebPreview();

            document.getElementById('deb-form').scrollIntoView({ behavior: 'smooth' });
        }

        function cancelDebEdit() {
            document.getElementById('deb-edit-mode').value = '0';
            document.getElementById('deb-edit-orig-pkg').value = '';
            document.getElementById('deb-name').value = '';
            document.getElementById('deb-pkg-id').value = '';
            document.getElementById('deb-version').value = '';
            document.getElementById('deb-ios-range').value = '';
            document.getElementById('deb-color').value = 'green';
            document.getElementById('deb-desc').value = '';
            document.getElementById('deb-note').value = '';
            document.getElementById('deb-temp-filename').value = '';

            document.getElementById('btn-deb-submit').innerHTML = '<span>⚡ Lưu Nút & Tự Động Build Vào Cydia</span>';
            document.getElementById('btn-deb-cancel-edit').style.display = 'none';

            removeDebSelectedFile();
            switchDebSourceTab('file');
            updateDebPreview();
        }

        function deleteQuickInstallItem(idx) {
            var item = quickInstallItems[idx];
            if (!item) return;
            var pkgId = item.package_id;

            if (!confirm("Bạn có chắc chắn muốn XÓA nút cài đặt nhanh '" + (item.name || pkgId) + "' khỏi trang chủ tomkidsrepo.cloud?")) {
                return;
            }

            var formData = new FormData();
            formData.append('package_id', pkgId);

            fetch('/api/quickinstall/delete', { method: 'POST', body: formData })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (data.success) {
                        alert(data.message);
                        loadQuickInstallList();
                    } else {
                        alert('Lỗi: ' + data.error);
                    }
                });
        }

        function toggleHideQuickInstallItem(idx) {
            var item = quickInstallItems[idx];
            if (!item) return;

            fetch('/api/quickinstall/toggle-hide', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ package_id: item.package_id })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    loadQuickInstallList();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

        // ─── MODULE 3: QUẢN LÝ ẨN/HIỆN KHO ỨNG DỤNG ──────────────────────
        var visOtaData = {};
        var visHomeSettings = { hide_ota_section: false, hidden_categories: [] };
        var visCategoriesList = [];

        function escapeVisHtml(str) {
            return String(str || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function loadVisibilityManager() {
            fetch('/api/apps/visibility-data?t=' + Date.now())
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (!data.success) {
                        alert('Lỗi tải dữ liệu: ' + (data.error || 'Không xác định'));
                        return;
                    }
                    visOtaData = data.ota_data || {};
                    visHomeSettings = data.home_settings || { hide_ota_section: false, hidden_categories: [] };
                    cachedTabs = data.tabs || cachedTabs;
                    visCategoriesList = Object.keys(visOtaData);
                    populateVisCategoryFilter();
                    populateVisStatusFilter();
                    renderVisibilityHomeControls();
                    renderVisibilityApps();
                })
                .catch(function(err) {
                    var listEl = document.getElementById('vis-apps-list');
                    if (listEl) listEl.innerHTML = '<p style="color:#f87171; font-size:13px; text-align:center;">Lỗi tải dữ liệu: ' + err + '</p>';
                });
        }

        function populateVisCategoryFilter() {
            var sel = document.getElementById('vis-cat-filter');
            if (!sel) return;
            var currentVal = sel.value || 'ALL';
            var html = '<option value="ALL">📂 Tất cả chuyên mục</option>';
            visCategoriesList.forEach(function(cat) {
                var count = (visOtaData[cat] || []).length;
                html += '<option value="' + escapeVisHtml(cat) + '">' + escapeVisHtml(cat) + ' (' + count + ')</option>';
            });
            sel.innerHTML = html;
            if (currentVal === 'ALL' || visCategoriesList.indexOf(currentVal) !== -1) {
                sel.value = currentVal;
            }
        }

        function populateVisStatusFilter() {
            var sel = document.getElementById('vis-status-filter');
            if (!sel) return;
            var currentVal = sel.value || 'ALL';
            var html = '<option value="ALL">👁️ Tất cả trạng thái</option>' +
                       '<option value="HOME">🏠 Đang hiện trên Trang chủ</option>' +
                       '<option value="APP_ONLY">📱 Chỉ hiện ở /app/</option>';
            for (var i = 0; i < cachedTabs.length; i++) {
                var tab = cachedTabs[i];
                if (tab.type === 'curated') {
                    html += '<option value="CURATED_' + tab.id + '">' + (tab.icon || '🌟') + ' Được hiện ở Tab ' + escapeVisHtml(tab.name) + '</option>';
                }
            }
            html += '<option value="HIDDEN">🙈 Đang ẩn hoàn toàn</option>';
            sel.innerHTML = html;
            sel.value = currentVal;
        }

        function isAppInCuratedTab(app, tab) {
            if (!app || !tab) return false;
            var field = tab.field || ('show_on_' + tab.id.toLowerCase());
            if (app[field] === true) return true;
            if (app.custom_tabs && app.custom_tabs.indexOf(tab.id) !== -1) return true;
            return false;
        }

        function renderVisibilityHomeControls() {
            var masterBtn = document.getElementById('btn-toggle-home-section');
            var hideAll = visHomeSettings.hide_ota_section === true;
            if (masterBtn) {
                if (hideAll) {
                    masterBtn.innerText = '🙈 Đang ẨN cả mục trên Trang Chủ (Bấm để Hiện)';
                    masterBtn.style.background = '#7f1d1d';
                    masterBtn.style.color = '#fecaca';
                    masterBtn.style.borderColor = '#dc2626';
                } else {
                    masterBtn.innerText = '👁️ Đang HIỆN mục trên Trang Chủ (Bấm để Ẩn)';
                    masterBtn.style.background = '#14532d';
                    masterBtn.style.color = '#bbf7d0';
                    masterBtn.style.borderColor = '#16a34a';
                }
            }

            var grid = document.getElementById('vis-categories-grid');
            if (!grid) return;
            var hiddenCats = visHomeSettings.hidden_categories || [];
            if (visCategoriesList.length === 0) {
                grid.innerHTML = '<span style="font-size:12px; color:#64748b;">Chưa có chuyên mục nào trong ota_data.json.</span>';
                return;
            }

            var html = '';
            visCategoriesList.forEach(function(cat, cIdx) {
                var isCatHidden = hiddenCats.indexOf(cat) !== -1;
                var totalCount = (visOtaData[cat] || []).length;
                var homeCount = (visOtaData[cat] || []).filter(function(a) {
                    return a.hidden !== true && a.show_on_home !== false;
                }).length;

                var btnStyle = isCatHidden
                    ? 'background:#1e1b24; color:#fca5a5; border:1px dashed #ef4444; padding:8px 12px; border-radius:10px; font-size:12px; cursor:pointer;'
                    : 'background:#0f2942; color:#bae6fd; border:1px solid #0284c7; padding:8px 12px; border-radius:10px; font-size:12px; cursor:pointer;';

                html += '<button type="button" onclick="toggleHomeCategoryIdx(' + cIdx + ')" style="' + btnStyle + '">' +
                            (isCatHidden ? '🙈 ' : '👁️ ') +
                            '<b>' + escapeVisHtml(cat) + '</b> ' +
                            '<span style="opacity:0.8;">(' + homeCount + '/' + totalCount + ' ở Trang chủ)</span>' +
                        '</button>';
            });
            grid.innerHTML = html;
        }

        function renderVisibilityApps() {
            var container = document.getElementById('vis-apps-list');
            var countBadge = document.getElementById('vis-apps-count');
            var searchInput = document.getElementById('vis-search-input');
            var catFilterEl = document.getElementById('vis-cat-filter');
            var statusFilterEl = document.getElementById('vis-status-filter');
            var bulkBar = document.getElementById('vis-bulk-bar');
            var bulkLabel = document.getElementById('vis-bulk-label');

            if (!container) return;

            var keyword = (searchInput ? searchInput.value : '').trim().toLowerCase();
            var catFilter = catFilterEl ? catFilterEl.value : 'ALL';
            var statusFilter = statusFilterEl ? statusFilterEl.value : 'ALL';

            if (bulkBar) {
                if (catFilter !== 'ALL') {
                    bulkBar.style.display = 'flex';
                    if (bulkLabel) bulkLabel.innerText = 'Thao tác nhanh chuyên mục "' + catFilter + '":';
                } else {
                    bulkBar.style.display = 'none';
                }
            }

            var html = '';
            var totalVisibleMatches = 0;
            var totalAppsAll = 0;

            visCategoriesList.forEach(function(cat, cIdx) {
                var list = visOtaData[cat] || [];
                totalAppsAll += list.length;
                if (catFilter !== 'ALL' && catFilter !== cat) return;

                list.forEach(function(app, aIdx) {
                    var appName = app.name || 'Không rõ';
                    if (keyword && appName.toLowerCase().indexOf(keyword) === -1) return;

                    var isHiddenAll = app.hidden === true;
                    var isShowHome = !isHiddenAll && (app.show_on_home !== false);

                    if (statusFilter === 'HOME' && !isShowHome) return;
                    if (statusFilter === 'APP_ONLY' && (isHiddenAll || isShowHome)) return;
                    if (statusFilter === 'HIDDEN' && !isHiddenAll) return;
                    if (statusFilter.indexOf('CURATED_') === 0) {
                        var targetTabId = statusFilter.substring(8);
                        var targetTab = null;
                        for (var ti = 0; ti < cachedTabs.length; ti++) {
                            if (cachedTabs[ti].id.toLowerCase() === targetTabId.toLowerCase()) {
                                targetTab = cachedTabs[ti];
                                break;
                            }
                        }
                        if (!targetTab || !isAppInCuratedTab(app, targetTab)) return;
                    }

                    totalVisibleMatches++;

                    // Render dynamic badges for all curated tabs
                    var curatedBadges = '';
                    for (var cti = 0; cti < cachedTabs.length; cti++) {
                        var curTab = cachedTabs[cti];
                        if (curTab.type === 'curated' && isAppInCuratedTab(app, curTab)) {
                            curatedBadges += '<span style="background:' + (curTab.color || '#581c87') + '33; border:1px solid ' + (curTab.color || '#9333ea') + '; color:' + (curTab.color || '#e9d5ff') + '; font-size:10px; padding:2px 7px; border-radius:10px; margin-left:4px;">' + (curTab.icon || '🌟') + ' Tab ' + escapeVisHtml(curTab.name) + '</span>';
                        }
                    }

                    var statusBadge = '';
                    var rowStyle = '';
                    if (isHiddenAll) {
                        statusBadge = '<span style="background:#7f1d1d; color:#fca5a5; font-size:10px; padding:2px 7px; border-radius:10px; margin-left:6px;">🙈 Ẩn hoàn toàn</span>' + curatedBadges;
                        rowStyle = ' style="opacity:0.58; border-style:dashed; border-color:#7f1d1d;"';
                    } else if (isShowHome) {
                        statusBadge = '<span style="background:#14532d; color:#86efac; font-size:10px; padding:2px 7px; border-radius:10px; margin-left:6px;">🏠 Trang chủ + 📱 /app/</span>' + curatedBadges;
                    } else {
                        statusBadge = '<span style="background:#1e3a8a; color:#93c5fd; font-size:10px; padding:2px 7px; border-radius:10px; margin-left:6px;">📱 Chỉ ở /app/</span>' + curatedBadges;
                    }

                    var homeBtnText = isShowHome ? '🏠 Trang chủ: HIỆN' : '🏠 Trang chủ: ẨN';
                    var homeBtnStyle = isShowHome
                        ? 'background:#14532d; color:#bbf7d0; border-color:#16a34a;'
                        : 'background:#1e293b; color:#94a3b8; border-color:#475569;';

                    var allBtnText = isHiddenAll ? '📱 /app/: ĐANG ẨN' : '📱 /app/: HIỆN';
                    var allBtnStyle = isHiddenAll
                        ? 'background:#7f1d1d; color:#fecaca; border-color:#dc2626;'
                        : 'background:#1e3a8a; color:#dbeafe; border-color:#2563eb;';

                    // Dynamic curated buttons
                    var curatedButtonsHtml = '';
                    for (var cbi = 0; cbi < cachedTabs.length; cbi++) {
                        var curTabBtn = cachedTabs[cbi];
                        if (curTabBtn.type === 'curated') {
                            var isCurOn = isAppInCuratedTab(app, curTabBtn);
                            var cBtnText = (curTabBtn.icon || '🌟') + ' ' + curTabBtn.name + ': ' + (isCurOn ? 'BẬT' : 'TẮT');
                            var cBtnStyle = isCurOn
                                ? ('background:' + (curTabBtn.color || '#581c87') + '; color:#fff; border-color:' + (curTabBtn.color || '#9333ea') + ';')
                                : 'background:#1e293b; color:#94a3b8; border-color:#475569;';
                            var cField = curTabBtn.field || ('show_on_' + curTabBtn.id.toLowerCase());
                            curatedButtonsHtml += '<button type="button" class="btn-action" style="' + cBtnStyle + '" onclick="toggleAppFlag(' + cIdx + ', ' + aIdx + ', ' + String.fromCharCode(39) + cField + String.fromCharCode(39) + ', ' + String.fromCharCode(39) + curTabBtn.id + String.fromCharCode(39) + ')" title="Tích chọn cho phép app này xuất hiện ở Tab ' + escapeVisHtml(curTabBtn.name) + '">' + cBtnText + '</button>';
                        }
                    }

                    html += '<div class="existing-item"' + rowStyle + '>' +
                                '<div class="item-info">' +
                                    '<div class="item-title">' +
                                        '<span style="color:#64748b; font-size:12px; margin-right:4px;">#' + (aIdx + 1) + '</span> ' +
                                        '<b>' + escapeVisHtml(appName) + '</b>' +
                                        '<span style="color:#94a3b8; font-size:11px; margin-left:6px;">v' + escapeVisHtml(app.version || '1.0') + '</span>' +
                                        statusBadge +
                                    '</div>' +
                                    '<div class="item-pkg" style="color:#94a3b8;">📂 ' + escapeVisHtml(cat) + '</div>' +
                                '</div>' +
                                '<div class="item-actions">' +
                                    (aIdx > 0 ? '<button type="button" class="btn-action" title="Di chuyển lên trong chuyên mục" onclick="moveOtaApp(' + cIdx + ', ' + aIdx + ', -1)">⬆️</button>' : '') +
                                    (aIdx < list.length - 1 ? '<button type="button" class="btn-action" title="Di chuyển xuống trong chuyên mục" onclick="moveOtaApp(' + cIdx + ', ' + aIdx + ', 1)">⬇️</button>' : '') +
                                    '<button type="button" class="btn-action" style="' + homeBtnStyle + '" onclick="toggleAppFlag(' + cIdx + ', ' + aIdx + ', ' + String.fromCharCode(39) + 'show_on_home' + String.fromCharCode(39) + ')" title="Bật/tắt hiển thị ở mục Cài trực tiếp trên Trang chủ">' + homeBtnText + '</button>' +
                                    curatedButtonsHtml +
                                    '<button type="button" class="btn-action" style="' + allBtnStyle + '" onclick="toggleAppFlag(' + cIdx + ', ' + aIdx + ', ' + String.fromCharCode(39) + 'hidden' + String.fromCharCode(39) + ')" title="Ẩn/hiện app khỏi toàn bộ web (cả Trang chủ và /app/)">' + allBtnText + '</button>' +
                                    '<button type="button" class="btn-action btn-action-del" onclick="deleteOtaApp(' + cIdx + ', ' + aIdx + ')" title="Xóa app khỏi ota_data.json">🗑️</button>' +
                                '</div>' +
                            '</div>';
                });
            });

            if (countBadge) countBadge.innerText = totalVisibleMatches + ' / ' + totalAppsAll + ' app';
            if (!html) {
                container.innerHTML = '<p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Không có ứng dụng nào khớp bộ lọc.</p>';
            } else {
                container.innerHTML = html;
            }
        }

        function toggleHomeSection() {
            var nextHide = !(visHomeSettings.hide_ota_section === true);
            fetch('/api/apps/toggle-home-section', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ hide: nextHide })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    visHomeSettings = data.home_settings;
                    renderVisibilityHomeControls();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function toggleHomeCategoryIdx(catIdx) {
            var cat = visCategoriesList[catIdx];
            if (!cat) return;
            var hiddenCats = visHomeSettings.hidden_categories || [];
            var nextHide = hiddenCats.indexOf(cat) === -1;

            fetch('/api/apps/toggle-home-category', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category: cat, hide: nextHide })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    visHomeSettings = data.home_settings;
                    renderVisibilityHomeControls();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function toggleAppFlag(catIdx, appIdx, field, tabId) {
            var cat = visCategoriesList[catIdx];
            if (!cat || !visOtaData[cat] || !visOtaData[cat][appIdx]) return;
            var item = visOtaData[cat][appIdx];
            var curVal = false;
            if (field === 'show_on_home') {
                curVal = (item.show_on_home !== false);
            } else if (field === 'hidden') {
                curVal = (item.hidden === true);
            } else {
                curVal = (item[field] === true) || (item.custom_tabs && tabId && item.custom_tabs.indexOf(tabId) !== -1);
            }
            var nextVal = !curVal;

            fetch('/api/apps/toggle-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category: cat, index: appIdx, field: field, tab_id: tabId, value: nextVal })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    visOtaData[cat][appIdx] = data.item;
                    renderVisibilityHomeControls();
                    renderVisibilityApps();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function bulkSelectedCategoryHome(showOnHome) {
            var catFilterEl = document.getElementById('vis-cat-filter');
            var cat = catFilterEl ? catFilterEl.value : 'ALL';
            if (!cat || cat === 'ALL') return;

            fetch('/api/apps/bulk-home-category', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category: cat, show_on_home: showOnHome })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    (visOtaData[cat] || []).forEach(function(it) { it.show_on_home = showOnHome; });
                    renderVisibilityHomeControls();
                    renderVisibilityApps();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function moveOtaApp(catIdx, appIdx, dir) {
            var cat = visCategoriesList[catIdx];
            if (!cat || !visOtaData[cat]) return;
            var list = visOtaData[cat];
            var targetIdx = appIdx + dir;
            if (targetIdx < 0 || targetIdx >= list.length) return;

            fetch('/api/apps/move-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category: cat, index: appIdx, direction: dir })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    var temp = list[appIdx];
                    list[appIdx] = list[targetIdx];
                    list[targetIdx] = temp;
                    renderVisibilityApps();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

        function deleteOtaApp(catIdx, appIdx) {
            var cat = visCategoriesList[catIdx];
            if (!cat || !visOtaData[cat] || !visOtaData[cat][appIdx]) return;
            var item = visOtaData[cat][appIdx];
            if (!confirm('Bạn có chắc chắn muốn XÓA "' + (item.name || 'app này') + '" khỏi danh sách ota_data.json?')) {
                return;
            }
            fetch('/api/apps/delete-item', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ category: cat, index: appIdx })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    visOtaData[cat].splice(appIdx, 1);
                    populateVisCategoryFilter();
                    renderVisibilityHomeControls();
                    renderVisibilityApps();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            });
        }

        function handleDebFormSubmit(e) {
            e.preventDefault();
            var alertBox = document.getElementById('deb-alert-box');
            alertBox.style.display = 'none';

            var name = document.getElementById('deb-name').value.trim();
            var pkgId = document.getElementById('deb-pkg-id').value.trim();
            var ver = document.getElementById('deb-version').value.trim() || '1.0';
            var iosRange = document.getElementById('deb-ios-range').value.trim();
            var color = document.getElementById('deb-color').value;
            var desc = document.getElementById('deb-desc').value.trim();
            var note = document.getElementById('deb-note').value.trim();
            var autoRepo = document.getElementById('deb-auto-repo').checked;
            var tempFile = document.getElementById('deb-temp-filename').value;
            var editOrigPkg = document.getElementById('deb-edit-orig-pkg').value;

            if (!name || !pkgId) {
                alert("Vui lòng nhập Tên hiển thị trên nút và Package ID!");
                return;
            }

            var btn = document.getElementById('btn-deb-submit');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Đang xử lý & Đẩy lên GitHub... Vui lòng đợi</span>';

            var progressWrap = document.getElementById('deb-progress-wrap');
            var progressFill = document.getElementById('deb-progress-bar-fill');
            var progressText = document.getElementById('deb-progress-text');
            progressWrap.style.display = 'block';
            progressFill.style.width = '100%';
            progressText.innerText = '⚡ Đang lưu thông tin, đồng bộ Git và kích hoạt Cydia build...';

            var formData = new FormData();
            formData.append('name', name);
            formData.append('package_id', pkgId);
            formData.append('version', ver);
            formData.append('ios_range', iosRange);
            formData.append('color', color);
            formData.append('description', desc);
            formData.append('note', note);
            formData.append('auto_repo_a1', autoRepo ? 'true' : 'false');
            formData.append('temp_file', tempFile);
            formData.append('edit_orig_pkg', editOrigPkg);

            fetch('/api/quickinstall/save', { method: 'POST', body: formData })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    btn.disabled = false;
                    progressWrap.style.display = 'none';
                    if (data.success) {
                        var cleanMsg = (data.message || '').split(String.fromCharCode(10)).join('<br>');
                        alertBox.className = 'alert-box alert-success';
                        alertBox.innerHTML = '<b>' + cleanMsg + '</b>';
                        alertBox.style.display = 'block';
                        cancelDebEdit();
                        loadQuickInstallList();
                    } else {
                        btn.innerHTML = '<span>⚡ Lưu Nút & Tự Động Build Vào Cydia</span>';
                        alertBox.className = 'alert-box alert-error';
                        alertBox.innerText = 'Lỗi: ' + data.error;
                        alertBox.style.display = 'block';
                    }
                })
                .catch(function(err) {
                    btn.disabled = false;
                    btn.innerHTML = '<span>⚡ Lưu Nút & Tự Động Build Vào Cydia</span>';
                    progressWrap.style.display = 'none';
                    alertBox.className = 'alert-box alert-error';
                    alertBox.innerText = 'Lỗi kết nối máy chủ: ' + err;
                    alertBox.style.display = 'block';
                });
        }

        // ─── UTILS ────────────────────────────────────────────────────────
        function openIncomingFolder() {
            fetch('/api/open-incoming', { method: 'POST' });
        }

        function cleanIncomingFolder() {
            if (confirm("Bạn có chắc chắn muốn xóa toàn bộ file tạm trong thư mục incoming/ để giải phóng bộ nhớ máy tính?")) {
                fetch('/api/clean-incoming', { method: 'POST' })
                    .then(function(res) { return res.json(); })
                    .then(function(data) {
                        alert(data.message || data.error);
                        loadIncomingFilesList();
                        loadDebIncomingList();
                    });
            }
        }

        function openGitHubDesktop() {
            fetch('/api/open-github-desktop', { method: 'POST' });
        }

        function triggerGitPush() {
            var btn = document.getElementById('btn-git-push');
            if (btn) {
                btn.disabled = true;
                btn.innerText = '⏳ Đang đồng bộ Git...';
            }

            fetch('/api/git-push', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '⚡ Đồng Bộ Lên Web Tức Thì';
                    }
                    alert(data.message || 'Đã đồng bộ thành công!');
                })
                .catch(function(err) {
                    if (btn) {
                        btn.disabled = false;
                        btn.innerText = '⚡ Đồng Bộ Lên Web Tức Thì';
                    }
                    alert('Đã hoàn tất đồng bộ Git!');
                });
        }

        /* ==========================================================================
           QUẢN LÝ TÀI KHOẢN APPSTORE (MODULE 4)
           ========================================================================== */

        function escapeHtml(str) {
            if (!str) return '';
            return String(str)
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;')
                .replace(/'/g, '&#039;');
        }

        var authManagerData = { enabled: false, accounts: [] };
        var editingUsername = null;

        function loadAccountsManager() {
            var btnToggle = document.getElementById('btn-toggle-auth-protection');
            if (btnToggle) btnToggle.innerText = 'Đang tải...';

            fetch('/api/tabs/list?t=' + (new Date()).getTime())
            .then(function(res) { return res.json(); })
            .then(function(tData) {
                if (tData.success) {
                    cachedTabs = tData.tabs || [];
                    renderPermCheckboxes();
                }
            })
            .catch(function(e) { console.error('Lỗi nạp tabs:', e); })
            .finally(function() {
                var xhr = new XMLHttpRequest();
                xhr.open('GET', '/api/auth/data?t=' + (new Date()).getTime(), true);
                xhr.onreadystatechange = function() {
                    if (xhr.readyState === 4) {
                        if (xhr.status === 200) {
                            try {
                                authManagerData = JSON.parse(xhr.responseText) || { enabled: false, accounts: [] };
                            } catch(e) {
                                authManagerData = { enabled: false, accounts: [] };
                            }
                        } else {
                            console.error('Lỗi HTTP status:', xhr.status);
                            authManagerData = { enabled: false, accounts: [] };
                        }
                        renderAccountsManager();
                    }
                };
                xhr.onerror = function(err) {
                    console.error('Lỗi mạng nạp auth data:', err);
                    renderAccountsManager();
                };
                xhr.send(null);
            });
        }

        function renderAccountsManager() {
            var btnToggle = document.getElementById('btn-toggle-auth-protection');
            if (btnToggle) {
                if (authManagerData.enabled) {
                    btnToggle.className = 'btn-action btn-active';
                    btnToggle.innerHTML = '🔒 ĐANG BẬT BẢO VỆ (Bấm để Tắt)';
                    btnToggle.style.background = '#22c55e';
                    btnToggle.style.color = '#fff';
                } else {
                    btnToggle.className = 'btn-action';
                    btnToggle.innerHTML = '🔓 ĐANG TẮT BẢO VỆ (Bấm để Bật)';
                    btnToggle.style.background = '#475569';
                    btnToggle.style.color = '#fff';
                }
            }

            var countDisp = document.getElementById('acc-count-display');
            var accounts = authManagerData.accounts || [];
            if (countDisp) countDisp.innerText = accounts.length;

            var container = document.getElementById('acc-list-container');
            if (!container) return;

            if (accounts.length === 0) {
                container.innerHTML = '<div style="text-align:center; padding:30px; color:#64748b;">Chưa có tài khoản nào được cấp. Hãy nhập thông tin phía trên để cấp tài khoản đầu tiên!</div>';
                return;
            }

            var html = '';
            for (var i = 0; i < accounts.length; i++) {
                var acc = accounts[i];
                var isActive = acc.active !== false;
                var statusBadge = isActive 
                    ? '<span style="background:#166534; color:#86efac; font-size:11px; padding:3px 8px; border-radius:10px; font-weight:bold;">Hoạt Động</span>'
                    : '<span style="background:#991b1b; color:#fca5a5; font-size:11px; padding:3px 8px; border-radius:10px; font-weight:bold;">Đã Khóa</span>';

                var safeUser = encodeURIComponent(acc.username);

                html += '<div style="display:flex; justify-content:space-between; align-items:center; background:#0f172a; padding:12px 16px; border-radius:10px; margin-bottom:10px; border:1px solid #1e293b; flex-wrap:wrap; gap:10px;">';
                html += '  <div style="display:flex; align-items:center; gap:12px;">';
                html += '    <div style="width:36px; height:36px; border-radius:50%; background:#334155; display:flex; align-items:center; justify-content:center; font-weight:bold; color:#f8fafc;">' + escapeHtml(acc.username.substring(0, 2).toUpperCase()) + '</div>';
                html += '    <div>';
                html += '      <div style="display:flex; align-items:center; gap:8px;">';
                html += '        <span style="font-weight:bold; color:#f8fafc; font-size:14px;">' + escapeHtml(acc.username) + '</span>';
                html += '        ' + statusBadge;
                html += '      </div>';
                var perms = acc.allowed_categories || ['ALL'];
                var permBadges = '';
                if (perms.indexOf('ALL') !== -1) {
                    permBadges = '<span style="background:#0369a1; color:#e0f2fe; font-size:11px; padding:2px 7px; border-radius:8px;">🌐 Xem Tất Cả</span>';
                } else {
                    var badges = [];
                    for (var k = 0; k < perms.length; k++) {
                        var pId = perms[k];
                        var foundTab = null;
                        for (var tIdx = 0; tIdx < cachedTabs.length; tIdx++) {
                            if (cachedTabs[tIdx].id.toLowerCase() === pId.toLowerCase()) {
                                foundTab = cachedTabs[tIdx];
                                break;
                            }
                        }
                        if (foundTab) {
                            var tabBStyle = 'background:' + (foundTab.color || '#334155') + '33; color:' + (foundTab.color || '#cbd5e1') + '; border:1px solid ' + (foundTab.color || '#334155') + '; font-size:11px; padding:2px 7px; border-radius:8px; margin-right:4px;';
                            badges.push('<span style="' + tabBStyle + '">' + (foundTab.icon ? foundTab.icon + ' ' : '') + escapeHtml(foundTab.name) + '</span>');
                        } else {
                            badges.push('<span style="background:#334155; color:#cbd5e1; font-size:11px; padding:2px 7px; border-radius:8px; margin-right:4px;">' + escapeHtml(pId) + '</span>');
                        }
                    }
                    permBadges = badges.join('');
                }

                html += '      <div style="font-size:12px; color:#94a3b8; margin-top:2px;">';
                html += '        Mật khẩu: <code style="background:#1e293b; padding:1px 6px; border-radius:4px; color:#38bdf8;">' + escapeHtml(acc.password) + '</code>';
                html += '        • Quyền: ' + permBadges;
                if (acc.note) {
                    html += ' • <i>' + escapeHtml(acc.note) + '</i>';
                }
                html += '      </div>';
                html += '    </div>';
                html += '  </div>';
                html += '  <div style="display:flex; gap:6px;">';
                html += '    <button type="button" class="btn-secondary" data-user="' + safeUser + '" onclick="onEditAccClick(this)" style="padding:5px 12px; font-size:12px;">✏️ Sửa</button>';
                html += '    <button type="button" class="btn-secondary" data-user="' + safeUser + '" onclick="onToggleAccClick(this)" style="padding:5px 12px; font-size:12px;">' + (isActive ? '🔒 Khóa' : '🔓 Mở') + '</button>';
                html += '    <button type="button" class="btn-action btn-danger" data-user="' + safeUser + '" onclick="onDeleteAccClick(this)" style="padding:5px 10px; font-size:12px;">🗑️ Xóa</button>';
                html += '  </div>';
                html += '</div>';
            }

            container.innerHTML = html;
        }

        function toggleAuthProtection() {
            var newState = !authManagerData.enabled;
            fetch('/api/auth/toggle-protection', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ enabled: newState })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    authManagerData.enabled = data.enabled;
                    renderAccountsManager();
                } else {
                    alert('Lỗi: ' + (data.error || 'Không xác định'));
                }
            });
        }

        
        function getSelectedPermissions() {
            var allCb = document.getElementById('perm-all');
            if (allCb && allCb.checked) return ['ALL'];
            var perms = [];
            var cbs = document.querySelectorAll('.perm-cat-check');
            for (var i = 0; i < cbs.length; i++) {
                if (cbs[i].checked) perms.push(cbs[i].value);
            }
            return perms.length > 0 ? perms : ['ALL'];
        }

        function setSelectedPermissions(perms, isGuest) {
            perms = perms || ['ALL'];
            var allCb = document.getElementById('perm-all');
            var isAll = perms.indexOf('ALL') !== -1;
            if (allCb) allCb.checked = isAll;

            var cbs = document.querySelectorAll('.perm-cat-check');
            for (var i = 0; i < cbs.length; i++) {
                var val = cbs[i].value;
                if (isAll) {
                    cbs[i].checked = false;
                } else {
                    cbs[i].checked = (perms.indexOf(val) !== -1);
                }
            }
        }

        function onPermAllChanged(cb) {
            if (cb.checked) {
                var cbs = document.querySelectorAll('.perm-cat-check');
                for (var i = 0; i < cbs.length; i++) cbs[i].checked = false;
            }
        }

        function onPermCatChanged() {
            var anyChecked = false;
            var cbs = document.querySelectorAll('.perm-cat-check');
            for (var i = 0; i < cbs.length; i++) {
                if (cbs[i].checked) { anyChecked = true; break; }
            }
            var allCb = document.getElementById('perm-all');
            if (anyChecked && allCb) allCb.checked = false;
        }

        function setPermPreset(preset) {
            var allCb = document.getElementById('perm-all');
            var cbs = document.querySelectorAll('.perm-cat-check');
            for (var i = 0; i < cbs.length; i++) cbs[i].checked = false;
            if (preset === 'ALL') {
                if (allCb) allCb.checked = true;
            } else if (preset === 'NONE') {
                if (allCb) allCb.checked = false;
            } else {
                if (allCb) allCb.checked = false;
                var targetCb = document.getElementById('perm-' + preset.toLowerCase());
                if (targetCb) {
                    targetCb.checked = true;
                } else {
                    for (var j = 0; j < cbs.length; j++) {
                        if (cbs[j].value.toLowerCase() === preset.toLowerCase()) {
                            cbs[j].checked = true;
                            break;
                        }
                    }
                }
            }
        }
        function submitSaveAccount() {
            console.log('submitSaveAccount clicked!');
            var usernameEl = document.getElementById('acc-username-input');
            var passwordEl = document.getElementById('acc-password-input');
            var noteEl = document.getElementById('acc-note-input');
            var activeEl = document.getElementById('acc-active-checkbox');

            var username = usernameEl ? usernameEl.value.trim() : '';
            var password = passwordEl ? passwordEl.value.trim() : '';
            var note = noteEl ? noteEl.value.trim() : '';
            var active = activeEl ? activeEl.checked : true;
            var perms = getSelectedPermissions();
            var isGuest = (perms.length === 1 && perms[0] === 'GUEST');

            if (!username) {
                alert('Vui lòng nhập Tên Đăng Nhập!');
                return;
            }
            if (!editingUsername && !password) {
                alert('Vui lòng nhập Mật Khẩu!');
                return;
            }

            fetch('/api/auth/save-account', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    username: username,
                    password: password,
                    note: note,
                    active: active,
                    allowed_categories: perms,
                    is_guest: isGuest,
                    is_edit: !!editingUsername
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    alert(data.message || 'Lưu thành công!');
                    resetAccountForm();
                    loadAccountsManager();
                } else {
                    alert('Lỗi: ' + (data.error || 'Không rõ lỗi'));
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

function onEditAccClick(btn) {
            var u = decodeURIComponent(btn.getAttribute('data-user'));
            editAccount(u);
        }
        function onToggleAccClick(btn) {
            var u = decodeURIComponent(btn.getAttribute('data-user'));
            toggleAccount(u);
        }
        function onDeleteAccClick(btn) {
            var u = decodeURIComponent(btn.getAttribute('data-user'));
            deleteAccount(u);
        }

        function editAccount(username) {
            var accounts = authManagerData.accounts || [];
            for (var i = 0; i < accounts.length; i++) {
                if (accounts[i].username.toLowerCase() === username.toLowerCase()) {
                    var acc = accounts[i];
                    editingUsername = acc.username;
                    document.getElementById('acc-username-input').value = acc.username;
                    document.getElementById('acc-username-input').disabled = true;
                    document.getElementById('acc-password-input').value = acc.password;
                    document.getElementById('acc-note-input').value = acc.note || '';
                    document.getElementById('acc-active-checkbox').checked = acc.active !== false;
                    setSelectedPermissions(acc.allowed_categories || ['ALL'], acc.is_guest === true);

                    document.getElementById('acc-form-title').innerText = '✏️ Chỉnh Sửa Tài Khoản: ' + acc.username;
                    document.getElementById('btn-acc-cancel-edit').style.display = 'inline-block';
                    document.getElementById('btn-save-account').innerText = '💾 Cập Nhật Tài Khoản';
                    break;
                }
            }
        }

        function resetAccountForm() {
            editingUsername = null;
            document.getElementById('acc-username-input').value = '';
            document.getElementById('acc-username-input').disabled = false;
            document.getElementById('acc-password-input').value = '';
            document.getElementById('acc-note-input').value = '';
            document.getElementById('acc-active-checkbox').checked = true;
            setPermPreset('ALL');

            document.getElementById('acc-form-title').innerText = '➕ Cấp Tài Khoản Mới';
            document.getElementById('btn-acc-cancel-edit').style.display = 'none';
            document.getElementById('btn-save-account').innerText = '💾 Lưu Tài Khoản';
        }

        function toggleAccount(username) {
            fetch('/api/auth/toggle-account', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    loadAccountsManager();
                } else {
                    alert('Lỗi: ' + (data.error || 'Không xác định'));
                }
            });
        }

        function deleteAccount(username) {
            if (!confirm('Bạn có chắc chắn muốn xóa tài khoản ' + username + ' không?')) {
                return;
            }
            fetch('/api/auth/delete-account', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ username: username })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    loadAccountsManager();
                } else {
                    alert('Lỗi: ' + (data.error || 'Không xác định'));
                }
            });
        }

        function renderPermCheckboxes() {
            var container = document.getElementById('perm-checkboxes-container');
            var presetsCon = document.getElementById('perm-presets-container');
            var notesCon = document.getElementById('perm-notes-container');
            if (!container) return;

            // Presets
            if (presetsCon) {
                var q = String.fromCharCode(39);
                var phtml = '<button type="button" class="btn-action" onclick="setPermPreset(' + q + 'ALL' + q + ')" style="font-size:11px; padding:4px 9px;">Chọn Tất Cả</button>';
                for (var i = 0; i < cachedTabs.length; i++) {
                    var tab = cachedTabs[i];
                    if (tab.type === 'curated') {
                        phtml += '<button type="button" class="btn-action" onclick="setPermPreset(' + q + tab.id + q + ')" style="font-size:11px; padding:4px 9px; background:' + (tab.color || '#581c87') + '33; color:' + (tab.color || '#e9d5ff') + '; border-color:' + (tab.color || '#9333ea') + ';">' + (tab.icon || '🌟') + ' Chỉ ' + escapeHtml(tab.name) + '</button>';
                    }
                }
                phtml += '<button type="button" class="btn-action" onclick="setPermPreset(' + q + 'NONE' + q + ')" style="font-size:11px; padding:4px 9px;">Bỏ Chọn</button>';
                presetsCon.innerHTML = phtml;
            }

            // Checkboxes
            var chtml = '';
            chtml += '<label style="display:flex; align-items:center; gap:6px; cursor:pointer; background:#1e293b; padding:8px 10px; border-radius:8px; border:1px solid #334155;">' +
                     '<input type="checkbox" id="perm-all" value="ALL" onchange="onPermAllChanged(this)" style="width:16px; height:16px;"> <b>🌐 Tất Cả</b></label>';

            for (var j = 0; j < cachedTabs.length; j++) {
                var cTab = cachedTabs[j];
                if (cTab.type === 'curated') {
                    chtml += '<label style="display:flex; align-items:center; gap:6px; cursor:pointer; background:' + (cTab.color || '#3b0764') + '22; padding:8px 10px; border-radius:8px; border:1px solid ' + (cTab.color || '#7e22ce') + '; color:#fff;">' +
                             '<input type="checkbox" id="perm-' + cTab.id.toLowerCase() + '" value="' + cTab.id + '" class="perm-cat-check" onchange="onPermCatChanged()" style="width:16px; height:16px;"> <b>' + (cTab.icon || '🌟') + ' Tab ' + escapeHtml(cTab.name) + '</b></label>';
                }
            }

            for (var k = 0; k < cachedTabs.length; k++) {
                var catTab = cachedTabs[k];
                if (catTab.type === 'category') {
                    chtml += '<label style="display:flex; align-items:center; gap:6px; cursor:pointer; background:#0f172a; padding:8px 10px; border-radius:8px; border:1px solid #1e293b;">' +
                             '<input type="checkbox" id="perm-' + catTab.id.toLowerCase() + '" value="' + catTab.id + '" class="perm-cat-check" onchange="onPermCatChanged()" style="width:16px; height:16px;"> ' + (catTab.icon || '📂') + ' ' + escapeHtml(catTab.name) + '</label>';
                }
            }

            container.innerHTML = chtml;

            // Notes
            if (notesCon) {
                var nhtml = '';
                for (var m = 0; m < cachedTabs.length; m++) {
                    var nTab = cachedTabs[m];
                    if (nTab.type === 'curated') {
                        nhtml += '💡 <i><b>"' + (nTab.icon || '🌟') + ' Tab ' + escapeHtml(nTab.name) + '"</b>: ' + escapeHtml(nTab.description || 'Chỉ thấy các app được bật ở nút tương ứng trong mục Ẩn/Hiện Kho App.') + '</i><br>';
                    }
                }
                notesCon.innerHTML = nhtml;
            }
        }

        /* ==========================================================================
           QUẢN LÝ TAB KHO APP (MODULE 5)
           ========================================================================== */
        var cachedTabs = [];
        var editingTabId = null;

        function loadTabsManager() {
            var countDisp = document.getElementById('tabs-count-display');
            if (countDisp) countDisp.innerText = '...';

            fetch('/api/tabs/list?t=' + (new Date()).getTime())
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    cachedTabs = data.tabs || [];
                    renderTabsManager();
                    renderPermCheckboxes();
                } else {
                    alert('Lỗi nạp danh sách Tab: ' + data.error);
                }
            })
            .catch(function(err) {
                console.error('Lỗi nạp Tab:', err);
            });
        }

        function renderTabsManager() {
            var countDisp = document.getElementById('tabs-count-display');
            if (countDisp) countDisp.innerText = cachedTabs.length;

            var container = document.getElementById('tabs-list-container');
            if (!container) return;

            if (cachedTabs.length === 0) {
                container.innerHTML = '<p style="font-size:13px; color:#64748b; text-align:center; padding:15px;">Chưa có Tab nào.</p>';
                return;
            }

            var html = '';
            for (var i = 0; i < cachedTabs.length; i++) {
                var t = cachedTabs[i];
                var isSystem = t.system === true;
                var typeBadge = (t.type === 'curated')
                    ? '<span style="background:#581c87; color:#e9d5ff; font-size:11px; padding:2px 8px; border-radius:8px; font-weight:bold;">🌟 Tuyển Chọn</span>'
                    : (t.type === 'all'
                        ? '<span style="background:#0369a1; color:#e0f2fe; font-size:11px; padding:2px 8px; border-radius:8px; font-weight:bold;">🌐 Toàn Bộ</span>'
                        : '<span style="background:#1e293b; color:#94a3b8; font-size:11px; padding:2px 8px; border-radius:8px;">📂 Chuyên Mục</span>');

                var colorDot = '<span style="display:inline-block; width:12px; height:12px; border-radius:50%; background:' + (t.color || '#3b82f6') + '; margin-right:6px; vertical-align:middle;"></span>';

                html += '<div class="existing-item" style="border-left:4px solid ' + (t.color || '#3b82f6') + ';">';
                html += '  <div class="item-info">';
                html += '    <div class="item-title">';
                html += '      <span style="color:#64748b; font-size:12px; margin-right:4px;">#' + (i + 1) + '</span>';
                html += '      <span style="font-size:16px;">' + (t.icon || '🏷️') + '</span>';
                html += '      <b style="color:#f8fafc; font-size:14px;">' + escapeHtml(t.name) + '</b>';
                html += '      <code style="background:#0f172a; color:#38bdf8; padding:1px 6px; border-radius:4px; font-size:11px;">' + escapeHtml(t.id) + '</code>';
                html += '      ' + typeBadge;
                if (isSystem) {
                    html += '<span style="background:#334155; color:#94a3b8; font-size:10px; padding:2px 6px; border-radius:6px; margin-left:4px;">Hệ thống</span>';
                }
                html += '    </div>';
                html += '    <div style="font-size:12px; color:#94a3b8; margin-top:4px;">' + colorDot + escapeHtml(t.description || 'Không có mô tả') + '</div>';
                html += '  </div>';
                html += '  <div class="item-actions">';
                if (i > 0) {
                    html += '<button type="button" class="btn-action" title="Di chuyển lên" onclick="moveTab(' + i + ', -1)">⬆️</button>';
                }
                if (i < cachedTabs.length - 1) {
                    html += '<button type="button" class="btn-action" title="Di chuyển xuống" onclick="moveTab(' + i + ', 1)">⬇️</button>';
                }
                html += '<button type="button" class="btn-action" title="Chỉnh sửa Tab" onclick="editTab(' + i + ')">✏️ Sửa</button>';
                if (!isSystem) {
                    html += '<button type="button" class="btn-action btn-action-del" title="Xóa Tab" onclick="deleteTab(' + i + ')">🗑️ Xóa</button>';
                }
                html += '  </div>';
                html += '</div>';
            }

            container.innerHTML = html;
        }

        function resetTabForm() {
            editingTabId = null;
            var titleEl = document.getElementById('tab-form-title');
            var btnCancel = document.getElementById('btn-tab-cancel-edit');
            var btnSave = document.getElementById('btn-save-tab');
            var idInput = document.getElementById('tab-id-input');
            var nameInput = document.getElementById('tab-name-input');
            var iconInput = document.getElementById('tab-icon-input');
            var colorInput = document.getElementById('tab-color-input');
            var colorPicker = document.getElementById('tab-color-picker');
            var typeSelect = document.getElementById('tab-type-select');
            var descInput = document.getElementById('tab-desc-input');

            if (titleEl) titleEl.innerText = '➕ Thêm Tab Mới';
            if (btnCancel) btnCancel.style.display = 'none';
            if (btnSave) btnSave.innerText = '💾 Lưu Tab';
            if (idInput) { idInput.value = ''; idInput.disabled = false; }
            if (nameInput) nameInput.value = '';
            if (iconInput) iconInput.value = '🏷️';
            if (colorInput) colorInput.value = '#3b82f6';
            if (colorPicker) colorPicker.value = '#3b82f6';
            if (typeSelect) { typeSelect.value = 'curated'; typeSelect.disabled = false; }
            if (descInput) descInput.value = '';
        }

        function editTab(idx) {
            var t = cachedTabs[idx];
            if (!t) return;
            editingTabId = t.id;

            var titleEl = document.getElementById('tab-form-title');
            var btnCancel = document.getElementById('btn-tab-cancel-edit');
            var btnSave = document.getElementById('btn-save-tab');
            var idInput = document.getElementById('tab-id-input');
            var nameInput = document.getElementById('tab-name-input');
            var iconInput = document.getElementById('tab-icon-input');
            var colorInput = document.getElementById('tab-color-input');
            var colorPicker = document.getElementById('tab-color-picker');
            var typeSelect = document.getElementById('tab-type-select');
            var descInput = document.getElementById('tab-desc-input');

            if (titleEl) titleEl.innerText = '✏️ Chỉnh Sửa Tab: ' + t.name;
            if (btnCancel) btnCancel.style.display = 'inline-block';
            if (btnSave) btnSave.innerText = '💾 Cập Nhật Tab';

            if (idInput) {
                idInput.value = t.id;
                idInput.disabled = (t.system === true);
            }
            if (nameInput) nameInput.value = t.name;
            if (iconInput) iconInput.value = t.icon || '🏷️';
            if (colorInput) colorInput.value = t.color || '#3b82f6';
            if (colorPicker) colorPicker.value = t.color || '#3b82f6';
            if (typeSelect) {
                typeSelect.value = t.type;
                typeSelect.disabled = (t.system === true);
            }
            if (descInput) descInput.value = t.description || '';

            window.scrollTo({ top: document.getElementById('module-tabs-container').offsetTop, behavior: 'smooth' });
        }

        function submitSaveTab() {
            var idInput = document.getElementById('tab-id-input');
            var nameInput = document.getElementById('tab-name-input');
            var iconInput = document.getElementById('tab-icon-input');
            var colorInput = document.getElementById('tab-color-input');
            var typeSelect = document.getElementById('tab-type-select');
            var descInput = document.getElementById('tab-desc-input');

            var tabId = idInput ? idInput.value.trim() : '';
            var name = nameInput ? nameInput.value.trim() : '';
            var icon = iconInput ? iconInput.value.trim() : '🏷️';
            var color = colorInput ? colorInput.value.trim() : '#3b82f6';
            var tabType = typeSelect ? typeSelect.value : 'curated';
            var desc = descInput ? descInput.value.trim() : '';

            if (!tabId) {
                alert('Vui lòng nhập Mã Tab / ID!');
                return;
            }
            if (!name) {
                alert('Vui lòng nhập Tên Hiển Thị của Tab!');
                return;
            }

            fetch('/api/tabs/save', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    id: tabId,
                    name: name,
                    icon: icon,
                    color: color,
                    type: tabType,
                    description: desc,
                    is_edit: !!editingTabId,
                    old_id: editingTabId
                })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    alert(data.message || 'Lưu Tab thành công!');
                    resetTabForm();
                    cachedTabs = data.tabs || [];
                    renderTabsManager();
                    renderPermCheckboxes();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

        function deleteTab(idx) {
            var t = cachedTabs[idx];
            if (!t) return;
            if (t.system) {
                alert('Không thể xóa Tab hệ thống!');
                return;
            }
            if (!confirm('Bạn có chắc chắn muốn XÓA Tab "' + t.name + '" (ID: ' + t.id + ')?\\nCác thiết lập phân quyền liên quan đến tab này cũng sẽ được gỡ bỏ.')) {
                return;
            }

            fetch('/api/tabs/delete', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ id: t.id })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    alert(data.message || 'Xóa thành công!');
                    cachedTabs = data.tabs || [];
                    renderTabsManager();
                    renderPermCheckboxes();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

        function moveTab(idx, dir) {
            fetch('/api/tabs/reorder', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ index: idx, direction: dir })
            })
            .then(function(res) { return res.json(); })
            .then(function(data) {
                if (data.success) {
                    cachedTabs = data.tabs || [];
                    renderTabsManager();
                    renderPermCheckboxes();
                } else {
                    alert('Lỗi: ' + data.error);
                }
            })
            .catch(function(err) {
                alert('Lỗi kết nối: ' + err);
            });
        }

        // Tự động nạp sẵn dữ liệu Tab khi tải trang
        loadTabsManager();

    </script>
</body>
</html>
'''


# ==============================================================================
# 5. CÁC API FLASK CHO APPSTORE VÀ CÀI ĐẶT NHANH DEB
# ==============================================================================
@app.after_request
def add_header(response):
    response.headers['Cache-Control'] = 'no-store, no-cache, must-revalidate, max-age=0'
    response.headers['Pragma'] = 'no-cache'
    response.headers['Expires'] = '0'
    return response


@app.route('/')
def index_page():
    return render_template_string(HTML_TEMPLATE)


# ==============================================================================
# QUẢN LÝ TÀI KHOẢN ĐĂNG NHẬP TOMKIDS APPSTORE
# ==============================================================================
@app.route('/api/auth/data')
def get_auth_data():
    return jsonify(load_auth_accounts())

@app.route('/api/auth/toggle-protection', methods=['POST'])
def toggle_auth_protection():
    try:
        data = load_auth_accounts()
        req = request.get_json() or {}
        if 'enabled' in req:
            data['enabled'] = bool(req['enabled'])
        else:
            data['enabled'] = not data.get('enabled', False)
        save_auth_accounts(data)
        return jsonify({'success': True, 'enabled': data['enabled']})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auth/save-account', methods=['POST'])
def save_auth_account():
    try:
        req = request.get_json() or {}
        username = req.get('username', '').strip()
        password = req.get('password', '').strip()
        note = req.get('note', '').strip()
        active = req.get('active', True)
        is_edit = req.get('is_edit', False)
        allowed_categories = req.get('allowed_categories', ['ALL'])
        if not allowed_categories or not isinstance(allowed_categories, list):
            allowed_categories = ['ALL']
        is_guest = (allowed_categories == ['GUEST'])

        if not username:
            return jsonify({'success': False, 'error': 'Vui lòng nhập tên đăng nhập!'})

        data = load_auth_accounts()
        accounts = data.get('accounts', [])
        
        found = False
        for acc in accounts:
            if acc.get('username', '').lower() == username.lower():
                found = True
                if is_edit:
                    if password:
                        acc['password'] = password
                    acc['note'] = note
                    acc['active'] = active
                    acc['allowed_categories'] = allowed_categories
                    acc['is_guest'] = is_guest
                else:
                    return jsonify({'success': False, 'error': f'Tài khoản {username} đã tồn tại!'})
                break
        
        if not found:
            if not password:
                return jsonify({'success': False, 'error': 'Vui lòng nhập mật khẩu cho tài khoản mới!'})
            accounts.append({
                'username': username,
                'password': password,
                'note': note,
                'active': active,
                'allowed_categories': allowed_categories,
                'is_guest': is_guest
            })

        data['accounts'] = accounts
        save_auth_accounts(data)
        return jsonify({'success': True, 'message': f'Đã lưu tài khoản {username} thành công!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auth/toggle-account', methods=['POST'])
def toggle_auth_account():
    try:
        req = request.get_json() or {}
        username = req.get('username', '').strip()
        data = load_auth_accounts()
        accounts = data.get('accounts', [])
        for acc in accounts:
            if acc.get('username', '').lower() == username.lower():
                acc['active'] = not acc.get('active', True)
                save_auth_accounts(data)
                return jsonify({'success': True, 'active': acc['active']})
        return jsonify({'success': False, 'error': 'Không tìm thấy tài khoản!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})

@app.route('/api/auth/delete-account', methods=['POST'])
def delete_auth_account():
    try:
        req = request.get_json() or {}
        username = req.get('username', '').strip()
        data = load_auth_accounts()
        accounts = data.get('accounts', [])
        new_accs = [acc for acc in accounts if acc.get('username', '').lower() != username.lower()]
        data['accounts'] = new_accs
        save_auth_accounts(data)
        return jsonify({'success': True, 'message': f'Đã xóa tài khoản {username}!'})
    except Exception as e:
        return jsonify({'success': False, 'error': str(e)})


@app.route('/api/list-incoming')
def list_incoming():
    files = []
    if os.path.exists(INCOMING_DIR):
        for f in os.listdir(INCOMING_DIR):
            if f.lower().endswith(('.ipa', '.deb', '.m4r', '.mp3', '.pdf', '.jpg', '.png')):
                files.append(f)
    return jsonify({"files": files})


@app.route('/api/open-incoming', methods=['POST'])
def open_incoming():
    try:
        os.startfile(INCOMING_DIR)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def resolve_and_download_link(link, target_path):
    """
    Tự động nhận diện và tải file từ mọi định dạng link:
    1. GitHub repo local (nếu link trỏ tới package_repo_A1 của chính máy tính):
       -> Tự động đọc tức thì từ D:\\GitHub\\Tomkidsrepos\\package_repo_A1\\...
    2. GitHub Blob link (https://github.com/.../blob/...):
       -> Tự động chuyển đổi thành link Raw trực tiếp
    3. Google Drive link (cả /d/... và id=...):
       -> Bóc tách file ID và tải tự động
    4. Link tải trực tiếp / GitHub Releases:
       -> Tải qua curl.exe hỗ trợ theo dõi redirect (-L)
    """
    link = link.strip()
    if not link:
        raise Exception("Chưa nhập đường dẫn link!")

    # 1. Kiểm tra nếu link trỏ tới package_repo_A1 trên máy tính
    if "package_repo_A1" in link:
        clean_url = link.split('?')[0].split('#')[0]
        fname = clean_url.split('/')[-1]
        local_cand = os.path.join(PACKAGE_REPO_A1_DIR, fname)
        if os.path.exists(local_cand) and os.path.isfile(local_cand):
            print(f"[+] Nhận diện file có sẵn trong package_repo_A1: {local_cand}")
            shutil.copy2(local_cand, target_path)
            return target_path

    # 2. Xử lý link GitHub Blob (chuyển sang Raw)
    if "github.com" in link and "/blob/" in link:
        raw_link = link.replace("github.com", "raw.githubusercontent.com").replace("/blob/", "/")
        print(f"[+] Tự động chuyển link GitHub blob sang raw: {raw_link}")
        link = raw_link

    # 3. Google Drive
    if "drive.google.com" in link:
        import re
        file_id = None
        m1 = re.search(r'/d/([a-zA-Z0-9_-]+)', link)
        if m1:
            file_id = m1.group(1)
        else:
            m2 = re.search(r'id=([a-zA-Z0-9_-]+)', link)
            if m2:
                file_id = m2.group(1)
        if not file_id:
            raise Exception("Định dạng link Google Drive không hợp lệ!")
        try:
            import gdown
            gdown.download(id=file_id, output=target_path, quiet=False)
        except:
            uc_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
            subprocess.run(["curl.exe", "-L", "-o", target_path, uc_url], check=True)
    else:
        # Tải bằng curl.exe hỗ trợ redirect (-L)
        res = subprocess.run(["curl.exe", "-L", "-s", "-o", target_path, link])
        if res.returncode != 0:
            raise Exception(f"Không thể tải file từ link (curl exit code {res.returncode})")

    if not os.path.exists(target_path) or os.path.getsize(target_path) == 0:
        raise Exception("Tải file thất bại hoặc file nhận về bị rỗng!")

    # Kiểm tra xem có bị nhận nhầm trang HTML hay không
    with open(target_path, 'rb') as f:
        head = f.read(50)
        if b'<!DOCTYPE' in head.upper() or b'<HTML' in head.upper():
            raise Exception("Link bạn cung cấp dẫn tới trang web hiển thị HTML thay vì file nhị phân trực tiếp!")

    return target_path


def process_file_item(target_file_path, category=None, release_url=None, show_on_home=False, custom_name=None, custom_version=None):
    if not target_file_path or not os.path.exists(target_file_path):
        raise Exception(f"File không tồn tại: {target_file_path}")

    # Kiểm tra nội dung file (Magic bytes)
    with open(target_file_path, 'rb') as f:
        header = f.read(16)

    if header.startswith(b'<!DOCTYPE') or header.startswith(b'<html') or b'<body' in header:
        raise Exception("File tải về là trang web HTML lỗi thay vì file dữ liệu!")

    # Nếu là DEB (Magic: !<arch>\n)
    if header.startswith(b'!<arch>\n') or target_file_path.lower().endswith('.deb'):
        out_ipa = os.path.splitext(target_file_path)[0] + ".ipa"
        deb_to_ipa(target_file_path, out_ipa)
        target_file_path = out_ipa
        with open(target_file_path, 'rb') as f:
            header = f.read(16)

    ext = os.path.splitext(target_file_path)[1].lower()

    # Nhận diện chuyên mục phù hợp
    is_media_book = ext in ('.pdf', '.epub')
    is_media_audio = ext in ('.m4r', '.mp3')
    is_media_img = ext in ('.jpg', '.jpeg', '.png') and not target_file_path.endswith('.ipa')

    if is_media_book:
        actual_cat = category if category in ('Sách', 'Truyện') else 'Sách'
        raw_name = os.path.splitext(os.path.basename(target_file_path))[0]
        title = raw_name.replace('-', ' ').replace('_', ' ').title()
        pages = "iBooks / PDF"
        if ext == '.pdf':
            try:
                import pypdf
                reader = pypdf.PdfReader(target_file_path)
                pages = f"{len(reader.pages)} trang"
            except:
                pages = "PDF"

        safe_name = os.path.basename(target_file_path)
        uploaded_url = upload_to_github_releases(target_file_path, safe_name)
        final_url = uploaded_url or f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

        section = "books" if actual_cat == "Sách" else "comics"
        record = {
            "title": title,
            "author": "Tomkids Library",
            "type": "PDF / iBooks",
            "pages": pages,
            "icon": "📖" if actual_cat == "Sách" else "📚",
            "url": final_url
        }
        update_media_json(section, record)
        return {
            "success": True,
            "app_name": title,
            "version": pages,
            "bundle_id": "com.apple.iBooks",
            "plist": final_url,
            "category": actual_cat,
            "release_url": final_url
        }

    elif is_media_audio:
        raw_name = os.path.splitext(os.path.basename(target_file_path))[0]
        title = raw_name.replace('-', ' ').replace('_', ' ').title()
        safe_name = os.path.basename(target_file_path)
        uploaded_url = upload_to_github_releases(target_file_path, safe_name)
        final_url = uploaded_url or f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

        record = {
            "title": title,
            "desc": "Nhạc chuông chất lượng cao cho iPhone",
            "file": final_url,
            "duration": "0:30"
        }
        update_media_json("ringtones", record)
        return {
            "success": True,
            "app_name": title,
            "version": "Audio",
            "bundle_id": "com.apple.mobileipod",
            "plist": final_url,
            "category": "Nhạc chuông",
            "release_url": final_url
        }

    elif is_media_img:
        raw_name = os.path.splitext(os.path.basename(target_file_path))[0]
        title = raw_name.replace('-', ' ').replace('_', ' ').title()
        safe_name = os.path.basename(target_file_path)
        uploaded_url = upload_to_github_releases(target_file_path, safe_name)
        final_url = uploaded_url or f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

        record = {
            "title": title,
            "url": final_url
        }
        update_media_json("wallpapers", record)
        return {
            "success": True,
            "app_name": title,
            "version": "Wallpaper",
            "bundle_id": "com.apple.mobileslideshow",
            "plist": final_url,
            "category": "Hình nền",
            "release_url": final_url
        }

    elif header.startswith(b'PK') or ext == '.ipa':
        if not target_file_path.lower().endswith('.ipa'):
            new_ipa_path = target_file_path + '.ipa'
            shutil.move(target_file_path, new_ipa_path)
            target_file_path = new_ipa_path

        app_info = extract_ipa_info(target_file_path, custom_name=custom_name, custom_version=custom_version)
        safe_bid = make_safe_slug(app_info['bundle_id'], 'com.tomkids.app')
        safe_ver = make_safe_slug(app_info['version'], '1.0')
        safe_name = f"{safe_bid}_{safe_ver}.ipa"
        final_ipa_path = os.path.join(INCOMING_DIR, safe_name)
        if target_file_path != final_ipa_path:
            shutil.move(target_file_path, final_ipa_path)

        if not release_url:
            uploaded_dl_url = upload_to_github_releases(final_ipa_path, safe_name)
            if uploaded_dl_url:
                release_url = uploaded_dl_url
            else:
                release_url = f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

        plist_path = create_ota_plist(app_info, release_url)
        actual_cat = category if category not in ('Sách', 'Truyện', 'Nhạc chuông', 'Hình nền', None) else 'Trò Chơi'
        record = {
            "name": app_info["name"],
            "version": app_info["version"],
            "icon": app_info["icon"],
            "plist": plist_path,
            "show_on_home": bool(show_on_home)
        }
        update_ota_json(actual_cat, record)

        return {
            "success": True,
            "app_name": app_info["name"],
            "version": app_info["version"],
            "bundle_id": app_info["bundle_id"],
            "plist": plist_path,
            "category": actual_cat,
            "release_url": release_url
        }
    else:
        raise Exception(f"Định dạng file không được hỗ trợ ({ext})!")


@app.route('/api/process', methods=['POST'])
def process_upload():
    try:
        source_type = request.form.get('source_type', 'file')
        category = request.form.get('category', 'Trò Chơi')
        release_url = request.form.get('release_url', '').strip()
        show_on_home = request.form.get('show_on_home', 'false').lower() == 'true'
        custom_name = request.form.get('custom_name', '').strip()
        custom_version = request.form.get('custom_version', '').strip()

        target_file_path = None

        if source_type == 'file':
            uploaded_file = request.files.get('file')
            if not uploaded_file or uploaded_file.filename == '':
                return jsonify({"success": False, "error": "Chưa chọn file!"})

            filename = uploaded_file.filename
            target_file_path = os.path.join(INCOMING_DIR, filename)
            uploaded_file.save(target_file_path)

        elif source_type == 'incoming':
            incoming_name = request.form.get('incoming_file')
            target_file_path = os.path.join(INCOMING_DIR, incoming_name)

        elif source_type == 'link':
            link = request.form.get('link', '').strip()
            if not link:
                return jsonify({"success": False, "error": "Chưa nhập link!"})

            clean_url = link.split('?')[0].split('#')[0]
            url_filename = clean_url.split('/')[-1] or "downloaded_package"
            target_file_path = os.path.join(INCOMING_DIR, f"temp_{url_filename}")
            resolve_and_download_link(link, target_file_path)

        res = process_file_item(target_file_path, category=category, release_url=release_url, show_on_home=show_on_home, custom_name=custom_name, custom_version=custom_version)
        return jsonify(res)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/process-all-incoming', methods=['POST'])
def process_all_incoming():
    try:
        if not os.path.exists(INCOMING_DIR):
            return jsonify({"success": False, "error": "Thư mục incoming/ không tồn tại!"})

        show_on_home = request.form.get('show_on_home', 'false').lower() == 'true'

        valid_exts = ('.ipa', '.deb', '.pdf', '.epub', '.m4r', '.mp3', '.jpg', '.jpeg', '.png')
        all_entries = [f for f in os.listdir(INCOMING_DIR) if not f.startswith('.') and not f.endswith('.plist')]
        files = [f for f in all_entries if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(INCOMING_DIR, f))]

        if not files:
            return jsonify({"success": False, "error": "Không có file hợp lệ (.ipa, .deb, .pdf, .m4r, v.v.) nào trong thư mục incoming/ để xử lý!"})

        results = []
        for f in sorted(files):
            fpath = os.path.join(INCOMING_DIR, f)
            try:
                res = process_file_item(fpath, show_on_home=show_on_home)
                results.append({
                    "file": f,
                    "success": True,
                    "name": res.get("app_name"),
                    "category": res.get("category"),
                    "version": res.get("version")
                })
            except Exception as fe:
                results.append({
                    "file": f,
                    "success": False,
                    "error": str(fe)
                })

        success_count = sum(1 for r in results if r.get("success"))
        return jsonify({
            "success": True,
            "total": len(files),
            "processed": success_count,
            "results": results
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/clean-incoming', methods=['POST'])
def clean_incoming():
    try:
        count = 0
        if os.path.exists(INCOMING_DIR):
            for f in os.listdir(INCOMING_DIR):
                fpath = os.path.join(INCOMING_DIR, f)
                if os.path.isfile(fpath) and f != '.gitkeep':
                    os.remove(fpath)
                    count += 1
        return jsonify({"success": True, "message": f"Đã dọn dẹp sạch {count} file tạm trong incoming/!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/open-github-desktop', methods=['POST'])
def open_github_desktop():
    try:
        app_path = os.path.expandvars(r"%LOCALAPPDATA%\GitHubDesktop\GitHubDesktop.exe")
        if os.path.exists(app_path):
            os.startfile(app_path)
            return jsonify({"success": True})
        return jsonify({"success": False, "error": "Không tìm thấy GitHub Desktop"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/git-push', methods=['POST'])
def git_push():
    try:
        ok_io, msg_io = git_push_repo(REPO_DIR, "Auto-update apps from Tomkids Admin", branch="main")
        ok_a1, msg_a1 = git_push_repo(PACKAGE_REPO_A1_DIR, "Auto-update packages from Tomkids Admin", branch="master")

        if ok_io and ok_a1:
            return jsonify({"success": True, "message": "⚡ Đồng bộ thần tốc thành công 100% lên GitHub & tomkidsrepo.cloud!"})
        elif ok_io:
            return jsonify({"success": True, "message": "🌐 Đã đồng bộ trang chủ lên tomkidsrepo.cloud!\n(Kho DEB package_repo_A1: hãy bấm Push trong GitHub Desktop nếu cần)."})
        else:
            return jsonify({"success": False, "message": "📁 Đã lưu và commit dữ liệu trên máy tính!\n👉 Bạn chỉ cần mở GitHub Desktop và bấm 'Push origin' là web cập nhật ngay!"})
    except Exception as e:
        return jsonify({"success": False, "message": f"Lỗi: {e}"})


# ==============================================================================
# 6. CÁC API FLASK RIÊNG CHO MODULE CÀI ĐẶT NHANH DEB
# ==============================================================================
@app.route('/api/quickinstall/list')
def api_quickinstall_list():
    items = load_quickinstall_data()
    return jsonify({"success": True, "items": items})


@app.route('/api/quickinstall/extract-deb', methods=['POST'])
def api_quickinstall_extract():
    try:
        source_type = request.form.get('source_type', 'file')
        target_path = None

        if source_type == 'file':
            up_file = request.files.get('file')
            if not up_file or not up_file.filename:
                return jsonify({"success": False, "error": "Chưa chọn file DEB!"})
            target_path = os.path.join(INCOMING_DIR, f"temp_{up_file.filename}")
            up_file.save(target_path)

        elif source_type == 'incoming':
            inc_file = request.form.get('incoming_file', '').strip()
            target_path = os.path.join(INCOMING_DIR, inc_file)

        elif source_type == 'link':
            link = request.form.get('link', '').strip()
            if not link:
                return jsonify({"success": False, "error": "Chưa nhập link!"})

            clean_url = link.split('?')[0].split('#')[0]
            url_filename = clean_url.split('/')[-1]
            if not url_filename.lower().endswith('.deb'):
                url_filename = "downloaded_package.deb"

            target_path = os.path.join(INCOMING_DIR, f"temp_{url_filename}")
            resolve_and_download_link(link, target_path)

        if not target_path or not os.path.exists(target_path):
            return jsonify({"success": False, "error": "Không tìm thấy file để bóc tách!"})

        info = extract_deb_control(target_path)
        return jsonify({
            "success": True,
            "info": info,
            "temp_file": os.path.basename(target_path)
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/quickinstall/save', methods=['POST'])
def api_quickinstall_save():
    try:
        name = request.form.get('name', '').strip()
        package_id = request.form.get('package_id', '').strip()
        version = request.form.get('version', '').strip() or '1.0'
        ios_range = request.form.get('ios_range', '').strip()
        color = request.form.get('color', 'green').strip()
        description = request.form.get('description', '').strip()
        note = request.form.get('note', '').strip()
        auto_repo_a1 = request.form.get('auto_repo_a1', 'false').lower() in ('true', '1', 'on')
        temp_file = request.form.get('temp_file', '').strip()
        edit_orig_pkg = request.form.get('edit_orig_pkg', '').strip()

        if not name or not package_id:
            return jsonify({"success": False, "error": "Tên nút và Package ID là bắt buộc!"})

        deb_pushed = False
        # 1. Nếu có file DEB và bật tự động lưu vào package_repo_A1
        if auto_repo_a1 and temp_file:
            src_deb_path = os.path.join(INCOMING_DIR, temp_file)
            if os.path.exists(src_deb_path) and os.path.exists(PACKAGE_REPO_A1_DIR):
                target_deb_name = f"{package_id}_{version}_iphoneos-arm.deb"
                dest_deb_path = os.path.join(PACKAGE_REPO_A1_DIR, target_deb_name)
                if os.path.abspath(src_deb_path) != os.path.abspath(dest_deb_path):
                    shutil.copy2(src_deb_path, dest_deb_path)
                print(f"[+] Đã copy file DEB vào package_repo_A1: {dest_deb_path}")

                # Commit & push sang package_repo_A1 (branch master)
                push_ok, push_msg = git_push_repo(
                    PACKAGE_REPO_A1_DIR,
                    f"Thêm package {package_id} v{version}",
                    branch="master"
                )
                deb_pushed = push_ok
                print(f"[*] Kết quả push package_repo_A1: {push_msg}")

        # 2. Cập nhật quickinstall.json
        items = load_quickinstall_data()

        item_record = {
            "name": name,
            "package_id": package_id,
            "version": version,
            "source_repo": "https://tomkidsrepo.cloud",
            "color": color,
            "added": datetime.date.today().strftime('%Y-%m-%d')
        }
        if ios_range:
            item_record["ios_range"] = ios_range
        if description:
            item_record["description"] = description
        if note:
            item_record["note"] = note

        replaced = False
        # Nếu đang chỉnh sửa nút có sẵn
        if edit_orig_pkg:
            for idx, it in enumerate(items):
                if it.get('package_id') == edit_orig_pkg:
                    items[idx] = item_record
                    replaced = True
                    break

        if not replaced:
            # Kiểm tra xem package_id này đã có chưa
            for idx, it in enumerate(items):
                if it.get('package_id') == package_id:
                    items[idx] = item_record
                    replaced = True
                    break

        if not replaced:
            # Thêm mới vào danh sách
            items.append(item_record)

        save_quickinstall_data(items)

        # 3. Commit & Push tomkidsrepos.github.io (branch main)
        push_io_ok, push_io_msg = git_push_repo(
            REPO_DIR,
            f"Update Quick Install DEB: {name}",
            branch="main"
        )

        msg = f"🎉 Đã lưu nút cài đặt nhanh '{name}' thành công!"
        if auto_repo_a1 and deb_pushed:
            msg += "\n⚡ File DEB đã được đưa lên package_repo_A1 (GitHub đang tự động build Cydia Packages & sync repo)!"
        elif auto_repo_a1 and not deb_pushed:
            msg += "\n⚠️ File DEB đã lưu vào máy nhưng chưa push được. Hãy mở GitHub Desktop để push!"

        if push_io_ok:
            msg += "\n🌐 Đã đồng bộ tức thì lên https://tomkidsrepo.cloud/!"
        else:
            msg += "\n⚠️ Web tomkidsrepo.cloud: Đã commit trên máy tính. Bạn hãy mở GitHub Desktop và bấm 'Push origin' để cập nhật lên web!"

        return jsonify({
            "success": True,
            "message": msg,
            "deb_pushed": deb_pushed,
            "io_pushed": push_io_ok
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/quickinstall/delete', methods=['POST'])
def api_quickinstall_delete():
    try:
        pkg_id = request.form.get('package_id', '').strip()
        if not pkg_id:
            return jsonify({"success": False, "error": "Thiếu Package ID để xóa!"})

        items = load_quickinstall_data()
        filtered = [it for it in items if it.get('package_id') != pkg_id]
        if len(filtered) == len(items):
            return jsonify({"success": False, "error": f"Không tìm thấy package {pkg_id}!"})

        save_quickinstall_data(filtered)

        # Commit & push tomkidsrepos.github.io
        push_io_ok, push_io_msg = git_push_repo(
            REPO_DIR,
            f"Remove Quick Install DEB: {pkg_id}",
            branch="main"
        )
        return jsonify({
            "success": True,
            "message": f"Đã xóa nút '{pkg_id}' khỏi danh sách và đồng bộ lên web!"
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/quickinstall/reorder', methods=['POST'])
def api_quickinstall_reorder():
    try:
        data = request.get_json(silent=True) or {}
        order = data.get('order', [])
        if not order:
            return jsonify({"success": False, "error": "Danh sách thứ tự không hợp lệ!"})

        items = load_quickinstall_data()
        pkg_map = {it['package_id']: it for it in items}

        new_items = []
        for pid in order:
            if pid in pkg_map:
                new_items.append(pkg_map[pid])

        # Giữ lại các item còn lại nếu có
        for it in items:
            if it['package_id'] not in order:
                new_items.append(it)

        save_quickinstall_data(new_items)

        # Commit & push
        push_io_ok, push_io_msg = git_push_repo(
            REPO_DIR,
            "Reorder Quick Install DEB buttons",
            branch="main"
        )
        return jsonify({"success": True, "message": "Đã lưu và đồng bộ thứ tự các nút!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/quickinstall/toggle-hide', methods=['POST'])
def api_quickinstall_toggle_hide():
    try:
        data = request.get_json(silent=True) or {}
        pkg_id = (data.get('package_id') or request.form.get('package_id') or '').strip()
        if not pkg_id:
            return jsonify({"success": False, "error": "Thiếu package_id!"})

        items = load_quickinstall_data()
        target_item = None
        for it in items:
            if it.get('package_id') == pkg_id:
                it['hidden'] = not bool(it.get('hidden', False))
                target_item = it
                break

        if not target_item:
            return jsonify({"success": False, "error": f"Không tìm thấy package_id: {pkg_id}"})

        save_quickinstall_data(items)
        push_io_ok, push_io_msg = git_push_repo(
            REPO_DIR,
            f"Toggle visibility Quick Install: {pkg_id}",
            branch="main"
        )
        state_text = "ĐÃ ẨN khỏi trang chủ" if target_item['hidden'] else "ĐÃ HIỆN lại trên trang chủ"
        msg = f"{state_text}: {target_item.get('name', pkg_id)}"
        if not push_io_ok:
            msg += f" (Chưa đẩy Git: {push_io_msg} - hãy bấm Đồng Bộ Lên Web Tức Thì)"
        return jsonify({"success": True, "hidden": target_item['hidden'], "message": msg})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/visibility-data', methods=['GET'])
def api_apps_visibility_data():
    try:
        return jsonify({
            "success": True,
            "ota_data": load_ota_data(),
            "home_settings": load_home_settings(),
            "tabs": load_app_tabs()
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/toggle-home-section', methods=['POST'])
def api_apps_toggle_home_section():
    try:
        data = request.get_json(silent=True) or {}
        settings = load_home_settings()
        settings['hide_ota_section'] = bool(data.get('hide', not settings.get('hide_ota_section', False)))
        save_home_settings(settings)
        return jsonify({"success": True, "home_settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/toggle-home-category', methods=['POST'])
def api_apps_toggle_home_category():
    try:
        data = request.get_json(silent=True) or {}
        cat = data.get('category', '')
        if not cat:
            return jsonify({"success": False, "error": "Thiếu tên chuyên mục!"})
        settings = load_home_settings()
        hidden_cats = list(settings.get('hidden_categories', []))
        hide = data.get('hide')
        if hide is None:
            hide = cat not in hidden_cats
        if hide and cat not in hidden_cats:
            hidden_cats.append(cat)
        elif not hide and cat in hidden_cats:
            hidden_cats = [c for c in hidden_cats if c != cat]
        settings['hidden_categories'] = hidden_cats
        save_home_settings(settings)
        return jsonify({"success": True, "home_settings": settings})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/toggle-item', methods=['POST'])
def api_apps_toggle_item():
    try:
        data = request.get_json(silent=True) or {}
        cat = data.get('category', '')
        idx = int(data.get('index', -1))
        field = data.get('field', '')
        tab_id = data.get('tab_id', '')

        # Tự động suy ra field nếu truyền tab_id
        if tab_id and not field:
            if tab_id.upper() == 'GUEST':
                field = 'show_on_guest'
            elif tab_id.upper() == 'PRIVATE':
                field = 'show_on_private'
            else:
                field = f"show_on_{tab_id.lower()}"

        is_valid_field = (
            field in ('show_on_home', 'hidden', 'show_on_guest', 'show_on_private')
            or field.startswith('show_on_')
        )
        if not is_valid_field:
            return jsonify({"success": False, "error": "Trường cập nhật không hợp lệ!"})

        ota_data = load_ota_data()
        if cat not in ota_data or idx < 0 or idx >= len(ota_data[cat]):
            return jsonify({"success": False, "error": "Không tìm thấy ứng dụng cần cập nhật!"})

        item = ota_data[cat][idx]
        default_val = True if field == 'show_on_home' else False
        current_val = bool(item.get(field, default_val))
        new_val = bool(data['value']) if 'value' in data else (not current_val)
        item[field] = new_val

        # Đồng bộ danh sách custom_tabs nếu là trường tuyển chọn curated
        if field.startswith('show_on_') and field != 'show_on_home':
            custom_tabs = list(item.get('custom_tabs', []))
            tab_key = tab_id if tab_id else field.replace('show_on_', '').upper()
            if new_val:
                if tab_key not in custom_tabs:
                    custom_tabs.append(tab_key)
            else:
                if tab_key in custom_tabs:
                    custom_tabs.remove(tab_key)
            item['custom_tabs'] = custom_tabs

        save_ota_data(ota_data)
        return jsonify({"success": True, "item": item})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


# ==============================================================================
# APIS QUẢN LÝ TAB ĐỘNG (THÊM, SỬA, XÓA, ĐỔI THỨ TỰ)
# ==============================================================================
@app.route('/api/tabs/list', methods=['GET'])
def api_tabs_list():
    try:
        tabs = load_app_tabs()
        return jsonify({"success": True, "tabs": tabs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/tabs/save', methods=['POST'])
def api_tabs_save():
    try:
        data = request.get_json(silent=True) or {}
        tab_id = str(data.get('id', '')).strip()
        name = str(data.get('name', '')).strip()
        icon = str(data.get('icon', '🏷️')).strip() or '🏷️'
        color = str(data.get('color', '#3b82f6')).strip() or '#3b82f6'
        tab_type = str(data.get('type', 'curated')).strip()
        description = str(data.get('description', '')).strip()
        is_edit = bool(data.get('is_edit', False))
        old_id = str(data.get('old_id', '')).strip()

        if not tab_id:
            return jsonify({"success": False, "error": "Mã Tab (ID) không được để trống!"})
        if not name:
            return jsonify({"success": False, "error": "Tên Tab không được để trống!"})
        if tab_type not in ('curated', 'category'):
            return jsonify({"success": False, "error": "Loại tab phải là 'curated' hoặc 'category'!"})

        tabs = load_app_tabs()
        existing_idx = -1
        for i, t in enumerate(tabs):
            target_match = old_id if (is_edit and old_id) else tab_id
            if t.get('id', '').lower() == target_match.lower():
                existing_idx = i
                break

        if not is_edit:
            if existing_idx != -1:
                return jsonify({"success": False, "error": f"Tab với mã '{tab_id}' đã tồn tại!"})
            new_tab = {
                "id": tab_id,
                "name": name,
                "icon": icon,
                "color": color,
                "type": tab_type,
                "system": False,
                "description": description
            }
            if tab_type == 'curated':
                new_tab["field"] = f"show_on_{tab_id.lower()}"
            tabs.append(new_tab)
        else:
            if existing_idx == -1:
                return jsonify({"success": False, "error": f"Không tìm thấy tab '{old_id or tab_id}' để sửa!"})
            target_tab = tabs[existing_idx]
            is_system = target_tab.get('system', False)

            target_tab['name'] = name
            target_tab['icon'] = icon
            target_tab['color'] = color
            target_tab['description'] = description

            if not is_system:
                target_tab['type'] = tab_type
                if tab_type == 'curated':
                    target_tab['field'] = f"show_on_{tab_id.lower()}"
                elif 'field' in target_tab:
                    del target_tab['field']

                if old_id and old_id.lower() != tab_id.lower():
                    for i, t in enumerate(tabs):
                        if i != existing_idx and t.get('id', '').lower() == tab_id.lower():
                            return jsonify({"success": False, "error": f"Mã Tab '{tab_id}' đã trùng với tab khác!"})
                    target_tab['id'] = tab_id

                    # Cập nhật trong auth_accounts
                    try:
                        auth_data = load_auth_accounts()
                        changed_auth = False
                        for acc in auth_data.get('accounts', []):
                            cats = acc.get('allowed_categories', [])
                            if old_id in cats:
                                idx_c = cats.index(old_id)
                                cats[idx_c] = tab_id
                                changed_auth = True
                        if changed_auth:
                            save_auth_accounts(auth_data)
                    except Exception:
                        pass

        save_app_tabs(tabs)
        return jsonify({"success": True, "tabs": tabs, "message": "Lưu Tab thành công!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/tabs/delete', methods=['POST'])
def api_tabs_delete():
    try:
        data = request.get_json(silent=True) or {}
        tab_id = str(data.get('id', '')).strip()
        if not tab_id:
            return jsonify({"success": False, "error": "Thiếu mã Tab cần xóa!"})

        tabs = load_app_tabs()
        target_idx = -1
        for i, t in enumerate(tabs):
            if t.get('id', '').lower() == tab_id.lower():
                target_idx = i
                break

        if target_idx == -1:
            return jsonify({"success": False, "error": f"Không tìm thấy tab '{tab_id}'!"})

        if tabs[target_idx].get('system', False):
            return jsonify({"success": False, "error": f"Không thể xóa Tab hệ thống mặc định '{tab_id}'!"})

        deleted_tab = tabs.pop(target_idx)
        save_app_tabs(tabs)

        # Xóa khỏi auth_accounts nếu có
        try:
            auth_data = load_auth_accounts()
            changed_auth = False
            for acc in auth_data.get('accounts', []):
                cats = acc.get('allowed_categories', [])
                if tab_id in cats:
                    cats.remove(tab_id)
                    changed_auth = True
            if changed_auth:
                save_auth_accounts(auth_data)
        except Exception:
            pass

        return jsonify({"success": True, "tabs": tabs, "message": f"Đã xóa tab '{deleted_tab.get('name', tab_id)}' thành công!"})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/tabs/reorder', methods=['POST'])
def api_tabs_reorder():
    try:
        data = request.get_json(silent=True) or {}
        idx = int(data.get('index', -1))
        direction = int(data.get('direction', 0))
        if direction not in (-1, 1):
            return jsonify({"success": False, "error": "Hướng di chuyển không hợp lệ!"})

        tabs = load_app_tabs()
        if idx < 0 or idx >= len(tabs):
            return jsonify({"success": False, "error": "Vị trí tab không hợp lệ!"})

        target_idx = idx + direction
        if target_idx < 0 or target_idx >= len(tabs):
            return jsonify({"success": False, "error": "Đã ở vị trí đầu hoặc cuối danh sách!"})

        tabs[idx], tabs[target_idx] = tabs[target_idx], tabs[idx]
        save_app_tabs(tabs)
        return jsonify({"success": True, "tabs": tabs})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/bulk-home-category', methods=['POST'])
def api_apps_bulk_home_category():
    try:
        data = request.get_json(silent=True) or {}
        cat = data.get('category', '')
        show_on_home = bool(data.get('show_on_home', True))
        ota_data = load_ota_data()
        if cat not in ota_data:
            return jsonify({"success": False, "error": "Không tìm thấy chuyên mục!"})
        for item in ota_data[cat]:
            item['show_on_home'] = show_on_home
        save_ota_data(ota_data)
        return jsonify({"success": True})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/delete-item', methods=['POST'])
def api_apps_delete_item():
    try:
        data = request.get_json(silent=True) or {}
        cat = data.get('category', '')
        idx = int(data.get('index', -1))
        ota_data = load_ota_data()
        if cat not in ota_data or idx < 0 or idx >= len(ota_data[cat]):
            return jsonify({"success": False, "error": "Không tìm thấy ứng dụng cần xóa!"})
        removed = ota_data[cat].pop(idx)
        save_ota_data(ota_data)
        return jsonify({"success": True, "removed": removed.get("name", "")})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/apps/move-item', methods=['POST'])
def api_apps_move_item():
    try:
        data = request.get_json(silent=True) or {}
        cat = data.get('category', '')
        idx = int(data.get('index', -1))
        direction = int(data.get('direction', 0))
        if direction not in (-1, 1):
            return jsonify({"success": False, "error": "Hướng di chuyển không hợp lệ!"})

        ota_data = load_ota_data()
        if cat not in ota_data or idx < 0 or idx >= len(ota_data[cat]):
            return jsonify({"success": False, "error": "Không tìm thấy ứng dụng!"})

        target_idx = idx + direction
        if target_idx < 0 or target_idx >= len(ota_data[cat]):
            return jsonify({"success": False, "error": "Đã ở vị trí đầu hoặc cuối chuyên mục!"})

        ota_data[cat][idx], ota_data[cat][target_idx] = ota_data[cat][target_idx], ota_data[cat][idx]
        save_ota_data(ota_data)
        return jsonify({"success": True, "new_index": target_idx})
    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


def main():
    port = 8080
    print("\n=======================================================")
    print(f"[*] Tomkids AppStore & Cydia Admin dang chay tai:")
    print(f"    http://127.0.0.1:{port}")
    print("=======================================================\n")
    if os.environ.get('WERKZEUG_RUN_MAIN') != 'true':
        try:
            webbrowser.open(f"http://127.0.0.1:{port}")
        except:
            pass
    app.run(host='127.0.0.1', port=port, debug=False)


if __name__ == '__main__':
    main()
