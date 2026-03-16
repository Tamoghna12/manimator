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
        "description": "Dark end card with references, CTA, and branding.",
        "fields": {
            "type": '"closing"',
            "id": "unique snake_case id (usually 'refs' or 'end')",
            "title": '(optional) default "Key References"',
            "references": "list of citation strings (Author et al. (Year) Journal)",
            "cta_text": '(optional) call-to-action text, e.g. "Subscribe for weekly science!"',
        },
        "example": {
            "type": "closing",
            "id": "refs",
            "title": "Key References",
            "references": [
                "Jinek et al. (2012) Science 337, 816-821",
                "Doudna & Charpentier (2014) Science 346, 1258096"
            ],
            "cta_text": "Follow for more science!"
        },
    },
}


# ═══════════════════════════════════════════════════════════════════════════════
# DOMAIN TEMPLATES — pre-filled storyboards for common topics
# ═══════════════════════════════════════════════════════════════════════════════

DOMAIN_TEMPLATES = {
    # ── Biology ─────────────────────────────────────────────────────────────
    "biology_mechanism": {
        "description": "Full mechanism explainer with data",
        "theme": "npg",
        "structure": "explainer",
        "custom_scenes": [
            {"type": "title"},
            {"type": "bullet_list"},
            {"type": "flowchart"},
            {"type": "comparison_table"},
            {"type": "bar_chart"},
            {"type": "scatter_plot"},
            {"type": "equation"},
            {"type": "pipeline_diagram"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "title": {"subtitle": "Molecular Mechanism & Applications"},
            "bullet_list": {"header": "Key Components", "items": ["Component A — describe its role", "Component B — how it interacts", "Component C — regulatory function", "Component D — structural feature"]},
            "flowchart": {"header": "Mechanism Steps", "stages": [{"label": "Recognition", "color_key": "blue"}, {"label": "Binding", "color_key": "cyan"}, {"label": "Activation", "color_key": "green"}, {"label": "Catalysis", "color_key": "orange"}, {"label": "Product Release", "color_key": "red"}]},
            "comparison_table": {"header": "Method Comparison", "columns": ["Feature", "Method A", "Method B", "Method C"], "rows": [["Specificity", "High", "Moderate", "Low"], ["Cost", "$$$", "$$", "$"], ["Speed", "Slow", "Medium", "Fast"]]},
            "bar_chart": {"header": "Efficiency Comparison", "bars": [{"label": "Method A", "value": 85, "color_key": "blue"}, {"label": "Method B", "value": 62, "color_key": "green"}, {"label": "Method C", "value": 45, "color_key": "orange"}], "value_suffix": "%"},
            "scatter_plot": {"header": "Dose-Response Data", "clusters": [{"label": "Low dose", "center": [1.0, 2.0], "n": 20, "spread": 0.4, "color_key": "blue"}, {"label": "High dose", "center": [3.0, 5.0], "n": 20, "spread": 0.5, "color_key": "red"}], "axes": ["Concentration (μM)", "Response (%)"]},
            "equation": {"header": "Kinetics", "latex": "v = \\frac{V_{max}[S]}{K_m + [S]}", "explanation": "Michaelis-Menten equation relating reaction rate to substrate concentration."},
            "pipeline_diagram": {"header": "From Discovery to Therapy", "left_track": {"label": "Basic Research", "sublabel": "Target identification"}, "right_track": {"label": "Clinical Data", "sublabel": "Patient cohorts"}, "center_block": {"label": "Development Pipeline", "items": ["Target validation", "Lead optimization", "Preclinical testing", "Clinical trials"]}},
            "closing": {"references": ["Author et al. (Year) Journal, Volume, Pages", "Author et al. (Year) Journal, Volume, Pages"]},
        },
        "example_topics": [
            "How CRISPR-Cas9 edits genomes",
            "The MAP kinase signaling cascade",
            "How mRNA vaccines produce immunity",
        ],
    },
    "biology_reel": {
        "description": "Quick bio reel: hook → table → chart → flow",
        "theme": "npg",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "bullet_list"},
            {"type": "comparison_table"},
            {"type": "bar_chart"},
            {"type": "flowchart"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "This molecular machine can rewrite your DNA", "subtitle": "Here's how it works"},
            "bullet_list": {"header": "3 Key Facts", "items": ["Fact 1 — the core mechanism", "Fact 2 — why it matters clinically", "Fact 3 — how fast it's advancing"]},
            "comparison_table": {"header": "Technology Comparison", "columns": ["Feature", "Old Method", "New Method"], "rows": [["Precision", "Low", "High"], ["Cost", "$10,000+", "<$100"], ["Time", "Months", "Days"]]},
            "bar_chart": {"header": "Key Statistics", "bars": [{"label": "Efficiency", "value": 95, "color_key": "blue"}, {"label": "Specificity", "value": 88, "color_key": "green"}, {"label": "Off-target", "value": 5, "color_key": "red"}], "value_suffix": "%"},
            "flowchart": {"header": "How It Works", "stages": [{"label": "Design Guide", "color_key": "blue"}, {"label": "Deliver to Cell", "color_key": "green"}, {"label": "Edit & Repair", "color_key": "orange"}]},
            "closing": {"references": ["Author et al. (Year) Journal"]},
        },
        "example_topics": [
            "CRISPR in 60 seconds",
            "How your immune system fights cancer",
            "Why antibiotic resistance is accelerating",
        ],
    },

    # ── Computer Science ────────────────────────────────────────────────────
    "cs_algorithm": {
        "description": "Algorithm deep-dive with benchmarks",
        "theme": "tol_bright",
        "structure": "explainer",
        "custom_scenes": [
            {"type": "title"},
            {"type": "bullet_list"},
            {"type": "flowchart"},
            {"type": "two_panel"},
            {"type": "equation"},
            {"type": "bar_chart"},
            {"type": "pipeline_diagram"},
            {"type": "scatter_plot"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "title": {"subtitle": "Algorithm Design & Analysis"},
            "bullet_list": {"header": "Key Properties", "items": ["Time complexity: O(?)", "Space complexity: O(?)", "Best suited for: describe problem class", "Invented by: Author (Year)"]},
            "flowchart": {"header": "Algorithm Steps", "stages": [{"label": "Input Processing", "color_key": "blue"}, {"label": "Core Computation", "color_key": "green"}, {"label": "Optimization", "color_key": "orange"}, {"label": "Output", "color_key": "red"}]},
            "two_panel": {"header": "Algorithm Comparison", "left_title": "This Algorithm", "left_items": ["Advantage 1", "Advantage 2", "Best for: scenario"], "right_title": "Alternative", "right_items": ["Trade-off 1", "Trade-off 2", "Best for: other scenario"]},
            "equation": {"header": "Core Formula", "latex": "T(n) = 2T\\!\\left(\\frac{n}{2}\\right) + O(n)", "explanation": "Recurrence relation for divide-and-conquer algorithms."},
            "bar_chart": {"header": "Benchmark Results", "bars": [{"label": "Small input (n=100)", "value": 2, "color_key": "blue"}, {"label": "Medium (n=10K)", "value": 45, "color_key": "green"}, {"label": "Large (n=1M)", "value": 320, "color_key": "orange"}], "value_suffix": " ms"},
            "pipeline_diagram": {"header": "System Integration", "left_track": {"label": "Input Data", "sublabel": "Raw records"}, "right_track": {"label": "Configuration", "sublabel": "Parameters"}, "center_block": {"label": "Processing Pipeline", "items": ["Preprocessing", "Algorithm execution", "Post-processing", "Output formatting"]}},
            "scatter_plot": {"header": "Scaling Behavior", "clusters": [{"label": "O(n log n)", "center": [2.0, 1.5], "n": 20, "spread": 0.3, "color_key": "blue"}, {"label": "O(n²)", "center": [2.0, 4.0], "n": 20, "spread": 0.5, "color_key": "red"}], "axes": ["Input Size (log)", "Runtime (log)"]},
            "closing": {"references": ["Author (Year) Original paper", "Textbook reference"]},
        },
        "example_topics": [
            "How transformers process sequences",
            "Dijkstra's shortest path algorithm",
            "How gradient descent optimizes neural networks",
        ],
    },
    "cs_reel": {
        "description": "Quick CS reel: equation → pipeline → panels",
        "theme": "tol_bright",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "bullet_list"},
            {"type": "equation"},
            {"type": "two_panel"},
            {"type": "pipeline_diagram"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "This algorithm powers every search you do", "subtitle": "Here's the key insight"},
            "bullet_list": {"header": "Core Concepts", "items": ["Concept 1 — what it computes", "Concept 2 — why it's fast", "Concept 3 — where it's used"]},
            "equation": {"header": "The Key Formula", "latex": "\\text{softmax}(z_i) = \\frac{e^{z_i}}{\\sum_j e^{z_j}}", "explanation": "Converts raw scores into a probability distribution."},
            "two_panel": {"header": "Approach A vs Approach B", "left_title": "Approach A", "left_items": ["Property 1", "Property 2", "Use case"], "right_title": "Approach B", "right_items": ["Property 1", "Property 2", "Use case"]},
            "pipeline_diagram": {"header": "Architecture Overview", "left_track": {"label": "Input", "sublabel": "Raw data"}, "right_track": {"label": "Parameters", "sublabel": "Learned weights"}, "center_block": {"label": "Processing", "items": ["Layer 1", "Layer 2", "Layer 3", "Output"]}},
            "closing": {"references": ["Author et al. (Year) Conference/Journal"]},
        },
        "example_topics": [
            "How ChatGPT actually works",
            "Why hash tables are O(1)",
            "How RSA encryption keeps you safe",
        ],
    },

    # ── Mathematics ─────────────────────────────────────────────────────────
    "math_concept": {
        "description": "Theorem deep-dive with proof & visualization",
        "theme": "wong",
        "structure": "tutorial",
        "custom_scenes": [
            {"type": "title"},
            {"type": "bullet_list"},
            {"type": "equation"},
            {"type": "flowchart"},
            {"type": "scatter_plot"},
            {"type": "bullet_list"},
            {"type": "bar_chart"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "title": {"subtitle": "Theorem, Proof & Applications"},
            "bullet_list": [
                {"header": "Prerequisites", "items": ["Concept A — brief definition", "Concept B — how it relates", "Concept C — what you need to know"]},
                {"header": "Applications", "items": ["Application 1 — field and use", "Application 2 — real-world impact", "Application 3 — modern extensions"]},
            ],
            "equation": {"header": "The Main Result", "latex": "\\int_{-\\infty}^{\\infty} e^{-x^2} dx = \\sqrt{\\pi}", "explanation": "The Gaussian integral — fundamental to probability and statistics."},
            "flowchart": {"header": "Proof Outline", "stages": [{"label": "Assume", "color_key": "blue"}, {"label": "Transform", "color_key": "green"}, {"label": "Evaluate", "color_key": "orange"}, {"label": "Conclude", "color_key": "red"}]},
            "scatter_plot": {"header": "Visualization", "clusters": [{"label": "Distribution A", "center": [0.0, 2.0], "n": 30, "spread": 0.5, "color_key": "blue"}, {"label": "Distribution B", "center": [2.0, 1.0], "n": 30, "spread": 0.7, "color_key": "orange"}], "axes": ["x", "f(x)"]},
            "bar_chart": {"header": "Numerical Example", "bars": [{"label": "n = 10", "value": 25, "color_key": "blue"}, {"label": "n = 100", "value": 50, "color_key": "green"}, {"label": "n = 1000", "value": 50, "color_key": "orange"}], "value_suffix": ""},
            "closing": {"references": ["Textbook: Author (Year) Title, Publisher"]},
        },
        "example_topics": [
            "The Central Limit Theorem",
            "Eigenvalues and eigenvectors",
            "Bayes' theorem and posterior inference",
        ],
    },
    "math_reel": {
        "description": "Quick math reel: equation → scatter → bars",
        "theme": "wong",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "equation"},
            {"type": "bullet_list"},
            {"type": "scatter_plot"},
            {"type": "bar_chart"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "A 99% accurate test says you're sick — are you?", "subtitle": "The answer will surprise you"},
            "equation": {"header": "The Formula", "latex": "P(A|B) = \\frac{P(B|A)\\,P(A)}{P(B)}", "explanation": "Bayes' theorem — updating beliefs with evidence."},
            "bullet_list": {"header": "What Each Term Means", "items": ["P(A|B) — posterior: updated belief", "P(B|A) — likelihood: evidence strength", "P(A) — prior: initial belief"]},
            "scatter_plot": {"header": "Prior vs Posterior", "clusters": [{"label": "Prior belief", "center": [-1.5, 1.0], "n": 25, "spread": 0.8, "color_key": "blue"}, {"label": "After evidence", "center": [1.5, 1.5], "n": 25, "spread": 0.4, "color_key": "red"}], "axes": ["Belief Strength", "Probability"]},
            "bar_chart": {"header": "The Medical Test Paradox", "bars": [{"label": "Test accuracy", "value": 99, "color_key": "green"}, {"label": "Disease rate", "value": 1, "color_key": "orange"}, {"label": "Actual P(sick)", "value": 50, "color_key": "red"}], "value_suffix": "%"},
            "closing": {"references": ["Bayes (1763) Phil. Trans. Royal Society"]},
        },
        "example_topics": [
            "Why 0.999... equals 1",
            "The birthday paradox explained",
            "How Euler's identity connects 5 constants",
        ],
    },

    # ── Physics ──────────────────────────────────────────────────────────────
    "physics_reel": {
        "description": "Quick physics reel: equation → two-panel → chart",
        "theme": "tol_bright",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "equation"},
            {"type": "two_panel"},
            {"type": "bar_chart"},
            {"type": "bullet_list"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "Nothing can travel faster than light — or can it?", "subtitle": "Einstein's most famous equation explains why"},
            "equation": {"header": "The Equation", "latex": "E = mc^2", "explanation": "Mass-energy equivalence — a small mass stores enormous energy."},
            "two_panel": {"header": "Classical vs Relativistic", "left_title": "Classical Mechanics", "left_items": ["F = ma", "Absolute time", "Galilean transforms"], "right_title": "Special Relativity", "right_items": ["E = mc²", "Time dilation", "Lorentz transforms"]},
            "bar_chart": {"header": "Energy Scales", "bars": [{"label": "Chemical bond", "value": 5, "color_key": "blue"}, {"label": "Nuclear fission", "value": 200, "color_key": "orange"}, {"label": "Nuclear fusion", "value": 600, "color_key": "red"}], "value_suffix": " MeV"},
            "bullet_list": {"header": "Real-World Impact", "items": ["GPS satellites correct for time dilation", "Nuclear power plants use E=mc²", "Particle accelerators confirm predictions"]},
            "closing": {"references": ["Einstein (1905) Annalen der Physik"]},
        },
        "example_topics": [
            "Why time slows near black holes",
            "How quantum tunneling works",
            "The double-slit experiment explained",
        ],
    },

    # ── Chemistry ────────────────────────────────────────────────────────────
    "chemistry_reel": {
        "description": "Quick chemistry reel: flow → table → equation",
        "theme": "npg",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "flowchart"},
            {"type": "comparison_table"},
            {"type": "equation"},
            {"type": "bar_chart"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "This reaction powers every battery in your phone", "subtitle": "The chemistry is beautiful"},
            "flowchart": {"header": "Reaction Mechanism", "stages": [{"label": "Reactants", "color_key": "blue"}, {"label": "Transition State", "color_key": "orange"}, {"label": "Intermediate", "color_key": "green"}, {"label": "Products", "color_key": "red"}]},
            "comparison_table": {"header": "Bond Properties", "columns": ["Bond Type", "Energy (kJ/mol)", "Length (pm)", "Example"], "rows": [["Single", "347", "154", "C-C"], ["Double", "614", "134", "C=C"], ["Triple", "839", "120", "C≡C"]]},
            "equation": {"header": "Rate Law", "latex": "r = k[A]^m[B]^n", "explanation": "Reaction rate depends on concentrations raised to their reaction orders."},
            "bar_chart": {"header": "Activation Energies", "bars": [{"label": "Uncatalyzed", "value": 180, "color_key": "red"}, {"label": "With catalyst", "value": 60, "color_key": "green"}, {"label": "Enzyme", "value": 25, "color_key": "blue"}], "value_suffix": " kJ/mol"},
            "closing": {"references": ["Author et al. (Year) Journal of Chemistry"]},
        },
        "example_topics": [
            "How catalysts speed up reactions",
            "Why water is a polar molecule",
            "The chemistry behind lithium-ion batteries",
        ],
    },

    # ── Economics ─────────────────────────────────────────────────────────────
    "economics_reel": {
        "description": "Quick econ reel: scatter → bars → two-panel",
        "theme": "wong",
        "custom_scenes": [
            {"type": "hook"},
            {"type": "scatter_plot"},
            {"type": "bar_chart"},
            {"type": "two_panel"},
            {"type": "bullet_list"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "hook": {"hook_text": "Why do prices rise when everyone has more money?", "subtitle": "The economics is counterintuitive"},
            "scatter_plot": {"header": "Supply & Demand", "clusters": [{"label": "Supply", "center": [2.0, 3.0], "n": 20, "spread": 0.5, "color_key": "blue"}, {"label": "Demand", "center": [3.0, 1.5], "n": 20, "spread": 0.5, "color_key": "red"}], "axes": ["Quantity", "Price"]},
            "bar_chart": {"header": "Key Indicators", "bars": [{"label": "GDP Growth", "value": 3.2, "color_key": "green"}, {"label": "Inflation", "value": 2.1, "color_key": "orange"}, {"label": "Unemployment", "value": 4.5, "color_key": "red"}], "value_suffix": "%"},
            "two_panel": {"header": "Keynesian vs Monetarist", "left_title": "Keynesian", "left_items": ["Government spending drives growth", "Fiscal policy is primary tool", "Short-run focus"], "right_title": "Monetarist", "right_items": ["Money supply drives growth", "Monetary policy is primary tool", "Long-run equilibrium focus"]},
            "bullet_list": {"header": "Key Takeaways", "items": ["Supply and demand set equilibrium price", "Government intervention has trade-offs", "Economic models simplify complex reality"]},
            "closing": {"references": ["Mankiw (2020) Principles of Economics"]},
        },
        "example_topics": [
            "Why inflation happens",
            "How interest rates affect the economy",
            "The economics of climate change",
        ],
    },

    # ── Cross-domain ────────────────────────────────────────────────────────
    "paper_review": {
        "description": "Paper summary: title → methods → results → critique",
        "theme": "wong",
        "structure": "paper_summary",
        "custom_scenes": [
            {"type": "title"},
            {"type": "bullet_list"},
            {"type": "flowchart"},
            {"type": "bar_chart"},
            {"type": "comparison_table"},
            {"type": "closing"},
        ],
        "scaffold_content": {
            "title": {"subtitle": "Paper Summary & Critique"},
            "bullet_list": {"header": "Research Question & Motivation", "items": ["Gap in existing literature", "Hypothesis or objective", "Key contribution claimed"]},
            "flowchart": {"header": "Methodology", "stages": [{"label": "Data Collection", "color_key": "blue"}, {"label": "Processing", "color_key": "green"}, {"label": "Analysis", "color_key": "orange"}, {"label": "Validation", "color_key": "red"}]},
            "bar_chart": {"header": "Main Results", "bars": [{"label": "This method", "value": 92, "color_key": "green"}, {"label": "Baseline A", "value": 78, "color_key": "blue"}, {"label": "Baseline B", "value": 71, "color_key": "orange"}], "value_suffix": "%"},
            "comparison_table": {"header": "Results Summary", "columns": ["Metric", "This Paper", "State of Art", "Improvement"], "rows": [["Accuracy", "92%", "88%", "+4%"], ["Speed", "2.1s", "5.3s", "2.5x faster"]]},
            "closing": {"references": ["Full paper citation here"]},
        },
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
                    "type": "comparison_table", "id": "tech_compare",
                    "header": "Genome Editing Technologies",
                    "columns": ["Feature", "ZFN", "TALEN", "CRISPR"],
                    "rows": [
                        ["Design complexity", "High (protein engineering)", "Moderate (repeat assembly)", "Low (20-nt RNA guide)"],
                        ["Cost per target", "$5,000+", "$1,000+", "<$100"],
                        ["Multiplexing", "Not feasible", "Difficult", "Easy (multiple gRNAs)"],
                        ["Off-target rate", "High", "Low", "Moderate (improvable)"],
                        ["Time to design", "Weeks to months", "1-2 weeks", "1-2 days"]
                    ],
                    "callout": "CRISPR's ease of use made genome editing accessible to any lab."
                },
                {
                    "type": "bar_chart", "id": "stats",
                    "header": "Editing Efficiency",
                    "bars": [
                        {"label": "Gene Knockout (NHEJ)", "value": 95, "color_key": "blue"},
                        {"label": "Gene Insert (HDR)", "value": 40, "color_key": "green"},
                        {"label": "Base Editing", "value": 78, "color_key": "orange"},
                        {"label": "Prime Editing", "value": 55, "color_key": "purple"}
                    ],
                    "value_suffix": "%",
                    "callout": "Casgevy, the first CRISPR therapy, was approved by FDA in Dec 2023."
                },
                {
                    "type": "closing", "id": "end",
                    "title": "Key References",
                    "references": [
                        "Jinek et al. (2012) Science 337, 816-821",
                        "Doudna & Charpentier (2014) Science 346, 1258096"
                    ],
                    "cta_text": "Follow for more biotech explainers!"
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
                    "type": "equation", "id": "attention_formula",
                    "header": "Scaled Dot-Product Attention",
                    "latex": "\\text{Attention}(Q,K,V) = \\text{softmax}\\!\\left(\\frac{QK^{T}}{\\sqrt{d_k}}\\right)V",
                    "explanation": "Queries and keys are compared via dot product, scaled by sqrt(d_k) to prevent gradient vanishing, then softmax produces attention weights over values.",
                    "callout": "Multi-head attention runs h parallel attention functions (h=8 in the original paper)."
                },
                {
                    "type": "two_panel", "id": "enc_vs_dec",
                    "header": "Encoder vs Decoder",
                    "left_title": "Encoder",
                    "left_items": [
                        "Bidirectional: attends to all positions",
                        "Used in BERT, sentence embeddings",
                        "Self-attention + feed-forward layers",
                        "Good for classification and retrieval"
                    ],
                    "right_title": "Decoder",
                    "right_items": [
                        "Causal: attends only to past tokens",
                        "Used in GPT, LLaMA, code generation",
                        "Masked self-attention + cross-attention",
                        "Good for text generation and reasoning"
                    ],
                    "callout": "The original Transformer uses both; modern LLMs are decoder-only."
                },
                {
                    "type": "pipeline_diagram", "id": "architecture",
                    "header": "Transformer Forward Pass",
                    "left_track": {"label": "Input Tokens", "sublabel": "Tokenized text + positional encoding"},
                    "right_track": {"label": "Learned Embeddings", "sublabel": "d_model = 512 dimensions"},
                    "center_block": {
                        "label": "N x Transformer Blocks",
                        "items": ["Multi-Head Attention", "Add & LayerNorm", "Feed-Forward Network", "Add & LayerNorm"]
                    },
                    "callout": "The original paper stacks N=6 identical blocks for both encoder and decoder."
                },
                {
                    "type": "closing", "id": "refs",
                    "references": [
                        "Vaswani et al. (2017) Attention Is All You Need, NeurIPS",
                        "Devlin et al. (2019) BERT: Pre-training of Deep Bidirectional Transformers, NAACL"
                    ],
                    "cta_text": "Follow for more AI architecture breakdowns!"
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
                    "type": "equation", "id": "bayes_formula",
                    "header": "Bayes' Theorem",
                    "latex": "P(A \\mid B) = \\frac{P(B \\mid A)\\, P(A)}{P(B)}",
                    "explanation": "The probability of hypothesis A given evidence B equals the likelihood of B under A, times the prior probability of A, divided by the total probability of B.",
                    "callout": "Published posthumously by Thomas Bayes in 1763."
                },
                {
                    "type": "bullet_list", "id": "terms",
                    "header": "Breaking Down the Formula",
                    "items": [
                        "P(A|B) — Posterior: your updated belief after seeing evidence",
                        "P(B|A) — Likelihood: how probable the evidence is if A is true",
                        "P(A) — Prior: your initial belief before any evidence",
                        "P(B) — Evidence: total probability of observing B across all cases"
                    ],
                    "callout": "The key insight: rare events stay unlikely even with strong evidence."
                },
                {
                    "type": "scatter_plot", "id": "distributions",
                    "header": "Prior vs Posterior Belief",
                    "clusters": [
                        {"label": "Prior (before test)", "center": [-1.5, 1.0], "n": 30, "spread": 0.8, "color_key": "blue"},
                        {"label": "Posterior (after positive test)", "center": [1.5, 1.0], "n": 30, "spread": 0.4, "color_key": "red"},
                        {"label": "Posterior (after negative test)", "center": [-2.0, -1.0], "n": 30, "spread": 0.3, "color_key": "green"}
                    ],
                    "axes": ["Belief Strength", "Probability Density"],
                    "callout": "The posterior is narrower — evidence reduces uncertainty."
                },
                {
                    "type": "bar_chart", "id": "medical_test",
                    "header": "Medical Test: The Math",
                    "bars": [
                        {"label": "Sensitivity (true positive)", "value": 99, "color_key": "green"},
                        {"label": "Disease prevalence", "value": 1, "color_key": "orange"},
                        {"label": "P(sick | positive test)", "value": 50, "color_key": "red"},
                        {"label": "False positive rate", "value": 1, "color_key": "purple"}
                    ],
                    "value_suffix": "%",
                    "callout": "With 1% prevalence and 1% false positive rate, half of positive results are wrong."
                },
                {
                    "type": "closing", "id": "refs",
                    "references": [
                        "Bayes (1763) An Essay towards Solving a Problem in the Doctrine of Chances, Phil. Trans.",
                        "McGrayne (2011) The Theory That Would Not Die, Yale University Press"
                    ],
                    "cta_text": "Follow for more math in 60 seconds!"
                }
            ]
        },
    }
    return examples.get(domain, examples["biology_reel"])
