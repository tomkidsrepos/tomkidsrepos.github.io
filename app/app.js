/**
 * APPVN RETRO CLIENT ENGINE - ES5 PURE VANILLA JAVASCRIPT
 * Tương thích 100% với Mobile Safari trên iOS 4, 5, 6, 7, 8, 9, 10
 */

// Global State
var rawAppData = {};        // Dữ liệu từ ota_data.json
var allAppsFlat = [];       // Danh sách phẳng tất cả các app
var filteredApps = [];      // Danh sách app sau khi lọc/tìm kiếm
var currentCategory = 'ALL';
var currentTab = 'featured'; // 'newest' | 'featured' | 'popular'
var currentMainSection = 'apps'; // 'apps' | 'books' | 'comics' | 'movies' | 'wallpapers' | 'ringtones' | 'favorites'

var selectedApp = null;     // App đang chọn cho Action Sheet
var audioPlayer = null;     // Thẻ Audio để phát nhạc chuông thử nghiệm

// LocalStorage Keys
var STORAGE_USER_NAME = 'appvn_username';
var STORAGE_WALLET = 'appvn_wallet';
var STORAGE_DOWNLOADS = 'appvn_downloads';
var STORAGE_FAVORITES = 'appvn_favorites';

// Khởi chạy khi tài liệu sẵn sàng
window.onload = function() {
    initUserData();
    loadOtaData();
    updateDownloadBadge();
};

/* ==========================================================================
   1. QUẢN LÝ TÀI KHOẢN & VÍ XU / RUBY / VÀNG (PHONG CÁCH APPVN)
   ========================================================================== */
function initUserData() {
    var storedName = localStorage.getItem(STORAGE_USER_NAME);
    if (!storedName || storedName === 'tuanem') {
        storedName = 'Tomkids';
        localStorage.setItem(STORAGE_USER_NAME, storedName);
    }
    document.getElementById('user-name-display').innerText = storedName;
    document.getElementById('user-avatar').innerText = (storedName === 'Tomkids') ? 'TK' : storedName.substring(0, 2).toUpperCase();

    var wallet = getStoredWallet();
    document.getElementById('val-xu').innerText = wallet.xu;
    document.getElementById('val-ruby').innerText = wallet.ruby;
    document.getElementById('val-vang').innerText = wallet.vang;
}

function getStoredWallet() {
    var raw = localStorage.getItem(STORAGE_WALLET);
    if (!raw) {
        var initial = { xu: 9999, ruby: 9999, vang: 9999 };
        localStorage.setItem(STORAGE_WALLET, JSON.stringify(initial));
        return initial;
    }
    try {
        return JSON.parse(raw);
    } catch(e) {
        return { xu: 9999, ruby: 9999, vang: 9999 };
    }
}

function updateWallet(addXu, addRuby, addVang) {
    var w = getStoredWallet();
    w.xu = (w.xu || 0) + (addXu || 0);
    w.ruby = (w.ruby || 0) + (addRuby || 0);
    w.vang = (w.vang || 0) + (addVang || 0);
    localStorage.setItem(STORAGE_WALLET, JSON.stringify(w));

    document.getElementById('val-xu').innerText = w.xu;
    document.getElementById('val-ruby').innerText = w.ruby;
    document.getElementById('val-vang').innerText = w.vang;
}

function changeUserName() {
    var current = localStorage.getItem(STORAGE_USER_NAME) || 'Tomkids';
    var newName = prompt("Nhập tên hiển thị tài khoản Tomkids AppStore của bạn:", current);
    if (newName && newName.trim().length > 0) {
        newName = newName.trim();
        localStorage.setItem(STORAGE_USER_NAME, newName);
        document.getElementById('user-name-display').innerText = newName;
        document.getElementById('user-avatar').innerText = (newName === 'Tomkids') ? 'TK' : newName.substring(0, 2).toUpperCase();
        showToast("Đã đổi tên thành công: " + newName);
    }
}

