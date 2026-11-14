import io
from reportlab.lib.pagesizes import letter
from reportlab.lib import colors
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle, KeepTogether, HRFlowable
)
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from typing import Dict, Any

def generate_weekly_report_pdf(report: Dict[str, Any]) -> io.BytesIO:
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(
        buffer,
        pagesize=letter,
        rightMargin=36,
        leftMargin=36,
        topMargin=36,
        bottomMargin=36
    )

    styles = getSampleStyleSheet()
    
    # Custom styles
    title_style = ParagraphStyle(
        'DocTitle',
        parent=styles['Heading1'],
        fontSize=20,
        leading=24,
        textColor=colors.HexColor('#1E293B'),
        fontName='Helvetica-Bold'
    )
    subtitle_style = ParagraphStyle(
        'DocSubtitle',
        parent=styles['Normal'],
        fontSize=10,
        leading=14,
        textColor=colors.HexColor('#64748B')
    )
    h2_style = ParagraphStyle(
        'SectionHeading',
        parent=styles['Heading2'],
        fontSize=13,
        leading=17,
        textColor=colors.HexColor('#0F172A'),
        fontName='Helvetica-Bold',
        spaceBefore=12,
        spaceAfter=6
    )
    body_style = ParagraphStyle(
        'BodyDark',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13.5,
        textColor=colors.HexColor('#334155')
    )
    bold_label = ParagraphStyle(
        'BoldLabel',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=13.5,
        fontName='Helvetica-Bold',
        textColor=colors.HexColor('#1E293B')
    )
    ai_box_text = ParagraphStyle(
        'AIBoxText',
        parent=styles['Normal'],
        fontSize=9.5,
        leading=14,
        textColor=colors.HexColor('#1E1B4B')
    )

    elements = []

    # Title & Header
    elements.append(Paragraph("Employee Weekly Work Report", title_style))
    elements.append(Paragraph("Weekly Accountability & Performance Overview", subtitle_style))
    elements.append(Spacer(1, 10))
    elements.append(HRFlowable(width="100%", thickness=1.5, color=colors.HexColor('#3B82F6'), spaceAfter=12))

    # Meta Info Table
    user_name = report.get("user_name", "N/A")
    user_email = report.get("user_email", "N/A")
    manager_name = report.get("manager_name", "N/A")
    week_str = f"{report.get('week_start_date')} to {report.get('week_end_date')}"
    status = (report.get("status") or "draft").capitalize()
    submitted_at = str(report.get("submitted_at") or "Not yet submitted")[:19]

    meta_data = [
        [
            Paragraph("<b>Employee:</b> " + user_name, body_style),
            Paragraph("<b>Week:</b> " + week_str, body_style)
        ],
        [
            Paragraph("<b>Email:</b> " + user_email, body_style),
            Paragraph("<b>Status:</b> " + status, body_style)
        ],
        [
            Paragraph("<b>Manager:</b> " + manager_name, body_style),
            Paragraph("<b>Submitted:</b> " + submitted_at, body_style)
        ]
    ]

    meta_table = Table(meta_data, colWidths=[270, 270])
    meta_table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#F8FAFC')),
        ('PADDING', (0, 0), (-1, -1), 6),
        ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#F1F5F9')),
    ]))
    elements.append(meta_table)
    elements.append(Spacer(1, 14))

    # AI Summary Section
    ai = report.get("ai_summary")
    if ai:
        elements.append(Paragraph("🤖 AI-Generated Executive Summary", h2_style))
        model_str = ai.get("model_used", "AI Model")
        elements.append(Paragraph(f"<i>Powered by {model_str}</i>", subtitle_style))
        elements.append(Spacer(1, 4))

        exec_summary = ai.get("executive_summary", "")
        highlights = ai.get("key_highlights", [])
        blockers = ai.get("blockers_identified", [])
        recommendation = ai.get("manager_recommendation", "")

        ai_content = [
            [Paragraph("<b>Executive Overview:</b>", bold_label)],
            [Paragraph(exec_summary, ai_box_text)],
            [Spacer(1, 4)],
            [Paragraph("<b>Key Highlights:</b>", bold_label)],
            [Paragraph("<br/>".join([f"• {h}" for h in highlights]) if highlights else "None", ai_box_text)],
            [Spacer(1, 4)],
            [Paragraph("<b>Blockers / Challenges Identified:</b>", bold_label)],
            [Paragraph("<br/>".join([f"• {b}" for b in blockers]) if blockers else "None", ai_box_text)],
            [Spacer(1, 4)],
            [Paragraph("<b>Manager Action Recommendation:</b>", bold_label)],
            [Paragraph(recommendation, ai_box_text)]
        ]

        ai_table = Table(ai_content, colWidths=[540])
        ai_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#EEF2FF')),
            ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#818CF8')),
            ('PADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(ai_table)
        elements.append(Spacer(1, 14))

    # Weekly Questions Section
    elements.append(Paragraph("📋 Weekly Reflection Questions", h2_style))
    answers = report.get("answers", [])
    if answers:
        q_data = []
        for a in answers:
            q_text = a.get("question_text", "Question")
            ans_text = a.get("answer", "") or "<i>No answer provided</i>"
            q_data.append([Paragraph(f"<b>Q: {q_text}</b>", bold_label)])
            q_data.append([Paragraph(ans_text.replace('\n', '<br/>'), body_style)])
            q_data.append([Spacer(1, 4)])

        q_table = Table(q_data, colWidths=[540])
        q_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#FAFAFA')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#E5E7EB')),
            ('PADDING', (0, 0), (-1, -1), 5),
        ]))
        elements.append(q_table)
    else:
        elements.append(Paragraph("No questions recorded.", body_style))

    elements.append(Spacer(1, 14))

    # Work Updates Section
    elements.append(Paragraph("🗓️ Daily Work Updates", h2_style))
    updates = report.get("work_updates", [])
    if updates:
        table_rows = [
            [
                Paragraph("<b>Date</b>", bold_label),
                Paragraph("<b>Category</b>", bold_label),
                Paragraph("<b>Hours</b>", bold_label),
                Paragraph("<b>Details</b>", bold_label)
            ]
        ]
        for u in updates:
            date_str = u.get("date", "")
            cat = u.get("category", "-")
            hours = f"{u.get('hours_spent')}h" if u.get('hours_spent') is not None else "-"
            title = u.get("title", "")
            desc = u.get("description", "")
            detail_html = f"<b>{title}</b><br/>{desc}"
            table_rows.append([
                Paragraph(date_str, body_style),
                Paragraph(cat, body_style),
                Paragraph(hours, body_style),
                Paragraph(detail_html, body_style)
            ])

        update_table = Table(table_rows, colWidths=[70, 75, 45, 350])
        update_table.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#F1F5F9')),
            ('BOX', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
            ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#E2E8F0')),
            ('PADDING', (0, 0), (-1, -1), 5),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ]))
        elements.append(update_table)
    else:
        elements.append(Paragraph("No daily work updates logged for this week.", body_style))

    doc.build(elements)
    buffer.seek(0)
    return buffer
