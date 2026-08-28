import json
import sys
sys.stdout.reconfigure(encoding='utf-8')
with open('ota_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

for app in data.get('Mạng Xã Hội', []):
    print(f"{app['name']}: {app['icon']}")