/* ==========================================================================
   2. TẢI DỮ LIỆU TỪ ota_data.json (DÙNG XMLHttpRequest THAY CHO FETCH)
   ========================================================================== */
function loadOtaData() {
    var container = document.getElementById('app-list-container');
    var xhr = new XMLHttpRequest();
    // Thêm timestamp để tránh cache trình duyệt
    xhr.open('GET', '../ota_data.json?t=' + new Date().getTime(), true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200 || xhr.status === 0) {
                try {
                    rawAppData = JSON.parse(xhr.responseText);
                    processAppData();
                } catch(e) {
                    container.innerHTML = '<div class="loading-state"><p style="color:#ef4444;">Lỗi đọc dữ liệu: ' + e.message + '</p></div>';
                }
            } else {
                container.innerHTML = '<div class="loading-state"><p style="color:#ef4444;">Không thể tải danh sách ứng dụng.</p></div>';
            }
        }
    };
    xhr.send();
}

function processAppData() {
    allAppsFlat = [];
    var categories = Object.keys ? Object.keys(rawAppData) : [];
    if (categories.length === 0) {
        for (var k in rawAppData) {
            if (rawAppData.hasOwnProperty(k)) categories.push(k);
        }
    }

    var appCounter = 1;
    for (var c = 0; c < categories.length; c++) {
        var catName = categories[c];
        var list = rawAppData[catName] || [];
        for (var i = 0; i < list.length; i++) {
            var item = list[i];
            if (item.hidden === true) continue;
            // Chuẩn hóa đường dẫn icon và plist
            var iconUrl = item.icon;
            if (iconUrl.indexOf('http') !== 0) {
                iconUrl = '../' + iconUrl;
            }
            var plistUrl = item.plist;
            if (plistUrl.indexOf('http') !== 0) {
                plistUrl = 'https://tomkidsrepo.cloud/' + plistUrl;
            }

            allAppsFlat.push({
                index: appCounter++,
                name: item.name || 'Không rõ',
                version: item.version || '1.0',
                category: catName,
                icon: iconUrl,
                plist: plistUrl,
                rating: 5,
                ratingCount: Math.floor(Math.random() * 20) + 1,
                author: getAuthorFromName(item.name),
                size: (item.name.length * 3.5 + 4).toFixed(1) + ' MB'
            });
        }
    }

    applyFilterAndRender();
}

function getAuthorFromName(name) {
    if (name.indexOf('Flappy') >= 0) return 'Adam Carter';
    if (name.indexOf('PvZ') >= 0 || name.indexOf('Bejeweled') >= 0) return 'PopCap';
    if (name.indexOf('Facebook') >= 0 || name.indexOf('Messenger') >= 0) return 'Meta Inc.';
    if (name.indexOf('TikTok') >= 0) return 'ByteDance';
    if (name.indexOf('YouTube') >= 0 || name.indexOf('Google') >= 0 || name.indexOf('Chrome') >= 0) return 'Google LLC';
    if (name.indexOf('Zing') >= 0) return 'VNG Corp';
    if (name.indexOf('Contra') >= 0) return 'PunchBox';
    if (name.indexOf('Opera') >= 0) return 'Opera Software';
    return 'Tomkids Team';
}

/* ==========================================================================
   3. RENDER DANH SÁCH ỨNG DỤNG (THEO CHUẨN GIAO DIỆN HÌNH 1 & 3)
   ========================================================================== */
function applyFilterAndRender() {
    filteredApps = [];
    for (var i = 0; i < allAppsFlat.length; i++) {
        var app = allAppsFlat[i];
        if (currentCategory === 'ALL' || app.category === currentCategory) {
            filteredApps.push(app);
        }
    }

    // Sắp xếp theo Tab:
    if (currentTab === 'newest') {
        filteredApps.reverse();
    } else if (currentTab === 'popular') {
        // Ưu tiên các game/app nổi tiếng
        filteredApps.sort(function(a, b) {
            return b.name.length - a.name.length;
        });
    }

    renderAppList(filteredApps);
}

