"""
Storyboard authoring system — structures, schema docs, and LLM prompts.

Provides:
1. Named story structures (explainer, short, data, tutorial, social_reel, debate)
2. Full JSON schema documentation for every scene type
3. LLM prompt generator with complete schema + examples
4. Domain-specific storyboard templates (biology, CS, math)
"""

import json

# ═══════════════════════════════════════════════════════════════════════════════
# STORY STRUCTURES — scene sequences for different video types
# ═══════════════════════════════════════════════════════════════════════════════

STRUCTURES = {
    "explainer": {
        "description": "Standard academic explainer (8-9 scenes, 2-3 min)",
        "scenes": [
            {"type": "title", "purpose": "Title with paper reference"},
            {"type": "bullet_list", "purpose": "Background and motivation"},
            {"type": "flowchart", "purpose": "Process or mechanism"},
            {"type": "two_panel", "purpose": "Comparison of approaches"},
            {"type": "bar_chart", "purpose": "Quantitative results"},
            {"type": "scatter_plot", "purpose": "Data clustering or trends"},
            {"type": "equation", "purpose": "Core mathematical relationship"},
            {"type": "pipeline_diagram", "purpose": "System architecture"},
            {"type": "closing", "purpose": "References"},
        ],
    },
    "short": {
        "description": "Quick explainer (4-5 scenes, 30-60s)",
        "scenes": [
            {"type": "hook", "purpose": "Attention-grabbing opener"},
            {"type": "bullet_list", "purpose": "What it is (3-4 points)"},
            {"type": "flowchart", "purpose": "How it works (3 steps)"},
            {"type": "bar_chart", "purpose": "Key numbers"},
            {"type": "closing", "purpose": "References + CTA"},
        ],
    },
    "data_heavy": {
        "description": "Results-focused presentation (7 scenes)",
        "scenes": [
            {"type": "title", "purpose": "Study title and authors"},
            {"type": "bullet_list", "purpose": "Methods overview"},
            {"type": "bar_chart", "purpose": "Primary results"},
            {"type": "scatter_plot", "purpose": "Secondary analysis"},
            {"type": "comparison_table", "purpose": "Benchmarking"},
            {"type": "equation", "purpose": "Model formulation"},
            {"type": "closing", "purpose": "References"},
        ],
    },
    "tutorial": {
        "description": "Step-by-step tutorial (7-8 scenes)",
        "scenes": [
            {"type": "title", "purpose": "Tutorial title"},
            {"type": "bullet_list", "purpose": "Prerequisites"},
            {"type": "flowchart", "purpose": "Overview of all steps"},
            {"type": "bullet_list", "purpose": "Step 1 details"},
            {"type": "bullet_list", "purpose": "Step 2 details"},
            {"type": "equation", "purpose": "Key formula or concept"},
            {"type": "bullet_list", "purpose": "Step 3 details"},
            {"type": "closing", "purpose": "Summary and resources"},
        ],
    },
    "social_reel": {
        "description": "Instagram/TikTok reel (4-5 scenes, 30-45s)",
        "scenes": [
            {"type": "hook", "purpose": "Bold claim or question"},
            {"type": "bullet_list", "purpose": "3 key facts"},
            {"type": "flowchart", "purpose": "Simple 3-step process"},
            {"type": "bar_chart", "purpose": "Impressive statistics"},
            {"type": "closing", "purpose": "References + follow CTA"},
        ],
    },
    "debate": {
        "description": "Two-sided analysis (7 scenes)",
        "scenes": [
            {"type": "title", "purpose": "Topic framing"},
            {"type": "bullet_list", "purpose": "Context and stakes"},
            {"type": "two_panel", "purpose": "Arguments for vs against"},
            {"type": "comparison_table", "purpose": "Feature-by-feature comparison"},
            {"type": "bar_chart", "purpose": "Evidence or survey data"},
            {"type": "bullet_list", "purpose": "Expert consensus / nuance"},
            {"type": "closing", "purpose": "Key references"},
        ],
    },
    "paper_summary": {
        "description": "Summarize a single research paper (6 scenes)",
        "scenes": [
            {"type": "title", "purpose": "Paper title, authors, journal"},
            {"type": "bullet_list", "purpose": "Problem and motivation"},
            {"type": "flowchart", "purpose": "Method or experimental design"},
            {"type": "bar_chart", "purpose": "Main results"},
            {"type": "bullet_list", "purpose": "Key findings and implications"},
            {"type": "closing", "purpose": "Full citation"},
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# SCENE TYPE SCHEMA — complete field documentation for LLM prompts
# ═══════════════════════════════════════════════════════════════════════════════

SCENE_SCHEMAS = {
    "hook": {
        "description": "Dark background, large bold text. For social videos.",
        "fields": {
            "type": '"hook"',
            "id": "unique snake_case id",
            "hook_text": "Bold attention-grabbing statement (8-15 words)",
            "subtitle": "(optional) Supporting line",
        },
        "example": {
            "type": "hook",
            "id": "hook",
            "hook_text": "Scientists can now edit ANY gene in your DNA",
            "subtitle": "Here's how CRISPR works"
        },
    },
    "title": {
        "description": "Title slide with optional subtitle and footnote.",
        "fields": {
            "type": '"title"',
            "id": "unique snake_case id",
            "title": "Main title text",
            "subtitle": "(optional) Subtitle or tagline",
            "footnote": "(optional) Citation or date",
        },
        "example": {
            "type": "title",
            "id": "title",
            "title": "CRISPR-Cas9: Programmable Genome Editing",
            "subtitle": "From Bacterial Immunity to Therapeutic Tool",
            "footnote": "Jinek et al. (2012) Science 337, 816-821"
        },
    },
    "bullet_list": {
        "description": "Header + bulleted items + optional callout. Most versatile scene.",
        "fields": {
            "type": '"bullet_list"',
            "id": "unique snake_case id",
            "header": "Section header text",
            "items": "list of 3-6 bullet point strings",
            "callout": "(optional) Key takeaway in bold box",
        },
        "example": {
            "type": "bullet_list",
            "id": "components",
            "header": "Core Components",
            "items": [
                "Guide RNA (gRNA): 20-nt spacer complementary to target DNA",
                "Cas9 nuclease: HNH and RuvC catalytic domains",
                "PAM sequence (5'-NGG-3'): required for recognition",
                "RNP complex: gRNA-Cas9 assembly"
            ],
            "callout": "The complex scans 3 billion base pairs to find one 20-nt target."
        },
    },
    "flowchart": {
        "description": "Vertical flow of 3-6 numbered stages with arrows between them.",
        "fields": {
            "type": '"flowchart"',
            "id": "unique snake_case id",
            "header": "Section header",
            "stages": 'list of {"label": "Stage Name", "color_key": "blue|green|orange|red"}',
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "flowchart",
            "id": "mechanism",
            "header": "Editing Mechanism",
            "stages": [
                {"label": "gRNA Design", "color_key": "blue"},
                {"label": "RNP Assembly", "color_key": "cyan"},
                {"label": "PAM Recognition", "color_key": "green"},
                {"label": "DSB Creation", "color_key": "orange"},
                {"label": "DNA Repair", "color_key": "red"}
            ],
            "callout": "DSB triggers NHEJ (error-prone) or HDR (precise) repair."
        },
    },
    "two_panel": {
        "description": "Two stacked panels comparing two sides of a topic.",
        "fields": {
            "type": '"two_panel"',
            "id": "unique snake_case id",
            "header": "Comparison header",
            "left_title": "Panel A title",
            "left_items": "list of 3-5 strings",
            "right_title": "Panel B title",
            "right_items": "list of 3-5 strings",
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "two_panel",
            "id": "comparison",
            "header": "Supervised vs Unsupervised Learning",
            "left_title": "Supervised",
            "left_items": ["Requires labeled data", "Classification / Regression", "Higher accuracy on known tasks"],
            "right_title": "Unsupervised",
            "right_items": ["No labels needed", "Clustering / Dimensionality reduction", "Discovers hidden patterns"],
            "callout": "Semi-supervised methods combine both approaches."
        },
    },
    "comparison_table": {
        "description": "Table with header row and data rows. Good for feature comparison.",
        "fields": {
            "type": '"comparison_table"',
            "id": "unique snake_case id",
            "header": "Table title",
            "columns": "list of column header strings",
            "rows": "list of lists — each inner list = one data row",
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "comparison_table",
            "id": "methods",
            "header": "Genome Editing Technologies",
            "columns": ["Feature", "ZFN", "TALEN", "CRISPR"],
            "rows": [
                ["Design complexity", "High", "Moderate", "Low"],
                ["Cost per target", "$5,000+", "$1,000+", "<$100"],
                ["Multiplexing", "No", "Difficult", "Easy"]
            ]
        },
    },
    "bar_chart": {
        "description": "Horizontal bar chart with animated fills. Good for stats.",
        "fields": {
            "type": '"bar_chart"',
            "id": "unique snake_case id",
            "header": "Chart title",
            "bars": 'list of {"label": "Name", "value": number, "color_key": "blue|green|..."}',
            "value_suffix": '(optional) unit suffix, e.g. "%", " ms", " GB"',
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "bar_chart",
            "id": "efficiency",
            "header": "Editing Efficiency by Method",
            "bars": [
                {"label": "NHEJ", "value": 92, "color_key": "blue"},
                {"label": "HDR", "value": 38, "color_key": "green"},
                {"label": "Base Editing", "value": 78, "color_key": "orange"},
                {"label": "Prime Editing", "value": 55, "color_key": "red"}
            ],
            "value_suffix": "%",
            "callout": "HDR requires donor template co-delivery."
        },
    },
    "scatter_plot": {
        "description": "2D scatter plot with colored clusters. For PCA, correlation, etc.",
        "fields": {
            "type": '"scatter_plot"',
            "id": "unique snake_case id",
            "header": "Plot title",
            "clusters": 'list of {"label": "Group", "center": [x, y], "n": 20, "spread": 0.4, "color_key": "blue"}',
            "axes": '["X axis label", "Y axis label"]',
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "scatter_plot",
            "id": "pca",
            "header": "PCA of Gene Expression",
            "clusters": [
                {"label": "Control", "center": [2.0, 1.5], "n": 25, "spread": 0.5, "color_key": "blue"},
                {"label": "Treated", "center": [-1.5, -1.0], "n": 25, "spread": 0.6, "color_key": "red"}
            ],
            "axes": ["PC1 (45% var)", "PC2 (22% var)"]
        },
    },
    "equation": {
        "description": "Display a mathematical equation with explanation.",
        "fields": {
            "type": '"equation"',
            "id": "unique snake_case id",
            "header": "Section header",
            "latex": "LaTeX string for the equation",
            "explanation": "(optional) Plain-English explanation",
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "equation",
            "id": "loss",
            "header": "Cross-Entropy Loss",
            "latex": "L = -\\sum_{i} y_i \\log(\\hat{y}_i)",
            "explanation": "Measures divergence between predicted probabilities and true labels.",
            "callout": "Minimizing cross-entropy is equivalent to maximizing likelihood."
        },
    },
    "pipeline_diagram": {
        "description": "Two input tracks feeding into a central processing block.",
        "fields": {
            "type": '"pipeline_diagram"',
            "id": "unique snake_case id",
            "header": "Diagram title",
            "left_track": '{"label": "Input A", "sublabel": "optional detail"}',
            "right_track": '{"label": "Input B", "sublabel": "optional detail"}',
            "center_block": '{"label": "Process", "items": ["Step 1", "Step 2", ...]}',
            "callout": "(optional) Key takeaway",
        },
        "example": {
            "type": "pipeline_diagram",
            "id": "pipeline",
            "header": "ML Training Pipeline",
            "left_track": {"label": "Training Data", "sublabel": "Labeled examples"},
            "right_track": {"label": "Validation Data", "sublabel": "Held-out split"},
            "center_block": {
                "label": "Model Training",
                "items": ["Feature extraction", "Forward pass", "Loss computation", "Backpropagation"]
            },
            "callout": "Early stopping on validation loss prevents overfitting."
        },
    },
    "closing": {
        "description": "Dark end card with references and follow CTA.",
        "fields": {
            "type": '"closing"',
            "id": "unique snake_case id (usually 'refs' or 'end')",
            "title": '(optional) default "Key References"',
            "references": "list of citation strings (Author et al. (Year) Journal)",
        },
        "example": {
            "type": "closing",
            "id": "refs",
            "title": "Key References",
            "references": [
                "Jinek et al. (2012) Science 337, 816-821",
                "Doudna & Charpentier (2014) Science 346, 1258096"
            ]
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN TEMPLATES — pre-filled storyboards for common topics
# ═══════════════════════════════════════════════════════════════════════════════

DOMAIN_TEMPLATES = {
    # ── Biology ─────────────────────────────────────────────────────────────
    "biology_mechanism": {
        "description": "Explain a biological mechanism (enzyme, pathway, etc.)",
        "theme": "npg",
        "structure": "explainer",
        "scene_guidance": [
            "Title: Mechanism name + key paper",
            "Bullet list: Components involved, their roles",
            "Flowchart: Step-by-step mechanism (3-6 stages)",
            "Two panel: Compare to related mechanism OR normal vs disease",
            "Bar chart: Kinetic parameters, efficiency, or prevalence data",
            "Scatter plot: Experimental data (e.g., dose-response, expression)",
            "Equation: Rate law, Michaelis-Menten, binding affinity, etc.",
            "Pipeline: From discovery to therapeutic application",
            "Closing: 3-5 key papers",
        ],
        "example_topics": [
            "How CRISPR-Cas9 edits genomes",
            "The MAP kinase signaling cascade",
            "How mRNA vaccines produce immunity",
            "Mechanism of action of checkpoint inhibitors",
        ],
    },
    "biology_reel": {
        "description": "Quick biology explainer for social media",
        "theme": "npg",
        "structure": "social_reel",
        "scene_guidance": [
            "Hook: Surprising fact or bold claim about the topic",
            "Bullet list: 3 key points (what it is, why it matters)",
            "Flowchart: 3-step simplified mechanism",
            "Bar chart: 3-4 striking statistics with source",
            "Closing: 1-2 key references + CTA",
        ],
        "example_topics": [
            "CRISPR in 60 seconds",
            "How your immune system fights cancer",
            "Why antibiotic resistance is accelerating",
        ],
    },

    # ── Computer Science ────────────────────────────────────────────────────
    "cs_algorithm": {
        "description": "Explain an algorithm or data structure",
        "theme": "tol_bright",
        "structure": "explainer",
        "scene_guidance": [
            "Title: Algorithm name + original paper/textbook",
            "Bullet list: Problem it solves, key properties (time/space complexity)",
            "Flowchart: Algorithm steps",
            "Two panel: Compare to alternative algorithms",
            "Bar chart: Benchmark performance (runtime, accuracy, etc.)",
            "Scatter plot: Performance vs input size or accuracy vs recall",
            "Equation: Recurrence relation or key formula",
            "Pipeline: Where it fits in a larger system",
            "Closing: References (original paper, textbook, survey)",
        ],
        "example_topics": [
            "How transformers process sequences",
            "Dijkstra's shortest path algorithm",
            "How gradient descent optimizes neural networks",
            "B-trees and database indexing",
        ],
    },
    "cs_reel": {
        "description": "Quick CS explainer for social media",
        "theme": "tol_bright",
        "structure": "social_reel",
        "scene_guidance": [
            "Hook: What problem does this solve? Why should you care?",
            "Bullet list: 3 key concepts or properties",
            "Flowchart: 3-step simplified algorithm",
            "Bar chart: Performance comparison or adoption stats",
            "Closing: Original paper + modern reference",
        ],
        "example_topics": [
            "How ChatGPT actually works",
            "Why hash tables are O(1)",
            "How RSA encryption keeps you safe",
        ],
    },

    # ── Mathematics ─────────────────────────────────────────────────────────
    "math_concept": {
        "description": "Explain a mathematical concept or theorem",
        "theme": "wong",
        "structure": "tutorial",
        "scene_guidance": [
            "Title: Theorem/concept name + field",
            "Bullet list: Prerequisites and definitions",
            "Flowchart: Proof outline or derivation steps",
            "Bullet list: Key properties or implications",
            "Bullet list: Applications",
            "Equation: The main result",
            "Bullet list: Extensions or generalizations",
            "Closing: Textbook references",
        ],
        "example_topics": [
            "The Central Limit Theorem",
            "Eigenvalues and eigenvectors",
            "Bayes' theorem and posterior inference",
            "Fourier transform and signal decomposition",
        ],
    },
    "math_reel": {
        "description": "Quick math explainer for social media",
        "theme": "wong",
        "structure": "social_reel",
        "scene_guidance": [
            "Hook: Counterintuitive result or real-world application",
            "Bullet list: 3 key ideas in plain language",
            "Flowchart: 3-step intuition builder",
            "Bar chart: Numerical example or comparison",
            "Closing: Textbook reference",
        ],
        "example_topics": [
            "Why 0.999... equals 1",
            "The birthday paradox explained",
            "How Euler's identity connects 5 constants",
        ],
    },

    # ── Cross-domain ────────────────────────────────────────────────────────
    "paper_review": {
        "description": "Summarize and critique a specific research paper",
        "theme": "wong",
        "structure": "paper_summary",
        "scene_guidance": [
            "Title: Full paper title, all authors, journal + year",
            "Bullet list: Research question, gap in literature, hypothesis",
            "Flowchart: Experimental/computational methodology",
            "Bar chart: Main quantitative results (use actual numbers from paper)",
            "Bullet list: Key findings, limitations, future directions",
            "Closing: Full citation + related works",
        ],
        "example_topics": [
            "Attention Is All You Need (Vaswani et al. 2017)",
            "AlphaFold2 protein structure prediction (Jumper et al. 2021)",
            "CRISPR-Cas9 genome editing (Jinek et al. 2012)",
        ],
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# LLM PROMPT GENERATOR
# ═══════════════════════════════════════════════════════════════════════════════

def _format_schema_docs() -> str:
    """Generate complete schema documentation for all scene types."""
    lines = []
    for stype, info in SCENE_SCHEMAS.items():
        lines.append(f"### {stype}")
        lines.append(f"{info['description']}")
        lines.append("Fields:")
        for field, desc in info["fields"].items():
            lines.append(f"  - {field}: {desc}")
        lines.append(f"Example: {json.dumps(info['example'], indent=2)}")
        lines.append("")
    return "\n".join(lines)


def get_storyboard_prompt(topic: str,
                          structure: str = "explainer",
                          domain: str = None,
                          format_type: str = "presentation",
                          theme: str = "wong") -> str:
    """Generate a comprehensive LLM prompt for storyboard creation.

    Args:
        topic: The subject to create a video about
        structure: Story structure key (explainer, short, social_reel, etc.)
        domain: Optional domain template key (biology_mechanism, cs_algorithm, etc.)
        format_type: Output format (presentation, instagram_reel, linkedin, etc.)
        theme: Color theme (wong, npg, tol_bright)

    Returns:
        A detailed prompt string to send to an LLM
    """
    # Resolve structure
    if domain and domain in DOMAIN_TEMPLATES:
        dt = DOMAIN_TEMPLATES[domain]
        struct_key = dt["structure"]
        theme = dt.get("theme", theme)
        guidance = dt.get("scene_guidance", [])
    else:
        struct_key = structure
        guidance = []

    struct = STRUCTURES.get(struct_key, STRUCTURES["explainer"])
    scene_list = struct["scenes"]

    # Build scene-by-scene instructions
    scene_instructions = []
    for i, s in enumerate(scene_list):
        purpose = s.get("purpose", "")
        guide = guidance[i] if i < len(guidance) else ""
        schema = SCENE_SCHEMAS.get(s["type"], {})
        fields = schema.get("fields", {})

        inst = f"Scene {i+1} — type: \"{s['type']}\""
        if purpose:
            inst += f" — {purpose}"
        if guide:
            inst += f"\n    Guidance: {guide}"
        inst += f"\n    Required fields: {', '.join(fields.keys())}"
        scene_instructions.append(inst)

    # Determine portrait vs landscape
    is_portrait = format_type in ("instagram_reel", "tiktok", "youtube_short")
    format_note = ""
    if is_portrait:
        format_note = """
FORMAT NOTE: This is for a PORTRAIT (9:16) social media video.
- Keep text SHORT and punchy (max 8-10 words per bullet)
- Use 3 items max per bullet_list
- Use 3 stages max per flowchart
- Use 3-4 bars max per bar_chart
- Hook scene should be provocative and shareable
- Total video should be under 60 seconds of content"""
    else:
        format_note = """
FORMAT NOTE: This is for a LANDSCAPE presentation/LinkedIn video.
- Bullet items can be more detailed (up to 15-20 words each)
- Use 4-6 items per bullet_list
- Use 4-6 stages per flowchart
- Use 4-6 bars per bar_chart
- Include callouts with key takeaways on most scenes"""

    prompt = f"""Generate a manimator storyboard JSON for the topic:
"{topic}"

{format_note}

STRUCTURE ({struct["description"]}):
{chr(10).join(scene_instructions)}

META BLOCK:
{{
  "meta": {{
    "title": "<concise title>",
    "color_theme": "{theme}",
    "format": "{format_type}"
  }}
}}

SCENE TYPE SCHEMAS:
{_format_schema_docs()}

RULES:
1. Output ONLY valid JSON — no markdown fences, no commentary
2. Every scene needs a unique "id" field (snake_case, short)
3. All facts must be scientifically accurate with real data
4. References must be real papers with correct authors and years
5. color_key options: blue, orange, green, red, purple, cyan
6. Include a "callout" on most scenes (key takeaway)
7. Keep language clear and accessible — no jargon without explanation
8. Bar chart values must be realistic numbers, not made up
9. The "id" field should be descriptive: "mechanism", "results", "comparison" — not "scene1"
10. Start the scenes array with the first scene type listed above
"""
    return prompt


def list_structures() -> str:
    """Return a formatted list of available story structures."""
    lines = ["Available story structures:"]
    for key, val in STRUCTURES.items():
        lines.append(f"  {key:15s} — {val['description']}")
    return "\n".join(lines)


def list_domains() -> str:
    """Return a formatted list of available domain templates."""
    lines = ["Available domain templates:"]
    for key, val in DOMAIN_TEMPLATES.items():
        topics = ", ".join(val.get("example_topics", [])[:2])
        lines.append(f"  {key:20s} — {val['description']}")
        if topics:
            lines.append(f"  {'':20s}   e.g., {topics}")
    return "\n".join(lines)


def get_example_storyboard(domain: str = "biology_reel") -> dict:
    """Return a complete example storyboard for reference."""
    examples = {
        "biology_reel": {
            "meta": {
                "title": "CRISPR in 60 Seconds",
                "color_theme": "npg",
                "format": "instagram_reel"
            },
            "scenes": [
                {
                    "type": "hook", "id": "hook",
                    "hook_text": "Scientists can now edit ANY gene in your DNA",
                    "subtitle": "Here's how CRISPR works"
                },
                {
                    "type": "bullet_list", "id": "what",
                    "header": "What is CRISPR?",
                    "items": [
                        "Molecular scissors that cut DNA at precise locations",
                        "Guided by a 20-letter RNA address tag",
                        "Can delete, replace, or insert genes"
                    ],
                    "callout": "Nobel Prize in Chemistry 2020"
                },
                {
                    "type": "flowchart", "id": "how",
                    "header": "How It Works",
                    "stages": [
                        {"label": "Design gRNA", "color_key": "blue"},
                        {"label": "Cas9 Cuts", "color_key": "red"},
                        {"label": "Cell Repairs", "color_key": "green"}
                    ],
                    "callout": "The cell's own repair machinery fixes the cut."
                },
                {
                    "type": "bar_chart", "id": "stats",
                    "header": "Editing Efficiency",
                    "bars": [
                        {"label": "Gene Knockout", "value": 95, "color_key": "blue"},
                        {"label": "Gene Insert", "value": 40, "color_key": "green"},
                        {"label": "Base Edit", "value": 75, "color_key": "orange"}
                    ],
                    "value_suffix": "%",
                    "callout": "First CRISPR therapy approved by FDA in 2023."
                },
                {
                    "type": "closing", "id": "end",
                    "title": "Key References",
                    "references": [
                        "Jinek et al. (2012) Science",
                        "Doudna & Charpentier (2014) Science"
                    ]
                }
            ]
        },
        "cs_reel": {
            "meta": {
                "title": "How Transformers Work",
                "color_theme": "tol_bright",
                "format": "instagram_reel"
            },
            "scenes": [
                {
                    "type": "hook", "id": "hook",
                    "hook_text": "One architecture powers ChatGPT, DALL-E, and AlphaFold",
                    "subtitle": "It's called the Transformer"
                },
                {
                    "type": "bullet_list", "id": "what",
                    "header": "What is a Transformer?",
                    "items": [
                        "A neural network that processes all tokens in parallel",
                        "Uses attention to learn which words relate to which",
                        "Replaced RNNs for nearly all sequence tasks"
                    ],
                    "callout": "65,000+ papers cite the original Transformer paper"
                },
                {
                    "type": "flowchart", "id": "how",
                    "header": "Core Mechanism",
                    "stages": [
                        {"label": "Token Embedding", "color_key": "blue"},
                        {"label": "Self-Attention", "color_key": "orange"},
                        {"label": "Feed-Forward", "color_key": "green"}
                    ],
                    "callout": "Multi-head attention lets the model focus on different relationships simultaneously."
                },
                {
                    "type": "bar_chart", "id": "scale",
                    "header": "Model Scale (Parameters)",
                    "bars": [
                        {"label": "BERT", "value": 340, "color_key": "blue"},
                        {"label": "GPT-3", "value": 175000, "color_key": "orange"},
                        {"label": "GPT-4", "value": 1800000, "color_key": "red"}
                    ],
                    "value_suffix": "M",
                    "callout": "Scaling laws show predictable improvement with more parameters."
                },
                {
                    "type": "closing", "id": "refs",
                    "references": [
                        "Vaswani et al. (2017) NeurIPS",
                        "Brown et al. (2020) NeurIPS"
                    ]
                }
            ]
        },
        "math_reel": {
            "meta": {
                "title": "Bayes' Theorem in 60 Seconds",
                "color_theme": "wong",
                "format": "instagram_reel"
            },
            "scenes": [
                {
                    "type": "hook", "id": "hook",
                    "hook_text": "A 99% accurate test says you're sick. Are you actually sick?",
                    "subtitle": "Probably not — here's why"
                },
                {
                    "type": "bullet_list", "id": "what",
                    "header": "What is Bayes' Theorem?",
                    "items": [
                        "Updates your belief when you get new evidence",
                        "Combines prior probability with test accuracy",
                        "Foundation of spam filters, medical diagnosis, and AI"
                    ],
                    "callout": "Published by Thomas Bayes in 1763 — still revolutionary"
                },
                {
                    "type": "flowchart", "id": "how",
                    "header": "How It Works",
                    "stages": [
                        {"label": "Prior Belief", "color_key": "blue"},
                        {"label": "New Evidence", "color_key": "orange"},
                        {"label": "Updated Belief", "color_key": "green"}
                    ],
                    "callout": "The posterior becomes your new prior as more data arrives."
                },
                {
                    "type": "bar_chart", "id": "example",
                    "header": "Medical Test Example",
                    "bars": [
                        {"label": "Test Accuracy", "value": 99, "color_key": "green"},
                        {"label": "Disease Prevalence", "value": 1, "color_key": "orange"},
                        {"label": "Chance You're Actually Sick", "value": 50, "color_key": "red"}
                    ],
                    "value_suffix": "%",
                    "callout": "Even a 99% accurate test is wrong half the time if the disease is rare."
                },
                {
                    "type": "closing", "id": "refs",
                    "references": [
                        "Bayes (1763) Phil. Trans. Royal Society",
                        "McGrayne (2011) The Theory That Would Not Die"
                    ]
                }
            ]
        },
    }
    return examples.get(domain, examples["biology_reel"])
