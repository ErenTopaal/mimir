"""Widget.js serving and SVG badge generation."""
from __future__ import annotations

import re
from typing import Annotated

from fastapi import APIRouter, Depends, Response
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from api.core.deps import get_db
from api.models.job import Job, JobStatus


router = APIRouter(tags=['widget'])
DbSessionDep = Annotated[AsyncSession, Depends(get_db)]

AVALANCHE_ADDRESS_RE = re.compile(r'^0x[0-9a-fA-F]{40}$')


@router.get('/widget.js')
async def get_widget_js() -> Response:
    """Serve the embeddable widget script."""
    js = """
(function() {
  var script = document.currentScript;
  var address = script.getAttribute('data-address') || '';
  var chain = script.getAttribute('data-chain') || 'avalanche';
  var theme = script.getAttribute('data-theme') || 'light';
  var variant = script.getAttribute('data-variant') || 'compact';
  var frontendUrl = script.getAttribute('data-frontend-url') || window.location.origin;
  var apiBase = script.src.replace('/widget.js', '');

  var container = document.createElement('div');
  var borderColor = theme==='dark'?'#374151':'#e5e7eb';
  var bgColor = theme==='dark'?'#1f2937':'#fff';
  var fgColor = theme==='dark'?'#f9fafb':'#111827';
  var cardBg = theme==='dark'?'#374151':'#f3f4f6';

  if (variant === 'card') {
    container.style.cssText = 'font-family:system-ui,sans-serif;border:1px solid ' + borderColor + ';border-radius:8px;padding:20px;max-width:400px;background:' + bgColor + ';color:' + fgColor;
  } else {
    container.style.cssText = 'font-family:system-ui,sans-serif;border:1px solid #e5e7eb;border-radius:8px;padding:16px;max-width:400px;background:' + bgColor + ';color:' + fgColor;
  }

  function esc(s){return String(s).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;').replace(/"/g,'&quot;');}
  if (!address) { container.textContent = 'AvaxBench: missing data-address'; script.parentNode && script.parentNode.insertBefore(container, script.nextSibling); return; }

  container.innerHTML = '<div style="font-size:12px;opacity:.6">AvaxBench | Loading...</div>';
  script.parentNode && script.parentNode.insertBefore(container, script.nextSibling);

  fetch(apiBase + '/v1/permalink/' + chain + '/' + address)
    .then(function(r){ return r.json(); })
    .then(function(data) {
      if (data.status === 'source_not_available') {
        if (variant === 'card') {
          var addr = address.slice(0,6) + '...' + address.slice(-4);
          container.innerHTML = '<div style="font-size:14px;font-weight:600;margin-bottom:12px">Security Report</div>' +
            '<div style="font-size:12px;opacity:.6;margin-bottom:4px">Contract: <span style="font-family:monospace">' + addr + '</span></div>' +
            '<div style="font-size:12px;opacity:.6;margin-bottom:12px">Source not verified</div>' +
            '<div style="font-size:12px;padding:8px;border-radius:4px;background:' + cardBg + ';border-left:3px solid #6b7280">Contract source code is not available for auditing.</div>';
        } else {
          container.innerHTML = '<div style="font-size:13px;font-weight:600">AvaxBench Security</div><div style="font-size:12px;opacity:.6;margin-top:4px">Source not verified</div>';
        }
        return;
      }
      if (data.status === 'scanning' || !data.result) {
        if (variant === 'card') {
          var addr2 = address.slice(0,6) + '...' + address.slice(-4);
          container.innerHTML = '<div style="font-size:14px;font-weight:600;margin-bottom:12px">Security Report</div>' +
            '<div style="font-size:12px;opacity:.6;margin-bottom:4px">Contract: <span style="font-family:monospace">' + addr2 + '</span></div>' +
            '<div style="font-size:12px;color:#d97706;margin-bottom:12px">Scan in progress...</div>' +
            '<div style="font-size:12px;padding:8px;border-radius:4px;background:' + cardBg + ';border-left:3px solid #d97706">Audit is currently running. Results will appear here once complete.</div>';
        } else {
          container.innerHTML = '<div style="font-size:13px;font-weight:600">AvaxBench Security</div><div style="font-size:12px;color:#d97706;margin-top:4px">Scanning...</div>';
        }
        return;
      }
      var vulns = (data.result && data.result.vulnerabilities) || [];
      if (variant === 'card') {
        var critical = vulns.filter(function(v){ return v.severity==='critical'; }).length;
        var high = vulns.filter(function(v){ return v.severity==='high'; }).length;
        var medium = vulns.filter(function(v){ return v.severity==='medium'; }).length;
        var low = vulns.filter(function(v){ return v.severity==='low'; }).length;
        var date = data.finished_at ? new Date(data.finished_at).toLocaleDateString() : 'N/A';
        var addr3 = address.slice(0,6) + '...' + address.slice(-4);
        var topVuln = vulns.length > 0 ? esc(vulns[0].title) : '';
        var reportUrl = frontendUrl + '/results?chain=' + chain + '&address=' + address;
        var severityColor = high > 0 || critical > 0 ? '#dc2626' : '#16a34a';
        var html = '<div style="font-size:14px;font-weight:600;margin-bottom:12px">Security Report</div>';
        html += '<div style="font-size:12px;opacity:.6;margin-bottom:4px">Contract: <span style="font-family:monospace">' + addr3 + '</span></div>';
        html += '<div style="font-size:12px;opacity:.6;margin-bottom:12px">Last audit: ' + esc(date) + '</div>';
        html += '<div style="display:flex;gap:12px;margin-bottom:12px">';
        html += '<span style="font-size:12px;color:' + (critical>0?'#dc2626':'#6b7280') + '">' + critical + ' Critical</span>';
        html += '<span style="font-size:12px;color:' + (high>0?'#dc2626':'#6b7280') + '">' + high + ' High</span>';
        html += '<span style="font-size:12px;color:' + (medium>0?'#d97706':'#6b7280') + '">' + medium + ' Medium</span>';
        html += '<span style="font-size:12px;color:#6b7280">' + low + ' Low</span>';
        html += '</div>';
        if (topVuln) {
          html += '<div style="font-size:12px;padding:8px;border-radius:4px;background:' + cardBg + ';margin-bottom:12px;border-left:3px solid ' + severityColor + '">' + topVuln + '</div>';
        }
        html += '<a href="' + reportUrl + '" target="_blank" style="font-size:12px;color:#3b82f6;text-decoration:none">View full report \\u2192</a>';
        container.innerHTML = html;
      } else {
        var high = vulns.filter(function(v){ return v.severity==='high'; }).length;
        var color = high > 0 ? '#dc2626' : '#16a34a';
        var label = high > 0 ? high + ' high severity finding' + (high>1?'s':'') : 'No high severity findings';
        container.innerHTML = '<div style="font-size:13px;font-weight:600">AvaxBench Security</div>' +
          '<div style="font-size:12px;color:' + color + ';margin-top:4px">' + label + '</div>' +
          '<div style="font-size:11px;opacity:.5;margin-top:8px">Audited by AvaxBench</div>';
      }
    })
    .catch(function() {
      container.innerHTML = '<div style="font-size:12px;opacity:.6">AvaxBench: unable to load</div>';
    });
})();
"""
    return Response(content=js, media_type='application/javascript')