function renderAppList(list) {
    var container = document.getElementById('app-list-container');
    if (!list || list.length === 0) {
        container.innerHTML = '<div class="loading-state"><p>Không tìm thấy ứng dụng nào.</p></div>';
        return;
    }

    var html = '';
    for (var i = 0; i < list.length; i++) {
        var app = list[i];
        var itemNum = (i + 1);

        html += '<div class="app-card-item" onclick="openActionSheet(' + i + ')">' +
                    '<div class="app-index-num">' + itemNum + '.</div>' +
                    '<img class="app-icon-img" src="' + app.icon + '" onerror="this.src=\'../CydiaIcon.png\'">' +
                    '<div class="app-details">' +
                        '<div class="app-name">' + escapeHtml(app.name) + '</div>' +
                        '<div class="app-stars-row">' +
                            '★★★★★ <span class="app-rating-count">(' + app.ratingCount + ')</span>' +
                        '</div>' +
                        '<div class="app-meta-sub">' +
                            escapeHtml(app.author) + ' • ' + escapeHtml(app.version) + ' • ' + app.size +
                        '</div>' +
                    '</div>' +
                    '<div class="app-download-btn-wrap">' +
                        '<a href="javascript:void(0)" class="circle-download-btn" onclick="event.stopPropagation(); triggerDirectInstall(' + i + ')" title="Cài đặt">' +
                            '↓' +
                        '</a>' +
                    '</div>' +
                '</div>';
    }

    container.innerHTML = html;
}

/* ==========================================================================
   4. ACTION SHEET POPUP CỔ ĐIỂN (THEO ẢNH 2: XEM CHI TIẾT / CÀI ĐẶT / TẢI LẠI...)
   ========================================================================== */
function openActionSheet(index) {
    selectedApp = filteredApps[index];
    if (!selectedApp) return;

    document.getElementById('as-app-icon').src = selectedApp.icon;
    document.getElementById('as-app-title').innerText = selectedApp.name;
    document.getElementById('as-app-sub').innerText = selectedApp.version + ' • ' + selectedApp.size;

    // Kiểm tra xem app đã nằm trong mục "Đã tải" chưa để hiện nút Xoá
    var downloads = getStoredDownloads();
    var isDownloaded = false;
    for (var d = 0; d < downloads.length; d++) {
        if (downloads[d].name === selectedApp.name) {
            isDownloaded = true;
            break;
        }
    }
    document.getElementById('as-btn-delete').style.display = isDownloaded ? 'block' : 'none';

    document.getElementById('action-sheet-overlay').style.display = 'block';
    var sheet = document.getElementById('action-sheet');
    sheet.className = 'action-sheet open';
}

function closeActionSheet() {
    document.getElementById('action-sheet-overlay').style.display = 'none';
    var sheet = document.getElementById('action-sheet');
    sheet.className = 'action-sheet';
}

function onActionSheetInstall() {
    closeActionSheet();
    if (selectedApp) {
        executeInstallApp(selectedApp);
    }
}

function onActionSheetReinstall() {
    closeActionSheet();
    if (selectedApp) {
        executeInstallApp(selectedApp);
    }
}

function onActionSheetDetail() {
    closeActionSheet();
    if (selectedApp) {
        openDetailModal(selectedApp);
    }
}

function onActionSheetDelete() {
    closeActionSheet();
    if (selectedApp) {
        removeDownloadRecord(selectedApp.name);
        showToast("Đã xoá " + selectedApp.name + " khỏi lịch sử tải.");
        updateDownloadBadge();
        // Nếu đang ở màn hình Quản lý tải thì tải lại
        if (document.getElementById('download-manager-modal').style.display === 'block') {
            renderDownloadManagerContent('downloaded');
        }
    }
}

/* ==========================================================================
   5. CƠ CHẾ CÀI ĐẶT TRỰC TIẾP OTA (itms-services://)
   ========================================================================== */
function triggerDirectInstall(index) {
    var app = filteredApps[index];
    if (app) {
        executeInstallApp(app);
    }
}

