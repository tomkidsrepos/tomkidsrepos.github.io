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
var STORAGE_AUTH_USER = 'appvn_auth_user';

// Cấu hình Tab & Chuyên mục mặc định (sẽ được ghi đè tự động từ app_tabs.json)
var appTabs = [
    { id: "ALL", name: "Tất cả", icon: "🌐", color: "#38bdf8", type: "all" },
    { id: "GUEST", name: "Guest", icon: "🌟", color: "#a855f7", type: "curated", field: "show_on_guest" },
    { id: "PRIVATE", name: "Private", icon: "🔒", color: "#ec4899", type: "curated", field: "show_on_private" },
    { id: "Trò Chơi", name: "Trò Chơi", icon: "🎮", color: "#3b82f6", type: "category" },
    { id: "Mạng Xã Hội", name: "Mạng Xã Hội", icon: "🌐", color: "#3b82f6", type: "category" },
    { id: "Giải Trí", name: "Giải Trí", icon: "🎵", color: "#3b82f6", type: "category" },
    { id: "Công Cụ", name: "Công Cụ", icon: "🛠️", color: "#3b82f6", type: "category" },
    { id: "Hệ thống", name: "Hệ thống", icon: "⚙️", color: "#3b82f6", type: "category" },
    { id: "Jailbreak", name: "Jailbreak", icon: "🔓", color: "#3b82f6", type: "category" }
];

function isAppInCuratedTab(app, tab) {
    if (!app || !tab) return false;
    var field = tab.field || ('show_on_' + tab.id.toLowerCase());
    if (app[field] === true) return true;
    if (app.custom_tabs && app.custom_tabs.indexOf(tab.id) !== -1) return true;
    return false;
}

function loadAppTabs(callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '../app_tabs.json?t=' + (new Date()).getTime(), true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200 || xhr.status === 0) {
                try {
                    var data = JSON.parse(xhr.responseText);
                    if (data && data.tabs && data.tabs.length > 0) {
                        appTabs = data.tabs;
                    }
                } catch(e) {}
            }
            renderDynamicTabsUI();
            if (typeof callback === 'function') callback();
        }
    };
    xhr.send(null);
}

function renderDynamicTabsUI() {
    var chipsContainer = document.getElementById('chips-scroll');
    var ddContainer = document.getElementById('category-dropdown');

    if (chipsContainer) {
        var chipsHtml = '';
        for (var i = 0; i < appTabs.length; i++) {
            var tab = appTabs[i];
            var isActive = (currentCategory === tab.id);
            var activeClass = isActive ? 'chip-item active' : 'chip-item';
            var customStyle = '';
            if (tab.type === 'curated') {
                customStyle = 'style="color:' + (tab.color || '#a855f7') + '; font-weight:bold; border-color:' + (tab.color || '#a855f7') + ';"';
            }
            var label = (tab.icon ? tab.icon + ' ' : '') + tab.name;
            chipsHtml += '<button class="' + activeClass + '" id="chip-' + tab.id.toLowerCase() + '" data-cat="' + escapeHtml(tab.id) + '" onclick="filterBySubCategory(\'' + escapeHtml(tab.id) + '\')" ' + customStyle + '>' + escapeHtml(label) + '</button>';
        }
        chipsContainer.innerHTML = chipsHtml;
    }

    if (ddContainer) {
        var ddHtml = '';
        for (var j = 0; j < appTabs.length; j++) {
            var tab2 = appTabs[j];
            var ddStyle = '';
            if (tab2.type === 'curated') {
                ddStyle = 'style="color:' + (tab2.color || '#a855f7') + '; font-weight:bold;"';
            }
            var ddLabel = (tab2.icon ? tab2.icon + ' ' : '') + tab2.name;
            ddHtml += '<div class="dropdown-item" data-cat="' + escapeHtml(tab2.id) + '" onclick="filterBySubCategory(\'' + escapeHtml(tab2.id) + '\')" ' + ddStyle + '>' + escapeHtml(ddLabel) + '</div>';
        }
        ddContainer.innerHTML = ddHtml;
    }

    applyUserPermissionsUI();
}

