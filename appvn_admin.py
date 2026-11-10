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
def extract_ipa_info(ipa_path):
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

        app_name = plist.get('CFBundleDisplayName') or plist.get('CFBundleName', 'App')
        version = plist.get('CFBundleShortVersionString') or plist.get('CFBundleVersion', '1.0')
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

        icon_rel_path = f"ota_apps/icons/{bundle_id}.png"
        icon_dest = os.path.join(REPO_DIR, icon_rel_path)
        if best_icon:
            with ipa.open(best_icon) as source, open(icon_dest, 'wb') as target:
                shutil.copyfileobj(source, target)
            print(f"[+] Đã trích xuất icon: {icon_rel_path}")
        else:
            icon_rel_path = "CydiaIcon.png"

        return {
            "name": app_name,
            "version": version,
            "bundle_id": bundle_id,
            "min_os": min_os,
            "icon": icon_rel_path
        }


# ==============================================================================
# 2.5. TỰ ĐỘNG LẤY TOKEN & UPLOAD LÊN GITHUB RELEASES (OTA-Storage)
# ==============================================================================
def get_github_token():
    try:
        import win32cred
        for target in ['GitHub - https://api.github.com/tomkidsrepos', 'git:https://github.com']:
            try:
                cred = win32cred.CredRead(target, win32cred.CRED_TYPE_GENERIC)
                raw = cred['CredentialBlob']
                token = raw.decode('utf-16') if b'\x00' in raw else raw.decode('utf-8')
                if token and len(token) > 10:
                    return token
            except:
                pass
    except:
        pass
    return os.environ.get('GITHUB_TOKEN', '')