function executeInstallApp(app) {
    // 1. Lưu vào danh sách đã tải
    recordDownload(app);

    // 2. Thưởng 10 Xu khi cài app
    updateWallet(10, 1, 0);

    // 3. Chuẩn bị link itms-services
    var otaUrl = "itms-services://?action=download-manifest&url=" + encodeURIComponent(app.plist);

    // 4. Hiển thị thông báo Toast
    showToast("Đang kích hoạt cài đặt: " + app.name + "... Hãy bấm 'Cài đặt' trên màn hình.");

    // 5. Chuyển hướng sang giao thức iOS
    setTimeout(function() {
        window.location.href = otaUrl;
    }, 400);
}

function recordDownload(app) {
    var downloads = getStoredDownloads();
    var exists = false;
    var now = new Date();
    var dateStr = now.getDate() + "-" + (now.getMonth() + 1) + "-" + now.getFullYear();

    for (var i = 0; i < downloads.length; i++) {
        if (downloads[i].name === app.name) {
            downloads[i].date = dateStr;
            downloads[i].status = "Đã cài";
            exists = true;
            break;
        }
    }

    if (!exists) {
        downloads.unshift({
            name: app.name,
            version: app.version,
            icon: app.icon,
            plist: app.plist,
            date: dateStr,
            status: "Đã cài"
        });
    }

    localStorage.setItem(STORAGE_DOWNLOADS, JSON.stringify(downloads));
    updateDownloadBadge();
}

function getStoredDownloads() {
    var raw = localStorage.getItem(STORAGE_DOWNLOADS);
    if (!raw) return [];
    try {
        return JSON.parse(raw);
    } catch(e) {
        return [];
    }
}

function removeDownloadRecord(appName) {
    var downloads = getStoredDownloads();
    var filtered = [];
    for (var i = 0; i < downloads.length; i++) {
        if (downloads[i].name !== appName) {
            filtered.push(downloads[i]);
        }
    }
    localStorage.setItem(STORAGE_DOWNLOADS, JSON.stringify(filtered));
}

function updateDownloadBadge() {
    var downloads = getStoredDownloads();
    var badge = document.getElementById('download-badge');
    if (downloads.length > 0) {
        badge.innerText = downloads.length;
        badge.style.display = 'block';
    } else {
        badge.style.display = 'none';
    }
}

/* ==========================================================================
   6. QUẢN LÝ TẢI & LỊCH SỬ TẢI (THEO ẢNH 2 & 5)
   ========================================================================== */
function openDownloadManager(tab) {
    toggleSidebar(false);
    document.getElementById('download-manager-modal').style.display = 'block';
    switchDmTab(tab || 'downloaded');
}

function closeDownloadManager() {
    document.getElementById('download-manager-modal').style.display = 'none';
}

function switchDmTab(tabName) {
    var tabs = document.querySelectorAll ? document.querySelectorAll('.dm-tab') : [];
    for (var i = 0; i < tabs.length; i++) {
        tabs[i].className = 'dm-tab';
    }
    var activeTab = document.getElementById('dm-tab-' + tabName);
    if (activeTab) activeTab.className = 'dm-tab active';

    renderDownloadManagerContent(tabName);
}

function renderDownloadManagerContent(tabName) {
    var container = document.getElementById('dm-content-list');
    var downloads = getStoredDownloads();

    if (tabName === 'downloaded') {
        if (downloads.length === 0) {
            container.innerHTML = '<div class="loading-state"><p>Chưa có ứng dụng nào được tải.</p></div>';
            return;
        }

        var html = '';
        for (var i = 0; i < downloads.length; i++) {
            var item = downloads[i];
            html += '<div class="dm-item" onclick="openActionSheetFromHistory(' + i + ')">' +
                        '<img class="dm-item-icon" src="' + item.icon + '" onerror="this.src=\'../CydiaIcon.png\'">' +
                        '<div class="dm-item-info">' +
                            '<div class="dm-item-name">' + escapeHtml(item.name) + '</div>' +
                            '<div class="dm-item-date">' + item.date + '</div>' +
                        '</div>' +
                        '<div class="dm-item-status">' + (item.status || 'Đã cài') + '</div>' +
                    '</div>';
        }
        container.innerHTML = html;
    } else if (tabName === 'downloading') {
        container.innerHTML = '<div class="loading-state"><p>Không có ứng dụng nào đang chờ xử lý.</p></div>';
    } else if (tabName === 'update') {
        container.innerHTML = '<div class="loading-state"><p>Tất cả ứng dụng của bạn đều ở phiên bản tương thích tốt nhất!</p></div>';
    }
}

