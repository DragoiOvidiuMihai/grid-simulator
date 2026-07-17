"""
PDF Report Generator
====================
Generates a professional engineering report from simulation results.
Uses ReportLab Platypus for structured layout.

Report structure:
  Page 1 — Cover + Executive Summary
  Page 2 — Technical Results (voltages, losses, generation)
  Page 3 — Time-series summary (only for time-series results)
"""

from __future__ import annotations
from io import BytesIO
from datetime import datetime
from typing import Optional

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, PageBreak, KeepTogether,
)
from reportlab.platypus.flowables import Flowable
from reportlab.pdfgen import canvas as pdfcanvas


# ─────────────────────────────────────────────────────────────────────────────
# COLOUR PALETTE
# ─────────────────────────────────────────────────────────────────────────────

NAVY       = colors.HexColor('#1F3864')
BLUE       = colors.HexColor('#2E75B6')
LIGHT_BLUE = colors.HexColor('#D6E4F0')
GREEN      = colors.HexColor('#375623')
LIGHT_GREEN= colors.HexColor('#E2EFDA')
RED        = colors.HexColor('#C00000')
LIGHT_RED  = colors.HexColor('#FFDCDC')
AMBER      = colors.HexColor('#9C6500')
LIGHT_AMBER= colors.HexColor('#FFEB9C')
GRAY_DARK  = colors.HexColor('#595959')
GRAY_MID   = colors.HexColor('#BFBFBF')
GRAY_LIGHT = colors.HexColor('#F2F2F2')
WHITE      = colors.white
BLACK      = colors.black


# ─────────────────────────────────────────────────────────────────────────────
# PAGE TEMPLATE (header / footer on every page)
# ─────────────────────────────────────────────────────────────────────────────

class ReportTemplate(SimpleDocTemplate):
    def __init__(self, buffer, grid_name: str, report_date: str, **kwargs):
        self.grid_name   = grid_name
        self.report_date = report_date
        super().__init__(buffer, **kwargs)

    def handle_pageBegin(self):
        super().handle_pageBegin()

    def afterPage(self):
        pass


def _draw_header_footer(canvas, doc, grid_name: str, report_date: str):
    """Draw consistent header and footer on every page."""
    canvas.saveState()
    W, H = A4

    # ── Header bar ────────────────────────────────────────────────────────────
    if doc.page > 1:
        canvas.setFillColor(NAVY)
        canvas.rect(0, H - 18*mm, W, 18*mm, fill=1, stroke=0)

        canvas.setFillColor(WHITE)
        canvas.setFont('Helvetica-Bold', 9)
        canvas.drawString(15*mm, H - 11*mm, 'GRID SIMULATOR')
        canvas.setFont('Helvetica', 8)
        canvas.drawString(15*mm, H - 16*mm, f'Distribution Network Analysis Report')

        canvas.setFont('Helvetica', 8)
        canvas.drawRightString(W - 15*mm, H - 11*mm, grid_name)
        canvas.drawRightString(W - 15*mm, H - 16*mm, report_date)

    # ── Footer ────────────────────────────────────────────────────────────────
    canvas.setFillColor(GRAY_MID)
    canvas.rect(0, 0, W, 10*mm, fill=1, stroke=0)

    canvas.setFillColor(GRAY_DARK)
    canvas.setFont('Helvetica', 7)
    canvas.drawString(15*mm, 3.5*mm,
        'Standards: IEC 61089 | IEC 60502-2 | IEC 60228 | EN 50160 | EN 50182 | Dyn11 vector group')
    canvas.setFont('Helvetica', 7)
    canvas.drawRightString(W - 15*mm, 3.5*mm, f'Page {doc.page}')

    canvas.restoreState()


# ─────────────────────────────────────────────────────────────────────────────
# STYLES
# ─────────────────────────────────────────────────────────────────────────────

