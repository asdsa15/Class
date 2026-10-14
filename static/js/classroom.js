/* ==========================================================================
   课堂检测页面脚本：图片检测 / 视频检测 / 实时课堂（WebSocket）
   ========================================================================== */
document.addEventListener('DOMContentLoaded', function () {
  let courses = [];
  let currentSession = null;
  let socket = null;
  let captureTimer = null;
  let awaitingFrame = false;
  let mediaStream = null;
  let liveScores = [];
  let videoPollTimer = null;
  let realtimeRunning = false;
  let logLines = [];

  const courseSelect = document.getElementById('courseSelect');
  const sessionInfo = document.getElementById('sessionInfo');
  const startBtn = document.getElementById('startBtn');
  const stopBtn = document.getElementById('stopBtn');
  const realtimeBtn = document.getElementById('realtimeBtn');
  const realtimeHint = document.getElementById('realtimeHint');
  const saveResults = document.getElementById('saveResults');
  const liveBox = document.getElementById('liveBox');
  const liveSource = document.getElementById('liveSource');
  const captureCanvas = document.getElementById('captureCanvas');
  const behaviorGrid = document.getElementById('behaviorGrid');
  const detectionBody = document.getElementById('detectionBody');

  /* ------------------------------ 通用渲染 ------------------------------ */
  function log(message) {
    const stamp = new Date().toLocaleTimeString('zh-CN', { hour12: false });
    logLines.unshift('[' + stamp + '] ' + message);
    logLines = logLines.slice(0, 80);
    document.getElementById('realtimeLog').innerHTML = logLines.map((line) => '<div>' + esc(line) + '</div>').join('');
  }

  function renderBehaviorGrid(counts) {
    counts = counts || {};
    behaviorGrid.innerHTML = BEHAVIOR_ORDER.map((key) => `
      <div class="behavior-cell ${isFocused(key) ? 'focused' : 'unfocused'}">
        <div class="name">${esc(behaviorCn(key))}</div>
        <div class="count">${counts[key] || 0}</div>
      </div>`).join('');
  }

  function renderStats(payload) {
    const attention = payload.attention || {};
    const score = attention.score === undefined ? null : attention.score;
    const scoreBox = document.getElementById('attentionScore');
    scoreBox.textContent = score === null ? '--' : Number(score).toFixed(1) + '%';
    scoreBox.className = 'score-value ' + attentionClass(score);
    document.getElementById('attentionLevel').textContent =
      '专注度评价：' + (attention.level || '无有效数据');
    document.getElementById('studentCount').textContent = payload.student_count === undefined ? '--' : payload.student_count;
    document.getElementById('focusSplit').textContent =
      (payload.focused_count === undefined ? '--' : payload.focused_count) + ' / ' +
      (payload.unfocused_count === undefined ? '--' : payload.unfocused_count);
    document.getElementById('detectTime').textContent =
      payload.detect_time === undefined ? '--' : payload.detect_time + ' s';
    renderBehaviorGrid(payload.counts);

    const items = payload.detections || [];
    if (!items.length) {
      detectionBody.innerHTML = '<tr><td class="empty" colspan="4">本帧未检测到课堂行为</td></tr>';
    } else {
      detectionBody.innerHTML = items.slice(0, 50).map((item) => `
        <tr>
          <td>${esc(item.behavior_cn || behaviorCn(item.behavior_key))}</td>
          <td>${esc(item.class_name)}</td>
          <td>${(item.confidence * 100).toFixed(1)}%</td>
          <td>${item.xyxy.map((value) => Math.round(value)).join(', ')}</td>
        </tr>`).join('');
    }
    document.getElementById('detectionHint').textContent = '共 ' + items.length + ' 个目标';
  }

  function pushScore(score) {
    if (score === null || score === undefined) return;
    liveScores.push(Number(score));
    if (liveScores.length > 80) liveScores.shift();
    Chart.line(document.getElementById('liveTrend'), {
      labels: liveScores.map((item, index) => String(index + 1)),
      values: liveScores,
      height: 140,
      color: '#23a55a',
      emptyText: '暂无专注度数据',
    });
  }

  /* ------------------------------ 课堂管理 ------------------------------ */
  function renderSession() {
    if (!currentSession) {
      sessionInfo.className = 'banner';
      sessionInfo.textContent = '尚未创建课堂：请选择课程后点击「开始课堂」，检测结果将保存到该课堂。';
      startBtn.disabled = false;
      stopBtn.disabled = true;
      realtimeBtn.disabled = true;
      realtimeHint.textContent = '请先开始课堂';
      return;
    }
    sessionInfo.className = currentSession.status === 'running' ? 'banner' : 'banner warn';
    const elapsed = elapsedText();
    sessionInfo.innerHTML =
      '当前课堂：<strong>' + esc(currentSession.course_name) + '</strong>（课堂 ID ' + currentSession.id + '）' +
      ' ｜ 开始时间 ' + fmtTime(currentSession.start_time) +
      ' ｜ 已进行 <strong id="elapsed"></strong>' +
      ' ｜ 状态 ' + statusBadge(currentSession.status);
    updateElapsed();
    startBtn.disabled = currentSession.status === 'running';
    stopBtn.disabled = currentSession.status !== 'running';
    realtimeBtn.disabled = false;
    realtimeHint.textContent = currentSession.status === 'running'
      ? '实时检测结果会按设定间隔自动写入本课堂'
      : '该课堂已结束，实时检测结果不会写入数据库（可继续预览）';
  }

  function elapsedText() {
    if (!currentSession || !currentSession.start_time) return '--';
    const start = new Date(currentSession.start_time);
    const end = currentSession.status === 'finished' && currentSession.end_time
      ? new Date(currentSession.end_time) : new Date();
    const seconds = Math.max(0, Math.floor((end - start) / 1000));
    const minutes = Math.floor(seconds / 60);
    return minutes + ' 分 ' + (seconds % 60) + ' 秒';
  }

  function updateElapsed() {
    const box = document.getElementById('elapsed');
    if (box) box.textContent = elapsedText();
  }
  setInterval(updateElapsed, 1000);

  async function loadCourses() {
    try {
      courses = await api('/api/courses');
      if (!courses.length) {
        courseSelect.innerHTML = '<option value="">暂无课程，请先到「课程管理」创建</option>';
        return;
      }
      courseSelect.innerHTML = courses.map((course) =>
        `<option value="${course.id}">${esc(course.course_name)}${course.class_name ? '（' + esc(course.class_name) + '）' : ''}</option>`
      ).join('');
      const params = new URLSearchParams(window.location.search);
      const courseId = params.get('course_id');
      if (courseId) courseSelect.value = courseId;
      await resolveRunningSession(params.get('session_id'));
    } catch (err) {
      toast(err.message, 'error');
    }
  }

  async function resolveRunningSession(preferSessionId) {
    const courseId = courseSelect.value;
    if (!courseId) return;
    const rows = await api('/api/classrooms?course_id=' + courseId + '&limit=20');
    let session = null;
    if (preferSessionId) {
      session = rows.find((item) => String(item.id) === String(preferSessionId)) || null;
    }
    if (!session) session = rows.find((item) => item.status === 'running') || null;
    currentSession = session;
    renderSession();
  }

  startBtn.addEventListener('click', async function () {
    const courseId = courseSelect.value;
    if (!courseId) { toast('请先选择课程', 'error'); return; }
    startBtn.disabled = true;
    try {
      currentSession = await api('/api/classrooms/start', { method: 'POST', body: { course_id: Number(courseId) } });
      toast('课堂已开始（ID ' + currentSession.id + '）', 'success');
      renderSession();
    } catch (err) {
      toast(err.message, 'error');
      startBtn.disabled = false;
    }
  });

  stopBtn.addEventListener('click', async function () {
    if (!currentSession) return;
    if (!window.confirm('确定结束当前课堂吗？结束后可以查看课堂报告。')) return;
    try {
      stopRealtime(true);
      currentSession = await api('/api/classrooms/' + currentSession.id + '/stop', { method: 'POST' });
      toast('课堂已结束，可到「历史课堂」查看报告', 'success');
      renderSession();
    } catch (err) { toast(err.message, 'error'); }
  });

  courseSelect.addEventListener('change', function () {
    currentSession = null;
    renderSession();
    resolveRunningSession(null).catch(() => {});
  });

  /* ------------------------------ 图片检测 ------------------------------ */
  document.getElementById('imageBtn').addEventListener('click', async function () {
    const fileInput = document.getElementById('imageFile');
    if (!fileInput.files.length) { toast('请先选择一张图片', 'error'); return; }
    const button = this;
    button.disabled = true;
    button.textContent = '检测中…';
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    form.append('conf', document.getElementById('confInput').value || '0.25');
    form.append('with_box', 'true');
    form.append('return_base64', 'true');
    if (currentSession) {
      form.append('session_id', String(currentSession.id));
      form.append('save', saveResults.checked ? 'true' : 'false');
    }
    try {
      const data = await api('/api/detection/image', { method: 'POST', body: form });
      const box = document.getElementById('imageBox');
      box.innerHTML = data.image_base64
        ? '<img src="' + data.image_base64 + '" alt="检测结果">'
        : '<div>检测完成，但未返回标注图片</div>';
      renderStats(data);
      pushScore(data.attention ? data.attention.score : null);
      toast(data.message || '检测完成', 'success');
      log('图片检测完成：' + data.filename + '，目标 ' + (data.detections || []).length + ' 个');
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '开始检测';
    }
  });

  /* ------------------------------ 视频检测 ------------------------------ */
  document.getElementById('videoBtn').addEventListener('click', async function () {
    const fileInput = document.getElementById('videoFile');
    if (!fileInput.files.length) { toast('请先选择一个视频文件', 'error'); return; }
    const button = this;
    button.disabled = true;
    button.textContent = '上传中…';
    const form = new FormData();
    form.append('file', fileInput.files[0]);
    if (currentSession) form.append('session_id', String(currentSession.id));
    try {
      const task = await api('/api/detection/video', { method: 'POST', body: form });
      document.getElementById('videoStatus').textContent = '任务已提交，正在后台检测…';
      document.getElementById('videoProgress').style.width = '0%';
      document.getElementById('videoBox').innerHTML = '<div>检测进行中，请稍候…</div>';
      log('已提交视频检测任务：' + task.task_id);
      pollVideo(task.task_id);
    } catch (err) {
      toast(err.message, 'error');
    } finally {
      button.disabled = false;
      button.textContent = '提交检测任务';
    }
  });

  function pollVideo(taskId) {
    clearInterval(videoPollTimer);
    videoPollTimer = setInterval(async function () {
      try {
        const task = await api('/api/detection/video/' + taskId);
        document.getElementById('videoProgress').style.width = (task.progress || 0) + '%';
        document.getElementById('videoStatus').innerHTML =
          '<div>已处理 ' + task.processed_frames + ' / ' + task.total_frames + ' 帧，'
          + '已检测 ' + task.detected_frames + ' 帧，进度 ' + Number(task.progress || 0).toFixed(1) + '%</div>'
          + '<div>已用时间 ' + fmtSeconds(task.elapsed_seconds)
          + '，平均 ' + Number(task.fps || 0).toFixed(1) + ' FPS'
          + '，' + (task.eta_seconds === null || task.eta_seconds === undefined
            ? '正在估算剩余时间' : '预计剩余 ' + fmtSeconds(task.eta_seconds))
          + '，运行设备 ' + (task.device ? String(task.device).toUpperCase() : '--') + '</div>';
        if (task.status === 'finished') {
          clearInterval(videoPollTimer);
          document.getElementById('videoBox').innerHTML = task.result_video_url
            ? '<video controls src="' + task.result_video_url + '"></video>'
            : '<div>检测完成，但结果视频不可用</div>';
          document.getElementById('videoStatus').innerHTML =
            '<div>检测完成：共处理 ' + task.processed_frames + ' 帧，其中检测 ' + task.detected_frames + ' 帧，'
            + '平均专注度 ' + (task.avg_attention === null ? '--' : task.avg_attention + '%') + '</div>'
            + '<div>总耗时 ' + fmtSeconds(task.elapsed_seconds) + '，平均 '
            + Number(task.fps || 0).toFixed(1) + ' FPS，运行设备 '
            + (task.device ? String(task.device).toUpperCase() : '--') + '</div>';
          (task.attention_scores || []).forEach((score) => pushScore(score));
          toast('视频检测完成', 'success');
          log('视频检测完成，平均专注度 ' + task.avg_attention + '%');
        } else if (task.status === 'failed') {
          clearInterval(videoPollTimer);
          document.getElementById('videoStatus').textContent = '检测失败：' + (task.error || '未知错误');
          toast('视频检测失败：' + (task.error || ''), 'error');
        }
      } catch (err) {
        clearInterval(videoPollTimer);
        toast(err.message, 'error');
      }
    }, 2000);
  }

  /* ------------------------------ 实时课堂 ------------------------------ */
  const sourceSelect = document.getElementById('sourceSelect');
  sourceSelect.addEventListener('change', function () {
    document.getElementById('realtimeFile').style.display = sourceSelect.value === 'file' ? 'inline-block' : 'none';
  });

  function ensureLiveImage() {
    let image = document.getElementById('liveImage');
    if (!image) {
      liveBox.innerHTML = '';
      image = document.createElement('img');
      image.id = 'liveImage';
      liveBox.appendChild(image);
    }
    return image;
  }

  realtimeBtn.addEventListener('click', function () {
    if (realtimeRunning) { stopRealtime(false); return; }
    startRealtime().catch((err) => { toast(err.message, 'error'); stopRealtime(false); });
  });

  async function startRealtime() {
    if (!currentSession) { toast('请先开始课堂', 'error'); return; }
    const scheme = window.location.protocol === 'https:' ? 'wss://' : 'ws://';
    socket = new WebSocket(scheme + window.location.host + '/ws/classroom/' + currentSession.id);
    realtimeRunning = true;
    realtimeBtn.textContent = '停止实时检测';
    realtimeBtn.className = 'btn btn-danger';
    log('正在连接实时检测服务…');

    socket.onmessage = function (event) {
      let message = null;
      try { message = JSON.parse(event.data); } catch (err) { return; }
      if (message.type === 'ready') {
        log('实时检测已连接（课堂 ID ' + currentSession.id + '）');
        startSource().catch((err) => { toast(err.message, 'error'); log('启动视频源失败：' + err.message); });
        return;
      }
      if (message.type === 'result') {
        ensureLiveImage().src = message.frame;
        renderStats(message);
        pushScore(message.attention ? message.attention.score : null);
        awaitingFrame = false;
        return;
      }
      if (message.type === 'camera_started') { log('服务器摄像头已开启（设备 ' + message.device + '）'); return; }
      if (message.type === 'camera_stopped') { log('服务器摄像头已停止'); return; }
      if (message.type === 'error') { log('错误：' + message.message); toast(message.message, 'error'); }
    };
    socket.onclose = function (event) {
      if (realtimeRunning) {
        log('实时检测连接已关闭（代码 ' + event.code + '）');
        stopRealtime(false);
      }
    };
    socket.onerror = function () { log('实时检测连接发生错误'); };
  }

  async function startSource() {
    const mode = sourceSelect.value;
    if (mode === 'server') {
      socket.send(JSON.stringify({ type: 'start_camera', device: 0 }));
      log('已请求服务器本机摄像头（如服务器无摄像头会返回错误）');
      return;
    }
    if (mode === 'file') {
      const file = document.getElementById('realtimeFile').files[0];
      if (!file) { throw new Error('请先选择本地视频文件'); }
      liveSource.srcObject = null;
      liveSource.src = URL.createObjectURL(file);
      liveSource.loop = true;
      await liveSource.play();
      log('已开始播放本地视频：' + file.name);
      startCaptureLoop();
      return;
    }
    mediaStream = await navigator.mediaDevices.getUserMedia({ video: { width: { ideal: 1280 } }, audio: false });
    liveSource.srcObject = mediaStream;
    await liveSource.play();
    log('浏览器摄像头已开启，开始推送画面（需在浏览器中授权摄像头）');
    startCaptureLoop();
  }

  function startCaptureLoop() {
    clearInterval(captureTimer);
    captureTimer = setInterval(function () {
      if (!socket || socket.readyState !== WebSocket.OPEN || awaitingFrame) return;
      const width = liveSource.videoWidth;
      const height = liveSource.videoHeight;
      if (!width || !height) return;
      const scale = Math.min(1, 960 / Math.max(width, height));
      captureCanvas.width = Math.round(width * scale);
      captureCanvas.height = Math.round(height * scale);
      captureCanvas.getContext('2d').drawImage(liveSource, 0, 0, captureCanvas.width, captureCanvas.height);
      const dataUrl = captureCanvas.toDataURL('image/jpeg', 0.7);
      awaitingFrame = true;
      socket.send(JSON.stringify({ type: 'frame', image: dataUrl }));
    }, 400);
  }

  function stopRealtime(silent) {
    realtimeRunning = false;
    clearInterval(captureTimer);
    captureTimer = null;
    awaitingFrame = false;
    if (socket && socket.readyState === WebSocket.OPEN) {
      try {
        socket.send(JSON.stringify({ type: 'stop_camera' }));
        socket.close();
      } catch (err) { /* 忽略关闭异常 */ }
    }
    socket = null;
    if (mediaStream) {
      mediaStream.getTracks().forEach((track) => track.stop());
      mediaStream = null;
    }
    liveSource.pause();
    if (liveSource.src && liveSource.src.startsWith('blob:')) {
      URL.revokeObjectURL(liveSource.src);
      liveSource.removeAttribute('src');
    }
    realtimeBtn.textContent = '开始实时检测';
    realtimeBtn.className = 'btn btn-primary';
    if (!silent) log('实时检测已停止');
  }

  document.addEventListener('tab-shown', function (event) {
    if (event.detail.tab !== 'realtime') stopRealtime(true);
  });

  renderBehaviorGrid({});
  Chart.line(document.getElementById('liveTrend'), { labels: [], values: [], height: 140, emptyText: '暂无专注度数据' });
  loadCourses();
});