function openActionSheetFromHistory(index) {
    var downloads = getStoredDownloads();
    var item = downloads[index];
    if (!item) return;

    // Tìm trong allAppsFlat hoặc tạo mock
    selectedApp = {
        name: item.name,
        version: item.version,
        icon: item.icon,
        plist: item.plist,
        size: '15 MB'
    };

    document.getElementById('as-app-icon').src = selectedApp.icon;
    document.getElementById('as-app-title').innerText = selectedApp.name;
    document.getElementById('as-app-sub').innerText = selectedApp.version + ' • ' + selectedApp.size;
    document.getElementById('as-btn-delete').style.display = 'block';

    document.getElementById('action-sheet-overlay').style.display = 'block';
    document.getElementById('action-sheet').className = 'action-sheet open';
}

/* ==========================================================================
   7. CHUYỂN ĐỔI CHUYÊN MỤC CHÍNH (SÁCH, NHẠC CHUÔNG, HÌNH NỀN...)
   ========================================================================== */
function switchMainCategory(section) {
    currentMainSection = section;
    toggleSidebar(false);

    // Cập nhật tiêu đề
    var titleEl = document.getElementById('current-title');
    var appView = document.getElementById('app-list-container');
    var mediaView = document.getElementById('media-list-container');
    var chipsBar = document.getElementById('chips-scroll');
    var tabsBar = document.getElementById('sub-nav-tabs');

    // Reset active menu
    var menuItems = document.querySelectorAll ? document.querySelectorAll('.menu-item') : [];
    for (var i = 0; i < menuItems.length; i++) {
        menuItems[i].className = 'menu-item';
    }

    if (section === 'apps') {
        titleEl.innerText = "Danh mục";
        appView.style.display = 'block';
        mediaView.style.display = 'none';
        chipsBar.style.display = 'block';
        tabsBar.style.display = '-webkit-flex';
        applyFilterAndRender();
    } else {
        appView.style.display = 'none';
        mediaView.style.display = 'block';
        chipsBar.style.display = 'none';
        tabsBar.style.display = 'none';

        if (section === 'ringtones') {
            titleEl.innerText = "Nhạc chuông";
            renderRingtones();
        } else if (section === 'books' || section === 'comics') {
            titleEl.innerText = (section === 'books') ? "Kho Sách" : "Kho Truyện";
            renderBooks();
        } else if (section === 'wallpapers') {
            titleEl.innerText = "Hình nền";
            renderWallpapers();
        } else if (section === 'movies') {
            titleEl.innerText = "Phim cổ điển";
            renderMovies();
        } else if (section === 'favorites') {
            titleEl.innerText = "Yêu thích";
            renderFavorites();
        }
    }
}

var rawMediaData = null;

function loadMediaData(callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '../media_data.json?t=' + new Date().getTime(), true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200 || xhr.status === 0) {
                try {
                    rawMediaData = JSON.parse(xhr.responseText);
                } catch(e) {}
            }
            callback(rawMediaData || {});
        }
    };
    xhr.send();
}

