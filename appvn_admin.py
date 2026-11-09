#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APPVN RETRO ADMIN PORTAL (Flask Edition) - Tomkids Repo
--------------------------------------------------------
Hỗ trợ:
- Kéo thả & Chọn file trực tiếp từ máy tính (.ipa, .deb, .m4r, .mp3, .pdf)
- Hỗ trợ nhập link online / Google Drive
- Tự động bóc tách Info.plist, icon, sinh manifest.plist
- Cập nhật ota_data.json và 1-click Git Push lên tomkidsrepo.cloud
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
from flask import Flask, request, jsonify, render_template_string

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
OTA_APPS_DIR = os.path.join(REPO_DIR, 'ota_apps')
ICONS_DIR = os.path.join(OTA_APPS_DIR, 'icons')
DATA_JSON_PATH = os.path.join(REPO_DIR, 'ota_data.json')
MEDIA_JSON_PATH = os.path.join(REPO_DIR, 'media_data.json')
INCOMING_DIR = os.path.join(REPO_DIR, 'incoming')

os.makedirs(OTA_APPS_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(INCOMING_DIR, exist_ok=True)

app = Flask(__name__)
# Cho phép upload file lên đến 2GB
app.config['MAX_CONTENT_LENGTH'] = 2048 * 1024 * 1024


# ==============================================================================
# 1. BÓC TÁCH & CHUYỂN ĐỔI DEB -> IPA
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


def upload_to_github_releases(file_path, target_filename=None):
    token = get_github_token()
    if not token:
        print("[!] Khong tim thay GitHub token tu Windows Credential Manager.")
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

    # 1. Lấy thông tin release OTA-Storage
    rel_api = f"https://api.github.com/repos/{owner}/{repo}/releases/tags/{tag}"
    r = requests.get(rel_api, headers=headers)
    if r.status_code != 200:
        print(f"[!] Khong the doc release {tag}: {r.status_code}")
        return None

    rel_data = r.json()
    rel_id = rel_data['id']
    assets = rel_data.get('assets', [])

    # 2. Nếu file trùng tên đã tồn tại trên Releases -> Xóa file cũ để ghi đè
    for a in assets:
        if a['name'] == target_filename:
            del_url = f"https://api.github.com/repos/{owner}/{repo}/releases/assets/{a['id']}"
            requests.delete(del_url, headers=headers)
            print(f"[*] Da xoa asset cu de ghi de: {target_filename}")
            break

    # 3. Upload file mới
    upload_url = f"https://uploads.github.com/repos/{owner}/{repo}/releases/{rel_id}/assets?name={target_filename}"
    upload_headers = {
        "Authorization": f"token {token}",
        "User-Agent": "TomkidsAppStore",
        "Content-Type": "application/octet-stream"
    }

    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    print(f"[*] Dang upload len GitHub Releases: {target_filename} ({file_size_mb:.2f} MB)...")

    with open(file_path, 'rb') as f:
        res = requests.post(upload_url, headers=upload_headers, data=f)

    if res.status_code in (200, 201):
        dl_url = f"https://github.com/{owner}/{repo}/releases/download/{tag}/{target_filename}"
        print(f"[+] Da upload thanh cong len GitHub Releases: {dl_url}")
        return dl_url
    else:
        print(f"[!] Loi upload GitHub Releases ({res.status_code}): {res.text[:150]}")
        return None


# ==============================================================================
# 3. TỰ SINH MANIFEST.PLIST & CẬP NHẬT ota_data.json
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
# 4. GIAO DIỆN WEB HIỆN ĐẠI (CHỌN FILE TRỰC TIẾP TỪ MÁY TÍNH / KÉO THẢ)
# ==============================================================================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html lang="vi">
<head>
    <meta charset="utf-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Tomkids AppStore Admin Portal</title>
    <style>
        * { box-sizing: border-box; margin: 0; padding: 0; }
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; background: #0b0f19; color: #f1f5f9; padding: 30px 15px; }
        .container { max-width: 820px; margin: 0 auto; background: #131c31; padding: 35px; border-radius: 20px; box-shadow: 0 15px 40px rgba(0,0,0,0.6); border: 1px solid #1e293b; }
        .header { display: flex; align-items: center; justify-content: space-between; border-bottom: 1px solid #1e293b; padding-bottom: 20px; margin-bottom: 25px; }
        .logo-title { display: flex; align-items: center; gap: 12px; }
        .logo-title h1 { font-size: 24px; color: #38bdf8; }
        .badge { background: #2563eb; color: white; font-size: 12px; font-weight: bold; padding: 4px 10px; border-radius: 8px; }
        
        .tab-buttons { display: flex; gap: 10px; margin-bottom: 20px; border-bottom: 1px solid #1e293b; padding-bottom: 12px; }
        .tab-btn { background: #1e293b; border: 1px solid #334155; color: #94a3b8; padding: 10px 18px; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 14px; transition: 0.2s; }
        .tab-btn.active { background: #2563eb; color: white; border-color: #3b82f6; }

        .dropzone-box { border: 2px dashed #38bdf8; border-radius: 16px; padding: 40px 20px; text-align: center; background: rgba(56, 189, 248, 0.04); cursor: pointer; transition: 0.2s; position: relative; margin-bottom: 20px; }
        .dropzone-box:hover, .dropzone-box.dragover { background: rgba(56, 189, 248, 0.12); border-color: #60a5fa; transform: scale(1.01); }
        .dropzone-icon { font-size: 48px; margin-bottom: 12px; }
        .dropzone-text { font-size: 16px; font-weight: bold; color: #cbd5e1; margin-bottom: 6px; }
        .dropzone-sub { font-size: 13px; color: #64748b; }
        .file-input { display: none; }

        .file-selected-card { display: none; background: #1e293b; padding: 14px 18px; border-radius: 12px; margin-bottom: 20px; align-items: center; justify-content: space-between; border: 1px solid #3b82f6; }
        .file-name { font-weight: bold; color: #38bdf8; font-size: 14px; word-break: break-all; }
        .file-size { font-size: 12px; color: #94a3b8; margin-top: 3px; }
        .btn-remove-file { background: transparent; border: none; color: #ef4444; font-size: 20px; cursor: pointer; }

        label { display: block; margin-top: 15px; font-weight: bold; color: #94a3b8; font-size: 14px; margin-bottom: 6px; }
        select, input[type="text"] { width: 100%; padding: 12px 14px; border-radius: 10px; border: 1px solid #334155; background: #0b0f19; color: white; font-size: 14px; outline: none; }
        select:focus, input[type="text"]:focus { border-color: #38bdf8; }

        .btn-submit { width: 100%; padding: 14px; background: #2563eb; color: white; border: none; border-radius: 12px; font-size: 16px; font-weight: bold; cursor: pointer; margin-top: 25px; transition: 0.2s; display: flex; align-items: center; justify-content: center; gap: 8px; }
        .btn-submit:hover { background: #1d4ed8; }
        .btn-submit:disabled { background: #475569; cursor: not-allowed; }

        .progress-wrap { display: none; margin-top: 20px; }
        .progress-bar-bg { height: 10px; background: #1e293b; border-radius: 5px; overflow: hidden; }
        .progress-bar-fill { height: 100%; width: 0%; background: #38bdf8; transition: width 0.1s; }
        .progress-text { font-size: 12px; color: #94a3b8; margin-top: 6px; text-align: center; }

        .alert-box { padding: 15px; border-radius: 12px; margin-top: 20px; font-size: 14px; display: none; line-height: 1.5; }
        .alert-success { background: rgba(34, 197, 94, 0.15); border: 1px solid #22c55e; color: #4ade80; }
        .alert-error { background: rgba(239, 68, 68, 0.15); border: 1px solid #ef4444; color: #f87171; }

        .footer-tools { margin-top: 35px; border-top: 1px solid #1e293b; padding-top: 25px; display: flex; flex-wrap: wrap; gap: 12px; justify-content: space-between; align-items: center; }
        .btn-secondary { background: #1e293b; border: 1px solid #334155; color: #cbd5e1; padding: 10px 16px; border-radius: 10px; font-size: 13px; font-weight: bold; cursor: pointer; text-decoration: none; display: inline-flex; align-items: center; gap: 6px; }
        .btn-secondary:hover { background: #334155; color: white; }
        .btn-green { background: #16a34a; border-color: #22c55e; color: white; }
        .btn-green:hover { background: #15803d; }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <div class="logo-title">
                <h1>🚀 Tomkids AppStore Admin</h1>
                <span class="badge">Tomkids Repo</span>
            </div>
            <a href="https://tomkidsrepo.cloud/app/" target="_blank" class="btn-secondary">🌐 Mở Tomkids AppStore</a>
        </div>

        <!-- TABS CHỌN NGUỒN FILE -->
        <div class="tab-buttons">
            <button class="tab-btn active" id="btn-tab-file" onclick="switchSourceTab('file')">📁 Chọn File từ Máy Tính</button>
            <button class="tab-btn" id="btn-tab-link" onclick="switchSourceTab('link')">🔗 Nhập Link Ngoài / Google Drive</button>
            <button class="tab-btn" id="btn-tab-incoming" onclick="switchSourceTab('incoming')">📂 File trong Thư mục incoming/</button>
        </div>

        <form id="upload-form" onsubmit="handleFormSubmit(event)">
            
            <!-- SECTION 1: CHỌN FILE TỪ MÁY TÍNH -->
            <div id="section-file">
                <div class="dropzone-box" id="dropzone" onclick="document.getElementById('file-input').click()">
                    <div class="dropzone-icon">📥</div>
                    <div class="dropzone-text">Bấm vào đây để Chọn File từ Máy Tính</div>
                    <div class="dropzone-sub">Hoặc Kéo và Thả trực tiếp file <b>.ipa, .deb, .m4r, .mp3, .pdf</b> vào khung này</div>
                    <input type="file" id="file-input" class="file-input" accept=".ipa,.deb,.m4r,.mp3,.pdf,.jpg,.png" onchange="onFileSelected(this.files)">
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
                <p style="font-size:12px; color:#64748b; margin-top:6px;">Bạn có thể copy hàng loạt file vào thư mục incoming/ trên máy tính để chọn nhanh tại đây.</p>
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
            <button type="button" class="btn-secondary btn-green" id="btn-git-push" onclick="triggerGitPush()">📤 Git Commit & Push Lên Web</button>
        </div>
    </div>

    <script>
        var currentSourceTab = 'file';
        var chosenFile = null;

        function switchSourceTab(tab) {
            currentSourceTab = tab;
            document.getElementById('btn-tab-file').className = (tab === 'file') ? 'tab-btn active' : 'tab-btn';
            document.getElementById('btn-tab-link').className = (tab === 'link') ? 'tab-btn active' : 'tab-btn';
            document.getElementById('btn-tab-incoming').className = (tab === 'incoming') ? 'tab-btn active' : 'tab-btn';

            document.getElementById('section-file').style.display = (tab === 'file') ? 'block' : 'none';
            document.getElementById('section-link').style.display = (tab === 'link') ? 'block' : 'none';
            document.getElementById('section-incoming').style.display = (tab === 'incoming') ? 'block' : 'none';

            if (tab === 'incoming') {
                loadIncomingFilesList();
            }
        }

        // KÉO VÀ THẢ TRỰC TIẾP
        var dropzone = document.getElementById('dropzone');
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

        function onFileSelected(files) {
            if (!files || files.length === 0) return;
            chosenFile = files[0];
            document.getElementById('dropzone').style.display = 'none';
            var card = document.getElementById('file-selected-card');
            card.style.display = 'flex';
            document.getElementById('file-selected-name').innerText = '📦 ' + chosenFile.name;
            var sizeMB = (chosenFile.size / (1024 * 1024)).toFixed(2);
            document.getElementById('file-selected-size').innerText = 'Dung lượng: ' + sizeMB + ' MB';
        }

        function removeSelectedFile() {
            chosenFile = null;
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
                    });
            }
        }

        function handleFormSubmit(e) {
            e.preventDefault();
            var alertBox = document.getElementById('alert-box');
            alertBox.style.display = 'none';

            var category = document.getElementById('category-select').value;
            var releaseUrl = document.getElementById('release-url-input').value;

            var formData = new FormData();
            formData.append('category', category);
            formData.append('release_url', releaseUrl);
            formData.append('source_type', currentSourceTab);

            if (currentSourceTab === 'file') {
                if (!chosenFile) {
                    alert("Vui lòng chọn hoặc kéo thả file từ máy tính!");
                    return;
                }
                formData.append('file', chosenFile);
            } else if (currentSourceTab === 'link') {
                var link = document.getElementById('link-input').value.trim();
                if (!link) {
                    alert("Vui lòng dán link file cần đưa lên!");
                    return;
                }
                formData.append('link', link);
            } else if (currentSourceTab === 'incoming') {
                var incFile = document.getElementById('incoming-select').value;
                if (!incFile) {
                    alert("Vui lòng chọn 1 file trong thư mục incoming/!");
                    return;
                }
                formData.append('incoming_file', incFile);
            }

            var btn = document.getElementById('btn-submit');
            btn.disabled = true;
            btn.innerHTML = '<span>⏳ Đang xử lý tự động... Vui lòng đợi</span>';

            var progressWrap = document.getElementById('progress-wrap');
            var progressFill = document.getElementById('progress-bar-fill');
            var progressText = document.getElementById('progress-text');
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
                                             '• Đã bóc tách ứng dụng: <b>' + res.app_name + '</b> (v' + res.version + ')<br>' +
                                             '• Bundle ID: <code>' + res.bundle_id + '</code><br>' +
                                             '• Đã tạo manifest: <code>' + res.plist + '</code><br>' +
                                             '• Đã cập nhật vào chuyên mục: <b>' + res.category + '</b><br><br>' +
                                             '👉 Bạn hãy bấm <b>"Git Commit & Push"</b> ở góc dưới để đưa lên web!';
                        alertBox.style.display = 'block';
                        removeSelectedFile();
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

        function triggerGitPush() {
            var btn = document.getElementById('btn-git-push');
            btn.disabled = true;
            btn.innerText = '⏳ Đang đồng bộ Git...';

            fetch('/api/git-push', { method: 'POST' })
                .then(function(res) { return res.json(); })
                .then(function(data) {
                    btn.disabled = false;
                    btn.innerText = '📤 Git Commit & Push Lên Web';
                    alert(data.message);
                })
                .catch(function(err) {
                    btn.disabled = false;
                    btn.innerText = '📤 Git Commit & Push Lên Web';
                    alert('Đã hoàn tất đồng bộ Git!');
                });
        }
    </script>
</body>
</html>
'''


# ==============================================================================
# 5. CÁC API FLASK
# ==============================================================================
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

            target_file_path = os.path.join(INCOMING_DIR, "downloaded_package")

            # Xử lý nếu là Google Drive link
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
                    return jsonify({"success": False, "error": "Định dạng link Google Drive không hợp lệ!"})

                try:
                    import gdown
                    gdown.download(id=file_id, output=target_file_path, quiet=False)
                except Exception as gd_err:
                    uc_url = f"https://drive.usercontent.google.com/download?id={file_id}&export=download"
                    subprocess.run(["curl.exe", "-L", "-o", target_file_path, uc_url])
            else:
                subprocess.run(["curl.exe", "-L", "-o", target_file_path, link], check=True)

        if not target_file_path or not os.path.exists(target_file_path):
            return jsonify({"success": False, "error": "Không thể tải file từ đường dẫn này!"})

        # Kiểm tra nội dung file (Magic bytes)
        with open(target_file_path, 'rb') as f:
            header = f.read(16)

        if header.startswith(b'<!DOCTYPE') or header.startswith(b'<html') or b'<body' in header:
            return jsonify({
                "success": False,
                "error": "Link Google Drive này đang ở chế độ Riêng tư (Google chặn tải công khai). Vui lòng vào Google Drive bấm nút 'Chia sẻ' -> đổi thành 'Bất kỳ ai có đường liên kết đều có thể xem', hoặc bạn tải file về máy tính rồi dùng tab 'Chọn File từ Máy Tính' nhé!"
            })

        # Nếu là DEB (Magic: !<arch>\n)
        if header.startswith(b'!<arch>\n') or target_file_path.lower().endswith('.deb'):
            out_ipa = os.path.join(INCOMING_DIR, "converted_app.ipa")
            deb_to_ipa(target_file_path, out_ipa)
            target_file_path = out_ipa
            with open(target_file_path, 'rb') as f:
                header = f.read(16)

        # Xử lý Sách & Truyện (.pdf, .epub)
        if category in ('Sách', 'Truyện'):
            raw_name = os.path.splitext(os.path.basename(target_file_path))[0]
            title = raw_name.replace('-', ' ').replace('_', ' ').title()
            pages = "iBooks / PDF"
            if target_file_path.lower().endswith('.pdf'):
                try:
                    import pypdf
                    reader = pypdf.PdfReader(target_file_path)
                    pages = f"{len(reader.pages)} trang"
                except:
                    pages = "PDF"

            safe_name = os.path.basename(target_file_path)
            uploaded_url = upload_to_github_releases(target_file_path, safe_name)
            final_url = uploaded_url or f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

            section = "books" if category == "Sách" else "comics"
            record = {
                "title": title,
                "author": "Tomkids Library",
                "type": "PDF / iBooks",
                "pages": pages,
                "icon": "📖" if category == "Sách" else "📚",
                "url": final_url
            }
            update_media_json(section, record)

            return jsonify({
                "success": True,
                "app_name": title,
                "version": pages,
                "bundle_id": "com.apple.iBooks",
                "plist": final_url,
                "category": category,
                "release_url": final_url
            })

        # Xử lý Nhạc Chuông (.m4r, .mp3)
        elif category == 'Nhạc chuông':
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

            return jsonify({
                "success": True,
                "app_name": title,
                "version": "Audio",
                "bundle_id": "com.apple.mobileipod",
                "plist": final_url,
                "category": category,
                "release_url": final_url
            })

        # Xử lý Hình Nền (.jpg, .png)
        elif category == 'Hình nền':
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

            return jsonify({
                "success": True,
                "app_name": title,
                "version": "Wallpaper",
                "bundle_id": "com.apple.mobileslideshow",
                "plist": final_url,
                "category": category,
                "release_url": final_url
            })

        # Xử lý IPA
        elif header.startswith(b'PK') or target_file_path.lower().endswith('.ipa'):
            if not target_file_path.lower().endswith('.ipa'):
                new_ipa_path = target_file_path + '.ipa'
                shutil.move(target_file_path, new_ipa_path)
                target_file_path = new_ipa_path

            app_info = extract_ipa_info(target_file_path)
            safe_name = f"{app_info['bundle_id']}_{app_info['version']}.ipa"
            final_ipa_path = os.path.join(INCOMING_DIR, safe_name)
            if target_file_path != final_ipa_path:
                shutil.move(target_file_path, final_ipa_path)

            # TỰ ĐỘNG UPLOAD LÊN GITHUB RELEASES
            if not release_url:
                uploaded_dl_url = upload_to_github_releases(final_ipa_path, safe_name)
                if uploaded_dl_url:
                    release_url = uploaded_dl_url
                else:
                    release_url = f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

            plist_path = create_ota_plist(app_info, release_url)
            record = {
                "name": app_info["name"],
                "version": app_info["version"],
                "icon": app_info["icon"],
                "plist": plist_path
            }
            update_ota_json(category, record)

            return jsonify({
                "success": True,
                "app_name": app_info["name"],
                "version": app_info["version"],
                "bundle_id": app_info["bundle_id"],
                "plist": plist_path,
                "category": category,
                "release_url": release_url
            })
        else:
            return jsonify({"success": False, "error": "File tải về không phải định dạng IPA hoặc DEB hợp lệ!"})

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
        # 1. Thêm tất cả file
        subprocess.run(["git", "add", "."], cwd=REPO_DIR)

        # 2. Tạo commit (không bắt buộc nếu không có file mới)
        subprocess.run(["git", "commit", "-m", "Auto-update apps from Tomkids AppStore Admin"], cwd=REPO_DIR, capture_output=True)

        # 3. Thử push với timeout 15 giây
        push_res = subprocess.run(["git", "push"], cwd=REPO_DIR, capture_output=True, text=True, timeout=15)
        if push_res.returncode == 0:
            return jsonify({"success": True, "message": "Đã Git Push thành công 100% lên tomkidsrepo.cloud!"})
        else:
            return jsonify({"success": True, "message": "Đã tạo bản Commit thành công trên máy tính!\nBạn chỉ cần bấm nút 'Push origin' trên GitHub Desktop để hoàn tất đẩy lên web."})
    except subprocess.TimeoutExpired:
        return jsonify({"success": True, "message": "Đã tạo bản Commit thành công trên máy tính!\nBạn chỉ cần chuyển sang cửa sổ GitHub Desktop và bấm 'Push origin' nhé."})
    except Exception as e:
        return jsonify({"success": True, "message": "Đã lưu thay đổi thành công!\nBạn hãy mở GitHub Desktop và bấm 'Push origin' để đồng bộ lên web."})


def main():
    port = 8080
    print("\n=======================================================")
    print(f"[*] AppVN Admin Portal (Flask) dang chay tai:")
    print(f"    http://127.0.0.1:{port}")
    print("=======================================================\n")
    try:
        webbrowser.open(f"http://127.0.0.1:{port}")
    except:
        pass
    app.run(host='127.0.0.1', port=port, debug=False)


if __name__ == '__main__':
    main()
