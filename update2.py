with open('index.html', 'r', encoding='utf-8') as f:
    html = f.read()

start_marker = '// Danh sách App mẫu'
if start_marker not in html:
    start_marker = 'var otaData = {'

end_marker = 'container.innerHTML = htmlContent;'

start_idx = html.find(start_marker)
end_idx = html.find(end_marker) + len(end_marker)

replacement = '''
    var container = document.getElementById('ota-container');
    
    fetch('ota_data.json')
        .then(response => response.json())
        .then(otaData => {
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
        })
        .catch(error => {
            console.error("Error loading OTA data:", error);
            container.innerHTML = "<p style='color:white;text-align:center;'>Không thể tải danh sách ứng dụng.</p>";
        });
'''

if start_idx != -1 and end_idx != -1:
    new_html = html[:start_idx] + replacement + html[end_idx:]
    with open('index.html', 'w', encoding='utf-8') as f:
        f.write(new_html)