// 7.1. Chuyên mục Nhạc Chuông (.m4r)
function renderRingtones() {
    loadMediaData(function(data) {
        var ringtones = data.ringtones || [
            { title: "Marimba (Nhạc Chuông Gốc iPhone)", desc: "Âm thanh huyền thoại của Steve Jobs", file: "https://www.soundhelix.com/examples/mp3/SoundHelix-Song-1.mp3", duration: "0:30" }
        ];

        var html = '<div style="margin-bottom:12px; font-size:13px; color:#475569; padding:0 4px;">' +
                       'Nhạc chuông định dạng chuẩn <b>.m4r</b> cho iPhone. Bạn có thể nghe thử trực tiếp hoặc tải về:' +
                   '</div>';

        for (var i = 0; i < ringtones.length; i++) {
            var r = ringtones[i];
            html += '<div class="media-item">' +
                        '<div class="media-item-thumb" onclick="playAudio(\'' + r.file + '\')">▶</div>' +
                        '<div class="media-item-info">' +
                            '<div class="media-title">' + escapeHtml(r.title) + '</div>' +
                            '<div class="media-sub">' + escapeHtml(r.desc) + ' • ' + (r.duration || "0:30") + '</div>' +
                        '</div>' +
                        '<a href="' + r.file + '" download class="media-action-btn">Tải .m4r</a>' +
                    '</div>';
        }

        document.getElementById('media-list-container').innerHTML = html;
    });
}

function playAudio(url) {
    if (!audioPlayer) {
        audioPlayer = new Audio();
    }
    if (audioPlayer.src === url && !audioPlayer.paused) {
        audioPlayer.pause();
        showToast("Đã tạm dừng phát.");
    } else {
        audioPlayer.src = url;
        audioPlayer.play();
        showToast("Đang phát thử nghiệm...");
    }
}

// 7.2. Chuyên mục Sách & Truyện (.pdf / .epub / iBooks)
function renderBooks() {
    loadMediaData(function(data) {
        var key = (currentMainSection === 'comics') ? 'comics' : 'books';
        var books = data[key] || [];

        if (books.length === 0) {
            document.getElementById('media-list-container').innerHTML = 
                '<div class="loading-state"><p>Chưa có sách hoặc truyện nào trong mục này.</p></div>';
            return;
        }

        var html = '<div style="margin-bottom:12px; font-size:13px; color:#475569; padding:0 4px;">' +
                       'Bấm "Mở trong iBooks" để Safari tự động thêm trực tiếp vào app iBooks của iPhone:' +
                   '</div>';

        for (var i = 0; i < books.length; i++) {
            var b = books[i];
            html += '<div class="media-item">' +
                        '<div class="media-item-thumb">' + (b.icon || "📖") + '</div>' +
                        '<div class="media-item-info">' +
                            '<div class="media-title">' + escapeHtml(b.title) + '</div>' +
                            '<div class="media-sub">' + escapeHtml(b.author || "Tomkids") + ' • ' + escapeHtml(b.pages || "PDF") + '</div>' +
                        '</div>' +
                        '<a href="' + b.url + '" target="_blank" class="media-action-btn">Mở iBooks</a>' +
                    '</div>';
        }

        document.getElementById('media-list-container').innerHTML = html;
    });
}

// 7.3. Chuyên mục Hình Nền (Retina iOS cổ)
function renderWallpapers() {
    loadMediaData(function(data) {
        var wallpapers = data.wallpapers || [];

        var html = '<div style="margin-bottom:12px; font-size:13px; color:#475569; padding:0 4px;">' +
                       'Nhấn vào hình để xem kích thước lớn, sau đó <b>chạm và giữ 1 giây</b> để chọn <i>Lưu hình ảnh</i> vào Cuộn Camera:' +
                   '</div><div class="wallpaper-grid">';

        for (var i = 0; i < wallpapers.length; i++) {
            var w = wallpapers[i];
            html += '<div class="wallpaper-card">' +
                        '<a href="' + w.url + '" target="_blank">' +
                            '<img class="wallpaper-img" src="' + w.url + '" alt="' + escapeHtml(w.title) + '">' +
                        '</a>' +
                    '</div>';
        }
        html += '</div>';

        document.getElementById('media-list-container').innerHTML = html;
    });
}

