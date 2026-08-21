import sys
import zipfile
import plistlib
import json
import os
import shutil

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
            
        name = plist.get('CFBundleDisplayName') or plist.get('CFBundleName', 'Unknown App')
        version = plist.get('CFBundleShortVersionString') or plist.get('CFBundleVersion', '1.0')
        bundle_id = plist.get('CFBundleIdentifier', 'com.unknown.app')
        
        # Try to extract icon
        icon_path = None
        icon_names = []
        if 'CFBundleIconFiles' in plist:
            icon_names = plist['CFBundleIconFiles']
        elif 'CFBundleIcons' in plist and 'CFBundlePrimaryIcon' in plist['CFBundleIcons']:
            icon_names = plist['CFBundleIcons']['CFBundlePrimaryIcon'].get('CFBundleIconFiles', [])
            
        if not icon_names:
            icon_names = ['Icon', 'AppIcon']
            
        # Search for icon in zip
        best_icon = None
        app_folder = info_plist_path.replace('Info.plist', '')
        for name in ipa.namelist():
            if name.startswith(app_folder):
                basename = os.path.basename(name)
                for iname in icon_names:
                    if iname in basename and basename.endswith('.png'):
                        best_icon = name
                        # Prefer @2x or @3x if available
                        if '@2x' in basename or '@3x' in basename:
                            break
                        
        if best_icon:
            os.makedirs('ota_apps/icons', exist_ok=True)
            icon_dest = f"ota_apps/icons/{bundle_id}.png"
            with ipa.open(best_icon) as source, open(icon_dest, 'wb') as target:
                shutil.copyfileobj(source, target)
            print(f"Extracted icon to {icon_dest}")
        else:
            icon_dest = "CydiaIcon.png" # Fallback
            
        return name, version, bundle_id, icon_dest

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
    with open(json_path, 'r', encoding='utf-8') as f:
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

if __name__ == "__main__":
    if len(sys.argv) != 4:
        print("Usage: python ota_automator.py <ipa_path> <category> <ipa_download_url>")
        sys.exit(1)
        
    ipa_path = sys.argv[1]
    category = sys.argv[2]
    ipa_download_url = sys.argv[3]
    
    name, version, bundle_id, icon_path = extract_ipa_info(ipa_path)
    print(f"Found App: {name} (v{version}) - {bundle_id}")
    
    icon_url = f"https://tomkidsrepo.cloud/{icon_path}"
    plist_path = create_ota_plist(name, version, bundle_id, ipa_download_url, icon_url)
    
    app_data = {
        "name": name,
        "version": version,
        "icon": icon_path,
        "plist": plist_path
    }
    
    update_ota_json(category, app_data)
    print("Automation complete!")
