/* 首页概览：数据统计、最近课堂、系统运行状态（数据库 / 模型 / 实时检测服务） */
document.addEventListener('DOMContentLoaded', function () {
  var statusBox = document.getElementById('systemStatus');

  /* -------------------- 数据统计与最近课堂 -------------------- */
  api('/api/reports/dashboard').then(function (data) {
    document.getElementById('courseCount').textContent = data.course_count;
    document.getElementById('sessionCount').textContent = data.session_count;
    document.getElementById('todayCount').textContent = data.today_session_count;
    document.getElementById('runningCount').textContent = data.running_session_count;
    document.getElementById('avgAttention').innerHTML = data.avg_attention === null
      ? '--'
      : data.avg_attention.toFixed(1) + '<small>%</small>';

    var trend = data.attention_trend || [];
    Chart.line(document.getElementById('trendChart'), {
      labels: trend.map(function (item) { return item.label; }),
      values: trend.map(function (item) { return item.value; }),
      height: 236,
      emptyText: '暂无课堂专注度数据',
    });

    var body = document.getElementById('recentBody');
    var rows = data.recent_sessions || [];
    if (!rows.length) {
      body.innerHTML = '<tr><td class="empty" colspan="9">暂无课堂记录，请先到「课堂检测」开始一次课堂</td></tr>';
      return;
    }
    body.innerHTML = rows.map(function (item) {
      return '<tr>' +
        '<td class="strong">' + esc(item.course_name) + '</td>' +
        '<td>' + (esc(item.class_name) || '--') + '</td>' +
        '<td>' + esc(item.date) + '</td>' +
        '<td>' + (esc(item.time_range) || '--') + '</td>' +
        '<td>' + fmtDuration(item.duration_minutes) + '</td>' +
        '<td class="strong">' + fmtPercent(item.avg_attention) + '</td>' +
        '<td>' + esc(item.level) + '</td>' +
        '<td>' + (item.status === 'running' ? '进行中' : '已结束') + '</td>' +
        '<td><a href="/report/' + item.id + '">查看报告</a>' +
        (item.status === 'running'
          ? ' <a href="/classroom?session_id=' + item.id + '">继续检测</a>' : '') +
        '</td></tr>';
    }).join('');
  }).catch(function (err) {
    toast(err.message, 'error');
  });

  /* -------------------- 系统运行状态 -------------------- */
  function statusItem(label, value, level) {
    return '<div class="status-item"><span class="dot ' + (level || '') + '"></span>' +
      '<b>' + esc(label) + '</b>' + esc(value) + '</div>';
  }

  function loadStatus() {
    statusBox.innerHTML = '<div class="status-item"><span class="dot wait"></span><b>正在检测…</b></div>';
    api('/api/system/status').then(function (status) {
      var model = status.model || {};
      var db = status.database || {};
      var items = [];

      if (db.is_mysql) {
        items.push(statusItem('数据库：', 'MySQL ' + (db.server_version || '') + ' · ' + db.database_name, 'ok'));
      } else if (db.fallback_to_sqlite) {
        items.push(statusItem('数据库：', 'SQLite（未连接 MySQL）', 'warn'));
      } else {
        items.push(statusItem('数据库：', '未连接', 'error'));
      }

      if (!model.model_exists) {
        items.push(statusItem('检测模型：', '权重文件缺失', 'error'));
      } else if (model.loaded) {
        items.push(statusItem('检测模型：', 'YOLOv8 已加载', 'ok'));
      } else {
        items.push(statusItem('检测模型：', 'YOLOv8 待加载', 'warn'));
      }

      items.push(statusItem('识别类别：', '6 类课堂行为', 'ok'));
      if (model.avg_inference_ms) {
        items.push(statusItem(
          '推理性能：',
          model.avg_inference_ms + ' ms/帧（' + String(model.runtime_device || 'cpu').toUpperCase()
          + '，模型加载 ' + (model.load_seconds || 0) + ' 秒）',
          'ok'
        ));
      } else {
        items.push(statusItem('推理性能：', '尚未执行检测', 'wait'));
      }
      items.push('<div class="status-item" id="wsStatus"><span class="dot wait"></span>' +
        '<b>实时检测服务：</b>检测中…</div>');
      statusBox.innerHTML = items.join('');
      checkWebSocket();
    }).catch(function (err) {
      statusBox.innerHTML = statusItem('状态获取失败：', err.message, 'error');
    });
  }

  /* 通过 /ws/ping 探测 WebSocket 通道是否可用 */
  function checkWebSocket() {
    var box = document.getElementById('wsStatus');
    if (!box) return;
    var scheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    var socket;
    var finished = false;
    function done(text, level) {
      if (finished) return;
      finished = true;
      box.innerHTML = '<span class="dot ' + level + '"></span><b>实时检测服务：</b>' + esc(text);
      try { socket.close(); } catch (err) { /* 忽略 */ }
    }
    try {
      socket = new WebSocket(scheme + window.location.host + '/ws/ping');
    } catch (err) {
      done('不可用', 'error');
      return;
    }
    socket.onmessage = function () { done('可用', 'ok'); };
    socket.onerror = function () { done('不可用', 'error'); };
    setTimeout(function () { done('不可用（超时）', 'error'); }, 4000);
  }

  document.getElementById('refreshStatus').addEventListener('click', loadStatus);
  loadStatus();
});