// Khởi chạy khi tài liệu sẵn sàng
window.onload = function() {
    checkAppAuth(function(isAllowed) {
        if (isAllowed) {
            initUserData();
            loadAppTabs(function() {
                loadOtaData();
            });
            updateDownloadBadge();
        }
    });
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
            // Chuẩn hóa đường dẫn icon và plist
            var iconUrl = item.icon || '';
            if (iconUrl.indexOf('http') !== 0) {
                iconUrl = '../' + iconUrl;
            }
            var plistUrl = item.plist || '';
            if (plistUrl.indexOf('http') !== 0) {
                plistUrl = 'https://tomkidsrepo.cloud/' + plistUrl;
            }

            var appObj = {
                index: appCounter++,
                name: item.name || 'Không rõ',
                version: item.version || '1.0',
                category: catName,
                hidden: (item.hidden === true),
                show_on_home: (item.show_on_home !== false),
                show_on_guest: (item.show_on_guest === true),
                show_on_private: (item.show_on_private === true),
                custom_tabs: item.custom_tabs || [],
                icon: iconUrl,
                plist: plistUrl,
                rating: 5,
                ratingCount: Math.floor(Math.random() * 20) + 1,
                author: getAuthorFromName(item.name),
                size: (item.name ? (item.name.length * 3.5 + 4).toFixed(1) : '10.5') + ' MB'
            };

            // Copy dynamic show_on_* properties
            for (var prop in item) {
                if (item.hasOwnProperty(prop) && prop.indexOf('show_on_') === 0) {
                    appObj[prop] = item[prop];
                }
            }

            allAppsFlat.push(appObj);
        }
    }

    applyFilterAndRender();
    applyUserPermissionsUI();
}

function getAuthorFromName(name) {
    if (!name) return 'Tomkids Team';
    if (name.indexOf('Flappy') >= 0) return 'Adam Carter';
    if (name.indexOf('PvZ') >= 0 || name.indexOf('Bejeweled') >= 0) return 'PopCap';
    if (name.indexOf('Facebook') >= 0 || name.indexOf('Messenger') >= 0) return 'Meta Inc.';
    if (name.indexOf('TikTok') >= 0) return 'ByteDance';
    if (name.indexOf('YouTube') >= 0 || name.indexOf('Google') >= 0 || name.indexOf('Chrome') >= 0) return 'Google LLC';
    if (name.indexOf('Zing') >= 0) return 'VNG Corp';
    if (name.indexOf('Contra') >= 0) return 'PunchBox';
    if (name.indexOf('Opera') >= 0) return 'Opera Software';
    return 'Collected & uploaded by Tomkids Team';
}

/* ==========================================================================
   3. RENDER DANH SÁCH ỨNG DỤNG (THEO CHUẨN GIAO DIỆN HÌNH 1 & 3)
   ========================================================================== */