// 7.4. Phim & Clips
function renderMovies() {
    document.getElementById('media-list-container').innerHTML = 
        '<div class="loading-state">' +
            '<p>🎬 Kho Phim Cổ Điển đang được đồng bộ máy chủ.</p>' +
            '<p style="font-size:12px; color:#94a3b8; margin-top:8px;">Hỗ trợ định dạng MP4 chuẩn H.264/AAC tương thích hoàn hảo mọi chip Apple A4/A5.</p>' +
        '</div>';
}

// 7.5. Mục Yêu Thích
function renderFavorites() {
    document.getElementById('media-list-container').innerHTML = 
        '<div class="loading-state">' +
            '<p>⭐ Danh sách yêu thích của bạn.</p>' +
            '<p style="font-size:12px; color:#94a3b8; margin-top:8px;">Nhấn vào bất kỳ app nào trong danh mục và chọn Yêu Thích để lưu lại tại đây.</p>' +
        '</div>';
}

/* ==========================================================================
   8. TƯƠNG TÁC GIAO DIỆN & TÌM KIẾM
   ========================================================================== */
function toggleSidebar(show) {
    var drawer = document.getElementById('sidebar-drawer');
    var overlay = document.getElementById('drawer-overlay');
    if (show) {
        overlay.style.display = 'block';
        drawer.className = 'sidebar-drawer open';
    } else {
        overlay.style.display = 'none';
        drawer.className = 'sidebar-drawer';
    }
}

function switchTab(tabName) {
    currentTab = tabName;
    var tabs = ['newest', 'featured', 'popular'];
    for (var i = 0; i < tabs.length; i++) {
        var el = document.getElementById('tab-' + tabs[i]);
        if (el) el.className = (tabs[i] === tabName) ? 'nav-tab active' : 'nav-tab';
    }
    applyFilterAndRender();
}

function filterBySubCategory(cat) {
    currentCategory = cat;
    document.getElementById('category-dropdown').style.display = 'none';

    // Cập nhật chip button
    var chips = document.querySelectorAll ? document.querySelectorAll('.chip-item') : [];
    for (var i = 0; i < chips.length; i++) {
        var text = chips[i].innerText;
        if ((cat === 'ALL' && text === 'Tất cả') || text.indexOf(cat) >= 0) {
            chips[i].className = 'chip-item active';
        } else {
            chips[i].className = 'chip-item';
        }
    }

    applyFilterAndRender();
}

function toggleCategoryDropdown() {
    var dd = document.getElementById('category-dropdown');
    dd.style.display = (dd.style.display === 'none') ? 'block' : 'none';
}

function toggleSearchBox() {
    var box = document.getElementById('search-box-bar');
    if (box.style.display === 'none') {
        box.style.display = '-webkit-flex';
        box.style.display = 'flex';
        document.getElementById('search-input').focus();
    } else {
        box.style.display = 'none';
        clearSearch();
    }
}

function handleSearch(keyword) {
    if (!keyword || keyword.trim() === '') {
        applyFilterAndRender();
        return;
    }
    var q = keyword.toLowerCase().trim();
    var results = [];
    for (var i = 0; i < allAppsFlat.length; i++) {
        var a = allAppsFlat[i];
        if (a.name.toLowerCase().indexOf(q) >= 0 || a.author.toLowerCase().indexOf(q) >= 0 || a.category.toLowerCase().indexOf(q) >= 0) {
            results.push(a);
        }
    }
    renderAppList(results);
}

function clearSearch() {
    document.getElementById('search-input').value = '';
    applyFilterAndRender();
}

/* ==========================================================================
   9. MODAL CHI TIẾT ỨNG DỤNG
   ========================================================================== */
