"""Generate a D3.js v6 stock visualization web app with bubble chart and data table."""
import os
import shutil
import subprocess

def ensure_d3_library(output_dir):
    """Ensure d3.v6.min.js exists in the output js directory."""
    js_dir = os.path.join(output_dir, 'js')
    os.makedirs(js_dir, exist_ok=True)
    d3_path = os.path.join(js_dir, 'd3.v6.min.js')
    if not os.path.exists(d3_path):
        npm_path = os.path.expanduser('~/node_modules/d3/dist/d3.min.js')
        if not os.path.exists(npm_path):
            subprocess.run(['npm', 'install', 'd3@6'], cwd=os.path.expanduser('~'), check=True)
        shutil.copy(npm_path, d3_path)
    return d3_path

def copy_data(input_data_dir, output_dir):
    """Copy input data to output/data/ directory."""
    out_data = os.path.join(output_dir, 'data')
    if os.path.exists(out_data):
        shutil.rmtree(out_data)
    shutil.copytree(input_data_dir, out_data)

def write_css(output_dir):
    """Write style.css for the web app."""
    css_dir = os.path.join(output_dir, 'css')
    os.makedirs(css_dir, exist_ok=True)
    css_content = """* { margin: 0; padding: 0; box-sizing: border-box; }
body { font-family: 'Segoe UI', Tahoma, Geneva, Verdana, sans-serif; background: #f5f5f5; padding: 20px; }
h1 { text-align: center; margin-bottom: 20px; color: #333; }
.container { display: flex; flex-direction: row; justify-content: center; align-items: flex-start; gap: 20px; max-width: 1600px; margin: 0 auto; flex-wrap: nowrap; }
.chart-container { flex: 1 1 auto; min-width: 700px; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 15px; }
.table-container { flex: 0 0 450px; background: #fff; border-radius: 8px; box-shadow: 0 2px 8px rgba(0,0,0,0.1); padding: 15px; max-height: 700px; overflow-y: auto; }
.table-container h2, .chart-container h2 { margin-bottom: 10px; color: #333; font-size: 16px; }
.legend { display: flex; flex-wrap: wrap; gap: 10px; margin-top: 10px; padding: 5px 0; }
.legend-item { display: flex; align-items: center; gap: 6px; font-size: 13px; color: #333; }
.legend-swatch { display: inline-block; width: 14px; height: 14px; border-radius: 3px; flex-shrink: 0; }
table { width: 100%; border-collapse: collapse; font-size: 13px; }
table thead th { background: #4a90d9; color: white; padding: 8px 10px; text-align: left; position: sticky; top: 0; z-index: 1; }
table tbody tr { border-bottom: 1px solid #eee; cursor: pointer; transition: background-color 0.2s; }
table tbody tr:hover { background-color: #e8f0fe; }
table tbody tr.highlighted { background-color: #fff3cd !important; }
table tbody tr.selected { background-color: #fff3cd !important; }
table tbody td { padding: 6px 10px; }
.tooltip { position: absolute; pointer-events: none; background: rgba(0,0,0,0.85); color: #fff; padding: 10px 14px; border-radius: 6px; font-size: 13px; line-height: 1.5; opacity: 0; transition: opacity 0.2s; z-index: 1000; max-width: 300px; }
.tooltip.visible { opacity: 1; }
.bubble-label { pointer-events: none; text-anchor: middle; dominant-baseline: central; font-size: 10px; font-weight: bold; fill: #fff; }
.bubble { cursor: pointer; stroke: #fff; stroke-width: 1.5; transition: stroke 0.2s, stroke-width 0.2s; }
.bubble.selected { stroke: #ff6600; stroke-width: 3; }
.bubble.highlighted { stroke: #ff6600; stroke-width: 3; }
svg { display: block; }
"""
    with open(os.path.join(css_dir, 'style.css'), 'w') as f:
        f.write(css_content)

