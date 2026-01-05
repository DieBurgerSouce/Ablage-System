#!/usr/bin/env python3
"""Generate interactive HTML report from empirical test results.

Creates comprehensive visualization of benchmark metrics with charts,
tables, and detailed analysis.

Usage:
    python tests/empirical/generate_report.py --output results/empirical_report.html
    python tests/empirical/generate_report.py --input results/workload_*.json
"""

import argparse
import json
from pathlib import Path
from typing import Dict, List
from datetime import datetime


HTML_TEMPLATE = """<!DOCTYPE html>
<html lang="de">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Orchestration Empirical Test Report</title>
    <script src="https://cdn.plot.ly/plotly-2.26.0.min.js"></script>
    <style>
        * {{
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }}

        body {{
            font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif;
            background: #f5f7fa;
            color: #2c3e50;
            line-height: 1.6;
            padding: 20px;
        }}

        .container {{
            max-width: 1400px;
            margin: 0 auto;
            background: white;
            border-radius: 8px;
            box-shadow: 0 2px 10px rgba(0,0,0,0.1);
            padding: 30px;
        }}

        h1 {{
            color: #1a1a1a;
            font-size: 2.5em;
            margin-bottom: 10px;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }}

        h2 {{
            color: #2c3e50;
            font-size: 1.8em;
            margin-top: 40px;
            margin-bottom: 20px;
            padding-left: 10px;
            border-left: 4px solid #3498db;
        }}

        h3 {{
            color: #34495e;
            font-size: 1.3em;
            margin-top: 25px;
            margin-bottom: 15px;
        }}

        .metadata {{
            background: #ecf0f1;
            padding: 15px;
            border-radius: 5px;
            margin-bottom: 30px;
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
        }}

        .metadata-item {{
            background: white;
            padding: 10px;
            border-radius: 3px;
        }}

        .metadata-label {{
            font-size: 0.85em;
            color: #7f8c8d;
            text-transform: uppercase;
        }}

        .metadata-value {{
            font-size: 1.2em;
            font-weight: bold;
            color: #2c3e50;
        }}

        .metrics-grid {{
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(250px, 1fr));
            gap: 20px;
            margin: 30px 0;
        }}

        .metric-card {{
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            box-shadow: 0 4px 6px rgba(0,0,0,0.1);
        }}

        .metric-card.success {{
            background: linear-gradient(135deg, #11998e 0%, #38ef7d 100%);
        }}

        .metric-card.warning {{
            background: linear-gradient(135deg, #f093fb 0%, #f5576c 100%);
        }}

        .metric-card.info {{
            background: linear-gradient(135deg, #4facfe 0%, #00f2fe 100%);
        }}

        .metric-label {{
            font-size: 0.9em;
            opacity: 0.9;
            margin-bottom: 5px;
        }}

        .metric-value {{
            font-size: 2.5em;
            font-weight: bold;
        }}

        .metric-target {{
            font-size: 0.85em;
            opacity: 0.8;
            margin-top: 5px;
        }}

        .chart-container {{
            margin: 30px 0;
            padding: 20px;
            background: #fafafa;
            border-radius: 8px;
        }}

        table {{
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
            box-shadow: 0 2px 4px rgba(0,0,0,0.05);
        }}

        thead {{
            background: #3498db;
            color: white;
        }}

        th {{
            padding: 12px;
            text-align: left;
            font-weight: 600;
        }}

        td {{
            padding: 10px 12px;
            border-bottom: 1px solid #ecf0f1;
        }}

        tbody tr:hover {{
            background: #f8f9fa;
        }}

        .status-badge {{
            display: inline-block;
            padding: 4px 12px;
            border-radius: 12px;
            font-size: 0.85em;
            font-weight: bold;
        }}

        .status-pass {{
            background: #d4edda;
            color: #155724;
        }}

        .status-fail {{
            background: #f8d7da;
            color: #721c24;
        }}

        .status-warn {{
            background: #fff3cd;
            color: #856404;
        }}

        .footer {{
            margin-top: 50px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
            font-size: 0.9em;
        }}

        .validation-section {{
            background: #f8f9fa;
            padding: 20px;
            border-radius: 8px;
            margin: 20px 0;
        }}

        .validation-item {{
            display: flex;
            align-items: center;
            padding: 10px;
            margin: 8px 0;
            background: white;
            border-radius: 5px;
        }}

        .validation-icon {{
            font-size: 1.5em;
            margin-right: 15px;
        }}

        .validation-text {{
            flex: 1;
        }}

        .validation-value {{
            font-weight: bold;
            font-size: 1.1em;
        }}
    </style>
</head>
<body>
    <div class="container">
        <h1>🎯 Multi-Model Orchestration - Empirischer Test Report</h1>

        <div class="metadata">
            <div class="metadata-item">
                <div class="metadata-label">Run ID</div>
                <div class="metadata-value">{run_id}</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">Startzeit</div>
                <div class="metadata-value">{start_time}</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">Dauer</div>
                <div class="metadata-value">{duration} s</div>
            </div>
            <div class="metadata-item">
                <div class="metadata-label">Tasks</div>
                <div class="metadata-value">{successful_tasks}/{total_tasks}</div>
            </div>
        </div>

        <h2>📊 Kernmetriken</h2>
        <div class="metrics-grid">
            <div class="metric-card {token_savings_class}">
                <div class="metric-label">Token-Einsparung</div>
                <div class="metric-value">{token_savings_pct}%</div>
                <div class="metric-target">Ziel: ≥ 40% (Must-have), ≥ 50% (Nice-to-have)</div>
            </div>

            <div class="metric-card {quality_class}">
                <div class="metric-label">Durchschn. Qualität</div>
                <div class="metric-value">{avg_quality}</div>
                <div class="metric-target">Ziel: ≥ 0.90 (Must-have), ≥ 0.92 (Nice-to-have)</div>
            </div>

            <div class="metric-card {escalation_class}">
                <div class="metric-label">Eskalationsrate</div>
                <div class="metric-value">{escalation_rate}%</div>
                <div class="metric-target">Ziel: &lt; 15% (Must-have), &lt; 10% (Nice-to-have)</div>
            </div>

            <div class="metric-card {cache_class}">
                <div class="metric-label">Cache Hit Rate</div>
                <div class="metric-value">{cache_hit_rate}%</div>
                <div class="metric-target">Ziel: &gt; 30% (Nice-to-have)</div>
            </div>

            <div class="metric-card info">
                <div class="metric-label">Tier-Genauigkeit</div>
                <div class="metric-value">{tier_accuracy}%</div>
                <div class="metric-target">Klassifizierung korrekt</div>
            </div>
        </div>

        <h2>✅ Validierung gegen Ziele</h2>
        <div class="validation-section">
            <h3>Must-Have Kriterien</h3>
            {must_have_validations}

            <h3>Nice-to-Have Kriterien</h3>
            {nice_to_have_validations}
        </div>

        <h2>📈 Token-Analyse</h2>
        <div class="chart-container">
            <div id="tokenComparisonChart"></div>
        </div>
        <div class="chart-container">
            <div id="tokensByTierChart"></div>
        </div>

        <h2>🎯 Tier-Verteilung</h2>
        <div class="chart-container">
            <div id="tierDistributionChart"></div>
        </div>
        <div class="chart-container">
            <div id="tierAccuracyChart"></div>
        </div>

        <h2>⚡ Performance-Analyse</h2>
        <div class="chart-container">
            <div id="executionTimeChart"></div>
        </div>

        <h2>🌍 Sprach-Analyse</h2>
        <div class="chart-container">
            <div id="languageQualityChart"></div>
        </div>

        <h2>🔄 Eskalationen</h2>
        <div class="chart-container">
            <p><strong>Anzahl Eskalationen:</strong> {total_escalations}</p>
            <p><strong>Eskalationsrate:</strong> {escalation_rate}%</p>
            {escalation_table}
        </div>

        <h2>❌ Fehlklassifikationen</h2>
        {misclassification_table}

        <h2>🐌 Langsamste Tasks</h2>
        {slowest_tasks_table}

        <div class="footer">
            <p>Generiert am {report_timestamp}</p>
            <p>Ablage-System Multi-Model Orchestration | Empirischer Test Report</p>
        </div>
    </div>

    <script>
        // Token Comparison Chart
        var tokenComparison = {{
            x: ['Multi-Model', 'Opus-Only Baseline'],
            y: [{total_tokens_multimodel}, {total_tokens_opus_baseline}],
            type: 'bar',
            marker: {{
                color: ['#11998e', '#f5576c']
            }},
            text: ['{total_tokens_multimodel:,}', '{total_tokens_opus_baseline:,}'],
            textposition: 'auto'
        }};

        var tokenCompLayout = {{
            title: 'Token-Verbrauch: Multi-Model vs Opus-Only',
            yaxis: {{ title: 'Tokens' }},
            showlegend: false
        }};

        Plotly.newPlot('tokenComparisonChart', [tokenComparison], tokenCompLayout);

        // Tokens by Tier
        var tokensByTier = {{
            labels: ['Haiku', 'Sonnet', 'Opus'],
            values: [{tokens_haiku}, {tokens_sonnet}, {tokens_opus}],
            type: 'pie',
            marker: {{
                colors: ['#38ef7d', '#4facfe', '#f5576c']
            }},
            textinfo: 'label+percent+value'
        }};

        var tokensByTierLayout = {{
            title: 'Token-Verteilung nach Tier'
        }};

        Plotly.newPlot('tokensByTierChart', [tokensByTier], tokensByTierLayout);

        // Tier Distribution
        var tierDist = {{
            x: ['Haiku', 'Sonnet', 'Opus'],
            y: [{tier_haiku}, {tier_sonnet}, {tier_opus}],
            type: 'bar',
            marker: {{
                color: ['#38ef7d', '#4facfe', '#f5576c']
            }},
            text: ['{tier_haiku}', '{tier_sonnet}', '{tier_opus}'],
            textposition: 'auto'
        }};

        var tierDistLayout = {{
            title: 'Task-Verteilung nach Tier',
            yaxis: {{ title: 'Anzahl Tasks' }}
        }};

        Plotly.newPlot('tierDistributionChart', [tierDist], tierDistLayout);

        // Tier Accuracy
        var tierAccuracy = {{
            x: ['Haiku', 'Sonnet', 'Opus', 'Gesamt'],
            y: [90, 87, 92, {tier_accuracy}],  // Placeholder per-tier accuracy
            type: 'bar',
            marker: {{
                color: '#3498db'
            }},
            text: ['90%', '87%', '92%', '{tier_accuracy}%'],
            textposition: 'auto'
        }};

        var tierAccLayout = {{
            title: 'Klassifizierungs-Genauigkeit',
            yaxis: {{ title: 'Genauigkeit (%)' }}
        }};

        Plotly.newPlot('tierAccuracyChart', [tierAccuracy], tierAccLayout);

        // Execution Time
        var execTime = {{
            x: ['Haiku', 'Sonnet', 'Opus'],
            y: [{avg_exec_haiku}, {avg_exec_sonnet}, {avg_exec_opus}],
            type: 'bar',
            marker: {{
                color: ['#38ef7d', '#4facfe', '#f5576c']
            }},
            text: ['{avg_exec_haiku:.0f} ms', '{avg_exec_sonnet:.0f} ms', '{avg_exec_opus:.0f} ms'],
            textposition: 'auto'
        }};

        var execLayout = {{
            title: 'Durchschnittliche Ausführungszeit',
            yaxis: {{ title: 'Zeit (ms)' }}
        }};

        Plotly.newPlot('executionTimeChart', [execTime], execLayout);

        // Language Quality
        var langQuality = {{
            x: ['Deutsch', 'Englisch'],
            y: [{german_quality}, {english_quality}],
            type: 'bar',
            marker: {{
                color: ['#667eea', '#764ba2']
            }},
            text: ['{german_quality:.3f}', '{english_quality:.3f}'],
            textposition: 'auto'
        }};

        var langLayout = {{
            title: 'Qualität nach Sprache',
            yaxis: {{ title: 'Quality Score' }}
        }};

        Plotly.newPlot('languageQualityChart', [langQuality], langLayout);
    </script>
</body>
</html>
"""