function openDetailModal(app) {
    document.getElementById('modal-app-title').innerText = app.name;
    var body = document.getElementById('modal-detail-body');
    body.innerHTML = 
        '<div style="text-align:center; margin-bottom:12px;">' +
            '<img src="' + app.icon + '" style="width:72px; height:72px; -webkit-border-radius:16px; border-radius:16px; -webkit-box-shadow:0 3px 6px rgba(0,0,0,0.2);">' +
            '<div style="font-size:16px; font-weight:bold; margin-top:8px;">' + escapeHtml(app.name) + '</div>' +
            '<div style="font-size:12px; color:#64748b;">Phiên bản: ' + app.version + ' • Dung lượng: ' + app.size + '</div>' +
        '</div>' +
        '<div style="border-top:1px solid #e2e8f0; padding-top:10px;">' +
            '<p><b>Nhà phát triển:</b> ' + escapeHtml(app.author) + '</p>' +
            '<p><b>Chuyên mục:</b> ' + escapeHtml(app.category) + '</p>' +
            '<p><b>Yêu cầu hệ điều hành:</b> Tương thích hoàn hảo iOS 5.0, 6.1.6, 7.1.2, 8.4.1, 9.3.5, 10.3.3.</p>' +
            '<p style="margin-top:8px; color:#475569; font-style:italic;">Ứng dụng được bảo tồn và chia sẻ bởi Tomkids Repo. Yêu cầu thiết bị đã jailbreak và cài AppSync Unified.</p>' +
        '</div>';

    document.getElementById('detail-modal').style.display = '-webkit-flex';
    document.getElementById('detail-modal').style.display = 'flex';
}

function closeDetailModal() {
    document.getElementById('detail-modal').style.display = 'none';
}

function onModalInstall() {
    closeDetailModal();
    if (selectedApp) {
        executeInstallApp(selectedApp);
    }
}

/* ==========================================================================
   10. VÒNG QUAY MAY MẮN (MINI GAME KIẾM XU PHONG CÁCH APPVN)
   ========================================================================== */
function openWheelModal() {
    toggleSidebar(false);
    document.getElementById('wheel-result').style.display = 'none';
    document.getElementById('wheel-modal').style.display = '-webkit-flex';
    document.getElementById('wheel-modal').style.display = 'flex';
}

function closeWheelModal() {
    document.getElementById('wheel-modal').style.display = 'none';
}

function spinLuckyWheel() {
    var btn = document.getElementById('btn-spin');
    btn.disabled = true;
    var disc = document.getElementById('wheel-disc');

    var randomDeg = 1440 + Math.floor(Math.random() * 360);
    disc.style.webkitTransform = 'rotate(' + randomDeg + 'deg)';
    disc.style.transform = 'rotate(' + randomDeg + 'deg)';

    var prizes = [
        { xu: 100, ruby: 10, text: "+100 Xu & +10 Ruby!" },
        { xu: 200, ruby: 20, text: "+200 Xu & +20 Ruby!" },
        { xu: 500, ruby: 50, text: "ĐẠI THẮNG: +500 Xu & +50 Ruby!" },
        { xu: 50,  ruby: 5,  text: "+50 Xu khích lệ!" }
    ];
    var win = prizes[Math.floor(Math.random() * prizes.length)];

    setTimeout(function() {
        btn.disabled = false;
        updateWallet(win.xu, win.ruby, 0);
        var res = document.getElementById('wheel-result');
        res.innerText = "🎉 Chúc mừng bạn đã nhận: " + win.text;
        res.style.display = 'block';
    }, 2500);
}

function openGiftModal() {
    toggleSidebar(false);
    alert("🎁 Cửa Hàng Đổi Quà Tomkids AppStore:\n\nHiện tại bạn đang có: " + document.getElementById('val-xu').innerText + " Xu.\nTính năng đổi thẻ cào ảo và danh hiệu VIP đang được hoàn thiện!");
}

/* ==========================================================================
   TIỆN ÍCH BỔ TRỢ
   ========================================================================== */
function showToast(message) {
    var toast = document.getElementById('toast-msg');
    toast.innerText = message;
    toast.style.display = 'block';
    setTimeout(function() {
        toast.style.display = 'none';
    }, 3200);
}

function escapeHtml(str) {
    if (!str) return '';
    return str.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
}
