#!/usr/bin/env python3
"""Generate the AEGIS Autonomous Adaptive Portfolio Hedge Agent Pitch Deck (.pptx).

Styles:
- 16:9 Widescreen (13.333 x 7.5 inches)
- FT Luxury Editorial "Alabaster Spruce" Theme:
  - Canvas: #F4F7F5 (Alabaster Botanical)
  - Spruce Green: #1B4332 (Primary Accent)
  - Antique Gold: #A67C37 (Hairline / Accent)
  - Charcoal Slate: #0E1713 (Text Main)
  - Sage Muted: #52665C (Subtitles & Labels)
  - Card Fill: #FFFFFF (Crisp White)
  - Border: #CCD8D2 (Technical Line)
"""

from __future__ import annotations

import os
from pptx import Presentation
from pptx.util import Inches, Pt
from pptx.dml.color import RGBColor
from pptx.enum.text import PP_ALIGN
from pptx.enum.shapes import MSO_SHAPE

# Brand Colors
COLOR_SPRUCE = RGBColor(0x1B, 0x43, 0x32)       # Primary Dark Spruce #1B4332
COLOR_SPRUCE_DARK = RGBColor(0x0F, 0x27, 0x1D)  # Ultra Dark Spruce
COLOR_GOLD = RGBColor(0xA6, 0x7C, 0x37)         # Antique Gold #A67C37
COLOR_GOLD_LIGHT = RGBColor(0xD4, 0xAF, 0x67)   # Pale Gold
COLOR_CHARCOAL = RGBColor(0x0E, 0x17, 0x13)     # Main Text #0E1713
COLOR_SAGE = RGBColor(0x52, 0x66, 0x5C)         # Muted Sage #52665C
COLOR_CANVAS = RGBColor(0xF4, 0xF7, 0xF5)       # Alabaster Canvas #F4F7F5
COLOR_WHITE = RGBColor(0xFF, 0xFF, 0xFF)        # Pure White #FFFFFF
COLOR_BORDER = RGBColor(0xCC, 0xD8, 0xD2)       # Card Border #CCD8D2
COLOR_CARD_SUBTLE = RGBColor(0xEA, 0xF1, 0xEE)  # Sage Card Fill
COLOR_SAFE = RGBColor(0x15, 0x80, 0x3D)         # Forest Green #15803D
COLOR_WARNING = RGBColor(0xD9, 0x77, 0x06)      # Amber #D97706
COLOR_DANGER = RGBColor(0xBE, 0x12, 0x3C)       # Ruby Red #BE123C
COLOR_TEAL = RGBColor(0x0D, 0x94, 0x88)         # Cyan Teal #0D9488

FONT_SERIF = "Georgia"
FONT_SANS = "Segoe UI"
FONT_MONO = "Consolas"

