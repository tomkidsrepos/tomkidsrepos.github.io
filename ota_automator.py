import sys
import zipfile
import plistlib
import json
import os
import io
import shutil
import tarfile

# ────────────────────────────────────────────────
# HELPERS – DEB (AR archive) parsing
# ────────────────────────────────────────────────

def _read_deb_member(deb_path, target_name):
    """Return raw bytes of a named member from a DEB (AR-format) file."""
    with open(deb_path, 'rb') as f:
        magic = f.read(8)
        if magic != b'!<arch>\n':
            raise Exception("Not a valid DEB file (bad magic)")
        while True:
            header = f.read(60)
            if len(header) < 60:
                break
            name = header[0:16].strip().decode('ascii', errors='replace')
            size = int(header[48:58].strip())
            data = f.read(size)
            if size % 2:
                f.read(1)   # AR padding byte
            if target_name in name:
                return data
    return None


def deb_to_ipa(deb_path, output_ipa_path):
    """
    Convert a DEB package that contains a .app bundle into an IPA file.
    Returns the output_ipa_path on success.
    """
    print(f"Converting DEB → IPA: {deb_path}")

    # 1. Read the data section (handles .gz / .xz / .bz2 / .lzma)
    data_raw = _read_deb_member(deb_path, 'data')
    if not data_raw:
        raise Exception("No data.tar.* section found in DEB")

    data_tar = tarfile.open(fileobj=io.BytesIO(data_raw), mode='r:*')

    # 2. Locate the .app directory inside the tar
    app_dir_path = None
    for m in data_tar.getmembers():
        if m.isdir() and m.name.rstrip('/').endswith('.app'):
            # Prefer /Applications/ path (system apps) over others
            if '/Applications/' in m.name or m.name.startswith('./Applications/'):
                app_dir_path = m.name.rstrip('/')
                break
    if not app_dir_path:
        for m in data_tar.getmembers():
            if m.isdir() and m.name.rstrip('/').endswith('.app'):
                app_dir_path = m.name.rstrip('/')
                break
    if not app_dir_path:
        raise Exception("No .app bundle found inside DEB data")

    app_name = os.path.basename(app_dir_path)
    print(f"Found .app bundle: {app_name}")

    # 3. Repack into IPA (Payload/AppName.app/...)
    payload_prefix = app_dir_path + '/'
    os.makedirs(os.path.dirname(output_ipa_path) or '.', exist_ok=True)

    with zipfile.ZipFile(output_ipa_path, 'w', zipfile.ZIP_DEFLATED) as zf:
        for m in data_tar.getmembers():
            if m.isfile() and m.name.startswith(payload_prefix):
                rel = m.name[len(payload_prefix):]        # path inside .app
                arcname = f"Payload/{app_name}/{rel}"
                try:
                    fobj = data_tar.extractfile(m)
                    if fobj:
                        zf.writestr(arcname, fobj.read())
                except Exception as e:
                    print(f"  Warning: skipped {m.name}: {e}")

    print(f"IPA created: {output_ipa_path}")
    return output_ipa_path


# ────────────────────────────────────────────────
# HELPERS – IPA metadata extraction
# ────────────────────────────────────────────────