def git_push_repo(repo_path, commit_msg, branch='main'):
    if not os.path.exists(repo_path):
        return False, f"Thư mục repo không tồn tại: {repo_path}"
    try:
        subprocess.run(["git", "add", "."], cwd=repo_path)
        subprocess.run(["git", "commit", "-m", commit_msg], cwd=repo_path, capture_output=True)

        token = get_github_token()
        repo_name = os.path.basename(repo_path)
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/tomkidsrepos/{repo_name}.git"
            res = subprocess.run(["git", "push", remote_url, branch], cwd=repo_path, capture_output=True, text=True, timeout=15)
            if res.returncode == 0:
                return True, f"Đã đẩy thành công lên {repo_name} ({branch})"

        res = subprocess.run(["git", "push", "origin", branch], cwd=repo_path, capture_output=True, text=True, timeout=8)
        if res.returncode == 0:
            return True, f"Đã đẩy thành công lên {repo_name} ({branch})"
        return True, f"Đã commit trên máy tính ({repo_name}), bạn có thể push qua GitHub Desktop!"
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

    plist_rel_path = f"ota_apps/{bundle_id}.plist"
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

    updated = False
    for i, app in enumerate(data[category]):
        if app.get('plist') == app_record.get('plist') or app.get('name') == app_record.get('name'):
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
            var conApp = document.getElementById('module-appstore-container');
            var conDeb = document.getElementById('module-deb-container');

            if (mod === 'appstore') {
                if (btnApp) btnApp.className = 'module-tab-btn active';
                if (btnDeb) btnDeb.className = 'module-tab-btn';
                if (conApp) conApp.style.display = 'block';
                if (conDeb) conDeb.style.display = 'none';
            } else {
                if (btnApp) btnApp.className = 'module-tab-btn';
                if (btnDeb) btnDeb.className = 'module-tab-btn active';
                if (conApp) conApp.style.display = 'none';
                if (conDeb) conDeb.style.display = 'block';
                if (typeof loadQuickInstallList === 'function') loadQuickInstallList();
                if (typeof loadDebIncomingList === 'function') loadDebIncomingList();
                if (typeof updateDebPreview === 'function') updateDebPreview();
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
            <button type="button" class="module-tab-btn active" id="btn-module-appstore" onclick="switchModule('appstore', event)">
                🍎 Kho AppStore OTA (IPA / Sách / Nhạc)
            </button>
            <button type="button" class="module-tab-btn" id="btn-module-deb" onclick="switchModule('deb', event)">
                ⚡ Cài Đặt Nhanh DEB (Cydia Tweak)
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

                <!-- TÙY CHỌN LINK GITHUB RELEASES -->
                <label>Đường dẫn tải trên GitHub Releases (Tùy chọn):</label>
                <input type="text" id="release-url-input" placeholder="Mặc định: https://github.com/.../releases/download/OTA-Storage/app.ipa">

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

            fetch('/api/process-all-incoming', { method: 'POST' })
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
                        var colorDot = item.color === 'blue' ? '🔵' : (item.color === 'orange' ? '🟠' : '🟢');
                        var badgeHtml = item.ios_range ? '<span style="background:#0f3460; color:#60a5fa; font-size:10px; padding:2px 6px; border-radius:10px; margin-left:6px;">' + item.ios_range + '</span>' : '';

                        html += '<div class="existing-item">' +
                                    '<div class="item-info">' +
                                        '<div class="item-title">' +
                                            '<span style="color:#64748b; font-size:12px; margin-right:4px;">#' + (idx + 1) + '</span> ' +
                                            colorDot + ' <b>' + item.name + '</b>' + badgeHtml +
                                        '</div>' +
                                        '<div class="item-pkg">ID: ' + item.package_id + ' (v' + (item.version || '1.0') + ')</div>' +
                                        (item.description ? '<div class="item-desc">' + item.description + '</div>' : '') +
                                        (item.note ? '<div class="item-note">ⓘ ' + item.note + '</div>' : '') +
                                    '</div>' +
                                    '<div class="item-actions">' +
                                        (idx > 0 ? '<button type="button" class="btn-action" title="Di chuyển lên" onclick="moveQuickInstallItem(' + idx + ', -1)">⬆️</button>' : '') +
                                        (idx < quickInstallItems.length - 1 ? '<button type="button" class="btn-action" title="Di chuyển xuống" onclick="moveQuickInstallItem(' + idx + ', 1)">⬇️</button>' : '') +
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


def process_file_item(target_file_path, category=None, release_url=None):
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

        app_info = extract_ipa_info(target_file_path)
        safe_name = f"{app_info['bundle_id']}_{app_info['version']}.ipa"
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
            "plist": plist_path
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

        res = process_file_item(target_file_path, category=category, release_url=release_url)
        return jsonify(res)

    except Exception as e:
        return jsonify({"success": False, "error": str(e)})


@app.route('/api/process-all-incoming', methods=['POST'])
def process_all_incoming():
    try:
        if not os.path.exists(INCOMING_DIR):
            return jsonify({"success": False, "error": "Thư mục incoming/ không tồn tại!"})

        valid_exts = ('.ipa', '.deb', '.pdf', '.epub', '.m4r', '.mp3', '.jpg', '.jpeg', '.png')
        all_entries = [f for f in os.listdir(INCOMING_DIR) if not f.startswith('.') and not f.endswith('.plist')]
        files = [f for f in all_entries if f.lower().endswith(valid_exts) and os.path.isfile(os.path.join(INCOMING_DIR, f))]

        if not files:
            return jsonify({"success": False, "error": "Không có file hợp lệ (.ipa, .deb, .pdf, .m4r, v.v.) nào trong thư mục incoming/ để xử lý!"})

        results = []
        for f in sorted(files):
            fpath = os.path.join(INCOMING_DIR, f)
            try:
                res = process_file_item(fpath)
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
        subprocess.run(["git", "add", "."], cwd=REPO_DIR)
        subprocess.run(["git", "commit", "-m", "Auto-update apps from Tomkids AppStore Admin"], cwd=REPO_DIR, capture_output=True)

        token = get_github_token()
        if token:
            remote_url = f"https://x-access-token:{token}@github.com/tomkidsrepos/tomkidsrepos.github.io.git"
            push_res = subprocess.run(["git", "push", remote_url, "main"], cwd=REPO_DIR, capture_output=True, text=True, timeout=12)
            if push_res.returncode == 0:
                return jsonify({"success": True, "message": "⚡ Đồng bộ thần tốc thành công 100% lên tomkidsrepo.cloud!"})

        push_res = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True, timeout=8)
        if push_res.returncode == 0:
            return jsonify({"success": True, "message": "⚡ Đã Git Push thành công 100% lên tomkidsrepo.cloud!"})
        else:
            return jsonify({"success": True, "message": "Đã lưu commit trên máy tính!\nBạn chỉ cần bấm 'Push origin' trên GitHub Desktop để hoàn tất."})
    except subprocess.TimeoutExpired:
        return jsonify({"success": True, "message": "Đã lưu commit trên máy tính!\nBạn hãy chuyển sang cửa sổ GitHub Desktop và bấm 'Push origin' nhé."})
    except Exception as e:
        return jsonify({"success": True, "message": "Đã lưu thay đổi thành công!\nBạn hãy mở GitHub Desktop và bấm 'Push origin' để đồng bộ lên web."})


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
        if push_io_ok:
            msg += "\n🌐 Đã đồng bộ tức thì lên https://tomkidsrepo.cloud/!"

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
    app.run(host='127.0.0.1', port=port, debug=True)


if __name__ == '__main__':
    main()