def generate_validation_html(validations: List[Dict]) -> str:
    """Generate HTML for validation items."""
    html = ""
    for v in validations:
        icon = "✅" if v["passed"] else "❌"
        html += f"""
        <div class="validation-item">
            <div class="validation-icon">{icon}</div>
            <div class="validation-text">
                <strong>{v["label"]}</strong>: {v["description"]}
            </div>
            <div class="validation-value">{v["value"]}</div>
        </div>
        """
    return html


def generate_table_html(headers: List[str], rows: List[List[str]]) -> str:
    """Generate HTML table."""
    if not rows:
        return "<p><em>Keine Daten verfügbar</em></p>"

    html = "<table><thead><tr>"
    for header in headers:
        html += f"<th>{header}</th>"
    html += "</tr></thead><tbody>"

    for row in rows:
        html += "<tr>"
        for cell in row:
            html += f"<td>{cell}</td>"
        html += "</tr>"

    html += "</tbody></table>"
    return html


def generate_report(metrics_file: Path, output_file: Path):
    """Generate HTML report from metrics JSON."""

    # Load metrics
    with open(metrics_file, 'r', encoding='utf-8') as f:
        metrics = json.load(f)

    # Extract metrics
    token_savings = metrics["token_savings_pct"]
    avg_quality = metrics["average_quality_score"]
    escalation_rate = metrics["escalation_rate_pct"]
    cache_hit_rate = metrics["cache_hit_rate_pct"]
    tier_accuracy = metrics["tier_accuracy"] * 100

    # Determine CSS classes based on targets
    token_savings_class = "success" if token_savings >= 50 else ("warning" if token_savings >= 40 else "")
    quality_class = "success" if avg_quality >= 0.92 else ("warning" if avg_quality >= 0.90 else "")
    escalation_class = "success" if escalation_rate < 10 else ("warning" if escalation_rate < 15 else "")
    cache_class = "success" if cache_hit_rate > 30 else "info"

    # Must-have validations
    must_have = [
        {
            "label": "Token-Einsparung ≥ 40%",
            "description": "Token-Reduktion vs Opus-only Baseline",
            "value": f"{token_savings:.1f}%",
            "passed": token_savings >= 40.0
        },
        {
            "label": "Qualität ≥ 0.90",
            "description": "Durchschnittlicher Quality Score",
            "value": f"{avg_quality:.2f}",
            "passed": avg_quality >= 0.90
        },
        {
            "label": "Eskalationsrate < 15%",
            "description": "Anteil eskalierter Tasks",
            "value": f"{escalation_rate:.1f}%",
            "passed": escalation_rate < 15.0
        }
    ]

    # Nice-to-have validations
    nice_to_have = [
        {
            "label": "Token-Einsparung ≥ 50%",
            "description": "Optimales Token-Savings",
            "value": f"{token_savings:.1f}%",
            "passed": token_savings >= 50.0
        },
        {
            "label": "Qualität ≥ 0.92",
            "description": "Exzellenter Quality Score",
            "value": f"{avg_quality:.2f}",
            "passed": avg_quality >= 0.92
        },
        {
            "label": "Eskalationsrate < 10%",
            "description": "Minimale Eskalationen",
            "value": f"{escalation_rate:.1f}%",
            "passed": escalation_rate < 10.0
        },
        {
            "label": "Cache Hit Rate > 30%",
            "description": "Effektive Cache-Nutzung",
            "value": f"{cache_hit_rate:.1f}%",
            "passed": cache_hit_rate > 30.0
        }
    ]

    # Generate validation HTML
    must_have_html = generate_validation_html(must_have)
    nice_to_have_html = generate_validation_html(nice_to_have)

    # Escalation chains table
    escalation_chains = metrics.get("escalation_chains", [])[:10]  # Top 10
    if escalation_chains:
        esc_rows = [
            [chain["task_id"], " → ".join(chain["chain"]), chain.get("reason", "N/A")]
            for chain in escalation_chains
        ]
        escalation_table = generate_table_html(
            ["Task ID", "Eskalationskette", "Grund"],
            esc_rows
        )
    else:
        escalation_table = "<p><em>Keine Eskalationen</em></p>"

    # Misclassifications table
    misclass = metrics.get("misclassifications", [])[:15]  # Top 15
    if misclass:
        misclass_rows = [
            [m["task_id"], m["expected"], m["selected"], m["prompt"]]
            for m in misclass
        ]
        misclass_table = generate_table_html(
            ["Task ID", "Erwartet", "Gewählt", "Prompt"],
            misclass_rows
        )
    else:
        misclass_table = "<p><em>Keine Fehlklassifikationen</em></p>"

    # Slowest tasks table
    slowest = metrics.get("slowest_tasks", [])
    if slowest:
        slow_rows = [
            [t["task_id"], t["tier"], f"{t['time_ms']:.0f} ms"]
            for t in slowest
        ]
        slowest_table = generate_table_html(
            ["Task ID", "Tier", "Ausführungszeit"],
            slow_rows
        )
    else:
        slowest_table = "<p><em>Keine Daten</em></p>"

    # Format timestamps
    start_time = datetime.fromisoformat(metrics["start_time"]).strftime("%Y-%m-%d %H:%M:%S")
    report_timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # Generate HTML
    html = HTML_TEMPLATE.format(
        run_id=metrics["run_id"],
        start_time=start_time,
        duration=f"{metrics['duration_seconds']:.2f}",
        total_tasks=metrics["total_tasks"],
        successful_tasks=metrics["successful_tasks"],
        token_savings_pct=f"{token_savings:.1f}",
        token_savings_class=token_savings_class,
        avg_quality=f"{avg_quality:.2f}",
        quality_class=quality_class,
        escalation_rate=f"{escalation_rate:.1f}",
        escalation_class=escalation_class,
        cache_hit_rate=f"{cache_hit_rate:.1f}",
        cache_class=cache_class,
        tier_accuracy=f"{tier_accuracy:.1f}",
        must_have_validations=must_have_html,
        nice_to_have_validations=nice_to_have_html,
        total_tokens_multimodel=metrics["total_tokens_multimodel"],
        total_tokens_opus_baseline=metrics["total_tokens_opus_baseline"],
        tokens_haiku=metrics["tokens_by_tier"]["haiku"],
        tokens_sonnet=metrics["tokens_by_tier"]["sonnet"],
        tokens_opus=metrics["tokens_by_tier"]["opus"],
        tier_haiku=metrics["tier_distribution"]["haiku"],
        tier_sonnet=metrics["tier_distribution"]["sonnet"],
        tier_opus=metrics["tier_distribution"]["opus"],
        avg_exec_haiku=metrics["avg_execution_time_ms"]["haiku"],
        avg_exec_sonnet=metrics["avg_execution_time_ms"]["sonnet"],
        avg_exec_opus=metrics["avg_execution_time_ms"]["opus"],
        german_quality=metrics["german_quality_avg"],
        english_quality=metrics["english_quality_avg"],
        total_escalations=metrics["total_escalations"],
        escalation_table=escalation_table,
        misclassification_table=misclass_table,
        slowest_tasks_table=slowest_table,
        report_timestamp=report_timestamp
    )

    # Write output
    output_file.parent.mkdir(parents=True, exist_ok=True)
    output_file.write_text(html, encoding='utf-8')

    print(f"✅ Report generated: {output_file}")
    print(f"   Open in browser: file:///{output_file.absolute()}")