def extract_ipa_info(ipa_path):
    print(f"Extracting info from {ipa_path}...")
    with zipfile.ZipFile(ipa_path, 'r') as ipa:
        info_plist_path = None
        for name in ipa.namelist():
            if name.startswith('Payload/') and name.endswith('.app/Info.plist') and name.count('/') == 2:
                info_plist_path = name
                break

        if not info_plist_path:
            raise Exception("Info.plist not found in IPA!")

        with ipa.open(info_plist_path) as f:
            plist = plistlib.load(f)

        app_name    = plist.get('CFBundleDisplayName') or plist.get('CFBundleName', 'Unknown App')
        version     = plist.get('CFBundleShortVersionString') or plist.get('CFBundleVersion', '1.0')
        bundle_id   = plist.get('CFBundleIdentifier', 'com.unknown.app')

        # Icon extraction
        icon_names = []
        if 'CFBundleIconFiles' in plist:
            icon_names = plist['CFBundleIconFiles']
        elif 'CFBundleIcons' in plist and 'CFBundlePrimaryIcon' in plist.get('CFBundleIcons', {}):
            icon_names = plist['CFBundleIcons']['CFBundlePrimaryIcon'].get('CFBundleIconFiles', [])
        if not icon_names:
            icon_names = ['Icon', 'AppIcon']

        app_folder  = info_plist_path.replace('Info.plist', '')
        best_icon   = None
        for name in ipa.namelist():
            if name.startswith(app_folder):
                basename = os.path.basename(name)
                for iname in icon_names:
                    if iname in basename and basename.endswith('.png'):
                        best_icon = name
                        if '@2x' in basename or '@3x' in basename:
                            break

        if best_icon:
            os.makedirs('ota_apps/icons', exist_ok=True)
            icon_dest = f"ota_apps/icons/{bundle_id}.png"
            with ipa.open(best_icon) as source, open(icon_dest, 'wb') as target:
                shutil.copyfileobj(source, target)
            print(f"Extracted icon to {icon_dest}")
        else:
            icon_dest = "CydiaIcon.png"

        return app_name, version, bundle_id, icon_dest


# ────────────────────────────────────────────────
# HELPERS – plist / JSON
# ────────────────────────────────────────────────

def create_ota_plist(name, version, bundle_id, ipa_url, icon_url):
    plist_path = f"ota_apps/{bundle_id}.plist"
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
					<string>{ipa_url}</string>
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
    os.makedirs('ota_apps', exist_ok=True)
    with open(plist_path, 'w', encoding='utf-8') as f:
        f.write(xml_content)
    return plist_path


def update_ota_json(category, app_data):
    json_path = 'ota_data.json'
    with open(json_path, 'r', encoding='utf-8-sig') as f:
        data = json.load(f)

    if category not in data:
        data[category] = []

    updated = False
    for i, app in enumerate(data[category]):
        if app['plist'] == app_data['plist']:
            data[category][i] = app_data
            updated = True
            break

    if not updated:
        data[category].append(app_data)

    with open(json_path, 'w', encoding='utf-8') as f:
        json.dump(data, f, ensure_ascii=False, indent=4)

    print(f"Updated ota_data.json with {app_data['name']}")


# ────────────────────────────────────────────────
# ENTRY POINT
# ────────────────────────────────────────────────

if __name__ == "__main__":
    # --- Mode 1: DEB → IPA conversion only ---
    # Usage: python ota_automator.py convert <deb_path>
    if len(sys.argv) == 3 and sys.argv[1] == 'convert':
        deb_path = sys.argv[2]
        out_dir  = os.path.dirname(deb_path) or '.'
        out_ipa  = os.path.join(out_dir, 'converted.ipa')
        deb_to_ipa(deb_path, out_ipa)
        # Print IPA path so workflow can capture it
        print(f"IPA_OUTPUT={out_ipa}")
        sys.exit(0)

    # --- Mode 2: Process IPA → plist + JSON update ---
    # Usage: python ota_automator.py <ipa_path> <category> <download_url>
    if len(sys.argv) != 4:
        print("Usage:")
        print("  python ota_automator.py convert <deb_path>")
        print("  python ota_automator.py <ipa_path> <category> <download_url>")
        sys.exit(1)

    ipa_path         = sys.argv[1]
    category         = sys.argv[2]
    ipa_download_url = sys.argv[3]

    name, version, bundle_id, icon_path = extract_ipa_info(ipa_path)
    print(f"Found App: {name} (v{version}) - {bundle_id}")

    icon_url   = f"https://tomkidsrepo.cloud/{icon_path}"
    plist_path = create_ota_plist(name, version, bundle_id, ipa_download_url, icon_url)

    app_data = {
        "name":    name,
        "version": version,
        "icon":    icon_path,
        "plist":   plist_path
    }

    update_ota_json(category, app_data)
    print("Automation complete!")
