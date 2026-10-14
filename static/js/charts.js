/* ==========================================================================
   图表绘制（原生 Canvas 实现，不依赖 ECharts 等外部库）
   样式风格：浅灰网格、细线条、平铺色块，与系统整体配色保持一致
   ========================================================================== */

var Chart = (function () {
  var GRID = '#eef0f3';
  var AXIS_TEXT = '#909399';
  var VALUE_TEXT = '#606266';
  var FONT = '11px "Microsoft YaHei", "微软雅黑", sans-serif';

  function setup(canvas, height) {
    var dpr = window.devicePixelRatio || 1;
    var width = canvas.clientWidth || (canvas.parentElement ? canvas.parentElement.clientWidth : 600) || 600;
    width = Math.max(width, 240);
    canvas.width = width * dpr;
    canvas.height = height * dpr;
    canvas.style.height = height + 'px';
    var ctx = canvas.getContext('2d');
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    return { ctx: ctx, width: width, height: height };
  }

  function empty(canvas, height, message) {
    var env = setup(canvas, height);
    env.ctx.fillStyle = AXIS_TEXT;
    env.ctx.font = '12px "Microsoft YaHei", sans-serif';
    env.ctx.textAlign = 'center';
    env.ctx.fillText(message || '暂无数据', env.width / 2, env.height / 2);
  }

  /* ------------------------------- 折线图 ------------------------------- */
  function line(canvas, options) {
    var labels = options.labels || [];
    var values = options.values || [];
    var hasValue = values.some(function (item) { return item !== null && item !== undefined; });
    if (!labels.length || !hasValue) {
      empty(canvas, options.height || 200, options.emptyText);
      return;
    }
    var height = options.height || 200;
    var env = setup(canvas, height);
    var ctx = env.ctx;
    var pad = { left: 42, right: 12, top: 14, bottom: 26 };
    var chartW = env.width - pad.left - pad.right;
    var chartH = height - pad.top - pad.bottom;
    var min = options.min === undefined ? 0 : options.min;
    var max = options.max === undefined ? 100 : options.max;
    var color = options.color || '#2b6cb0';

    function yOf(value) { return pad.top + chartH - ((value - min) / (max - min)) * chartH; }
    function xOf(index) {
      return pad.left + (labels.length === 1 ? chartW / 2 : (chartW * index) / (labels.length - 1));
    }

    ctx.font = FONT;
    ctx.lineWidth = 1;
    ctx.strokeStyle = GRID;
    for (var i = 0; i <= 5; i += 1) {
      var tickValue = min + ((max - min) * i) / 5;
      var y = yOf(tickValue);
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartW, y);
      ctx.stroke();
      ctx.fillStyle = AXIS_TEXT;
      ctx.textAlign = 'right';
      ctx.fillText(String(Math.round(tickValue)), pad.left - 7, y + 4);
    }

    var points = values.map(function (value, index) {
      return { x: xOf(index), y: yOf(value === null ? min : value), value: value };
    });

    ctx.beginPath();
    points.forEach(function (point, index) {
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.lineTo(points[points.length - 1].x, pad.top + chartH);
    ctx.lineTo(points[0].x, pad.top + chartH);
    ctx.closePath();
    ctx.fillStyle = 'rgba(43, 108, 176, 0.07)';
    ctx.fill();

    ctx.beginPath();
    points.forEach(function (point, index) {
      if (index === 0) ctx.moveTo(point.x, point.y);
      else ctx.lineTo(point.x, point.y);
    });
    ctx.strokeStyle = color;
    ctx.lineWidth = 1.6;
    ctx.stroke();

    ctx.fillStyle = AXIS_TEXT;
    ctx.textAlign = 'center';
    var lastLabelX = -999;
    labels.forEach(function (label, index) {
      var x = xOf(index);
      var isLast = index === labels.length - 1;
      if (x - lastLabelX < 56 && !isLast) return;
      if (isLast && x - lastLabelX < 56) return;
      ctx.fillText(label, x, height - 8);
      lastLabelX = x;
    });

    ctx.fillStyle = color;
    points.forEach(function (point) {
      if (point.value === null || point.value === undefined) return;
      ctx.beginPath();
      ctx.arc(point.x, point.y, 2.2, 0, Math.PI * 2);
      ctx.fill();
    });
  }

  /* ------------------------------- 柱状图 ------------------------------- */
  function bar(canvas, options) {
    var labels = options.labels || [];
    var values = options.values || [];
    if (!labels.length) {
      empty(canvas, options.height || 200, options.emptyText);
      return;
    }
    var height = options.height || 200;
    var env = setup(canvas, height);
    var ctx = env.ctx;
    var pad = { left: 42, right: 12, top: 18, bottom: 28 };
    var chartW = env.width - pad.left - pad.right;
    var chartH = height - pad.top - pad.bottom;
    var max = Math.max.apply(null, values.concat([1])) * 1.18;
    var slot = chartW / values.length;
    var barWidth = Math.min(slot * 0.5, 40);

    ctx.font = FONT;
    ctx.lineWidth = 1;
    for (var i = 0; i <= 4; i += 1) {
      var y = pad.top + chartH - (chartH * i) / 4;
      ctx.strokeStyle = GRID;
      ctx.beginPath();
      ctx.moveTo(pad.left, y);
      ctx.lineTo(pad.left + chartW, y);
      ctx.stroke();
      ctx.fillStyle = AXIS_TEXT;
      ctx.textAlign = 'right';
      ctx.fillText(String(Math.round((max * i) / 4)), pad.left - 7, y + 4);
    }

    values.forEach(function (value, index) {
      var barHeight = Math.max((value / max) * chartH, value > 0 ? 2 : 0);
      var x = pad.left + slot * index + (slot - barWidth) / 2;
      var y = pad.top + chartH - barHeight;
      ctx.fillStyle = (options.colors && options.colors[index]) || options.color || '#2b6cb0';
      ctx.fillRect(x, y, barWidth, barHeight);
      ctx.textAlign = 'center';
      if (value > 0) {
        ctx.fillStyle = VALUE_TEXT;
        ctx.fillText(String(value), x + barWidth / 2, y - 4);
      }
      ctx.fillStyle = AXIS_TEXT;
      ctx.fillText(labels[index], pad.left + slot * index + slot / 2, height - 9);
    });
  }

  /* --------------------------- 环形图（饼图） --------------------------- */
  function pie(canvas, options) {
    var items = (options.items || []).filter(function (item) { return item.value > 0; });
    if (!items.length) {
      empty(canvas, options.height || 210, options.emptyText);
      return null;
    }
    var height = options.height || 210;
    var env = setup(canvas, height);
    var ctx = env.ctx;
    var total = items.reduce(function (sum, item) { return sum + item.value; }, 0);
    var centerX = env.width / 2;
    var centerY = height / 2;
    var radius = Math.min(env.width, height) / 2 - 14;
    var start = -Math.PI / 2;

    items.forEach(function (item) {
      var angle = (item.value / total) * Math.PI * 2;
      ctx.beginPath();
      ctx.moveTo(centerX, centerY);
      ctx.arc(centerX, centerY, radius, start, start + angle);
      ctx.closePath();
      ctx.fillStyle = item.color || '#2b6cb0';
      ctx.fill();
      start += angle;
    });

    ctx.beginPath();
    ctx.arc(centerX, centerY, radius * 0.58, 0, Math.PI * 2);
    ctx.fillStyle = '#fff';
    ctx.fill();
    ctx.textAlign = 'center';
    ctx.fillStyle = '#303133';
    ctx.font = '600 16px "Microsoft YaHei", sans-serif';
    ctx.fillText(String(total), centerX, centerY + 1);
    ctx.fillStyle = AXIS_TEXT;
    ctx.font = FONT;
    ctx.fillText('累计人次', centerX, centerY + 17);
    return items;
  }

  return { line: line, bar: bar, pie: pie, empty: empty };
}());