def get_visualization_js(csv_relative_path='data/stock-descriptions.csv'):
    """Return the visualization.js content string."""
    return '''(function() {
  var chartWidth = 750, chartHeight = 650;
  var margin = { top: 30, right: 30, bottom: 30, left: 30 };
  var innerWidth = chartWidth - margin.left - margin.right;
  var innerHeight = chartHeight - margin.top - margin.bottom;
  var tooltip = d3.select('body').append('div').attr('class', 'tooltip');

  function formatMarketCap(val) {
    if (val == null || isNaN(val) || val === '') return 'N/A';
    val = +val;
    if (val >= 1e12) return (val / 1e12).toFixed(2) + 'T';
    if (val >= 1e9) return (val / 1e9).toFixed(2) + 'B';
    if (val >= 1e6) return (val / 1e6).toFixed(2) + 'M';
    if (val >= 1e3) return (val / 1e3).toFixed(2) + 'K';
    return val.toFixed(2);
  }

  d3.csv("''' + csv_relative_path + '''").then(function(rawData) {
    var data = rawData.map(function(d) {
      return {
        ticker: d.ticker, sector: d.sector, name: d['full name'],
        marketCap: d.marketCap && d.marketCap.trim() !== '' ? +d.marketCap : null,
        country: d.country && d.country.trim() !== '' ? d.country : null,
        website: d.website && d.website.trim() !== '' ? d.website : null,
        isETF: d.sector === 'ETF'
      };
    });
    var sectors = Array.from(new Set(data.map(function(d) { return d.sector; })));
    var colorScale = d3.scaleOrdinal().domain(sectors).range(d3.schemeTableau10);
    var marketCaps = data.filter(function(d) { return d.marketCap != null; }).map(function(d) { return d.marketCap; });
    var radiusScale = d3.scaleSqrt().domain([0, d3.max(marketCaps)]).range([6, 50]);
    var defaultETFRadius = 12;
    function getRadius(d) { return d.isETF ? defaultETFRadius : radiusScale(d.marketCap || 0); }
    var centerX = innerWidth / 2, centerY = innerHeight / 2;
    var numSectors = sectors.length;
    var clusterCenters = {};
    var clusterRadius = Math.min(innerWidth, innerHeight) * 0.3;
    sectors.forEach(function(s, i) {
      var angle = (2 * Math.PI * i) / numSectors - Math.PI / 2;
      clusterCenters[s] = { x: centerX + clusterRadius * Math.cos(angle), y: centerY + clusterRadius * Math.sin(angle) };
    });
    var svg = d3.select('#bubble-chart').append('svg').attr('width', chartWidth).attr('height', chartHeight);
    var g = svg.append('g').attr('transform', 'translate(' + margin.left + ',' + margin.top + ')');
    var simulation = d3.forceSimulation(data)
      .force('x', d3.forceX(function(d) { return clusterCenters[d.sector].x; }).strength(0.3))
      .force('y', d3.forceY(function(d) { return clusterCenters[d.sector].y; }).strength(0.3))
      .force('collide', d3.forceCollide(function(d) { return getRadius(d) + 2; }).iterations(4))
      .force('center', d3.forceCenter(centerX, centerY).strength(0.02))
      .force('charge', d3.forceManyBody().strength(-3))
      .on('tick', ticked);
    var bubbles = g.selectAll('.bubble').data(data).join('circle')
      .attr('class', 'bubble').attr('r', function(d) { return getRadius(d); })
      .attr('fill', function(d) { return colorScale(d.sector); })
      .attr('data-ticker', function(d) { return d.ticker; })
      .on('mouseover', function(event, d) {
        if (d.isETF) return;
        tooltip.classed('visible', true).html('<strong>' + d.ticker + '</strong><br/>' + d.name + '<br/>Sector: ' + d.sector);
      })
      .on('mousemove', function(event) { tooltip.style('left', (event.pageX + 12) + 'px').style('top', (event.pageY - 28) + 'px'); })
      .on('mouseout', function() { tooltip.classed('visible', false); })
      .on('click', function(event, d) { selectStock(d.ticker); });
    var labels = g.selectAll('.bubble-label').data(data).join('text')
      .attr('class', 'bubble-label').text(function(d) { return d.ticker; })
      .style('font-size', function(d) {
        var r = getRadius(d), len = d.ticker.length;
        var size = Math.min(r * 1.2, r * 2 / len * 1.2);
        return Math.max(6, Math.min(size, 14)) + 'px';
      });
    function ticked() {
      bubbles.attr('cx', function(d) { return d.x; }).attr('cy', function(d) { return d.y; });
      labels.attr('x', function(d) { return d.x; }).attr('y', function(d) { return d.y; });
    }
    // HTML Legend
    var legendContainer = d3.select('#legend');
    sectors.forEach(function(s) {
      var item = legendContainer.append('div').attr('class', 'legend-item');
      item.append('span').attr('class', 'legend-swatch').style('background-color', colorScale(s));
      item.append('span').attr('class', 'legend-label').text(s);
    });
    // Data Table
    var table = d3.select('#data-table').append('table');
    var thead = table.append('thead');
    thead.append('tr').selectAll('th').data(['Ticker symbol', 'Full company name', 'Sector', 'Market cap']).join('th').text(function(d) { return d; });
    var tbody = table.append('tbody');
    var rows = tbody.selectAll('tr').data(data).join('tr')
      .attr('data-ticker', function(d) { return d.ticker; })
      .on('click', function(event, d) { selectStock(d.ticker); });
    rows.selectAll('td').data(function(d) { return [d.ticker, d.name, d.sector, formatMarketCap(d.marketCap)]; }).join('td').text(function(d) { return d; });
    // Selection / Coordination
    var selectedTicker = null;
    function selectStock(ticker) {
      if (selectedTicker === ticker) { selectedTicker = null; bubbles.classed('selected', false).classed('highlighted', false); rows.classed('highlighted', false).classed('selected', false); return; }
      selectedTicker = ticker;
      bubbles.classed('selected', function(d) { return d.ticker === ticker; }).classed('highlighted', function(d) { return d.ticker === ticker; });
      rows.classed('highlighted', function(d) { return d.ticker === ticker; }).classed('selected', function(d) { return d.ticker === ticker; });
      var tableContainer = document.querySelector('.table-container');
      var highlightedRow = tableContainer.querySelector('tr[data-ticker="' + ticker + '"]');
      if (highlightedRow) { highlightedRow.scrollIntoView({ block: 'center', behavior: 'smooth' }); }
    }
  }).catch(function(err) { console.error('Error loading data:', err); });
})();
''';

