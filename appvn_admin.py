#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
APPVN RETRO ADMIN TOOL & AUTOMATION PIPELINE (Tomkids Repo)
-----------------------------------------------------------
Công cụ quản trị cục bộ: Tự động bóc tách IPA, DEB, Nhạc chuông M4R, Sách PDF,
tạo manifest.plist chuẩn OTA, sửa lỗi icon và đồng bộ lên GitHub Pages & Releases.
"""

import os
import sys
import json
import zipfile
import plistlib
import shutil
import io
import tarfile
import subprocess
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
import urllib.parse

REPO_DIR = os.path.dirname(os.path.abspath(__file__))
OTA_APPS_DIR = os.path.join(REPO_DIR, 'ota_apps')
ICONS_DIR = os.path.join(OTA_APPS_DIR, 'icons')
DATA_JSON_PATH = os.path.join(REPO_DIR, 'ota_data.json')
INCOMING_DIR = os.path.join(REPO_DIR, 'incoming')

os.makedirs(OTA_APPS_DIR, exist_ok=True)
os.makedirs(ICONS_DIR, exist_ok=True)
os.makedirs(INCOMING_DIR, exist_ok=True)


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

        # Tìm Icon phù hợp
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

    print(f"[+] Đã tạo manifest plist: {plist_rel_path}")
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

    print(f"[+] Đã cập nhật ota_data.json cho '{app_record['name']}' vào mục '{category}'")


# ==============================================================================
# 4. WEB ADMIN INTERFACE CỤC BỘ (HTTP://LOCALHOST:8080)
# ==============================================================================
HTML_TEMPLATE = '''<!DOCTYPE html>
<html>
<head>
    <meta charset="utf-8">
    <title>AppVN Admin - Tomkids Repo</title>
    <style>
        body { font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif; background: #0f172a; color: white; padding: 30px; margin: 0; }
        .container { max-width: 800px; margin: 0 auto; background: #1e293b; padding: 30px; border-radius: 16px; box-shadow: 0 10px 30px rgba(0,0,0,0.5); }
        h1 { color: #38bdf8; margin-top: 0; display: flex; align-items: center; gap: 10px; font-size: 24px; }
        .badge { background: #2563eb; color: white; font-size: 12px; padding: 3px 8px; border-radius: 8px; }
        label { display: block; margin-top: 15px; font-weight: bold; color: #94a3b8; font-size: 14px; }
        input[type="text"], select { width: 100%; padding: 10px 14px; margin-top: 6px; border-radius: 8px; border: 1px solid #334155; background: #0f172a; color: white; box-sizing: border-box; font-size: 14px; }
        .dropzone { border: 2px dashed #38bdf8; border-radius: 12px; padding: 35px 20px; text-align: center; margin-top: 15px; background: rgba(56,189,248,0.05); cursor: pointer; }
        .dropzone:hover { background: rgba(56,189,248,0.12); }
        .btn { background: #2563eb; color: white; padding: 12px 24px; border: none; border-radius: 10px; font-weight: bold; cursor: pointer; font-size: 15px; margin-top: 20px; display: inline-block; text-decoration: none; }
        .btn:hover { background: #1d4ed8; }
        .btn-green { background: #16a34a; }
        .btn-green:hover { background: #15803d; }
        .card-list { margin-top: 25px; background: #0f172a; border-radius: 12px; padding: 15px; }
        .status-msg { margin-top: 15px; padding: 12px; border-radius: 8px; background: #1e3a8a; font-size: 14px; display: none; }
    </style>
</head>
<body>
    <div class="container">
        <h1><span>🚀 AppVN Admin Portal</span> <span class="badge">Tomkids Repo</span></h1>
        <p style="color:#94a3b8; font-size:14px;">Tự động phân tích file IPA, DEB, tạo manifest OTA và cập nhật kho ứng dụng cho iOS cổ.</p>

        <form method="POST" action="/process" enctype="application/x-www-form-urlencoded">
            <label>1. Tên file trong thư mục "incoming" (hoặc đường link trực tiếp / Google Drive):</label>
            <input type="text" name="file_source" placeholder="VD: FlappyBird.ipa hoặc https://..." required>

            <label>2. Chọn Chuyên mục:</label>
            <select name="category">
                <option value="Trò Chơi">🎮 Trò Chơi</option>
                <option value="Mạng Xã Hội">🌐 Mạng Xã Hội</option>
                <option value="Giải Trí">🎵 Giải Trí / Media</option>
                <option value="Công Cụ">🛠️ Công Cụ / Tiện ích</option>
                <option value="Hệ thống">⚙️ Hệ thống</option>
                <option value="Jailbreak">🔓 Jailbreak</option>
            </select>

            <label>3. Đường dẫn tải trực tiếp trên GitHub Releases (Nếu đã có link):</label>
            <input type="text" name="release_url" placeholder="Để trống nếu muốn tự tạo đường dẫn Releases mặc định">

            <button type="submit" class="btn">⚡ Bắt Đầu Xử Lý Tự Động</button>
        </form>

        <div style="margin-top: 35px; border-top: 1px solid #334155; padding-top: 20px; display: flex; justify-content: space-between; align-items: center;">
            <div>
                <b style="color: #cbd5e1;">Đồng bộ lên GitHub:</b>
                <p style="color: #64748b; font-size: 13px; margin: 4px 0 0 0;">Đẩy code và app mới lên tomkidsrepo.cloud</p>
            </div>
            <form method="POST" action="/git-push" style="margin:0;">
                <button type="submit" class="btn btn-green">📤 Git Commit & Push</button>
            </form>
        </div>
    </div>
</body>
</html>
'''

class AdminHTTPHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.send_header('Content-Type', 'text/html; charset=utf-8')
        self.end_headers()
        self.wfile.write(HTML_TEMPLATE.encode('utf-8'))

    def do_POST(self):
        length = int(self.headers.get('Content-Length', 0))
        body = self.rfile.read(length).decode('utf-8')
        params = urllib.parse.parse_qs(body)

        if self.path == '/process':
            source = params.get('file_source', [''])[0].strip()
            category = params.get('category', ['Trò Chơi'])[0]
            rel_url = params.get('release_url', [''])[0].strip()

            result_msg = ""
            try:
                # Kiểm tra nếu file nằm trong thư mục incoming/
                local_path = os.path.join(INCOMING_DIR, source)
                if not os.path.exists(local_path):
                    local_path = source

                if source.endswith('.deb'):
                    out_ipa = os.path.join(INCOMING_DIR, os.path.basename(source).replace('.deb', '.ipa'))
                    deb_to_ipa(local_path, out_ipa)
                    local_path = out_ipa

                if os.path.exists(local_path) and local_path.endswith('.ipa'):
                    app_info = extract_ipa_info(local_path)
                    safe_name = os.path.basename(local_path)
                    if not rel_url:
                        rel_url = f"https://github.com/tomkidsrepos/tomkidsrepos.github.io/releases/download/OTA-Storage/{safe_name}"

                    plist_path = create_ota_plist(app_info, rel_url)
                    record = {
                        "name": app_info["name"],
                        "version": app_info["version"],
                        "icon": app_info["icon"],
                        "plist": plist_path
                    }
                    update_ota_json(category, record)
                    result_msg = f"Thành công! Đã xử lý '{app_info['name']}' ({app_info['version']}) vào danh mục {category}."
                else:
                    result_msg = f"Lỗi: Không tìm thấy file IPA/DEB tại: {local_path}"
            except Exception as e:
                result_msg = f"Đã xảy ra lỗi: {str(e)}"

            response_html = f'''<html><head><meta charset="utf-8"></head><body style="background:#0f172a; color:white; font-family:sans-serif; padding:40px; text-align:center;">
                <h2>{result_msg}</h2>
                <br><a href="/" style="background:#2563eb; color:white; padding:10px 20px; border-radius:8px; text-decoration:none;">Quay lại Admin</a>
            </body></html>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(response_html.encode('utf-8'))

        elif self.path == '/git-push':
            try:
                subprocess.run(["git", "add", "."], cwd=REPO_DIR, check=True)
                subprocess.run(["git", "commit", "-m", "Auto-update apps from AppVN Admin"], cwd=REPO_DIR, check=True)
                subprocess.run(["git", "push"], cwd=REPO_DIR, check=True)
                msg = "Đã đồng bộ Git Push thành công lên tomkidsrepo.cloud!"
            except Exception as e:
                msg = f"Lỗi Git Push: {str(e)}"

            response_html = f'''<html><head><meta charset="utf-8"></head><body style="background:#0f172a; color:white; font-family:sans-serif; padding:40px; text-align:center;">
                <h2>{msg}</h2>
                <br><a href="/" style="background:#2563eb; color:white; padding:10px 20px; border-radius:8px; text-decoration:none;">Quay lại Admin</a>
            </body></html>'''
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write(response_html.encode('utf-8'))


def run_server(port=8080):
    server = HTTPServer(('127.0.0.1', port), AdminHTTPHandler)
    url = f"http://127.0.0.1:{port}"
    print(f"\n=======================================================")
    print(f"🚀 AppVN Admin Portal đang chạy tại: {url}")
    print(f"   Mở trình duyệt trên máy tính để quản trị và đưa app lên!")
    print(f"=======================================================\n")
    try:
        webbrowser.open(url)
    except:
        pass
    server.serve_forever()


if __name__ == '__main__':
    if len(sys.argv) > 1 and sys.argv[1] == 'server':
        run_server()
    elif len(sys.argv) == 4:
        # CLI Mode: python appvn_admin.py <file_path> <category> <download_url>
        fpath = sys.argv[1]
        cat = sys.argv[2]
        durl = sys.argv[3]
        if fpath.endswith('.deb'):
            out_ipa = fpath.replace('.deb', '.ipa')
            deb_to_ipa(fpath, out_ipa)
            fpath = out_ipa
        info = extract_ipa_info(fpath)
        plist_path = create_ota_plist(info, durl)
        rec = {
            "name": info["name"],
            "version": info["version"],
            "icon": info["icon"],
            "plist": plist_path
        }
        update_ota_json(cat, rec)
        print("Hoàn tất xử lý CLI!")
    else:
        # Chạy giao diện Web mặc định
        run_server()
