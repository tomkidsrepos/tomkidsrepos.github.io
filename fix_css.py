import os

with open('index.html', 'r', encoding='utf-8') as f:
    content = f.read()

media_query = '''
/* Responsive adjustments for iPhone 4S */
@media (max-width: 480px) {
    h1 { font-size: 32px; margin-top:15px; }
    .subtitle { font-size: 14px; }
    .source { padding: 12px 15px; font-size: 14px; margin-top:20px; }
    .info {
        padding: 15px;
        margin-top: 25px;
        border-radius: 15px;
    }
    .info h2 { font-size: 16px; margin-bottom: 10px; }
    
    .buttons .btn {
        display: block;
        margin: 10px auto;
        max-width: 250px;
        padding: 12px 20px;
        font-size: 14px;
    }
    
    /* Quick install steps adjustments */
    .step-box {
        padding: 12px !important;
    }
    .step-btn {
        padding: 8px 12px !important;
        font-size: 13px !important;
        white-space: normal !important;
        line-height: 1.3 !important;
    }
    
    /* OTA Apps list */
    .accordion-header {
        padding: 12px 15px;
        font-size: 14px;
    }
    .app-icon {
        width: 45px;
        height: 45px;
        margin-right: 10px;
    }
    .app-title { font-size: 13px; }
    .app-version { font-size: 11px; }
    .btn-install {
        padding: 6px 12px;
        font-size: 12px;
    }
}
</style>'''

content = content.replace('</style>', media_query)

content = content.replace('<div style="background:#0f172a; border-radius:14px; padding:18px; margin-bottom:16px; text-align:left; max-width:520px; margin-left:auto; margin-right:auto;">', 
                          '<div class="step-box" style="background:#0f172a; border-radius:14px; padding:18px; margin-bottom:16px; text-align:left; max-width:520px; margin-left:auto; margin-right:auto;">')
content = content.replace('<div style="background:#0f172a; border-radius:14px; padding:18px; text-align:left; max-width:520px; margin-left:auto; margin-right:auto;">',
                          '<div class="step-box" style="background:#0f172a; border-radius:14px; padding:18px; text-align:left; max-width:520px; margin-left:auto; margin-right:auto;">')

content = content.replace('style="background:#2563eb;color:white;padding:10px 20px;-webkit-border-radius:10px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;"',
                          'class="step-btn" style="background:#2563eb;color:white;padding:10px 20px;-webkit-border-radius:10px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;"')
content = content.replace('style="background:#16a34a;color:white;padding:10px 20px;-webkit-border-radius:10px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;"',
                          'class="step-btn" style="background:#16a34a;color:white;padding:10px 20px;-webkit-border-radius:10px;border-radius:10px;text-decoration:none;font-weight:bold;font-size:14px;display:inline-block;"')

with open('index.html', 'w', encoding='utf-8') as f:
    f.write(content)
