/* OcuVal report page: interactive charts.
 *
 * Every value drawn here comes from the JSON embedded in index.html, which
 * scripts/08_build_site.py generates from the evaluation records. Nothing is computed
 * that the page does not already state. If Plotly fails to load, or a chart fails to
 * draw, that chart keeps its static figure from docs/figures.
 */
(function () {
  "use strict";

  var DATA = JSON.parse(document.getElementById("ocuval-data").textContent);
  var FOLDS = ["cirrus", "spectralis", "topcon"];
  var CLASSES = ["IRF", "SRF", "PED"];
  var ARMS = ["held_out", "in_domain"];
  var NAME = { cirrus: "Cirrus", spectralis: "Spectralis", topcon: "Topcon", pooled: "Pooled" };
  var ARM_NAME = { held_out: "Unseen brand", in_domain: "Familiar brands" };
  var CONFIG = { responsive: true, displayModeBar: false };
  var FONT = 13;

  function css(name) {
    return getComputedStyle(document.documentElement).getPropertyValue(name).trim();
  }

  function theme() {
    return {
      fg: css("--fg"), muted: css("--muted"), grid: css("--border"), band: css("--band"),
      bg: css("--bg"), held: css("--held"), ref: css("--ref"), present: css("--present")
    };
  }

  function f4(x) {
    return x === null || x === undefined ? "not defined" : x.toFixed(4);
  }

  function signed(x) {
    return (x >= 0 ? "+" : "") + x.toFixed(4);
  }

  function ivText(d) {
    if (d.value === null) return "not defined";
    if (d.n === 1) return f4(d.value) + " (1 patient, no interval)";
    return f4(d.value) + " [" + f4(d.ci_low) + ", " + f4(d.ci_high) + "]";
  }

  function base(t, height) {
    return {
      height: height,
      paper_bgcolor: t.bg,
      plot_bgcolor: t.bg,
      font: { family: css("--font"), size: FONT, color: t.fg },
      hoverlabel: { font: { size: FONT } },
      legend: { orientation: "h", x: 0.5, xanchor: "center", y: 1.02, yanchor: "bottom" },
      margin: { l: 120, r: 16, t: 56, b: 64 }
    };
  }

  /* Rows of the two interval charts: each run's three fluid types, then the pooled rows. */
  function rows() {
    var out = [];
    var comps = FOLDS.concat(["pooled"]);
    var n = comps.length * CLASSES.length;
    comps.forEach(function (comp, k) {
      CLASSES.forEach(function (cls, j) {
        var y = n - 1 - (k * CLASSES.length + j);
        if (comp === "pooled") y -= 0.6;
        out.push({ comp: comp, cls: cls, y: y });
      });
    });
    return out;
  }

  function furniture(t, rs) {
    var shapes = [];
    [0, 2].forEach(function (k) {
      var ys = rs.slice(k * 3, k * 3 + 3).map(function (r) { return r.y; });
      shapes.push({
        type: "rect", xref: "paper", x0: 0, x1: 1, yref: "y",
        y0: Math.min.apply(null, ys) - 0.5, y1: Math.max.apply(null, ys) + 0.5,
        fillcolor: t.band, line: { width: 0 }, layer: "below"
      });
    });
    var sep = (rs[8].y + rs[9].y) / 2;
    shapes.push({ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y", y0: sep, y1: sep,
                  line: { color: t.fg, width: 2 } });
    return {
      shapes: shapes,
      yaxis: {
        tickvals: rs.map(function (r) { return r.y; }),
        ticktext: rs.map(function (r) { return NAME[r.comp] + " " + r.cls; }),
        range: [rs[rs.length - 1].y - 0.6, rs[0].y + 0.6],
        showgrid: false, zeroline: false, fixedrange: true
      }
    };
  }

  function errorTrace(points, color, name, symbol, opts) {
    opts = opts || {};
    return {
      type: "scatter", mode: "markers", name: name,
      x: points.map(function (p) { return p.v; }),
      y: points.map(function (p) { return p.y; }),
      customdata: points.map(function (p) { return p.hover; }),
      hovertemplate: "%{customdata}<extra></extra>",
      marker: { color: opts.open ? "rgba(0,0,0,0)" : color, size: 12, symbol: symbol,
                line: { color: color, width: 2 } },
      opacity: opts.opacity || 1,
      error_x: {
        type: "data", symmetric: false, color: color, thickness: 2.5, width: 6,
        array: points.map(function (p) { return p.hi - p.v; }),
        arrayminus: points.map(function (p) { return p.v - p.lo; })
      }
    };
  }

  function headline(el, t) {
    var rs = rows();
    var lookup = {};
    DATA.results.per_run.forEach(function (r) { lookup[r.run + r.fluid + r.arm] = r.dice; });
    DATA.results.pooled.forEach(function (r) { lookup["pooled" + r.fluid + r.arm] = r.dice; });
    var traces = ARMS.map(function (arm, a) {
      var pts = rs.map(function (r) {
        var d = lookup[r.comp + r.cls + arm];
        return {
          v: d.value, lo: d.ci_low, hi: d.ci_high, y: r.y + (a === 0 ? 0.17 : -0.17),
          hover: "<b>" + NAME[r.comp] + " " + r.cls + "</b>" +
            (r.comp === "pooled" ? " (pooled, post-hoc)" : "") + "<br>" + ARM_NAME[arm] +
            ": Dice " + ivText(d) + "<br>n = " + d.n + " patients"
        };
      });
      return errorTrace(pts, a === 0 ? t.held : t.ref,
                        a === 0 ? "Unseen brand (held-out)" : "Familiar brands, new patients (in-domain)",
                        "circle");
    });
    var f = furniture(t, rs);
    var layout = base(t, el.clientWidth < 600 ? 640 : 580);
    layout.shapes = f.shapes;
    layout.yaxis = f.yaxis;
    layout.xaxis = { range: [-0.02, 0.8], dtick: 0.1, gridcolor: t.grid, zeroline: false,
                     title: { text: "Dice over all scans, 95% interval" }, fixedrange: true };
    Plotly.newPlot(el, traces, layout, CONFIG);
  }

  function difference(el, t) {
    var rs = rows();
    var groups = { "all-volume": [], "class-present": [], invalid: [] };
    DATA.results.differences.forEach(function (d) {
      var r = rs.filter(function (q) { return q.comp === d.comparison && q.cls === d.fluid; })[0];
      var allScans = d.view === "all-volume";
      var p = {
        v: d.value, lo: d.ci_low, hi: d.ci_high, y: r.y + (allScans ? 0.17 : -0.17),
        hover: "<b>" + NAME[d.comparison] + " " + d.fluid + "</b>, " +
          (allScans ? "all scans" : "only scans containing the fluid type") +
          "<br>Unseen minus familiar: " + signed(d.value) + " [" + signed(d.ci_low) + ", " +
          signed(d.ci_high) + "]<br>n = " + d.n_held_out + " unseen, " + d.n_in_domain +
          " familiar patients" + (d.excludes_zero ? "<br>Excludes zero" : "") +
          (d.n_in_domain === 1 ? "<br>One familiar patient: not a valid interval" : "")
      };
      if (!allScans && d.n_in_domain === 1) groups.invalid.push(p);
      else groups[d.view].push(p);
    });
    var traces = [
      errorTrace(groups["all-volume"], t.fg, "All scans", "circle"),
      errorTrace(groups["class-present"], t.present, "Only scans containing the fluid type", "diamond"),
      errorTrace(groups.invalid, t.present, "Only 1 familiar-brand patient: not a valid interval",
                 "diamond", { open: true, opacity: 0.6 })
    ];
    var f = furniture(t, rs);
    var layout = base(t, el.clientWidth < 600 ? 680 : 600);
    layout.shapes = f.shapes.concat([{ type: "line", xref: "x", x0: 0, x1: 0, yref: "paper",
                                       y0: 0, y1: 1, line: { color: t.fg, width: 3 } }]);
    layout.yaxis = f.yaxis;
    layout.margin.b = 96;
    layout.xaxis = { range: [-0.75, 0.75], dtick: 0.2, gridcolor: t.grid, zeroline: false,
                     title: { text: "Held-out minus in-domain Dice, 95% interval", standoff: 36 },
                     fixedrange: true };
    layout.annotations = [
      { xref: "paper", yref: "paper", x: 0, y: -0.09, xanchor: "left", yanchor: "top",
        showarrow: false, text: "<i>← unseen brand worse</i>" },
      { xref: "paper", yref: "paper", x: 1, y: -0.09, xanchor: "right", yanchor: "top",
        showarrow: false, text: "<i>unseen brand better →</i>" }
    ];
    Plotly.newPlot(el, traces, layout, CONFIG);
  }

  /* Per-scan charts: one column of points per run, test set and fluid type. */
  function columns() {
    var cols = [];
    FOLDS.forEach(function (fold, fi) {
      ARMS.forEach(function (arm, ai) {
        CLASSES.forEach(function (cls, ci) {
          cols.push({ fold: fold, arm: arm, cls: cls, x: fi * 8 + ai * 3.6 + ci * 1.1 });
        });
      });
    });
    return cols;
  }

  function scatterByColumn(t, value, hoverValue) {
    var cols = columns();
    var traces = [];
    ARMS.forEach(function (arm) {
      [true, false].forEach(function (present) {
        var xs = [], ys = [], hs = [];
        cols.filter(function (c) { return c.arm === arm; }).forEach(function (c) {
          var pts = DATA.per_scan.rows.filter(function (s) {
            return s.run === c.fold && s.arm === arm && s.fluid === c.cls && s.present === present;
          });
          pts.forEach(function (s, i) {
            var spread = pts.length > 1 ? (i / (pts.length - 1) - 0.5) * 0.7 : 0;
            xs.push(c.x + (present ? -0.18 : 0.18) + spread * 0.35);
            ys.push(value(s));
            hs.push(NAME[c.fold] + " held out, " + ARM_NAME[arm].toLowerCase() + " test set<br>" +
                    c.cls + (present ? " present" : " absent") + " (" + NAME[s.vendor] + " scan)<br>" +
                    hoverValue(s));
          });
        });
        var color = arm === "held_out" ? t.held : t.ref;
        traces.push({
          type: "scatter", mode: "markers", x: xs, y: ys, customdata: hs,
          hovertemplate: "%{customdata}<extra></extra>",
          name: ARM_NAME[arm] + ", fluid " + (present ? "present" : "absent"),
          marker: { size: 8, color: present ? color : "rgba(0,0,0,0)",
                    line: { color: color, width: 1.5 } }
        });
      });
    });
    var annotations = FOLDS.map(function (fold, fi) {
      return { xref: "x", yref: "paper", x: fi * 8 + 2.9, y: 1.0, yanchor: "bottom",
               showarrow: false, text: "<b>" + NAME[fold] + " held out</b>" };
    });
    FOLDS.forEach(function (fold, fi) {
      ARMS.forEach(function (arm, ai) {
        annotations.push({
          xref: "x", yref: "paper", x: fi * 8 + ai * 3.6 + 1.1, y: -0.1, yanchor: "top",
          showarrow: false, text: ai === 0 ? "unseen" : "familiar",
          font: { color: arm === "held_out" ? t.held : t.ref }
        });
      });
    });
    var xaxis = {
      tickvals: cols.map(function (c) { return c.x; }),
      ticktext: cols.map(function (c) { return c.cls; }),
      tickangle: 0, tickfont: { size: 11 },
      range: [-0.8, 2 * 8 + 3.6 + 2.2 + 0.8], showgrid: false, zeroline: false, fixedrange: true
    };
    var seps = [1, 2].map(function (k) {
      return { type: "line", xref: "x", x0: k * 8 - 1.25, x1: k * 8 - 1.25, yref: "paper",
               y0: 0, y1: 1, line: { color: t.grid, width: 1.5 } };
    });
    return { traces: traces, annotations: annotations, xaxis: xaxis, shapes: seps };
  }

  function perscan(el, t) {
    var c = scatterByColumn(t, function (s) { return s.dice; }, function (s) {
      return "Dice " + f4(s.dice);
    });
    var layout = base(t, 520);
    layout.margin = { l: 64, r: 16, t: 96, b: 72 };
    layout.legend.y = 1.12;
    layout.xaxis = c.xaxis;
    layout.yaxis = { range: [-0.05, 1.05], gridcolor: t.grid, zeroline: false,
                     title: { text: "Dice per scan" }, fixedrange: true };
    layout.annotations = c.annotations;
    layout.shapes = c.shapes;
    Plotly.newPlot(el, c.traces, layout, CONFIG);
  }

  function detection(el, t) {
    var threshold = DATA.facts.threshold;
    var c = scatterByColumn(t, function (s) {
      return s.predicted_voxels > 0 ? s.predicted_voxels : 0.5;
    }, function (s) {
      return s.predicted_voxels > 0 ? s.predicted_voxels.toLocaleString("en") + " voxels predicted"
                                    : "no voxels predicted";
    });
    var top = Math.max.apply(null, DATA.per_scan.rows.map(function (s) { return s.predicted_voxels; }));
    var layout = base(t, 520);
    layout.margin = { l: 72, r: 16, t: 96, b: 72 };
    layout.legend.y = 1.12;
    layout.xaxis = c.xaxis;
    layout.yaxis = { type: "log", range: [Math.log10(0.35), Math.log10(top * 2)],
                     gridcolor: t.grid, title: { text: "Predicted voxels (log scale)" },
                     fixedrange: true };
    layout.annotations = c.annotations.concat([{
      xref: "paper", yref: "y", x: 1, y: Math.log10(threshold), xanchor: "right",
      yanchor: "bottom", showarrow: false, text: "threshold: " + threshold + " voxels",
      font: { color: t.muted }
    }]);
    layout.shapes = c.shapes.concat([{ type: "line", xref: "paper", x0: 0, x1: 1, yref: "y",
                                       y0: threshold, y1: threshold,
                                       line: { color: t.fg, width: 1.5, dash: "dash" } }]);
    Plotly.newPlot(el, c.traces, layout, CONFIG);
  }

  function training(el, t) {
    var narrow = el.clientWidth < 700;
    var traces = [], shapes = [], annotations = [];
    var layout = base(t, narrow ? 900 : 560);
    layout.margin = { l: 64, r: 16, t: 72, b: 56 };
    layout.showlegend = true;
    /* Plotly names its first axes "xaxis" and "x", not "xaxis1" and "x1". */
    function ax(n) { return n === 1 ? "" : String(n); }
    FOLDS.forEach(function (fold, k) {
      var r = DATA.training[fold];
      var top = ax(k + 1), bottom = ax(k + 4);
      var xdom = narrow ? [0, 1] : [k * 0.35, k * 0.35 + 0.3];
      var band = narrow ? [1 - (k + 1) / 3 + 0.05, 1 - k / 3 - 0.05] : [0, 0.94];
      var ytop = [band[0] + (band[1] - band[0]) * 0.55, band[1]];
      var ybot = [band[0], band[0] + (band[1] - band[0]) * 0.42];
      layout["xaxis" + top] = { domain: xdom, anchor: "y" + top, showticklabels: false,
                                gridcolor: t.grid, fixedrange: true };
      layout["xaxis" + bottom] = { domain: xdom, anchor: "y" + bottom, matches: "x" + top,
                                   gridcolor: t.grid, title: { text: "epoch" }, fixedrange: true };
      layout["yaxis" + top] = { domain: ytop, anchor: "x" + top, gridcolor: t.grid,
                                title: { text: k === 0 || narrow ? "training loss" : "" },
                                fixedrange: true };
      layout["yaxis" + bottom] = { domain: ybot, anchor: "x" + bottom, gridcolor: t.grid,
                                   title: { text: k === 0 || narrow ? "validation Dice" : "" },
                                   fixedrange: true };
      [["train_loss", top, "Training loss"], ["val_dice", bottom, "Validation Dice"]].forEach(
        function (s) {
          traces.push({
            type: "scatter", mode: "lines", x: r.epoch, y: r[s[0]], showlegend: false,
            xaxis: "x" + s[1], yaxis: "y" + s[1], line: { color: t.fg, width: 1.8 },
            hovertemplate: NAME[fold] + " held out<br>Epoch %{x}<br>" + s[2] +
              " %{y:.4f}<extra></extra>"
          });
          var dom = s[1] === top ? ytop : ybot;
          var marks = [[r.best_epoch, t.ref, "dash"], [r.last_epoch, t.muted, "dot"]];
          r.resumed_at.forEach(function (e) { marks.push([e, t.held, "dashdot"]); });
          marks.forEach(function (m) {
            shapes.push({ type: "line", xref: "x" + s[1], x0: m[0], x1: m[0], yref: "paper",
                          y0: dom[0], y1: dom[1], line: { color: m[1], width: 1.6, dash: m[2] } });
          });
        });
      annotations.push({ xref: "paper", yref: "paper", x: (xdom[0] + xdom[1]) / 2,
                         y: band[1], yanchor: "bottom", showarrow: false,
                         text: "<b>" + NAME[fold] + " held out</b><br>best epoch " + r.best_epoch });
    });
    [["Best epoch (checkpoint used)", t.ref, "dash"], ["Early stop", t.muted, "dot"],
     ["Session resumed", t.held, "dashdot"]].forEach(function (k) {
      traces.push({ type: "scatter", mode: "lines", x: [null], y: [null], name: k[0],
                    line: { color: k[1], dash: k[2], width: 2 }, hoverinfo: "skip" });
    });
    layout.legend.y = 1.04;
    layout.margin.t = 96;
    layout.shapes = shapes;
    layout.annotations = annotations;
    Plotly.newPlot(el, traces, layout, CONFIG);
  }

  var CHARTS = { headline: headline, difference: difference, perscan: perscan,
                 detection: detection, training: training };

  function drawAll() {
    if (!window.Plotly) return; // the static figures stay
    var t = theme();
    document.querySelectorAll("figure.chart[data-chart]").forEach(function (fig) {
      var el = fig.querySelector(".plot");
      fig.classList.add("drawn");
      try {
        Plotly.purge(el);
        CHARTS[fig.getAttribute("data-chart")](el, t);
      } catch (err) {
        fig.classList.remove("drawn");
        if (window.console) console.error("chart failed, static figure kept:", err);
      }
    });
  }

  drawAll();
  if (window.matchMedia) {
    var mq = window.matchMedia("(prefers-color-scheme: dark)");
    if (mq.addEventListener) mq.addEventListener("change", drawAll);
  }
})();