def write_visualization_js(output_dir, csv_relative_path='data/stock-descriptions.csv'):
    """Write visualization.js."""
    js_dir = os.path.join(output_dir, 'js')
    os.makedirs(js_dir, exist_ok=True)
    with open(os.path.join(js_dir, 'visualization.js'), 'w') as f:
        f.write(get_visualization_js(csv_relative_path))

def write_index_html(output_dir):
    """Write index.html entry point."""
    html = """<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Stock Visualization Dashboard</title>
  <link rel="stylesheet" href="css/style.css">
</head>
<body>
  <h1>Stock Market Visualization</h1>
  <div class="container">
    <div class="chart-container">
      <h2>Stock Bubble Chart (by Sector &amp; Market Cap)</h2>
      <div id="bubble-chart"></div>
      <div id="legend" class="legend"></div>
    </div>
    <div class="table-container">
      <h2>Stock Data Table</h2>
      <div id="data-table"></div>
    </div>
  </div>
  <script src="js/d3.v6.min.js"></script>
  <script src="js/visualization.js"></script>
</body>
</html>"""
    with open(os.path.join(output_dir, 'index.html'), 'w') as f:
        f.write(html)

def generate_stock_viz_app(input_data_dir, output_dir):
    """End-to-end: generate the complete stock visualization web app."""
    os.makedirs(output_dir, exist_ok=True)
    ensure_d3_library(output_dir)
    copy_data(input_data_dir, output_dir)
    write_css(output_dir)
    write_visualization_js(output_dir)
    write_index_html(output_dir)
    print(f'Stock visualization app generated at {output_dir}')

def validate_app(output_dir):
    """Validate the generated app has all required files and structure."""
    required = ['index.html', 'js/d3.v6.min.js', 'js/visualization.js', 'css/style.css', 'data/stock-descriptions.csv']
    errors = []
    for f in required:
        path = os.path.join(output_dir, f)
        if not os.path.exists(path):
            errors.append(f'Missing: {f}')
        elif os.path.getsize(path) == 0:
            errors.append(f'Empty: {f}')
    indiv = os.path.join(output_dir, 'data', 'indiv-stock')
    if not os.path.isdir(indiv):
        errors.append('Missing: data/indiv-stock/ directory')
    else:
        csvs = [f for f in os.listdir(indiv) if f.endswith('.csv')]
        if len(csvs) < 40:
            errors.append(f'Too few stock CSVs: {len(csvs)}')
    if errors:
        for e in errors:
            print(f'  - {e}')
        return False
    print('Validation PASSED')
    return True

if __name__ == '__main__':
    import sys
    input_dir = sys.argv[1] if len(sys.argv) > 1 else '/root/data'
    output = sys.argv[2] if len(sys.argv) > 2 else '/root/output'
    generate_stock_viz_app(input_dir, output)
    validate_app(output)