def _build_styles():
    base = getSampleStyleSheet()
    styles = {}

    styles['cover_title'] = ParagraphStyle('cover_title',
        fontName='Helvetica-Bold', fontSize=28, textColor=WHITE,
        alignment=TA_LEFT, spaceAfter=4*mm)

    styles['cover_subtitle'] = ParagraphStyle('cover_subtitle',
        fontName='Helvetica', fontSize=13, textColor=LIGHT_BLUE,
        alignment=TA_LEFT, spaceAfter=2*mm)

    styles['cover_meta'] = ParagraphStyle('cover_meta',
        fontName='Helvetica', fontSize=10, textColor=GRAY_MID,
        alignment=TA_LEFT, spaceAfter=1*mm)

    styles['section_heading'] = ParagraphStyle('section_heading',
        fontName='Helvetica-Bold', fontSize=11, textColor=NAVY,
        spaceBefore=6*mm, spaceAfter=3*mm, borderPad=0)

    styles['body'] = ParagraphStyle('body',
        fontName='Helvetica', fontSize=9, textColor=BLACK,
        spaceAfter=2*mm, leading=13)

    styles['table_header'] = ParagraphStyle('table_header',
        fontName='Helvetica-Bold', fontSize=8, textColor=WHITE,
        alignment=TA_CENTER)

    styles['caption'] = ParagraphStyle('caption',
        fontName='Helvetica', fontSize=7.5, textColor=GRAY_DARK,
        alignment=TA_LEFT, spaceAfter=2*mm)

    styles['compliance_ok'] = ParagraphStyle('compliance_ok',
        fontName='Helvetica-Bold', fontSize=10, textColor=GREEN,
        alignment=TA_CENTER)

    styles['compliance_fail'] = ParagraphStyle('compliance_fail',
        fontName='Helvetica-Bold', fontSize=10, textColor=RED,
        alignment=TA_CENTER)

    return styles


# ─────────────────────────────────────────────────────────────────────────────
# HELPER — styled table
# ─────────────────────────────────────────────────────────────────────────────

def _make_table(data: list[list], col_widths: list[float],
                header_rows: int = 1) -> Table:
    """Create a styled table with navy header and alternating row colours."""
    t = Table(data, colWidths=col_widths, repeatRows=header_rows)

    style_cmds = [
        # Header
        ('BACKGROUND',   (0, 0), (-1, header_rows - 1), NAVY),
        ('TEXTCOLOR',    (0, 0), (-1, header_rows - 1), WHITE),
        ('FONTNAME',     (0, 0), (-1, header_rows - 1), 'Helvetica-Bold'),
        ('FONTSIZE',     (0, 0), (-1, header_rows - 1), 8),
        ('ALIGN',        (0, 0), (-1, header_rows - 1), 'CENTER'),
        ('VALIGN',       (0, 0), (-1, -1), 'MIDDLE'),
        ('ROWBACKGROUND',(0, header_rows), (-1, -1),
            [GRAY_LIGHT, WHITE]),
        ('FONTNAME',     (0, header_rows), (-1, -1), 'Helvetica'),
        ('FONTSIZE',     (0, header_rows), (-1, -1), 8),
        ('ALIGN',        (0, header_rows), (-1, -1), 'CENTER'),
        ('GRID',         (0, 0), (-1, -1), 0.5, GRAY_MID),
        ('TOPPADDING',   (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 3),
        ('LEFTPADDING',  (0, 0), (-1, -1), 4),
        ('RIGHTPADDING', (0, 0), (-1, -1), 4),
    ]
    t.setStyle(TableStyle(style_cmds))
    return t


def _status_cell(ok: bool) -> str:
    return 'PASS' if ok else 'FAIL'


def _color_status_row(table, row_idx: int, ok: bool):
    """Colour entire row green or red based on pass/fail."""
    bg = LIGHT_GREEN if ok else LIGHT_RED
    fg = GREEN if ok else RED
    table._addCommand(('BACKGROUND', (0, row_idx), (-1, row_idx), bg))
    table._addCommand(('TEXTCOLOR',  (-1, row_idx), (-1, row_idx), fg))
    table._addCommand(('FONTNAME',   (-1, row_idx), (-1, row_idx), 'Helvetica-Bold'))


# ─────────────────────────────────────────────────────────────────────────────
# COVER PAGE
# ─────────────────────────────────────────────────────────────────────────────

def _build_cover_page(story, styles, grid_name: str, report_date: str,
                      sim_mode: str, season: str = None,
                      multiplier: float = None):
    W, H = A4

    # Full-page navy background via a large coloured table trick
    cover_bg = Table([['']], colWidths=[W], rowHeights=[H * 0.42])
    cover_bg.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), NAVY),
        ('LINEBELOW',  (0, 0), (-1, -1), 3, BLUE),
    ]))
    story.append(cover_bg)
    story.append(Spacer(1, -H * 0.42))  # overlap — draw text over the block

    # Title block (overlaid on blue area via negative spacer trick)
    story.append(Spacer(1, 18*mm))
    story.append(Paragraph('DISTRIBUTION NETWORK', styles['cover_title']))
    story.append(Paragraph('SIMULATION REPORT', styles['cover_title']))
    story.append(Spacer(1, 4*mm))
    story.append(HRFlowable(width='100%', thickness=1, color=BLUE, spaceAfter=4*mm))
    story.append(Paragraph(f'Grid: {grid_name}', styles['cover_subtitle']))
    story.append(Paragraph(f'Simulation mode: {sim_mode}', styles['cover_meta']))
    story.append(Paragraph(f'Generated: {report_date}', styles['cover_meta']))

    if season:
        story.append(Paragraph(
            f'Season: {season.capitalize()}  |  Load multiplier: {multiplier}x',
            styles['cover_meta']
        ))

    story.append(Spacer(1, 8*mm))

    # Standards badge
    badge_data = [[
        'EU/IEC COMPLIANT SIMULATION',
        'Solver: OpenDSS',
        'Voltage std: EN 50160',
    ]]
    badge = Table(badge_data, colWidths=[60*mm, 60*mm, 60*mm])
    badge.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), BLUE),
        ('TEXTCOLOR',     (0, 0), (-1, -1), WHITE),
        ('FONTNAME',      (0, 0), (-1, -1), 'Helvetica-Bold'),
        ('FONTSIZE',      (0, 0), (-1, -1), 7.5),
        ('ALIGN',         (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN',        (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING',    (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('LINEAFTER',     (0, 0), (1, 0), 0.5, LIGHT_BLUE),
    ]))
    story.append(badge)
    story.append(Spacer(1, 10*mm))


