#!/bin/bash

# Dừng script nếu có bất kỳ lỗi nào xảy ra
set -e

echo "=== BẮT ĐẦU QUÁ TRÌNH GOM GÓI VÀ ĐỒNG BỘ ==="

# 1. Tìm kiếm các kho có gắn thẻ
echo "1. Đang gọi GitHub API để lấy danh sách kho..."
# Lấy danh sách tối đa 100 kho của tomkidsrepos có gắn thẻ cydia-package
REPOS=$(gh repo list tomkidsrepos --topic cydia-package --json name -q '.[].name' -L 100)

if [ -z "$REPOS" ]; then
    echo "Không tìm thấy kho nào có gắn thẻ 'cydia-package'. Hệ thống sẽ không quét."
    exit 0
fi

echo "Danh sách các kho tìm thấy:"
echo "$REPOS"

# 2. Xóa và tạo lại thư mục chứa tạm
echo "2. Chuẩn bị thư mục hệ thống..."
rm -rf debs
mkdir -p debs

# 3. Tải tất cả các repo về thư mục debs
for REPO in $REPOS; do
    echo "-> Đang tải kho $REPO..."
    # Chỉ tải phiên bản mới nhất (depth 1) cho nhanh, bỏ qua lịch sử commit
    git clone --depth 1 "https://github.com/tomkidsrepos/$REPO.git" "./debs_temp/$REPO"
    
    # Chuyển vào thư mục chính thức và dọn dẹp file thừa (thư mục .git ẩn)
    mv "./debs_temp/$REPO" "./debs/$REPO"
    rm -rf "./debs/$REPO/.git"
done
rm -rf debs_temp

# 4. Quét mã tạo file Packages
echo "3. Đang quét file .deb và tạo file Packages..."
dpkg-scanpackages debs /dev/null > Packages
bzip2 -c9 Packages > Packages.bz2

# 5. Tạo file Release với mã băm bảo mật
echo "4. Đang tạo file Release..."
cat <<EOF > Release
Origin: Tomkids Repo
Label: Tomkids Repo
Suite: stable
Version: 1.0
Codename: ios
Architectures: iphoneos-arm
Components: main
Description: Classic Jailbreak Repository
MD5Sum:
 $(md5sum Packages | cut -d" " -f1) $(stat -c%s Packages) Packages
 $(md5sum Packages.bz2 | cut -d" " -f1) $(stat -c%s Packages.bz2) Packages.bz2
SHA1:
 $(sha1sum Packages | cut -d" " -f1) $(stat -c%s Packages) Packages
 $(sha1sum Packages.bz2 | cut -d" " -f1) $(stat -c%s Packages.bz2) Packages.bz2
SHA256:
 $(sha256sum Packages | cut -d" " -f1) $(stat -c%s Packages) Packages
 $(sha256sum Packages.bz2 | cut -d" " -f1) $(stat -c%s Packages.bz2) Packages.bz2
EOF

echo "=== ĐỒNG BỘ THÀNH CÔNG ==="
