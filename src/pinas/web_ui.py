PAGE=r'''<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>PiNAS · Raspberry Pi NAS</title><style>
/* Self-hosted fonts for the login and dashboard, available offline. */
@font-face{font-family:'Clear Sans';src:url('/assets/fonts/ClearSans-Regular.woff') format('woff');font-style:normal;font-weight:400;font-display:swap}
@font-face{font-family:'Clear Sans';src:url('/assets/fonts/ClearSans-Medium.woff') format('woff');font-style:normal;font-weight:500 600;font-display:swap}
@font-face{font-family:'Clear Sans';src:url('/assets/fonts/ClearSans-Bold.woff') format('woff');font-style:normal;font-weight:700 900;font-display:swap}
@font-face{font-family:'Source Code Pro';src:url('/assets/fonts/SourceCodePro-Regular.woff2') format('woff2');font-style:normal;font-weight:400 600;font-display:swap}
@font-face{font-family:'Source Code Pro';src:url('/assets/fonts/SourceCodePro-Bold.woff2') format('woff2');font-style:normal;font-weight:700 900;font-display:swap}
:root{--font-ui:'Clear Sans',Arial,sans-serif;--font-mono:'Source Code Pro','Courier New',monospace;--accent:#c51a4a;--bg:#f7f8fa;--surface:#fff;--ink:#20232a;--muted:#646b76;--line:#e4e7eb;--soft:#f1f3f6;--success:#218457;--warning:#a76a12;--danger:#bb3444;--radius:16px;--radius-sm:11px;--space:8px;--ease:cubic-bezier(.2,.75,.25,1);--duration:190ms;--shadow:0 6px 24px rgba(20,24,34,.035);font-family:var(--font-ui);font-size:12px;color:var(--ink);background:var(--bg)}
*{box-sizing:border-box}body{margin:0}button,input,select,textarea{font:inherit}pre,code,kbd,samp,#ms-folders{font-family:var(--font-mono)}button{cursor:pointer}button:disabled{opacity:.5;cursor:default}header{height:72px;background:var(--surface);border-bottom:1px solid var(--line);display:flex;align-items:center;padding:0 max(24px,calc((100vw - 1220px)/2));gap:18px}.brand{display:flex;align-items:center;gap:12px;font-weight:800;font-size:23px;white-space:nowrap}.mark{background:var(--accent);color:white;border-radius:12px;width:43px;height:43px;display:grid;place-items:center;font-size:27px}.brand small{font-size:11px;font-weight:500;color:var(--muted);display:block;letter-spacing:.6px}nav{display:flex;gap:4px;flex:1;overflow-x:auto;position:relative}nav button{background:transparent;border:0;color:var(--muted);padding:12px 14px;border-radius:8px;font-weight:600;white-space:nowrap}nav button.active{background:transparent;color:var(--ink)}main{max-width:1220px;margin:35px auto;padding:0 24px}h1{font-size:30px;letter-spacing:-1px;margin:0 0 7px}h2{font-size:17px;margin:0 0 16px}p{color:var(--muted);line-height:1.6}.subtitle{margin:0 0 27px}.grid{display:grid;grid-template-columns:repeat(3,minmax(0,1fr));gap:18px}.card{background:var(--surface);border:1px solid var(--line);border-radius:var(--radius);padding:23px;min-width:0}.wide{grid-column:1/-1}.span2{grid-column:span 2}.label{font-size:12px;color:var(--muted);font-weight:700;text-transform:uppercase;letter-spacing:.8px}.big{font-size:29px;font-weight:800;margin:11px 0}.small{font-size:12px;color:var(--muted)}.pill{display:inline-flex;padding:6px 10px;border-radius:30px;background:var(--soft);color:var(--muted);font-size:12px;font-weight:700}.bar{height:9px;background:var(--soft);border-radius:9px;overflow:hidden;margin:15px 0}.bar i{height:100%;display:block;background:var(--accent);border-radius:9px}.line{border-top:1px solid var(--line);padding:14px 0;display:flex;align-items:center;justify-content:space-between;gap:15px}.line:first-of-type{border-top:0}.line strong{display:block}.btn{background:var(--accent);border:1px solid var(--accent);color:white;padding:11px 17px;border-radius:8px;font-weight:700}.outline{background:transparent;border-color:var(--line);color:var(--ink)}.field{display:flex;flex-direction:column;gap:8px;margin:15px 0}.field input,.field select{background:var(--surface);border:1px solid var(--line);border-radius:8px;padding:12px;color:var(--ink);width:100%;max-width:440px}.hint{background:var(--soft);padding:15px;border-radius:9px;color:var(--muted);line-height:1.6}.login{min-height:100vh;display:grid;place-items:center;padding:24px;background-position:center;background-size:cover}.login .card{width:min(100%,430px);box-shadow:0 14px 45px #00000017}.login h1{margin-top:22px}.login input{max-width:none}.login .btn{width:100%}.loginbg{background-image:var(--login-image)}.hidden{display:none!important}.footer{padding:26px 0;color:var(--muted);font-size:12px;display:flex;justify-content:space-between}input[type=color]{padding:3px;width:64px;height:42px}input[type=file]{max-width:440px}#message{margin-top:12px;color:var(--accent)}@media(max-width:900px){header{height:auto;flex-wrap:wrap;padding:12px 20px}nav{order:3;width:100%;flex-basis:100%}.grid{grid-template-columns:repeat(2,minmax(0,1fr))}.span2{grid-column:1/-1}}@media(max-width:560px){.grid{grid-template-columns:1fr}.span2{grid-column:auto}main{padding:0 15px;margin:22px auto}header{padding:10px 15px}.card{padding:18px}}
.icon-btn{display:grid;place-items:center;width:42px;height:42px;border:1px solid var(--line);border-radius:10px;background:var(--surface);color:var(--ink)}.icon-btn:hover{border-color:var(--accent)}.share-permission-groups{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:12px;margin:12px 0}.share-permission-group{border:1px solid var(--line);border-radius:9px;padding:12px;min-width:0}.share-permission-group legend{font-weight:700;padding:0 5px}.share-user-choice{display:flex;align-items:center;gap:10px;padding:7px 0;cursor:pointer;overflow-wrap:anywhere}.share-user-choice input,.share-public-toggle input{width:18px;height:18px;flex:none;accent-color:var(--accent)}.share-public-toggle{display:flex;align-items:flex-start;gap:10px;padding:14px;margin:14px 0;border:1px solid var(--line);border-radius:9px;cursor:pointer}.share-public-toggle small{display:block;color:var(--muted);margin-top:5px}.share-public-write{padding:10px 14px;background:var(--soft);border-radius:9px}.share-public-write[hidden]{display:none}.share-permissions-disabled{opacity:.45}@media(max-width:440px){.share-permission-groups{grid-template-columns:1fr}}.share-top-actions{display:flex;justify-content:flex-start;margin:12px 0}.share-icon-btn{padding:0;width:42px;height:42px;min-width:42px;line-height:1;flex:none}.share-icon-btn svg{width:24px;height:24px;margin:0;flex:none}.share-entry{align-items:center}.share-meta{min-width:0;flex:1;overflow-wrap:anywhere}.share-meta>div{margin:4px 0}.share-meta strong{display:inline;font-weight:700}.share-actions{display:flex;gap:8px;align-items:center;flex:none;flex-wrap:wrap}.user-row-actions{display:flex;gap:8px;align-items:center;justify-content:flex-end;flex-wrap:wrap}.delete-folder-action{color:var(--danger);border-color:var(--danger)}.delete-folder-action:hover:not(:disabled){background:var(--danger);border-color:var(--danger);color:#fff}.delete-folder-action svg{display:block;width:22px;height:22px;flex:none}@media(max-width:550px){.share-entry{align-items:flex-start}.share-actions{flex-direction:column}}.modal-overlay{position:fixed;inset:0;z-index:1000;background:#0009;display:grid;place-items:center;padding:16px}.settings-modal{width:min(100%,760px);max-height:min(90vh,850px);display:flex;flex-direction:column;box-shadow:0 20px 80px #0005}.modal-heading,.modal-actions{display:flex;align-items:center;justify-content:space-between;gap:12px}.modal-heading h2{margin:0}.modal-actions{justify-content:flex-end;padding-top:16px;border-top:1px solid var(--line)}.settings-scroll{overflow-y:auto;padding:12px 2px}.settings-scroll h3{margin:24px 0 8px;font-size:1.1rem}.settings-scroll .field{max-width:100%}.stat .big{font-size:38px}.clickable{cursor:pointer}.clickable:hover{border-color:var(--accent)}.chart-title,.chart-footer{display:flex;align-items:center;justify-content:space-between;gap:12px}.chart-title h2{margin:0}.cpu-chart{margin:10px 0 4px;height:85px}.cpu-chart svg{height:100%;width:100%}.chart-footer .big{margin:5px 0}.metric{text-align:center}.metric h2{text-align:left}.ring{display:block;max-width:170px;width:100%;margin:8px auto}.metric p{margin:5px 0}.overview .wide{grid-column:1/-1}.overview-counts{min-width:0}.overview-summary{display:flex;flex-direction:column;gap:8px}.overview-summary .stat{padding:4px 0;text-align:center;min-width:0}.overview-summary .stat+.stat{border-top:1px solid var(--line);padding-top:9px}.overview-summary .big{font-size:clamp(22px,3vw,30px);margin:3px 0}.overview-summary .small{display:none}.overview .disk-summary{padding:12px 0;border-top:1px solid var(--line)}.overview .disk-summary:first-of-type{border-top:0}.overview .disk-summary .disk-heading{gap:12px;flex-wrap:wrap}.overview .disk-summary .bar{margin:9px 0 0}@media(max-width:560px){.overview .wide{grid-column:auto}}

 .storage-disk-entry{display:flex;align-items:center;justify-content:space-between;gap:20px;padding:22px 0;border-top:1px solid var(--line)}.storage-disk-entry:first-of-type{border-top:0}.disk-properties{display:grid;gap:9px;min-width:0}.disk-properties>div{display:grid;grid-template-columns:135px minmax(0,1fr);gap:12px;align-items:baseline}.disk-properties span{color:var(--muted)}.disk-properties strong{font-weight:600;overflow-wrap:anywhere}.disk-management-action{display:flex;justify-content:space-between;align-items:center;gap:18px;border-top:1px solid var(--line);padding:18px 0}.disk-management-action>div{min-width:0}.disk-management-action p{margin:7px 0}.disk-management-action .btn{min-width:135px}.disk-management-action button:disabled{opacity:.45}@media(max-width:560px){.storage-disk-entry,.disk-management-action{align-items:stretch;flex-direction:column}.disk-properties>div{grid-template-columns:115px minmax(0,1fr)}}.storage-action{min-width:125px}.storage-volume{padding:10px 0;border-top:1px solid var(--line)}.wizard-option{display:block;padding:12px;border:1px solid var(--line);border-radius:var(--radius-sm);margin:8px 0}.wizard-option input{margin-right:8px}.wizard-option small{display:block;color:var(--muted);margin:5px 0 0 25px}.storage-wizard{width:min(100%,610px)}.disk-summary{padding:18px 0;border-top:1px solid var(--line)}.disk-summary:first-of-type{border-top:0}.disk-heading,.disk-foot{display:flex;justify-content:space-between;gap:12px;align-items:center}.disk-heading strong,.disk-heading .small{display:block}.disk-heading .small{margin-top:5px}.disk-usage{height:12px;margin:12px 0 8px}.disk-foot{color:var(--muted);font-size:12px}@media(max-width:560px){.disk-heading{align-items:flex-start;flex-direction:column}}
.raid-wizard{width:min(100%,660px)}.raid-disk{display:flex;gap:12px;align-items:center;border:1px solid var(--line);padding:12px;border-radius:var(--radius-sm);margin:8px 0;cursor:pointer}.raid-disk span{display:flex;flex-direction:column;gap:4px}.raid-disk small{color:var(--muted)}.raid-disk input{accent-color:var(--accent)}
.health-grid{display:grid;grid-template-columns:repeat(2,minmax(0,1fr));gap:20px}.health-grid>div{display:flex;flex-direction:column;gap:7px;min-width:0}.health-grid strong{overflow-wrap:anywhere;font-size:1.1rem}@media(max-width:560px){.health-grid{grid-template-columns:1fr}}
.share-remove-confirm{background:var(--danger)!important;color:#fff!important;border-color:var(--danger)!important}
/* PiNAS unified design system — no per-page hard-coded appearance rules */
[data-theme=dark]{--bg:#12151a;--surface:#1b2028;--ink:#f4f5f7;--muted:#abb3bf;--line:#343b47;--soft:#272e38}
nav button{border-radius:0;position:relative;font-size:calc(1rem + 1.5px)}nav button:hover{background:transparent;color:var(--ink)}nav .nav-indicator{position:absolute;bottom:0;height:3px;background:var(--accent);border-radius:3px;pointer-events:none;left:0;width:0;transition:transform 260ms cubic-bezier(.22,1,.36,1),width 260ms cubic-bezier(.22,1,.36,1);will-change:transform,width}body{min-width:320px}header{gap:14px}main{margin-top:32px}.card{box-shadow:var(--shadow);transition:border-color var(--duration) var(--ease),box-shadow var(--duration) var(--ease)}.card:hover{box-shadow:0 9px 28px rgba(20,24,34,.06)}.btn,.icon-btn,nav button{transition:background var(--duration) var(--ease),color var(--duration) var(--ease),border-color var(--duration) var(--ease),transform var(--duration) var(--ease)}.btn:not(:disabled):active,.icon-btn:active{transform:scale(.98)}.btn:hover:not(:disabled){filter:brightness(.96)}.btn:focus-visible,.icon-btn:focus-visible,nav button:focus-visible,input:focus-visible,select:focus-visible,.clickable:focus-visible{outline:3px solid var(--accent);outline-offset:3px}.good{color:var(--success)}.danger{color:var(--danger)}.hint{border:1px solid var(--line)}.pill{font-weight:600}.settings-group{border:1px solid var(--line);border-radius:var(--radius-sm);margin:9px 0;overflow:hidden}.settings-group>summary{padding:14px 16px;font-weight:600;cursor:pointer;background:var(--soft);list-style-position:inside}.settings-group-body{padding:16px}.settings-group[open]>summary{border-bottom:1px solid var(--line)}.settings-modal{animation:modal-in var(--duration) var(--ease)}.modal-overlay{animation:fade-in var(--duration) ease}.settings-scroll{overscroll-behavior:contain}.settings-modal .icon-btn{flex-shrink:0}.field input,.field select{min-height:44px}.clickable{transition:transform var(--duration) var(--ease),border-color var(--duration) var(--ease)}.clickable:hover{transform:translateY(-1px)}.line>div{min-width:0;overflow-wrap:anywhere}.footer{gap:12px;flex-wrap:wrap}.login .brand{justify-content:center}.login .card{border-radius:20px}.login h1{letter-spacing:-.7px}@keyframes modal-in{from{opacity:0;transform:translateY(8px) scale(.99)}to{opacity:1;transform:translateY(0) scale(1)}}@keyframes fade-in{from{opacity:0}to{opacity:1}}@media(prefers-reduced-motion:reduce){*,*::before,*::after{animation-duration:.01ms!important;transition-duration:.01ms!important;scroll-behavior:auto!important}}@media(max-width:900px){header{gap:8px}nav{scrollbar-width:none}nav::-webkit-scrollbar{display:none}}@media(max-width:560px){.modal-overlay{padding:8px}.settings-modal{max-height:94dvh}.chart-footer{flex-wrap:wrap}}
.section-spaced{margin-top:16px}.status-spaced{margin-top:12px}.button-with-icon{display:inline-flex;align-items:center;justify-content:center;gap:9px}.table-scroll{overflow-x:auto}.updates-package-table{width:100%;text-align:left;border-spacing:0 9px}.compact-card{padding:14px}.file-toolbar{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0}

.file-action-btn{width:38px;height:38px;min-width:38px;display:inline-flex;align-items:center;justify-content:center;padding:6px;border-radius:10px;flex-shrink:0}.file-action-btn svg{display:block;flex-shrink:0}.file-action-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}.file-action-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
.file-toolbar .icon-btn{flex:0 0 48px;width:48px;height:48px;border-radius:11px;padding:8px;box-shadow:none;appearance:none;overflow:hidden}.file-toolbar .icon-btn svg{display:block;flex-shrink:0}.file-toolbar .icon-btn:hover:not(:disabled),.file-toolbar .file-upload-control:hover:not(:has(input:disabled)){background:var(--accent);border-color:var(--accent);color:#fff}.file-toolbar .icon-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}.file-upload-control{position:relative;cursor:pointer}.file-upload-control input{position:absolute;width:1px;height:1px;opacity:0;overflow:hidden}.file-upload-control:focus-within{outline:3px solid var(--accent);outline-offset:3px}.file-upload-control:has(input:disabled){opacity:.5;cursor:default}.file-entry{display:flex;align-items:center;gap:11px;min-width:0}.file-entry svg{flex-shrink:0;color:var(--accent)}.file-entry .file-name{overflow-wrap:anywhere}.action-icon-btn svg{display:block;width:22px;height:22px;flex:none}.action-icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.updates-history-controls{display:flex;align-items:end;gap:12px;flex-wrap:wrap;margin-top:12px}.updates-history-controls .field{margin:0}.update-history-row{padding:0;border:1px solid var(--line);border-radius:var(--radius-sm);margin:10px 0;background:var(--surface)}.update-history-row>summary{display:flex;justify-content:space-between;align-items:center;gap:12px;cursor:pointer;padding:15px 16px}.update-history-row>summary .small{display:block;margin-top:4px}.update-history-row[open]>summary{border-bottom:1px solid var(--line)}.update-history-details{padding:14px 16px}.update-history-details ul{padding-left:22px}.update-history-details li{padding:3px 0}.update-history-row .line{padding:7px 0}.update-history-row pre{white-space:pre-wrap;overflow-wrap:anywhere}.update-unit-action{display:flex;align-items:center;gap:10px;flex-wrap:wrap;justify-content:flex-end}.storage-summary-heading{padding-bottom:16px;margin-bottom:14px;flex-wrap:wrap;row-gap:12px}.storage-summary-heading .btn{flex-shrink:0}.storage-summary-heading .btn svg{width:22px;height:22px;display:block;flex:none}.storage-summary-heading .btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.disk-smart-meta{display:flex;gap:18px;flex-wrap:wrap;margin-top:9px}.disk-health-good{color:var(--success)}.disk-health-warning{color:var(--danger)}.storage-safety-warning{border:1px solid var(--warning);margin-bottom:16px}.storage-safety-warning h2{margin-bottom:8px}.storage-safety-warning p{margin:6px 0}.user-avatar{width:38px;height:38px;border-radius:50%;object-fit:cover;background:var(--soft);border:1px solid var(--line)}.user-header{display:flex;align-items:center;gap:10px;margin-left:auto}.profile-preview{width:74px;height:74px;border-radius:50%;object-fit:cover;border:1px solid var(--line);background:var(--soft)}.avatar-placeholder{display:inline-flex;align-items:center;justify-content:center;color:var(--muted);flex-shrink:0}.avatar-placeholder svg{width:70%;height:70%;display:block}.profile-preview img{width:100%;height:100%;border-radius:50%;object-fit:cover}.update-reboot-panel[hidden]{display:none}.update-reboot-panel{margin:16px 0;padding:15px;border:1px solid var(--warning);border-radius:var(--radius-sm)}.update-reboot-panel p{margin:0 0 12px}
.file-entry{border:0;background:transparent;color:var(--ink);font:inherit;text-align:left;cursor:pointer;flex:1;padding:8px 0}.file-entry:hover{text-decoration:underline}
/* Shared icon behaviour across administrator and NAS-user views. */
.icon-btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}
.icon-btn svg{display:block;flex-shrink:0}
.icon-btn:focus-visible{outline:3px solid var(--accent);outline-offset:2px}
/* Keep input focus rings entirely within the control, including scrollable dialogs. */
.field input:focus,.field select:focus,.field textarea:focus{outline:none;border-color:var(--accent);box-shadow:inset 0 0 0 2px var(--accent)}
.field input:focus-visible,.field select:focus-visible,.field textarea:focus-visible{outline:none;outline-offset:0}
.settings-scroll{padding-left:8px;padding-right:8px}
.sr-only{position:absolute;width:1px;height:1px;padding:0;margin:-1px;overflow:hidden;clip:rect(0,0,0,0);white-space:nowrap;border:0}.modal-actions .btn svg,#transfer-cancel svg{width:19px;height:19px;vertical-align:middle;margin-right:6px}.user-header #file-logout{width:42px;height:42px;flex-shrink:0}.user-header #file-logout svg{display:block;width:24px;height:24px}.user-header #file-logout:hover{background:var(--accent);border-color:var(--accent);color:#fff}.user-top-actions{display:flex;justify-content:flex-start;gap:12px;flex-wrap:wrap;margin:0 0 18px}.add-user-button{display:inline-flex;align-items:center;justify-content:center;gap:8px;transition:background .18s ease,border-color .18s ease,color .18s ease}.add-user-button svg{display:block;width:22px;height:22px;flex:none}.add-user-button:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.add-user-button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.user-management-cards{display:grid;grid-template-columns:1fr;gap:18px}.edit-user-button{display:inline-flex;align-items:center;gap:8px;flex-shrink:0}.edit-user-button svg{width:22px;height:22px;display:block;flex:none}.edit-user-button:hover{background:var(--accent);border-color:var(--accent);color:#fff}.edit-user-button:focus-visible{outline:2px solid var(--accent);outline-offset:3px}
.raid-array-entry{border:1px solid var(--line);border-radius:12px;padding:16px;margin:14px 0}.raid-array-entry .line{gap:12px}.progress-track{height:8px;background:var(--line);border-radius:8px;overflow:hidden;margin:8px 0}.progress-fill{height:100%;background:var(--accent);border-radius:8px;transition:width .3s ease}

.updates-schedule-options{border:0;padding:0;margin:14px 0 12px;min-width:0}.updates-schedule-options legend{font-weight:600;margin-bottom:10px}.updates-schedule-options label{display:flex;align-items:center;gap:12px;padding:10px 12px;margin:5px 0;border:1px solid var(--line);border-radius:11px;cursor:pointer;transition:border-color .18s,background .18s}.updates-schedule-options label:hover{border-color:var(--accent);background:var(--accent-soft,rgba(160,40,55,.06))}.updates-schedule-options input[type=radio]{accent-color:var(--accent);width:18px;height:18px;flex:none;margin:0}.updates-schedule-options label:has(input:checked){border-color:var(--accent)}.updates-schedule-options label:focus-within{outline:2px solid var(--accent);outline-offset:2px}

.save-schedule-button{display:inline-flex;align-items:center;gap:9px;margin:12px 0 8px}.save-schedule-button svg{flex:none;display:block}.save-schedule-button:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff}
.updates-actions{display:flex;gap:10px;flex-wrap:wrap;margin:14px 0 12px}.updates-actions .btn{display:inline-flex;align-items:center;justify-content:center;gap:9px;transition:background var(--duration) var(--ease),border-color var(--duration) var(--ease),color var(--duration) var(--ease),transform var(--duration) var(--ease)}.updates-actions .btn svg{display:block;width:22px;height:22px;flex:none}.updates-actions .btn:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}.updates-actions .btn:focus-visible{outline:2px solid var(--accent);outline-offset:3px}.updates-actions .btn:disabled{opacity:.45;cursor:not-allowed;transform:none;filter:none}.updates-status-row{display:flex;align-items:center;gap:12px;min-height:32px;margin:0 0 16px}.updates-spinner{width:18px;height:18px;flex:none;border:2px solid var(--line);border-top-color:var(--accent);border-radius:50%;animation:updates-spin .8s linear infinite}.updates-spinner[hidden]{display:none!important}@keyframes updates-spin{to{transform:rotate(360deg)}}.updates-log{margin-top:16px;border:1px solid var(--line);border-radius:11px;overflow:hidden}.updates-log summary{cursor:pointer;padding:12px 14px;font-weight:600;user-select:none}.updates-log summary:hover{color:var(--accent)}.updates-log pre{white-space:pre-wrap;overflow:auto;max-height:250px;margin:0;padding:12px 14px;border-top:1px solid var(--line)}.updates-actions .btn:disabled{opacity:.45;cursor:not-allowed;filter:grayscale(1)}
/* RC16.4 shared UI consistency and accessibility pass */
:root{--control-radius:var(--radius-sm);--control-height:42px;--dialog-gap:16px}
.btn{display:inline-flex;align-items:center;justify-content:center;gap:8px;min-height:var(--control-height);border-radius:var(--control-radius);line-height:1.25;text-align:center}
.btn:disabled,.icon-btn:disabled{opacity:.5;cursor:not-allowed;transform:none;filter:none}
.btn.danger,.share-remove-confirm{background:#b72b3c!important;border-color:#b72b3c!important;color:#fff!important}
.btn.danger:hover:not(:disabled),.share-remove-confirm:hover:not(:disabled){background:#992234!important;border-color:#992234!important;filter:none}
.modal-overlay{overflow-y:auto;overscroll-behavior:contain}
.modal-overlay>.settings-modal{margin:auto;width:min(100%,570px);max-height:calc(100dvh - 32px);min-width:0;overflow-y:auto;overscroll-behavior:contain}
.modal-overlay .modal-heading{flex-shrink:0}
.modal-overlay .modal-actions{flex-wrap:wrap;row-gap:10px}
.modal-overlay .modal-actions>.btn{white-space:normal}
.modal-overlay .field input,.modal-overlay .field select{min-width:0}.disk-danger-consent span{display:flex;align-items:center;gap:10px}.nas-home-choice{display:flex;align-items:center;gap:10px;margin:15px 0}.modal-overlay .nas-home-choice input[type="checkbox"]{width:18px;height:18px;min-width:18px;max-width:18px;padding:0;margin:0;flex:none;accent-color:var(--accent)}.modal-overlay .disk-danger-consent input[type="checkbox"]{width:18px;height:18px;min-width:18px;max-width:18px;padding:0;margin:0;flex:none;accent-color:var(--accent)}
.modal-overlay [role="status"]{overflow-wrap:anywhere}
@media(max-width:560px){.modal-overlay>.settings-modal{max-height:calc(100dvh - 16px);padding:16px}.modal-overlay .modal-actions>.btn{flex:1 1 auto}}

.media-actions{display:flex;flex-wrap:wrap;gap:var(--space);margin:14px 0}
.media-fields{display:grid;grid-template-columns:repeat(auto-fit,minmax(240px,1fr));gap:12px}
.media-checkbox{display:flex;gap:10px;align-items:center;padding:8px 0}
#ms-form h3{margin-top:22px}
#ms-folders{width:100%;min-height:110px;border:1px solid var(--line);background:var(--surface);color:var(--ink);border-radius:var(--radius-sm);font:inherit;padding:12px;resize:vertical}
.media-picker{display:flex;gap:12px;align-items:flex-end;flex-wrap:wrap}.media-picker .field{flex:1 1 220px}.media-picker .btn{margin-bottom:12px}
.media-setup{border:1px solid var(--line);border-radius:var(--radius-sm);padding:16px;margin:18px 0;background:var(--soft)}
.media-setup h3{margin:0 0 6px}
.media-fields .hint{display:block;line-height:1.5;margin-top:5px}
.media-fields .hint em{font-style:normal;color:var(--muted)}
.media-checkbox .hint{font-weight:normal}

/* Storage categories: a central palette instead of inline colour literals. */
:root{--media-video:#6e80d6;--media-pictures:#c56ca1;--media-music:#39a58b;--media-other:#949aa4;--media-free:var(--soft)}
.disk-usage{display:flex;overflow:hidden;background:var(--media-free);align-items:stretch}
.disk-usage .media-segment{display:block;height:100%;min-width:0;flex-shrink:0}
.media-video{background:var(--media-video)}.media-pictures{background:var(--media-pictures)}
.media-music{background:var(--media-music)}.media-other{background:var(--media-other)}.media-free{background:var(--media-free)}
.media-legend{display:flex;flex-wrap:wrap;column-gap:16px;row-gap:8px;margin:8px 0 12px;font-size:.92rem;color:var(--muted)}
.media-legend span{display:inline-flex;align-items:center;gap:6px}
.media-legend i{display:inline-block;width:9px;height:9px;border-radius:3px;flex-shrink:0;border:1px solid var(--line)}
.media-advanced{margin-top:20px}.media-advanced summary{font-weight:650;cursor:pointer;padding:10px 0}.media-advanced>.media-fields{margin-top:12px}.storage-file-types{border-top:1px solid var(--line);margin:14px 0 20px;padding-top:16px}.storage-file-types .line{align-items:center}.storage-file-types .line>div{display:flex;flex-direction:column;gap:4px}.storage-scan-bar{margin:12px 0}.storage-disk-entry+.disk-smart-meta{padding:9px 4px}.storage-file-types [data-scan-status]{min-height:20px}.media-folder-action{align-items:center;gap:12px;flex-wrap:wrap}.media-folder-action>.small{overflow-wrap:anywhere;flex:1;min-width:180px}.media-folder-buttons{display:flex;gap:8px;flex-wrap:wrap}.media-upload-modal{max-width:650px}.media-upload-modal .field input[type=file]{width:100%;padding:12px 0}.media-upload-progress{display:block;width:100%;height:12px;margin:14px 0}.media-upload-progress[hidden]{display:none}
/* Common accent hover and icon alignment for all outline button actions. */
.btn.outline:hover:not(:disabled){background:var(--accent);border-color:var(--accent);color:#fff;filter:none}
.btn.button-with-icon{display:inline-flex;align-items:center;justify-content:center;gap:8px}
.btn.button-with-icon>svg{display:block;width:22px;height:22px;min-width:22px;flex:none;color:inherit}
.btn.button-with-icon>span{display:inline-block}
</style></head><body><div id="app"></div><script>
const app=document.getElementById('app');let info={},cfg={},cpu={},page='Overview',csrf='',role='admin',username='',displayName='',refreshTimer=null,lastNavRect=null;
let lastUserAction=Date.now(),lastActivitySync=Date.now(),sessionRedirecting=false;
const sessionIdleMs=()=>[5,10,15,30,60].includes(Number(cfg.session_timeout))?Number(cfg.session_timeout)*60000:300000;
function returnToLogin(){
 if(!csrf||sessionRedirecting)return;
 sessionRedirecting=true;csrf='';
 window.location.replace('/');
}
function checkSessionIdle(){
 if(csrf&&Date.now()-lastUserAction>=sessionIdleMs())returnToLogin();
}
function recordUserActivity(){
 if(!csrf||sessionRedirecting)return;
 if(Date.now()-lastUserAction>=sessionIdleMs()){returnToLogin();return;}
 lastUserAction=Date.now();
 if(lastUserAction-lastActivitySync<30000)return;
 lastActivitySync=lastUserAction;
 fetch('/api/session-touch',{method:'POST',headers:{'Content-Type':'application/json','X-PiNAS-CSRF':csrf},body:'{}'})
   .then(response=>{if(response.status===403)returnToLogin()}).catch(()=>{});
}
for(const eventName of ['pointerdown','keydown','wheel','scroll'])
 document.addEventListener(eventName,recordUserActivity,{capture:true,passive:true});
window.addEventListener('focus',checkSessionIdle);
document.addEventListener('visibilitychange',checkSessionIdle);
setInterval(checkSessionIdle,1000);
// Navigation is derived from actual mounted NAS volumes, not a setup flag.
// Once provisioned, existing accounts/shares remain accessible for recovery.
const storageReady=()=>disks().some(d=>(d.volumes||[]).some(v=>v.fs&&v.persistent&&(v.mounts||[]).some(m=>m&&m!=='/'&&!m.startsWith('/boot'))));
const navItems=()=>{const ready=storageReady(),existingUsers=Number(info.nas_users||0)>0,existingShares=(info.shares||[]).length>0;let items=['Overview','Storage'];if(raidPageAvailable())items.push('RAID');items.push('Updates');items.push('Media Server');if(ready||existingUsers||existingShares)items.push('Users');if((ready&&existingUsers)||existingShares)items.push('Shares');return items};
const setupNotice=()=>{if(!storageReady())return `<div class="card wide setup-next"><h2>Get your NAS ready</h2><p>Start by configuring a data disk. Once a supported filesystem is mounted and configured to reconnect at startup, PiNAS will unlock user management.</p><button class="btn" data-next="Storage">Set up storage</button></div>`;if(!(Number(info.nas_users||0)>0))return `<div class="card wide setup-next"><h2>Next step: Create a NAS user</h2><p>Your storage is ready. Create a Samba account before setting up shared folders. Create a NAS user to unlock shared folders.</p><button class="btn outline" data-next="Users">View users</button></div>`;if(!(info.shares||[]).length)return `<div class="card wide setup-next"><h2>Next step: Create a share</h2><p>Storage and Samba users are detected. The Shares page is now available; Create a NAS share now and assign its user permissions.</p><button class="btn outline" data-next="Shares">View shares</button></div>`;return ''};const esc=s=>String(s??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));const size=n=>n?Number(n/1073741824).toFixed(1)+' GB':'—';const formatBytes=n=>{let i=0;while(n>=1024&&i<4){n/=1024;i++}return n.toFixed(i?1:0)+' '+['B','KB','MB','GB','TB'][i]};const post=async(path,data)=>{let r=await fetch(path,{method:'POST',headers:{'Content-Type':'application/json','X-PiNAS-CSRF':csrf},body:JSON.stringify(data)});let j=await r.json();if(!r.ok){if(r.status===403&&/authentication required|access required/i.test(j.error||''))returnToLogin();throw Error(j.error||'Request failed')}if(j.job_id){const jobId=j.job_id;for(let attempt=0;attempt<450;attempt++){await new Promise(resolve=>setTimeout(resolve,2000));const statusResponse=await fetch('/api/job?id='+encodeURIComponent(jobId),{cache:'no-store'});const status=await statusResponse.json();if(!statusResponse.ok)throw Error(status.error||'Job unavailable');if(!status.running){if(status.error)throw Error(status.error);return status.result}}throw Error('Operation is still running. Check job status before retrying.')}return j};async function signOut(button){
 if(button.disabled)return;
 button.disabled=true;
 try{
   await post('/api/logout',{});
   csrf='';
   // A full page navigation clears the old user view and requests fresh session state.
   window.location.replace('/');
 }catch(error){
   button.disabled=false;
   const status=document.getElementById('file-message')||document.getElementById('message');
   if(status)status.textContent='Unable to sign out: '+error.message;
   else alert('Unable to sign out: '+error.message);
 }
}async function init(){let r=await fetch('/api/state');let j=await r.json();cfg=j.settings||{};csrf=j.csrf||'';info=j.hardware||{};cpu=j.cpu||{};role=j.role||'admin';username=j.username||'';displayName=j.display_name||username;apply();if(!j.setup||!j.authenticated)login(!j.setup);else if(role==='user')renderFiles();else render();if(j.authenticated){lastUserAction=Date.now();lastActivitySync=lastUserAction;sessionRedirecting=false}};function apply(){let theme=cfg.theme==='dark'?'dark':'light';document.documentElement.dataset.theme=theme;document.documentElement.style.fontSize=(cfg.font||12)+'px';document.documentElement.style.setProperty('--login-image',cfg.has_background?"url('/api/background-image')":'none')};function login(setup){const proposed=info.suggested_hostname||'pinas';app.innerHTML=`<section class="login ${cfg.has_background?'loginbg':''}"><div class="card"><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>RASPBERRY PI NAS</small></div></div><h1>${setup?'Welcome to PiNAS':'Sign in'}</h1><p>${setup?'Name your NAS and create its administrator account.':'Manage your Raspberry Pi storage or access your files.'}</p><form id="auth">${setup?`<label class="field">NAS name / hostname<input name="hostname" required minlength="1" maxlength="63" pattern="[a-z][a-z0-9-]*[a-z0-9]|[a-z]" value="${esc(proposed)}" autocomplete="off"><span class="small">Your NAS will be reachable as <strong id="hostname-preview">${esc(proposed)}.local</strong> when local network discovery is available.</span></label>`:''}<label class="field">Username<input name="user" required value="${setup?'admin':''}" autocomplete="username"></label><label class="field">Password<input name="password" type="password" required minlength="${setup?12:1}" autocomplete="${setup?'new-password':'current-password'}"></label>${setup?'<label class="field">Confirm password<input name="confirm" type="password" required minlength="12" autocomplete="new-password"></label><p class="small">Use at least 12 characters. The administrator account is separate from Samba users.</p>':''}<button class="btn">${setup?'Create administrator':'Sign in'}</button><div id="message"></div></form></div></section>`;document.getElementById('auth').onsubmit=async e=>{e.preventDefault();let f=new FormData(e.target);if(setup&&f.get('password')!==f.get('confirm')){document.getElementById('message').textContent='Passwords do not match';return}try{await post(setup?'/api/setup':'/api/login',{user:f.get('user'),password:f.get('password'),...(setup?{hostname:String(f.get('hostname')||'').toLowerCase()}: {})});await init()}catch(err){document.getElementById('message').textContent=err.message}};if(setup){const nameInput=document.querySelector('#auth input[name="hostname"]'),preview=document.getElementById('hostname-preview');if(nameInput&&preview)nameInput.addEventListener('input',()=>{preview.textContent=(nameInput.value||'pinas').toLowerCase()+'.local'})}}function shell(body){const oldActive=document.querySelector('nav button.active');if(oldActive)lastNavRect=oldActive.getBoundingClientRect();app.innerHTML=`<header><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>RASPBERRY PI NAS</small></div></div><nav>${navItems().map(n=>`<button data-page="${n}" class="${n===page?'active':''}">${n}</button>`).join('')}<span class="nav-indicator" aria-hidden="true"></span></nav><button class="icon-btn" id="settings-trigger" aria-label="Settings" title="Settings">${SETTINGS_ICON}</button><button class="icon-btn" id="power-menu" aria-label="Device maintenance" title="Restart or shut down PiNAS"><svg viewBox="0 0 24 24" width="24" height="24" aria-hidden="true"><path d="M12 3v9m-5.8-6a9 9 0 1 0 11.6 0" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round"/></svg></button><button class="icon-btn" id="logout" aria-label="Sign out" title="Sign out">${LOGOFF_ICON}<span class="sr-only">Sign out</span></button></header><main>${body}<div class="footer"><span>PiNAS ${esc(info.version)}</span><span>${esc(info.hostname)} · ${esc(info.profile||'essential')} profile</span></div></main>`;const navEl=document.querySelector('nav'),activeNav=navEl.querySelector('button.active'),indicator=navEl.querySelector('.nav-indicator');if(activeNav){const navRect=navEl.getBoundingClientRect(),target=activeNav.getBoundingClientRect();let startX=target.left-navRect.left+navEl.scrollLeft,startW=target.width;if(lastNavRect){startX=lastNavRect.left-navRect.left+navEl.scrollLeft;startW=lastNavRect.width}indicator.style.transition='none';indicator.style.transform=`translateX(${startX}px)`;indicator.style.width=startW+'px';requestAnimationFrame(()=>{requestAnimationFrame(()=>{indicator.style.transition='';indicator.style.transform=`translateX(${target.left-navRect.left+navEl.scrollLeft}px)`;indicator.style.width=target.width+'px'})});lastNavRect=null}navEl.addEventListener('scroll',()=>{if(!activeNav)return;indicator.style.transition='none';indicator.style.transform=`translateX(${activeNav.offsetLeft}px)`;requestAnimationFrame(()=>indicator.style.transition='')},{passive:true});document.querySelectorAll('[data-page]').forEach(b=>b.onclick=()=>{page=b.dataset.page;render()});document.getElementById('settings-trigger').onclick=()=>openSettings();document.getElementById('power-menu').onclick=openPowerMenu;document.getElementById('logout').onclick=()=>signOut(document.getElementById('logout'))};
function openPowerMenu(){
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML='<section class="card settings-modal file-dialog" role="dialog" aria-modal="true" aria-label="Device maintenance" tabindex="-1">'+
  '<div class="modal-heading"><h2>Device maintenance</h2><button class="icon-btn" id="power-close" aria-label="Close">'+CANCEL_ICON+'</button></div>'+
  '<p>Restart or shut down the Raspberry Pi. Active SMB transfers and media playback will be disconnected.</p>'+
  '<div class="modal-actions"><button type="button" class="btn outline" id="power-cancel">Cancel</button>'+
  '<button type="button" class="btn outline" id="power-reboot">Restart PiNAS</button>'+
  '<button type="button" class="btn danger" id="power-shutdown">Shut down PiNAS</button></div></section>';
 document.body.append(overlay);
 const dismiss=()=>{document.removeEventListener('keydown',key);overlay.remove()};
 const key=e=>{if(e.key==='Escape'){e.preventDefault();dismiss()}};
 document.addEventListener('keydown',key);
 overlay.querySelector('#power-close').onclick=dismiss;
 overlay.querySelector('#power-cancel').onclick=dismiss;
 overlay.addEventListener('click',e=>{if(e.target===overlay)dismiss()});
 for(const action of ['reboot','shutdown']){
  overlay.querySelector('#power-'+action).onclick=async()=>{
   dismiss();
   const label=action==='reboot'?'Restart':'Shut down';
   const password=await fileTextDialog({
    title:label+' PiNAS',label:'Administrator password',password:true,
    confirmLabel:label+' device',
    description:'Confirm '+label.toLowerCase()+' of this Raspberry Pi. Network shares, downloads and active applications will disconnect. The command will begin 8 seconds after confirmation.'
   });
   if(password===null)return;
   try{
    const result=await post('/api/power',{action,admin_password:password,confirm:true});
    const message=document.createElement('div');message.className='modal-overlay';
    message.innerHTML='<section class="card settings-modal file-dialog" role="status" aria-live="polite"><h2>'+
      (action==='reboot'?'Restart scheduled':'Shutdown scheduled')+'</h2><p>'+
      (action==='reboot'?'PiNAS is restarting. Reconnect when the device is available.':
       'PiNAS is shutting down. Power the Raspberry Pi back on manually when needed.')+'</p></section>';
    document.body.append(message);
   }catch(err){
    const message=document.getElementById('disk-health-message')||document.getElementById('disk-health-storage-message');
    if(message)message.textContent='Device maintenance failed: '+err.message;
    else alert('Device maintenance failed: '+err.message);
   }
  };
 }
 overlay.querySelector('#power-reboot').focus();
}

function ring(percent,center,label,color){let r=52,c=2*Math.PI*r,p=Math.max(0,Math.min(100,percent));return `<svg class="ring" viewBox="0 0 150 150" role="img" aria-label="${esc(label)}: ${esc(center)}"><circle cx="75" cy="75" r="${r}" stroke="var(--soft)" stroke-width="13" fill="none"/><circle cx="75" cy="75" r="${r}" stroke="${color}" stroke-width="13" fill="none" stroke-linecap="round" stroke-dasharray="${(p*c/100).toFixed(1)} ${c.toFixed(1)}" transform="rotate(-90 75 75)"/><text x="75" y="73" fill="var(--ink)" font-size="25" font-weight="700" text-anchor="middle">${esc(center)}</text><text x="75" y="92" fill="var(--muted)" font-size="11" text-anchor="middle">${esc(label)}</text></svg>`}
function drawCPU(){let target=document.getElementById('cpu-chart');if(!target)return;let samples=cpu.samples||[],minutes=cfg.cpu_history||10,now=Date.now()/1000,points=samples.filter(p=>p[0]>=now-minutes*60),max=Math.max(0,...points.map(p=>p[1]));let coords=points.map(p=>[8+((p[0]-(now-minutes*60))/(minutes*60))*624,108-p[1]]);let path=coords.map((p,i)=>`${i?'L':'M'}${p[0].toFixed(1)} ${p[1].toFixed(1)}`).join(' ');target.innerHTML=`<svg viewBox="0 0 640 136" preserveAspectRatio="none" aria-hidden="true"><path d="M8 8H632 M8 58H632 M8 108H632" stroke="var(--line)" stroke-dasharray="4 5" fill="none"/>${coords.length>1?`<path d="${path}" stroke="var(--accent)" stroke-width="2.5" fill="none" stroke-linejoin="round" stroke-linecap="round"/>`:''}</svg>`;document.getElementById('cpu-current').textContent=(cpu.current??0).toFixed(1)+'%';document.getElementById('cpu-peak').textContent=max.toFixed(1)+'%';target.title=points.length?`${points.length} CPU samples; peak ${max.toFixed(1)}%`:'Waiting for CPU samples'}
async function refreshOverview(){if(!['Overview','Storage','RAID'].includes(page)||!csrf||role!=='admin')return;try{let r=await fetch('/api/state',{cache:'no-store'});if(!r.ok)return;let j=await r.json();if(!j.authenticated){returnToLogin();return}const before=navItems().join('|')+'|'+storageReady()+'|'+(info.shares||[]).length;info=j.hardware||info;cpu=j.cpu||cpu;const after=navItems().join('|')+'|'+storageReady()+'|'+(info.shares||[]).length;if(before!==after){render();return}if(page==='Overview')updateOverview()}catch(e){/* transient connectivity */}}
setInterval(refreshOverview,10000);
function uptimeText(seconds){if(seconds==null)return 'Unavailable';let days=Math.floor(seconds/86400),hours=Math.floor(seconds%86400/3600),mins=Math.floor(seconds%3600/60);return days?`${days}d ${hours}h`:hours?`${hours}h ${mins}m`:`${mins}m`}

let diskSmartSnapshot=null;
let diskSmartBusy=false;
function displayDiskHealth(){
 const snapshot=diskSmartSnapshot;
 const entries=new Map((snapshot?.drives||[]).filter(d=>typeof d.device==='string').map(d=>[d.device,d]));
 document.querySelectorAll('[data-smart-device]').forEach(panel=>{
  const drive=entries.get(panel.dataset.smartDevice);
  const status=panel.querySelector('[data-smart-status]'),temperature=panel.querySelector('[data-smart-temp]');
  if(!status||!temperature)return;
  const health=!snapshot?'Not checked':!snapshot.installed?'SMART unavailable':drive?.status||'Unavailable';
  status.textContent=health;
  status.classList.toggle('disk-health-good',health==='Healthy');
  status.classList.toggle('disk-health-warning',health==='Warning');
  temperature.textContent=drive&&typeof drive.temperature==='number'?drive.temperature+'°C':'—';
  const detail=panel.querySelector('[data-smart-detail]');if(detail)detail.textContent=drive?.message||'';
 });
}
let diskSmartLastChecked=0,diskSmartLastPage='',diskSmartLastMessage='';
function diskSmartMessage(message){
 diskSmartLastMessage=message;
 const el=document.getElementById(page==='Storage'?'disk-health-storage-message':'disk-health-message');
 if(el)el.textContent=message;
}
async function checkSmartHealth(){
 if(!['Overview','Storage'].includes(page)||diskSmartBusy)return;
 diskSmartBusy=true;diskSmartLastChecked=Date.now();
 diskSmartMessage('Checking drive health…');
 try{
  const response=await fetch('/api/smart-health',{cache:'no-store'});
  const result=await response.json();
  if(!response.ok){if(response.status===403)returnToLogin();throw Error(result.error||'SMART check failed')}
  diskSmartSnapshot=result;
  displayDiskHealth();
  diskSmartMessage(!result.installed?'SMART Tools are not installed. To enable checks: sudo apt install smartmontools':
   !(result.drives||[]).length?'No SMART-compatible physical drives detected.':
   'SMART health checked automatically. Standby drives remain asleep; some USB adapters may not report health or temperature.');
 }catch(error){diskSmartMessage('Unable to read disk health: '+error.message)}
 finally{diskSmartBusy=false}
}
function autoDiskHealth(){
 if(!['Overview','Storage'].includes(page))return;
 displayDiskHealth();
 if(diskSmartLastMessage)diskSmartMessage(diskSmartLastMessage);
 if(diskSmartLastPage!==page||Date.now()-diskSmartLastChecked>=600000){
  diskSmartLastPage=page;
  checkSmartHealth();
 }
}
setInterval(()=>{if(['Overview','Storage'].includes(page)&&Date.now()-diskSmartLastChecked>=600000)checkSmartHealth()},60000);

async function restartAutomaticUpdate(unit){
 const description=unit==='service'?'This will start an automatic APT upgrade now. Services may temporarily restart.':'This will restart the automatic-update timer with its saved schedule.';
 const password=await fileTextDialog({title:'Restart automatic updates',label:'Administrator password',description,confirmLabel:'Restart',password:true});
 if(password===null)return;
 try{
  await post('/api/updates',{action:'restart-auto',unit,admin_password:password});
  if(page==='Overview')await refreshServiceHealth();
  if(page==='Updates')await loadUpdateUnitHealth();
 }catch(error){
  const target=document.getElementById(page==='Updates'?'update-unit-health':'service-health-warnings');
  if(target)target.textContent='Unable to restart automatic updates: '+error.message;
 }
}
function bindUpdateRestartActions(root){
 if(root)root.querySelectorAll('[data-restart-auto]').forEach(button=>button.onclick=()=>restartAutomaticUpdate(button.dataset.restartAuto));
}
async function loadUpdateUnitHealth(){
 const panel=document.getElementById('update-unit-health');if(!panel)return;
 panel.textContent='Checking automatic update units…';
 try{
  const response=await fetch('/api/service-health',{cache:'no-store'}),result=await response.json();
  if(!response.ok)throw Error(result.error||'Service health unavailable');
  panel.innerHTML=(result.services||[]).filter(s=>['pinas-auto-updates.timer','pinas-auto-updates.service'].includes(s.unit)).map(s=>
   `<div class="line"><div><strong>${esc(s.name)}</strong><span class="small">${esc(s.detail)}</span></div><div class="update-unit-action"><span class="pill ${s.state==='healthy'?'good':''}">${esc(s.state)}</span>${s.restart_action?`<button class="btn outline" data-restart-auto="${esc(s.restart_action)}">Restart</button>`:''}</div></div>`).join('');
  bindUpdateRestartActions(panel);
 }catch(error){panel.textContent='Update service status unavailable: '+error.message}
}
async function refreshServiceHealth(){
    const target=document.getElementById('service-health-results');
    const notices=document.getElementById('service-health-warnings');
    const button=document.getElementById('refresh-service-health');
    if(!target||!notices)return;
    if(button)button.disabled=true;
    target.textContent='Checking services…';
    try{
        const response=await fetch('/api/service-health',{cache:'no-store'});
        const data=await response.json();
        if(!response.ok)throw Error(data.error||'Service health unavailable');
        const stateText={healthy:'Running',warning:'Attention',inactive:'Stopped','not-installed':'Not installed',pending:'Starting',unknown:'Unavailable'};
        target.innerHTML=(data.services||[]).map(s=>'<div class="line"><div><strong>'+esc(s.name)+'</strong><span class="small">'+esc(s.unit)+'</span></div><div class="update-unit-action"><span class="pill '+(s.state==='healthy'?'good':'')+'">'+esc(stateText[s.state]||'Unavailable')+'</span><span class="small">'+esc(s.detail)+'</span>'+(s.restart_action?'<button class="btn outline" type="button" data-restart-auto="'+esc(s.restart_action)+'">Restart</button>':'')+'</div></div>').join('');bindUpdateRestartActions(target);
        notices.innerHTML=(data.warnings||[]).length?'<h3>System messages</h3>'+(data.warnings||[]).map(w=>'<p class="small"><strong>'+esc(w.name)+':</strong> '+esc(w.message)+'</p>').join(''):'';
    }catch(error){target.textContent='Unable to check services: '+error.message;notices.textContent=''}finally{if(button)button.disabled=false}
}
function updateHealth(){const uptime=document.getElementById('health-uptime'),os=document.getElementById('health-os'),kernel=document.getElementById('health-kernel');if(uptime)uptime.textContent=uptimeText(info.uptime_seconds);if(os)os.textContent=info.os_name||'Unavailable';if(kernel)kernel.textContent=info.kernel||'Unavailable'}
function updateOverview(){if(page!=='Overview')return;let disksCount=(info.disks||[]).filter(d=>d.type==='disk').length;for(let [id,value] of [['count-disks',disksCount],['count-shares',info.shares?.length||0],['count-users',info.nas_users??'—']]){let el=document.getElementById(id);if(el)el.textContent=value}let mem=info.memory_total||1,used=info.memory_used||0,temp=info.temperature;let a=document.getElementById('memory-ring'),b=document.getElementById('temp-ring');if(a)a.innerHTML=ring(Math.round(100*used/mem),Math.round(100*used/mem)+'%','Used','var(--accent)')+`<p class="small">${size(used)} / ${size(mem)}</p>`;if(b)b.innerHTML=ring(temp??0,temp==null?'—':temp+'°C','Temperature',temp>=75?'var(--danger)':temp>=65?'var(--warning)':'var(--success)')+`<p class="small">${temp==null?'Unavailable':temp>=75?'High temperature':temp>=65?'Elevated temperature':'Normal temperature'}</p>`;drawCPU();updateHealth()} 
const head=(name,desc)=>`<h1>${name}</h1><p class="subtitle">${desc}</p>`;const disks=()=>(info.disks||[]).filter(d=>d.type==='disk'&&!/^(zram|ram|loop|nbd|sr|fd)\d*/i.test(d.name||'')&&!/^\/dev\/(zram|ram|loop)/i.test(d.path||''));
// Count only writable data disks that could be selected by the RAID planner.
const raidEligibleDisks=()=>disks().filter(d=>!d.read_only&&Number(d.size)>0);
// Keep existing arrays visible for health monitoring if a member disconnects.
const raidPageAvailable=()=>raidEligibleDisks().length>=2||(info.raid||[]).length>0;
function storageSafetyWarnings(){
 const problems=(info.managed_storage_health||[]).filter(item=>item.state!=='mounted');
 const arrayProblems=(info.raid||[]).filter(item=>Number(item.degraded||0)>0);
 if(!problems.length&&!arrayProblems.length)return '';
 const mounted=problems.map(item=>{const status=item.state==='missing'?'Device missing':item.state==='mismatch'?'Unexpected filesystem mounted':'Not mounted';return `<p class="small"><strong>${esc(status)}</strong> · ${esc(item.mount)} (${esc(item.filesystem)}) · UUID ${esc(item.uuid)}</p>`}).join('');
 const raids=arrayProblems.map(item=>`<p class="small"><strong>RAID degraded</strong> · ${esc(item.name)} · ${esc(item.degraded)} missing/failed member(s)</p>`).join('');
 return `<div class="card storage-safety-warning" role="alert"><h2>Storage needs attention</h2><p class="small">A configured data filesystem or RAID array is not healthy. Check connections and mounts before writing new files. PiNAS will not automatically format, repair, or mount these devices.</p>${mounted}${raids}</div>`;
}

let mediaBreakdownTimer=null;
const MEDIA_STORAGE_TYPES=[
 ['video','Video','media-video'],['pictures','Pictures','media-pictures'],
 ['music','Music','media-music'],['other','Other / filesystem','media-other']
];
function diskSummary(){
 return disks().map(d=>{
  const fs=d.filesystems||[],total=fs.reduce((a,f)=>a+(f.total||0),0),used=fs.reduce((a,f)=>a+(f.used||0),0),pct=total?Math.min(100,Math.round(used/total*100)):0;
  return '<div class="disk-summary"><div class="disk-heading"><strong>'+esc(d.model||d.name||'Attached disk')+'</strong><span class="small">'+
   (total?size(used)+' used · '+size(Math.max(0,total-used))+' available':'Usage unavailable')+'</span></div>'+
   '<div class="bar disk-usage" role="progressbar" aria-label="'+esc(d.model||d.name||'Disk')+' space used" aria-valuemin="0" aria-valuemax="100" aria-valuenow="'+pct+'"><i style="width:'+pct+'%"></i></div>'+ 
   '<div class="disk-smart-meta" data-smart-device="'+esc(d.path||'')+'"><span class="small">Health: <strong data-smart-status>Not checked</strong></span><span class="small">Temperature: <strong data-smart-temp>—</strong></span><span class="small" data-smart-detail></span></div></div>';
 }).join('')||'<p class="small">No attached data disks detected.</p>';
}
function storageScanPanels(d){
 const mounts=[...new Set((d.volumes||[]).filter(v=>v.persistent)
    .flatMap(v=>v.mounts||[]).filter(m=>/^\/mnt\/pinas\/[^/]+$/.test(m)))];
 if(!mounts.length)return '<p class="hint">File Type Scan requires a configured, mounted PiNAS data volume.</p>';
 return mounts.map(m=>'<section class="storage-file-types" data-file-type-mount="'+esc(m)+'"><div class="line"><div><strong>File Type Scan</strong><span class="small">'+esc(m)+'</span></div><button type="button" class="btn outline button-with-icon" data-scan-volume="'+esc(m)+'">'+NAS_ACTION_ICONS.scan+'<span>Scan file types</span></button></div>'+
   '<p class="hint" data-scan-status role="status">Not scanned. Runs only when requested.</p><div data-scan-chart></div></section>').join('');
}
function renderScanResult(panel,report){
 const message=panel.querySelector('[data-scan-status]'),chart=panel.querySelector('[data-scan-chart]');
 if(!message||!chart)return;
 if(!report||(!report.categories&&!report.running&&!report.error)){
  message.textContent='Not scanned. Select Scan file types to analyse this volume.';chart.replaceChildren();return;
 }
 message.textContent=report.running?'Scanning file metadata in the background; this may take time on large disks…':
    report.error?'Scan failed: '+report.error:
    'Last scan: '+new Date(report.scanned_at*1000).toLocaleString()+' · '+(report.files||0).toLocaleString()+' files'+
    (report.skipped_dirs?' · '+report.skipped_dirs+' paths could not be read':'')+'.';
 const parts=report.categories;
 if(!parts){chart.replaceChildren();return}
 const mount=panel.dataset.fileTypeMount;
 const disk=disks().find(d=>(d.volumes||[]).some(v=>(v.mounts||[]).includes(mount)));
 const fs=disk?.filesystems?.find(f=>f.mount===mount);
 const total=fs?.total||0,used=fs?.used||0;
 const types={...parts};
 const known=['video','pictures','music'].reduce((n,k)=>n+(types[k]||0),0);
 if(used&&known>used){const factor=used/known;for(const k of ['video','pictures','music'])types[k]*=factor}
 types.other=Math.max(0,used-(types.video||0)-(types.pictures||0)-(types.music||0));
 const segments=MEDIA_STORAGE_TYPES.map(([key,label,cls])=>
   '<span class="media-segment '+cls+'" style="width:'+(total?100*Math.max(0,types[key]||0)/total:0)+'%" title="'+esc(label)+' · '+size(types[key])+'"></span>').join('');
 chart.innerHTML='<div class="bar disk-usage storage-scan-bar" role="img" aria-label="Used storage by file type">'+segments+'</div>'+
  '<div class="media-legend">'+MEDIA_STORAGE_TYPES.map(([key,label,cls])=>'<span><i class="'+cls+'"></i>'+esc(label)+': '+size(types[key])+'</span>').join('')+
  '<span><i class="media-free"></i>Free: '+size(Math.max(0,total-used))+'</span></div>';
}
async function readFileTypeStatus(mount){
 try{
  const response=await fetch('/api/media-breakdown?mount='+encodeURIComponent(mount),{cache:'no-store'});
  const result=await response.json();
  if(!response.ok)throw Error(result.error||'Scan unavailable');
  const panel=[...document.querySelectorAll('[data-file-type-mount]')].find(e=>e.dataset.fileTypeMount===mount);
  if(panel)renderScanResult(panel,result);
  return result;
 }catch(err){
  const panel=[...document.querySelectorAll('[data-file-type-mount]')].find(e=>e.dataset.fileTypeMount===mount);
  if(panel)renderScanResult(panel,{error:err.message});
  return null;
 }
}
async function scanFileTypes(mount){
 const panel=[...document.querySelectorAll('[data-file-type-mount]')].find(e=>e.dataset.fileTypeMount===mount);
 if(!panel)return;
 const button=panel.querySelector('[data-scan-volume]');if(button)button.disabled=true;
 try{
  await post('/api/media-breakdown',{action:'refresh',mount});
  await watchFileTypeScan(mount);
 }catch(err){
  renderScanResult(panel,{error:err.message});if(button)button.disabled=false;
 }
}
async function watchFileTypeScan(mount){
 const result=await readFileTypeStatus(mount);
 const panel=[...document.querySelectorAll('[data-file-type-mount]')].find(e=>e.dataset.fileTypeMount===mount);
 if(!panel)return;
 const button=panel.querySelector('[data-scan-volume]');
 if(button)button.disabled=!!result?.running;
 if(mediaBreakdownTimer){clearTimeout(mediaBreakdownTimer);mediaBreakdownTimer=null}
 if(result?.running&&page==='Storage')mediaBreakdownTimer=setTimeout(()=>watchFileTypeScan(mount),3000);
}
function bindStorageScans(){
 document.querySelectorAll('[data-scan-volume]').forEach(button=>{
  const mount=button.dataset.scanVolume;button.onclick=()=>scanFileTypes(mount);
  readFileTypeStatus(mount).then(result=>{if(result?.running)watchFileTypeScan(mount)});
 });
}

function render(){if(!navItems().includes(page))page='Overview';let body='';if(page==='Media Server'){body=head('Media Server','Share photos, music and videos with DLNA-capable devices.')+'<div class="card"><h2>MiniDLNA / ReadyMedia</h2><div id="media-server-panel" role="status">Checking installation…</div></div>';}else if(page==='Overview'){let used=info.memory_used||0,total=info.memory_total||1,pct=Math.min(100,Math.round(100*used/total)),temp=info.temperature,disksCount=disks().filter(d=>d.type==='disk').length;body=head('Overview','Your Raspberry Pi NAS at a glance.')+`<div class="grid overview">`+setupNotice()+storageSafetyWarnings()+`<div class="card wide"><div class="chart-title storage-summary-heading"><h2>Storage at a glance</h2></div>${diskSummary()}<p class="small" id="disk-health-message" role="status">SMART health and temperature are checked automatically.</p></div><div class="card wide"><div class="chart-title"><h2>CPU Activity</h2><span class="pill">Last ${cfg.cpu_history||10} minutes</span></div><div id="cpu-chart" class="cpu-chart" role="img" aria-label="CPU activity history"></div><div class="chart-footer"><div><div class="label">Current CPU</div><div class="big" id="cpu-current">—</div></div><div><div class="label">Peak in view</div><div class="big" id="cpu-peak">—</div></div></div></div><div class="card metric"><h2>Memory</h2><div id="memory-ring">${ring(pct,pct+'%','Used','var(--accent)')}<p class="small">${size(used)} / ${size(total)}</p></div></div><div class="card metric"><h2>CPU Temperature</h2><div id="temp-ring">${ring(temp==null?0:Math.min(100,temp),temp==null?'—':temp+'°C','Temperature',temp!=null&&temp>=75?'var(--danger)':temp!=null&&temp>=65?'var(--warning)':'var(--success)')}<p class="small">${temp==null?'Unavailable':temp>=75?'High temperature':temp>=65?'Elevated temperature':'Normal temperature'}</p></div></div><div class="card overview-counts"><h2>NAS Overview</h2><div class="overview-summary"><div class="stat clickable" role="button" tabindex="0" data-jump="Storage"><div class="label">Attached disks</div><div class="big" id="count-disks">${disksCount}</div><span class="small">Physical drives</span></div><div class="stat clickable" role="button" tabindex="0" data-jump="Shares"><div class="label">Network shares</div><div class="big" id="count-shares">${info.shares?.length||0}</div><span class="small">Samba shares</span></div><div class="stat clickable" role="button" tabindex="0" data-jump="Users"><div class="label">NAS users</div><div class="big" id="count-users">${info.nas_users??'—'}</div><span class="small">Samba accounts</span></div></div></div><div class="card wide"><h2>System health</h2><div class="health-grid"><div><span class="label">Device</span><strong>${esc(info.model)}</strong></div><div><span class="label">Hostname</span><strong>${esc(info.hostname)}</strong></div><div><span class="label">Throttling</span><strong>${esc(info.throttle||"Unavailable")}</strong></div><div><span class="label">Uptime</span><strong id="health-uptime">${uptimeText(info.uptime_seconds)}</strong></div><div><span class="label">Operating system</span><strong id="health-os">${esc(info.os_name||'Unavailable')}</strong></div><div><span class="label">Kernel</span><strong id="health-kernel">${esc(info.kernel||'Unavailable')}</strong></div></div><p class="small">System information is read directly from Linux and refreshed with the Overview page. No additional monitoring service is required.</p></div><div class="card wide"><div class="chart-title"><h2>NAS service health</h2><button class="btn outline button-with-icon action-icon-btn" id="refresh-service-health" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M20.62 7.9c-3.12-4.09-6.2-4.86-8.67-4.86a9.08 9.08 0 1 0 6.36 15.55"/><path d="M21.4 2.77v2.02c0 1.89 0 2.83-.58 3.42s-1.53.59-3.41.59h-2.03"/></g></svg><span>Refresh</span></button></div><div id="service-health-warnings" role="status"></div><div id="service-health-results" role="status">Checking services…</div></div></div>`}else if(page==='Storage'){body=head('Storage','Your attached data drives. System storage and swap devices are excluded.')+storageSafetyWarnings()+`<div class="card"><div class="line"><h2>Detected drives</h2></div><p class="small" id="disk-health-storage-message" role="status">SMART health checks run automatically; standby disks are not woken.</p>${disks().map((d,i)=>{const vs=d.volumes||[],v=vs.find(x=>x.mounts?.length)||vs[0],fs=[...new Set(vs.map(x=>x.fs).filter(Boolean))],mounts=vs.flatMap(x=>x.mounts||[]),persistent=vs.some(x=>x.persistent);return `<div class="storage-disk-entry"><div class="disk-properties"><div><span>Name:</span><strong>${esc(d.model||d.name||'Attached drive')}</strong></div><div><span>Capacity:</span><strong>${size(d.size)}</strong></div><div><span>File System:</span><strong>${esc(fs.join(', ')||'None detected')}</strong></div><div><span>Mount Status:</span><strong>${mounts.length?'Mounted':'Not mounted'}</strong></div><div><span>Mount Point:</span><strong>${esc(mounts.join(', ')||'—')}</strong></div><div><span>Persistent Mount:</span><strong>${persistent?'Yes':'No'}</strong></div></div><button class="btn outline button-with-icon action-icon-btn storage-action" data-disk="${i}" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><ellipse cx="12" cy="5.23" fill="currentColor" opacity=".2" rx="8.88" ry="3.44" transform="rotate(-180 12 5.23)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M20.88 5.23v13.73"/><path fill="currentColor" d="M3.25 16.32c0-1.15 0-1.72.38-2.02c.37-.3.93-.18 2.04.06l5.95 1.27c.21.05.31.07.42.07s.21-.02.42-.06l6.02-1.28c1.12-.24 1.68-.36 2.05-.06s.37.87.37 2.01v2.19c0 .75 0 1.13-.22 1.4c-.2.27-.58.36-1.3.54l-6.86 1.68c-.24.05-.36.08-.48.08s-.24-.03-.48-.09l-6.78-1.67c-.73-.18-1.1-.27-1.31-.54c-.22-.27-.22-.65-.22-1.4z" opacity=".2"/><ellipse cx="12" cy="5.23" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="8.88" ry="3.44" transform="rotate(-180 12 5.23)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.12 11.95c0 1.87 3.98 3.38 8.88 3.38s8.88-1.51 8.88-3.38"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.06 11.3c.4.26 1.15.59 2.2.8c1.17.22 1.74.25 2.67.25m-4.87 5.31c.4.25 1.15.58 2.2.79c1.17.23 1.74.26 2.67.26m-7.81.12c0 1.87 3.98 3.38 8.88 3.38s8.88-1.51 8.88-3.38M3.12 5.23v13.38"/></g></svg><span>Manage Disk</span></button></div><div class="disk-smart-meta" data-smart-device="${esc(d.path||'')}"><span class="small">Health: <strong data-smart-status>Not checked</strong></span><span class="small">Temperature: <strong data-smart-temp>—</strong></span><span class="small" data-smart-detail></span></div>${storageScanPanels(d)}`}).join('')||'<p>No attached data drives detected. System disks and zram swap are intentionally hidden.</p>'}</div><p class="hint">Existing filesystems can be adopted without formatting. Wiping and formatting require administrator confirmation. Back up important data first.</p>`}else if(page==='RAID'){const arrays=info.raid||[];body=head('Software RAID','Discover and monitor Linux mdadm arrays. RAID creation remains protected.')+storageSafetyWarnings()+`<div class="card"><h2>Existing RAID arrays</h2>${arrays.map(r=>{const degraded=Number(r.degraded||0),healthy=r.state==='clean'||r.state==='active',status=degraded?'Degraded':healthy?'Healthy':'Check status';return `<div class="raid-array-entry"><div class="line"><div><strong>${esc(r.name)} · ${esc(r.level)}</strong><span class="small">${esc(r.state||'Unknown')} · ${r.raid_disks??'—'} expected members · ${r.members?.length??0} detected</span></div><span class="pill ${!degraded&&healthy?'good':''}">${status}</span></div><div class="disk-properties"><div><span>Sync activity:</span><strong>${esc(r.sync||'Unknown')}</strong></div><div><span>Degraded members:</span><strong>${degraded}</strong></div><div><span>Metadata:</span><strong>${esc(r.metadata||'—')}</strong></div></div>${r.progress!=null&&r.sync!=='idle'?`<div class="small">${esc(r.sync)}: ${r.progress}%</div><div class="progress-track"><div class="progress-fill" style="width:${Math.min(100,Math.max(0,r.progress))}%"></div></div>`:''}${(r.members||[]).map(m=>`<div class="line"><span>${esc(m.device)} · Slot ${esc(m.slot||'—')}</span><span class="small">${esc(m.state)}</span></div>`).join('')||'<p class="hint">No members reported by the kernel.</p>'}</div>`}).join('')||'<p>No mdadm arrays detected. You can review the RAID planner without changing any disks.</p>'}<button class="btn outline button-with-icon action-icon-btn" id="raid-create" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><ellipse cx="12" cy="5.23" fill="currentColor" opacity=".2" rx="8.88" ry="3.44" transform="rotate(-180 12 5.23)"/><path fill="currentColor" d="M3.25 16.32c0-1.15 0-1.72.38-2.02c.37-.3.93-.18 2.04.06l5.87 1.26c.25.05.37.08.5.07s.25-.04.5-.11l8.18-2.46v5.65c0 .65 0 .98-.18 1.24c-.19.26-.48.36-1.08.57c-1.75.63-5 1.65-7.42 1.65c-2.46 0-5.76-1.05-7.54-1.69c-.59-.2-.88-.32-1.06-.57c-.19-.26-.19-.59-.19-1.24z" opacity=".2"/><ellipse cx="12" cy="5.23" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="8.88" ry="3.44" transform="rotate(-180 12 5.23)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M3.12 11.95c0 1.87 3.98 3.38 8.88 3.38s8.88-1.51 8.88-3.38"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.06 11.3c.4.26 1.15.59 2.2.8c1.17.22 1.74.25 2.67.25m-4.87 5.31c.4.25 1.15.58 2.2.79c1.17.23 1.74.26 2.67.26m-7.81.12c0 1.87 3.98 3.38 8.88 3.38a9 9 0 0 0 2.2-.24m6.68-16.23v6.15M3.12 5.74V18.6m14.31 1h5.2m-2.6 2.6V17"/></g></svg><span>Configure RAID</span></button></div><p class="hint">This release is monitoring-only. RAID creation, deletion and member replacement remain disabled until device safeguards and recovery workflows have been tested. RAID is not a backup.</p>`}else if(page==='Shares'){body=head('Network shares','Manage shared folders and their access permissions.')+`<div class="card"><h2>Configured network shares</h2><div class="share-top-actions"><button class="btn outline icon-btn share-icon-btn" id="create-nas-share" title="Create share" aria-label="Create share">${CREATE_SHARE_ICON}</button></div>${(info.shares||[]).map(s=>{const d=(info.share_details||[]).find(x=>x.name===s);const perms=d?.public?(d.public_write?'Public | Read & Write':'Public | Read Only'):d?Object.entries(d.access||{}).map(([u,p])=>esc(u)+' | '+(p==='rw'?'Read & Write':'Read Only')).join(', '):'Unavailable';return `<div class="line share-entry"><div class="share-meta"><div><strong>Name:</strong> <span>${esc(s)}</span></div><div><strong>Location:</strong> <span>${esc(d?.folder||'Unavailable')}</span></div><div><strong>Permissions:</strong> <span>${perms}</span></div><div><strong>Type:</strong> <span>SMB</span></div></div><div class="share-actions">${d?.folder?.includes("/PiNAS Shares/")?`<button type="button" class="btn outline" data-migrate-share="${esc(s)}" title="Move legacy share folder to pinas-shares">Move folder</button>`:""}<button class="btn outline" data-stop-share="${esc(s)}" title="${d?'Stop network sharing and preserve this folder':'External share — not managed by PiNAS'}" ${d?'':'disabled'}>Stop Sharing</button><button class="btn outline button-with-icon delete-folder-action" data-delete-folder="${esc(s)}" title="${d?'Permanently delete this share folder and all of its contents':'External share — not managed by PiNAS'}" aria-label="Delete Folder ${esc(s)}" ${d?'':'disabled'}>${DELETE_FOLDER_ICON}<span>Delete Folder</span></button><button class="btn outline icon-btn share-icon-btn" data-edit-share="${esc(s)}" title="${d?'Edit share':'External share — not managed by PiNAS'}" aria-label="Edit share ${esc(s)}" ${d?'':'disabled'}>${EDIT_SHARE_ICON}</button><button class="btn outline" data-repair-share="${esc(s)}" title="${d?'Reapply existing share ACLs to files and folders':'PiNAS-managed shares only'}" ${d?'':'disabled'}>Repair access</button></div></div>`}).join('')||'<p>No network shares detected.</p>'}</div><p class="hint">Stop Sharing removes SMB access but preserves the folder and all its contents. Delete Folder permanently deletes a PiNAS-managed share folder and all contents; administrator re-authentication and explicit confirmation are required. Editing a share changes its network name or access permissions without moving its folder.</p>`} else if(page==='Users'){body=head('User Management','Manage PiNAS administrators and NAS users.')+`<div class="user-top-actions"><button class="btn outline add-user-button" id="add-nas-user">${ADD_USER_ICON}<span>Add New User</span></button><button class="btn outline add-user-button" id="add-admin-user">${ADD_USER_ICON}<span>Add Admin User</span></button></div><div class="user-management-cards"><div class="card"><h2>Administrators</h2><p>Accounts authorised to manage PiNAS settings and storage.</p>${(info.admin_user_list||[]).map(u=>`<div class="line"><div><strong>${esc(u.display_name||u.name)}</strong><span class="small">@${esc(u.name)}</span></div><div class="user-row-actions"><button class="btn outline edit-user-button" data-edit-admin="${esc(u.name)}">${EDIT_USER_ICON}<span>Edit User</span></button>${u.name!==username&&u.name!==(info.admin_user_list||[])[0]?.name?`<button class="btn outline edit-user-button" data-remove-admin="${esc(u.name)}" title="Remove administrator ${esc(u.name)}">${REMOVE_USER_ICON}<span>Remove User</span></button>`:""}</div></div>`).join('')||'<p>No administrator accounts listed.</p>'}</div><div class="card"><h2>Users</h2><p>NAS accounts for accessing shared folders. Share permissions are managed from the Shares page.</p>${(info.nas_user_list||[]).map(u=>`<div class="line"><div><strong>${esc(u.display_name||u.name)}</strong><span class="small">@${esc(u.name)}</span></div><div class="user-row-actions"><button class="btn outline edit-user-button" data-edit-nas="${esc(u.name)}">${EDIT_USER_ICON}<span>Edit User</span></button><button class="btn outline edit-user-button" data-remove-nas="${esc(u.name)}" title="Remove NAS user ${esc(u.name)}">${REMOVE_USER_ICON}<span>Remove User</span></button></div></div>`).join('')||'<p>No NAS users configured yet.</p>'}</div></div>`}else if(page==='Updates'){body=head('System Updates','Raspberry Pi OS and Debian package updates. PiNAS application updates are managed separately.')+`<div class="card"><h2>OS Updates</h2><div class="updates-actions"><button class="btn outline button-with-icon" id="check-os-updates"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12.46 6H2.65m9.81 6H2.65m9.81 6H2.65M16.23 7.21l.88 1.08c.36.44.54.66.78.66s.41-.22.77-.67l2.72-3.35"/><rect width="5.15" height="5.15" fill="currentColor" opacity=".2" rx="1.5" transform="matrix(0 -1 -1 0 21.38 18.04)"/><rect width="5.15" height="5.15" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="1.5" transform="matrix(0 -1 -1 0 21.38 18.04)"/></g></svg><span>Check for updates</span></button><button class="btn outline button-with-icon" id="install-os-updates"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M13.65 6H2.61m11.04 6H2.61m11.04 6H2.61M17.13 6.1l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7m-4.35 7.93l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7m-4.35 7.93l.62.77c.36.44.54.66.78.66s.42-.22.77-.66l2.18-2.7"/></svg><span>Install updates</span></button></div><div class="updates-status-row"><div id="updates-message" role="status">Loading available updates…</div><span id="updates-spinner" class="updates-spinner" role="img" aria-label="Update operation in progress" hidden></span></div><div id="firmware-update-status" class="small" role="status"></div><div id="updates-list"></div><div class="update-reboot-panel" id="update-reboot-panel" hidden><p><strong>Reboot required</strong></p><p class="small">Installed system updates require a restart to take effect. The NAS and its shares will be temporarily unavailable during the reboot.</p><button type="button" class="btn outline" id="reboot-after-updates">Reboot PiNAS</button></div><details class="updates-log"><summary>CLI output</summary><pre id="updates-output" class="small"></pre></details><p class="hint">Checking refreshes APT metadata without installing packages. Installation uses a standard APT upgrade without removing packages. Some updates may require a reboot.</p></div><div class="card section-spaced"><h2>Automatic updates</h2><button class="btn outline save-schedule-button" id="save-updates-schedule"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><path fill="currentColor" d="M4.71 20.95c-.93 0-1.4 0-1.69-.28l-.01-.02c-.29-.29-.29-.75-.29-1.69V4.9c0-.94 0-1.4.3-1.7c.29-.3.77-.3 1.72-.3c.77 0 1.15 0 1.42.22c.28.22.36.59.54 1.33l.23.98c.17.74.26 1.11.53 1.33s.65.21 1.41.21h2.45c.84 0 1.26 0 1.54-.25c.28-.24.34-.66.44-1.5l.3-2.4l4.05 2.82l2.95 2.6c.33.29.5.44.59.63c.09.2.09.42.09.87V19c0 .89 0 1.33-.26 1.62l-.07.06c-.29.26-.73.26-1.61.26c-.78 0-1.17 0-1.44-.22l-.07-.05c-.25-.24-.3-.63-.42-1.4l-.5-3.55c-.11-.77-.16-1.15-.42-1.4c-.26-.23-.65-.26-1.43-.31l-3.06-.2l-3.06.2c-.79.05-1.18.08-1.45.33c-.26.25-.3.64-.4 1.43l-.4 3.42c-.1.83-.15 1.24-.43 1.5h-.01c-.28.25-.7.25-1.54.25" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.77 21.38c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V8.6c0-2.83 0-4.24.88-5.12s2.3-.88 5.12-.88h3.58c1.05 0 1.58 0 2.07.18s.9.5 1.72 1.17l1.72 1.4l1.1.88c1.11.89 1.67 1.33 1.97 1.95s.3 1.33.3 2.75v4.45c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88z"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.64 2.82v.65c0 1.55 0 2.32.4 2.86a2 2 0 0 0 .4.39c.53.4 1.3.4 2.84.4c1.55 0 2.32 0 2.86-.4a2 2 0 0 0 .39-.4c.4-.53.4-1.3.4-2.85v-.65m3.43 18.44v-3.29c0-1.89 0-2.83-.58-3.41c-.59-.59-1.53-.59-3.42-.59h-2.72c-1.89 0-2.83 0-3.42.59c-.58.58-.58 1.52-.58 3.41v3.29"/></g></svg><span>Save schedule</span></button><p id="updates-schedule-message" class="small" role="status"></p><p class="small">Choose how often PiNAS checks for and installs all available OS package updates.</p><fieldset class="updates-schedule-options"><legend>Pick your schedule</legend><label><input type="radio" name="updates-schedule" value="off" checked><span>Off — Manual updates only</span></label><label><input type="radio" name="updates-schedule" value="daily"><span>Daily</span></label><label><input type="radio" name="updates-schedule" value="weekly"><span>Weekly</span></label><label><input type="radio" name="updates-schedule" value="monthly"><span>Monthly</span></label></fieldset><p id="updates-schedule-description" class="small" aria-live="polite"></p><p class="hint">Times use the Raspberry Pi's local timezone. Automatic updates do not reboot the NAS. A scheduled update may temporarily restart services.</p></div><div class="card section-spaced"><div class="chart-title"><h2>Automatic update service health</h2><button class="btn outline button-with-icon action-icon-btn" id="refresh-update-service-health" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M20.38 8.6c-2.24-3.19-4.95-5.38-8.8-5.38c-3.84 0-6.74 1.37-8.43 5m.5 7.18c2.24 3.14 4.92 5.38 8.77 5.38s6.93-1.55 8.43-5"/><path d="M21.34 4.23v1.3c0 1.9 0 2.84-.58 3.43c-.59.58-1.53.58-3.42.58h-1.31M2.66 19.77v-1.3c0-1.9 0-2.84.58-3.43c.59-.58 1.53-.58 3.42-.58h1.31"/></g></svg><span>Refresh</span></button></div><p class="small">The timer should be active when scheduling is enabled. The update service normally becomes inactive after a successful one-shot run.</p><div id="update-unit-health" role="status"></div></div><div class="card section-spaced"><h2>Installed update history</h2><p class="small">Manual and automatic APT installation attempts, with package names and results. Stored in a separate SQLite database on PiNAS system storage.</p><div class="updates-history-controls"><label class="field">Keep update history<select id="update-history-weeks">${Array.from({length:52},(_,i)=>`<option value="${i+1}" ${i===11?"selected":""}>${i+1} week${i===0?"":"s"}</option>`).join("")}</select></label><button class="btn outline button-with-icon action-icon-btn" id="save-update-history" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><path fill="currentColor" d="M4.71 20.95c-.93 0-1.4 0-1.69-.28l-.01-.02c-.29-.29-.29-.75-.29-1.69V4.9c0-.94 0-1.4.3-1.7c.29-.3.77-.3 1.72-.3c.77 0 1.15 0 1.42.22c.28.22.36.59.54 1.33l.23.98c.17.74.26 1.11.53 1.33s.65.21 1.41.21h2.45c.84 0 1.26 0 1.54-.25c.28-.24.34-.66.44-1.5l.3-2.4l4.05 2.82l2.95 2.6c.33.29.5.44.59.63c.09.2.09.42.09.87V19c0 .89 0 1.33-.26 1.62l-.07.06c-.29.26-.73.26-1.61.26c-.78 0-1.17 0-1.44-.22l-.07-.05c-.25-.24-.3-.63-.42-1.4l-.5-3.55c-.11-.77-.16-1.15-.42-1.4c-.26-.23-.65-.26-1.43-.31l-3.06-.2l-3.06.2c-.79.05-1.18.08-1.45.33c-.26.25-.3.64-.4 1.43l-.4 3.42c-.1.83-.15 1.24-.43 1.5h-.01c-.28.25-.7.25-1.54.25" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.77 21.38c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V8.6c0-2.83 0-4.24.88-5.12s2.3-.88 5.12-.88h3.58c1.05 0 1.58 0 2.07.18s.9.5 1.72 1.17l1.72 1.4l1.1.88c1.11.89 1.67 1.33 1.97 1.95s.3 1.33.3 2.75v4.45c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88z"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.64 2.82v.65c0 1.55 0 2.32.4 2.86a2 2 0 0 0 .4.39c.53.4 1.3.4 2.84.4c1.55 0 2.32 0 2.86-.4a2 2 0 0 0 .39-.4c.4-.53.4-1.3.4-2.85v-.65m3.43 18.44v-3.29c0-1.89 0-2.83-.58-3.41c-.59-.59-1.53-.59-3.42-.59h-2.72c-1.89 0-2.83 0-3.42.59c-.58.58-.58 1.52-.58 3.41v3.29"/></g></svg><span>Save</span></button><button class="btn outline button-with-icon action-icon-btn" id="download-update-logs" type="button"><svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" aria-hidden="true"><g fill="none" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5"><path d="M12 3v12m-4-4 4 4 4-4M4 17v3h16v-3"/></g></svg><span>Download Logs</span></button></div><p class="small" id="update-history-message' role="status"></p><div id="update-history-list"></div></div>`}shell(body);if(page==='Media Server')loadMediaServer();if(page==='Updates'){document.getElementById('refresh-update-service-health')?.addEventListener('click',loadUpdateUnitHealth);loadUpdateUnitHealth();const downloadLogs=document.getElementById('download-update-logs');
if(downloadLogs)downloadLogs.onclick=async()=>{
 downloadLogs.disabled=true;
 const message=document.getElementById('update-history-message');
 if(message)message.textContent='Preparing update history log…';
 try{
  const response=await fetch('/api/update-history-download',{cache:'no-store'});
  if(!response.ok){
   if(response.status===403)returnToLogin();
   const error=await response.json();throw Error(error.error||'Unable to download update logs');
  }
  const file=await response.blob(),url=URL.createObjectURL(file);
  const match=(response.headers.get('Content-Disposition')||'').match(/filename="([^"]+)"/);
  const anchor=document.createElement('a');anchor.href=url;anchor.download=match?match[1]:'pinas-update-history.txt';
  document.body.appendChild(anchor);anchor.click();anchor.remove();
  setTimeout(()=>URL.revokeObjectURL(url),1000);
  if(message)message.textContent='Update history log downloaded.';
 }catch(error){if(message)message.textContent='Download failed: '+error.message}
 finally{downloadLogs.disabled=false}
};
const saveHistory=document.getElementById('save-update-history');if(saveHistory)saveHistory.onclick=async()=>{const message=document.getElementById('update-history-message');saveHistory.disabled=true;message.textContent='Saving retention…';try{const weeks=Number(document.getElementById('update-history-weeks').value);await post('/api/updates',{action:'history-retention',weeks});message.textContent='History retention saved. Older records have been removed.';await loadUpdates()}catch(error){message.textContent=error.message}finally{saveHistory.disabled=false}};const scheduleRadios=[...document.querySelectorAll('input[name="updates-schedule"]')],desc=document.getElementById('updates-schedule-description');const selectedSchedule=()=>scheduleRadios.find(r=>r.checked)?.value||'off';const descriptions={off:'Automatic updates are disabled.',daily:'Updates will be checked and installed at 01:00 every day.',weekly:'Updates will be checked and installed every Friday at 01:00.',monthly:'Updates will be checked and installed on the 28th of every month at 01:00.'};const updateScheduleDescription=()=>{desc.textContent=descriptions[selectedSchedule()]};scheduleRadios.forEach(r=>r.addEventListener('change',updateScheduleDescription));updateScheduleDescription();document.getElementById('save-updates-schedule').onclick=async()=>{const b=document.getElementById('save-updates-schedule'),m=document.getElementById('updates-schedule-message');b.disabled=true;m.textContent='Saving schedule…';try{await post('/api/updates',{action:'schedule',schedule:selectedSchedule()});m.textContent='Schedule saved.';await loadUpdates()}catch(e){m.textContent=e.message}finally{b.disabled=false}};document.getElementById('reboot-after-updates').onclick=async()=>{const password=await updatePasswordDialog('reboot');if(password===null)return;const button=document.getElementById('reboot-after-updates');button.disabled=true;try{await post('/api/updates',{action:'reboot',admin_password:password});document.getElementById('updates-message').textContent='System reboot scheduled. The NAS will temporarily disconnect.';button.textContent='Reboot scheduled'}catch(e){document.getElementById('updates-message').textContent=e.message;button.disabled=false}};document.getElementById('install-os-updates').onclick=async()=>{const pw=await updatePasswordDialog();if(pw===null)return;document.getElementById('updates-spinner').hidden=false;document.getElementById('updates-message').textContent='Starting update installation…';try{await post('/api/updates',{action:'upgrade',admin_password:pw});await loadUpdates()}catch(e){document.getElementById('updates-message').textContent=e.message}};document.getElementById('check-os-updates').onclick=async()=>{const b=document.getElementById('check-os-updates');b.disabled=true;document.getElementById('updates-spinner').hidden=false;document.getElementById('updates-message').textContent='Checking for updates…';try{await post('/api/updates',{action:'refresh'});await loadUpdates()}catch(e){document.getElementById('updates-message').textContent=e.message}finally{await loadUpdates()}};loadUpdates()}if(page==='Overview'){document.querySelectorAll('[data-jump]').forEach(el=>{if(!navItems().includes(el.dataset.jump)){el.classList.remove('clickable');el.removeAttribute('role');el.removeAttribute('tabindex');el.removeAttribute('data-jump')}})}if(page==='Users'){document.getElementById('add-nas-user')?.addEventListener('click',openNasUserWizard);document.getElementById('add-admin-user')?.addEventListener('click',()=>openAccountWizard('admin'));document.querySelectorAll('[data-edit-nas]').forEach(b=>b.onclick=()=>openAccountWizard('nas',(info.nas_user_list||[]).find(u=>u.name===b.dataset.editNas)));document.querySelectorAll('[data-edit-admin]').forEach(b=>b.onclick=()=>openAccountWizard('admin',(info.admin_user_list||[]).find(u=>u.name===b.dataset.editAdmin)));document.querySelectorAll('[data-remove-nas]').forEach(b=>b.onclick=()=>removePinasUser('nas',b.dataset.removeNas));document.querySelectorAll('[data-remove-admin]').forEach(b=>b.onclick=()=>removePinasUser('admin',b.dataset.removeAdmin))}if(page==='Shares'){document.getElementById('create-nas-share')?.addEventListener('click',openNasShareWizard);document.querySelectorAll('[data-stop-share]').forEach(b=>b.addEventListener('click',()=>stopNasSharing(b.dataset.stopShare)));document.querySelectorAll('[data-delete-folder]').forEach(b=>b.addEventListener('click',()=>deleteNasShareFolder(b.dataset.deleteFolder)));document.querySelectorAll('[data-edit-share]').forEach(b=>b.addEventListener('click',()=>editNasShare(b.dataset.editShare)));document.querySelectorAll('[data-repair-share]').forEach(b=>b.addEventListener('click',()=>repairNasShare(b.dataset.repairShare)));document.querySelectorAll('[data-migrate-share]').forEach(b=>b.addEventListener('click',()=>migrateNasShare(b.dataset.migrateShare)))}if(page==='RAID'){document.getElementById('raid-create')?.addEventListener('click',openRaidWizard)}if(page==='Storage'){document.querySelectorAll('[data-disk]').forEach(b=>b.onclick=()=>openDiskWizard(Number(b.dataset.disk)));bindStorageScans();autoDiskHealth()}if(page==='Overview'){document.getElementById('refresh-service-health')?.addEventListener('click',refreshServiceHealth);refreshServiceHealth();autoDiskHealth();document.querySelectorAll('[data-jump]').forEach(el=>{el.onclick=()=>{page=navItems().includes(el.dataset.jump)?el.dataset.jump:'Storage';render()};el.onkeydown=e=>{if(e.key==='Enter'||e.key===' '){e.preventDefault();el.click()}}});drawCPU()}document.querySelectorAll('[data-next]').forEach(b=>b.onclick=()=>{page=b.dataset.next;render()})};

function updatePasswordDialog(action='upgrade'){return new Promise(resolve=>{const overlay=document.createElement('div');overlay.className='modal-overlay';const reboot=action==='reboot';overlay.innerHTML=`<div class="settings-modal card" role="dialog" aria-modal="true" aria-label="${reboot?'Reboot PiNAS':'Install updates'}"><h2>${reboot?'Reboot PiNAS':'Install system updates'}</h2><p>${reboot?'Installed updates require a reboot. All network shares and PiNAS access will be unavailable until the device restarts.':'APT will upgrade available packages without removing packages. Back up important data first. A reboot may be required.'}</p><label class="field">Current administrator password<input type="password" autocomplete="current-password" id="apt-password"></label><div class="modal-actions"><button class="btn outline" id="apt-cancel">Cancel</button><button class="btn ${reboot?'danger':''}" id="apt-confirm">${reboot?'Confirm reboot':'Install updates'}</button></div></div>`;document.body.appendChild(overlay);const close=v=>{overlay.remove();resolve(v)};overlay.querySelector('#apt-cancel').onclick=()=>close(null);overlay.querySelector('#apt-confirm').onclick=()=>close(overlay.querySelector('#apt-password').value);overlay.onkeydown=e=>{if(e.key==='Escape')close(null);if(e.key==='Enter')close(overlay.querySelector('#apt-password').value)};overlay.querySelector('#apt-password').focus()})}
async function loadUpdates(){
 const message=document.getElementById('updates-message'),list=document.getElementById('updates-list');if(!message)return;
 try{const r=await fetch('/api/updates',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error(j.error||'Could not read updates');
 const status=j.status||{};const rebootPanel=document.getElementById('update-reboot-panel');if(rebootPanel)rebootPanel.hidden=!j.reboot_required||!!status.running;const radios=[...document.querySelectorAll('input[name="updates-schedule"]')];if(radios.length&&!radios.some(r=>r===document.activeElement)){const selected=j.schedule||'off';radios.forEach(r=>{r.checked=r.value===selected});radios.find(r=>r.checked)?.dispatchEvent(new Event('change'))}const output=document.getElementById('updates-output');if(output)output.textContent=status.output||'';const fw=document.getElementById('firmware-update-status');if(fw){const f=j.firmware||{};fw.textContent=f.state==='available'?'Raspberry Pi EEPROM firmware update available':f.state==='current'?'Raspberry Pi EEPROM firmware is current':f.state==='unsupported'?'EEPROM firmware checks not applicable on this hardware':f.state==='missing'?'EEPROM checker is not installed':f.state==='error'?'Firmware check failed: '+(f.message||'Unknown error'):'Firmware status will be checked with package updates'}const install=document.getElementById('install-os-updates');if(install)install.disabled=!!status.running||!j.packages?.length;const check=document.getElementById('check-os-updates');if(check)check.disabled=!!status.running;const spinner=document.getElementById('updates-spinner');if(spinner)spinner.hidden=!status.running;message.textContent=status.running?(status.operation==='upgrade'?'Installing available updates…':'Refreshing package indexes…'):j.error?'APT: '+j.error:status.error?'Last check failed: '+status.error:`${j.packages.length} available package update${j.packages.length===1?'':'s'}${j.reboot_required?' · Reboot required':''}`;
 list.innerHTML=(j.packages||[]).length?`<div class="table-scroll"><table class="updates-package-table"><thead><tr><th>Package</th><th>Installed</th><th>Available</th></tr></thead><tbody>${j.packages.map(p=>`<tr><td>${esc(p.name)}<div class="small">${esc(p.repository)} · ${esc(p.architecture)}</div></td><td>${esc(p.installed)}</td><td>${esc(p.candidate)}</td></tr>`).join('')}</tbody></table></div>`:!j.error?'<p class="small">No upgradable packages are currently listed in the local APT indexes.</p>':'';
 const historyRetention=document.getElementById('update-history-weeks');
 if(historyRetention&&document.activeElement!==historyRetention)historyRetention.value=String(Number.isInteger(j.history_weeks)&&j.history_weeks>=1&&j.history_weeks<=52?j.history_weeks:12);
 const historyList=document.getElementById('update-history-list');
 if(historyList){
  const records=j.history||[];
  historyList.innerHTML=records.length?records.map(item=>{
   const packages=Array.isArray(item.packages)?item.packages:[];
   const date=new Date(Number(item.started_at)*1000);
   const stamp=Number.isFinite(date.getTime())?date.toLocaleDateString():'Unknown date';
   const source=item.source==='automatic'?'Automatic':'Manual';
   const result=item.result==='success'?'Installed':'Failed';
   return `<details class="update-history-row"><summary><span><strong>${esc(stamp)}</strong><span class="small">${source} · ${packages.length} package${packages.length===1?'':'s'} recorded</span></span><span class="pill ${item.result==='success'?'good':''}">${result}</span></summary><div class="update-history-details"><strong>Packages</strong><ul>${packages.length?packages.map(name=>`<li>${esc(name)}</li>`).join(''):'<li>No package changes recorded</li>'}</ul><strong>APT summary</strong><pre class="small">${esc(item.summary||'No summary available')}</pre></div></details>`;
  }).join(''):'<p class="small">No update installations recorded yet. Future manual and scheduled APT upgrades will appear here.</p>';
 }
 if(status.running&&page==='Updates')setTimeout(()=>{if(page==='Updates')loadUpdates()},3000);
 }catch(e){message.textContent=e.message}
}

const MEDIA_FIELDS=[
 ['friendly_name','Server name','text'],['port','HTTP port','number'],
 ['network_interface','Network interfaces (comma separated)','text'],
 ['notify_interval','Announce interval (seconds)','number'],['max_connections','Maximum connections','number'],
 ['model_name','Model name','text'],['model_number','Model number','text'],
 ['serial','Serial number','text'],['uuid','UPnP UUID','text'],
 ['presentation_url','Presentation URL','text'],['album_art_names','Album art filenames','text'],
 ['force_sort_criteria','Sorting criteria','text'],['log_level','Log levels','text'],
 ['root_container','Root container (. B M V P)','text'],
 ['tivo_discovery','TiVo discovery (bonjour or beacon)','text'],
 ['inotify','Watch media changes','checkbox'],['strict_dlna','Strict DLNA mode','checkbox'],
 ['merge_media_dirs','Merge media folders','checkbox'],
 ['enable_subtitles','Enable subtitles','checkbox'],['enable_tivo','Enable TiVo','checkbox'],
 ['enable_thumbnail','Generate thumbnails (if compiled in)','checkbox'],['thumbnail_width','Thumbnail width','number'],
 ['thumbnail_quality','Thumbnail quality','number'],['enable_thumbnail_filmstrip','Thumbnail filmstrip','checkbox']
];

const MEDIA_DOC={
 friendly_name:['Name advertised to DLNA devices. Default is the host name and service account.','PiNAS'],
 port:['HTTP streaming port. Common Debian package setting: 8200.','8200'],
 network_interface:['Leave blank to use all available network interfaces, e.g. eth0 or wlan0.','All interfaces'],
 notify_interval:['Seconds between discovery announcements. MiniDLNA default: 895.','895'],
 max_connections:['Maximum simultaneous client connections. Recommended starting value: 50.','50'],
 model_name:['Optional model description reported to players. Blank uses MiniDLNA built-in default.','Windows Media Connect compatible (MiniDLNA)'],
 model_number:['Leave blank to use the MiniDLNA version.','MiniDLNA version'],
 serial:['Leave blank to use the automatically detected identifier.','Automatic'],
 uuid:['Optional UPnP identifier. Leave blank unless you need a fixed device identity.','Automatic'],
 presentation_url:['Optional HTTP URL shown to clients; normally leave blank.','http://pinas.local:8200'],
 album_art_names:['Slash-delimited names of album cover files, e.g. Cover.jpg/Folder.jpg.','Cover.jpg/Folder.jpg'],
 force_sort_criteria:['Optional UPnP sort order. Leave empty to respect the client request.','Client-controlled'],
 log_level:['Syntax: general=warn or scanner,metadata=info. Levels: off, fatal, error, warn, info, debug.','general,artwork,database,inotify,scanner,metadata,http,ssdp,tivo=warn'],
 root_container:['Choose which container clients open first. Default is standard hierarchy.','.'],
 tivo_discovery:['Bonjour (default) or legacy beacon discovery. Normally leave at default.','bonjour'],
 inotify:['Automatically detect new media; recommended for most NAS libraries.','yes'],
 strict_dlna:['Strict compliance may add image conversion overhead. Default: no.','no'],
 merge_media_dirs:['Merge all folders into a single root listing. Default: no.','no'],
 enable_subtitles:['Expose external subtitle files when supported by the package build.','yes'],
 enable_tivo:['TiVo compatibility is normally unnecessary.','no'],
 enable_thumbnail:['Thumbnail generation requires a MiniDLNA build that supports it.','no'],
 thumbnail_width:['Width in pixels; accepted range 64–1024. Leave empty for package default.','Automatic'],
 thumbnail_quality:['Quality level 1–10. Leave empty for package default.','Automatic'],
 enable_thumbnail_filmstrip:['Filmstrip thumbnails require package build support.','no']
};
const MEDIA_SELECTS={
 root_container:[['','Default (standard hierarchy)'],['.','Standard hierarchy (.)'],['B','Browse folders (B)'],['M','Music (M)'],['V','Video (V)'],['P','Pictures (P)']],
 tivo_discovery:[['','Default (Bonjour)'],['bonjour','Bonjour'],['beacon','Legacy beacon']]
};
const MEDIA_NUMERIC={port:[1024,65535],notify_interval:[30,86400],max_connections:[1,100],thumbnail_width:[64,1024],thumbnail_quality:[1,10]};
const mediaLibraryVolumes=()=>disks().flatMap(d=>(d.volumes||[])
  .filter(v=>v.fs&&v.persistent&&!v.read_only)
  .flatMap(v=>(v.mounts||[]).filter(m=>/^\/mnt\/pinas\/[^/]+$/.test(m))
   .map(m=>({mount:m,label:(d.model||d.name||'Disk')+' · '+(v.fs||'Filesystem')+' · '+m}))));
let mediaSuccess='';
let mediaBusy=false;

// Shared PiNAS media and storage button glyphs.
const NAS_ACTION_ICONS={scan:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M15.5 11.29a4.25 4.25 0 1 1-8.5 0a4.25 4.25 0 0 1 8.5 0"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.93 21.32c2.27 0 3.4 0 4.2-.57a3 3 0 0 0 .64-.65c.58-.8.58-1.93.58-4.2M15.97 2.71c2.23 0 3.35 0 4.13.56a3 3 0 0 1 .69.69c.56.78.56 1.9.56 4.14M8.07 21.32c-2.27 0-3.4 0-4.2-.58a3 3 0 0 1-.64-.64c-.58-.8-.58-1.93-.58-4.2M8.07 2.71c-2.27 0-3.4 0-4.2.58a3 3 0 0 0-.64.65c-.58.79-.58 1.92-.58 4.2m11.64 6.11L17 16.97m-1.5-5.68a4.24 4.24 0 0 1-4.25 4.25a4.25 4.25 0 1 1 4.26-4.25"/></svg>`,start:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.82 12a10.18 10.18 0 1 0 20.36 0a10.18 10.18 0 0 0-20.36 0m7.63-5.46l8.54 4.9l-1.91 2.89l-6.63 3.45L7.73 12z"/><circle cx="12" cy="12" r="10.18" stroke="currentColor" stroke-width="1.5"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M8.2 12c0-3.05 0-4.57.97-5.16l.12-.07c1-.51 2.3.28 4.9 1.88c2.41 1.47 3.61 2.2 3.65 3.28v.14c-.04 1.07-1.24 1.81-3.65 3.28c-2.6 1.6-3.9 2.4-4.9 1.88l-.12-.07c-.96-.59-.96-2.11-.96-5.16"/></svg>`,stop:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.78 12a10.22 10.22 0 1 0 20.44 0a10.22 10.22 0 0 0-20.44 0m5.54-4.52h9.2v9.16h-9.2z"/><circle cx="12" cy="12" r="10.22" stroke="currentColor" stroke-width="1.5"/><rect x="7.26" y="7.26" width="9.47" height="9.47" rx="2" stroke="currentColor" stroke-width="1.5"/></svg>`,restart:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M3.03 13.34a8.97 8.97 0 1 0 17.94 0a8.97 8.97 0 0 0-17.94 0"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="m14.64 1.7l-2.02 1.65c-.8.65-1.19.98-1.21 1.42s.33.8 1.06 1.54l1.83 1.86"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12.18 4.74c5.75-.24 8.8 3.64 8.8 8.6A8.97 8.97 0 1 1 6.74 6.06"/></svg>`,rescan:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.69 12a10.31 10.31 0 1 0 20.62 0a10.31 10.31 0 0 0-20.62 0"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5.75 13.95v-3.9m12.5 3.9v-3.9M12 14.61V9.39m-3.05 6.96v-8.7m6.1 8.7v-8.7M1.7 12a10.31 10.31 0 1 1 20.61 0A10.31 10.31 0 0 1 1.7 12"/></svg>`,rebuild:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.69 12a10.31 10.31 0 1 0 20.62 0a10.31 10.31 0 0 0-20.62 0"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.7 12a10.31 10.31 0 1 1 20.61 0A10.31 10.31 0 0 1 1.7 12m6.49 5.15h7.63M8 9.9h8m-4 4.02V5.9"/></svg>`,create:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.78 12a10.22 10.22 0 1 0 20.44 0a10.22 10.22 0 0 0-20.44 0"/><circle cx="12" cy="12" r="10.22" stroke="currentColor" stroke-width="1.5"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12 17V7m5 5H7"/></svg>`,folder:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><g fill="none"><path fill="currentColor" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24-.88-5.12-.88s-.88-2.3-.88-5.12V7.5c0-.65 0-.98.05-1.25a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05H6.5c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.39.33c.83.71 1.25 1.06 1.75 1.25s1.05.18 2.14.18h1.56c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V6.5a2.56 2.56 0 0 1 2.56-2.56H6.5c1.04 0 1.55 0 2.03.16l.23.1c.46.2.84.55 1.6 1.25s1.14 1.06 1.6 1.26l.23.1c.47.16 1 .16 2.03.16h2.01c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12zM8.7 13.58h6.6M12 16.89v-6.6"/></g></svg>`,grant:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path fill="currentColor" opacity=".2" d="M1.63 14.52a4.12 4.12 0 1 0 8.23 0a4.12 4.12 0 0 0-8.23 0m12.51 0a4.12 4.12 0 1 0 8.23 0a4.12 4.12 0 0 0-8.23 0"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.63 14.52a4.1 4.1 0 0 0 4.12 4.11a4.12 4.12 0 1 0-4.12-4.11m12.51 0a4.1 4.1 0 0 0 4.12 4.11a4.12 4.12 0 1 0-4.12-4.11"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="m2.6 11.83l3.02-5.3a2.05 2.05 0 0 1 3.35-.32m12.43 5.62l-3-5.28a2.06 2.06 0 0 0-3.37-.3m-5.17 7.74c.69-.67 1.25-.9 2.14-.9s1.45.23 2.14.9"/></svg>`,upload:`<svg xmlns="http://www.w3.org/2000/svg" width="22" height="22" viewBox="0 0 24 24" fill="none" aria-hidden="true"><g fill="none"><path fill="currentColor" d="M2.4 12.01h19.2v2.96c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H8.4c-2.83 0-4.24-.88-5.12-.88s-.88-2.3-.88-5.12z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M2.69 12.01v2.96c0 2.83 0 4.24.88 5.12c.87.88 2.29.88 5.12.88h6.62c2.83 0 4.25 0 5.12-.88s.88-2.3.88-5.12v-2.96M17.1 6.77l-2.28-2.29c-1.34-1.33-2-2-2.83-2s-1.5.66-2.83 2l-2.3 2.3M11.98 16V3.32"/></g></svg>`};
async function loadMediaServer(){
 const panel=document.getElementById('media-server-panel');if(!panel)return;
 try{
  const response=await fetch('/api/media-server',{cache:'no-store'}),result=await response.json();
  if(!response.ok)throw Error(result.error||'Unable to read MiniDLNA');
  if(!result.installed){
   panel.innerHTML='<p>MiniDLNA is not installed. Install the lightweight DLNA service to share chosen media folders on the local network.</p><button class="btn" id="ms-install">Install MiniDLNA</button><p class="hint">Requires Raspberry Pi OS/Debian package repositories and an internet connection.</p><p id="ms-message" role="status"></p>';
   panel.querySelector('#ms-install').onclick=()=>mediaAction('install',true);
   return;
  }
  const opts=result.settings||{},defaultValue={
   friendly_name:info.hostname||'PiNAS',port:'8200',notify_interval:'895',
   max_connections:'50',root_container:'.',tivo_discovery:'bonjour',
   inotify:'yes',enable_subtitles:'yes',strict_dlna:'no',merge_media_dirs:'no',
   enable_tivo:'no',enable_thumbnail:'no',enable_thumbnail_filmstrip:'no'
  };
  const volumes=mediaLibraryVolumes(),hasFolders=Boolean((opts.media_dir||[]).length);
  const options=volumes.map(v=>'<option value="'+esc(v.mount)+'">'+esc(v.label)+'</option>').join('');
  const setupPanel='<section class="media-setup"><h3>'+(hasFolders?'Standard media library':'Complete media server setup')+'</h3>'
   +'<p>'+(hasFolders?'Create an additional standard library on your preferred disk. This replaces the current MiniDLNA media folder list, but does not remove or alter existing files.':
     'Choose a configured storage disk to create a ready-to-use library with Movies, Television, Music and Pictures folders.')+'</p>'
   +'<div class="media-picker"><label class="field">Storage disk<select id="ms-library-volume"><option value="">Choose a mounted disk…</option>'+options+'</select></label>'
   +'<button type="button" class="btn button-with-icon" id="ms-library-setup" '+(!volumes.length?'disabled':'')+'>'+NAS_ACTION_ICONS.create+'<span>Create media library</span></button></div>'
   +'<p class="hint">Creates /mnt/pinas/&lt;disk-id&gt;/pinas-media/ with four subfolders and configures MiniDLNA to scan them. Existing media files are never deleted. The folders are readable by MiniDLNA but are not automatically shared for SMB uploads.</p>'
   +(!volumes.length?'<p class="hint">Configure and persistently mount a data disk in Storage first.</p>':'')+'</section>';
  const shareOptions=(info.share_details||[]).filter(s=>typeof s.folder==='string'&&s.folder.startsWith('/mnt/pinas/')&&(!s.access||Object.keys(s.access).length!==1||Object.keys(s.access)[0]!==s.name)).map(s=>
    '<option value="'+esc(s.folder)+'">'+esc(s.name||s.folder)+'</option>').join('');
  const folderActions=(opts.media_dir||[]).map(item=>{
   const path=item.replace(/^[AVP],/,'');
   return '<div class="line media-folder-action"><span class="small">'+esc(path)+'</span><div class="media-folder-buttons"><button type="button" class="btn outline button-with-icon" data-media-grant="'+esc(path)+'">'+NAS_ACTION_ICONS.grant+'<span>Grant DLNA read access</span></button><button type="button" class="btn outline button-with-icon" data-media-upload="'+esc(path)+'">'+NAS_ACTION_ICONS.upload+'<span>Upload media</span></button></div></div>';
  }).join('')||'<p class="hint">Save at least one media folder to configure its read access.</p>';
  const fields=MEDIA_FIELDS.map(([key,label,type])=>{
   const val=opts[key]??defaultValue[key]??'';
   const doc=MEDIA_DOC[key]||['',''];
   const hint='<span class="hint">'+esc(doc[0])+' <em>Default: '+esc(doc[1])+'</em></span>';
   if(type==='checkbox')return '<label class="media-checkbox"><input type="checkbox" data-ms-key="'+key+'" '+(val==='yes'?'checked':'')+'><span>'+esc(label)+hint+'</span></label>';
   if(MEDIA_SELECTS[key]){
    const choices=MEDIA_SELECTS[key].map(([v,name])=>'<option value="'+esc(v)+'" '+(val===v?'selected':'')+'>'+esc(name)+'</option>').join('');
    return '<label class="field">'+esc(label)+'<select data-ms-key="'+key+'">'+choices+'</select>'+hint+'</label>';
   }
   const limits=MEDIA_NUMERIC[key],attrs=limits?' min="'+limits[0]+'" max="'+limits[1]+'" step="1"':'';
   return '<label class="field">'+esc(label)+'<input data-ms-key="'+key+'" type="'+type+'" value="'+esc(val)+'" placeholder="'+esc(doc[1])+'" maxlength="180"'+attrs+'>'+hint+'</label>';
  }).join('');
  panel.innerHTML='<div class="line"><strong>Service status</strong><span class="pill '+(result.state==='active'?'good':'')+'">'+esc(result.state==='active'?'Running':result.state)+'</span></div>'
   +'<div class="media-actions"><button class="btn outline button-with-icon" data-media-action="start">'+NAS_ACTION_ICONS.start+'<span>Start</span></button><button class="btn outline button-with-icon" data-media-action="stop">'+NAS_ACTION_ICONS.stop+'<span>Stop</span></button><button class="btn outline button-with-icon" data-media-action="restart">'+NAS_ACTION_ICONS.restart+'<span>Restart</span></button><button class="btn outline button-with-icon" data-media-action="rescan">'+NAS_ACTION_ICONS.rescan+'<span>Restart scan</span></button><button class="btn outline button-with-icon" data-media-action="rebuild">'+NAS_ACTION_ICONS.rebuild+'<span>Rebuild library</span></button></div>'
   +setupPanel+(mediaSuccess?'<p class="hint" role="status">'+esc(mediaSuccess)+'</p>':'')
   +'<form id="ms-form"><h3>Media folders</h3><p class="hint">One full folder path per line under /mnt/pinas/. Optionally prefix A, V or P followed by a comma for audio, video or photos.</p>'
   +'<div class="media-picker"><label class="field">Choose an existing NAS share<select id="ms-preset-share"><option value="">Select a share…</option>'+shareOptions+'</select></label><label class="field">Media type<select id="ms-preset-type"><option value="">All media</option><option value="A">Audio</option><option value="V">Video</option><option value="P">Photos</option></select></label><button type="button" class="btn outline button-with-icon" id="ms-preset-add">'+NAS_ACTION_ICONS.folder+'<span>Add folder</span></button></div>'
   +'<label class="field">Shared folders<textarea id="ms-folders" rows="5" placeholder="V,/mnt/pinas/UUID/pinas-shares/Movies">'+esc((opts.media_dir||[]).join('\n'))+'</textarea></label>'
   +'<p class="hint"><strong>Privacy:</strong> DLNA discovery is intended for trusted local networks and does not enforce NAS user accounts. Only add folders you intend to expose. The minidlna service account must have read permission; PiNAS only grants read permissions when you explicitly choose Grant DLNA read access below.</p>'
   +'<h3>Folder permissions</h3>'+folderActions+'<details class="media-advanced"><summary>Advanced MiniDLNA settings</summary><div class="media-fields">'+fields+'</div></details><div class="modal-actions"><button class="btn" type="submit">Save settings</button><button type="button" class="btn outline" id="ms-refresh">Refresh</button></div></form><p id="ms-message" role="status"></p>';
  panel.querySelectorAll('[data-media-action]').forEach(button=>{
   button.disabled=(button.dataset.mediaAction==='start'&&result.state==='active')||(button.dataset.mediaAction==='stop'&&result.state!=='active');
   button.onclick=()=>mediaAction(button.dataset.mediaAction,false);
  });
  panel.querySelectorAll('[data-media-grant]').forEach(button=>button.onclick=()=>mediaAction('grant',true,{path:button.dataset.mediaGrant}));
  panel.querySelectorAll('[data-media-upload]').forEach(button=>button.onclick=()=>openMediaUpload(button.dataset.mediaUpload));
  panel.querySelector('#ms-library-setup').onclick=async()=>{
   const target=panel.querySelector('#ms-library-volume').value;
   if(!target)return;
   if(hasFolders&&!confirm('Replace the configured MiniDLNA media folders with a standard library on the selected disk? Existing media files will remain untouched.'))return;
   await mediaAction('setup-library',true,{volume:target});
  };
  panel.querySelector('#ms-preset-add').onclick=()=>{
   const folder=panel.querySelector('#ms-preset-share').value,type=panel.querySelector('#ms-preset-type').value;
   if(!folder)return;
   const input=panel.querySelector('#ms-folders'),entry=(type?type+',':'')+folder;
   const lines=input.value.split('\n').map(x=>x.trim()).filter(Boolean);
   if(!lines.includes(entry))input.value=lines.concat(entry).join('\n');
  };
  panel.querySelector('#ms-refresh').onclick=loadMediaServer;
  panel.querySelector('#ms-form').onsubmit=async event=>{
   event.preventDefault();
   const settings={};
   panel.querySelectorAll('[data-ms-key]').forEach(el=>{settings[el.dataset.msKey]=el.type==='checkbox'?el.checked:el.type==='number'?(el.value.trim()===''?null:Number(el.value)):el.value.trim()});
   Object.keys(settings).forEach(key=>{if(settings[key]===null)delete settings[key]});
   settings.media_dir=panel.querySelector('#ms-folders').value.split('\n').map(x=>x.trim()).filter(Boolean).map(value=>{
    const match=value.match(/^([AVP]),(\/.*)$/);
    return {type:match?match[1]:'',path:match?match[2]:value};
   });
   await mediaAction('save',true,settings);
  };
 }catch(error){panel.textContent='Media server unavailable: '+error.message}
}

function openMediaUpload(path){
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML='<section class="card settings-modal media-upload-modal" role="dialog" aria-modal="true" aria-label="Upload MiniDLNA media">'+
  '<div class="modal-heading"><h2>Upload media</h2><button type="button" class="icon-btn" id="media-upload-close" aria-label="Close">'+CANCEL_ICON+'</button></div>'+
  '<p>Destination folder: <strong>'+esc(path)+'</strong></p>'+
  '<label class="field">Choose video, music, picture or subtitle files'+
  '<input type="file" id="media-upload-files" multiple accept=".avi,.mp4,.m4v,.mkv,.mov,.wmv,.flv,.webm,.mpeg,.mpg,.m2ts,.mts,.ts,.3gp,.vob,.ogv,.mp3,.wav,.aac,.flac,.m4a,.ogg,.opus,.wma,.aiff,.alac,.ape,.jpg,.jpeg,.png,.bmp,.svg,.gif,.webp,.tif,.tiff,.heic,.heif,.avif,.ico,.srt,.vtt,.ass,.ssa,.sub,.idx"></label>'+
  '<p class="hint">Files are uploaded in small chunks and are never overwritten. Newly uploaded files receive MiniDLNA read access; run Grant DLNA read access if the folder itself does not allow traversal.</p>'+
  '<progress class="media-upload-progress" id="media-upload-progress" max="100" value="0" hidden></progress>'+
  '<p id="media-upload-status" role="status">Select one or more files.</p>'+
  '<div class="modal-actions"><button type="button" class="btn outline" id="media-upload-cancel">Cancel</button>'+
  '<button type="button" class="btn" id="media-upload-start">Upload files</button></div></section>';
 document.body.append(overlay);
 const filesInput=overlay.querySelector('#media-upload-files'),progress=overlay.querySelector('#media-upload-progress');
 const status=overlay.querySelector('#media-upload-status'),begin=overlay.querySelector('#media-upload-start');
 const cancel=overlay.querySelector('#media-upload-cancel'),close=overlay.querySelector('#media-upload-close');
 let uploading=false,cancelled=false,token=null,completed=0;
 const dismiss=()=>{document.removeEventListener('keydown',key);overlay.remove()};
 const onCancel=()=>{if(uploading){cancelled=true;status.textContent='Cancelling after the current chunk…';cancel.disabled=true;return}dismiss()};
 const key=e=>{if(e.key==='Escape'){e.preventDefault();onCancel()}};
 document.addEventListener('keydown',key);
 close.onclick=onCancel;cancel.onclick=onCancel;
 overlay.addEventListener('click',e=>{if(e.target===overlay)onCancel()});
 begin.onclick=async()=>{
  const files=[...filesInput.files];
  if(!files.length){status.textContent='Select at least one media file.';return}
  if(files.some(file=>file.size<1||file.size>100*1024**3)){
   status.textContent='Each media file must be between 1 byte and 100 GiB.';return
  }
  const password=await fileTextDialog({title:'Upload to MiniDLNA',label:'Administrator password',
    description:'Authorise uploading '+files.length+' media file(s) to '+path+'. Existing files will not be replaced.',
    confirmLabel:'Authorise upload',password:true});
  if(password===null||!overlay.isConnected)return;
  uploading=true;cancelled=false;completed=0;
  begin.disabled=true;filesInput.disabled=true;close.disabled=true;progress.hidden=false;
  const totalSize=files.reduce((sum,file)=>sum+file.size,0);
  let transferred=0;
  const update=(file,index,offset)=>{
   const done=transferred+offset;
   progress.value=Math.min(100,totalSize?100*done/totalSize:0);
   status.textContent='File '+index+'/'+files.length+': '+file.name+' — '+size(offset)+' / '+size(file.size);
  };
  try{
   for(let index=0;index<files.length;index++){
    const file=files[index];let offset=0;token=null;
    if(cancelled)throw Error('Upload cancelled.');
    const result=await post('/api/media-upload',{action:'start',path,name:file.name,size:file.size,admin_password:password});
    token=result.token;
    while(offset<file.size){
     if(cancelled)throw Error('Upload cancelled.');
     const bytes=new Uint8Array(await file.slice(offset,offset+384*1024).arrayBuffer());
     let binary='';
     for(let n=0;n<bytes.length;n+=8192)binary+=String.fromCharCode(...bytes.subarray(n,n+8192));
     const answer=await post('/api/media-upload',{action:'chunk',path,token,offset,content:btoa(binary)});
     if(!Number.isInteger(answer.offset)||answer.offset<=offset)throw Error('Unexpected transfer offset');
     offset=answer.offset;update(file,index+1,offset);
    }
    if(cancelled)throw Error('Upload cancelled.');
    await post('/api/media-upload',{action:'finish',path,token});
    token=null;completed++;transferred+=file.size;
   }
   mediaSuccess=completed+' media file(s) uploaded to '+path+'. MiniDLNA will index them when scanning is enabled.';
   dismiss();await loadMediaServer();
  }catch(err){
   if(token){try{await post('/api/media-upload',{action:'cancel',path,token})}catch(_){}}
   status.textContent=(cancelled?'Upload cancelled. ': 'Upload failed: ')+err.message+
     (completed?' '+completed+' earlier file(s) uploaded successfully.':'');
   begin.disabled=false;filesInput.disabled=false;close.disabled=false;cancel.disabled=false;
   if(cancelled){dismiss();if(completed){mediaSuccess=completed+' media file(s) uploaded to '+path;await loadMediaServer()}}
  }finally{uploading=false}
 };
 filesInput.focus();
}

async function mediaAction(action,needsPassword,settings){
 if(mediaBusy)return;
 const panel=document.getElementById('media-server-panel');if(!panel)return;
 let admin_password=null;
 if(needsPassword){
  const titles={install:'Install MiniDLNA',save:'Save MiniDLNA settings',grant:'Allow media server folder access',rebuild:'Rebuild MiniDLNA library','setup-library':'Create standard media library'};
  const descriptions={
   install:'Install and enable MiniDLNA from the OS package repository.',
   save:'Validate and save the configuration, then restart MiniDLNA.',
   grant:'Give the MiniDLNA service account read/traverse access to this folder and its existing files and add default read ACLs for new files. DLNA clients on your local network may be able to browse this media.',
   rebuild:'Stop MiniDLNA, remove only its cached media index and restart scanning. Media files are preserved, but client bookmarks may be lost.',
   'setup-library':'Create Movies, Television, Music and Pictures folders on the selected mounted disk, and replace MiniDLNA media folder settings. Existing files and folders are preserved.'
  };
  admin_password=await fileTextDialog({title:titles[action]||'Manage MiniDLNA',
    label:'Administrator password',description:descriptions[action]||'',confirmLabel:action==='install'?'Install':action==='rebuild'?'Rebuild':'Confirm',password:true});
  if(admin_password===null)return;
 }else if(!confirm('Run '+action+' on MiniDLNA?'))return;
 mediaBusy=true;
 const message=panel.querySelector('#ms-message');if(message)message.textContent='Applying '+action+'…';
 try{const result=await post('/api/media-server',{action,admin_password,settings});mediaSuccess=action==='setup-library'?'Media library ready at '+result.library_path:action==='install'?'MiniDLNA installed. Choose a storage disk to complete setup.':'';await loadMediaServer()}
 catch(error){if(message)message.textContent=error.message;else alert(error.message)}
 finally{mediaBusy=false}
}


async function repairNasShare(name){
 const password=await fileTextDialog({title:'Repair access for '+name,
   label:'Administrator password',
   description:'Reapply the current share-user permissions to existing files and directories in this share only. This may take time on large libraries. It does not change ownership, make files public or cross nested mounts.',
   confirmLabel:'Repair permissions',password:true});
 if(password===null)return;
 try{
  await post('/api/repair-share',{name,admin_password:password});
  alert('Permissions repaired for '+name+'. New SMB folders will inherit the share ACL.');
 }catch(error){alert('Share permission repair failed: '+error.message)}
}

function openRaidWizard(){
 const available=raidEligibleDisks();
 const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.id='raid-overlay';
 const close=()=>{document.removeEventListener('keydown',onKey);overlay.remove()};
 const onKey=e=>{if(e.key==='Escape')close()};document.addEventListener('keydown',onKey);
 const options=available.map((d,i)=>`<label class="raid-disk"><input type="checkbox" data-raid-disk="${i}"><span><strong>${esc(d.model||d.name)}</strong><small>${esc(d.path)} · ${size(d.size)}${d.volumes?.length?' · Existing partitions/data will be erased':''}</small></span></label>`).join('');
 overlay.innerHTML=`<section class="card settings-modal raid-wizard" role="dialog" aria-modal="true" aria-labelledby="raid-title" tabindex="-1"><div class="modal-heading"><h2 id="raid-title">Set up software RAID</h2><button class="icon-btn" id="raid-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Select the disks to combine. <strong class="danger">Creating an array destroys all existing data on every selected disk.</strong> Back up anything you want to keep before continuing.</p><h3>1. Select disks</h3>${options||'<p>No eligible writable data disks detected.</p>'}<p id="raid-selection" class="small" aria-live="polite">Select at least two disks.</p><h3>2. RAID layout</h3><label class="field">RAID type<select id="raid-level"><option value="1">RAID 1 — Mirror (recommended for two disks)</option><option value="0">RAID 0 — Stripe (no redundancy)</option><option value="5">RAID 5 — Distributed parity (three or more disks)</option></select></label><div id="raid-layout-description" class="hint"></div><h3>3. Filesystem</h3>${Object.entries(FS_GUIDE).map(([key,v])=>`<label class="wizard-option"><input type="radio" name="raid-filesystem" value="${key}" ${key==='ext4'?'checked':''}><strong>${key.toUpperCase()}</strong>${key==='ext4'?' · Recommended':''} — ${v[0]}<small>${v[1]}</small></label>`).join('')}<h3>4. Review</h3><div class="hint" id="raid-review" aria-live="polite"></div><p class="danger"><strong>Destructive operation:</strong> the selected disks would be wiped, partitioned, assembled into an mdadm array, formatted and mounted automatically. The administrator password and final explicit confirmation will be required when RAID creation is implemented.</p></div><div class="modal-actions"><button class="btn outline" id="raid-cancel">Close</button><button class="btn" disabled title="Protected RAID creation not implemented">Create RAID (coming soon)</button></div></section>`;
 document.body.appendChild(overlay);overlay.querySelector('#raid-close').onclick=close;overlay.querySelector('#raid-cancel').onclick=close;overlay.onclick=e=>{if(e.target===overlay)close()};
 const level=overlay.querySelector('#raid-level');const boxes=[...overlay.querySelectorAll('[data-raid-disk]')];
 const refresh=()=>{const selected=boxes.filter(b=>b.checked).map(b=>available[Number(b.dataset.raidDisk)]),n=selected.length,min=selected.length?Math.min(...selected.map(d=>Number(d.size))):0;const validLevels=n>=3?['0','1','5']:['0','1'];level.querySelector('option[value="5"]').disabled=n<3;if(!validLevels.includes(level.value))level.value='1';const l=level.value;const estimated=n>=2?(l==='0'?n*min:l==='1'?min:(n-1)*min):0;const lost=n>=2?selected.reduce((a,d)=>a+Number(d.size),0)-n*min:0;overlay.querySelector('#raid-selection').textContent=n?`${n} disk${n===1?'':'s'} selected · Smallest disk: ${size(min)}`:'Select at least two disks.';
 overlay.querySelector('#raid-layout-description').textContent=l==='0'?'RAID 0 combines disk capacity and performance, but offers NO redundancy. Failure of one disk loses the entire array.':l==='1'?'RAID 1 mirrors data. With two disks, one disk can fail without immediate data loss; capacity is limited to the smallest disk. For three or more disks, mdadm mirrors across all selected disks.':'RAID 5 distributes parity across three or more disks. It tolerates one disk failure, but rebuilding a degraded array can be slow and risky.';
 overlay.querySelector('#raid-review').innerHTML=n<2?'Select at least two data disks to calculate capacity.':`<strong>Estimated usable array capacity: ${size(estimated)}</strong><p class="small">${n} × ${size(min)} equal-sized member partitions · ${l==='0'?'Striping':l==='1'?'Mirroring':'Single distributed parity'} · Before filesystem overhead</p>${lost?`<p class="small">${size(lost)} of larger-disk capacity would be unused because each member is limited by the smallest selected disk.</p>`:''}<p class="small">All selected disks would be erased. RAID is not a backup.</p>`;};
 boxes.forEach(b=>b.onchange=refresh);level.onchange=refresh;refresh();overlay.querySelector('.raid-wizard').focus();
}
function openNasUserWizard(){
 const volumes=disks().flatMap(d=>(d.volumes||[]).filter(v=>['ext4','xfs','btrfs'].includes(v.fs)&&v.persistent&&v.mounts?.length&&!v.read_only).map(v=>({path:v.path,label:(d.model||d.name)+' · '+v.name+' · '+v.mounts[0]})));
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<div class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Create NAS user"><div class="modal-heading"><h2>Create NAS user</h2><button class="icon-btn" id="nu-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Create a Samba account for shared folders and web file access. This account cannot log in through SSH or the Linux console.</p><form id="nu-form"><label class="field">Display Name<input name="display_name" required maxlength="80" autocomplete="off" placeholder="e.g. Alice Smith"></label><label class="field">Username<input name="username" required minlength="3" maxlength="32" pattern="[a-z_][a-z0-9_-]{2,31}" autocomplete="off" placeholder="e.g. alice"></label><label class="field">Password<input name="password" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><label class="field">Confirm Password<input name="confirm" type="password" minlength="12" maxlength="256" required autocomplete="new-password"></label><label class="nas-home-choice"><input id="nu-create-home" name="create_home_share" type="checkbox" ${volumes.length?'':'disabled'}><span>Create private home folder share</span></label><div id="nu-home-details" class="hidden"><label class="field">Home share storage<select name="home_volume" required disabled>${volumes.map(v=>`<option value="${esc(v.path)}">${esc(v.label)}</option>`).join('')}</select></label><label class="field">Administrator password<input name="admin_password" type="password" autocomplete="current-password" required disabled></label><p class="hint">A private SMB share named after the username will be created with read/write access exclusively for this NAS user. Storage location: pinas-shares/username.</p></div>${!volumes.length?'<p class="hint">Mount a persistent data disk to enable private home shares.</p>':''}<p class="hint">The display name is used in PiNAS. The username is used for Samba and private home shares.</p><div id="nu-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="nu-cancel">Cancel</button><button class="btn" type="submit" id="nu-submit">Create user</button></div></form></div></div>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();overlay.querySelector('#nu-close').onclick=close;overlay.querySelector('#nu-cancel').onclick=close;
 const homeCheck=overlay.querySelector('#nu-create-home'),homeDetails=overlay.querySelector('#nu-home-details');
 homeCheck.onchange=()=>{homeDetails.classList.toggle('hidden',!homeCheck.checked);homeDetails.querySelectorAll('select,input').forEach(el=>{el.disabled=!homeCheck.checked})};
 overlay.querySelector('#nu-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#nu-message'),btn=overlay.querySelector('#nu-submit');if(f.get('password')!==f.get('confirm')){msg.textContent='Passwords do not match.';return}btn.disabled=true;msg.textContent='Creating account…';try{await post('/api/nas-users',{display_name:f.get('display_name'),username:f.get('username'),password:f.get('password'),create_home_share:homeCheck.checked,home_volume:homeCheck.checked?f.get('home_volume'):null,admin_password:homeCheck.checked?f.get('admin_password'):null});let j=await (await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=username]').focus();
}
function openAccountWizard(kind,existing=null){
 const editing=!!existing,admin=kind==='admin',overlay=document.createElement('div');overlay.className='modal-overlay';
 const title=editing?'Edit User':admin?'Add Admin User':'Add New User';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="${title}"><div class="modal-heading"><h2>${title}</h2><button class="icon-btn" id="account-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><form id="account-form"><label class="field">Display Name<input name="display_name" required maxlength="80" value="${esc(existing?.display_name||'')}"></label><label class="field">Username<input name="username" required minlength="3" maxlength="32" pattern="[a-z_][a-z0-9_-]{2,31}" value="${esc(existing?.name||'')}" ${editing?'disabled':''}></label><label class="field">${editing?'New Password (leave blank to keep current)':'Password'}<input name="password" type="password" minlength="12" maxlength="256" ${editing?'':'required'} autocomplete="new-password"></label><label class="field">Confirm Password<input name="confirm" type="password" minlength="12" maxlength="256" ${editing?'':'required'} autocomplete="new-password"></label>${admin&&!editing?'<label class="field">Current Administrator Password<input name="admin_password" type="password" required autocomplete="current-password"></label>':''}<p class="hint">${editing?'The username cannot be changed. Leave password fields blank to keep the existing password.':admin?'Administrators can manage PiNAS. Confirm your own password to authorise creation.':'NAS users access shared folders and cannot administer PiNAS.'}</p><div id="account-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="account-cancel">Cancel</button><button class="btn" id="account-submit" type="submit">${editing?'Save Changes':'Create User'}</button></div></form></div></section>`;
 document.body.append(overlay);const close=()=>overlay.remove();overlay.querySelector('#account-close').onclick=close;overlay.querySelector('#account-cancel').onclick=close;
 overlay.querySelector('#account-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#account-message'),btn=overlay.querySelector('#account-submit');if(f.get('password')!==f.get('confirm')){msg.textContent='Passwords do not match.';return}btn.disabled=true;try{const payload={kind,username:editing?existing.name:f.get('username'),display_name:f.get('display_name'),password:f.get('password')};if(admin&&!editing)payload.admin_password=f.get('admin_password');await post(editing?'/api/edit-user':admin?'/api/admin-users':'/api/nas-users',payload);const j=await(await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=display_name]').focus();
}
function sharePermissionGroups(users,access={}){
 return `<div class="share-permission-groups" data-permission-groups><fieldset class="share-permission-group"><legend>Read Only</legend>${users.map(u=>`<label class="share-user-choice"><input type="checkbox" data-share-user="${esc(u.name)}" data-share-level="ro" ${access[u.name]==='ro'?'checked':''}><span>${esc(u.name)}</span></label>`).join('')||'<p class="small">No NAS users configured.</p>'}</fieldset><fieldset class="share-permission-group"><legend>Read &amp; Write</legend>${users.map(u=>`<label class="share-user-choice"><input type="checkbox" data-share-user="${esc(u.name)}" data-share-level="rw" ${access[u.name]==='rw'?'checked':''}><span>${esc(u.name)}</span></label>`).join('')||'<p class="small">No NAS users configured.</p>'}</fieldset></div><label class="share-public-toggle"><input type="checkbox" data-share-public><span><strong>Public Share — No Authentication</strong><small>Anyone with network access can connect without a user account.</small></span></label><div class="share-public-write" hidden><label class="share-user-choice"><input type="checkbox" data-share-public-write><span>Allow public Read &amp; Write access</span></label><p class="small">Warning: Anyone who can reach this share can create, modify or delete files.</p></div>`;
}
function bindSharePermissionGroups(overlay,initialPublic=false,initialWrite=false){
 const publicBox=overlay.querySelector('[data-share-public]'),writeBox=overlay.querySelector('[data-share-public-write]'),writePanel=overlay.querySelector('.share-public-write'),choices=[...overlay.querySelectorAll('[data-share-user]')];
 choices.forEach(box=>box.addEventListener('change',()=>{if(box.checked)choices.forEach(other=>{if(other!==box&&other.dataset.shareUser===box.dataset.shareUser)other.checked=false})}));
 function sync(){const enabled=publicBox.checked;choices.forEach(box=>box.disabled=enabled);overlay.querySelector('[data-permission-groups]').classList.toggle('share-permissions-disabled',enabled);writePanel.hidden=!enabled;if(!enabled)writeBox.checked=false}
 publicBox.checked=initialPublic;writeBox.checked=initialWrite;publicBox.addEventListener('change',sync);sync();
 return ()=>{const access={};if(!publicBox.checked)choices.forEach(box=>{if(box.checked)access[box.dataset.shareUser]=box.dataset.shareLevel});return {access,public:publicBox.checked,public_write:publicBox.checked&&writeBox.checked}};
}
async function migrateNasShare(name){
 const item=(info.share_details||[]).find(s=>s.name===name);
 if(!item||!item.folder?.includes('/PiNAS Shares/'))return;
 const password=await fileTextDialog({title:'Move legacy share folder',label:'Administrator password',description:'Move the '+name+' share to pinas-shares on the same disk. Samba connections to this folder may briefly be interrupted. Existing files and permissions will be preserved. No destination folder will be overwritten.',confirmLabel:'Move folder',password:true});
 if(password===null)return;
 try{
  await post('/api/migrate-share',{name,confirm:'MOVE SHARE',admin_password:password});
  const response=await fetch('/api/state',{cache:'no-store'}),result=await response.json();
  if(!response.ok)throw Error(result.error||'Unable to refresh shares');
  info=result.hardware||info;
  render();
 }catch(error){alert('Share migration: '+error.message)}
}
function editNasShare(name){
 const d=(info.share_details||[]).find(x=>x.name===name);if(!d)return;
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 const users=info.nas_user_list||[];
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Edit share" tabindex="-1"><div class="modal-heading"><h2>Edit network share</h2><button class="icon-btn" id="es-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p class="small">Location: ${esc(d.folder||'Unavailable')}. The folder and files will not be moved or renamed.</p><form id="es-form"><label class="field">Share name<input name="new_name" maxlength="32" required pattern="[A-Za-z][A-Za-z0-9 _-]{0,31}" value="${esc(name)}"></label><h3>Share permissions</h3>${sharePermissionGroups(users,d.access||{})}<label class="field">Administrator password<input name="admin_password" type="password" required autocomplete="current-password"></label><p class="hint">Samba access and Linux ACLs are updated together. Existing files and subfolders are reconciled automatically; large shares may take time. Linux file ownership is preserved.</p><p id="es-message" role="status"></p><div class="modal-actions"><button class="btn outline" type="button" id="es-cancel">Cancel</button><button class="btn" type="submit" id="es-save">Save changes</button></div></form></div></section>`;
 document.body.appendChild(overlay);const getPolicy=bindSharePermissionGroups(overlay,!!d.public,!!d.public_write);const close=()=>overlay.remove();overlay.querySelector('#es-close').onclick=close;overlay.querySelector('#es-cancel').onclick=close;
 overlay.querySelector('#es-form').onsubmit=async e=>{e.preventDefault();const form=e.currentTarget,{access,public:publicShare,public_write:publicWrite}=getPolicy();const msg=overlay.querySelector('#es-message'),btn=overlay.querySelector('#es-save');if(!publicShare&&!Object.keys(access).length){msg.textContent='Assign access to at least one user.';return}btn.disabled=true;msg.textContent='Saving Samba permissions and synchronising Linux ACLs…';try{const values=new FormData(form),newName=values.get('new_name'),adminPassword=values.get('admin_password');await post('/api/edit-share',{name,new_name:newName,access,public:publicShare,public_write:publicWrite,admin_password:adminPassword});const r=await fetch('/api/state',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error('Unable to refresh shares');info=j.hardware||info;close();render()}catch(error){msg.textContent=error.message;btn.disabled=false}};
 overlay.querySelector('[name=new_name]').focus();
}
function stopNasSharing(name){
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Stop Sharing" tabindex="-1"><div class="modal-heading"><h2>Stop Sharing</h2><button class="icon-btn" id="ds-close" aria-label="Close">${CANCEL_ICON}</button></div><p>Stop sharing <strong>${esc(name)}</strong> over the network?</p><p class="hint">The network share will be removed, but its folder and files will be preserved on disk.</p><form id="ds-form"><label class="field">Administrator password<input type="password" name="admin_password" required autocomplete="current-password"></label><p id="ds-message" role="status"></p><div class="modal-actions"><button type="button" class="btn outline" id="ds-cancel">Cancel</button><button type="submit" class="btn" id="ds-submit">Stop Sharing</button></div></form></section>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();
 overlay.querySelector('#ds-close').onclick=close;overlay.querySelector('#ds-cancel').onclick=close;
 overlay.querySelector('#ds-form').onsubmit=async e=>{e.preventDefault();const btn=overlay.querySelector('#ds-submit'),msg=overlay.querySelector('#ds-message');btn.disabled=true;msg.textContent='Stopping SMB sharing…';try{await post('/api/delete-share',{name,admin_password:new FormData(e.currentTarget).get('admin_password')});const r=await fetch('/api/state',{cache:'no-store'}),j=await r.json();if(!r.ok)throw Error('Unable to refresh shares');info=j.hardware||info;close();render()}catch(error){msg.textContent=error.message;btn.disabled=false}};
 overlay.querySelector('[name=admin_password]').focus();
}
function removePinasUser(kind,name){
 const admin=kind==='admin',overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Remove User"><div class="modal-heading"><h2>Remove User</h2><button class="icon-btn" id="ru-close" aria-label="Close">${CANCEL_ICON}</button></div><p>Delete ${admin?'administrator':'NAS user'} <strong>${esc(name)}</strong>?</p><p class="hint">${admin?'This administrator will no longer have access to PiNAS.':'The Samba and managed Linux user accounts will be removed. Existing files and folders are preserved. Remove the user from network share permissions first; their private share must be stopped before removing the account.'}</p><form id="ru-form"><label class="field">Type username to confirm<input name="confirm_name" autocomplete="off" required placeholder="${esc(name)}"></label><label class="field">Administrator password<input name="admin_password" type="password" autocomplete="current-password" required></label><label class="share-user-choice"><input name="confirm" type="checkbox" required><span>I understand this removes the account.</span></label><p id="ru-message" role="status"></p><div class="modal-actions"><button class="btn outline" type="button" id="ru-cancel">Cancel</button><button class="btn danger share-remove-confirm" type="submit" id="ru-submit">Remove User</button></div></form></section>`;
 document.body.appendChild(overlay);
 const close=()=>overlay.remove();overlay.querySelector('#ru-close').onclick=close;overlay.querySelector('#ru-cancel').onclick=close;
 overlay.querySelector('#ru-form').onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.currentTarget),message=overlay.querySelector('#ru-message'),button=overlay.querySelector('#ru-submit');
  if(form.get('confirm_name')!==name){message.textContent='Enter the exact username to confirm.';return}
  button.disabled=true;message.textContent='Removing user…';
  try{
   await post('/api/remove-user',{kind,username:name,confirm:'REMOVE USER',confirm_name:form.get('confirm_name'),admin_password:form.get('admin_password')});
   const response=await fetch('/api/state',{cache:'no-store'}),result=await response.json();
   if(!response.ok)throw Error(result.error||'Unable to refresh users');
   info=result.hardware||info;close();render();
  }catch(error){message.textContent=error.message;button.disabled=false}
 };
 overlay.querySelector('[name=confirm_name]').focus();
}
function deleteNasShareFolder(name){
 const entry=(info.share_details||[]).find(item=>item.name===name);
 if(!entry)return;
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Delete Folder"><div class="modal-heading"><h2>Delete Folder</h2><button class="icon-btn" id="df-close" aria-label="Close">${CANCEL_ICON}</button></div><p><strong>PERMANENTLY DELETE</strong> the network share folder <strong>${esc(name)}</strong>?</p><p class="hint">This stops SMB sharing, then recursively removes the entire folder and all files and subfolders at <strong>${esc(entry.folder||'Unavailable')}</strong>. This cannot be undone. Back up important data first.</p><form id="df-form"><label class="field">Type share name to confirm<input name="confirm_name" autocomplete="off" required placeholder="${esc(name)}"></label><label class="field">Administrator password<input name="admin_password" type="password" autocomplete="current-password" required></label><label class="share-user-choice"><input name="confirm" type="checkbox" required><span>I understand this permanently deletes all files in this folder.</span></label><p id="df-message" role="status"></p><div class="modal-actions"><button type="button" class="btn outline" id="df-cancel">Cancel</button><button class="btn danger share-remove-confirm" type="submit" id="df-submit">Delete Folder</button></div></form></section>`;
 document.body.appendChild(overlay);const close=()=>overlay.remove();overlay.querySelector('#df-close').onclick=close;overlay.querySelector('#df-cancel').onclick=close;
 overlay.querySelector('#df-form').onsubmit=async event=>{
  event.preventDefault();const form=new FormData(event.currentTarget),message=overlay.querySelector('#df-message'),button=overlay.querySelector('#df-submit');
  if(form.get('confirm_name')!==name){message.textContent='Enter the exact share name to confirm.';return}
  button.disabled=true;message.textContent='Stopping SMB sharing and permanently deleting folder…';
  try{
   await post('/api/delete-folder',{name,confirm:'DELETE FOLDER',confirm_name:form.get('confirm_name'),admin_password:form.get('admin_password')});
   const response=await fetch('/api/state',{cache:'no-store'}),result=await response.json();
   if(!response.ok)throw Error(result.error||'Unable to refresh shares');
   info=result.hardware||info;close();render();
  }catch(error){message.textContent=error.message+' Check whether SMB sharing was already stopped before retrying.';button.disabled=false}
 };
 overlay.querySelector('[name=confirm_name]').focus();
}
function openNasShareWizard(){
 const users=info.nas_user_list||[],volumes=disks().flatMap(d=>(d.volumes||[]).filter(v=>['ext4','xfs','btrfs'].includes(v.fs)&&v.persistent&&v.mounts?.length).map(v=>({path:v.path,label:(d.model||d.name)+' · '+v.name+' · '+v.mounts[0]})));
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Create NAS share" tabindex="-1"><div class="modal-heading"><h2>Create network share</h2><button class="icon-btn" id="ns-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>Choose a name, a configured data disk and the users who may access this share. PiNAS creates a new folder without changing existing files.</p><form id="ns-form"><label class="field">Share name<input name="name" maxlength="32" required pattern="[A-Za-z][A-Za-z0-9 _-]{0,31}" placeholder="e.g. Family Photos"></label><label class="field">Storage location<select name="volume" required>${volumes.map(v=>`<option value="${esc(v.path)}">${esc(v.label)}</option>`).join('')}</select></label><h3>Share permissions</h3>${sharePermissionGroups(users)}<label class="field">Administrator password<input name="admin_password" type="password" required autocomplete="current-password"></label><p class="hint">Permissions are applied to both SMB access and the underlying folder using POSIX ACLs. Share creation is not destructive.</p><div id="ns-message" role="status"></div><div class="modal-actions"><button class="btn outline" type="button" id="ns-cancel">Cancel</button><button class="btn" type="submit" id="ns-submit" ${!volumes.length?'disabled':''}>Create share</button></div></form></div></section>`;
 document.body.appendChild(overlay);const getPolicy=bindSharePermissionGroups(overlay);const close=()=>overlay.remove();overlay.querySelector('#ns-close').onclick=close;overlay.querySelector('#ns-cancel').onclick=close;
 overlay.querySelector('#ns-form').onsubmit=async e=>{e.preventDefault();const f=new FormData(e.target),msg=overlay.querySelector('#ns-message'),btn=overlay.querySelector('#ns-submit'),{access,public:publicShare,public_write:publicWrite}=getPolicy();if(!publicShare&&!Object.keys(access).length){msg.textContent='Assign access to at least one user.';return}btn.disabled=true;msg.textContent='Creating share…';try{await post('/api/nas-shares',{name:f.get('name'),volume:f.get('volume'),access,public:publicShare,public_write:publicWrite,admin_password:f.get('admin_password')});const j=await (await fetch('/api/state',{cache:'no-store'})).json();info=j.hardware||info;close();render()}catch(err){msg.textContent=err.message;btn.disabled=false}};
 overlay.querySelector('[name=name]').focus();
}
const FS_GUIDE={ext4:['Recommended for most users','Simple, reliable Linux filesystem. A good default for general NAS storage.'],xfs:['Large files and media','Well suited to large files and sustained throughput; shrinking is not supported.'],btrfs:['Snapshots and data integrity','Checksums and snapshots; more advanced maintenance and memory requirements.']};
const DISK_ACTION_ICONS={"wipe":"<svg viewBox=\"0 0 24 24\" width=\"22\" height=\"22\" aria-hidden=\"true\"><g fill=\"none\"><path fill=\"currentColor\" d=\"M18.34 20.81c.94 0 1.42 0 1.8-.1a3 3 0 0 0 2.1-2.1c.11-.4.11-.87.11-1.81s0-1.42-.1-1.81a3 3 0 0 0-2.1-2.1c-.4-.11-.87-.11-1.81-.11H5.66c-.94 0-1.42 0-1.8.1a3 3 0 0 0-2.1 2.1c-.11.4-.11.87-.11 1.82c0 .94 0 1.42.1 1.8a3 3 0 0 0 2.1 2.1c.4.11.87.11 1.81.11z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M18.34 20.81H5.66c-.94 0-1.42 0-1.8-.1a3 3 0 0 1-2.1-2.1c-.11-.4-.11-.87-.11-1.81s0-1.42.1-1.81a3 3 0 0 1 2.1-2.1c.4-.11.87-.11 1.81-.11h12.68c.94 0 1.42 0 1.8.1a3 3 0 0 1 2.1 2.1c.11.4.11.87.11 1.82c0 .94 0 1.42-.1 1.8a3 3 0 0 1-2.1 2.1c-.4.11-.87.11-1.81.11\"/><path fill=\"currentColor\" stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M5.79 16.24a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14m4.73 0a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M14.62 3.74L9.4 8.98m-.01-5.25l5.23 5.24\"/></g></svg>","format":"<svg viewBox=\"0 0 24 24\" width=\"22\" height=\"22\" aria-hidden=\"true\"><g fill=\"none\"><path fill=\"currentColor\" d=\"M18.34 20.25c.94 0 1.42 0 1.8-.11a3 3 0 0 0 2.1-2.1c.11-.4.11-.86.11-1.81s0-1.42-.1-1.81a3 3 0 0 0-2.1-2.1c-.4-.11-.87-.11-1.81-.11H5.66c-.94 0-1.42 0-1.8.1a3 3 0 0 0-2.1 2.11c-.11.39-.11.86-.11 1.8c0 .96 0 1.43.1 1.82a3 3 0 0 0 2.1 2.1c.4.1.87.1 1.81.1z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M5.64 12.21c-.93 0-1.39 0-1.77.1a3 3 0 0 0-2.12 2.13c-.1.38-.1.84-.1 1.78s0 1.43.1 1.82a3 3 0 0 0 2.1 2.1c.4.1.87.1 1.81.1h12.68c.94 0 1.42 0 1.8-.1a3 3 0 0 0 2.1-2.1c.11-.4.11-.87.11-1.82c0-.94 0-1.4-.1-1.78a3 3 0 0 0-2.12-2.13c-.38-.1-.84-.1-1.77-.1\"/><path fill=\"currentColor\" stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M5.79 15.67a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14m4.73 0a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M15.84 6.27c-1.36-1.78-2.7-2.12-3.78-2.12a3.96 3.96 0 1 0 2.78 6.78\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M16.36 3.75v.04c0 1.42 0 2.12-.44 2.56c-.43.44-1.14.44-2.56.44h-.04\"/></g></svg>","mount":"<svg viewBox=\"0 0 24 24\" width=\"22\" height=\"22\" aria-hidden=\"true\"><g fill=\"none\"><path fill=\"currentColor\" d=\"M18.34 20.81c.94 0 1.42 0 1.8-.1a3 3 0 0 0 2.1-2.1c.11-.4.11-.87.11-1.81s0-1.42-.1-1.81a3 3 0 0 0-2.1-2.1c-.4-.11-.87-.11-1.81-.11H5.66c-.94 0-1.42 0-1.8.1a3 3 0 0 0-2.1 2.1c-.11.4-.11.87-.11 1.82c0 .94 0 1.42.1 1.8a3 3 0 0 0 2.1 2.1c.4.11.87.11 1.81.11z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M18.34 20.81H5.66c-.94 0-1.42 0-1.8-.1a3 3 0 0 1-2.1-2.1c-.11-.4-.11-.87-.11-1.81s0-1.42.1-1.81a3 3 0 0 1 2.1-2.1c.4-.11.87-.11 1.81-.11h12.68c.94 0 1.42 0 1.8.1a3 3 0 0 1 2.1 2.1c.11.4.11.87.11 1.82c0 .94 0 1.42-.1 1.8a3 3 0 0 1-2.1 2.1c-.4.11-.87.11-1.81.11\"/><path fill=\"currentColor\" stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M5.79 16.24a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14m4.73 0a.57.57 0 1 1 0 1.14a.57.57 0 0 1 0-1.14\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M12 3.19v6.33M8.83 6.35h6.34\"/></g></svg>"};
function confirmDestructiveDisk(d,action){
 return new Promise(resolve=>{
  const formatting=action==='format';
  const title=formatting?'Format Disk':'Wipe Disk';
  const overlay=document.createElement('div');
  overlay.className='modal-overlay';
  const formatChoice=formatting?'<label class="field">Filesystem<select id="disk-danger-filesystem" required><option value="ext4">EXT4</option><option value="xfs">XFS</option><option value="btrfs">Btrfs</option></select></label>':'';
  const description=formatting?'This removes existing partition metadata and creates a new filesystem directly on the disk. All existing data will be lost.':'This removes the partition table and filesystem signatures. It is a quick wipe, NOT a secure overwrite; the old data may remain recoverable.';
  overlay.innerHTML='<section class="card settings-modal" role="dialog" aria-modal="true" aria-labelledby="disk-danger-title">'
   +'<div class="modal-heading"><h2 id="disk-danger-title">'+esc(title)+'</h2><button class="icon-btn" type="button" id="disk-danger-close" aria-label="Close">'+CANCEL_ICON+'</button></div>'
   +'<form id="disk-danger-form"><div class="settings-scroll">'
   +'<p class="danger"><strong>High risk: This operation causes irreversible filesystem data loss.</strong></p>'
   +'<p>'+esc(description)+'</p>'
   +'<p><strong>'+esc(d.model||d.name)+'</strong> · '+esc(d.path)+' · '+size(d.size)+'</p>'
   +formatChoice
   +'<label class="field disk-danger-consent"><span><input id="disk-danger-yes" type="checkbox" required> Yes, I understand that the selected disk may lose all its data.</span></label>'
   +'<label class="field">Administrator password<input id="disk-danger-password" type="password" maxlength="256" autocomplete="current-password" required></label>'
   +'<p class="small">Mounted disks, system disks, active RAID devices and disks referenced in fstab are protected.</p>'
   +'</div><div class="modal-actions"><button class="btn outline" id="disk-danger-cancel" type="button">Cancel</button>'
   +'<button class="btn danger" id="disk-danger-confirm" type="submit" disabled>Confirm '+esc(title)+'</button></div></form></section>';
  document.body.appendChild(overlay);
  const form=overlay.querySelector('#disk-danger-form');
  const check=overlay.querySelector('#disk-danger-yes');
  const password=overlay.querySelector('#disk-danger-password');
  const submit=overlay.querySelector('#disk-danger-confirm');
  const update=()=>{submit.disabled=!(check.checked&&password.value.length)};
  check.onchange=update;password.oninput=update;
  const done=value=>{document.removeEventListener('keydown',onKey);overlay.remove();resolve(value)};
  const onKey=event=>{if(event.key==='Escape')done(null)};
  document.addEventListener('keydown',onKey);
  overlay.querySelector('#disk-danger-close').onclick=()=>done(null);
  overlay.querySelector('#disk-danger-cancel').onclick=()=>done(null);
  overlay.onclick=event=>{if(event.target===overlay)done(null)};
  form.onsubmit=event=>{
   event.preventDefault();
   if(!check.checked||!password.value)return;
   const approval={admin_password:password.value,filesystem:formatting?overlay.querySelector('#disk-danger-filesystem').value:null};
   password.value='';
   done(approval);
  };
  password.focus();
 });
}
function openDiskWizard(index){
 const d=disks()[index];if(!d)return;
 const managedIssues=(info.managed_storage_health||[]).filter(item=>item.state!=='mounted');
 const overlay=document.createElement('div');overlay.className='modal-overlay';
 const options=[
  {title:'Wipe Disk',icon:'wipe',id:'disk-wipe',description:'Remove filesystem signatures and partition tables (quick wipe, not secure erase). Existing data will become inaccessible.',disabled:false},
  {title:'Format Disk',icon:'format',id:'disk-format',description:'Erase existing partitions and create an EXT4, XFS or Btrfs filesystem. All existing data will be lost.',disabled:false},
  {title:'Mount Disk',icon:'mount',id:'disk-mount',description:'Make the disk ready for NAS storage. Existing supported filesystems can be adopted without erasing data.',disabled:false}
 ];
 overlay.innerHTML=`<section class="card settings-modal storage-wizard" role="dialog" aria-modal="true" aria-label="Manage disk" tabindex="-1"><div class="modal-heading"><h2>Manage Disk</h2><button class="icon-btn" id="disk-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p><strong>${esc(d.model||d.name)}</strong> · ${size(d.size)} · ${esc(d.path)}</p>${managedIssues.length?'<p class="hint">One or more configured drives need attention. Check drive identity and mounts before adopting storage.</p>':''}${options.map((o,i)=>`<div class="disk-management-action"><div><strong>${esc(o.title)}</strong><p class="small">${esc(o.description)}</p>${o.disabled?`<p class="small">${esc(o.reason)}</p>`:''}</div><button class="btn ${o.id==='disk-mount'?'':'danger'} ${i===0?'outline':''} button-with-icon action-icon-btn" id="${o.id}" type="button">${DISK_ACTION_ICONS[o.icon]}<span>${esc(o.title)}</span></button></div>`).join('')}<div id="disk-mount-options" class="hidden"></div><div id="disk-message" role="status"></div></div><div class="modal-actions"><button class="btn outline" id="disk-cancel">Close</button></div></section>`;
 document.body.appendChild(overlay);const close=()=>{document.removeEventListener('keydown',onKey);overlay.remove()};const onKey=e=>{if(e.key==='Escape')close()};document.addEventListener('keydown',onKey);overlay.querySelector('#disk-close').onclick=close;overlay.querySelector('#disk-cancel').onclick=close;overlay.onclick=e=>{if(e.target===overlay)close()};
 const mountOptions=overlay.querySelector('#disk-mount-options');
 const diskMessage=overlay.querySelector('#disk-message');
 const renderMountOptions=function renderMountOptions(){
 const current=disks().find(item=>item.path===d.path);
 const eligible=(current?.volumes||[]).filter(v=>['ext4','xfs','btrfs'].includes(v.fs)&&v.uuid&&!v.read_only);
 mountOptions.innerHTML='<h3>Existing filesystems</h3>'+(eligible.length?eligible.map(v=>
  `<div class="storage-volume"><strong>${esc(v.fs.toUpperCase())}</strong> · ${esc(v.name)}
   <p class="small">${v.mounts.length?'Mounted at '+esc(v.mounts.join(', ')):'Not mounted'} · ${v.persistent?'Persistent':'Not configured for startup'}</p>
   ${!v.persistent||!v.mounts.length?`<button type="button" class="btn outline" data-adopt="${esc(v.path)}">Adopt without formatting</button>`:'<p class="hint">Ready for NAS shares.</p>'}</div>`).join(''):
  '<p class="hint">No supported existing filesystem with a UUID was found. Use Format Disk to create a supported filesystem first.</p>');
 mountOptions.querySelectorAll('[data-adopt]').forEach(btn=>btn.onclick=async()=>{
  const device=btn.dataset.adopt;
  const password=await fileTextDialog({title:'Authorise storage adoption',label:'Administrator password',description:'PiNAS will preserve existing files and configure a UUID-based mount. The device will not be formatted.',confirmLabel:'Configure storage',password:true});
  if(password===null)return;
  btn.disabled=true;
  diskMessage.textContent='Configuring storage…';
  try{
   const result=await post('/api/storage',{device,admin_password:password});
   const response=await fetch('/api/state',{cache:'no-store'});
   const updated=await response.json();
   if(!response.ok)throw Error(updated.error||'Unable to refresh storage');
   info=updated.hardware||info;
   diskMessage.textContent='Storage mounted at '+result.mount;
   close();render();
  }catch(error){diskMessage.textContent='Storage mount: '+error.message;btn.disabled=false;}
 });
};
 renderMountOptions();
 overlay.querySelector('#disk-mount').onclick=()=>{renderMountOptions();mountOptions.classList.toggle('hidden')};
 for(const action of ['wipe','format']){
  const button=overlay.querySelector('#disk-'+action);
  button.onclick=async()=>{
   const approved=await confirmDestructiveDisk(d,action);
   if(!approved)return;
   button.disabled=true;
   const message=overlay.querySelector('#disk-message');
   message.textContent=action==='format'?'Formatting selected disk…':'Removing partition and filesystem signatures…';
   try{
    const result=await post('/api/disk-destructive',{action,device:d.path,expected_size:Number(d.size),filesystem:approved.filesystem,confirm:true,admin_password:approved.admin_password});
    message.textContent=result.message||'Disk operation complete.';
    const response=await fetch('/api/state',{cache:'no-store'});
    const data=await response.json();
    if(!response.ok)throw Error(data.error||'Unable to refresh disks');
    info=data.hardware||info;
    renderMountOptions();
    if(action==='format'){
     mountOptions.classList.remove('hidden');
     message.textContent='Disk formatted. Choose Adopt without formatting below to mount it.';
    }else{
     mountOptions.classList.add('hidden');
     message.textContent='Disk wiped. Choose Format Disk to create a filesystem, then mount it.';
    }
   }catch(error){
    message.textContent='Disk operation: '+error.message;
   }finally{button.disabled=false}
  };
 }
 overlay.querySelector('.storage-wizard').focus();
}

async function readPinasServiceInstance(){
 const response=await fetch('/api/pinas-build',{cache:'no-store',credentials:'same-origin'});
 if(!response.ok)throw Error('PiNAS service identity is unavailable');
 const build=await response.json();
 if(typeof build.instance!=='string'||!build.instance)throw Error('Invalid PiNAS service identity');
 return build.instance;
}
function watchPinasUpgradeRestart(previousInstance,status,message,button){
 // The service restart clears login sessions. The read-only build endpoint
 // remains accessible, allowing a reload after a same-version upgrade too.
 let checks=0,busy=false;
 const timer=setInterval(async()=>{
  if(busy)return;
  busy=true;
  try{
   checks++;
   try{
    const current=await readPinasServiceInstance();
    if(current!==previousInstance){
     clearInterval(timer);
     window.location.reload();
     return;
    }
   }catch(error){/* Service may temporarily be offline during restart. */}
   try{
    const response=await fetch('/api/pinas-upgrade',{cache:'no-store'});
    if(response.ok){
     const update=await response.json();
     if(status.isConnected)status.textContent=update.message||update.state||'';
     if(update.state==='failed'||update.state==='rolled_back'){
      clearInterval(timer);
      if(message.isConnected)message.textContent=update.message||'PiNAS update failed. Review the update status.';
      if(button.isConnected)button.disabled=false;
      return;
     }
    }
   }catch(error){/* Authentication or connection may reset during update. */}
   if(checks>=120){
    clearInterval(timer);
    if(message.isConnected)message.textContent='Unable to confirm the restart automatically. Check that PiNAS is running, then refresh this page manually.';
    if(button.isConnected)button.disabled=false;
   }
  }finally{busy=false}
 },2500);
}
function openSettings(){
 const existing=document.getElementById('settings-overlay');if(existing)existing.remove();
 const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.id='settings-overlay';
 overlay.innerHTML=`<section class="card settings-modal" role="dialog" aria-modal="true" aria-labelledby="settings-title" tabindex="-1">
 <div class="modal-heading"><h2 id="settings-title">PiNAS Settings</h2><button class="icon-btn" id="settings-close" aria-label="Close settings">${CANCEL_ICON}</button></div>
 <div class="settings-scroll">
 <details class="settings-group"><summary>Appearance</summary><div class="settings-group-body">
 <label class="field">Font Size<select id="font"><option value="10">S — 10px</option><option value="12">M — 12px</option><option value="14">L — 14px</option><option value="16">XL — 16px</option></select></label>
 <label class="field">Theme<select id="theme"><option value="dark">Dark</option><option value="light">Light</option></select></label>

 </div></details><details class="settings-group"><summary>Device storage</summary><div class="settings-group-body"><div class="card compact-card" id="device-storage"><div class="disk-heading"><strong>PiNAS system storage</strong><span class="small" id="system-usage">—</span></div><div class="bar"><i id="system-storage-bar" style="width:0%"></i></div><p class="small">Reserved for the operating system, updates, settings and optional applications. Not available for NAS shares.</p></div>
 </div></details><details class="settings-group"><summary>CPU monitoring</summary><div class="settings-group-body">
 <label class="field">Sampling interval<select id="cpu_interval"><option value="2">2 seconds</option><option value="5">5 seconds</option><option value="10">10 seconds</option></select></label>
 <label class="field">CPU history<select id="cpu_history"><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label>
 </div></details><details class="settings-group"><summary>Security</summary><div class="settings-group-body"><p class="small">HTTPS is enabled by default. The browser may require you to trust the locally generated certificate.</p><label class="field">Session idle timeout<select id="session_timeout"><option value="5">5 minutes</option><option value="10">10 minutes</option><option value="15">15 minutes</option><option value="30">30 minutes</option><option value="60">60 minutes</option></select></label>
 </div></details><details class="settings-group"><summary>Login screen</summary><div class="settings-group-body"><label class="field">Background image (JPEG, PNG or WebP, max 2 MB)<input id="background" type="file" accept="image/jpeg,image/png,image/webp"></label>
 <button class="btn outline" id="clear">Remove background</button>
 </div></details><details class="settings-group"><summary>Administration</summary><div class="settings-group-body"><p class="small">Reset Samba to PiNAS defaults. A dated backup is created first. NAS data and managed share definitions are preserved; custom Samba configuration may be lost.</p><button class="btn outline" id="reset-smb">Reset SMB Configuration</button>
 </div></details><details class="settings-group"><summary>Configuration backup & recovery</summary><div class="settings-group-body"><p class="small">Download a recovery inventory containing safe PiNAS preferences, NAS user names and share definitions. No passwords or files are included. Restoring this file applies only appearance, monitoring, session settings and user display names; SMB accounts, shares, disks and RAID must be recovered separately.</p><button class="btn outline" type="button" id="download-config-backup">Download configuration backup</button><label class="field">Restore configuration settings from a PiNAS JSON backup<input type="file" accept=".json,application/json" id="restore-config-file"></label><button class="btn outline" type="button" id="restore-config-backup">Restore settings from file</button><p class="small" role="status" id="config-backup-status"></p></div></details><details class="settings-group"><summary>Update PiNAS</summary><div class="settings-group-body"><p class="small">Upload an official PiNAS Python release file (.py). The same file can also be installed from the command line. This operation replaces application code, not your NAS configuration or shared files. Only install releases from sources you trust.</p><label class="field">PiNAS update package<input type="file" id="update-file" accept=".py,text/x-python"></label><button class="btn outline button-with-icon action-icon-btn" id="apply-pinas-update" type="button"><svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><g fill="none"><rect width="19.17" height="19.17" fill="currentColor" opacity=".2" rx="3" transform="rotate(90 0 21.58)scale(-1 1)"/><rect width="19.17" height="19.17" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="3" transform="rotate(90 0 21.58)scale(-1 1)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17.7 8.57H13m-1.84 5.51v2.7m2.85-2.7v2.7M9.99 7.16v2.83m-1.71 5.44H6.3m11.4 0h-1.02M6.3 8.57h.92"/></g></svg><span>Install selected update</span></button><p class="small" id="pinas-update-status" role="status"></p>
 </div></details><div id="settings-message" role="status"></div></div>
 <div class="modal-actions"><button class="btn outline" id="settings-cancel">Cancel</button><button class="btn" id="save">Save settings</button></div></section>`;
 document.body.appendChild(overlay);
 const close=()=>{document.removeEventListener('keydown',onEscape);overlay.remove()},field=id=>overlay.querySelector('#'+id),msg=field('settings-message');
 field('settings-close').onclick=close;field('settings-cancel').onclick=close;
 field('download-config-backup').onclick=async()=>{const button=field('download-config-backup'),status=field('config-backup-status');const password=await fileTextDialog({title:'Authorise configuration backup',label:'Administrator password',description:'Export portable settings and a read-only NAS inventory. Passwords and files are not included.',confirmLabel:'Download backup',password:true});if(password===null)return;button.disabled=true;try{const result=await post('/api/config-backup',{admin_password:password});const content=JSON.stringify(result.backup,null,2);const blob=new Blob([content],{type:'application/json'});const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='pinas-settings-backup-'+new Date().toISOString().slice(0,10)+'.json';document.body.appendChild(link);link.click();link.remove();URL.revokeObjectURL(url);status.textContent='Backup downloaded. Store it securely with your NAS recovery records.'}catch(e){status.textContent=e.message}finally{button.disabled=false}};
 field('restore-config-backup').onclick=async()=>{const input=field('restore-config-file'),file=input.files[0],button=field('restore-config-backup'),status=field('config-backup-status');if(!file){status.textContent='Select a PiNAS JSON backup first.';return}if(file.size>1024*1024){status.textContent='Backup file exceeds the 1 MB limit.';return}let backup;try{backup=JSON.parse(await file.text())}catch(e){status.textContent='The selected file is not valid JSON.';return}if(backup?.format!=='pinas-configuration-v1'||backup?.restore_scope!=='settings-and-display-names-only'){status.textContent='Not a supported PiNAS settings backup.';return}const password=await fileTextDialog({title:'Restore PiNAS settings',label:'Administrator password',description:'Restore only display names and device preferences from this backup. Existing accounts, shares, disks, RAID and files will not be changed. Continue?',confirmLabel:'Restore settings',password:true});if(password===null)return;button.disabled=true;try{const result=await post('/api/config-restore',{admin_password:password,confirm:'RESTORE SETTINGS',backup});status.textContent=result.message;Object.assign(cfg,result.settings||{});apply()}catch(e){status.textContent=e.message}finally{button.disabled=false}};
 field('reset-smb').onclick=()=>{const panel=document.createElement('div');panel.className='modal-overlay';panel.innerHTML='<section class="card settings-modal" role="dialog" aria-modal="true" aria-label="Confirm SMB reset" tabindex="-1"><h2>Reset SMB Configuration</h2><p class="hint">Reset Samba configuration? Custom Samba settings and unmanaged shares will be removed from the active configuration. Data files will not be deleted.</p><label class="field">Administrator password<input type="password" id="smb-reset-password" autocomplete="current-password"></label><p id="smb-reset-error" role="status"></p><div class="modal-actions"><button class="btn outline" id="smb-reset-cancel">Cancel</button><button class="btn" id="smb-reset-confirm">Reset configuration</button></div></section>';document.body.appendChild(panel);const cancel=()=>panel.remove();panel.querySelector('#smb-reset-cancel').onclick=cancel;panel.onclick=e=>{if(e.target===panel)cancel()};panel.addEventListener('keydown',e=>{if(e.key==='Escape'){e.stopPropagation();cancel()}});panel.querySelector('#smb-reset-confirm').onclick=async()=>{const btn=panel.querySelector('#smb-reset-confirm');btn.disabled=true;try{const result=await post('/api/reset-smb',{confirm:'RESET SMB CONFIGURATION',admin_password:panel.querySelector('#smb-reset-password').value});msg.textContent='SMB configuration reset. Backup: '+result.backup;cancel()}catch(e){panel.querySelector('#smb-reset-error').textContent=e.message;btn.disabled=false}};panel.querySelector('#smb-reset-password').focus()};
 overlay.onclick=e=>{if(e.target===overlay)close()};
 const onEscape=e=>{if(e.key==='Escape')close()};
 document.addEventListener('keydown',onEscape);
 const system=info.system_storage||{};field('system-usage').textContent=system.total?`${size(system.used)} used · ${size(system.free)} available of ${size(system.total)}`:'Unavailable';field('system-storage-bar').style.width=(system.percent||0)+'%';
 field('theme').value=cfg.theme==='dark'?'dark':'light';
 field('font').value=[10,12,14,16].includes(cfg.font)?cfg.font:12;

 field('cpu_interval').value=cfg.cpu_interval||5;field('cpu_history').value=cfg.cpu_history||10;field('session_timeout').value=cfg.session_timeout||5;
 field('save').onclick=async()=>{try{let j=await post('/api/settings',{theme:field('theme').value,font:Number(field('font').value),cpu_interval:Number(field('cpu_interval').value),cpu_history:Number(field('cpu_history').value),session_timeout:Number(field('session_timeout').value)});cfg=j.settings;lastUserAction=Date.now();lastActivitySync=lastUserAction;apply();render();close()}catch(e){msg.textContent=e.message}};
 field('clear').onclick=async()=>{try{let j=await post('/api/background',{image:''});cfg=j.settings;apply();msg.textContent='Background removed'}catch(e){msg.textContent=e.message}};
 field('background').onchange=e=>{let f=e.target.files[0];if(!f)return;if(f.size>2*1024*1024){msg.textContent='Maximum image size is 2 MB';return}let reader=new FileReader();reader.onload=async()=>{try{let j=await post('/api/background',{image:reader.result});cfg=j.settings;apply();msg.textContent='Background updated'}catch(err){msg.textContent=err.message}};reader.readAsDataURL(f)};
 field('update-file').onchange=e=>{const f=e.target.files[0];msg.textContent=f?'Selected '+f.name+' ('+Math.round(f.size/1024)+' KiB)':''};
 field('apply-pinas-update').onclick=async()=>{
   const f=field('update-file').files[0];if(!f){msg.textContent='Choose a PiNAS .py release first';return}
   if(!f.name.endsWith('.py')||f.size>2*1024*1024){msg.textContent='Only Python release files up to 2 MB are supported';return}
   const pw=await fileTextDialog({title:'Authorise PiNAS update',label:'Administrator password',description:'Replace the PiNAS application and restart its service. Current sessions will be disconnected.',confirmLabel:'Install update',password:true});
   if(pw===null)return;
   const button=field('apply-pinas-update');button.disabled=true;msg.textContent='Validating and scheduling update…';
   try{
     const data=await new Promise((resolve,reject)=>{const reader=new FileReader();reader.onload=()=>resolve(String(reader.result).split(',')[1]);reader.onerror=()=>reject(Error('Cannot read file'));reader.readAsDataURL(f)});
     const hashBuffer=await crypto.subtle.digest('SHA-256',await f.arrayBuffer());
     const sha256=Array.from(new Uint8Array(hashBuffer),v=>v.toString(16).padStart(2,'0')).join('');
     const previousInstance=await readPinasServiceInstance();
     await post('/api/pinas-upgrade',{admin_password:pw,filename:f.name,sha256,package_b64:data});
     msg.textContent='Update accepted. PiNAS will restart automatically. This page will refresh once the service reconnects; you may need to sign in again.';
     watchPinasUpgradeRestart(previousInstance,field('pinas-update-status'),msg,button);
   }catch(e){msg.textContent=e.message;button.disabled=false}
 };
 overlay.querySelector('.settings-modal').focus();
}
const FILE_ICONS={folder:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/>',file:'<path d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h6"/>',up:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="m9 14 3-3 3 3m-3-3v7"/>',plus:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M12 11v7m-3.5-3.5h7"/>',upload:'<path d="M6 2h8l6 6v12a2 2 0 0 1-2 2H6a2 2 0 0 1-2-2V4a2 2 0 0 1 2-2Z"/><path d="M14 2v6h6m-8 11v-8m-3 3 3-3 3 3"/>',refresh:'<path d="M3 7a2 2 0 0 1 2-2h5l2 2h7a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H5a2 2 0 0 1-2-2Z"/><path d="M8 15a4 4 0 0 1 7-2m0-3v3h-3m4 3a4 4 0 0 1-7 2m0 3v-3h3"/>',gear:'<circle cx="12" cy="12" r="3"/><path d="M19 13.5a2 2 0 0 0 0-3l1-2-3-3-2 1a2 2 0 0 0-3-1l-1-2H9l-1 2a2 2 0 0 0-3 1l-2-1-2 3 1 2a2 2 0 0 0 0 3l-1 2 3 3 2-1a2 2 0 0 0 3 1l1 2h3l1-2a2 2 0 0 0 3-1l2 1 2-3Z"/>'};
const TOOLBAR_SVGS={"up":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M22.23 15.94c0 1.18 0 1.77-.16 2.25a3 3 0 0 1-1.86 1.86c-.48.16-1.08.16-2.28.16H7.7c-2.83 0-4.25 0-5.13-.88s-.87-2.3-.87-5.12V7.47c0-.66 0-.98.05-1.26a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05h1.07c1.09 0 1.63 0 2.14.19c.5.18.91.54 1.75 1.25l.4.34c.83.7 1.24 1.06 1.74 1.24c.5.19 1.05.19 2.14.19h1.6c2.82 0 4.24 0 5.11.88c.88.87.88 2.29.88 5.12z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.23 11.44c0-1.4 0-2.1-.23-2.66a3 3 0 0 0-1.62-1.62c-.55-.23-1.25-.23-2.65-.23H14.2c-1.04 0-1.56 0-2.04-.16l-.22-.09c-.47-.2-.85-.56-1.61-1.27c-.76-.7-1.15-1.06-1.61-1.26l-.22-.09c-.48-.17-1-.17-2.04-.17h-2.2A2.57 2.57 0 0 0 1.7 6.46v7.75c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h5.95m5.84-5.31v6.2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m22.55 17.04l-.94-.95c-1-1-1.5-1.5-2.12-1.5s-1.12.5-2.12 1.5l-.95.95\"/></g>","refresh":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M14.47 20.18h.35a3 3 0 0 1 1.3.38l.29.18l.4.24a3 3 0 0 0 1.7.34l.45-.07l.4-.07l.27-.05a3 3 0 0 0 1.28-.64l.21-.19c.16-.14.23-.2.3-.28a3 3 0 0 0 .81-1.86V12.9c0-2.82 0-4.24-.87-5.12c-.88-.88-2.3-.88-5.12-.88h-1.6c-1.1 0-1.64 0-2.14-.18c-.5-.19-.92-.54-1.75-1.25l-.4-.34c-.84-.71-1.26-1.06-1.76-1.25S7.54 3.7 6.45 3.7H5.4c-.67 0-1 0-1.28.05a3 3 0 0 0-2.39 2.39c-.05.27-.05.6-.05 1.27v6.76c0 2.83 0 4.24.88 5.12s2.3.88 5.12.88z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.24 9.89a3 3 0 0 0-3-3h-5.05c-1.04 0-1.56 0-2.05-.17l-.2-.08c-.48-.2-.86-.56-1.62-1.27S9.17 4.29 8.7 4.09L8.5 4c-.48-.16-1-.16-2.05-.16h-2.2A2.57 2.57 0 0 0 1.67 6.4v7.77c0 2.83 0 4.24.88 5.12s2.3.88 5.12.88h2.79\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M21.77 15.87c-.93-1.32-2.05-2.22-3.64-2.22q-2.38 0-3.48 2.06m.2 3.49c.93 1.3 2.04 2.22 3.63 2.22q2.38 0 3.48-2.07\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m22.28 13.48l-.04.82c-.06.94-.08 1.42-.4 1.7c-.3.27-.77.24-1.72.18l-.82-.04m-4.99 5.3l.05-.68c.06-.94.09-1.41.4-1.69c.31-.27.78-.24 1.72-.18l.68.05\"/></g>","plus":"<path d=\"M0 0h24v24H0z\" fill=\"none\"/><g fill=\"none\"><path fill=\"currentColor\" d=\"M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V7.5c0-.65 0-.98.05-1.25a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05H6.5c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.39.33c.83.71 1.25 1.06 1.75 1.25s1.05.18 2.14.18h1.56c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V6.5a2.56 2.56 0 0 1 2.56-2.56H6.5c1.04 0 1.55 0 2.03.16l.23.1c.46.2.84.55 1.6 1.25s1.14 1.06 1.6 1.26l.23.1c.47.16 1 .16 2.03.16h2.01c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12zM8.7 13.58h6.6M12 16.89v-6.6\"/></g>","upload":"<path d=\"M0 0h24v24H0z\" fill=\"none\" /><g fill=\"none\"><path fill=\"currentColor\" d=\"M7.72 22.24c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.52-.58-3.41V5.78c0-1.87 0-2.8.57-3.38c.58-.59 1.52-.6 3.38-.62l2.24-.02c1.3-.02 1.96-.02 2.44.27a2 2 0 0 1 .69.67c.29.48.29 1.14.29 2.44s0 1.95.29 2.42q.25.42.67.68c.48.29 1.13.29 2.42.29c1.3 0 1.95 0 2.43.29q.41.26.67.67c.3.48.3 1.13.3 2.43v6.32c0 1.89 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\" opacity=\".2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.1 12.82v-2.56c0-1.25 0-1.87-.24-2.43s-.68-1-1.57-1.87L17.1 4.81l-1.24-1.23c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23h-1.9c-2.83 0-4.25 0-5.13.88S3.72 5 3.72 7.82v8.42c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h2.94\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.13 2.34v2.45c0 1.9 0 2.84.58 3.42s1.53.59 3.42.59h2.46m-1.29 7.94v6.2m3.07-4.07l-.94-.94c-1-1-1.5-1.5-2.13-1.5s-1.12.5-2.12 1.5l-.95.94\" /></g>"};
const ACTION_SVGS={"rename":"<path d=\"M7.67 22.24c-1.89 0-2.83 0-3.42-.59s-.58-1.53-.58-3.41V5.74c0-1.87 0-2.8.58-3.38c.57-.59 1.5-.6 3.38-.62l2.24-.02c1.31-.01 1.97-.02 2.45.27q.42.25.68.67c.3.48.3 1.14.3 2.45c0 1.3 0 1.95.29 2.43q.25.41.67.67c.48.3 1.13.3 2.43.3s1.95 0 2.43.28q.41.26.67.67c.3.48.3 1.13.3 2.43v2.96l-4.85 4.46l-1.14 2.93z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.08 11.28v-1.05c0-1.25 0-1.87-.23-2.43s-.69-1-1.58-1.87l-1.19-1.15l-1.24-1.24c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23H9.67c-2.83 0-4.24 0-5.12.88s-.88 2.3-.88 5.12v8.46c0 2.82 0 4.24.88 5.12s2.29.88 5.12.88h.48\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.1 2.3v2.47c0 1.88 0 2.83.58 3.41s1.53.59 3.41.59h2.48\"/><rect width=\"2.36\" height=\"2.64\" fill=\"currentColor\" opacity=\".2\" rx=\"1\" transform=\"rotate(135 6.603 13.18)scale(-1 1)\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"m20.59 17.84l-1.78-1.77m-3.66 6.53c.55-.12.83-.18 1.07-.3l.03-.02c.24-.14.44-.33.84-.72l4.54-4.46c.31-.3.47-.46.54-.63a1 1 0 0 0 0-.81c-.07-.18-.22-.33-.53-.64s-.47-.47-.64-.54a1 1 0 0 0-.8 0c-.18.07-.33.23-.64.54l-4.51 4.5c-.4.38-.6.58-.73.82l-.02.05c-.13.24-.19.5-.3 1.05c-.15.65-.22.97-.05 1.16l.04.04c.19.17.51.1 1.16-.04\"/>","copy":"<path fill=\"currentColor\" d=\"M13.09 11.27c-.1-.48-.16-.72-.26-.94a2 2 0 0 0-.25-.38a4 4 0 0 0-.74-.64l-.08-.06c-.62-.47-.94-.71-1.13-1.03l-.16-.32c-.13-.35-.13-.74-.13-1.53V5.5c0-1.1 0-1.66.2-2.09a2 2 0 0 1 .88-.87c.42-.22.98-.23 2.08-.24h1.3a2 2 0 0 1 1.93 2.1v.18a2 2 0 0 0 1.92 1.92h.78a2 2 0 0 1 1.8 1.8v1.92c0 1.64 0 2.46-.45 3.01a2 2 0 0 1-.31.31c-.56.44-1.38.43-3.02.4l-1.13-.02c-1.03-.01-1.54-.02-1.96-.23a2 2 0 0 1-.66-.54c-.29-.37-.4-.87-.61-1.88\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M19 17.68v.29c0 1.63 0 2.44-.45 2.99a2 2 0 0 1-.3.3c-.54.44-1.36.44-2.98.44\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M21 18.35c-.88-.88-1.32-1.33-1.86-1.38h-.28c-.54.05-.98.5-1.86 1.38M8.6 7.37v.25c-.01 1.89-.01 2.83.57 3.42c.59.58 1.53.58 3.42.58h.26m3.52-9.08v.25c0 1.89 0 2.83.58 3.42c.59.59 1.53.59 3.42.59h.26\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M6.77 18.76c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.53-.58-3.41v-3.4c0-1.88 0-2.82.58-3.4c.59-.6 1.53-.6 3.42-.6h1.46c.72 0 1.08 0 1.4.13c.34.12.61.35 1.17.8l.88.74l.52.43c.72.59 1.08.89 1.27 1.3c.2.4.2.87.2 1.8v2.2c0 1.88 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.86 14h3.37c1.89 0 2.83 0 3.42-.58c.58-.59.58-1.53.58-3.42V7.57c0-.91 0-1.37-.19-1.78c-.18-.4-.54-.7-1.24-1.28l-.56-.47l-.87-.75a4 4 0 0 0-1.17-.84c-.33-.12-.7-.12-1.43-.12h-1.43c-1.89 0-2.83 0-3.42.59c-.58.58-.58 1.52-.58 3.41v1.42\"/>","move":"<path fill=\"currentColor\" d=\"M7.8 22.23c-1.9 0-2.83 0-3.42-.59c-.59-.58-.59-1.53-.59-3.41V5.73c0-1.86 0-2.8.58-3.38s1.51-.6 3.38-.61L10 1.7c1.3-.01 1.97-.02 2.45.27q.42.26.68.67c.3.48.3 1.14.3 2.45c0 1.3 0 1.95.28 2.43q.26.42.67.67c.48.3 1.13.3 2.43.3s1.96 0 2.44.29q.41.26.66.66c.3.48.3 1.13.3 2.44v6.34c0 1.88 0 2.83-.59 3.41s-1.53.59-3.41.59z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M3.8 7.78v8.45c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.12.88h4.42c2.82 0 4.24 0 5.12-.88s.88-2.3.88-5.12v-6c0-1.25 0-1.88-.24-2.44s-.68-1-1.58-1.86l-1.18-1.16l-1.25-1.24c-.86-.87-1.3-1.3-1.85-1.53s-1.16-.22-2.38-.22H9.79c-2.82 0-4.24 0-5.12.87c-.88.88-.88 2.3-.88 5.13\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.22 2.3v2.46c0 1.89 0 2.83.58 3.42c.59.58 1.53.58 3.42.58h2.47m-6.23 9.73l.32-.32c1.33-1.34 2-2 2-2.83s-.66-1.5-2-2.83l-.32-.33m-5.61 3.15h7.8\"/>","delete":"<path fill=\"currentColor\" d=\"M7.85 22.2c-1.89 0-2.83 0-3.42-.58c-.58-.59-.58-1.53-.58-3.41V5.84c0-1.87 0-2.8.57-3.39c.58-.58 1.52-.59 3.38-.6l2.2-.03c1.3-.01 1.95-.02 2.43.26a2 2 0 0 1 .7.7c.28.47.28 1.12.28 2.4c0 1.29 0 1.93.29 2.4a2 2 0 0 0 .69.7c.47.28 1.11.28 2.4.28s1.92 0 2.39.28a2 2 0 0 1 .7.7c.27.47.27 1.1.27 2.39v6.28c0 1.88 0 2.82-.58 3.41c-.59.59-1.53.59-3.42.59z\" opacity=\".2\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M3.85 7.88v8.33c0 2.82 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h4.3c2.83 0 4.25 0 5.13-.88s.87-2.3.87-5.12v-5.92c0-1.25 0-1.87-.23-2.43s-.68-1-1.58-1.87l-1.16-1.13l-1.23-1.22c-.87-.87-1.3-1.3-1.85-1.53s-1.16-.23-2.39-.23H9.85c-2.83 0-4.25 0-5.13.88s-.87 2.3-.87 5.12\"/><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.21 2.4v2.42c0 1.89 0 2.83.58 3.42c.6.59 1.53.59 3.42.59h2.43M8.5 15.3h7\"/>"};
ACTION_SVGS.download="<path fill=\"currentColor\" d=\"M7.72 22.24c-1.89 0-2.83 0-3.42-.59c-.58-.58-.58-1.52-.58-3.41V5.78c0-1.87 0-2.8.57-3.38c.58-.59 1.52-.6 3.38-.62l2.24-.02c1.3-.02 1.96-.02 2.44.27a2 2 0 0 1 .69.67c.29.48.29 1.14.29 2.44s0 1.95.29 2.42q.25.42.67.68c.48.29 1.13.29 2.42.29c1.3 0 1.95 0 2.43.29q.41.26.67.67c.3.48.3 1.13.3 2.43v6.32c0 1.89 0 2.83-.6 3.41c-.58.59-1.52.59-3.4.59z\" opacity=\".2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M20.1 12.66v-2.4c0-1.25 0-1.87-.24-2.43s-.68-1-1.57-1.87L17.1 4.81l-1.24-1.23c-.87-.87-1.3-1.3-1.85-1.53s-1.17-.23-2.39-.23h-1.9c-2.83 0-4.25 0-5.13.88S3.72 5 3.72 7.82v8.42c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h2.2\" /><path stroke=\"currentColor\" stroke-linecap=\"round\" stroke-linejoin=\"round\" stroke-width=\"1.5\" d=\"M13.13 2.34v2.45c0 1.9 0 2.84.58 3.42s1.53.59 3.42.59h2.46M18.3 22.4v-6.2m3.07 4.07l-.94.94c-1 1-1.5 1.5-2.13 1.5s-1.12-.5-2.12-1.5l-.95-.94\" />";
const actionIcon=(name)=>`<svg viewBox="0 0 24 24" width="24" height="24" fill="none" aria-hidden="true">${ACTION_SVGS[name]}</svg>`;
const PINAS_BRAND_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="27" height="27" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><rect width="6.11" height="20.43" x="1.78" y="9" fill="currentColor" opacity=".2" rx="2" transform="rotate(-90 1.78 9)"/><rect width="6.11" height="20.43" x="1.78" y="21.23" fill="currentColor" opacity=".2" rx="2" transform="rotate(-90 1.78 21.23)"/><rect width="6.11" height="20.43" x="1.78" y="9" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 9)"/><rect width="6.11" height="20.43" x="1.78" y="15.11" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 15.11)"/><rect width="6.11" height="20.43" x="1.78" y="21.23" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" rx="2" transform="rotate(-90 1.78 21.23)"/><path fill="currentColor" stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M5.83 5.94a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m0 6.12a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m0 6.11a.41.41 0 1 1-.83 0a.41.41 0 0 1 .83 0m4.1-12.23a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0m0 6.12a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0m0 6.11a.41.41 0 1 1-.82 0a.41.41 0 0 1 .82 0"/></g></svg>`;
const LOGOFF_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none" /><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2" /><path fill="currentColor" d="M18.38 21.84H1.78a8.4 8.4 0 0 1 8.3-8.46c4.58 0 8.3 3.79 8.3 8.46" opacity=".2" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.78 21.68a8.3 8.3 0 0 1 11.11-7.8m3.49 1.58h5.33m-.15 5.14h-5.33m4.62-7.1l.55.55c.67.66 1 1 1 1.41c0 .42-.33.75-1 1.42l-.55.55m-3.75 1.19l-.55.55c-.67.67-1 1-1 1.42s.33.75 1 1.41l.55.56" /></g></svg>`;
const CANCEL_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><path fill="currentColor" fill-rule="evenodd" d="M7.345 4.017a42.3 42.3 0 0 1 9.31 0c1.713.192 3.095 1.541 3.296 3.26a40.7 40.7 0 0 1 0 9.446c-.201 1.719-1.583 3.068-3.296 3.26a42.3 42.3 0 0 1-9.31 0c-1.713-.192-3.095-1.541-3.296-3.26a40.7 40.7 0 0 1 0-9.445a3.734 3.734 0 0 1 3.295-3.26M8.47 8.47a.75.75 0 0 1 1.06 0L12 10.94l2.47-2.47a.75.75 0 1 1 1.06 1.06L13.06 12l2.47 2.47a.75.75 0 0 1-1.06 1.06L12 13.06l-2.47 2.47a.75.75 0 1 1-1.06-1.06L10.94 12L8.47 9.53a.75.75 0 0 1 0-1.06" clip-rule="evenodd"/></svg>`;
const DELETE_FOLDER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="m20.07 17.98l-.36.38c-.88.91-1.31 1.37-1.88 1.6c-.56.25-1.2.25-2.46.25H7.7c-2.83 0-4.25 0-5.13-.88s-.87-2.3-.87-5.12V7.47c0-.66 0-.98.05-1.26a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05h1.07c1.09 0 1.63 0 2.14.19c.5.18.91.54 1.75 1.25l.4.34c.83.7 1.24 1.06 1.74 1.24c.5.19 1.05.19 2.14.19h1.6c2.82 0 4.24 0 5.11.88c.88.87.88 2.29.88 5.12v.38c0 1.28 0 1.92-.24 2.49c-.25.57-.72 1-1.65 1.88z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M22.23 10.88c0-.88 0-1.32-.09-1.68a3 3 0 0 0-2.17-2.17c-.36-.1-.8-.1-1.69-.1H14.2c-1.04 0-1.56 0-2.04-.16l-.22-.09c-.47-.2-.85-.56-1.61-1.27c-.76-.7-1.15-1.06-1.61-1.26l-.22-.09c-.48-.17-1-.17-2.04-.17h-2.2A2.57 2.57 0 0 0 1.7 6.46v7.75c0 2.83 0 4.24.87 5.12c.88.88 2.3.88 5.13.88h5.23m4.15-5.45l5.53 5.53m-5.53 0l5.52-5.53"/></g></svg>`;

const CREATE_SHARE_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V7.5c0-.65 0-.98.05-1.25a3 3 0 0 1 2.4-2.4c.27-.05.6-.05 1.25-.05H6.5c1.1 0 1.64 0 2.14.18c.5.19.92.54 1.75 1.25l.39.33c.83.71 1.25 1.06 1.75 1.25s1.05.18 2.14.18h1.56c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12z" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M22.24 14.2c0 2.83 0 4.24-.88 5.12s-2.3.88-5.12.88H7.76c-2.83 0-4.24 0-5.12-.88s-.88-2.3-.88-5.12V6.5a2.56 2.56 0 0 1 2.56-2.56H6.5c1.04 0 1.55 0 2.03.16l.23.1c.46.2.84.55 1.6 1.25s1.14 1.06 1.6 1.26l.23.1c.47.16 1 .16 2.03.16h2.01c2.83 0 4.24 0 5.12.88s.88 2.3.88 5.12zM8.7 13.58h6.6M12 16.89v-6.6"/></g></svg>`;
const EDIT_SHARE_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" fill="none" aria-hidden="true"><path d="M4 20h16M6 16.5l.4-3.3L16.7 2.9a2.2 2.2 0 0 1 3.1 3.1L9.5 16.3 6 16.5Z" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/></svg>`;
const ADD_USER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2"/><path fill="currentColor" d="M18.38 21.84H1.78a8.4 8.4 0 0 1 8.3-8.46c4.58 0 8.3 3.79 8.3 8.46" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4m-.45 10.71h7.16m-3.58 3.58v-7.16"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.78 21.68a8.3 8.3 0 0 1 12.32-7.26"/></g></svg>`;
const REMOVE_USER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2"/><path fill="currentColor" d="M17.44 21.84H1.77a8.4 8.4 0 0 1 8.3-8.46c2.9 0 5.44 1.5 6.93 3.8c2.31 1.26 2.22 2.26.44 4.66" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="m16.71 16.65l5.29 5.3m-5.29-.01L22 16.65m-6.53-8.66a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M1.78 21.62a8.3 8.3 0 0 1 11.28-7.74"/></g></svg>`;
const EDIT_USER_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none"/><g fill="none"><path fill="currentColor" d="M15.47 7.99a5.4 5.4 0 1 1-10.79 0a5.4 5.4 0 0 1 10.8 0" opacity=".2"/><path fill="currentColor" d="M14.09 21.84H1.77a8.4 8.4 0 0 1 8.3-8.46c2.9 0 5.44 1.5 6.93 3.8c-1.59 1.38-3.2 2.89-2.91 4.66" opacity=".2"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M15.47 7.99a5.4 5.4 0 0 1-5.4 5.4a5.4 5.4 0 1 1 5.4-5.4"/><rect width="2.4" height="2.69" fill="currentColor" opacity=".2" rx="1" transform="rotate(-45 31.28 -16)scale(1 -1)"/><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="m20.47 17.45l-1.81-1.81m-3.72 6.65a4 4 0 0 0 1.1-.32c.25-.13.46-.34.87-.74l4.62-4.53c.33-.33.5-.5.57-.68a1 1 0 0 0 0-.77c-.07-.19-.23-.35-.56-.68a3 3 0 0 0-.67-.56a1 1 0 0 0-.77 0c-.19.07-.35.23-.67.56l-4.6 4.58a4 4 0 0 0-.76.87c-.13.25-.2.53-.31 1.09c-.15.67-.23 1-.04 1.2l.01.01c.2.19.53.11 1.2-.03M1.78 21.8a8.3 8.3 0 0 1 12.32-7.25"/></g></svg>`;
const SETTINGS_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="24" height="24" viewBox="0 0 24 24" aria-hidden="true"><path d="M0 0h24v24H0z" fill="none" /><g fill="none"><path fill="currentColor" fill-rule="evenodd" d="M1.48 12.67c0 .94 0 1.41.3 1.7c.29.3.76.3 1.7.3h1.45c.27 0 .4 0 .52.03a1 1 0 0 1 .47.27c.09.09.16.2.29.43s.2.35.23.47a1 1 0 0 1 0 .54c-.03.12-.1.24-.23.47l-.67 1.15c-.47.82-.7 1.23-.6 1.63c.11.4.52.63 1.34 1.1l.95.55c.81.47 1.22.7 1.62.6s.64-.51 1.1-1.33l.41-.7c.24-.4.35-.6.53-.73l.16-.1c.2-.09.43-.09.9-.09c.45 0 .69 0 .88.1l.17.09c.17.12.29.32.52.72l.4.7c.48.83.71 1.23 1.11 1.34c.4.1.81-.13 1.63-.6l.95-.55c.82-.47 1.22-.7 1.33-1.1c.1-.4-.13-.81-.6-1.63l-.41-.71c-.28-.5-.42-.74-.43-1q0-.15.04-.3c.07-.24.27-.44.67-.84c.22-.22.33-.33.46-.4l.17-.07c.15-.04.3-.04.62-.04h.82c.95 0 1.42 0 1.71-.3c.3-.29.3-.76.3-1.7v-1.1c0-.94 0-1.41-.3-1.7s-.76-.3-1.7-.3h-.83c-.32 0-.47 0-.62-.04l-.17-.08a2 2 0 0 1-.46-.4c-.4-.4-.6-.6-.67-.84a1 1 0 0 1-.04-.3c0-.26.15-.5.43-.99l.41-.71c.47-.82.7-1.23.6-1.63s-.51-.64-1.33-1.1l-.95-.55c-.82-.48-1.23-.71-1.63-.6s-.63.51-1.1 1.33l-.41.7c-.23.4-.35.6-.52.73l-.17.1c-.2.08-.43.08-.89.08s-.7 0-.89-.09l-.16-.1c-.18-.12-.3-.32-.53-.72l-.4-.7c-.47-.82-.71-1.23-1.11-1.33s-.8.12-1.62.6l-.95.54c-.82.47-1.23.71-1.34 1.11c-.1.4.13.8.6 1.63l.67 1.15c.13.23.2.34.23.46a1 1 0 0 1 0 .55c-.03.12-.1.23-.23.46s-.2.35-.29.44a1 1 0 0 1-.47.27c-.12.03-.25.03-.52.03H3.48c-.94 0-1.41 0-1.7.3c-.3.29-.3.76-.3 1.7zm7.8-.55a2.87 2.87 0 1 0 5.75 0a2.87 2.87 0 0 0-5.75 0" clip-rule="evenodd" opacity=".2" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M12.15 9.24a2.87 2.87 0 0 0-2.87 2.88a2.87 2.87 0 1 0 2.87-2.88" /><path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M4.03 14.67h.9a1.47 1.47 0 0 1 1.28 2.2l-.4.69a6 6 0 0 0-.44.86a2 2 0 0 0 .56 2.09c.16.14.38.27.82.53l.08.05c.37.2.55.31.72.37a2 2 0 0 0 2.2-.6c.12-.13.22-.3.43-.67l.18-.32a1.82 1.82 0 0 1 3.16 0l.18.32c.21.36.32.54.43.68a2 2 0 0 0 2.2.59c.18-.06.36-.16.72-.37l.24-.14c.3-.17.44-.26.56-.35a2 2 0 0 0 .62-2.31a5 5 0 0 0-.31-.58l-.23-.4a1.77 1.77 0 0 1 1.53-2.64h.3c.49 0 .73 0 .93-.04a2 2 0 0 0 1.55-1.56c.04-.2.04-.44.04-.92v-.06c0-.48 0-.72-.04-.92A2 2 0 0 0 20.7 9.6c-.2-.04-.44-.04-.92-.04h-.31a1.77 1.77 0 0 1-1.53-2.65l.23-.4c.17-.3.25-.44.3-.57a2 2 0 0 0-.61-2.32a5 5 0 0 0-.56-.34l-.24-.14c-.36-.2-.54-.31-.71-.37a2 2 0 0 0-2.2.59a5 5 0 0 0-.44.68l-.18.31a1.82 1.82 0 0 1-3.16 0l-.18-.31a5 5 0 0 0-.43-.68a2 2 0 0 0-2.2-.6a7 7 0 0 0-.72.38l-.08.05c-.44.25-.66.38-.82.53a2 2 0 0 0-.56 2.08c.07.2.2.43.45.87l.39.68a1.48 1.48 0 0 1-1.28 2.21h-.9c-.51 0-.77 0-.98.05a2 2 0 0 0-1.52 1.52c-.05.21-.05.47-.05.98c0 .5 0 .76.05.97a2 2 0 0 0 1.52 1.53c.21.05.47.05.98.05" /></g></svg>`;

const fileIcon=(name,size=22)=>`<svg viewBox="0 0 24 24" width="${size}" height="${size}" fill="none" ${TOOLBAR_SVGS[name]?'':'stroke="currentColor" stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round"'} aria-hidden="true">${TOOLBAR_SVGS[name]||FILE_ICONS[name]}</svg>`;
const DEFAULT_USER_AVATAR_ICON=`<svg xmlns="http://www.w3.org/2000/svg" width="1em" height="1em" viewBox="0 0 24 24" aria-hidden="true">
<path d="M0 0h24v24H0z" fill="none" />
<g fill="none">
<path fill="currentColor" fill-rule="evenodd" d="M19.56 21.3c.96 0 1.75-.78 1.75-1.74V8.69c0-2.82 0-4.24-.88-5.12s-2.3-.88-5.12-.88H8.69c-2.82 0-4.24 0-5.12.88S2.7 5.87 2.7 8.7v10.84a1.78 1.78 0 0 0 3.5.49l.43-1.5l.1-.34a3 3 0 0 1 .8-1.22l.27-.22c.31-.26.47-.38.6-.52a3 3 0 0 0 .73-2.84a7 7 0 0 0-.27-.74l-.17-.43l-.14-.36a3 3 0 0 1 .64-2.98l.2-.24a3 3 0 0 1 2.09-1H12c.42 0 .63 0 .82.02a3 3 0 0 1 2.2 1.46c.1.17.19.36.35.75l.2.49a2.7 2.7 0 0 1-.27 2.61a2.7 2.7 0 0 0 .56 3.7l.32.24l.05.05a3 3 0 0 1 .94 1.26l.02.06l.73 1.9c.26.69.9 1.14 1.64 1.14" clip-rule="evenodd" opacity=".2" />
<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M6.03 2.66h-.08l-.45.01a3 3 0 0 0-2.8 2.8v.45m15.28-3.26h.07l.45.01a3 3 0 0 1 2.8 2.8v.45M2.76 10.14v3.57m18.48-3.57v3.57M6.03 21.24H5.5a3 3 0 0 1-2.8-2.8V18m15.28 3.25h.52a3 3 0 0 0 2.8-2.8V18M5.75 21.24h12.5M10.22 2.67h3.57m2.03 8.73A3.8 3.8 0 0 1 12 15.22a3.82 3.82 0 1 1 3.82-3.82" />
<path stroke="currentColor" stroke-linecap="round" stroke-linejoin="round" stroke-width="1.5" d="M17.93 21.14a5.92 5.92 0 1 0-11.85 0" />
</g>
</svg>`;
function userAvatar(){return cfg.profile_avatar||''}
function userAvatarMarkup(styleClass){return userAvatar()? `<img class="${styleClass}" src="${esc(userAvatar())}" alt="Profile picture">` : `<span class="${styleClass} avatar-placeholder" role="img" aria-label="Default profile picture">${DEFAULT_USER_AVATAR_ICON}</span>`}
function updateAvatarPreview(avatar){const preview=document.getElementById('user-avatar-preview');if(preview)preview.innerHTML=avatar?`<img src="${esc(avatar)}" alt="Profile picture">`:DEFAULT_USER_AVATAR_ICON}

function openUserSettings(){const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.innerHTML=`<section class="card settings-modal" role="dialog" aria-modal="true" aria-labelledby="user-settings-title" tabindex="-1"><div class="modal-heading"><h2 id="user-settings-title">My Settings</h2><button class="icon-btn" id="user-settings-close" aria-label="Close">${CANCEL_ICON}</button></div><div class="settings-scroll"><p>These preferences belong to your NAS account.</p><label class="field">Profile picture<span id="user-avatar-preview" class="profile-preview avatar-placeholder" role="img" aria-label="Profile picture preview">${userAvatar()?`<img src="${esc(userAvatar())}" alt="Profile picture">`:DEFAULT_USER_AVATAR_ICON}</span><input type="file" id="user-avatar-input" accept="image/png,image/jpeg,image/webp"><span class="small">PNG, JPEG or WebP, maximum 256 KB.</span></label><button class="btn outline" id="user-avatar-remove" type="button">Remove picture</button><label class="field">Theme<select id="user-theme"><option value="light">Light</option><option value="dark">Dark</option></select></label><label class="field">Font size<select id="user-font"><option value="10">Small (10px)</option><option value="12">Medium (12px)</option><option value="14">Large (14px)</option><option value="16">Extra large (16px)</option></select></label><div id="user-settings-message" role="status"></div></div><div class="modal-actions"><button class="btn outline" id="user-settings-cancel">Cancel</button><button class="btn" id="user-settings-save">Save preferences</button></div></section>`;document.body.append(overlay);const get=id=>overlay.querySelector('#'+id),close=()=>overlay.remove();let avatar=userAvatar();get('user-theme').value=cfg.theme||'light';get('user-font').value=String(cfg.font||12);get('user-settings-close').onclick=close;get('user-settings-cancel').onclick=close;overlay.addEventListener('click',e=>{if(e.target===overlay)close()});get('user-avatar-remove').onclick=()=>{avatar='';updateAvatarPreview('')};get('user-avatar-input').onchange=e=>{const file=e.target.files[0];if(!file)return;if(file.size>256*1024||!['image/png','image/jpeg','image/webp'].includes(file.type)){get('user-settings-message').textContent='Choose a PNG, JPEG or WebP under 256 KB.';return}const reader=new FileReader();reader.onload=()=>{avatar=reader.result;updateAvatarPreview(avatar)};reader.readAsDataURL(file)};get('user-settings-save').onclick=async()=>{try{const result=await post('/api/user-preferences',{theme:get('user-theme').value,font:Number(get('user-font').value),avatar});cfg={...cfg,...result.preferences};apply();close();renderFiles()}catch(e){get('user-settings-message').textContent=e.message}};get('user-theme').focus()}
function fileTextDialog({title,label,initial='',description='',confirmLabel='Save',password=false}){return new Promise(resolve=>{const overlay=document.createElement('div');overlay.className='modal-overlay';overlay.innerHTML=`<section class="card settings-modal file-dialog" role="dialog" aria-modal="true" aria-labelledby="file-dialog-title" tabindex="-1"><div class="modal-heading"><h2 id="file-dialog-title">${esc(title)}</h2><button type="button" class="icon-btn" id="file-dialog-close" aria-label="Close">${CANCEL_ICON}</button></div><form id="file-dialog-form"><div class="settings-scroll">${description?`<p>${esc(description)}</p>`:''}<label class="field">${esc(label)}<input id="file-dialog-value" type="${password?'password':'text'}" required maxlength="${password?256:255}" autocomplete="${password?'current-password':'off'}" value="${esc(initial)}"></label><p id="file-dialog-error" role="status" class="small"></p></div><div class="modal-actions"><button type="button" class="btn outline" id="file-dialog-cancel">Cancel</button><button type="submit" class="btn">${esc(confirmLabel)}</button></div></form></section>`;document.body.append(overlay);const input=overlay.querySelector('#file-dialog-value');let finished=false;const done=v=>{if(finished)return;finished=true;document.removeEventListener('keydown',key);overlay.remove();resolve(v)};const key=e=>{if(e.key==='Escape'){e.preventDefault();done(null)}else if(e.key==='Tab'){const focusable=[...overlay.querySelectorAll('button:not([disabled]),input:not([disabled])')];if(!focusable.length)return;const first=focusable[0],last=focusable[focusable.length-1];if(e.shiftKey&&document.activeElement===first){e.preventDefault();last.focus()}else if(!e.shiftKey&&document.activeElement===last){e.preventDefault();first.focus()}}};document.addEventListener('keydown',key);overlay.querySelector('#file-dialog-close').onclick=()=>done(null);overlay.querySelector('#file-dialog-cancel').onclick=()=>done(null);overlay.addEventListener('click',e=>{if(e.target===overlay)done(null)});overlay.querySelector('#file-dialog-form').onsubmit=e=>{e.preventDefault();const value=password?input.value:input.value.trim();if(!value){overlay.querySelector('#file-dialog-error').textContent=password?'Please enter your password.':'Please enter a name.';return}done(value)};input.focus();input.select()})}
async function renderFiles(){
 app.innerHTML=`<header><div class="brand"><span class="mark">${PINAS_BRAND_ICON}</span><div>PiNAS<small>MY FILES</small></div></div><div class="user-header">${userAvatarMarkup("user-avatar")}<span class="small">${esc(displayName)}</span><button class="icon-btn" id="file-settings" aria-label="My Settings" title="My Settings">${SETTINGS_ICON}</button><button class="icon-btn" id="file-logout" aria-label="Sign out" title="Sign out">${LOGOFF_ICON}<span class="sr-only">Sign out</span></button></div></header><main><div class="page-heading"><h1>My Files</h1><p>Browse and manage your permitted SMB shares.</p></div><div class="card"><div id="file-breadcrumb" class="small"></div><div class="file-toolbar"><button class="icon-btn" id="file-back" aria-label="Folder up" title="Folder up">${fileIcon('up',32)}</button><button class="icon-btn" id="file-new" aria-label="New folder" title="New folder">${fileIcon('plus',32)}</button><label class="icon-btn file-upload-control" aria-label="Upload files" title="Upload files">${fileIcon('upload',32)}<input id="file-upload" type="file" multiple aria-label="Upload files"></label><button class="icon-btn" id="file-refresh" aria-label="Refresh folder" title="Refresh folder">${fileIcon('refresh',32)}</button></div><div id="file-items"><p>Loading files…</p></div><p class="small" id="file-message" role="status"></p><div id="transfer-panel" hidden><div class="small" id="transfer-label"></div><div class="bar"><i id="transfer-bar" style="width:0"></i></div><button class="btn outline" id="transfer-cancel">Cancel transfer</button></div></div></main>`;
 document.getElementById('file-settings').onclick=openUserSettings;
 document.getElementById('file-logout').onclick=()=>signOut(document.getElementById('file-logout'));
 let currentShare='',currentPath='',shares=[],activeTransfer=null;
 const msg=document.getElementById('file-message'),items=document.getElementById('file-items');
 const panel=document.getElementById('transfer-panel'),bar=document.getElementById('transfer-bar'),label=document.getElementById('transfer-label');
 const call=(action,extra={})=>post('/api/files',{action,share:currentShare,path:currentPath,...extra});
 const joined=(a,b)=>[a,b].filter(Boolean).join('/');
 const readonly=()=>!currentShare||shares.find(x=>x.name===currentShare)?.read_only;
 const fmt=formatBytes;
 const progress=(done,total,filename,start)=>{panel.hidden=false;bar.style.width=(total?Math.min(100,100*done/total):0)+'%';const speed=done/Math.max(.2,(Date.now()-start)/1000);label.textContent=`${filename} · ${fmt(done)} / ${fmt(total)} · ${fmt(speed)}/s`+(speed&&done<total?` · ${Math.ceil((total-done)/speed)}s remaining`:'')};
 document.getElementById('transfer-cancel').onclick=()=>{if(activeTransfer)activeTransfer.cancelled=true};
 async function downloadFile(path,name,size){
   // The browser streams directly to its download manager: no huge Blob,
   // repeated sudo/pdbedit process per chunk or temporary in-memory copies.
   const url='/api/file-download?share='+encodeURIComponent(currentShare)+'&path='+encodeURIComponent(path);
   const anchor=document.createElement('a');anchor.href=url;anchor.download=name;
   document.body.append(anchor);anchor.click();anchor.remove();
 }
 async function uploadFile(file,index,total){
   const transfer={cancelled:false};activeTransfer=transfer;let token=null,offset=0;const started=Date.now(),chunk=384*1024;
   try{const result=await call('upload_start',{name:file.name,size:file.size});token=result.token;
     while(offset<file.size){if(transfer.cancelled)throw Error('Upload cancelled');const bytes=new Uint8Array(await file.slice(offset,offset+chunk).arrayBuffer());let binary='';for(let j=0;j<bytes.length;j+=8192)binary+=String.fromCharCode(...bytes.subarray(j,j+8192));const r=await call('upload_chunk',{token,offset,content:btoa(binary)});offset=r.offset;progress(offset,file.size,`File ${index}/${total}: ${file.name}`,started)}
     if(transfer.cancelled)throw Error('Upload cancelled');await call('upload_finish',{token});token=null;msg.textContent=`Uploaded ${file.name}`;
   }catch(e){msg.textContent=e.message;if(token){try{await call('upload_cancel',{token})}catch(_){}}return false}
   finally{panel.hidden=true;activeTransfer=null}return true;
 }
 async function show(offset=0){try{
   msg.textContent='';let rows;
   if(!currentShare){const result=await call('shares');shares=result.shares||[];rows=shares.map(x=>({name:x.name,dir:true,share:true,read_only:x.read_only}));}
   else {const listed=await call('list',{offset});rows=listed.entries||[];var nextOffset=listed.next_offset,varTotal=listed.total};
   document.getElementById('file-breadcrumb').textContent=currentShare?currentShare+(currentPath?' / '+currentPath:''):'My Shares';
   document.getElementById('file-back').disabled=!currentShare;
   document.getElementById('file-new').disabled=readonly();document.getElementById('file-upload').disabled=readonly();
   if(!offset)items.replaceChildren();if(!rows.length&&!offset){let p=document.createElement('p');p.textContent='Nothing here yet.';items.append(p)}
   for(const x of rows){const line=document.createElement('div');line.className='line';const title=document.createElement('button');title.className='file-entry';title.innerHTML=fileIcon(x.dir?'folder':'file')+`<span class="file-name">${esc(x.name)}</span>`;line.append(title);
     title.onclick=async()=>{if(x.share){currentShare=x.name;currentPath='';await show()}else if(x.dir){currentPath=joined(currentPath,x.name);await show()}else await downloadFile(joined(currentPath,x.name),x.name,x.size)};
     // Downloads are available for files regardless of whether the share is read-only.
     if(!x.share&&!x.dir){const download=document.createElement('button');download.className='icon-btn file-action-btn';download.innerHTML=actionIcon('download');download.title='Download';download.setAttribute('aria-label','Download '+x.name);download.onclick=()=>downloadFile(joined(currentPath,x.name),x.name,x.size);line.append(download)}
     if(!x.share&&!readonly()){
       const action=async(kind,extra)=>{try{await call(kind,{path:joined(currentPath,x.name),...extra});await show()}catch(e){msg.textContent=e.message}};
       const rename=document.createElement('button');rename.className='icon-btn file-action-btn';rename.innerHTML=actionIcon('rename');rename.title='Rename';rename.setAttribute('aria-label','Rename '+x.name);rename.onclick=async()=>{const name=await fileTextDialog({title:'Rename item',label:'New name',initial:x.name,confirmLabel:'Rename'});if(name&&name!==x.name)action('rename',{name})};line.append(rename);
       const copy=document.createElement('button');copy.className='icon-btn file-action-btn';copy.innerHTML=actionIcon('copy');copy.title='Copy';copy.setAttribute('aria-label','Copy '+x.name);copy.onclick=async()=>{const dest=await fileTextDialog({title:'Copy item',label:'Destination within this share',initial:joined(currentPath,x.name+'-copy'),description:'Enter a path relative to the current share.',confirmLabel:'Copy'});if(dest)action('copy',{dest})};line.append(copy);
       const move=document.createElement('button');move.className='icon-btn file-action-btn';move.innerHTML=actionIcon('move');move.title='Move';move.setAttribute('aria-label','Move '+x.name);move.onclick=async()=>{const dest=await fileTextDialog({title:'Move item',label:'Destination within this share',initial:joined(currentPath,x.name),description:'Enter a path relative to the current share.',confirmLabel:'Move'});if(dest&&dest!==joined(currentPath,x.name))action('move',{dest})};line.append(move);
       const del=document.createElement('button');del.className='icon-btn file-action-btn file-action-delete';del.innerHTML=actionIcon('delete');del.title='Delete';del.setAttribute('aria-label','Delete '+x.name);del.onclick=async()=>{
         const password=await fileTextDialog({title:x.dir?'Delete folder and contents':'Delete file',label:'Your account password',description:'Permanently delete '+x.name+(x.dir?' and everything inside it':'')+' from '+currentShare+'. This cannot be undone. Re-enter the password for '+username+' to continue.',confirmLabel:'Delete permanently',password:true});
         if(password!==null)await action('delete',{password});
       };line.append(del);
     }items.append(line)}
   if(nextOffset!==null&&nextOffset!==undefined){const more=document.createElement('button');more.className='btn outline';more.textContent='Load more files ('+Math.min(nextOffset,varTotal)+' of '+varTotal+')';more.onclick=()=>{more.remove();show(nextOffset)};items.append(more)}
   }catch(e){msg.textContent=e.message}}
 document.getElementById('file-refresh').onclick=()=>show();
 document.getElementById('file-back').onclick=()=>{if(currentPath)currentPath=currentPath.split('/').slice(0,-1).join('/');else currentShare='';show()};
 document.getElementById('file-new').onclick=async()=>{const name=await fileTextDialog({title:'New folder',label:'Folder name',confirmLabel:'Create folder'});if(!name)return;try{await call('mkdir',{name});await show()}catch(e){msg.textContent=e.message}};
 document.getElementById('file-upload').onchange=async e=>{const files=Array.from(e.target.files);e.target.value='';for(let i=0;i<files.length;i++){if(!await uploadFile(files[i],i+1,files.length))break}await show()};
 await show();
}

init();
</script></body></html>'''
PAGE_BYTES=PAGE.encode('utf-8')

