from __future__ import annotations

PLOT_COLORS = [
    "#ffbf00",
    "#f45b69",
    "#3b82f6",
    "#45c97a",
    "#ff8c42",
    "#42c2b8",
    "#8b5cf6",
    "#d85bef",
    "#8e9aa1",
    "#1f5aa6",
]

SEVERITY_COLORS = {
    "critical": "#8746b8",
    "high": "#f45b69",
    "medium": "#ffd43b",
    "low": "#5b8def",
    "unknown": "#a7b0b7",
}

_DASHBOARD_CSS = """
:root{--ink:#0b172a;--muted:#687386;--yellow:#ffbf00;--blue:#2463eb;--paper:#ffffff;--soft:#f7f9fc;--line:#dfe5ec;--danger:#e64b5d;--success:#179c62}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--paper);color:var(--ink);font:15px/1.55 Inter,"Segoe UI",Arial,sans-serif}
a{color:inherit}.shell{max-width:1320px;margin:auto;padding:0 28px}.topbar{position:sticky;top:0;z-index:20;background:#fffffff2;backdrop-filter:blur(12px);border-bottom:1px solid var(--line)}
.nav{display:flex;align-items:center;justify-content:space-between;gap:24px;min-height:64px}.brand{display:flex;align-items:center;gap:11px;font-weight:900}.brand-mark{width:7px;height:34px;background:var(--yellow);transform:skew(-18deg)}
.nav-links{display:flex;gap:20px;flex-wrap:wrap;font-size:13px;font-weight:700;color:#435064}.nav-links a{text-decoration:none}.nav-links a:hover{color:var(--blue)}
.hero{padding:76px 0 44px;border-bottom:1px solid var(--line)}.hero-grid{display:grid;grid-template-columns:1.45fr .65fr;gap:40px;align-items:end}.hero-kicker{font-size:13px;font-weight:900;letter-spacing:.14em;text-transform:uppercase;color:#536075}
.hero h1,.section-title{position:relative;margin:12px 0 14px;padding-left:31px;font-weight:950;letter-spacing:-.045em;line-height:1}.hero h1{font-size:clamp(48px,6vw,82px)}.hero h1:before,.section-title:before{content:"";position:absolute;left:5px;top:0;width:8px;height:100%;background:var(--yellow);transform:skew(-17deg)}
.hero p{max-width:800px;margin:0;color:#4e5b70;font-size:18px}.hero-summary{border:1px solid var(--line);padding:22px;border-radius:4px;box-shadow:0 12px 28px #0b172a10}.hero-summary strong{display:block;font-size:45px;line-height:1}.hero-summary span{color:var(--muted)}
.review-flag{display:inline-flex;align-items:center;gap:8px;margin-top:20px;padding:8px 12px;background:#fff8df;border:1px solid #f0d46a;font-size:12px;font-weight:800;text-transform:uppercase;letter-spacing:.08em}
main{padding:20px 0 96px}.section{padding:64px 0;border-bottom:1px solid var(--line)}.section-title{font-size:clamp(34px,4vw,58px);margin:0 0 32px}.section-subtitle{margin:-18px 0 34px;padding-left:31px;color:var(--muted);font-size:17px}
.executive{display:grid;grid-template-columns:1.15fr .85fr;gap:22px}.panel{background:#fff;border:1px solid var(--line);border-radius:4px;padding:26px;box-shadow:0 8px 24px #0b172a0b}.panel h3{margin:0 0 10px;font-size:20px}.panel p{margin:0;color:#435064}
.findings{display:grid;gap:12px}.finding{border-left:5px solid var(--yellow);background:var(--soft);padding:15px 17px;color:#27364d}.gate{display:flex;justify-content:space-between;gap:16px;align-items:center;border-top:1px solid var(--line);margin-top:22px;padding-top:18px}.gate b{color:var(--success)}
.kpi-grid{display:grid;grid-template-columns:repeat(4,1fr);gap:14px}.kpi-card{border:1px solid var(--line);padding:18px;background:#fff;min-height:152px}.kpi-card.attention{border-top:5px solid var(--danger)}.kpi-card.watch{border-top:5px solid var(--yellow)}.kpi-card.stable{border-top:5px solid var(--success)}.kpi-card.context,.kpi-card.insufficient{border-top:5px solid #76849a}
.kpi-card span{display:block;color:var(--muted);font-size:13px;font-weight:700}.kpi-card strong{display:block;font-size:34px;line-height:1.15;margin:7px 0}.kpi-card p{font-size:13px;margin:0;color:#435064}
.kpi-detail-list{display:grid;gap:28px}.kpi-detail{display:grid;grid-template-columns:330px 1fr;border:1px solid var(--line);background:#fff;box-shadow:0 10px 30px #0b172a0b}.kpi-visual{background:var(--soft);padding:22px;border-right:1px solid var(--line)}.kpi-visual h3{font-size:22px;margin:0 0 4px}.kpi-visual>p{color:var(--muted);margin:0}.kpi-copy{padding:26px 30px;display:grid;gap:18px}.copy-block{display:grid;grid-template-columns:150px 1fr;gap:18px}.copy-block b{font-size:12px;text-transform:uppercase;letter-spacing:.11em}.copy-block p{margin:0;color:#34435a}.kpi-meta{display:flex;flex-wrap:wrap;gap:8px}.chip{background:#eef2f7;border:1px solid #dce3eb;padding:5px 9px;font-size:12px}.chip.review{background:#fff8df;border-color:#f0d46a}
.slide{border:1px solid var(--line);background:#fff;padding:28px;margin:20px 0;box-shadow:0 9px 26px #0b172a0b}.slide-head{text-align:center;margin-bottom:8px}.slide-head h3{font-size:28px;margin:0}.slide-head p{margin:4px 0;color:var(--muted)}
.chart-two{display:grid;grid-template-columns:1fr 1fr;gap:22px}.chart-box{min-width:0}.chart-box h4{text-align:center;font-size:18px;margin:4px 0 0}.slide-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:20px;align-items:start}.plot{min-height:280px}.plot>div{width:100%!important}
.cause-summary{display:grid;grid-template-columns:1fr 1fr;gap:24px}.cause-primary,.cause-other{padding:26px;border:1px solid var(--line)}.cause-primary{background:#fff8df;border-color:#f0d46a}.cause-stat{text-align:center;background:#fff;padding:17px;margin:14px 0 20px}.cause-stat strong{display:block;color:var(--danger);font-size:46px;line-height:1}.cause-stat span{font-weight:800}.cause-row{margin:14px 0}.cause-row-head{display:flex;justify-content:space-between;gap:10px;font-weight:700}.cause-track{height:9px;background:#fde8e8;margin-top:6px}.cause-track i{display:block;height:100%;background:var(--danger)}.cause-other ul{list-style:none;margin:16px 0 0;padding:0}.cause-other li{display:flex;justify-content:space-between;padding:9px 0;border-bottom:1px solid #edf0f4}
.pattern-grid{display:grid;grid-template-columns:repeat(2,1fr);gap:16px}.pattern{padding:20px;border:1px solid var(--line);background:var(--soft)}.pattern p{margin:0;color:#34435a}
.cluster{border:1px solid var(--line);margin:16px 0;background:#fff}.cluster summary{cursor:pointer;display:grid;grid-template-columns:1fr auto;gap:20px;align-items:center;padding:22px}.cluster summary h3{font-size:22px;margin:3px 0}.cluster summary p{margin:0;color:var(--muted)}.score{font-size:34px;font-weight:900;text-align:center}.score small{display:block;font-size:10px;letter-spacing:.12em;text-transform:uppercase;color:var(--muted)}
.cluster-body{padding:0 22px 24px}.hypothesis{border-top:1px solid var(--line);padding-top:22px;margin-top:18px}.hyp-head{display:flex;justify-content:space-between;gap:20px}.hyp-head h4{font-size:20px;margin:3px 0}.badge{height:max-content;padding:5px 10px;text-transform:uppercase;font-size:11px;font-weight:900;background:#fff1c9}
.impact-alert{color:var(--danger);font-weight:700;margin:10px 0;padding:12px;background:#fde8e8;border-left:4px solid var(--danger)}
.evidence-grid{display:grid;grid-template-columns:1fr 1fr;gap:14px}.evidence-box{background:var(--soft);padding:16px}.evidence-box h5{margin:0 0 8px}.evidence-box ul{margin:0;padding-left:18px}.actions{display:grid;grid-template-columns:repeat(3,1fr);gap:12px;margin-top:15px}.action{border:1px solid var(--line);border-top:5px solid #789;padding:15px}.action.corrective{border-top-color:var(--danger)}.action.detective{border-top-color:var(--yellow)}.action.preventive{border-top-color:var(--success)}.action h5{font-size:14px;margin:5px 0 8px}.action p{margin:5px 0;font-size:13px;color:#435064}
.table-wrap{overflow:auto;border:1px solid var(--line)}table{border-collapse:collapse;width:100%;background:#fff}th,td{padding:11px 13px;border-bottom:1px solid var(--line);text-align:left;white-space:nowrap}th{background:var(--soft);font-size:12px;text-transform:uppercase;letter-spacing:.06em}
.muted{color:var(--muted)}code{font-size:12px}footer{padding:28px;border-top:1px solid var(--line);color:var(--muted);text-align:center}
@media(max-width:1000px){.hero-grid,.executive,.kpi-detail,.cause-summary{grid-template-columns:1fr}.kpi-visual{border-right:0;border-bottom:1px solid var(--line)}.kpi-grid{grid-template-columns:repeat(2,1fr)}.actions{grid-template-columns:1fr}.nav-links{display:none}}
@media(max-width:720px){.shell{padding:0 16px}.hero{padding-top:44px}.hero h1{font-size:46px}.section{padding:44px 0}.section-title{font-size:36px}.kpi-grid,.chart-two,.slide-grid,.pattern-grid,.evidence-grid{grid-template-columns:1fr}.copy-block{grid-template-columns:1fr;gap:5px}.slide{padding:12px}.plot{min-height:280px}}
"""
