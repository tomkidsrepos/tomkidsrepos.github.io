import re

with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

css = """
.accordion-header {
    background:#1f2937;
    padding: 16px 20px;
    font-size: 18px;
    font-weight: bold;
    color: #60a5fa;
    cursor: pointer;
    border-radius: 12px;
    margin-bottom: 10px;
    display: flex;
    justify-content: space-between;
    align-items: center;
    transition: 0.2s;
}
.accordion-header:hover { background: #374151; }
.accordion-header.active { border-radius: 12px 12px 0 0; margin-bottom: 0; }
.accordion-content {
    background: #0f172a;
    border: 1px solid #1f2937;
    border-top: none;
    border-radius: 0 0 12px 12px;
    margin-bottom: 15px;
    display: none;
}
.app-item {
    display: flex;
    align-items: center;
    padding: 15px;
    border-bottom: 1px solid #1f2937;
    text-decoration: none;
    color: white;
}
.app-item:last-child { border-bottom: none; }
.app-icon {
    width: 60px; height: 60px;
    border-radius: 14px;
    margin-right: 15px;
}
.app-info { flex: 1; }
.app-title { font-size: 18px; font-weight: bold; margin-bottom: 5px; }
.app-version { font-size: 14px; color: #94a3b8; }
.btn-install {
    background: #2563eb; color: white;
    padding: 8px 16px; border-radius: 20px;
    font-size: 14px; font-weight: bold; text-decoration: none;
}
"""
html = html.replace('</style>', css + '</style>')

sections = """
<section class="info" style="text-align:center;">
    <h2>CÔNG CỤ HỖ TRỢ (CÀI ĐẶT CHỨNG CHỈ)</h2>
    <p style="margin-bottom:20px; color:#cbd5e1;">Sửa lỗi không vào được mạng, không truy cập được web trên iOS cũ.</p>
    <a class="btn primary" href="certs/Certificates%20for%20Legacy%20iOS.mobileconfig">Cài Chứng Chỉ SSL cho iOS Cổ</a>
</section>

<section class="info ota-section">
    <h2 style="text-align:center; margin-bottom:25px;">KHO ỨNG DỤNG IPA (CÀI TRỰC TIẾP OTA)</h2>
    <div id="ota-container"></div>
</section>

<script>
    function toggleAccordion(element) {
        element.classList.toggle("active");
        var content = element.nextElementSibling;
        if (content.style.display === "block") {
            content.style.display = "none";
        } else {
            content.style.display = "block";
        }
    }

    // Danh sách App mẫu (Nhóm theo Thể loại)
    var otaData = {
        "Mạng Xã Hội": [
            { name: "Facebook", version: "11.0", icon: "CydiaIcon.png", plist: "ota_apps/template.plist" },
            { name: "Messenger", version: "84.0", icon: "CydiaIcon.png", plist: "ota_apps/template.plist" }
        ],
        "Trò Chơi": [
            { name: "Flappy Bird", version: "1.2", icon: "CydiaIcon.png", plist: "ota_apps/template.plist" }
        ],
        "Công Cụ": [
            { name: "YouTube", version: "1.3.0", icon: "CydiaIcon.png", plist: "ota_apps/template.plist" }
        ]
    };

    var container = document.getElementById('ota-container');
    var htmlContent = "";

    for (var category in otaData) {
        var apps = otaData[category];
        if (apps.length > 0) {
            htmlContent += '<div class="accordion-group">' +
                           '<div class="accordion-header" onclick="toggleAccordion(this)">' +
                           '<span>' + category + '</span>' +
                           '<span>▾</span>' +
                           '</div>' +
                           '<div class="accordion-content">';
            for (var i = 0; i < apps.length; i++) {
                var app = apps[i];
                var installLink = 'itms-services://?action=download-manifest&url=https://tomkidsrepo.cloud/' + encodeURI(app.plist);
                htmlContent += '<div class="app-item">' +
                               '<img src="' + app.icon + '" class="app-icon">' +
                               '<div class="app-info">' +
                               '<div class="app-title">' + app.name + '</div>' +
                               '<div class="app-version">Phiên bản ' + app.version + '</div>' +
                               '</div>' +
                               '<a href="' + installLink + '" class="btn-install">Cài đặt</a>' +
                               '</div>';
            }
            htmlContent += '</div></div>';
        }
    }
    container.innerHTML = htmlContent;
</script>
"""

html = html.replace('</section>', '</section>' + sections, 1)

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(html)
