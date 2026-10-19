from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import HTMLResponse
from sqlalchemy.orm import Session

from app.api.deps import get_db
from app.examination.service import ExamService

router = APIRouter(prefix="/api/reports", tags=["reports"])


@router.get("/exam/{exam_id}")
def get_exam_report(exam_id: str, db: Session = Depends(get_db)):
    report = ExamService.generate_report(db, exam_id)
    if not report:
        raise HTTPException(404, detail={"code": "EXAM_NOT_FOUND", "message": "Examination not found."})
    return report


@router.get("/exam/{exam_id}/html", response_class=HTMLResponse)
def get_exam_report_html(exam_id: str, db: Session = Depends(get_db)):
    r = ExamService.generate_report(db, exam_id)
    if not r:
        raise HTTPException(404, detail={"code": "EXAM_NOT_FOUND", "message": "Examination not found."})

    m = r["metrics"]
    timeline_html = ""
    for item in r["timeline"]:
        rev_html = (
            f"<div class='review-box'><strong>Reviewed by {item['review']['reviewer_id']} ({item['review']['decision']}):</strong> {item['review']['notes']}</div>"
            if item.get("review")
            else "<span class='badge pending'>Pending Review</span>"
        )
        timeline_html += f"""
        <tr class="timeline-row">
            <td>{item['timestamp'][:19].replace('T', ' ')}</td>
            <td><strong>{item['category']}</strong><br><small>{item.get('seat_id') or 'General Room'}</small></td>
            <td><span class="badge {item['priority'].lower()}">{item['priority'].upper()}</span> ({item['score']})</td>
            <td>{item['explanation']}<br><small style="color:#64748b;">Limitations: {"; ".join(item['limitations'])}</small></td>
            <td>{rev_html}</td>
        </tr>
        """

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <title>OmniProctor Integrity Audit Report - {r['title']}</title>
    <style>
        body {{ font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif; color: #1e293b; margin: 40px; }}
        .header {{ border-bottom: 2px solid #0f172a; padding-bottom: 16px; margin-bottom: 24px; }}
        h1 {{ margin: 0 0 8px 0; font-size: 24px; }}
        .meta-grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 16px; margin-bottom: 24px; background: #f8fafc; padding: 16px; border-radius: 8px; border: 1px solid #e2e8f0; }}
        .stat-card {{ background: white; padding: 12px; border-radius: 6px; border: 1px solid #e2e8f0; }}
        .stat-val {{ font-size: 20px; font-weight: bold; color: #0f172a; }}
        .stat-lbl {{ font-size: 11px; text-transform: uppercase; color: #64748b; letter-spacing: 0.05em; }}
        table {{ width: 100%; border-collapse: collapse; margin-top: 16px; font-size: 13px; }}
        th, td {{ padding: 10px 12px; text-align: left; border-bottom: 1px solid #e2e8f0; }}
        th {{ background: #f1f5f9; color: #334155; }}
        .badge {{ display: inline-block; padding: 2px 8px; border-radius: 12px; font-size: 11px; font-weight: bold; }}
        .badge.high {{ background: #fee2e2; color: #991b1b; }}
        .badge.medium {{ background: #fef3c7; color: #92400e; }}
        .badge.low {{ background: #e0f2fe; color: #075985; }}
        .badge.pending {{ background: #f1f5f9; color: #64748b; }}
        .review-box {{ background: #f0fdf4; border: 1px solid #bbf7d0; padding: 6px 8px; border-radius: 4px; font-size: 12px; margin-top: 4px; }}
        .footer {{ margin-top: 40px; padding-top: 16px; border-top: 1px solid #e2e8f0; font-size: 11px; color: #64748b; }}
        @media print {{ body {{ margin: 20px; }} }}
    </style>
</head>
<body>
    <div class="header">
        <h1>OmniProctor Academic Integrity Audit Report</h1>
        <div>Examination: <strong>{r['title']}</strong> ({r.get('course_code') or 'N/A'}) &middot; Room: <strong>{r['room_name']}</strong></div>
        <div style="font-size: 12px; color: #64748b; margin-top: 4px;">Status: {r['status']} &middot; Duration: {r['duration_minutes'] or 'In progress'} min &middot; Generated: {utcnow().strftime('%Y-%m-%d %H:%M:%S UTC')}</div>
    </div>

    <div class="meta-grid">
        <div class="stat-card">
            <div class="stat-lbl">Total Workstations</div>
            <div class="stat-val">{r['total_seats']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-lbl">Recorded Alerts</div>
            <div class="stat-val">{m['total_alerts']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-lbl">High Priority Flags</div>
            <div class="stat-val" style="color:#b91c1c;">{m['priority_breakdown']['high']}</div>
        </div>
        <div class="stat-card">
            <div class="stat-lbl">Human Reviews Completed</div>
            <div class="stat-val">{m['reviews_completed']} / {m['total_alerts']}</div>
        </div>
    </div>

    <h3>Candidate Incident Log &amp; Reviewer Determinations</h3>
    <table>
        <thead>
            <tr>
                <th style="width: 140px;">Timestamp</th>
                <th style="width: 140px;">Category / Seat</th>
                <th style="width: 110px;">Priority (Score)</th>
                <th>Observation Summary &amp; Limitations</th>
                <th style="width: 240px;">Proctor Determination</th>
            </tr>
        </thead>
        <tbody>
            {timeline_html if timeline_html else "<tr><td colspan='5' style='text-align:center; padding: 24px; color:#64748b;'>No candidate incidents recorded during this examination session.</td></tr>"}
        </tbody>
    </table>

    <div class="footer">
        <p><strong>Ethical Notice:</strong> {r['compliance_notice']}</p>
        <p>OmniProctor Automated Review System &middot; Cryptographically signed audit record &middot; Official Examination Record</p>
    </div>
</body>
</html>
"""
    return HTMLResponse(content=html)