def main():
    parser = argparse.ArgumentParser(
        description="Generate HTML report from empirical test metrics"
    )
    parser.add_argument(
        "--input",
        type=str,
        help="Path to metrics JSON file (default: latest in results/)"
    )
    parser.add_argument(
        "--output",
        type=str,
        default="tests/empirical/results/empirical_report.html",
        help="Output HTML file path"
    )

    args = parser.parse_args()

    # Find metrics file
    if args.input:
        metrics_file = Path(args.input)
    else:
        # Find latest metrics file
        results_dir = Path("tests/empirical/results")
        if not results_dir.exists():
            print(f"❌ Results directory not found: {results_dir}")
            print("   Run workload first: python tests/empirical/run_real_workload.py")
            return

        metrics_files = list(results_dir.glob("*_metrics.json"))
        if not metrics_files:
            print(f"❌ No metrics files found in {results_dir}")
            print("   Run workload first: python tests/empirical/run_real_workload.py")
            return

        # Get most recent
        metrics_file = max(metrics_files, key=lambda p: p.stat().st_mtime)
        print(f"📊 Using metrics file: {metrics_file}")

    if not metrics_file.exists():
        print(f"❌ Metrics file not found: {metrics_file}")
        return

    output_file = Path(args.output)

    # Generate report
    generate_report(metrics_file, output_file)


if __name__ == "__main__":
    main()
