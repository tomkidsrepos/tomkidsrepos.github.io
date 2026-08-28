import json
import os

with open('ota_data.json', 'r', encoding='utf-8') as f:
    data = json.load(f)

print('Checking icon paths:')
for cat, apps in data.items():
    for app in apps:
        icon_path = app['icon']
        if not os.path.exists(icon_path):
            print(f"App: {app['name']}, Icon Path: {icon_path} - MISSING")
