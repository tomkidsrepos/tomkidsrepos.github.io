import hashlib
import os

def hash_file(fpath, algo):
    h = hashlib.new(algo)
    with open(fpath, 'rb') as f:
        h.update(f.read())
    return h.hexdigest()

with open('Release', 'w', encoding='utf-8') as f:
    f.write('Origin: Tomkids Repo\nLabel: Tomkids Repo\nSuite: stable\nVersion: 1.0\nCodename: ios\nArchitectures: iphoneos-arm\nComponents: main\nDescription: Classic Jailbreak Repository\n')
    
    files = ['Packages', 'Packages.bz2']
    
    f.write('MD5Sum:\n')
    for file in files: f.write(f' {hash_file(file, "md5")} {os.path.getsize(file)} {file}\n')
        
    f.write('SHA1:\n')
    for file in files: f.write(f' {hash_file(file, "sha1")} {os.path.getsize(file)} {file}\n')
        
    f.write('SHA256:\n')
    for file in files: f.write(f' {hash_file(file, "sha256")} {os.path.getsize(file)} {file}\n')