function applyFilterAndRender() {
    filteredApps = [];
    var allowedCats = (globalCurrentUserAcc && globalCurrentUserAcc.allowed_categories) ? globalCurrentUserAcc.allowed_categories : ['ALL'];
    var hasAll = (allowedCats.indexOf('ALL') !== -1);

    var currentTabObj = null;
    for (var t = 0; t < appTabs.length; t++) {
        if (appTabs[t].id.toLowerCase() === currentCategory.toLowerCase()) {
            currentTabObj = appTabs[t];
            break;
        }
    }

    for (var i = 0; i < allAppsFlat.length; i++) {
        var app = allAppsFlat[i];

        if (currentTabObj && currentTabObj.type === 'curated') {
            var hasPermForCurated = (hasAll || allowedCats.indexOf(currentTabObj.id) !== -1);
            if (hasPermForCurated && isAppInCuratedTab(app, currentTabObj)) {
                filteredApps.push(app);
            }
        } else {
            // Các tab khác không hiển thị app bị ẩn hoàn toàn (hidden === true)
            if (app.hidden === true) continue;

            if (currentCategory === 'ALL') {
                if (hasAll || allowedCats.indexOf(app.category) !== -1) {
                    filteredApps.push(app);
                }
            } else if (app.category === currentCategory) {
                if (hasAll || allowedCats.indexOf(app.category) !== -1) {
                    filteredApps.push(app);
                }
            }
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
        if (downloads[d].plist === selectedApp.plist || (downloads[d].name === selectedApp.name && downloads[d].version === selectedApp.version)) {
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
        removeDownloadRecord(selectedApp.plist, selectedApp.name, selectedApp.version);
        showToast("Đã xoá " + selectedApp.name + " (" + selectedApp.version + ") khỏi lịch sử tải.");
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
        if (downloads[i].plist === app.plist || (downloads[i].name === app.name && downloads[i].version === app.version)) {
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

function removeDownloadRecord(appPlist, appName, appVersion) {
    var downloads = getStoredDownloads();
    var filtered = [];
    for (var i = 0; i < downloads.length; i++) {
        var matchSame = (appPlist && downloads[i].plist === appPlist) || (downloads[i].name === appName && downloads[i].version === appVersion);
        if (!matchSame) {
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
    var appShell = document.getElementById('app-shell');

    var isOpen = drawer && drawer.className.indexOf('open') !== -1;
    var shouldOpen = (typeof show === 'boolean') ? show : !isOpen;

    if (shouldOpen) {
        if (drawer) drawer.className = 'sidebar-drawer open';
        if (appShell) appShell.className = 'app-shell pushed';
        if (overlay) overlay.style.display = 'block';
        document.body.className = (document.body.className.replace(/\s*sidebar-open/g, '') + ' sidebar-open').trim();
    } else {
        if (drawer) drawer.className = 'sidebar-drawer';
        if (appShell) appShell.className = 'app-shell';
        if (overlay) overlay.style.display = 'none';
        document.body.className = document.body.className.replace(/\s*sidebar-open/g, '').trim();
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
    var dd = document.getElementById('category-dropdown');
    if (dd) dd.style.display = 'none';

    var titleEl = document.getElementById('current-title');
    if (titleEl) {
        if (cat === 'ALL') {
            titleEl.innerText = 'Danh mục';
        } else {
            var found = null;
            for (var k = 0; k < appTabs.length; k++) {
                if (appTabs[k].id.toLowerCase() === cat.toLowerCase()) {
                    found = appTabs[k];
                    break;
                }
            }
            if (found) {
                titleEl.innerText = (found.icon ? found.icon + ' ' : '') + found.name;
            } else {
                titleEl.innerText = cat;
            }
        }
    }

    // Cập nhật chip button
    var chips = document.querySelectorAll ? document.querySelectorAll('.chip-item') : [];
    for (var i = 0; i < chips.length; i++) {
        var chip = chips[i];
        var dataCat = chip.getAttribute('data-cat');
        if (dataCat === cat) {
            chip.className = 'chip-item active';
        } else {
            chip.className = 'chip-item';
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
    filteredApps = results;
    renderAppList(filteredApps);
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


/* ==========================================================================
   XÁC THỰC BẢO VỆ KHO APP (THÍCH ỨNG SAFARI IOS CỔ 5, 6, 7, 8, 9, 10)
   ========================================================================== */
var globalAuthData = null;
var globalCurrentUserAcc = null;

function checkAppAuth(callback) {
    var xhr = new XMLHttpRequest();
    xhr.open('GET', '../auth_accounts.json?t=' + (new Date()).getTime(), true);
    xhr.onreadystatechange = function() {
        if (xhr.readyState === 4) {
            if (xhr.status === 200 || xhr.status === 0) {
                try {
                    globalAuthData = JSON.parse(xhr.responseText);
                } catch(e) {
                    globalAuthData = { enabled: false, accounts: [] };
                }
            } else {
                globalAuthData = { enabled: false, accounts: [] };
            }

            if (!globalAuthData || !globalAuthData.enabled) {
                if (callback) callback(true);
                return;
            }

            // Kiểm tra session hiện tại
            var sessionUser = localStorage.getItem(STORAGE_AUTH_USER);
            if (sessionUser) {
                var accounts = globalAuthData.accounts || [];
                for (var i = 0; i < accounts.length; i++) {
                    if (accounts[i].username.toLowerCase() === sessionUser.toLowerCase()) {
                        if (accounts[i].active !== false) {
                            globalCurrentUserAcc = accounts[i];
                            if (callback) callback(true);
                            return;
                        }
                    }
                }
            }

            // Chưa đăng nhập hoặc tài khoản bị khóa -> Hiện modal đăng nhập
            showAppAuthModal();
            if (callback) callback(false);
        }
    };
    xhr.send(null);
}

function showAppAuthModal() {
    var overlay = document.getElementById('app-auth-overlay');
    if (overlay) {
        overlay.style.display = 'block';
        document.getElementById('app-auth-user').value = '';
        document.getElementById('app-auth-pass').value = '';
        document.getElementById('app-auth-err').style.display = 'none';
    }
}

function submitAppAuth() {
    var u = document.getElementById('app-auth-user').value.replace(/^\s+|\s+$/g, '');
    var p = document.getElementById('app-auth-pass').value.replace(/^\s+|\s+$/g, '');
    var err = document.getElementById('app-auth-err');

    if (!u || !p) {
        err.innerText = 'Vui lòng nhập đầy đủ Tài khoản và Mật khẩu!';
        err.style.display = 'block';
        return;
    }

    if (!globalAuthData || !globalAuthData.enabled) {
        localStorage.setItem(STORAGE_AUTH_USER, u);
        localStorage.setItem(STORAGE_USER_NAME, u);
        document.getElementById('app-auth-overlay').style.display = 'none';
        initUserData();
        loadOtaData();
        updateDownloadBadge();
        return;
    }

    var accounts = globalAuthData.accounts || [];
    for (var i = 0; i < accounts.length; i++) {
        var acc = accounts[i];
        if (acc.username.toLowerCase() === u.toLowerCase()) {
            if (acc.active === false) {
                err.innerText = 'Tài khoản này hiện đang bị khóa!';
                err.style.display = 'block';
                return;
            }
            if (acc.password === p) {
                globalCurrentUserAcc = acc;
                localStorage.setItem(STORAGE_AUTH_USER, acc.username);
                localStorage.setItem(STORAGE_USER_NAME, acc.username);
                document.getElementById('app-auth-overlay').style.display = 'none';
                initUserData();
                loadOtaData();
                updateDownloadBadge();
                applyUserPermissionsUI();
                return;
            }
        }
    }

    err.innerText = 'Sai tài khoản hoặc mật khẩu!';
    err.style.display = 'block';
}

function logoutAppStore() {
    if (confirm('Bạn có chắc chắn muốn đăng xuất tài khoản khỏi Tomkids AppStore không?')) {
        localStorage.removeItem(STORAGE_AUTH_USER);
        localStorage.removeItem(STORAGE_USER_NAME);
        window.location.href = '../';
    }
}


function applyUserPermissionsUI() {
    if (!globalCurrentUserAcc) return;
    var allowedCats = globalCurrentUserAcc.allowed_categories || ['ALL'];
    var hasAll = (allowedCats.indexOf('ALL') !== -1);

    var chips = document.querySelectorAll ? document.querySelectorAll('.chip-item') : [];
    var ddItems = document.querySelectorAll ? document.querySelectorAll('.dropdown-item') : [];

    for (var i = 0; i < chips.length; i++) {
        var cat = chips[i].getAttribute('data-cat');
        if (hasAll) {
            chips[i].style.display = 'inline-block';
        } else {
            if (cat === 'ALL') {
                chips[i].style.display = 'none';
            } else if (allowedCats.indexOf(cat) !== -1) {
                chips[i].style.display = 'inline-block';
            } else {
                chips[i].style.display = 'none';
            }
        }
    }

    for (var j = 0; j < ddItems.length; j++) {
        var cat2 = ddItems[j].getAttribute('data-cat');
        if (hasAll) {
            ddItems[j].style.display = 'block';
        } else {
            if (cat2 === 'ALL') {
                ddItems[j].style.display = 'none';
            } else if (allowedCats.indexOf(cat2) !== -1) {
                ddItems[j].style.display = 'block';
            } else {
                ddItems[j].style.display = 'none';
            }
        }
    }

    // Điều hướng tab hiển thị phù hợp:
    if (!hasAll) {
        if (allowedCats.indexOf(currentCategory) === -1) {
            if (allowedCats.length > 0) {
                filterBySubCategory(allowedCats[0]);
            }
        }
    }
}