@router.get('/v1/badge/{chain}/{address}.svg')
async def get_badge_svg(
    chain: str,
    address: str,
    session: DbSessionDep,
) -> Response:
    """Generate a shields.io-style SVG badge."""
    if not AVALANCHE_ADDRESS_RE.match(address):
        label = 'invalid address'
        color = '#6b7280'
    else:
        tag = f'permalink:{chain}:{address.lower()}'
        job = await session.scalar(
            select(Job)
            .where(Job.file_name == tag, Job.status == JobStatus.succeeded)
            .order_by(Job.created_at.desc())
            .limit(1)
        )
        in_prog = await session.scalar(
            select(Job)
            .where(Job.file_name == tag, Job.status.in_([JobStatus.queued, JobStatus.running]))
            .limit(1)
        )
        if in_prog:
            label = 'scanning...'
            color = '#d97706'
        elif job and job.result:
            vulns = job.result.get('vulnerabilities', [])
            high = sum(1 for v in vulns if v.get('severity') == 'high')
            label = f'{high} high' if high else '0 high'
            color = '#dc2626' if high else '#16a34a'
        else:
            label = 'not audited'
            color = '#6b7280'

    left = 'AvaxBench'
    lw = len(left) * 7 + 10
    rw = len(label) * 7 + 10
    total = lw + rw

    svg = f"""<svg xmlns="http://www.w3.org/2000/svg" width="{total}" height="20">
  <linearGradient id="s" x2="0" y2="100%"><stop offset="0" stop-color="#bbb" stop-opacity=".1"/>
  <stop offset="1" stop-opacity=".1"/></linearGradient>
  <rect rx="3" width="{total}" height="20" fill="#555"/>
  <rect rx="3" x="{lw}" width="{rw}" height="20" fill="{color}"/>
  <rect width="{total}" height="20" rx="3" fill="url(#s)"/>
  <g fill="#fff" text-anchor="middle" font-family="DejaVu Sans,Verdana,Geneva,sans-serif" font-size="11">
    <text x="{lw//2}" y="15" fill="#010101" fill-opacity=".3">{left}</text>
    <text x="{lw//2}" y="14">{left}</text>
    <text x="{lw + rw//2}" y="15" fill="#010101" fill-opacity=".3">{label}</text>
    <text x="{lw + rw//2}" y="14">{label}</text>
  </g>
</svg>"""
    return Response(content=svg, media_type='image/svg+xml',
                    headers={'Cache-Control': 'no-cache', 'Access-Control-Allow-Origin': '*'})