# ─────────────────────────────────────────────────────────────────────────────
# COMPLIANCE SUMMARY BOX
# ─────────────────────────────────────────────────────────────────────────────

def _build_compliance_box(story, styles, all_pass: bool,
                          violation_count: int, bus_count: int):
    if all_pass:
        bg     = LIGHT_GREEN
        border = GREEN
        title  = 'EN 50160 COMPLIANCE: ALL BUSES WITHIN LIMITS'
        detail = (
            f'All {bus_count} buses maintained voltage within '
            f'the EN 50160 steady-state limit of +/-10% nominal '
            f'throughout the simulation period.'
        )
        style_key = 'compliance_ok'
    else:
        bg     = LIGHT_RED
        border = RED
        title  = f'EN 50160 COMPLIANCE: {violation_count} VIOLATION(S) DETECTED'
        detail = (
            f'{violation_count} bus(es) recorded voltage outside the EN 50160 '
            f'steady-state limit of +/-10% nominal. '
            f'Corrective action recommended — review loading conditions '
            f'or network topology.'
        )
        style_key = 'compliance_fail'

    box = Table(
        [[Paragraph(title, styles[style_key])],
         [Paragraph(detail, styles['body'])]],
        colWidths=[170*mm]
    )
    box.setStyle(TableStyle([
        ('BACKGROUND',   (0, 0), (-1, -1), bg),
        ('LINEABOVE',    (0, 0), (-1, 0),  2, border),
        ('LINEBELOW',    (0, -1), (-1, -1), 2, border),
        ('LINEBEFORE',   (0, 0), (0, -1),  2, border),
        ('LINEAFTER',    (-1, 0), (-1, -1), 2, border),
        ('TOPPADDING',   (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING',(0, 0), (-1, -1), 6),
        ('LEFTPADDING',  (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
    ]))
    story.append(KeepTogether([box]))
    story.append(Spacer(1, 5*mm))


# ─────────────────────────────────────────────────────────────────────────────
# SNAPSHOT RESULTS PAGE
# ─────────────────────────────────────────────────────────────────────────────

def _build_snapshot_results(story, styles, result: dict):
    W = 170*mm  # usable width

    # ── Simulation metadata ───────────────────────────────────────────────────
    story.append(Paragraph('1. Simulation Summary', styles['section_heading']))

    meta_data = [
        ['Parameter', 'Value'],
        ['Solver',          'OpenDSS (opendssdirect.py)'],
        ['Simulation mode', 'AC Steady-State Power Flow (Snapshot)'],
        ['Convergence',     'YES' if result.get('converged') else 'NO'],
        ['Iterations',      str(result.get('iterations', '-'))],
        ['Total active losses',   f"{result.get('total_loss_kw', 0):.3f} kW"],
        ['Total reactive losses', f"{result.get('total_loss_kvar', 0):.3f} kVAR"],
    ]
    meta_table = _make_table(meta_data, [75*mm, 95*mm])
    # Colour convergence row
    conv_row = 2
    if result.get('converged'):
        meta_table._addCommand(('BACKGROUND', (1, conv_row), (1, conv_row), LIGHT_GREEN))
        meta_table._addCommand(('TEXTCOLOR',  (1, conv_row), (1, conv_row), GREEN))
        meta_table._addCommand(('FONTNAME',   (1, conv_row), (1, conv_row), 'Helvetica-Bold'))
    else:
        meta_table._addCommand(('BACKGROUND', (1, conv_row), (1, conv_row), LIGHT_RED))
        meta_table._addCommand(('TEXTCOLOR',  (1, conv_row), (1, conv_row), RED))
        meta_table._addCommand(('FONTNAME',   (1, conv_row), (1, conv_row), 'Helvetica-Bold'))
    story.append(meta_table)
    story.append(Spacer(1, 4*mm))

    # ── EN 50160 Compliance ───────────────────────────────────────────────────
    story.append(Paragraph('2. EN 50160 Voltage Quality Compliance', styles['section_heading']))

    bus_voltages   = result.get('bus_voltages', [])
    violation_count = sum(1 for v in bus_voltages if not v.get('within_limits', True))
    all_pass        = violation_count == 0
    _build_compliance_box(story, styles, all_pass, violation_count, len(bus_voltages))

    # ── Bus Voltage Table ─────────────────────────────────────────────────────
    story.append(Paragraph('3. Bus Voltage Results', styles['section_heading']))
    story.append(Paragraph(
        'Voltage magnitudes at each network bus after power flow convergence. '
        'EN 50160 limits: 0.90 pu to 1.10 pu for both MV and LV networks.',
        styles['caption']
    ))

    v_data = [['Bus ID', 'Nominal (kV)', 'Actual (kV)', 'Voltage (pu)', 'Deviation', 'EN 50160']]
    for v in bus_voltages:
        v_data.append([
            v.get('bus_id', '-'),
            f"{v.get('nominal_kv', 0):.4f}",
            f"{v.get('voltage_kv', 0):.4f}",
            f"{v.get('per_unit', 0):.4f}",
            f"{v.get('deviation_pct', 0):+.2f}%",
            _status_cell(v.get('within_limits', True)),
        ])
    v_table = _make_table(v_data, [50*mm, 28*mm, 28*mm, 28*mm, 20*mm, 18*mm])
    for i, v in enumerate(bus_voltages, start=1):
        _color_status_row(v_table, i, v.get('within_limits', True))
    story.append(v_table)
    story.append(Spacer(1, 4*mm))

    # ── Power Losses ──────────────────────────────────────────────────────────
    story.append(Paragraph('4. Power Losses by Element', styles['section_heading']))

    power_losses = result.get('power_losses', [])
    if power_losses:
        l_data = [['Element', 'Type', 'Active Loss (kW)', 'Reactive Loss (kVAR)']]
        for p in power_losses:
            elem_id = p.get('element_id', '-')
            if elem_id.startswith('reactflow'):
                elem_id = p.get('element_type', '-').upper()
            l_data.append([
                elem_id,
                p.get('element_type', '-').capitalize(),
                f"{p.get('active_loss_kw', 0):.4f}",
                f"{p.get('reactive_loss_kvar', 0):.4f}",
            ])
        story.append(_make_table(l_data, [60*mm, 35*mm, 40*mm, 40*mm]))
        story.append(Spacer(1, 4*mm))

    # ── Generator Output ──────────────────────────────────────────────────────
    gen_outputs = result.get('generator_outputs', [])
    if gen_outputs:
        story.append(Paragraph('5. Generator and DER Output', styles['section_heading']))
        g_data = [['Generator ID', 'Active Output (kW)', 'Reactive Output (kVAR)']]
        for g in gen_outputs:
            gid = g.get('generator_id', '-').replace('PV_', 'PV: ')
            g_data.append([
                gid,
                f"{g.get('kw_output', 0):.3f}",
                f"{g.get('kvar_output', 0):.3f}",
            ])
        story.append(_make_table(g_data, [80*mm, 45*mm, 45*mm]))


# ─────────────────────────────────────────────────────────────────────────────
# TIME-SERIES RESULTS PAGES
# ─────────────────────────────────────────────────────────────────────────────

def _build_timeseries_results(story, styles, result: dict):

    story.append(Paragraph('1. Simulation Summary', styles['section_heading']))

    meta_data = [
        ['Parameter', 'Value'],
        ['Solver',              'OpenDSS (opendssdirect.py)'],
        ['Simulation mode',     '24-Hour Daily Time-Series (48 × 30-min steps)'],
        ['Season',              result.get('season', '-').capitalize()],
        ['Load multiplier',     f"{result.get('peak_load_multiplier', 1.0)}x"],
        ['Location reference',  'Bucharest, Romania (44.4 deg N)'],
        ['Converged steps',     f"{result.get('converged_steps', 0)} / {result.get('total_steps', 48)}"],
        ['Total PV energy',     f"{result.get('total_pv_energy_kwh', 0):.1f} kWh"],
        ['Total grid losses',   f"{result.get('total_energy_loss_kwh', 0):.3f} kWh"],
        ['Peak loss',           f"{result.get('peak_loss_kw', 0):.3f} kW at {result.get('peak_loss_time', '-')}"],
    ]
    story.append(_make_table(meta_data, [75*mm, 95*mm]))
    story.append(Spacer(1, 4*mm))

    # ── EN 50160 Compliance ───────────────────────────────────────────────────
    story.append(Paragraph('2. EN 50160 Voltage Quality Compliance (All Steps)', styles['section_heading']))

    summaries       = result.get('voltage_summaries', [])
    total_violations = sum(s.get('violations', 0) for s in summaries)
    all_pass         = total_violations == 0
    _build_compliance_box(story, styles, all_pass, total_violations, len(summaries))

    # ── Voltage Summary Table ─────────────────────────────────────────────────
    story.append(Paragraph('3. Bus Voltage Range Over 24 Hours', styles['section_heading']))
    story.append(Paragraph(
        'Minimum and maximum voltage recorded at each bus across all 48 simulation steps. '
        'EN 50160 limits: 0.90 pu to 1.10 pu.',
        styles['caption']
    ))

    vs_data = [['Bus ID', 'Min (pu)', 'Min Time', 'Max (pu)', 'Max Time', 'Violations', 'Status']]
    for s in summaries:
        viol = s.get('violations', 0)
        ok   = viol == 0
        vs_data.append([
            s.get('bus_id', '-'),
            f"{s.get('min_pu', 0):.4f}",
            s.get('min_time', '-'),
            f"{s.get('max_pu', 0):.4f}",
            s.get('max_time', '-'),
            str(viol),
            'PASS' if ok else 'FAIL',
        ])
    vs_table = _make_table(vs_data, [44*mm, 20*mm, 18*mm, 20*mm, 18*mm, 20*mm, 18*mm])
    for i, s in enumerate(summaries, start=1):
        _color_status_row(vs_table, i, s.get('violations', 0) == 0)
    story.append(vs_table)
    story.append(Spacer(1, 4*mm))

    # ── Hourly summary table (selected steps) ─────────────────────────────────
    story.append(Paragraph('4. Selected Hourly Snapshots', styles['section_heading']))
    story.append(Paragraph(
        'Voltage and generation output at key times of day.',
        styles['caption']
    ))

    timesteps = result.get('timesteps', [])
    # Pick every 4th step (every 2 hours) for the table
    key_indices = list(range(0, 48, 4))
    h_data = [['Time', 'LV Voltage (pu)', 'MV Voltage (pu)', 'PV Output (kW)', 'Losses (kW)']]

    for idx in key_indices:
        if idx >= len(timesteps):
            break
        ts = timesteps[idx]
        lv_pu = next(
            (v.get('per_unit', 0) for v in ts.get('bus_voltages', [])
             if 'lv' in v.get('bus_id', '').lower()), '-'
        )
        mv_pu = next(
            (v.get('per_unit', 0) for v in ts.get('bus_voltages', [])
             if 'mv' in v.get('bus_id', '').lower()), '-'
        )
        h_data.append([
            ts.get('time_label', '-'),
            f"{lv_pu:.4f}" if isinstance(lv_pu, float) else lv_pu,
            f"{mv_pu:.4f}" if isinstance(mv_pu, float) else mv_pu,
            f"{ts.get('pv_output_kw', 0):.2f}",
            f"{ts.get('total_loss_kw', 0):.4f}",
        ])

    story.append(_make_table(h_data, [24*mm, 36*mm, 36*mm, 38*mm, 36*mm]))


def _build_fault_results(story, styles, result: dict):

    story.append(Paragraph('1. Fault Study Summary', styles['section_heading']))
    story.append(Paragraph(
        'Short-circuit currents calculated using the Thevenin impedance method '
        '(EN 60909 methodology). Values represent bolted fault conditions at each '
        'bus terminal — the worst-case scenario for protection device sizing.',
        styles['caption']
    ))
    story.append(Spacer(1, 3*mm))

    bus_results = result.get('bus_results', [])

    # ── Compliance box ────────────────────────────────────────────────────────
    box_data = [[
        Paragraph('FAULT STUDY COMPLETE', ParagraphStyle('fs',
            fontName='Helvetica-Bold', fontSize=10,
            textColor=GREEN if result.get('success') else RED,
            alignment=TA_CENTER)),
    ],[
        Paragraph(
            f'{len(bus_results)} buses analysed. '
            'Results suitable for protection relay coordination and '
            'circuit breaker fault rating verification.',
            styles['body']
        ),
    ]]
    box = Table(box_data, colWidths=[170*mm])
    box.setStyle(TableStyle([
        ('BACKGROUND',    (0, 0), (-1, -1), LIGHT_GREEN if result.get('success') else LIGHT_RED),
        ('LINEABOVE',     (0, 0), (-1, 0),  2, GREEN if result.get('success') else RED),
        ('LINEBELOW',     (0, -1), (-1, -1), 2, GREEN if result.get('success') else RED),
        ('LINEBEFORE',    (0, 0), (0, -1),  2, GREEN if result.get('success') else RED),
        ('LINEAFTER',     (-1, 0), (-1, -1), 2, GREEN if result.get('success') else RED),
        ('TOPPADDING',    (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ('LEFTPADDING',   (0, 0), (-1, -1), 8),
        ('RIGHTPADDING',  (0, 0), (-1, -1), 8),
    ]))
    story.append(KeepTogether([box]))
    story.append(Spacer(1, 5*mm))

    # ── Fault current table ───────────────────────────────────────────────────
    story.append(Paragraph('2. Short-Circuit Currents by Bus', styles['section_heading']))
    story.append(Paragraph(
        'I_3ph = three-phase symmetrical fault current (most severe). '
        'I_1LG = single line-to-ground fault current (most common). '
        'X/R ratio affects DC offset and is critical for breaker selection.',
        styles['caption']
    ))

    f_data = [[
        'Bus ID', 'Voltage\n(kV L-L)',
        'I_3ph\n(kA)', 'I_3ph\n(A)',
        'I_1LG\n(kA)', 'I_1LG\n(A)',
        'X/R\nRatio'
    ]]
    for b in bus_results:
        f_data.append([
            b.get('bus_id', '-'),
            f"{b.get('voltage_kv_ll', 0):.3f}",
            f"{b.get('i3ph_ka', 0):.4f}",
            f"{b.get('i3ph_a', 0):.0f}",
            f"{b.get('i1lg_ka', 0):.4f}",
            f"{b.get('i1lg_a', 0):.0f}",
            f"{b.get('x_r_ratio', 0):.2f}",
        ])

    story.append(_make_table(f_data, [46*mm, 18*mm, 18*mm, 18*mm, 18*mm, 18*mm, 16*mm]))
    story.append(Spacer(1, 5*mm))

    # ── Thevenin impedance table ──────────────────────────────────────────────
    story.append(Paragraph('3. Thevenin Impedances', styles['section_heading']))
    story.append(Paragraph(
        'Positive-sequence (Z1) and zero-sequence (Z0) Thevenin impedances '
        'at each bus. Used for protection relay setting calculations.',
        styles['caption']
    ))

    z_data = [['Bus ID', 'Z1 Real (Ω)', 'Z1 Imag (Ω)', 'Z0 Real (Ω)', 'Z0 Imag (Ω)']]
    for b in bus_results:
        z_data.append([
            b.get('bus_id', '-'),
            f"{b.get('z1_real', 0):.6f}",
            f"{b.get('z1_imag', 0):.6f}",
            f"{b.get('z0_real', 0):.6f}",
            f"{b.get('z0_imag', 0):.6f}",
        ])

    story.append(_make_table(z_data, [46*mm, 31*mm, 31*mm, 31*mm, 31*mm]))


# ─────────────────────────────────────────────────────────────────────────────
# MAIN ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def generate_report(
    grid_name:        str,
    simulation_result: Optional[dict] = None,
    timeseries_result: Optional[dict] = None,
    fault_result:      Optional[dict] = None,
) -> bytes:
    """
    Generate a PDF report and return the raw bytes.

    Parameters
    ----------
    grid_name : str
        Name of the grid/scenario being reported.
    simulation_result : dict | None
        Snapshot simulation result dict (from /simulate endpoint).
    timeseries_result : dict | None
        Time-series result dict (from /simulate-timeseries endpoint).

    Returns
    -------
    bytes
        Raw PDF file content, ready to send as a file download.
    """

    if simulation_result is None and timeseries_result is None and fault_result is None:
        raise ValueError("At least one of simulation_result, timeseries_result, or fault_result must be provided.")

    buffer      = BytesIO()
    report_date = datetime.now().strftime('%d %B %Y, %H:%M')
    styles      = _build_styles()

    # Determine mode
    is_timeseries = timeseries_result is not None
    is_fault      = fault_result is not None
    sim_mode      = (
    '24-Hour Time-Series' if is_timeseries
    else 'Fault Study (EN 60909)' if is_fault
    else 'AC Snapshot'
    )
    season        = timeseries_result.get('season') if is_timeseries else None
    multiplier    = timeseries_result.get('peak_load_multiplier') if is_timeseries else None

    doc = SimpleDocTemplate(
        buffer,
        pagesize      = A4,
        leftMargin    = 20*mm,
        rightMargin   = 20*mm,
        topMargin     = 25*mm,
        bottomMargin  = 18*mm,
        title         = f'Grid Simulation Report — {grid_name}',
        author        = 'Grid Simulator v0.1',
        subject       = 'Distribution Network Analysis',
    )

    story = []

    # ── Cover page ────────────────────────────────────────────────────────────
    _build_cover_page(story, styles, grid_name, report_date,
                      sim_mode, season, multiplier)
    story.append(PageBreak())

    # ── Results pages ─────────────────────────────────────────────────────────
    if is_timeseries:
        _build_timeseries_results(story, styles, timeseries_result)
    elif is_fault:
        _build_fault_results(story, styles, fault_result)
    else:
        _build_snapshot_results(story, styles, simulation_result)

    # ── Build with header/footer callback ─────────────────────────────────────
    doc.build(
        story,
        onFirstPage = lambda c, d: _draw_header_footer(c, d, grid_name, report_date),
        onLaterPages= lambda c, d: _draw_header_footer(c, d, grid_name, report_date),
    )

    return buffer.getvalue()