def create_deck(output_path: str = "AEGIS_Pitch_Deck.pptx") -> str:
    prs = Presentation()
    prs.slide_width = Inches(13.333)
    prs.slide_height = Inches(7.5)
    blank_layout = prs.slide_layouts[6]  # Blank slide

    def set_canvas_bg(slide, dark: bool = False):
        bg = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, 0, 0, Inches(13.333), Inches(7.5))
        bg.fill.solid()
        if dark:
            bg.fill.fore_color.rgb = COLOR_SPRUCE_DARK
            bg.line.color.rgb = COLOR_SPRUCE_DARK
        else:
            bg.fill.fore_color.rgb = COLOR_CANVAS
            bg.line.color.rgb = COLOR_CANVAS

    def add_slide_header(slide, category: str, title: str, subtitle: str = ""):
        # Gold Hairline top rule
        gold_line = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(0.8), Inches(0.4), Inches(11.733), Inches(0.04))
        gold_line.fill.solid()
        gold_line.fill.fore_color.rgb = COLOR_GOLD
        gold_line.line.fill.background()

        # Category Badge
        cat_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.55), Inches(8), Inches(0.35))
        tf_cat = cat_box.text_frame
        tf_cat.word_wrap = True
        tf_cat.margin_left = tf_cat.margin_top = tf_cat.margin_bottom = tf_cat.margin_right = 0
        p_cat = tf_cat.paragraphs[0]
        p_cat.text = category.upper()
        p_cat.font.name = FONT_MONO
        p_cat.font.size = Pt(10)
        p_cat.font.bold = True
        p_cat.font.color.rgb = COLOR_GOLD

        # Slide Title
        title_box = slide.shapes.add_textbox(Inches(0.8), Inches(0.85), Inches(10), Inches(0.65))
        tf_title = title_box.text_frame
        tf_title.word_wrap = True
        tf_title.margin_left = tf_title.margin_top = tf_title.margin_bottom = tf_title.margin_right = 0
        p_title = tf_title.paragraphs[0]
        p_title.text = title
        p_title.font.name = FONT_SERIF
        p_title.font.size = Pt(24)
        p_title.font.bold = True
        p_title.font.color.rgb = COLOR_SPRUCE

        if subtitle:
            sub_box = slide.shapes.add_textbox(Inches(0.8), Inches(1.48), Inches(11.7), Inches(0.35))
            tf_sub = sub_box.text_frame
            tf_sub.word_wrap = True
            tf_sub.margin_left = tf_sub.margin_top = tf_sub.margin_bottom = tf_sub.margin_right = 0
            p_sub = tf_sub.paragraphs[0]
            p_sub.text = subtitle
            p_sub.font.name = FONT_SANS
            p_sub.font.size = Pt(12)
            p_sub.font.color.rgb = COLOR_SAGE

    def add_card(slide, left: float, top: float, width: float, height: float,
                 bg_color: RGBColor = COLOR_WHITE, border_color: RGBColor = COLOR_BORDER,
                 accent_top: bool = True, accent_color: RGBColor = COLOR_SPRUCE):
        card = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(height))
        card.fill.solid()
        card.fill.fore_color.rgb = bg_color
        card.line.color.rgb = border_color
        card.line.width = Pt(1)

        if accent_top:
            acc = slide.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(left), Inches(top), Inches(width), Inches(0.04))
            acc.fill.solid()
            acc.fill.fore_color.rgb = accent_color
            acc.line.fill.background()

        return card

    # =========================================================================
    # SLIDE 1: Title Slide (Dark Spruce Luxury Editorial)
    # =========================================================================
    s1 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s1, dark=True)

    # Top gold rule
    line1 = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.0), Inches(10.933), Inches(0.05))
    line1.fill.solid()
    line1.fill.fore_color.rgb = COLOR_GOLD
    line1.line.fill.background()

    # Category Pill
    pill = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(1.2), Inches(1.4), Inches(3.2), Inches(0.4))
    pill.fill.solid()
    pill.fill.fore_color.rgb = RGBColor(0x27, 0x56, 0x42)
    pill.line.color.rgb = COLOR_GOLD
    pill.line.width = Pt(1)
    tf_pill = pill.text_frame
    p_pill = tf_pill.paragraphs[0]
    p_pill.text = "ALPACA HACKATHON 2026 SUBMISSION"
    p_pill.font.name = FONT_MONO
    p_pill.font.size = Pt(10)
    p_pill.font.bold = True
    p_pill.font.color.rgb = COLOR_GOLD_LIGHT
    p_pill.alignment = PP_ALIGN.CENTER

    # Brand Title
    tb_title = s1.shapes.add_textbox(Inches(1.2), Inches(2.1), Inches(10.9), Inches(1.5))
    tf_title = tb_title.text_frame
    tf_title.word_wrap = True
    p1 = tf_title.paragraphs[0]
    p1.text = "AEGIS // PRIVATE WEALTH"
    p1.font.name = FONT_SERIF
    p1.font.size = Pt(46)
    p1.font.bold = True
    p1.font.color.rgb = COLOR_WHITE

    p2 = tf_title.add_paragraph()
    p2.text = "Autonomous Adaptive Portfolio Hedge Agent"
    p2.font.name = FONT_SERIF
    p2.font.size = Pt(26)
    p2.font.color.rgb = COLOR_GOLD_LIGHT
    p2.space_before = Pt(8)

    # Subtitle / Core Thesis
    tb_thesis = s1.shapes.add_textbox(Inches(1.2), Inches(4.1), Inches(10.9), Inches(1.2))
    tf_thesis = tb_thesis.text_frame
    tf_thesis.word_wrap = True
    p_th = tf_thesis.paragraphs[0]
    p_th.text = "A closed-loop multi-agent risk engine that transforms live Alpaca portfolios into self-protecting assets. Evaluates competing options hedges, enforces deterministic risk gates, executes multi-leg orders, and dynamically rebalances as market regimes shift."
    p_th.font.name = FONT_SANS
    p_th.font.size = Pt(15)
    p_th.font.color.rgb = RGBColor(0xD2, 0xDF, 0xD8)

    # 3 Feature Cards at Bottom
    features = [
        ("MULTI-AGENT REASONING", "LangGraph DAG + LLM Tournament"),
        ("DETERMINISTIC RISK GATE", "Zero Hallucinations • Hard Quant Math"),
        ("CLOSED-LOOP ADAPTATION", "Level-1 Drift & Level-2 De-Hedging"),
    ]
    card_w = 3.4
    for i, (title, desc) in enumerate(features):
        x = 1.2 + i * (card_w + 0.36)
        c = s1.shapes.add_shape(MSO_SHAPE.RECTANGLE, Inches(x), Inches(5.6), Inches(card_w), Inches(1.1))
        c.fill.solid()
        c.fill.fore_color.rgb = RGBColor(0x15, 0x36, 0x28)
        c.line.color.rgb = RGBColor(0x35, 0x62, 0x4F)
        c.line.width = Pt(1)
        tf = c.text_frame
        tf.word_wrap = True
        p_c1 = tf.paragraphs[0]
        p_c1.text = title
        p_c1.font.name = FONT_MONO
        p_c1.font.size = Pt(11)
        p_c1.font.bold = True
        p_c1.font.color.rgb = COLOR_GOLD_LIGHT

        p_c2 = tf.add_paragraph()
        p_c2.text = desc
        p_c2.font.name = FONT_SANS
        p_c2.font.size = Pt(11)
        p_c2.font.color.rgb = COLOR_WHITE
        p_c2.space_before = Pt(4)

    s1.notes_slide.notes_text_frame.text = (
        "Welcome judges and investors. Today we present AEGIS: the Autonomous Adaptive Portfolio Hedge Agent. "
        "Our mission is simple: transform a live Alpaca equity portfolio into a self-protecting financial asset. "
        "Unlike standard bots that blindly trade or guess market direction, AEGIS is a closed-loop institutional "
        "risk engine that combines multi-agent strategic reasoning with deterministic quantitative risk controls."
    )

    # =========================================================================
    # SLIDE 2: The Problem
    # =========================================================================
    s2 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s2)
    add_slide_header(s2, "Problem Statement", "Traditional Portfolio Hedging is Broken",
                     "Why static, manual, and heuristic-based hedging strategies consistently destroy portfolio alpha.")

    problem_cards = [
        ("01", "Naive Heuristics & Blind Rules",
         "Common industry rules like 'If down 10%, buy puts' fail completely in real markets.",
         ["Ignores market regime and why the asset is dropping",
          "Blind to implied volatility (IV) inflation and skew",
          "Buys overpriced protection at the market bottom",
          "Zero awareness of sector basis risk vs systemic shock"]),
        ("02", "Excessive Carry Cost & Alpha Drag",
         "Passive long puts act as a relentless tax on long-term compound performance.",
         ["Bleeds 5% to 9% annualized alpha through theta decay",
          "Unfunded single-leg puts suffer severe time decay",
          "Fails to leverage spreads or collars to offset premium",
          "Investors abandon protection just before crises occur"]),
        ("03", "The Unsolved 'Exit Problem'",
         "Traditional managers know when to buy protection, but never when to dismantle it.",
         ["Hedges are left on as markets recover, killing upside",
          "Manual adjustment is lagged, emotional, and slow",
          "Legging risk: partial fills during multi-leg rebalancing",
          "No automated feedback loop to harvest option profits"]),
    ]

    cw = 3.64
    for i, (num, title, sub, bullets) in enumerate(problem_cards):
        x = 0.8 + i * (cw + 0.4)
        add_card(s2, x, 1.95, cw, 4.3, accent_color=COLOR_DANGER)

        tb = s2.shapes.add_textbox(Inches(x + 0.2), Inches(2.1), Inches(cw - 0.4), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_num = tf.paragraphs[0]
        p_num.text = num
        p_num.font.name = FONT_MONO
        p_num.font.size = Pt(20)
        p_num.font.bold = True
        p_num.font.color.rgb = COLOR_DANGER

        p_t = tf.add_paragraph()
        p_t.text = title
        p_t.font.name = FONT_SERIF
        p_t.font.size = Pt(16)
        p_t.font.bold = True
        p_t.font.color.rgb = COLOR_SPRUCE
        p_t.space_before = Pt(4)

        p_s = tf.add_paragraph()
        p_s.text = sub
        p_s.font.name = FONT_SANS
        p_s.font.size = Pt(11)
        p_s.font.color.rgb = COLOR_SAGE
        p_s.space_before = Pt(6)

        for b in bullets:
            p_b = tf.add_paragraph()
            p_b.text = f"• {b}"
            p_b.font.name = FONT_SANS
            p_b.font.size = Pt(11)
            p_b.font.color.rgb = COLOR_CHARCOAL
            p_b.space_before = Pt(4)

    add_card(s2, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_bot = s2.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_bot = tb_bot.text_frame
    tf_bot.word_wrap = True
    p_bot = tf_bot.paragraphs[0]
    p_bot.text = "CORE TAKEAWAY: Portfolios do not need static rules or speculative predictions — they need continuous, adaptive risk management that actively dials protection up AND down."
    p_bot.font.name = FONT_MONO
    p_bot.font.size = Pt(11)
    p_bot.font.bold = True
    p_bot.font.color.rgb = COLOR_SPRUCE

    s2.notes_slide.notes_text_frame.text = (
        "Slide 2 establishes the core financial problem. Static hedging either bleeds your returns dry "
        "through constant put decay, or it fails to adapt when volatility regimes switch. Worst of all, "
        "most systems have no concept of de-hedging — when the market rebounds, they leave the puts on "
        "and watch their protection expire worthless while capping upside. AEGIS solves all three flaws."
    )

    # =========================================================================
    # SLIDE 3: The Solution - 5 Core Questions
    # =========================================================================
    s3 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s3)
    add_slide_header(s3, "System Objective", "The Solution: Continuous Closed-Loop Defense",
                     "AEGIS operates as an autonomous risk engine that continuously answers 5 foundational questions.")

    questions = [
        ("Q1", "Risk Detection", "What specific risks exist?",
         "Audits portfolio beta, factor concentration, drawdown, and macro market volatility shocks in real time."),
        ("Q2", "Protection Sizing", "How much protection is needed?",
         "Calculates exact mathematical hedge ratios using Black-Scholes Greeks, Cornish-Fisher VaR, and budget limits."),
        ("Q3", "Option Discovery", "Which structures are viable?",
         "Screens Alpaca option chains across strike, expiration, liquidity, IV skew, and multi-leg feasibility."),
        ("Q4", "Strategy Tournament", "Which trade-off is optimal?",
         "Compares 4 competing strategy hypotheses across 8 quantitative dimensions to select the best fit."),
        ("Q5", "Adaptive Lifecycle", "Should we adjust or remove?",
         "Continuously monitors hedge drift and market stabilization to increase, reduce, roll, or dismantle protection."),
    ]

    card_w = 2.18
    for i, (q, title, subtitle, detail) in enumerate(questions):
        x = 0.8 + i * (card_w + 0.2)
        add_card(s3, x, 1.95, card_w, 4.3, accent_color=COLOR_GOLD)

        tb = s3.shapes.add_textbox(Inches(x + 0.15), Inches(2.1), Inches(card_w - 0.3), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_q = tf.paragraphs[0]
        p_q.text = q
        p_q.font.name = FONT_MONO
        p_q.font.size = Pt(24)
        p_q.font.bold = True
        p_q.font.color.rgb = COLOR_GOLD

        p_t = tf.add_paragraph()
        p_t.text = title
        p_t.font.name = FONT_SERIF
        p_t.font.size = Pt(15)
        p_t.font.bold = True
        p_t.font.color.rgb = COLOR_SPRUCE
        p_t.space_before = Pt(4)

        p_s = tf.add_paragraph()
        p_s.text = subtitle
        p_s.font.name = FONT_SANS
        p_s.font.size = Pt(11)
        p_s.font.bold = True
        p_s.font.color.rgb = COLOR_CHARCOAL
        p_s.space_before = Pt(6)

        p_d = tf.add_paragraph()
        p_d.text = detail
        p_d.font.name = FONT_SANS
        p_d.font.size = Pt(11)
        p_d.font.color.rgb = COLOR_SAGE
        p_d.space_before = Pt(8)

    add_card(s3, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_SPRUCE, accent_top=False)
    tb_b = s3.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_b = tb_b.text_frame
    tf_b.word_wrap = True
    p_b = tf_b.paragraphs[0]
    p_b.text = "THE NORTH STAR: We do not predict market tops or bottoms. We continuously measure risk and dynamically adapt protection."
    p_b.font.name = FONT_MONO
    p_b.font.size = Pt(11)
    p_b.font.bold = True
    p_b.font.color.rgb = COLOR_WHITE

    s3.notes_slide.notes_text_frame.text = (
        "Here is the core logic loop. AEGIS continuously asks these 5 questions. "
        "Notice Q5: this is the crown jewel. Most trading bots only open positions. "
        "AEGIS actively manages the complete lifecycle, asking whether an existing hedge should be "
        "increased, decreased, rolled, or completely removed when the storm passes."
    )

    # =========================================================================
    # SLIDE 4: Architectural Law
    # =========================================================================
    s4 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s4)
    add_slide_header(s4, "System Design Law", "Agents Reason. Tools Provide. Deterministic Code Enforces.",
                     "Strict separation of concerns: LLMs provide qualitative judgment; pure Python math provides absolute safety.")

    pillars = [
        ("AGENTS REASON", "LLM Contextual Reasoning Layer", COLOR_SPRUCE,
         ["Analyzes macroeconomic market regimes",
          "Evaluates qualitative trade-offs between hedge candidates",
          "Synthesizes breaking news sentiment & shock events",
          "Formulates strategic hypotheses with plain-English rationales",
          "Dual-provider: Featherless AI (Submission) & OpenRouter (Dev)"]),
        ("TOOLS PROVIDE", "Integration & Ingestion Layer", COLOR_GOLD,
         ["Alpaca Trading & Market Data API streaming",
          "Full option chain retrieval & liquidity filtering",
          "Real-time news ingestion and corporate actions",
          "Alpaca MCP server interface for tool calling",
          "Persistent PostgreSQL state & auditable agent run logs"]),
        ("DETERMINISTIC CODE ENFORCES", "Quantitative Safety & Risk Gate", COLOR_DANGER,
         ["Zero hallucinated math — LLMs never compute Greeks or VaR",
          "Black-Scholes Delta (Δ), Gamma (Γ), Theta (Θ), Vega (ν)",
          "Parametric & Cornish-Fisher Value-at-Risk (VaR)",
          "Hard risk limits: maximum budget, notional, and position size",
          "Non-negotiable veto: Risk Agent overrides any LLM decision"]),
    ]

    pw = 3.64
    for i, (pill_title, pill_sub, acc_col, points) in enumerate(pillars):
        x = 0.8 + i * (pw + 0.4)
        add_card(s4, x, 1.95, pw, 4.3, accent_color=acc_col)

        tb = s4.shapes.add_textbox(Inches(x + 0.2), Inches(2.1), Inches(pw - 0.4), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_t1 = tf.paragraphs[0]
        p_t1.text = pill_title
        p_t1.font.name = FONT_MONO
        p_t1.font.size = Pt(13)
        p_t1.font.bold = True
        p_t1.font.color.rgb = acc_col

        p_t2 = tf.add_paragraph()
        p_t2.text = pill_sub
        p_t2.font.name = FONT_SERIF
        p_t2.font.size = Pt(15)
        p_t2.font.bold = True
        p_t2.font.color.rgb = COLOR_SPRUCE
        p_t2.space_before = Pt(4)

        for p in points:
            p_pt = tf.add_paragraph()
            p_pt.text = f"• {p}"
            p_pt.font.name = FONT_SANS
            p_pt.font.size = Pt(11)
            p_pt.font.color.rgb = COLOR_CHARCOAL
            p_pt.space_before = Pt(6)

    add_card(s4, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_g = s4.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_g = tb_g.text_frame
    tf_g.word_wrap = True
    p_g = tf_g.paragraphs[0]
    p_g.text = "MANDATORY SAFETY RULE: If an LLM proposes a trade that breaches the maximum hedge budget by $1, the deterministic Risk Gate instantly vetos or resizes the order without exception."
    p_g.font.name = FONT_MONO
    p_g.font.size = Pt(10)
    p_g.font.bold = True
    p_g.font.color.rgb = COLOR_DANGER

    s4.notes_slide.notes_text_frame.text = (
        "This is the single most important slide for judges evaluating safety and robustness. "
        "We adhere strictly to: Agents reason. Tools provide. Deterministic code enforces. "
        "Never let an LLM do financial math. LLMs reason about trade-offs and market narratives; "
        "deterministic Python code computes Black-Scholes Greeks, VaR, and enforces hard risk bounds."
    )

    # =========================================================================
    # SLIDE 5: Multi-Agent Orchestration
    # =========================================================================
    s5 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s5)
    add_slide_header(s5, "Multi-Agent Orchestration", "Stateful LangGraph DAG & The HedgeContext",
                     "Eliminating context dilution through specialized agent responsibilities and standardized data contracts.")

    add_card(s5, 0.8, 1.95, 5.6, 4.3, accent_color=COLOR_SPRUCE)
    tb_ing = s5.shapes.add_textbox(Inches(1.0), Inches(2.1), Inches(5.2), Inches(4.0))
    tf_ing = tb_ing.text_frame
    tf_ing.word_wrap = True
    tf_ing.margin_top = tf_ing.margin_left = tf_ing.margin_right = tf_ing.margin_bottom = 0

    p_it = tf_ing.paragraphs[0]
    p_it.text = "THE 5 SPECIALIZED INGESTION AGENTS"
    p_it.font.name = FONT_MONO
    p_it.font.size = Pt(13)
    p_it.font.bold = True
    p_it.font.color.rgb = COLOR_SPRUCE

    ing_agents = [
        ("Portfolio Management Agent", "Audits holdings, liquidation value, concentration, beta, and current hedge delta."),
        ("Stock Analysis Agent", "Computes idiosyncratic momentum, realized volatility, and correlation matrices."),
        ("Market Analysis Agent", "Tracks SPY/QQQ technicals, macro regimes, and VIX term structure."),
        ("News Analysis Agent", "Filters high-impact earnings releases, macro catalysts, and tail-risk headlines."),
        ("Options Analysis Agent", "Parses Alpaca option chains, filtering by moneyness, open interest, and bid-ask spreads."),
    ]
    for name, desc in ing_agents:
        p_n = tf_ing.add_paragraph()
        p_n.text = f"▶ {name}"
        p_n.font.name = FONT_SERIF
        p_n.font.size = Pt(12)
        p_n.font.bold = True
        p_n.font.color.rgb = COLOR_CHARCOAL
        p_n.space_before = Pt(6)

        p_d = tf_ing.add_paragraph()
        p_d.text = desc
        p_d.font.name = FONT_SANS
        p_d.font.size = Pt(10)
        p_d.font.color.rgb = COLOR_SAGE

    add_card(s5, 6.8, 1.95, 5.733, 4.3, accent_color=COLOR_GOLD)
    tb_hc = s5.shapes.add_textbox(Inches(7.0), Inches(2.1), Inches(5.3), Inches(4.0))
    tf_hc = tb_hc.text_frame
    tf_hc.word_wrap = True
    tf_hc.margin_top = tf_hc.margin_left = tf_hc.margin_right = tf_hc.margin_bottom = 0

    p_hct = tf_hc.paragraphs[0]
    p_hct.text = "THE STANDARDIZED HEDGECONTEXT CONTRACT"
    p_hct.font.name = FONT_MONO
    p_hct.font.size = Pt(13)
    p_hct.font.bold = True
    p_hct.font.color.rgb = COLOR_GOLD

    p_hcd = tf_hc.add_paragraph()
    p_hcd.text = "All raw telemetry is assembled into a single immutable, validated Pydantic contract. Downstream strategy agents receive clean, pre-computed inputs to prevent token bloat and hallucination:"
    p_hcd.font.name = FONT_SANS
    p_hcd.font.size = Pt(11)
    p_hcd.font.color.rgb = COLOR_CHARCOAL
    p_hcd.space_before = Pt(4)

    contract_fields = [
        ("portfolio_state", "AUM, cash, positions, beta, drawdown, existing hedges"),
        ("market_state", "Regime (Bull/Bear/Shock), VIX level, trend strength"),
        ("stock_state", "Idiosyncratic volatility, contribution to portfolio VaR"),
        ("news_context", "High-priority risk events, sentiment impact score"),
        ("option_candidates", "Pre-filtered liquid strikes with verified Black-Scholes Greeks"),
    ]
    for field, detail in contract_fields:
        p_f = tf_hc.add_paragraph()
        p_f.text = f"• {field}: {detail}"
        p_f.font.name = FONT_MONO
        p_f.font.size = Pt(10)
        p_f.font.color.rgb = COLOR_SPRUCE
        p_f.space_before = Pt(4)

    add_card(s5, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_SPRUCE_DARK, accent_top=False)
    tb_fl = s5.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_fl = tb_fl.text_frame
    tf_fl.word_wrap = True
    p_fl = tf_fl.paragraphs[0]
    p_fl.text = "WORKFLOW: Ingestion Agents ➔ HedgeContext ➔ 4 Strategy Agents ➔ Strategy Manager ➔ Risk Gate ➔ Alpaca Fill"
    p_fl.font.name = FONT_MONO
    p_fl.font.size = Pt(11)
    p_fl.font.bold = True
    p_fl.font.color.rgb = COLOR_GOLD_LIGHT

    s5.notes_slide.notes_text_frame.text = (
        "This slide breaks down our LangGraph state machine. Notice how we solve context dilution. "
        "Rather than dumping raw web text and raw price ticks into an LLM prompt, our 5 Ingestion Agents "
        "distill the data into a clean, typed HedgeContext contract. Every downstream agent operates on verified facts."
    )

    # =========================================================================
    # SLIDE 6: Strategy Arena
    # =========================================================================
    s6 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s6)
    add_slide_header(s6, "Strategy Layer", "The Strategy Arena: 4 Competing Option Architectures",
                     "Specialized agents formulate competing hypotheses evaluated across 8 quantitative dimensions.")

    strategies = [
        ("PROTECTIVE PUT", "Direct Downside Floor", COLOR_SPRUCE,
         "Buy OTM Put",
         "Full catastrophic protection with 100% upside retention.",
         "High cash premium, negative theta carry bleed.",
         "High-conviction crash or imminent shock regime."),
        ("BEAR PUT SPREAD", "Corridor Protection", COLOR_GOLD,
         "Buy High Put + Sell Low Put",
         "Substantially reduced net premium cost with defined protection zone.",
         "Protection capped below the short put strike.",
         "Moderate drawdown defense within hedge budget."),
        ("COLLAR STRUCTURE", "Self-Funded Hedge", COLOR_TEAL,
         "Buy OTM Put + Sell OTM Call",
         "Near-zero cash outlay; short call fully funds the long put.",
         "Upside potential strictly capped at short call strike.",
         "High IV environments where cash protection is overpriced."),
        ("NO-HEDGE DISCIPLINE", "Capital Preservation", COLOR_SAGE,
         "No Trade / Maintain Cash",
         "Zero premium spend; 100% upside participation and liquidity.",
         "Exposed to unhedged market tail risk.",
         "Low volatility, healthy portfolio, or unfavorable option skew."),
    ]

    sw = 2.68
    for i, (name, role, col, structure, pros, cons, regime) in enumerate(strategies):
        x = 0.8 + i * (sw + 0.33)
        add_card(s6, x, 1.95, sw, 4.3, accent_color=col)

        tb = s6.shapes.add_textbox(Inches(x + 0.15), Inches(2.1), Inches(sw - 0.3), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_t = tf.paragraphs[0]
        p_t.text = name
        p_t.font.name = FONT_MONO
        p_t.font.size = Pt(13)
        p_t.font.bold = True
        p_t.font.color.rgb = col

        p_r = tf.add_paragraph()
        p_r.text = role
        p_r.font.name = FONT_SERIF
        p_r.font.size = Pt(14)
        p_r.font.bold = True
        p_r.font.color.rgb = COLOR_CHARCOAL
        p_r.space_before = Pt(2)

        p_st = tf.add_paragraph()
        p_st.text = f"Structure: {structure}"
        p_st.font.name = FONT_MONO
        p_st.font.size = Pt(10)
        p_st.font.color.rgb = COLOR_SPRUCE
        p_st.space_before = Pt(4)

        p_p = tf.add_paragraph()
        p_p.text = f"+ Advantage: {pros}"
        p_p.font.name = FONT_SANS
        p_p.font.size = Pt(10)
        p_p.font.color.rgb = COLOR_SAFE
        p_p.space_before = Pt(6)

        p_c = tf.add_paragraph()
        p_c.text = f"- Trade-off: {cons}"
        p_c.font.name = FONT_SANS
        p_c.font.size = Pt(10)
        p_c.font.color.rgb = COLOR_DANGER
        p_c.space_before = Pt(4)

        p_rg = tf.add_paragraph()
        p_rg.text = f"▶ Regime: {regime}"
        p_rg.font.name = FONT_SANS
        p_rg.font.size = Pt(10)
        p_rg.font.color.rgb = COLOR_SAGE
        p_rg.space_before = Pt(6)

    add_card(s6, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_8d = s6.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_8d = tb_8d.text_frame
    tf_8d.word_wrap = True
    p_8d = tf_8d.paragraphs[0]
    p_8d.text = "STRATEGY MANAGER 8-D CRITERIA: Basis Risk • Net Carry Cost • Greeks Profile • Payoff Convexity • IV Surface Fit • Liquidity • Sizing • Opportunity Cost"
    p_8d.font.name = FONT_MONO
    p_8d.font.size = Pt(10)
    p_8d.font.bold = True
    p_8d.font.color.rgb = COLOR_SPRUCE

    s6.notes_slide.notes_text_frame.text = (
        "Here is the strategy arena. Instead of forcing one fixed strategy, we run a competition. "
        "Notice the 4th agent: No-Hedge Discipline. This is crucial: an autonomous trading agent must have "
        "the discipline to recommend 'DO NOTHING' if protection is overpriced or unnecessary. "
        "The Strategy Manager compares all viable proposals using an 8-dimensional scoring matrix."
    )

    # =========================================================================
    # SLIDE 7: Risk Gate & Alpaca Execution
    # =========================================================================
    s7 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s7)
    add_slide_header(s7, "Execution & Safety", "Deterministic Risk Gate & Alpaca Execution",
                     "No trade touches Alpaca paper brokerage without clearing 6 deterministic mathematical guardrails.")

    add_card(s7, 0.8, 1.95, 5.6, 4.3, accent_color=COLOR_DANGER)
    tb_rg = s7.shapes.add_textbox(Inches(1.0), Inches(2.1), Inches(5.2), Inches(4.0))
    tf_rg = tb_rg.text_frame
    tf_rg.word_wrap = True
    tf_rg.margin_top = tf_rg.margin_left = tf_rg.margin_right = tf_rg.margin_bottom = 0

    p_rgt = tf_rg.paragraphs[0]
    p_rgt.text = "THE 6 HARD DETERMINISTIC RISK GUARDRAILS"
    p_rgt.font.name = FONT_MONO
    p_rgt.font.size = Pt(13)
    p_rgt.font.bold = True
    p_rgt.font.color.rgb = COLOR_DANGER

    gates = [
        ("1. Max Hedge Ratio Cap", "Enforces maximum 40% portfolio notional protection to prevent over-hedging."),
        ("2. Cash Budget Ceiling", "Hard cap on option premium spend (e.g. max 2.5% of total portfolio value)."),
        ("3. Liquidity Screening", "Rejects contracts with wide bid-ask spreads or open interest below threshold."),
        ("4. Tenor Safety Bounds", "Filters out ultra-short theta death (<7 DTE) and illiquid LEAPS (>90 DTE)."),
        ("5. Greeks Sensitivity Cap", "Limits portfolio Delta drift (Δ) and excessive Gamma exposure (Γ)."),
        ("6. Margin & Buying Power", "Pre-flight check verifying account cash and buying power sufficiency."),
    ]
    for g_title, g_desc in gates:
        p_gt = tf_rg.add_paragraph()
        p_gt.text = f"✓ {g_title}"
        p_gt.font.name = FONT_SERIF
        p_gt.font.size = Pt(12)
        p_gt.font.bold = True
        p_gt.font.color.rgb = COLOR_SPRUCE
        p_gt.space_before = Pt(4)

        p_gd = tf_rg.add_paragraph()
        p_gd.text = g_desc
        p_gd.font.name = FONT_SANS
        p_gd.font.size = Pt(10)
        p_gd.font.color.rgb = COLOR_SAGE

    add_card(s7, 6.8, 1.95, 5.733, 4.3, accent_color=COLOR_SPRUCE)
    tb_al = s7.shapes.add_textbox(Inches(7.0), Inches(2.1), Inches(5.3), Inches(4.0))
    tf_al = tb_al.text_frame
    tf_al.word_wrap = True
    tf_al.margin_top = tf_al.margin_left = tf_al.margin_right = tf_al.margin_bottom = 0

    p_alt = tf_al.paragraphs[0]
    p_alt.text = "NATIVE ALPACA MULTI-LEG BROKERAGE EXECUTION"
    p_alt.font.name = FONT_MONO
    p_alt.font.size = Pt(13)
    p_alt.font.bold = True
    p_alt.font.color.rgb = COLOR_SPRUCE

    alpaca_features = [
        ("Atomic Multi-Leg Orders", "Executes Put Spreads and Collars natively via Alpaca API to completely eliminate 'legging risk' (partial single-leg fills)."),
        ("Alpaca MCP Integration", "Standardized Model Context Protocol tool endpoints for portfolio queries, option chain discovery, and order lifecycle."),
        ("Slippage & Fill Tracking", "Measures fill prices against midpoint and limits, logging exact execution slippage to database."),
        ("Auditable State Transition", "Fills update portfolio snapshots and hedge state; fails trigger automatic recovery workflows."),
    ]
    for af_t, af_d in alpaca_features:
        p_aft = tf_al.add_paragraph()
        p_aft.text = f"▶ {af_t}"
        p_aft.font.name = FONT_SERIF
        p_aft.font.size = Pt(12)
        p_aft.font.bold = True
        p_aft.font.color.rgb = COLOR_CHARCOAL
        p_aft.space_before = Pt(6)

        p_afd = tf_al.add_paragraph()
        p_afd.text = af_d
        p_afd.font.name = FONT_SANS
        p_afd.font.size = Pt(10)
        p_afd.font.color.rgb = COLOR_SAGE

    add_card(s7, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_ac = s7.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_ac = tb_ac.text_frame
    tf_ac.word_wrap = True
    p_ac = tf_ac.paragraphs[0]
    p_ac.text = "FAIL-SAFE ASSURANCE: The Execution Agent has zero discretion to modify approved orders. It only executes what the Risk Gate explicitly approved."
    p_ac.font.name = FONT_MONO
    p_ac.font.size = Pt(10)
    p_ac.font.bold = True
    p_ac.font.color.rgb = COLOR_SPRUCE

    s7.notes_slide.notes_text_frame.text = (
        "Judges love seeing risk management that works in practice. The Risk Gate is the non-negotiable filter. "
        "Even if the Strategy Manager chooses a brilliant spread, if it exceeds our 2.5% premium cap, it is "
        "either resized or vetoed. On execution, we use Alpaca's multi-leg capability so spreads fill atomically, "
        "avoiding asymmetric legging risk."
    )

    # =========================================================================
    # SLIDE 8: The Adaptive Lifecycle
    # =========================================================================
    s8 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s8)
    add_slide_header(s8, "Dynamic Rebalancing", "The Adaptive Lifecycle: 2-Tier Monitoring Loop",
                     "How AEGIS prevents overtrading while actively dismantling protection when market danger subsides.")

    add_card(s8, 0.8, 1.95, 5.6, 4.3, accent_color=COLOR_GOLD)
    tb_t1 = s8.shapes.add_textbox(Inches(1.0), Inches(2.1), Inches(5.2), Inches(4.0))
    tf_t1 = tb_t1.text_frame
    tf_t1.word_wrap = True
    tf_t1.margin_top = tf_t1.margin_left = tf_t1.margin_right = tf_t1.margin_bottom = 0

    p_t1t = tf_t1.paragraphs[0]
    p_t1t.text = "TIER-1: TICK-LEVEL DRIFT DETECTION"
    p_t1t.font.name = FONT_MONO
    p_t1t.font.size = Pt(13)
    p_t1t.font.bold = True
    p_t1t.font.color.rgb = COLOR_GOLD

    t1_points = [
        ("Hedge Drift Tracking", "Calculates the spread between Current Hedge Ratio and Target Hedge Ratio in real time."),
        ("Statistical Deadbands (±2.5%)", "Ignores small intraday market noise to prevent fee-churning and excessive order submission."),
        ("Strict Cooldown Windows", "Enforces a mandatory 60-minute cooldown post-execution to allow price discovery to settle."),
        ("Emergency Shock Override", "Extreme tail-risk shocks (>5% market drop or VIX >35) bypass cooldowns to trigger instant defense."),
    ]
    for t_title, t_desc in t1_points:
        p_pt = tf_t1.add_paragraph()
        p_pt.text = f"▶ {t_title}"
        p_pt.font.name = FONT_SERIF
        p_pt.font.size = Pt(12)
        p_pt.font.bold = True
        p_pt.font.color.rgb = COLOR_CHARCOAL
        p_pt.space_before = Pt(6)

        p_pd = tf_t1.add_paragraph()
        p_pd.text = t_desc
        p_pd.font.name = FONT_SANS
        p_pd.font.size = Pt(10)
        p_pd.font.color.rgb = COLOR_SAGE

    add_card(s8, 6.8, 1.95, 5.733, 4.3, accent_color=COLOR_SAFE)
    tb_t2 = s8.shapes.add_textbox(Inches(7.0), Inches(2.1), Inches(5.3), Inches(4.0))
    tf_t2 = tb_t2.text_frame
    tf_t2.word_wrap = True
    tf_t2.margin_top = tf_t2.margin_left = tf_t2.margin_right = tf_t2.margin_bottom = 0

    p_t2t = tf_t2.paragraphs[0]
    p_t2t.text = "TIER-2: CLOSED-LOOP REASSESSMENT ACTIONS"
    p_t2t.font.name = FONT_MONO
    p_t2t.font.size = Pt(13)
    p_t2t.font.bold = True
    p_t2t.font.color.rgb = COLOR_SAFE

    t2_actions = [
        ("INCREASE", "Market volatility spikes; scales hedge ratio up to target to absorb incoming shock."),
        ("DECREASE (The Differentiator!)", "Market stabilizes; systematically unwinds protection to lock in option gains and avoid theta decay."),
        ("REPLACE / ROLL", "Hedge approaches expiration or delta shifts out of the target corridor; rolls to optimal strike/expiry."),
        ("REMOVE", "Risk returns to baseline normal; closes remaining protection to return portfolio to 100% growth."),
        ("MAINTAIN", "Hedge is performing within optimal bounds; no action taken, saving transaction friction."),
    ]
    for a_title, a_desc in t2_actions:
        p_at = tf_t2.add_paragraph()
        p_at.text = f"• {a_title}"
        p_at.font.name = FONT_MONO
        p_at.font.size = Pt(11)
        p_at.font.bold = True
        p_at.font.color.rgb = COLOR_SPRUCE
        p_at.space_before = Pt(4)

        p_ad = tf_t2.add_paragraph()
        p_ad.text = a_desc
        p_ad.font.name = FONT_SANS
        p_ad.font.size = Pt(10)
        p_ad.font.color.rgb = COLOR_SAGE

    add_card(s8, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_SPRUCE, accent_top=False)
    tb_l = s8.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_l = tb_l.text_frame
    tf_l.word_wrap = True
    p_l = tf_l.paragraphs[0]
    p_l.text = "LIFECYCLE PROOF: AEGIS is not an options-buying bot. It knows when to harvest gains and remove hedges, returning capital to growth."
    p_l.font.name = FONT_MONO
    p_l.font.size = Pt(10)
    p_l.font.bold = True
    p_l.font.color.rgb = COLOR_WHITE

    s8.notes_slide.notes_text_frame.text = (
        "Here is the secret sauce of AEGIS: the 2-tier monitoring loop. "
        "Tier 1 handles high-frequency noise using deadbands and cooldowns so we don't overtrade. "
        "Tier 2 executes full reassessments. And when conditions improve, AEGIS executes DECREASE. "
        "It actively sells or closes hedges, capturing the option gain and eliminating theta drag."
    )

    # =========================================================================
    # SLIDE 9: Institutional UI
    # =========================================================================
    s9 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s9)
    add_slide_header(s9, "Frontend Experience", "Institutional Dashboard: 'Alabaster Spruce' UI",
                     "Swiss private banking elegance combined with real-time quantitative telemetry and auditable decision trails.")

    ui_cards = [
        ("PORTFOLIO KPI TELEMETRY", "Real-Time Equity & Risk Exposure", COLOR_SPRUCE,
         ["Live Net Liquidation Value & Uninvested Cash",
          "Current Drawdown vs Historical High-Water Mark",
          "Hedge Ratio Gauge (Current vs Target)",
          "Hedged P&L vs Unhedged Benchmark Overlay"]),
        ("INTERACTIVE PAYOFF CHART", "Recharts Visual Convexity Model", COLOR_GOLD,
         ["Multi-curve visualization: Unhedged vs Hedged",
          "Downside floor vs Capped upside collar visualization",
          "Interactive spot price slider & breakeven marker",
          "Real-time contract payoff expiration modeling"]),
        ("LIVE GREEKS MATRIX", "Second-Order Sensitivities", COLOR_TEAL,
         ["Portfolio Delta (Δ): Net directional dollar exposure",
          "Gamma (Γ): Rate of delta acceleration",
          "Theta (Θ): Daily time decay dollar cost",
          "Vega (ν): Volatility shift sensitivity"]),
        ("AUDITABLE DECISION TRAIL", "Full Regulatory & Judge Transparency", COLOR_CHARCOAL,
         ["Chronological log of every agent reasoning step",
          "Side-by-side strategy score comparison table",
          "Risk Gate approval/modification audit checklist",
          "Direct links to Alpaca order IDs and fill timestamps"]),
    ]

    uw = 2.68
    for i, (ut, us, ucol, upoints) in enumerate(ui_cards):
        x = 0.8 + i * (uw + 0.33)
        add_card(s9, x, 1.95, uw, 4.3, accent_color=ucol)

        tb = s9.shapes.add_textbox(Inches(x + 0.15), Inches(2.1), Inches(uw - 0.3), Inches(4.0))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_ut = tf.paragraphs[0]
        p_ut.text = ut
        p_ut.font.name = FONT_MONO
        p_ut.font.size = Pt(11)
        p_ut.font.bold = True
        p_ut.font.color.rgb = ucol

        p_us = tf.add_paragraph()
        p_us.text = us
        p_us.font.name = FONT_SERIF
        p_us.font.size = Pt(13)
        p_us.font.bold = True
        p_us.font.color.rgb = COLOR_SPRUCE
        p_us.space_before = Pt(3)

        for up in upoints:
            p_up = tf.add_paragraph()
            p_up.text = f"• {up}"
            p_up.font.name = FONT_SANS
            p_up.font.size = Pt(10)
            p_up.font.color.rgb = COLOR_CHARCOAL
            p_up.space_before = Pt(6)

    add_card(s9, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_ui = s9.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_ui = tb_ui.text_frame
    tf_ui.word_wrap = True
    p_ui = tf_ui.paragraphs[0]
    p_ui.text = "DESIGN SYSTEM: Built with React 18, TypeScript, Tailwind CSS, Playfair Display (Serif), and JetBrains Mono (non-jittering tabular financial figures)."
    p_ui.font.name = FONT_MONO
    p_ui.font.size = Pt(10)
    p_ui.font.bold = True
    p_ui.font.color.rgb = COLOR_SPRUCE

    s9.notes_slide.notes_text_frame.text = (
        "Here is our user interface. Built with an institutional FT Luxury Editorial aesthetic: "
        "clean botanical palette, crisp razor-sharp cards, and tabular monospace fonts that never jitter. "
        "A judge or wealth manager can immediately see: What is happening, what hedge is active, "
        "how the payoff curve looks, and the exact chronological audit trail of agent reasoning."
    )

    # =========================================================================
    # SLIDE 10: 8-Scene Live Demo
    # =========================================================================
    s10 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s10)
    add_slide_header(s10, "Demo Scenario", "The 8-Scene Golden Narrative Replay",
                     "Our deterministic test replay engine proves the complete autonomous cycle from market shock to de-hedging.")

    scenes = [
        ("1. Baseline State", "Healthy tech portfolio ($100k), VIX low at 14.2, hedge ratio 0%, No-Hedge active."),
        ("2. Volatility Shock", "Tech sell-off starts; portfolio drawdown reaches 3.8%, VIX jumps to 26.5."),
        ("3. Ingestion Phase", "5 Ingestion agents gather telemetry; standardized HedgeContext assembled."),
        ("4. Strategy Arena", "4 agents formulate hypotheses: Put, Put Spread, Collar, and No-Hedge."),
        ("5. Strategy Selection", "Put Spread wins: optimal balance of downside protection, budget, and upside."),
        ("6. Risk Gate Pass", "Risk checks Greeks, cash budget ($1,250 cap), liquidity, and verifies buying power."),
        ("7. Alpaca Execution", "Multi-leg order sent via Alpaca API; both legs fill atomically with logged slippage."),
        ("8. Market Recovery", "Market rallies; drift detected; agent autonomously executes DECREASE to lock gains!"),
    ]

    cw10 = 5.6
    for i, (stitle, sdesc) in enumerate(scenes):
        col_idx = i // 4
        row_idx = i % 4
        x = 0.8 + col_idx * (cw10 + 0.533)
        y = 1.95 + row_idx * 1.05

        card_col = COLOR_SAFE if i == 7 else (COLOR_DANGER if i == 1 else COLOR_WHITE)
        add_card(s10, x, y, cw10, 0.95, bg_color=card_col, accent_color=COLOR_SPRUCE)

        tb_sc = s10.shapes.add_textbox(Inches(x + 0.15), Inches(y + 0.1), Inches(cw10 - 0.3), Inches(0.8))
        tf_sc = tb_sc.text_frame
        tf_sc.word_wrap = True
        tf_sc.margin_top = tf_sc.margin_left = tf_sc.margin_right = tf_sc.margin_bottom = 0

        p_sct = tf_sc.paragraphs[0]
        p_sct.text = stitle
        p_sct.font.name = FONT_MONO
        p_sct.font.size = Pt(11)
        p_sct.font.bold = True
        p_sct.font.color.rgb = COLOR_SPRUCE

        p_scd = tf_sc.add_paragraph()
        p_scd.text = sdesc
        p_scd.font.name = FONT_SANS
        p_scd.font.size = Pt(10)
        p_scd.font.color.rgb = COLOR_CHARCOAL
        p_scd.space_before = Pt(2)

    add_card(s10, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_CARD_SUBTLE, accent_top=False)
    tb_dh = s10.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_dh = tb_dh.text_frame
    tf_dh.word_wrap = True
    p_dh = tf_dh.paragraphs[0]
    p_dh.text = "REPRODUCIBILITY: Run `make demo-restore` or `python -m backend.demo_replay` to deterministically replay the full 8-scene sequence in your local environment."
    p_dh.font.name = FONT_MONO
    p_dh.font.size = Pt(10)
    p_dh.font.bold = True
    p_dh.font.color.rgb = COLOR_SPRUCE

    s10.notes_slide.notes_text_frame.text = (
        "During live hackathon demos, reproducibility is everything. We built a dedicated demo replay script "
        "(demo_replay.py) that seeds the exact 8-scene golden narrative. Scene 1 through Scene 8 demonstrates "
        "the full journey: from baseline calm, to market shock, to put spread fill, and crucially to Scene 8: "
        "where the agent autonomously dials the hedge back down as the market recovers."
    )

    # =========================================================================
    # SLIDE 11: Production Tech Stack
    # =========================================================================
    s11 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s11)
    add_slide_header(s11, "Engineering Architecture", "Production Technology Stack & Quantitative Models",
                     "A robust, type-safe system built with high-concurrency Python, LangGraph, and PostgreSQL.")

    tech_layers = [
        ("Core Backend", "Python 3.11+, FastAPI, Pydantic v2, Uvicorn, Alembic database migrations"),
        ("Multi-Agent Orchestrator", "LangGraph stateful workflow DAG, StateGraph checkpointer, resilient retries"),
        ("Dual LLM Provider Layer", "Featherless AI (Competition submission) & OpenRouter (Development) via OpenAI API"),
        ("Quantitative Engine", "Black-Scholes analytical pricer, numerical Greek solvers, Cornish-Fisher VaR, Payoffs"),
        ("Brokerage & Market Data", "Alpaca Trading API, Alpaca Options Chains, Multi-leg Orders, Alpaca MCP Tools"),
        ("Database & Persistence", "PostgreSQL (Neon serverless pooled & unpooled DSN) storing runs, orders, & states"),
        ("Frontend Application", "React 18, TypeScript, Tailwind CSS, Vite, Recharts, Lucide Icons"),
        ("DevOps & Testing Suite", "Docker containerization, Makefile targets, pytest (unit/integration/smoke), CI GitHub Actions"),
    ]

    table_shape = s11.shapes.add_table(9, 2, Inches(0.8), Inches(1.95), Inches(11.733), Inches(4.3))
    table = table_shape.table
    table.columns[0].width = Inches(3.2)
    table.columns[1].width = Inches(8.533)

    cell_00 = table.cell(0, 0)
    cell_00.text = "SYSTEM COMPONENT"
    cell_00.fill.solid()
    cell_00.fill.fore_color.rgb = COLOR_SPRUCE
    p = cell_00.text_frame.paragraphs[0]
    p.font.name = FONT_MONO
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_WHITE

    cell_01 = table.cell(0, 1)
    cell_01.text = "TECHNOLOGY STACK & IMPLEMENTATION DETAILS"
    cell_01.fill.solid()
    cell_01.fill.fore_color.rgb = COLOR_SPRUCE
    p = cell_01.text_frame.paragraphs[0]
    p.font.name = FONT_MONO
    p.font.size = Pt(11)
    p.font.bold = True
    p.font.color.rgb = COLOR_WHITE

    for idx, (layer, tech) in enumerate(tech_layers):
        r = idx + 1
        bg_col = COLOR_CARD_SUBTLE if r % 2 == 1 else COLOR_WHITE

        c0 = table.cell(r, 0)
        c0.text = layer
        c0.fill.solid()
        c0.fill.fore_color.rgb = bg_col
        p0 = c0.text_frame.paragraphs[0]
        p0.font.name = FONT_MONO
        p0.font.size = Pt(10)
        p0.font.bold = True
        p0.font.color.rgb = COLOR_SPRUCE

        c1 = table.cell(r, 1)
        c1.text = tech
        c1.fill.solid()
        c1.fill.fore_color.rgb = bg_col
        p1 = c1.text_frame.paragraphs[0]
        p1.font.name = FONT_SANS
        p1.font.size = Pt(10)
        p1.font.color.rgb = COLOR_CHARCOAL

    add_card(s11, 0.8, 6.4, 11.733, 0.65, bg_color=COLOR_SPRUCE_DARK, accent_top=False)
    tb_cq = s11.shapes.add_textbox(Inches(1.0), Inches(6.45), Inches(11.3), Inches(0.55))
    tf_cq = tb_cq.text_frame
    tf_cq.word_wrap = True
    p_cq = tf_cq.paragraphs[0]
    p_cq.text = "ENGINEERING RIGOR: 100% type-checked with mypy/ruff, 8-phase verified test suites, full OpenAPI 3.1 contract compliance."
    p_cq.font.name = FONT_MONO
    p_cq.font.size = Pt(10)
    p_cq.font.bold = True
    p_cq.font.color.rgb = COLOR_GOLD_LIGHT

    s11.notes_slide.notes_text_frame.text = (
        "Slide 11 demonstrates production engineering standards. "
        "Notice the dual LLM provider layer: we can toggle seamlessly between OpenRouter during testing "
        "and Featherless AI for evaluation and submission. The database is PostgreSQL with Alembic migrations, "
        "and the entire system is tested with phased automated test suites."
    )

    # =========================================================================
    # SLIDE 12: Hackathon Alignment & Roadmap
    # =========================================================================
    s12 = prs.slides.add_slide(blank_layout)
    set_canvas_bg(s12)
    add_slide_header(s12, "Conclusion & Impact", "Judging Criteria Alignment & Commercial Roadmap",
                     "How AEGIS hits every evaluation criterion and scales into a commercial private wealth product.")

    pillars12 = [
        ("1. ALPACA INTEGRATION", "Deep Platform Utilization", COLOR_SPRUCE,
         ["Live Paper Trading Brokerage Account",
          "Real-time Options Chain Discovery",
          "Native Multi-Leg Execution (Spreads/Collars)",
          "Full Alpaca MCP Tool Calling Protocol"]),
        ("2. P&L & RISK PERFORMANCE", "Quantitative Downside Cushioning", COLOR_GOLD,
         ["Verified Drawdown Reduction during shocks",
          "Eliminates Theta Drag via Spread funding",
          "Maintains upside participation during recoveries",
          "Net P&L tracking vs unhedged benchmarks"]),
        ("3. CREATIVITY & NOVELTY", "Breakthrough Agentic Architecture", COLOR_TEAL,
         ["First closed-loop adaptive de-hedging agent",
          "4-Strategy autonomous competition arena",
          "Strict separation of LLM reasoning vs math",
          "Auditable multi-step decision trails"]),
        ("4. EXECUTION & RELIABILITY", "Institutional Engineering", COLOR_SAFE,
         ["Full 8-phase test verification suite",
          "Deterministic demo replay script",
          "FT Luxury Editorial UI design system",
          "Self-contained Docker & Make workflows"]),
    ]

    pw12 = 2.68
    for i, (ptit, psub, pcol, ppts) in enumerate(pillars12):
        x = 0.8 + i * (pw12 + 0.33)
        add_card(s12, x, 1.95, pw12, 3.2, accent_color=pcol)

        tb = s12.shapes.add_textbox(Inches(x + 0.15), Inches(2.1), Inches(pw12 - 0.3), Inches(2.9))
        tf = tb.text_frame
        tf.word_wrap = True
        tf.margin_top = tf.margin_left = tf.margin_right = tf.margin_bottom = 0

        p_t = tf.paragraphs[0]
        p_t.text = ptit
        p_t.font.name = FONT_MONO
        p_t.font.size = Pt(11)
        p_t.font.bold = True
        p_t.font.color.rgb = pcol

        p_s = tf.add_paragraph()
        p_s.text = psub
        p_s.font.name = FONT_SERIF
        p_s.font.size = Pt(13)
        p_s.font.bold = True
        p_s.font.color.rgb = COLOR_SPRUCE
        p_s.space_before = Pt(3)

        for pt in ppts:
            p_p = tf.add_paragraph()
            p_p.text = f"✓ {pt}"
            p_p.font.name = FONT_SANS
            p_p.font.size = Pt(10)
            p_p.font.color.rgb = COLOR_CHARCOAL
            p_p.space_before = Pt(4)

    add_card(s12, 0.8, 5.35, 11.733, 1.7, accent_color=COLOR_GOLD)
    tb_rm = s12.shapes.add_textbox(Inches(1.0), Inches(5.45), Inches(11.3), Inches(1.5))
    tf_rm = tb_rm.text_frame
    tf_rm.word_wrap = True
    tf_rm.margin_top = tf_rm.margin_left = tf_rm.margin_right = tf_rm.margin_bottom = 0

    p_rmt = tf_rm.paragraphs[0]
    p_rmt.text = "COMMERCIAL ROADMAP: SCALING FROM HACKATHON TO INSTITUTIONAL SAAS"
    p_rmt.font.name = FONT_MONO
    p_rmt.font.size = Pt(11)
    p_rmt.font.bold = True
    p_rmt.font.color.rgb = COLOR_GOLD

    roadmap_items = [
        ("Phase 1: Multi-User Wealth Portals", "OAuth2 login, encrypted Alpaca user key vaults, role-based portfolio access for RIAs."),
        ("Phase 2: Advanced Derivative Overlays", "Tier-B options strategies: VIX Call Calendar spreads, Ratio backspreads, synthetic long collars."),
        ("Phase 3: Tax-Loss Harvesting Engine", "Combining adaptive options hedging with intelligent tax-lot harvesting across taxable equity portfolios."),
    ]
    for r_title, r_detail in roadmap_items:
        p_ri = tf_rm.add_paragraph()
        p_ri.text = f"▶ {r_title}: {r_detail}"
        p_ri.font.name = FONT_SANS
        p_ri.font.size = Pt(10)
        p_ri.font.color.rgb = COLOR_CHARCOAL
        p_ri.space_before = Pt(4)

    s12.notes_slide.notes_text_frame.text = (
        "To conclude: AEGIS directly fulfills all 4 hackathon scoring criteria: Alpaca Technology, "
        "P&L performance, agentic originality, and engineering execution. "
        "Beyond the hackathon, AEGIS lays the technical groundwork for a real-world institutional SaaS "
        "protecting high-net-worth portfolios. Thank you, and we welcome your questions!"
    )

    prs.save(output_path)
    return output_path

if __name__ == "__main__":
    out = create_deck("AEGIS_Pitch_Deck.pptx")
    print(f"Presentation saved successfully to {os.path.abspath(out)}")
